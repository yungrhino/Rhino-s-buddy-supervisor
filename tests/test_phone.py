"""Phone access (1.4.0): the QR encoder, the LAN server's security rules and the editor endpoints."""
import http.client
import socket
import threading

import numpy as np
import pytest

from rhinos_buddy import app as A
from rhinos_buddy import appdata, phone, qr
from rhinos_buddy.runner import Runner
from tests.test_app import W, call, free_port


# ---------------------------------------------------------------- QR code
def _decode(text: str) -> str:
    cv2 = pytest.importorskip("cv2")
    a = np.array(qr.encode(text), dtype=np.uint8)
    det = cv2.QRCodeDetector()
    for scale in (8, 10, 12):  # the detector is picky about sizes; a real phone camera is not
        img = cv2.resize(np.pad((1 - a) * 255, 6, constant_values=255).astype(np.uint8), None, fx=scale, fy=scale,
                         interpolation=cv2.INTER_NEAREST)
        out = det.detectAndDecode(img)[0]
        if out == text:
            return out
    return out


@pytest.mark.parametrize("text", [
    "HELLO",
    "http://192.168.0.12:8766/m?t=Zm9vYmFyYmF6cXV4MTIzNA",
    "http://10.100.100.100:8766/m?t=aaaaaaaaaaaaaaaaaaaaaa",
    "http://172.16.254.1:8766/m?t=-_-_-_-_-_-_-_-_-_-_-_",
])
def test_qr_codes_decode_back_to_the_link(text):
    assert _decode(text) == text


def test_qr_structure_and_limits():
    m = qr.encode("http://192.168.0.12:8766/m?t=Zm9vYmFyYmF6cXV4MTIzNA")
    n = len(m)
    assert n == 33 and all(len(r) == n for r in m)                 # version 4
    assert m[0][:7] == [True] * 7 and m[1][:7] == [True, False, False, False, False, False, True]   # finder pattern
    assert qr.encode("x" * qr.capacity())                          # the largest accepted text
    with pytest.raises(ValueError):
        qr.encode("x" * (qr.capacity() + 1))
    svg = qr.to_svg(m)
    assert svg.startswith("<svg") and "<script" not in svg and "http" not in svg.replace("http://www.w3.org/2000/svg", "")


# ---------------------------------------------------------------- helpers
def test_which_clients_are_served():
    for ip in ("192.168.1.20", "10.0.0.5", "172.16.3.4", "127.0.0.1", "169.254.1.1", "::1", "::ffff:192.168.0.9"):
        assert phone.is_private_client(ip), ip
    for ip in ("8.8.8.8", "1.1.1.1", "203.0.113.9", "2001:4860:4860::8888", "garbage", ""):
        assert not phone.is_private_client(ip), ip


def test_lockout_after_repeated_wrong_tokens():
    t = {"v": 0.0}
    lk = phone.Lockout(clock=lambda: t["v"])
    for _ in range(phone.MAX_FAILS - 1):
        lk.fail("192.168.1.9")
    assert not lk.blocked("192.168.1.9")
    lk.fail("192.168.1.9")
    assert lk.blocked("192.168.1.9") and not lk.blocked("192.168.1.10")   # only that address
    t["v"] = phone.LOCK_SECONDS + 1
    assert not lk.blocked("192.168.1.9")                                  # it ends
    lk.fail("192.168.1.9"); lk.ok("192.168.1.9")
    assert not lk._fails.get("192.168.1.9")                               # a right token clears the count


def test_tokens_are_long_and_random():
    a, b = phone.new_token(), phone.new_token()
    assert a != b and len(a) >= 22 and appdata._clean_token(a) == a
    assert appdata._clean_token("short") == "" and appdata._clean_token("bad token with spaces!!") == ""


# ---------------------------------------------------------------- the LAN server
@pytest.fixture
def access(tmp_path):
    port = free_port()
    acc = phone.PhoneAccess(tmp_path, frame=lambda: b"\xff\xd8JPEGDATA", page=b"<html>viewer</html>", main_port=port - 1, bind_ip="127.0.0.1")
    acc.configure(enabled=True)
    assert acc.running, acc.error
    yield acc
    acc.stop()


def get(acc, path, host=None, method="GET"):
    c = http.client.HTTPConnection("127.0.0.1", acc.port, timeout=5)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{acc.port}")
    c.endheaders()
    r = c.getresponse()
    body = r.read()
    out = (r.status, body, dict(r.getheaders()))
    c.close()
    return out


def test_phone_server_needs_the_token(access):
    assert get(access, "/m")[0] == 403
    assert get(access, "/m/frame.jpg")[0] == 403
    code, body, _ = get(access, "/m?t=wrong")
    assert code == 403 and b"QR" in body and access.token.encode() not in body        # friendly page for a stale QR, no secrets in it
    assert get(access, "/m/frame.jpg?t=" + access.token[:-1])[0] == 403
    code, body, hdr = get(access, "/m?t=" + access.token)
    assert code == 200 and body == b"<html>viewer</html>"
    assert "default-src 'none'" in hdr["Content-Security-Policy"] and hdr["Cache-Control"] == "no-store"
    assert hdr["Referrer-Policy"] == "no-referrer" and hdr["X-Frame-Options"] == "DENY"
    code, body, hdr = get(access, "/m/frame.jpg?t=" + access.token)
    assert code == 200 and body.startswith(b"\xff\xd8") and hdr["Content-Type"] == "image/jpeg"


def test_phone_server_is_read_only_and_serves_nothing_else(access):
    t = "?t=" + access.token
    for path in ("/", "/index.html", "/api/state", "/api/layout", "/api/quit", "/api/phone", "/api/media/x.png", "/../etc/passwd", "/m/other"):
        assert get(access, path + t)[0] == 404, path
    for method in ("POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        assert get(access, "/m" + t, method=method)[0] == 405, method


def test_phone_server_checks_the_host_header(access):
    t = "?t=" + access.token
    assert get(access, "/m" + t, host="evil.example.com")[0] == 403           # DNS-rebinding style names
    assert get(access, "/m" + t, host="127.0.0.1:1")[0] == 403                # wrong port
    assert get(access, "/m" + t, host=f"localhost:{access.port}")[0] == 200


def test_phone_server_locks_out_a_guessing_client(access):
    for _ in range(phone.MAX_FAILS):
        assert get(access, "/m?t=guess")[0] == 403
    code, _, hdr = get(access, "/m?t=" + access.token)                        # even the right token waits now
    assert code == 429 and "Retry-After" in hdr


def test_new_link_invalidates_the_old_one(access):
    old = access.token
    access.configure(rotate=True)
    assert access.token != old
    assert get(access, "/m?t=" + old)[0] == 403
    assert get(access, "/m?t=" + access.token)[0] == 200


def test_turning_it_off_closes_the_port_and_survives_restarts(tmp_path):
    port = free_port()
    mk = lambda: phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", main_port=port - 1, bind_ip="127.0.0.1")  # noqa: E731
    a = mk()
    assert a.enabled is False and not a.running                                # off by default
    a.configure(enabled=True)
    tok = a.token
    b = mk()                                                                   # a "restart": the choice and the link are remembered
    assert b.enabled and b.token == tok and not b.running
    a.stop()
    b.apply()
    assert b.running
    b.configure(enabled=False)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)
    assert not mk().enabled
    b.stop()


def test_no_local_network_is_reported_not_crashed(tmp_path):
    a = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", ip_finder=lambda: None)
    a.configure(enabled=True)
    assert not a.running and "rede local" in a.error and a.status()["url"] == ""


def test_it_never_binds_every_interface(tmp_path):
    seen = []
    class Spy(phone._PhoneServer):
        def __init__(self, addr, handler):
            seen.append(addr[0]); super().__init__(("127.0.0.1", addr[1]), handler)
    orig, phone._PhoneServer = phone._PhoneServer, Spy
    try:
        a = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", main_port=free_port() - 1, ip_finder=lambda: "192.168.1.50")
        a.configure(enabled=True)
        a.stop()
    finally:
        phone._PhoneServer = orig
    assert seen == ["192.168.1.50"]                                            # the LAN address, never 0.0.0.0 / ""


# ---------------------------------------------------------------- the editor side
def test_editor_endpoints_for_phone_access(server, monkeypatch):
    app, base = server
    app.phone._bind_ip = "127.0.0.1"
    code, st = call(base + "/api/phone")
    assert code == 200 and st["enabled"] is False and st["running"] is False and st["url"] == ""
    assert call(base + "/api/phone", "POST", {"enabled": True})[0] == 403      # needs the editor header like every change
    code, st = call(base + "/api/phone", "POST", {"enabled": True}, W)
    assert code == 200 and st["enabled"] and st["running"] and st["url"].startswith("http://127.0.0.1:") and "/m?t=" in st["url"]
    assert st["svg"].startswith("<svg")
    assert call(base + "/api/status")[1]["phone_on"] is True
    code, st2 = call(base + "/api/phone", "POST", {"rotate": True}, W)
    assert st2["url"] != st["url"]
    code, st3 = call(base + "/api/phone", "POST", {"enabled": False}, W)
    assert st3["running"] is False and st3["svg"] == "" and call(base + "/api/status")[1]["phone_on"] is False
    # the editor port does not serve the phone page, and with a foreign Host nothing works
    assert call(base + "/m?t=" + app.phone.token)[0] == 404
    assert call(base + "/api/phone", host="192.168.0.5:8765")[0] == 403


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
    app.phone.stop()
    srv.shutdown()
    srv.server_close()
    runner.stop()


def test_the_real_viewer_page_and_frame(tmp_path):
    port = free_port()
    runner = Runner(tmp_path, hardware=False)
    runner.start()
    try:
        acc = phone.PhoneAccess(tmp_path, frame=runner.preview_jpeg, main_port=port - 1, bind_ip="127.0.0.1")
        acc.configure(enabled=True)
        code, body, _ = get(acc, "/m?t=" + acc.token)
        assert code == 200 and b"/m/frame.jpg" in body and b"fetch(" in body
        assert b"http://" not in body and b"https://" not in body              # the viewer loads nothing from outside
        code, jpg, _ = get(acc, "/m/frame.jpg?t=" + acc.token)
        from io import BytesIO
        from PIL import Image
        assert code == 200 and Image.open(BytesIO(jpg)).format == "JPEG"
        acc.stop()
    finally:
        runner.stop()
