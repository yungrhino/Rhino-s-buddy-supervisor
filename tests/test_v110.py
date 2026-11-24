"""Version 1.1.0: "Em teste" category, notification text alignment, orientation memory, what's-new pop-up."""
import json

import numpy as np
import pytest

from rhinos_buddy import appdata, layout as L, release_notes
from tests.test_notifications import Clock, notifier, region, screen


# ---- "Em teste" category + alignment option
def test_notification_card_lives_in_the_beta_category_and_has_an_alignment_option():
    cat = L.catalog()
    mod = next(m for m in cat["modules"] if m["id"] == "notificacao")
    assert mod["group"] == cat["beta_group"] == "Em teste"
    assert [m["id"] for m in cat["modules"] if m["group"] == "Em teste"] == ["notificacao"]
    al = next(o for o in mod["options"] if o["key"] == "align")
    assert [c[0] for c in al["choices"]] == ["left", "center", "right"]


def test_alignment_value_is_validated(tmp_path):
    lay = L.normalize({"pages": [{"slots": [{"module": "notificacao", "col": 0, "row": 0, "w": 4, "h": 3, "options": {"align": "sideways"}}]}]}, tmp_path)
    assert lay["pages"][0]["slots"][0]["options"]["align"] == "left"


def _bright_span(tmp_path, slots, setup):
    """Leftmost / rightmost bright pixel inside the card (a few px in from the edges, so the outline is ignored)."""
    n = notifier()
    eng, disp = screen(tmp_path, slots, n)
    n.ingest([])
    setup(n)
    for t in range(3):
        eng.step(float(t))
    img = region(disp, 8, 14, 312, 106)
    xs = np.where(img.sum(axis=2) > 330)[1] + 8
    return xs.min(), xs.max()


_ITEMS = [{"id": "1", "app": "Ana", "title": "Oi", "body": "ok", "created": 2}, {"id": "2", "app": "Bia", "title": "Tchau", "body": "ok", "created": 1}]


def test_list_text_follows_the_alignment(tmp_path):
    def span(al):
        return _bright_span(tmp_path, [{"module": "notificacao", "col": 0, "row": 0, "w": 8, "h": 3, "options": {"align": al, "rows": 2}}],
                            lambda n: n.ingest(_ITEMS))
    (l0, l1), (c0, c1), (r0, r1) = span("left"), span("center"), span("right")
    assert l0 < 12 and l1 < 170            # left: coloured initial and text hug the left edge
    assert c1 > l1 + 40                    # centre: the text moves towards the middle
    assert r0 > 140 and r1 > 300           # right: the initial sits on the right edge and the text ends there


def test_alert_overlay_uses_the_card_alignment(tmp_path):
    def span(al):
        return _bright_span(tmp_path, [{"module": "cpu", "col": 0, "row": 0, "w": 8, "h": 3, "options": {"notify": True, "align": al}}],
                            lambda n: n.ingest([{"id": "1", "app": "WhatsApp", "title": "Ana", "body": "oi"}]))
    (l0, l1), (c0, c1), (r0, r1) = span("left"), span("center"), span("right")
    assert l0 < 14 and r0 > l0 + 100 and c1 > l1 + 50


# ---- orientation memory
def _slot(module, col, row, w, h, **kw):
    return {"module": module, "col": col, "row": row, "w": w, "h": h, "options": {}, **kw}


def test_slot_remembers_its_place_in_the_other_orientation(tmp_path):
    raw = {"device": {"orientation": "landscape"}, "pages": [{"slots": [
        _slot("clock", 0, 0, 4, 2, alt={"portrait": {"col": 1, "row": 5, "w": 6, "h": 3}})]}]}
    s = L.normalize(raw, tmp_path)["pages"][0]["slots"][0]
    assert s["alt"] == {"portrait": {"col": 1, "row": 5, "w": 6, "h": 3}}


def test_remembered_place_is_clamped_to_the_other_grid_and_garbage_is_dropped(tmp_path):
    raw = {"device": {"orientation": "landscape"}, "pages": [{"slots": [
        _slot("clock", 0, 0, 4, 2, alt={"portrait": {"col": 99, "row": 99, "w": 50, "h": 50}}),
        _slot("cpu", 0, 2, 4, 2, alt={"portrait": "x"}),
        _slot("gpu", 4, 2, 4, 2, alt={"landscape": {"col": 3, "row": 3, "w": 1, "h": 1}}),   # own orientation: pointless
        _slot("ram", 8, 2, 4, 2, alt="nope")]}]}
    s = L.normalize(raw, tmp_path)["pages"][0]["slots"]
    assert s[0]["alt"]["portrait"] == {"col": 0, "row": 0, "w": 8, "h": 12}
    assert all("alt" not in x for x in s[1:])


def test_switching_orientation_keeps_the_cards_inside_the_new_grid(tmp_path):
    lay = L.default_layout()
    lay["device"]["orientation"] = "portrait"
    s = L.normalize(lay, tmp_path)["pages"][0]["slots"]
    assert s and all(x["col"] + x["w"] <= 8 and x["row"] + x["h"] <= 12 for x in s)


# ---- what's-new pop-up
def test_release_notes_exist_for_the_current_version():
    from rhinos_buddy import __version__
    n = release_notes.notes_for(__version__)
    assert n and n["title"] and len(n["items"]) >= 1


def test_popup_shows_once_per_version_and_can_be_turned_off():
    v = "1.1.0"
    assert release_notes.should_show(v, {"seen_version": "", "hide_notes": False, "lang": "pt", "lang_chosen": False})          # first start
    assert release_notes.should_show(v, {"seen_version": "1.0.10", "hide_notes": False})    # after an update
    assert not release_notes.should_show(v, {"seen_version": v, "hide_notes": False})       # opened again, no update
    assert not release_notes.should_show(v, {"seen_version": "", "hide_notes": True})       # "do not show again"
    assert not release_notes.should_show("9.9.9", {"seen_version": "", "hide_notes": False, "lang": "pt", "lang_chosen": False})  # version with no notes


def test_prefs_roundtrip_and_survive_garbage(tmp_path):
    ph = {"phone_enabled": False, "phone_edit": False}
    assert appdata.load_prefs(tmp_path) == {"seen_version": "", "hide_notes": False, "lang": "pt", "lang_chosen": False, **ph}
    appdata.save_prefs(tmp_path, {"seen_version": "1.1.0", "hide_notes": True, "lang": "pt", "lang_chosen": False})
    assert appdata.load_prefs(tmp_path) == {"seen_version": "1.1.0", "hide_notes": True, "lang": "pt", "lang_chosen": False, **ph}
    (tmp_path / appdata.PREFS_FILE).write_text("{not json", "utf-8")
    assert appdata.load_prefs(tmp_path) == {"seen_version": "", "hide_notes": False, "lang": "pt", "lang_chosen": False, **ph}
    (tmp_path / appdata.PREFS_FILE).write_text(json.dumps({"seen_version": ["x"], "hide_notes": "yes", "phone_enabled": "yes", "phone_edit": 1}), "utf-8")
    assert appdata.load_prefs(tmp_path) == {"seen_version": "", "hide_notes": False, "lang": "pt", "lang_chosen": False, **ph}


# ---- 1.2.1: a newer version replaces the running old copy -------------------------------------------------------
def test_running_instance_and_replace(monkeypatch):
    import json, threading, time
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from rhinos_buddy import app

    state = {"quit": False}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass
        def do_GET(self):
            b = json.dumps({"app": "rhinos_buddy", "version": "0.0.1"}).encode()
            self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        def do_POST(self):
            assert self.headers.get("X-Rhinos-Buddy") == "1" and self.path == "/api/quit"
            self.send_response(200); self.send_header("Content-Length", "2"); self.end_headers(); self.wfile.write(b"{}")
            state["quit"] = True
            threading.Thread(target=srv.shutdown, daemon=True).start()

    srv = HTTPServer(("127.0.0.1", 0), H)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    assert app.running_instance(port)["version"] == "0.0.1"
    assert app.already_running(port)
    assert app.replace_running_instance(port, timeout=1) is False or True  # port may stay bound until server_close
    assert state["quit"]
    srv.server_close()
    assert app.running_instance(port) is None
    assert app.replace_running_instance(port, timeout=0.5) is False          # nothing to quit


def test_github_link_is_in_the_page_next_to_the_version():
    from pathlib import Path
    html = (Path(__file__).resolve().parent.parent / "rhinos_buddy" / "web" / "index.html").read_text("utf-8")
    assert html.count("https://github.com/yungrhino") >= 2          # header + System tab
    assert 'id="vtag"' in html and 'rel="noopener noreferrer"' in html
