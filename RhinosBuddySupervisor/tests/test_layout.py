import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from rhinos_buddy import layout as L
from rhinos_buddy.devices import TeeDisplay
from rhinos_buddy.engine import Engine
from rhinos_buddy.metrics import Metrics


def engine_for(layout, home):
    cfg = L.to_config(layout, home)
    cfg["sensors"] = {"nvidia_smi": False, "lhm": False}
    m = Metrics(cfg["sensors"])
    disp = TeeDisplay(cfg["device"]["orientation"])
    return Engine(cfg, disp, metrics=m), disp


def test_default_layout_is_valid_and_renders(tmp_path):
    lay = L.default_layout()
    assert lay == L.normalize(lay, tmp_path)  # normalising is idempotent
    eng, disp = engine_for(lay, tmp_path)
    eng.step(time.monotonic())
    assert np.asarray(disp.snapshot()).std() > 5
    assert all(w.error is None for w in eng.pages[0].widgets)


def test_normalize_clamps_and_drops_garbage(tmp_path):
    lay = L.normalize({
        "device": {"port": "rm -rf /", "brightness": 900, "orientation": "sideways", "fps": "x"},
        "theme": {"text": "red", "font": "Comic", "card": {"opacity": -5}},
        "pages": [{"slots": [
            {"module": "cpu", "col": 99, "row": -3, "w": 50, "h": 0, "options": {"show_bar": "yes", "color": "javascript:1"}},
            {"module": "evil", "col": 0, "row": 0, "w": 1, "h": 1},
            "not a dict",
        ]}, "junk"],
    }, tmp_path)
    assert lay["device"]["port"] == "auto" and lay["device"]["brightness"] == 100
    assert lay["device"]["orientation"] == "landscape" and lay["device"]["fps"] == 20
    assert lay["theme"]["text"] == "#ffffff" and lay["theme"]["font"] == "Segoe UI"
    assert lay["theme"]["card"]["opacity"] == 0
    assert len(lay["pages"]) == 1 and len(lay["pages"][0]["slots"]) == 1
    s = lay["pages"][0]["slots"][0]
    assert (s["col"], s["row"], s["w"], s["h"]) == (0, 0, 12, 1)  # clamped inside the 12x8 grid
    assert s["options"]["show_bar"] is True and s["options"]["color"] == ""


def test_slots_follow_orientation_grid(tmp_path):
    lay = L.normalize({"device": {"orientation": "portrait"},
                       "pages": [{"slots": [{"module": "cpu", "col": 11, "row": 11, "w": 6, "h": 3}]}]}, tmp_path)
    s = lay["pages"][0]["slots"][0]
    assert L.grid_size("portrait") == (8, 12) and s["col"] + s["w"] <= 8 and s["row"] + s["h"] <= 12


def test_media_names_cannot_escape_the_media_folder(tmp_path):
    (tmp_path / "media").mkdir()
    (tmp_path / "media" / "foto.png").write_bytes(b"x")
    n = lambda v: L.normalize({"theme": {"background": {"image": v}}}, tmp_path)["theme"]["background"]["image"]
    assert n("foto.png") == "foto.png"
    assert n("../../etc/passwd") == ""
    assert n("C:\\Windows\\win.ini") == ""
    assert n("nao_existe.png") == ""


def test_background_image_fit_and_dim(tmp_path):
    (tmp_path / "media").mkdir()
    Image.new("RGB", (100, 100), (255, 255, 255)).save(tmp_path / "media" / "b.png")
    lay = L.default_layout()
    lay["pages"] = [{"name": "p", "duration": 10, "slots": []}]
    lay["theme"]["background"].update(image="b.png", dim=50, fit="stretch")
    eng, disp = engine_for(lay, tmp_path)
    eng.step(time.monotonic())
    r, g, b = disp.snapshot().getpixel((240, 160))
    assert 120 <= r <= 135 and r == g == b  # white dimmed by 50 %
    lay["theme"]["background"]["image"] = ""  # no image -> plain colour
    eng, disp = engine_for(lay, tmp_path)
    eng.step(time.monotonic())
    assert disp.snapshot().getpixel((240, 160)) == (11, 15, 26)


def test_every_module_renders_without_widget_errors(tmp_path):
    slots = [{"module": m, "col": (i % 3) * 4, "row": (i // 3) * 2, "w": 4, "h": 2, "options": {"show_graph": True}}
             for i, m in enumerate(L.MODULES) if m != "image"][:12]
    lay = L.default_layout()
    lay["pages"] = [{"name": "t", "duration": 10, "slots": slots}]
    eng, disp = engine_for(lay, tmp_path)
    eng.step(time.monotonic())
    assert [w.type_name for w in eng.pages[0].widgets if w.error] == []


def test_tee_display_survives_hardware_failure():
    class Broken:
        def blit(self, *a):
            raise OSError("unplugged")

        def close(self):
            pass

    t = TeeDisplay("landscape")
    t.hw = Broken()
    t.blit(Image.new("RGB", (8, 8), (255, 0, 0)), 0, 0)  # must not raise
    assert t.hw is None and isinstance(t.hw_error, OSError)
    assert t.snapshot().getpixel((1, 1)) == (255, 0, 0)  # preview kept working


def test_catalog_is_json_friendly():
    import json
    cat = L.catalog()
    json.dumps(cat)
    assert {"cpu", "gpu", "ram", "net", "clock", "date", "image", "text"} <= {m["id"] for m in cat["modules"]}


def test_device_stability_and_align_are_normalised():
    from rhinos_buddy import layout as L
    d = L.normalize({"device": {"stability": 9, "align": 3}})["device"]
    assert d["stability"] == 2 and d["align"] == 8
    d = L.normalize({"device": {"stability": 0, "align": 4}})["device"]
    assert d["stability"] == 0 and d["align"] == 4
    cfg = L.to_config(L.normalize({"device": {"align": 16}}), ".")
    assert cfg["device"]["align"] == 16 and cfg["device"]["stability"] == 2


def test_rings_template_and_date_never_overflow(tmp_path):
    from rhinos_buddy import layout as L
    from rhinos_buddy.widgets import load_font
    for o, c, r in (("landscape", 12, 8), ("portrait", 8, 12)):
        lay = L.normalize({"device": {"orientation": o}, "pages": [{"slots": L.template("aneis", c, r)}]}, tmp_path)
        mods = [s["module"] for s in lay["pages"][0]["slots"]]
        assert mods.count("cpu") == mods.count("gpu") == mods.count("vram") == mods.count("ram") == 1
        wd = L.to_config(lay, tmp_path)["page"][0]["widget"]
        assert sum(w["type"] == "radial" for w in wd) == 4 and not any(w["type"] == "bar" for w in wd)
    # the longest Portuguese date must fit the date slot at its computed size
    for month in ("fevereiro", "novembro", "setembro", "dezembro"):
        lay = L.normalize({"pages": [{"slots": [{"module": "date", "col": 5, "row": 0, "w": 7, "h": 2, "options": {"style": "extenso"}}]}]}, tmp_path)
        w = [x for x in L.to_config(lay, tmp_path)["page"][0]["widget"] if x["type"] == "text"][0]
        assert L.text_w(w["font"], w["size"], f"28 de {month} de 2026") <= w["w"]


def test_stat_modules_have_a_text_position_option(tmp_path):
    from rhinos_buddy import layout as L
    for m in ("cpu", "gpu", "vram", "ram", "disk", "cpu_temp", "gpu_temp", "net", "net_down", "net_up"):
        keys = [o["key"] for o in L.MODULES[m]["options"]]
        assert "align" in keys, m
    lay = L.normalize({"pages": [{"slots": [{"module": "cpu", "col": 0, "row": 0, "w": 6, "h": 3, "options": {"align": "nope"}}]}]}, tmp_path)
    assert lay["pages"][0]["slots"][0]["options"]["align"] == "padrao"


def _texts(module, align, w, h, radial=False, tmp_path=None):
    from rhinos_buddy import layout as L
    lay = {"theme": {"bar_style": "radial" if radial else "barra"},
           "pages": [{"slots": [{"module": module, "col": 0, "row": 0, "w": w, "h": h, "options": {"align": align}}]}]}
    wd = L.to_config(L.normalize(lay, tmp_path), tmp_path)["page"][0]["widget"]
    return [x for x in wd if x["type"] == "text"], [x for x in wd if x["type"] == "radial"]


def test_text_position_moves_label_and_value(tmp_path):
    for al in ("left", "center", "right"):
        t, _ = _texts("cpu", al, 6, 3, tmp_path=tmp_path)
        assert {x["align"] for x in t if x["text"] in ("CPU", "{cpu:.0f}%")} == {al}
    t, _ = _texts("cpu", "padrao", 6, 3, tmp_path=tmp_path)
    assert {x["align"] for x in t if x["text"] == "{cpu:.0f}%"} == {"left"}   # unchanged default
    # temperature goes to the opposite side when the label is on the right
    left = {x["text"]: x for x in _texts("cpu", "left", 6, 3, tmp_path=tmp_path)[0]}
    right = {x["text"]: x for x in _texts("cpu", "right", 6, 3, tmp_path=tmp_path)[0]}
    assert left["{cpu_temp:.0f} °C"]["x"] > right["{cpu_temp:.0f} °C"]["x"]
    # centred label never overlaps the temperature
    cen = {x["text"]: x for x in _texts("cpu", "center", 6, 3, tmp_path=tmp_path)[0]}
    assert cen["CPU"]["x"] + cen["CPU"]["w"] <= cen["{cpu_temp:.0f} °C"]["x"]


def test_compact_row_blocks_stay_inside_the_slot(tmp_path):
    for al in ("padrao", "left", "center", "right"):
        t, _ = _texts("ram", al, 12, 1, tmp_path=tmp_path)
        for x in t:
            assert x["x"] >= 4 - 1 and x["x"] + x["w"] <= 12 * 40 - 4 + 1, (al, x)
    xs = {al: min(x["x"] for x in _texts("ram", al, 12, 1, tmp_path=tmp_path)[0]) for al in ("left", "center", "right")}
    assert xs["left"] < xs["center"] < xs["right"]


def test_radial_ring_moves_with_text_position(tmp_path):
    for (w, h) in ((4, 3), (6, 3)):       # stacked and wide rings
        pos = {al: _texts("cpu", al, w, h, radial=True, tmp_path=tmp_path)[1][0]["x"] for al in ("left", "center", "right")}
        assert pos["left"] < pos["center"] <= pos["right"] or pos["left"] <= pos["center"] < pos["right"], (w, h, pos)
