import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rhinos_buddy import protocol as P
from rhinos_buddy.devices import RevADisplay, SimulatorDisplay
from rhinos_buddy.engine import Engine, load_config

EXAMPLE = Path(__file__).parent.parent / "examples" / "config.toml"


# ------------------------------------------------------------------ protocol
def unpack(pkt):
    x = (pkt[0] << 2) | (pkt[1] >> 6)
    y = ((pkt[1] & 0x3F) << 4) | (pkt[2] >> 4)
    ex = ((pkt[2] & 0x0F) << 6) | (pkt[3] >> 2)
    ey = ((pkt[3] & 0x03) << 8) | pkt[4]
    return x, y, ex, ey, pkt[5]


@pytest.mark.parametrize("vals", [(0, 0, 0, 0), (479, 319, 479, 319), (1, 2, 3, 4), (1023, 1023, 1023, 1023), (100, 17, 333, 256)])
def test_packet_roundtrip(vals):
    assert unpack(P.command_packet(P.CMD_DISPLAY_BITMAP, *vals)) == (*vals, P.CMD_DISPLAY_BITMAP)


def test_packet_out_of_range():
    with pytest.raises(ValueError):
        P.command_packet(1, x=1024)


def test_rgb565_primary_colors_little_endian():
    img = Image.new("RGB", (3, 1))
    img.putdata([(255, 0, 0), (0, 255, 0), (0, 0, 255)])
    assert P.rgb565_le(img) == bytes([0x00, 0xF8, 0xE0, 0x07, 0x1F, 0x00])


def test_orientation_and_brightness():
    assert P.screen_size("landscape") == (480, 320)
    assert P.screen_size("portrait") == (320, 480)
    pkt = P.orientation_packet("landscape")
    assert len(pkt) == 11 and pkt[5] == 0x79 and pkt[6] == 102 and pkt[7:] == bytes([1, 224, 1, 64])
    assert unpack(P.brightness_packet(100))[0] == 0 and unpack(P.brightness_packet(0))[0] == 255


# ------------------------------------------------------------- fake hardware
class FakeSerial:
    def __init__(self, *a, **k):
        self.buf = bytearray()

    def write(self, b):
        self.buf += b

    def close(self):
        pass


def test_revA_blit_writes_header_then_pixels():
    d = RevADisplay(port="X", orientation="landscape")
    d._ser = FakeSerial()
    img = Image.new("RGB", (10, 4), (255, 0, 0))
    d.blit(img, 20, 30)
    assert unpack(d._ser.buf[:6]) == (20, 30, 29, 33, P.CMD_DISPLAY_BITMAP)
    assert bytes(d._ser.buf[6:]) == bytes([0x00, 0xF8]) * 40


def test_revA_rejects_out_of_bounds():
    d = RevADisplay(port="X")
    d._ser = FakeSerial()
    with pytest.raises(ValueError):
        d.blit(Image.new("RGB", (10, 10)), 475, 0)


# ------------------------------------------------------------------- engine
def make_engine(tmp_path, cfg_text=None):
    if cfg_text is None:
        cfg = load_config(EXAMPLE)
    else:
        p = tmp_path / "c.toml"
        p.write_text(cfg_text)
        cfg = load_config(p)
    cfg["device"] = {"type": "simulator", "output": str(tmp_path / "p.png")}
    return Engine(cfg)


def test_example_config_renders_and_updates_partially(tmp_path):
    eng = make_engine(tmp_path)
    eng.display.open()
    t = time.monotonic()
    assert eng.step(t) == 1                      # first frame = full screen
    assert eng.display.blits[-1] == (0, 0, 480, 320)
    n = len(eng.display.blits)
    m = eng.ctx.metrics
    m.get()
    m._data = dict(m._data, cpu=77.0)
    m._t = time.monotonic() + 100  # freeze sampling so our value is used
    eng.step(t + 1.5)
    new = eng.display.blits[n:]
    assert new and all(w * h < 480 * 320 for _, _, w, h in new)  # partial updates only
    arr = np.asarray(eng.display.frame)
    assert arr.std() > 5  # something was actually drawn


def test_pages_rotate(tmp_path):
    eng = make_engine(tmp_path)
    eng.display.open()
    t = time.monotonic()
    eng.step(t)
    assert eng.page_index == 0
    eng.step(t + 13)
    assert eng.page_index == 1
    eng.step(t + 26)
    assert eng.page_index == 0


def test_command_widget_and_error_isolation(tmp_path):
    cfg = """
[[widget]]
type = "command"
x = 0
y = 0
w = 200
h = 40
command = "echo hello-world"
[[widget]]
type = "image"
x = 0
y = 50
w = 100
h = 100
path = "missing.png"
"""
    eng = make_engine(tmp_path, cfg)
    eng.display.open()
    eng.step(time.monotonic())  # must not raise despite the broken image widget
    page = eng.pages[0]
    assert page.widgets[0]._out == "hello-world"
    assert page.widgets[1].error


def test_image_widget_reloads_when_file_changes(tmp_path):
    img = tmp_path / "x.png"
    Image.new("RGB", (50, 50), (255, 0, 0)).save(img)
    eng = make_engine(tmp_path, '[[widget]]\ntype="image"\nx=0\ny=0\nw=50\nh=50\npath="x.png"\nfit="stretch"\n')
    eng.display.open()
    t = time.monotonic()
    eng.step(t)
    assert eng.display.frame.getpixel((10, 10)) == (255, 0, 0)
    Image.new("RGB", (50, 50), (0, 0, 255)).save(img)
    import os
    os.utime(img, (time.time() + 5, time.time() + 5))
    eng.step(t + 1)
    assert eng.display.frame.getpixel((10, 10)) == (0, 0, 255)


def test_plugin_widget(tmp_path):
    (tmp_path / "pl.py").write_text(
        "from PIL import Image\nclass Plugin:\n    def __init__(s,c,x): pass\n"
        "    def render(s,w,h): return Image.new('RGBA',(w,h),(0,255,0,255))\n"
    )
    eng = make_engine(tmp_path, '[[widget]]\ntype="plugin"\nmodule="pl.py"\nx=10\ny=10\nw=30\nh=30\n')
    eng.display.open()
    eng.step(time.monotonic())
    assert eng.display.frame.getpixel((20, 20)) == (0, 255, 0)


def test_screen_on_and_brightness_polarity():
    assert unpack(P.screen_on_packet())[4] == P.CMD_SCREEN_ON
    assert unpack(P.brightness_packet(100, inverted=False))[0] == 255
    assert unpack(P.brightness_packet(100, inverted=True))[0] == 0
    d = RevADisplay(port="X", invert_brightness=False)
    d._ser = FakeSerial()
    d.screen_on()
    d.set_brightness(100)
    assert unpack(d._ser.buf[:6])[4] == P.CMD_SCREEN_ON
    assert unpack(d._ser.buf[6:12])[0] == 255


# ---------------------------------------------------------- diff transmission
def test_changed_rects_tight_and_complete():
    m = np.zeros((320, 480), dtype=bool)
    assert P.changed_rects(m) == []
    m[100:110, 200:230] = True
    assert P.changed_rects(m) == [(200, 100, 230, 110)]
    m[300, 5] = True
    rects = P.changed_rects(m)
    assert len(rects) == 2
    covered = np.zeros_like(m)
    for x0, y0, x1, y1 in rects:
        covered[y0:y1, x0:x1] = True
    assert (covered & m).sum() == m.sum()  # every changed pixel is inside some rect


def test_changed_rects_falls_back_to_one_box():
    m = np.zeros((320, 480), dtype=bool)
    for i in range(10):
        m[i * 32 + 3, (i * 97) % 440] = True  # 10 scattered pixels
    rects = P.changed_rects(m)
    assert len(rects) == 1
    x0, y0, x1, y1 = rects[0]
    assert all(x0 <= x < x1 and y0 <= y < y1 for y, x in zip(*np.nonzero(m)))


def test_unchanged_frames_send_nothing(tmp_path):
    eng = make_engine(tmp_path, '[[widget]]\ntype="text"\nx=0\ny=0\nw=100\nh=30\ntext="hi"\n')
    eng.display.open()
    t = time.monotonic()
    eng.step(t)
    n = len(eng.display.blits)
    page = eng.pages[0]
    assert eng._send(page, (0, 0, 100, 30)) == 0  # identical pixels -> nothing transmitted
    assert len(eng.display.blits) == n


# ----------------------------------------------------------- software rotation
@pytest.mark.parametrize("mode", ["ccw", "cw"])
@pytest.mark.parametrize("rect", [(0, 0, 480, 320), (50, 30, 100, 40), (470, 310, 10, 10), (0, 300, 480, 20)])
def test_rotate_region_matches_full_rotation(mode, rect):
    rng = np.random.default_rng(3)
    full = Image.fromarray(rng.integers(0, 255, (320, 480, 3), dtype=np.uint8))
    ref = full.transpose(Image.ROTATE_90 if mode == "ccw" else Image.ROTATE_270)  # native 320x480
    x, y, w, h = rect
    piece, nx, ny = P.rotate_region(full.crop((x, y, x + w, y + h)), x, y, mode, 480, 320)
    canvas = Image.new("RGB", (320, 480))
    canvas.paste(piece, (nx, ny))
    box = (nx, ny, nx + piece.width, ny + piece.height)
    assert np.array_equal(np.asarray(canvas.crop(box)), np.asarray(ref.crop(box)))


def test_revA_rotate_sends_native_portrait_coordinates():
    d = RevADisplay(port="X", orientation="portrait", rotate="ccw")
    assert (d.width, d.height) == (480, 320)
    d._ser = FakeSerial()
    d.blit(Image.new("RGB", (100, 40), (255, 0, 0)), 50, 30)
    # logical (50,30,100x40) -> native x=30, y=480-150=330, 40 wide x 100 tall
    assert unpack(d._ser.buf[:6]) == (30, 330, 30 + 40 - 1, 330 + 100 - 1, P.CMD_DISPLAY_BITMAP)
    assert len(d._ser.buf) == 6 + 40 * 100 * 2
    with pytest.raises(ValueError):
        RevADisplay(port="X", orientation="landscape", rotate="cw")


def test_gif_plays_in_real_time_dropping_frames(tmp_path):
    frames = [Image.new("RGB", (20, 20), c) for c in ((255, 0, 0), (0, 255, 0), (0, 0, 255))]
    gif = tmp_path / "a.gif"
    frames[0].save(gif, save_all=True, append_images=frames[1:], duration=100, loop=0)
    eng = make_engine(tmp_path, '[[widget]]\ntype="image"\nx=0\ny=0\nw=20\nh=20\npath="a.gif"\nfit="stretch"\n')
    w = eng.pages[0].widgets[0]
    w._load()
    assert [w._index_at(w._t0 + t) for t in (0.0, 0.05, 0.15, 0.25, 0.31, 0.65)] == [0, 0, 1, 2, 0, 0]


# ------------------------------------------------------------ grid alignment
def test_align_rect():
    assert P.align_rect((71, 85, 84, 103), 8, 480, 320) == (64, 80, 88, 104)
    assert P.align_rect((470, 315, 480, 320), 8, 480, 320) == (464, 312, 480, 320)
    assert P.align_rect((3, 3, 5, 5), 1, 480, 320) == (3, 3, 5, 5)


def test_engine_only_sends_grid_aligned_rects_and_stays_correct(tmp_path):
    eng = make_engine(tmp_path)
    eng.display.open()
    t = time.monotonic()
    eng.step(t)
    m = eng.ctx.metrics
    for cpu in (7.0, 43.0, 99.0, 12.0):
        n = len(eng.display.blits)
        m.get()
        m._data = dict(m._data, cpu=cpu)
        m._t = time.monotonic() + 100
        eng.step(t + 2)
        for x, y, w, h in eng.display.blits[n:]:
            assert x % 8 == 0 and y % 8 == 0 and (x + w) % 8 == 0 and (y + h) % 8 == 0 or (x + w, y + h) == (480, 320)
    # what the (simulated) panel shows must equal a fresh full compose of the page
    page = eng.pages[0]
    full = np.asarray(page.compose((0, 0, 480, 320)))
    assert np.array_equal(np.asarray(eng.display.frame), full)


def test_metrics_deadband_ignores_jitter_but_follows_real_changes():
    from rhinos_buddy.metrics import Metrics
    m = Metrics({"nvidia_smi": False, "lhm": False})
    m.set_stability(2)
    base = {"cpu": 10.0, "net_down_kbs": 100.0, "net_up_kbs": 5.0, "ram_used_gb": 7.30}
    assert m._publish(dict(base))["cpu"] == 10.0
    assert m._publish({**base, "cpu": 12.0})["cpu"] == 10.0          # wobble ignored
    assert m._publish({**base, "cpu": 16.0})["cpu"] == 16.0          # real change shown
    out = m._publish({**base, "net_down_kbs": 120.0})
    assert out["net_down_h"] == "100 KB/s"                           # +20% < 50%
    assert m._publish({**base, "net_down_kbs": 2048.0})["net_down_h"] == "2.0 MB/s"
    m.set_stability(0)
    assert m._publish({**base, "cpu": 16.5})["cpu"] == 16.5          # off = every reading
    m.stop()
