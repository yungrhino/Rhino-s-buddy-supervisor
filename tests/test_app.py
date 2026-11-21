import json
import socket
import threading
import urllib.error
import urllib.request
from io import BytesIO

import pytest
from PIL import Image

from rhinos_buddy import app as A
from rhinos_buddy import layout as L
from rhinos_buddy.runner import Runner


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server(tmp_path):
    port = free_port()
    runner = Runner(tmp_path, hardware=False)
    runner.start()
    app = A.App(tmp_path, runner, port)
    srv = A._Server(("127.0.0.1", port), A.make_handler(app))
    app.server = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield app, f"http://127.0.0.1:{port}"
    srv.shutdown()
    srv.server_close()
    runner.stop()


def call(url, method="GET", body=None, headers=None, host=None):
    h = dict(headers or {})
    if host:
        h["Host"] = host
    data = body if isinstance(body, bytes) else (json.dumps(body).encode() if body is not None else None)
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if r.headers.get_content_type() == "application/json" else raw)
    except urllib.error.HTTPError as e:
        raw = e.read()
        return e.code, (json.loads(raw) if raw[:1] == b"{" else raw)


W = {"X-Rhinos-Buddy": "1"}


def test_serves_ui_state_and_preview(server):
    app, base = server
    code, html = call(base + "/")
    assert code == 200 and b"Rhino's Buddy Supervisor" in html
    code, st = call(base + "/api/state")
    assert code == 200 and st["layout"]["pages"] and st["catalog"]["modules"] and st["status"]["connected"] is False
    code, png = call(base + "/api/preview.png")
    assert code == 200 and png[:4] == b"\x89PNG"
    assert call(base + "/api/ping")[1]["app"] == "rhinos_buddy"
    assert A.already_running(int(base.rsplit(":", 1)[1]))


def test_layout_roundtrip_is_normalised_and_persisted(server):
    app, base = server
    lay = call(base + "/api/state")[1]["layout"]
    lay["device"]["brightness"] = 55
    lay["pages"][0]["slots"][0]["w"] = 999  # nonsense is clamped, not trusted
    code, r = call(base + "/api/layout", "POST", lay, {**W, "Content-Type": "application/json"})
    assert code == 200 and r["layout"]["device"]["brightness"] == 55 and r["layout"]["pages"][0]["slots"][0]["w"] == 12
    saved = json.loads((app.home / "layout.json").read_text("utf-8"))
    assert saved == r["layout"]


def test_rejects_foreign_hosts_and_missing_header(server):
    app, base = server
    assert call(base + "/api/state", host="evil.example")[0] == 403           # DNS rebinding
    assert call(base + "/api/layout", "POST", {}, {"Content-Type": "application/json"})[0] == 403  # CSRF
    assert call(base + "/api/quit", "POST", {})[0] == 403
    assert call(base + "/api/layout", "POST", b"not json", W)[0] == 400


def test_upload_media_and_serve_it_safely(server):
    app, base = server
    buf = BytesIO()
    Image.new("RGB", (8, 8), "blue").save(buf, "PNG")
    code, r = call(base + "/api/upload?name=fundo.png", "POST", buf.getvalue(), {**W, "Content-Type": "application/octet-stream"})
    assert code == 200 and r["name"] in r["media"]
    assert call(base + "/api/media/" + r["name"])[1][:4] == b"\x89PNG"
    assert call(base + "/api/media/..%2Flayout.json")[0] == 404
    assert call(base + "/api/upload?name=x.exe", "POST", b"MZ", W)[0] == 400
    assert call(base + "/api/upload?name=x.png", "POST", b"garbage", W)[0] == 400


def test_templates_focus_reset_and_unknown(server):
    app, base = server
    code, r = call(base + "/api/template?name=minimo&orientation=landscape")
    assert code == 200 and [s["module"] for s in r["slots"]] == ["clock", "date", "cpu_temp", "gpu_temp"]
    assert call(base + "/api/template?name=../../x")[0] == 400
    assert call(base + "/api/focus", "POST", {"page": 0}, W)[0] == 200
    assert call(base + "/api/reset", "POST", {}, W)[1]["layout"] == L.default_layout()
    assert call(base + "/api/nope")[0] == 404


def test_second_instance_detection_needs_our_app(tmp_path):
    port = free_port()
    assert not A.already_running(port)  # nothing listening
    s = socket.socket()
    s.bind(("127.0.0.1", port))
    s.listen(1)  # something else owns the port
    try:
        assert not A.already_running(port)
    finally:
        s.close()


def test_notify_test_endpoint_shows_a_sample_notification(server):
    from rhinos_buddy import notifications
    app, base = server
    n = notifications.get_notifier()
    n.history.clear()
    code, _ = call(base + "/api/notify_test", "POST", {}, W)
    assert code == 200 and n.active() is not None
    code, st = call(base + "/api/status")
    assert code == 200 and "notifications" in st
    n.history.clear()


def test_whatsnew_popup_flow_through_the_api(server):
    from rhinos_buddy import __version__
    app, base = server
    code, st = call(base + "/api/state")
    assert code == 200 and st["whatsnew"]["show"] is True and st["whatsnew"]["notes"]["version"] == __version__
    code, r = call(base + "/api/whatsnew", "POST", {"seen": True}, W)           # closed it
    assert code == 200 and r["show"] is False and r["hide"] is False
    assert call(base + "/api/state")[1]["whatsnew"]["show"] is False            # not shown again for this version
    code, r = call(base + "/api/whatsnew", "POST", {"hide": True}, W)           # "do not show again"
    assert r["hide"] is True
    assert call(base + "/api/whatsnew", "POST", {"hide": False}, W)[1]["hide"] is False
    assert call(base + "/api/whatsnew", "POST", {"seen": True})[0] == 403       # needs the CSRF header like every POST
