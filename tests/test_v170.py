"""1.7.0: storage card, notes history, short pairing codes (the phone pairing itself is in test_phone.py)."""

from pathlib import Path

from PIL import Image

from rhinos_buddy import i18n, layout as L, metrics as M, release_notes, sensors as S
from rhinos_buddy.widgets import Context, DiskWidget, make_widget

C = {"id": "C:", "mount": "C:\\", "total_gb": 931.5, "used_gb": 875.6, "free_gb": 55.9, "percent": 94.0, "removable": False}
D = {"id": "D:", "mount": "D:\\", "total_gb": 1863.0, "used_gb": 402.0, "free_gb": 1461.0, "percent": 21.6, "removable": False}
E = {"id": "E:", "mount": "E:\\", "total_gb": 58.0, "used_gb": 9.0, "free_gb": 49.0, "percent": 15.5, "removable": True}


class FakeMetrics:
    def __init__(self, **extra):
        self.data = {"drives": [C, D, E], "disk_temps": [{"name": "Samsung SSD 980", "temp": 39.0, "used": 94.0},
                                                         {"name": "WD Blue", "temp": 33.0, "used": 21.0}],
                     "disk_read_kbs": 12400.0, "disk_write_kbs": 850.0, **extra}

    def get(self):
        return self.data


def widget(metrics=None, w=300, h=150, **cfg):
    base = {"type": "disk", "w": w, "h": h, "view": "cartao", "size": 18, "text": "white", "muted": "#8b95a7", "color": "#ffa94d",
            "show_percent": True, "show_used": True, "show_bar": True}
    return make_widget({**base, **cfg}, Context(metrics=metrics or FakeMetrics(), base_dir=Path(".")))


def drawn(wd) -> bytes:
    wd.update()
    return wd.render().tobytes()


# ---------------------------------------------------------------- drives
def test_list_drives_reports_sane_numbers():
    ds = M.list_drives()
    assert ds, "this machine has at least one readable drive"
    for d in ds:
        assert d["total_gb"] > 0 and 0 <= d["percent"] <= 100 and d["used_gb"] >= 0 and d["free_gb"] >= 0
        assert set(d) >= {"id", "mount", "total_gb", "used_gb", "free_gb", "percent", "removable"}


def test_match_drive_understands_how_people_write_it():
    ds = [C, D, E]
    assert M.match_drive(ds, "d")["id"] == "D:" and M.match_drive(ds, "D:\\")["id"] == "D:" and M.match_drive(ds, " e: ")["id"] == "E:"
    assert M.match_drive(ds, "Z:") is None                       # not there: the card says so instead of showing another drive
    assert M.match_drive([], "C") is None
    assert M.match_drive(ds, "")["id"] in {"C:", "D:", "E:"} and M.match_drive(ds, "auto") is not None


def test_pick_disk_temp_rules():
    temps = [{"name": "Samsung SSD 980", "temp": 39.0, "used": 94.0}, {"name": "WD Blue", "temp": 33.0, "used": 21.0}]
    assert M.pick_disk_temp(temps, C, "wd") == 33.0                  # the name the user typed wins
    assert M.pick_disk_temp(temps, C, "nothing like it") != M.pick_disk_temp(temps, C, "nothing like it")  # NaN: no such disk
    assert M.pick_disk_temp(temps[:1], D, "") == 39.0                # a single disk is that disk
    assert M.pick_disk_temp(temps, C, "") == 39.0 and M.pick_disk_temp(temps, D, "") == 33.0   # closest "Used Space"
    assert M.pick_disk_temp([], C, "") != M.pick_disk_temp([], C, "")
    assert M.pick_disk_temp(temps, {**C, "percent": 60.0}, "") != M.pick_disk_temp(temps, {**C, "percent": 60.0}, "")  # ambiguous: no guess


def test_parse_lhm_reads_storage_temperatures():
    tree = {"Text": "Sensor", "Children": [{"Text": "PC", "Children": [
        {"Text": "Samsung SSD 980", "Children": [
            {"Text": "Temperatures", "Children": [{"Text": "Temperature", "Value": "39,0 °C", "Children": []}]},
            {"Text": "Load", "Children": [{"Text": "Used Space", "Value": "94,0 %", "Children": []}]}]},
        {"Text": "Example CPU", "Children": [
            {"Text": "Load", "Children": [{"Text": "CPU Total", "Value": "5,0 %", "Children": []}, {"Text": "Used Space", "Value": "1 %", "Children": []}]},
            {"Text": "Temperatures", "Children": [{"Text": "Core", "Value": "40,0 °C", "Children": []}]}]}]}]}
    r = S.parse_lhm(tree)
    assert r["disk_temps"] == [{"name": "Samsung SSD 980", "temp": 39.0, "used": 94.0}]   # the CPU is not a disk


# ---------------------------------------------------------------- the widget
def test_disk_card_draws_and_follows_the_numbers():
    a = drawn(widget(drive="C:"))
    assert Image.frombytes("RGBA", (300, 150), a).getbbox()
    assert drawn(widget(drive="D:")) != a                              # another drive, another picture
    m = FakeMetrics()
    wd = widget(m, drive="C:")
    first = drawn(wd)
    m.data = {**m.data, "drives": [{**C, "percent": 50.0, "used_gb": 465.0, "free_gb": 466.0}, D, E]}
    assert wd.update() is True and wd.render().tobytes() != first
    assert wd.update() is False                                        # nothing changed: nothing redrawn


def test_every_figure_is_optional():
    base = drawn(widget(drive="C:"))
    for opt in ("show_free", "show_temp", "show_rw"):
        assert drawn(widget(drive="C:", **{opt: True})) != base, opt   # switching it on changes the card
    assert drawn(widget(drive="C:", show_bar=False)) != base
    assert drawn(widget(drive="C:", radial=True)) != base
    assert drawn(widget(drive="C:", show_percent=False, show_used=False, show_bar=False)) != base
    # all figures off still draws the title and does not crash
    assert Image.frombytes("RGBA", (300, 150), drawn(widget(drive="C:", show_percent=False, show_used=False, show_bar=False))).getbbox()


def test_list_view_and_removable_drives():
    one = drawn(widget(view="lista", h=110))
    assert drawn(widget(view="lista", h=110, show_removable=True)) != one       # the USB stick appears only when asked
    assert drawn(widget(metrics=FakeMetrics(drives=[]), view="lista", h=110))   # no drives at all: still draws


def test_missing_drive_and_missing_data_do_not_crash():
    assert drawn(widget(drive="Z:")) != drawn(widget(drive="C:"))
    assert drawn(widget(metrics=FakeMetrics(drives=[]), drive="C:"))
    wd = DiskWidget({"w": 200, "h": 100, "size": 16, "text": "white", "muted": "#888", "color": "#fa4"}, Context(metrics=None, base_dir=Path(".")))
    wd.update()
    wd.render()


# ---------------------------------------------------------------- the module
def test_storage_module_is_in_the_catalog_with_optional_everything():
    mod = next(m for m in L.catalog()["modules"] if m["id"] == "armazenamento")
    assert mod["size"] == [4, 3]
    keys = {o["key"] for o in mod["options"]}
    assert {"view", "drive", "show_percent", "show_used", "show_free", "show_temp", "disk_sensor", "show_rw", "show_bar", "bar_style", "show_removable", "color"} <= keys
    defaults = {o["key"]: o["default"] for o in mod["options"]}
    assert defaults["show_temp"] is False and defaults["show_rw"] is False and defaults["show_removable"] is False   # heavier extras start off


def test_storage_module_builds_a_disk_widget(tmp_path):
    lay = L.normalize({"pages": [{"slots": [{"module": "armazenamento", "col": 0, "row": 0, "w": 4, "h": 3,
                                              "options": {"drive": "D", "show_temp": True, "bar_style": "radial"}}]}]}, tmp_path)
    ws = L.to_config(lay, tmp_path)["page"][0]["widget"]
    disk = [w for w in ws if w["type"] == "disk"]
    assert len(disk) == 1 and disk[0]["drive"] == "D" and disk[0]["show_temp"] is True and disk[0]["radial"] is True
    make_widget(disk[0], Context(metrics=FakeMetrics(), base_dir=tmp_path))


def test_storage_card_texts_exist_in_english():
    i18n.set_lang("en")
    try:
        label = next(m for m in L.catalog()["modules"] if m["id"] == "armazenamento")["label"]
        assert label != "Armazenamento (unidades de disco)" and "Storage" in label
    finally:
        i18n.set_lang("pt")


# ---------------------------------------------------------------- what's-new history
def test_history_lists_every_version_newest_first_in_both_languages():
    for lang in ("pt", "en"):
        h = release_notes.history(lang)
        versions = [n["version"] for n in h]
        assert versions == sorted(versions, key=lambda v: tuple(int(x) for x in v.split(".")), reverse=True) and len(versions) >= 8
        assert all(n["items"] and n["title"] for n in h)
    for v, n in release_notes.NOTES.items():
        assert n.get("items_en"), f"{v} has no English notes"
        assert n["title"].isascii(), f"{v} title must be English"


def test_whatsnew_endpoint_carries_the_history(tmp_path):
    from rhinos_buddy.app import App  # noqa: F401  (import check: the state builds it through App.whatsnew)
    assert release_notes.history("pt")[0]["version"] == max(release_notes.NOTES, key=lambda v: tuple(int(x) for x in v.split(".")))


# ---------------------------------------------------------------- friendly name (mDNS), 1.8.0
import socket
import struct

from rhinos_buddy import mdns


def _query(name: str, qtype: int = 1, qclass: int = 1, ident: int = 0) -> bytes:
    labels = b"".join(bytes([len(p)]) + p.encode() for p in name.split(".")) + b"\x00"
    return struct.pack("!HHHHHH", ident, 0, 1, 0, 0, 0) + labels + struct.pack("!HH", qtype, qclass)


def test_mdns_answers_only_for_its_own_name_with_the_lan_address():
    r = mdns.build_answer(_query("Rhinos-Buddy.local"), mdns.NAME, "192.168.1.20")
    assert r and r[:2] == b"\x00\x00" and r[2:4] == b"\x84\x00" and r.endswith(socket.inet_aton("192.168.1.20"))
    assert struct.unpack("!H", r[6:8])[0] == 1                                  # one answer: the A record
    assert mdns.build_answer(_query("other-pc.local"), mdns.NAME, "192.168.1.20") is None
    assert mdns.build_answer(_query("rhinos-buddy.local", qtype=16), mdns.NAME, "192.168.1.20") is None   # TXT: nothing to say
    assert mdns.build_answer(_query("rhinos-buddy.local", qclass=0x8001), mdns.NAME, "10.0.0.5")           # QU bit is fine


def test_mdns_says_no_aaaa_and_echoes_the_id_for_legacy_clients():
    r = mdns.build_answer(_query("rhinos-buddy.local", qtype=28, ident=0x1234), mdns.NAME, "192.168.1.20", legacy=True)
    assert r[:2] == b"\x12\x34" and struct.unpack("!H", r[6:8])[0] == 1 and struct.pack("!H", mdns.TYPE_NSEC) in r


def test_mdns_ignores_garbage_and_responses():
    for junk in (b"", b"\x00" * 5, b"\xff" * 40, _query("rhinos-buddy.local")[:20], b"\x00\x00\x84\x00" + b"\x00" * 8):
        assert mdns.build_answer(junk, mdns.NAME, "192.168.1.20") is None


def test_friendly_name_is_optional_and_falls_back_to_the_ip(tmp_path):
    from rhinos_buddy import appdata, phone
    from tests.test_phone import free_port
    acc = phone.PhoneAccess(tmp_path, lambda: b"", page=b"x", main_port=free_port(), bind_ip="127.0.0.1")
    try:
        assert acc.friendly is False and acc.start()
        st = acc.status()
        assert "127.0.0.1" in st["url"] and st["friendly_ok"] is False
        assert acc.host_ok(f"rhinos-buddy.local:{acc.port}") is False            # off: that name is not accepted
        acc.friendly = True
        acc.responder = type("R", (), {"running": True, "stop": lambda s: None})()   # pretend the responder works
        st = acc.status()
        assert st["url"].startswith(f"http://rhinos-buddy.local:{acc.port}/p?c=") and st["ip_url"].startswith("http://127.0.0.1:")
        assert acc.host_ok(f"rhinos-buddy.local:{acc.port}") and not acc.host_ok(f"evil.local:{acc.port}")
        acc.configure(enabled=True, friendly=False)
        assert appdata.load_prefs(tmp_path)["phone_friendly"] is False and "127.0.0.1" in acc.status()["url"]
    finally:
        acc.stop()
