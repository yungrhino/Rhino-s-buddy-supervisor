import sys
import time
import types

import pytest
from PIL import Image

from rhinos_buddy import appdata, autostart, runner as R
from rhinos_buddy import layout as L


class FakePanel:
    instances: list = []
    fail_open = None  # exception to raise on open

    def __init__(self, port="auto", orientation="landscape", brightness=None, invert_brightness=True, **_):
        self.orientation, self.brightness = orientation, brightness
        self.width, self.height = (480, 320) if "landscape" in orientation else (320, 480)
        self.blits, self.closed, self.explode = [], False, False
        self.brightness_calls = []
        self.port_name = "COM3"
        FakePanel.instances.append(self)

    def open(self):
        if FakePanel.fail_open:
            raise FakePanel.fail_open

    def close(self):
        self.closed = True

    def set_brightness(self, p):
        self.brightness_calls.append(p)

    def blit(self, img, x=0, y=0):
        if self.explode:
            raise OSError("device unplugged")
        self.blits.append((x, y, *img.size))


@pytest.fixture
def make_runner(tmp_path, monkeypatch):
    FakePanel.instances, FakePanel.fail_open = [], None
    monkeypatch.setattr(R, "RevADisplay", FakePanel)
    monkeypatch.setattr(R, "RETRY_SECONDS", 0.2)
    made = []

    def make(hardware=True, **dev):
        lay = L.default_layout()
        lay["device"].update(fps=30, **dev)
        lay["sensors"] = {"nvidia_smi": False, "lhm": False, "lhm_url": lay["sensors"]["lhm_url"]}
        r = R.Runner(tmp_path, lay, hardware=hardware)
        r.start()
        made.append(r)
        return r

    yield make
    for r in made:
        r.stop()


def wait(cond, timeout=5.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_connects_and_paints_the_panel(make_runner):
    r = make_runner()
    assert wait(lambda: r.status()["connected"])
    assert r.status()["port"] == "COM3"
    assert wait(lambda: FakePanel.instances and FakePanel.instances[0].blits)
    assert FakePanel.instances[0].blits[0][2:] == (480, 320)  # first paint = full frame
    assert r.preview_png()[:4] == b"\x89PNG"


def test_works_without_a_panel_and_keeps_retrying(make_runner):
    FakePanel.fail_open = RuntimeError("Could not auto-detect the screen")
    r = make_runner()
    assert wait(lambda: "não encontrada" in r.status()["message"])
    assert not r.status()["connected"]
    assert r.preview_png()[:4] == b"\x89PNG"  # preview keeps working
    FakePanel.fail_open = None  # plug it in
    assert wait(lambda: r.status()["connected"])


def test_unplug_and_replug_repaints_everything(make_runner):
    r = make_runner()
    assert wait(lambda: r.status()["connected"])
    first = FakePanel.instances[0]
    first.explode = True  # cable pulled
    assert wait(lambda: len(FakePanel.instances) >= 2)  # the runner noticed and opened a new link
    assert first.closed and wait(lambda: r.status()["connected"])
    second = FakePanel.instances[-1]
    assert wait(lambda: second.blits and second.blits[0][2:] == (480, 320))  # full repaint on the new link


def test_layout_change_is_applied_live_without_reconnect(make_runner):
    r = make_runner()
    assert wait(lambda: r.status()["connected"])
    n = len(FakePanel.instances)
    lay = r.layout.copy()
    lay["pages"] = [{"name": "x", "duration": 10, "slots": [
        {"module": "text", "col": 0, "row": 0, "w": 12, "h": 8, "options": {"text": "ola", "size": 60}}]}]
    norm = r.apply(lay)
    assert norm["pages"][0]["slots"][0]["module"] == "text"
    assert wait(lambda: r.engine.pages[0].widgets and r.engine.pages[0].widgets[0].type_name == "text")
    assert len(FakePanel.instances) == n  # no reconnection


def test_brightness_change_does_not_reconnect(make_runner):
    r = make_runner()
    assert wait(lambda: r.status()["connected"])
    lay = r.layout.copy()
    lay["device"] = dict(lay["device"], brightness=30)
    r.apply(lay)
    assert wait(lambda: FakePanel.instances[0].brightness_calls == [30])
    assert len(FakePanel.instances) == 1


def test_rotation_change_rebuilds_for_new_size(make_runner):
    r = make_runner()
    assert wait(lambda: r.status()["connected"])
    lay = r.layout.copy()
    lay["device"] = dict(lay["device"], orientation="portrait")
    r.apply(lay)
    assert wait(lambda: r.tee.height == 480)
    assert wait(lambda: r.status()["connected"] and FakePanel.instances[-1].orientation == "portrait")
    assert FakePanel.instances[0].closed


def test_preview_only_mode_never_touches_hardware(make_runner):
    r = make_runner(hardware=False)
    time.sleep(0.3)
    assert FakePanel.instances == [] and not r.status()["connected"]


# --------------------------------------------------------------- autostart / appdata
def test_autostart_command_line():
    assert autostart.command_line(True, r"C:\Apps\RhinosBuddySupervisor.exe") == r'"C:\Apps\RhinosBuddySupervisor.exe" --background'
    cmd = autostart.command_line(False, r"C:\Python\python.exe", r"C:\p\run_app.py")
    assert cmd == r'"C:\Python\pythonw.exe" "C:\p\run_app.py" --background'


def test_autostart_registry_roundtrip(monkeypatch):
    store = {}

    class K:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    wr = types.SimpleNamespace(
        HKEY_CURRENT_USER=1, KEY_READ=1, KEY_SET_VALUE=2, REG_SZ=1,
        OpenKey=lambda *a: K(),
        SetValueEx=lambda k, n, r, t, v: store.__setitem__(n, v),
        DeleteValue=lambda k, n: store.pop(n) if n in store else (_ for _ in ()).throw(FileNotFoundError()),
        QueryValueEx=lambda k, n: (store[n], 1) if n in store else (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(autostart, "_winreg", lambda: wr)
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    assert autostart.is_enabled() and "--background" in store["RhinosBuddySupervisor"]
    autostart.set_enabled(False)
    assert not autostart.is_enabled()
    autostart.set_enabled(False)  # deleting twice is fine


def test_autostart_refuses_on_non_windows(monkeypatch):
    monkeypatch.setattr(autostart, "supported", lambda: False)
    assert autostart.is_enabled() is False
    with pytest.raises(RuntimeError):
        autostart.set_enabled(True)


def test_media_upload_validation(tmp_path):
    from io import BytesIO
    buf = BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, "PNG")
    name = appdata.save_media(tmp_path, "Minha Foto!.png", buf.getvalue())
    assert name.endswith(".png") and (tmp_path / "media" / name).is_file() and " " not in name
    assert appdata.list_media(tmp_path) == [name]
    with pytest.raises(ValueError):
        appdata.save_media(tmp_path, "x.exe", b"MZ")
    with pytest.raises(ValueError):
        appdata.save_media(tmp_path, "fake.png", b"not an image")
    with pytest.raises(ValueError):
        appdata.save_media(tmp_path, "big.png", b"0" * (appdata.MAX_MEDIA_BYTES + 1))
    assert appdata.save_media(tmp_path, "../../evil.png", buf.getvalue()).startswith("evil-")  # path stripped


def test_layout_persistence_is_atomic_and_tolerant(tmp_path):
    lay = L.default_layout()
    lay["device"]["brightness"] = 42
    appdata.save_layout(tmp_path, lay)
    assert appdata.load_layout(tmp_path)["device"]["brightness"] == 42
    (tmp_path / "layout.json").write_text("{ corrupted", "utf-8")
    assert appdata.load_layout(tmp_path) == L.default_layout()  # corrupted file -> defaults, no crash


def test_pinned_page_holds_rotation_and_resumes(make_runner):
    r = make_runner()
    lay = r.layout.copy()
    lay["pages"] = [{"name": "A", "duration": 3, "slots": []}, {"name": "B", "duration": 3, "slots": [
        {"module": "text", "col": 0, "row": 0, "w": 12, "h": 8, "options": {"text": "B"}}]}]
    r.apply(lay)
    assert wait(lambda: len(r.engine.pages) == 2)
    r.focus(1)
    assert wait(lambda: r.engine.page_index == 1 and r.engine.pinned)
    time.sleep(0.4)
    assert r.engine.page_index == 1  # stays on the edited page
    r._focus = (1, time.monotonic() - 100)  # editor went quiet
    assert wait(lambda: not r.engine.pinned)


def test_old_start_with_windows_entry_is_migrated(monkeypatch):
    store = {"Subscreen": r'"C:\old\Subscreen.exe" --background'}

    class K:
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def delete(k, n):
        if n not in store:
            raise FileNotFoundError()
        del store[n]

    wr = types.SimpleNamespace(
        HKEY_CURRENT_USER=1, KEY_READ=1, KEY_SET_VALUE=2, REG_SZ=1, OpenKey=lambda *a: K(),
        SetValueEx=lambda k, n, r, t, v: store.__setitem__(n, v), DeleteValue=delete,
        QueryValueEx=lambda k, n: (store[n], 1) if n in store else (_ for _ in ()).throw(FileNotFoundError()),
    )
    monkeypatch.setattr(autostart, "supported", lambda: True)
    monkeypatch.setattr(autostart, "_winreg", lambda: wr)
    assert autostart.migrate_legacy() is True
    assert "Subscreen" not in store and "--background" in store["RhinosBuddySupervisor"]
    assert "Subscreen.exe" not in store["RhinosBuddySupervisor"]            # points at this program now
    assert autostart.migrate_legacy() is False                              # nothing left to migrate
    store.clear()
    assert autostart.migrate_legacy() is False and not store                # never enables by itself


def test_old_settings_folder_is_copied_once(tmp_path):
    old, new = tmp_path / "Subscreen", tmp_path / "RhinosBuddySupervisor"
    (old / "media").mkdir(parents=True)
    (old / "layout.json").write_text('{"version": 1, "theme": {"font": "Arial"}}', "utf-8")
    (old / "media" / "bg.png").write_bytes(b"png")
    (new / "media").mkdir(parents=True)
    assert appdata.migrate_legacy_home(new, [old]) is True
    assert (new / "layout.json").read_text("utf-8") == (old / "layout.json").read_text("utf-8")
    assert (new / "media" / "bg.png").read_bytes() == b"png" and (old / "layout.json").exists()  # copied, not moved
    (new / "layout.json").write_text("{}", "utf-8")   # the user already changed things
    assert appdata.migrate_legacy_home(new, [old]) is False
    assert (new / "layout.json").read_text("utf-8") == "{}"                  # never overwritten
    assert appdata.migrate_legacy_home(tmp_path / "x", [tmp_path / "missing"]) is False


def test_app_identity_is_renamed():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    leftovers = []
    for f in list(root.rglob("*.py")) + list(root.rglob("*.html")) + list(root.rglob("*.md")) + list(root.rglob("*.bat")):
        if "__pycache__" in f.parts or f.name in ("test_runner.py", "appdata.py", "autostart.py", "Desinstalar Rhinos Buddy Supervisor.bat"):  # these clean up / migrate the old name on purpose
            continue
        for n, line in enumerate(f.read_text("utf-8").splitlines(), 1):
            if re.search(r"subscreen", line, re.I) and "nome antigo" not in line and "old name" not in line:
                leftovers.append(f"{f.name}:{n}: {line.strip()[:80]}")
    assert not leftovers, leftovers


def test_license_collector_gathers_texts_and_reports_missing(tmp_path):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    import collect_licenses as C
    text, missing = C.collect(["Pillow", "numpy", "definitely-not-installed-pkg"])
    assert "pillow" in text.lower() and "numpy" in text.lower() and "permission" in text.lower()
    assert missing == ["definitely-not-installed-pkg"]
    assert C.main([str(tmp_path / "out")]) == 0
    out = tmp_path / "out"
    assert (out / "THIRD_PARTY_LICENSES.txt").stat().st_size > 1000
    assert (out / "LICENSE").is_file() and (out / "THIRD_PARTY_NOTICES.md").is_file()


def test_uninstaller_is_safe_and_shipped():
    """The uninstaller must keep CRLF line ends, never delete the source tree, and be copied into the packaged folder."""
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    bat = root / "Desinstalar Rhinos Buddy Supervisor.bat"
    raw = bat.read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")        # CRLF only
    assert all(c < 128 for c in raw)                                            # no code-page surprises in cmd
    text = raw.decode("ascii")
    assert "RhinosBuddySupervisor.exe" in text and "if not defined PACKAGED goto semexe" in text   # folder removal only for the packaged build
    assert text.count("rmdir /s /q") == 2 and "%DATADIR%" in text               # data is removed only in the "desinstalar" branch
    assert "RhinosBuddySupervisor /f" in text and "/api/quit" in text
    build = (root / "build_exe.bat").read_text("utf-8")
    assert "Desinstalar Rhinos Buddy Supervisor.bat" in build and "README_v*.md" in build and "README.md" in build


def test_release_readme_matches_the_current_version():
    from pathlib import Path
    from rhinos_buddy import __version__, __version_title__
    root = Path(__file__).resolve().parent.parent
    files = sorted(p.name for p in root.glob("README_v*.md"))
    assert files == [f"README_v{__version__}.md"]                               # only the current version's notes at the root
    text = (root / files[0]).read_text("utf-8")
    assert __version__ in text and __version_title__ in text
    assert (root / "docs" / "releases" / f"v{__version__}.md").read_text("utf-8") == text
    assert f"| {__version__} |" in (root / "docs" / "releases" / "HISTORICO.md").read_text("utf-8")
    from rhinos_buddy import release_notes
    assert release_notes.notes_for(__version__)["title"] == __version_title__
