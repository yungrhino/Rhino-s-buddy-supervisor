import pytest
import numpy as np
from pathlib import Path

from rhinos_buddy import audio, layout as L, nowplaying
from rhinos_buddy.engine import Engine
from rhinos_buddy.devices import SimulatorDisplay
from rhinos_buddy.metrics import Metrics

RATE = 48000


def tone(freq, n=audio.BLOCK, amp=0.5):
    t = np.arange(n) / RATE
    return (amp * np.sin(2 * np.pi * freq * t)).astype(np.float32)


class Clock:
    t = 100.0

    def __call__(self):
        return self.t


def make_analyzer():
    a = audio.Analyzer()
    a.clock = Clock()
    a.touch = lambda: None  # never start the real capture thread in tests
    return a


def test_tone_lights_the_matching_band():
    a = make_analyzer()
    a.process(tone(1000), RATE, now=a.clock())
    lv = a.levels(16)
    edges = audio.band_edges(16)
    expected = int(np.searchsorted(edges, 1000) - 1)
    assert int(np.argmax(lv)) == expected
    assert lv[expected] > 0.9
    assert lv[0] < 0.5 and lv[-1] < 0.5  # far bands stay low


def test_bass_tone_goes_to_first_bands():
    a = make_analyzer()
    a.process(tone(60), RATE, now=a.clock())
    assert int(np.argmax(a.levels(16))) <= 1


def test_silence_and_stale_audio_are_flat():
    a = make_analyzer()
    assert not a.levels(8).any()                       # nothing captured yet
    a.process(np.zeros(audio.BLOCK, dtype=np.float32), RATE, now=a.clock())
    assert a.levels(8).max() < 0.05
    a.process(tone(500), RATE, now=a.clock())
    a.clock.t += 2.0                                   # capture stopped (silent loopback sends nothing)
    assert not a.levels(8).any() and a.beat_strength() == 0.0


def test_beat_detector_fires_on_kicks_not_on_steady_bass():
    d = audio.BeatDetector()
    now, beats = 0.0, 0
    for i in range(60):  # steady bass: at most the first onset
        beats += d.feed(0.2, now)
        now += 0.043
    assert beats <= 1
    d = audio.BeatDetector()
    beats = 0
    for i in range(80):  # kick every ~0.5 s
        kick = i % 12 == 0
        beats += d.feed(0.9 if kick else 0.1, i * 0.043)
    assert 5 <= beats <= 7


def test_analyzer_beat_strength_decays():
    a = make_analyzer()
    for i in range(30):
        a.process(tone(80, amp=0.05), RATE, now=a.clock())
        a.clock.t += 0.043
    a.process(tone(80, amp=0.9), RATE, now=a.clock())
    assert a.beat_strength() == 1.0
    assert a.beat_strength() < 1.0


def test_stereo_input_is_mixed_down():
    st = np.stack([tone(440), tone(440)], axis=1)
    assert audio.analyze_block(st).shape == audio.analyze_block(tone(440)).shape


def test_missing_soundcard_package_reports_instead_of_crashing(monkeypatch):
    import builtins
    real = builtins.__import__

    def fake(name, *a, **k):
        if name == "soundcard":
            raise ImportError("no soundcard")
        return real(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake)
    a = audio.Analyzer()
    a._run()
    assert a.state == "unavailable" and "soundcard" in a.message


# --------------------------------------------------------------------------- now playing
def test_spotify_title_parsing():
    assert nowplaying.parse_spotify_title("The Weeknd - Blinding Lights") == {
        "title": "Blinding Lights", "artist": "The Weeknd", "app": "Spotify", "playing": True}
    assert nowplaying.parse_spotify_title("Spotify Free") == {}
    assert nowplaying.parse_spotify_title("") == {}
    assert nowplaying.parse_spotify_title("Daft Punk - One More Time - Radio Edit")["title"] == "One More Time - Radio Edit"


def test_nowplaying_poll_survives_errors():
    def boom():
        raise RuntimeError("x")
    n = nowplaying.NowPlaying(fetch=boom)
    n.poll_once()
    assert n.data == {}
    n.fetch = lambda: {"title": "A", "artist": "B", "playing": True}
    n.poll_once()
    assert n.data["title"] == "A"


# --------------------------------------------------------------------------- layout + widgets
class FakeAudio:
    def __init__(self):
        self.t = 0

    def levels(self, n, sens=50):
        self.t += 1
        return np.linspace(1, 0.1, n) * (0.5 + 0.5 * (self.t % 2))

    def beat_strength(self):
        return 1.0


class FakeNP:
    def __init__(self, info):
        self.info = info

    def get(self):
        return self.info


def build(slots, tmp_path, info=None, orient="landscape"):
    lay = L.normalize({"device": {"orientation": orient}, "pages": [{"slots": slots}]}, tmp_path)
    disp = SimulatorDisplay(orientation=orient, output=tmp_path / "o.png")
    eng = Engine(L.to_config(lay, tmp_path), disp, metrics=Metrics({"nvidia_smi": False, "lhm": False}))
    eng.ctx.audio = FakeAudio()
    eng.ctx.nowplaying = FakeNP(info if info is not None else {"title": "Song", "artist": "Artist", "playing": True})
    disp.open()
    return lay, eng, disp


def slot(**o):
    return {"module": "musica", "col": 0, "row": 0, "w": 6, "h": 3, "options": o}


def test_music_module_is_in_catalog_and_options_are_clamped(tmp_path):
    cat = L.catalog()
    mus = [m for m in cat["modules"] if m["id"] == "musica"]
    assert len(mus) == 1 and mus[0]["group"] == "Música"
    lay = L.normalize({"pages": [{"slots": [slot(bars=999, sensitivity=-5, viz_style="nope")]}]}, tmp_path)
    o = lay["pages"][0]["slots"][0]["options"]
    assert o["bars"] == 32 and o["sensitivity"] == 1 and o["viz_style"] == "barras"


def test_music_slot_builds_track_and_visualizer_widgets():
    lay = L.normalize({"pages": [{"slots": [slot()]}]})
    cfg = L.to_config(lay, Path("."))
    types = [w["type"] for w in cfg["page"][0]["widget"]]
    assert types.count("nowplaying") == 1 and types.count("visualizer") == 1
    only = L.to_config(L.normalize({"pages": [{"slots": [slot(show_viz=False)]}]}), Path("."))["page"][0]["widget"]
    assert [w["type"] for w in only] == ["nowplaying"]
    only = L.to_config(L.normalize({"pages": [{"slots": [slot(show_track=False)]}]}), Path("."))["page"][0]["widget"]
    assert [w["type"] for w in only] == ["visualizer"]
    none = L.to_config(L.normalize({"pages": [{"slots": [slot(show_track=False, show_viz=False)]}]}), Path("."))["page"][0]["widget"]
    assert none == []


def test_visualizer_redraw_rate_respects_the_usb_budget():
    def interval(w, h):
        s = {"module": "musica", "col": 0, "row": 0, "w": w, "h": h, "options": {"show_track": False}}
        wd = L.to_config(L.normalize({"pages": [{"slots": [s]}]}), Path("."))["page"][0]["widget"][0]
        return wd["interval"], wd["w"] * wd["h"] * 2 / wd["interval"]
    small_i, small_rate = interval(2, 1)
    big_i, big_rate = interval(12, 4)
    assert small_i < big_i
    assert big_rate <= L.USB_BUDGET * 1.05 or big_i == 1.0


def test_visualizer_all_styles_draw_and_stay_inside_their_box(tmp_path):
    for style in ("barras", "espelho", "circular", "pulso"):
        lay, eng, disp = build([slot(viz_style=style, show_track=False)], tmp_path)
        eng.step(1.0)
        eng.step(2.0)
        px = np.asarray(disp.frame.convert("RGB"))
        assert (px.sum(axis=2) > 120).any(), style          # something coloured was drawn
        assert not (px[:, 250:].sum(axis=2) > 120).any(), style  # nothing outside the 6-column slot


def test_flat_signal_means_no_redraw():
    from rhinos_buddy.widgets import Context, VisualizerWidget

    class Flat(FakeAudio):
        def levels(self, n, sens=50):
            return np.zeros(n)

        def beat_strength(self):
            return 0.0
    w = VisualizerWidget({"w": 100, "h": 50, "bars": 8}, Context(metrics=None, base_dir=Path("."), audio=Flat()))
    assert w.update() is True    # first draw
    assert w.update() is False   # silence stays silent: zero USB traffic


def test_visualizer_falls_gradually(tmp_path):
    from rhinos_buddy.widgets import Context, VisualizerWidget

    class Burst(FakeAudio):
        def __init__(self):
            super().__init__()
            self.loud = True

        def levels(self, n, sens=50):
            return np.ones(n) if self.loud else np.zeros(n)

        def beat_strength(self):
            return 0.0
    a = Burst()
    w = VisualizerWidget({"w": 100, "h": 50, "bars": 8}, Context(metrics=None, base_dir=Path("."), audio=a))
    w.update()
    a.loud = False
    w.update()
    assert 0 < w._levels().max() < 1   # decays, does not snap to zero


def test_nowplaying_widget_shows_track_then_placeholder(tmp_path):
    lay, eng, disp = build([slot(show_viz=False)], tmp_path)
    eng.step(1.0)
    with_track = np.asarray(disp.frame.convert("L")).copy()
    assert (with_track > 100).any()
    eng.ctx.nowplaying.info = {}
    eng.step(10.0)
    after = np.asarray(disp.frame.convert("L"))
    assert (after != with_track).any()  # changed to the "Nada tocando" placeholder


def test_long_titles_are_cut_with_an_ellipsis():
    from PIL import Image, ImageDraw
    from rhinos_buddy.widgets import _ellipsize, load_font
    d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    f = load_font(None, 16)
    out = _ellipsize(d, "A very very long song title that cannot possibly fit", f, 100)
    assert out.endswith("…") and d.textlength(out, font=f) <= 100
    assert _ellipsize(d, "Short", f, 100) == "Short"


# --------------------------------------------------------------------------- radial option
def test_radial_option_switches_module_and_theme(tmp_path):
    def types(theme, opts):
        lay = {"theme": theme, "pages": [{"slots": [{"module": "cpu", "col": 0, "row": 0, "w": 4, "h": 3, "options": opts}]}]}
        return {w["type"] for w in L.to_config(L.normalize(lay, tmp_path), tmp_path)["page"][0]["widget"]}
    assert "radial" not in types({}, {}) and "bar" not in types({"bar_style": "radial"}, {"show_bar": True})
    assert "radial" in types({"bar_style": "radial"}, {})
    assert "radial" in types({}, {"bar_style": "radial"})            # module overrides theme
    assert "radial" not in types({"bar_style": "radial"}, {"bar_style": "barra"})


def test_radial_ring_follows_value_and_is_stable_within_a_unit():
    from rhinos_buddy.widgets import Context, RadialWidget
    m = type("M", (), {"get": lambda self: {"cpu": 50.0}})()
    w = RadialWidget({"w": 100, "h": 100, "metric": "cpu", "color": "#35c46d"}, Context(metrics=m, base_dir=Path(".")))
    assert w.update() is True and w.update() is False
    img = w.render()
    a = np.asarray(img)[..., 3]
    assert a.shape == (100, 100) and a[50, 50] == 0 and a.max() == 255  # hollow centre, solid ring


# --------------------------------------------------------------------------- expanded card
def _cover_bytes():
    import io
    from PIL import Image
    im = Image.new("RGB", (200, 120), (200, 30, 30))  # not square on purpose
    b = io.BytesIO()
    im.save(b, "JPEG")
    return b.getvalue()


def card_engine(tmp_path, info, **o):
    opts = {"track_layout": "capa", **o}
    lay, eng, disp = build([{"module": "musica", "col": 0, "row": 0, "w": 12, "h": 5, "options": opts}], tmp_path, info=info)
    return eng, disp


def test_card_layout_builds_a_capa_widget_with_progress():
    lay = L.normalize({"pages": [{"slots": [slot(track_layout="capa", show_viz=False)]}]})
    wd = L.to_config(lay, Path("."))["page"][0]["widget"]
    assert [w["type"] for w in wd] == ["nowplaying"] and wd[0]["mode"] == "capa" and wd[0]["interval"] <= 0.25  # sampled often: no second is skipped
    big = L.normalize({"pages": [{"slots": [{"module": "musica", "col": 0, "row": 0, "w": 12, "h": 6, "options": {"track_layout": "capa"}}]}]})
    assert [w["type"] for w in L.to_config(big, Path("."))["page"][0]["widget"]] == ["nowplaying", "visualizer"]
    small = L.normalize({"pages": [{"slots": [slot(track_layout="capa")]}]})  # 6x3: no room for a strip
    assert [w["type"] for w in L.to_config(small, Path("."))["page"][0]["widget"]] == ["nowplaying"]


def test_card_shows_cover_and_progress_that_advances(tmp_path):
    info = {"title": "T", "artist": "A", "playing": True, "position": 30.0, "duration": 120.0, "art": _cover_bytes(), "fetched_at": 0.0}
    eng, disp = card_engine(tmp_path, info, show_viz=False)
    eng.step(1.0)
    px = np.asarray(disp.frame.convert("RGB")).astype(int)
    red = (px[..., 0] > 150) & (px[..., 1] < 80)
    assert red[:200, :200].sum() > 5000          # the cover (left, square) was drawn
    assert not red[:, 220:].any()                # ... and only there
    from rhinos_buddy.widgets import Context, NowPlayingWidget
    ctx = Context(metrics=None, base_dir=Path("."), nowplaying=FakeNP(info))
    nw = NowPlayingWidget({"w": 300, "h": 120, "mode": "capa"}, ctx)
    nw.clock = lambda: 0.0
    assert nw.update() is True and nw.update() is False
    nw.clock = lambda: 5.0                        # five seconds later the bar must move
    assert nw.update() is True
    nw.clock = lambda: 500.0
    assert nw._position(info) == 120.0           # never past the end of the track


def test_card_without_cover_or_times_still_renders(tmp_path):
    eng, disp = card_engine(tmp_path, {"title": "Só texto", "artist": "Spotify", "playing": True})
    eng.step(1.0)
    assert (np.asarray(disp.frame.convert("L")) > 100).any()
    eng, disp = card_engine(tmp_path, {"title": "x", "playing": True, "art": b"not an image"})
    eng.step(1.0)  # corrupt cover bytes must not crash the screen loop


def test_nowplaying_ignores_data_when_not_playing():
    n = nowplaying.NowPlaying(fetch=lambda: {"title": "x", "playing": False})
    n.poll_once()
    assert n.data == {}


def test_mmss_formatting():
    from rhinos_buddy.widgets import _mmss
    assert _mmss(142) == "2:22" and _mmss(0) == "0:00" and _mmss(3725) == "1:02:05"


# --------------------------------------------------------------------------- hidden slots + rotation switch
def test_hidden_slot_is_not_drawn_but_is_kept():
    lay = L.normalize({"pages": [{"slots": [
        {"module": "clock", "col": 0, "row": 0, "w": 5, "h": 2, "hidden": True},
        {"module": "cpu", "col": 0, "row": 2, "w": 5, "h": 2}]}]})
    sl = lay["pages"][0]["slots"]
    assert sl[0]["hidden"] is True and sl[1]["hidden"] is False
    assert L.normalize(lay) == lay
    wd = L.to_config(lay, Path("."))["page"][0]["widget"]
    assert not any(w["type"] == "clock" for w in wd) and any(w["type"] != "clock" for w in wd)


def test_rotation_can_be_turned_off(tmp_path):
    pages = [{"duration": 3, "slots": [{"module": "clock", "col": 0, "row": 0, "w": 5, "h": 2}]},
             {"duration": 3, "slots": [{"module": "cpu", "col": 0, "row": 0, "w": 5, "h": 2}]}]

    def run(rotate):
        lay = L.normalize({"device": {"rotate": rotate}, "pages": pages}, tmp_path)
        disp = SimulatorDisplay(orientation="landscape", output=tmp_path / "o.png")
        eng = Engine(L.to_config(lay, tmp_path), disp, metrics=Metrics({"nvidia_smi": False, "lhm": False}))
        disp.open()
        seen = set()
        for t in range(0, 40, 1):
            eng.step(float(t))
            seen.add(eng.page_index)
        return seen, eng
    assert run(True)[0] == {0, 1}
    seen, eng = run(False)
    assert seen == {0}
    eng.pin_page(1); eng.step(100.0)               # the editor looking at page 2 still works
    assert eng.page_index == 1
    eng.pin_page(None); eng.step(101.0)            # ... and the screen goes back to page 1 afterwards
    assert eng.page_index == 0
    assert L.normalize({"device": {"rotate": "x"}})["device"]["rotate"] is True


# --------------------------------------------------------------------------- standalone visualizer card
def test_standalone_visualizer_module(tmp_path):
    mod = [m for m in L.catalog()["modules"] if m["id"] == "visualizador"]
    assert len(mod) == 1 and mod[0]["group"] == "Música"
    keys = {o["key"] for o in mod[0]["options"]}
    assert {"viz_style", "bars", "sensitivity", "color"} <= keys and "show_track" not in keys
    lay = L.normalize({"pages": [{"slots": [
        {"module": "visualizador", "col": 0, "row": 0, "w": 4, "h": 2, "options": {"viz_style": "circular", "bars": 99}}]}]}, tmp_path)
    o = lay["pages"][0]["slots"][0]["options"]
    assert o["viz_style"] == "circular" and o["bars"] == 32
    wd = L.to_config(lay, tmp_path)["page"][0]["widget"]
    assert [w["type"] for w in wd] == ["visualizer"] and wd[0]["style"] == "circular"
    lay2, eng, disp = build([{"module": "visualizador", "col": 0, "row": 0, "w": 4, "h": 2, "options": {}}], tmp_path)
    eng.step(1.0); eng.step(2.0)
    px = np.asarray(disp.frame.convert("RGB"))
    assert (px.sum(axis=2) > 120).any() and not (px[:, 170:].sum(axis=2) > 120).any()


# --------------------------------------------------------------------------- following the default output device
import sys
import threading
import time
import types


class FakeWorld:
    """A fake `soundcard` module: devices come and go, every device plays its own pitch."""

    def __init__(self):
        self.default = ("id-spk", "Alto-falantes")
        self.pitch = {"Alto-falantes": 200.0, "Fone Bluetooth": 3500.0}
        self.block_forever: set = set()        # devices whose loopback blocks (silent device)
        self.broken: set = set()               # devices that raise when recording
        self.none = False
        self.opened: list = []
        self.release = threading.Event()

    def module(self):
        w, m = self, types.ModuleType("soundcard")

        class Speaker:
            def __init__(s, id_, name): s.id, s.name = id_, name

        def default_speaker():
            if w.none:
                raise RuntimeError("no output device")
            return Speaker(*w.default)

        class Rec:
            def __init__(s, name): s.name = name
            def __enter__(s): return s
            def __exit__(s, *a): return False
            def record(s, numframes):
                if s.name in w.block_forever:
                    w.release.wait(30)            # blocked like a silent WASAPI loopback
                    raise RuntimeError("woke up")
                if s.name in w.broken:
                    raise RuntimeError("device removed")
                time.sleep(0.01)
                t = np.arange(numframes) / 48000
                x = (0.5 * np.sin(2 * np.pi * w.pitch[s.name] * t)).astype(np.float32)
                return np.stack([x, x], axis=1)

        class Mic:
            def __init__(s, name): s.name = name
            def recorder(s, samplerate, channels, blocksize):
                w.opened.append(s.name)
                return Rec(s.name)

        m.default_speaker = default_speaker
        m.get_microphone = lambda id, include_loopback: Mic(id)
        return m


def run_with_world(monkeypatch, world):
    monkeypatch.setitem(sys.modules, "soundcard", world.module())
    monkeypatch.setattr(audio, "DEVICE_POLL", 0.03)
    a = audio.Analyzer()
    return a


def top_band(a):
    return int(np.argmax(a.levels(16)))


def wait_for(cond, seconds=3.0):
    end = time.time() + seconds
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


def test_visualizer_follows_a_new_default_device(monkeypatch):
    world = FakeWorld()
    a = run_with_world(monkeypatch, world)
    try:
        assert wait_for(lambda: a.levels(16).max() > 0.5)
        low = top_band(a)
        world.block_forever.add("Alto-falantes")   # the old device goes quiet/blocks, like a real loopback
        world.default = ("id-bt", "Fone Bluetooth")  # Bluetooth headset becomes the default output
        assert wait_for(lambda: a.device == "Fone Bluetooth")
        assert wait_for(lambda: a.levels(16).max() > 0.5 and top_band(a) > low + 4), "never switched to the new device"
        assert "Fone Bluetooth" in a.status()["message"]
        assert world.opened.count("Fone Bluetooth") == 1          # opened once, not over and over
        world.default = ("id-spk", "Alto-falantes")                # ... and back to the speakers
        world.block_forever.clear()
        assert wait_for(lambda: a.device == "Alto-falantes" and top_band(a) <= low + 1)
    finally:
        world.release.set()
        a.stop()


def test_stale_capture_cannot_overwrite_the_current_device(monkeypatch):
    world = FakeWorld()
    a = run_with_world(monkeypatch, world)
    try:
        assert wait_for(lambda: a.levels(16).max() > 0.5)
        world.block_forever.add("Alto-falantes")
        world.default = ("id-bt", "Fone Bluetooth")
        assert wait_for(lambda: a.device == "Fone Bluetooth" and top_band(a) > 8)
        world.release.set()                    # the old, blocked recording wakes up (raises): must be ignored
        time.sleep(0.3)
        assert a.status()["state"] == "ok" and "Fone Bluetooth" in a.status()["message"]
        assert top_band(a) > 8
    finally:
        world.release.set()
        a.stop()


def test_visualizer_recovers_when_the_device_disappears_and_returns(monkeypatch):
    world = FakeWorld()
    a = run_with_world(monkeypatch, world)
    try:
        assert wait_for(lambda: a.levels(16).max() > 0.5)
        world.broken.add("Alto-falantes")          # headset unplugged mid-capture
        assert wait_for(lambda: a.status()["state"] == "error")
        world.none = True                           # no output device at all for a while
        time.sleep(0.2)
        world.none = False
        world.broken.clear()
        world.default = ("id-bt", "Fone Bluetooth")
        assert wait_for(lambda: a.status()["state"] == "ok" and a.levels(16).max() > 0.5 and top_band(a) > 8, seconds=6.0)
    finally:
        world.release.set()
        a.stop()


# ---- progress counter: stays in step with the real playback

def test_timeline_age_trusts_only_plausible_stamps():
    from datetime import datetime, timedelta, timezone
    now = datetime(2026, 11, 16, 12, 0, 10, tzinfo=timezone.utc)
    assert nowplaying.timeline_age(now - timedelta(seconds=4), now) == 4.0
    assert nowplaying.timeline_age(None, now) is None
    assert nowplaying.timeline_age(now + timedelta(seconds=1), now) == 0.0            # tiny clock skew
    assert nowplaying.timeline_age(now + timedelta(seconds=30), now) is None           # from the future
    assert nowplaying.timeline_age(now - timedelta(days=2), now) is None               # ancient
    local_now = datetime(2026, 11, 16, 9, 0, 10)                                       # naive = the PC's local clock
    assert nowplaying.timeline_age(datetime(2026, 11, 16, 9, 0, 6), local_now) == 4.0


def _poll_sequence(positions, step=2.0):
    clock = [100.0]
    seq = iter(positions)
    n = nowplaying.NowPlaying(fetch=lambda: {"title": "t", "artist": "a", "playing": True,
                                             "position": next(seq), "duration": 155.0})
    n.clock = lambda: clock[0]
    shown = []
    for _ in positions:
        n.poll_once()
        shown.append(n.data["position"])
        clock[0] += step
    return shown


def test_counter_does_not_jump_when_the_player_reports_in_coarse_steps():
    # real time moves 2 s per poll, the player's reading wobbles by about a second around the truth
    shown = _poll_sequence([86.0, 88.9, 89.6, 92.4, 93.8, 96.3])
    steps = [b - a for a, b in zip(shown, shown[1:])]
    assert all(1.0 <= s <= 3.0 for s in steps), shown   # roughly 2 s per 2 s poll, no 0 s / 4 s lurches


def test_counter_follows_a_real_seek():
    shown = _poll_sequence([30.0, 32.0, 120.0, 122.0])
    assert shown[2] == 120.0 and shown[3] == 122.0


def test_counter_resets_on_a_new_track():
    clock = [0.0]
    tracks = iter([{"title": "A", "position": 100.0}, {"title": "B", "position": 3.0}])
    n = nowplaying.NowPlaying(fetch=lambda: {**next(tracks), "artist": "x", "playing": True, "duration": 200.0})
    n.clock = lambda: clock[0]
    n.poll_once(); clock[0] += 2; n.poll_once()
    assert n.data["position"] == 3.0


def _stream(readings, poll=2.0):
    """NowPlaying fed by (position, age, signature) readings, one per poll; returns the position after each."""
    clock = [100.0]
    seq = iter(readings)

    def fetch():
        pos, age, sig = next(seq)
        d = {"title": "t", "artist": "a", "playing": True, "position": pos, "duration": 300.0, "pos_age": age}
        if sig is not None:
            d["pos_sig"] = sig
        return d
    n = nowplaying.NowPlaying(fetch=fetch)
    n.clock = lambda: clock[0]
    out = []
    for _ in readings:
        n.poll_once()
        out.append(n.data["position"])
        clock[0] += poll
    return n, out


def test_rereading_the_same_stale_snapshot_never_moves_the_counter():
    # the player published once (pos 50, 1 s old) and then stays silent: Windows keeps returning the same snapshot
    _, shown = _stream([(50.0, 1.0, ("p", 1))] * 5)
    assert shown == [51.0, 53.0, 55.0, 57.0, 59.0]


def test_fresh_snapshots_keep_the_counter_in_step():
    _, shown = _stream([(50.0, 0.2, ("a", 1)), (52.1, 0.3, ("a", 2)), (54.0, 0.1, ("a", 3)), (56.2, 0.4, ("a", 4))])
    steps = [round(b - a, 1) for a, b in zip(shown, shown[1:])]
    assert all(1.7 <= s <= 2.3 for s in steps), shown


def test_untrustworthy_timestamps_do_not_make_the_counter_jump():
    # age unknown (stamp in another time zone, say): the raw snapshot is used and a stale one is not mistaken for a seek
    _, shown = _stream([(50.0, None, ("a", 1)), (50.0, None, ("a", 1)), (53.0, None, ("a", 2)), (53.0, None, ("a", 2)), (57.0, None, ("a", 3))])
    assert all(b > a for a, b in zip(shown, shown[1:])), shown
    assert max(b - a for a, b in zip(shown, shown[1:])) <= 3.2 and shown[-1] < 60


def test_a_seek_is_followed_immediately():
    _, shown = _stream([(50.0, 0.1, ("a", 1)), (52.0, 0.1, ("a", 2)), (200.0, 0.1, ("a", 3)), (202.0, 0.1, ("a", 4))])
    assert shown[2] == pytest.approx(200.1) and shown[3] == pytest.approx(202.0, abs=0.3)


def test_displayed_seconds_never_skip_or_repeat(tmp_path):
    """Run the progress card for two minutes (screen ticking at 4 Hz like the layout asks) against a player that
    publishes every ~3 s with some wobble: the shown seconds must go 0:10, 0:11, 0:12... without gaps or repeats."""
    import random
    from rhinos_buddy.widgets import Context, NowPlayingWidget
    rnd = random.Random(7)
    t = [1000.0]
    real_start = 10.0                      # the track was at 0:10 when the test starts
    state = {"sig": 0, "last_pub": -99.0, "pos": 0.0}

    def fetch():
        now = t[0]
        if now - state["last_pub"] >= 3.0:
            state["last_pub"] = now
            state["sig"] += 1
            state["pos"] = real_start + (now - 1000.0) + rnd.uniform(-0.4, 0.4)
        return {"title": "t", "artist": "a", "playing": True, "position": state["pos"], "duration": 300.0,
                "pos_age": now - state["last_pub"] + 0.1, "pos_sig": (state["sig"], 0)}
    np_ = nowplaying.NowPlaying(fetch=fetch)
    np_.clock = lambda: t[0]
    ctx = Context(metrics=None, base_dir=tmp_path)
    ctx.nowplaying = np_
    w = NowPlayingWidget({"w": 300, "h": 120, "mode": "capa", "show_progress": True}, ctx)
    w.clock = lambda: t[0]
    seen, next_poll = [], 0.0
    while t[0] < 1120.0:
        if t[0] >= next_poll:               # the poll thread: every 2 s
            np_.poll_once()
            next_poll = t[0] + 2.0
        w.update()
        pos = w._position(w._info) if w._info else None
        if pos is not None and (not seen or int(pos) != seen[-1]):
            seen.append(int(pos))
        t[0] += 0.25
    steps = {b - a for a, b in zip(seen, seen[1:])}
    assert steps == {1}, (steps, seen[:20])


def test_a_stamp_in_the_wrong_time_zone_is_not_added_to_the_position():
    _, shown = _stream([(50.0, 10800.0, ("a", 1)), (50.0, 10800.0, ("a", 1))])   # "3 hours old" on a 5-minute track
    assert shown == [50.0, 52.0]
