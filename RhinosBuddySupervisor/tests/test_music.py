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
    assert [w["type"] for w in wd] == ["nowplaying"] and wd[0]["mode"] == "capa" and wd[0]["interval"] == 1
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
