"""Phone access (1.4.0): the QR encoder, the LAN server's security rules and the editor endpoints."""
import http.client
import socket
import threading

import numpy as np
import pytest

from rhinos_buddy import app as A
from rhinos_buddy import appdata, phone, qr
from rhinos_buddy.runner import Runner
from tests.test_app import W, call, free_port as _free_port


def free_port():
    """A port whose successor (the phone server uses port + 1) is free too."""
    for _ in range(50):
        p = _free_port()
        try:
            with socket.socket() as s:
                s.bind(("127.0.0.1", p + 1))
            return p
        except OSError:
            continue
    raise RuntimeError("no free port pair")


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


def test_pairing_codes_are_long_and_random():
    a, b = phone.new_secret(), phone.new_secret()
    assert a != b and len(a) >= 22


# ---------------------------------------------------------------- the LAN server
import json
from io import BytesIO

from PIL import Image


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def req(acc, path, method="GET", cookie=None, host=None, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", acc.port, timeout=5)
    c.putrequest(method, path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{acc.port}")
    if cookie:
        c.putheader("Cookie", cookie)
    data = json.dumps(body).encode() if body is not None else b""
    for k, v in (headers or {}).items():
        c.putheader(k, v)
    if method == "POST":
        c.putheader("Content-Length", str(len(data)))
    c.endheaders(data if method == "POST" else None)
    r = c.getresponse()
    out = (r.status, r.read(), {k.lower(): v for k, v in r.getheaders()})
    c.close()
    return out


W_HDR = {"X-Rhinos-Buddy": "1"}


@pytest.fixture
def env(tmp_path):
    """A real App (layout, runner) with phone access listening on loopback instead of the LAN address."""
    port = free_port()
    runner = Runner(tmp_path, hardware=False)
    runner.start()
    clock = Clock()
    app = A.App(tmp_path, runner, port)
    acc = phone.PhoneAccess(tmp_path, frame=runner.preview_jpeg, main_port=port, bind_ip="127.0.0.1", api=app, clock=clock)
    app.phone = acc
    acc.clock_ctl = clock
    acc.configure(enabled=True)
    assert acc.running, acc.error
    yield app, acc
    acc.stop()
    runner.stop()


def pair(acc, ua="Mozilla/5.0 (iPhone; CPU iPhone OS 17)"):
    """Scan the QR code: returns the cookie header value of the new session."""
    code, _ = acc.pair_code()
    status, _, hdr = req(acc, "/p?c=" + code, headers={"User-Agent": ua})
    assert status == 303, status
    return hdr["set-cookie"].split(";")[0]


def test_nothing_works_without_pairing(env):
    _, acc = env
    for path in ("/m", "/", "/m/frame.jpg", "/api/state", "/m?t=anything", "/m/frame.jpg?t=" + acc.pair_code()[0]):
        status, body, _ = req(acc, path)
        assert status == 403, path
    assert b"QR" in req(acc, "/m")[1]
    assert req(acc, "/p")[0] == 403 and req(acc, "/p?c=wrong")[0] == 403


def test_scanning_the_qr_code_starts_a_session_cookie(env):
    _, acc = env
    code, left = acc.pair_code()
    assert phone.PAIR_SECONDS - 5 < left <= phone.PAIR_SECONDS
    status, _, hdr = req(acc, "/p?c=" + code)
    assert status == 303 and hdr["location"] == "/"
    sc = hdr["set-cookie"]
    assert sc.startswith("rb_s=") and "HttpOnly" in sc and "SameSite=Strict" in sc
    assert "Max-Age" not in sc and "Expires" not in sc                       # a session cookie: closing the browser ends it
    assert len(sc.split("=")[1].split(";")[0]) >= 40                          # 256-bit id
    cookie = sc.split(";")[0]
    status, body, hdr = req(acc, "/m", cookie=cookie)
    assert status == 200 and b"/m/frame.jpg" in body and "default-src 'none'" in hdr["content-security-policy"]
    status, jpg, hdr = req(acc, "/m/frame.jpg", cookie=cookie)
    assert status == 200 and Image.open(BytesIO(jpg)).format == "JPEG" and hdr["cache-control"] == "no-store"
    assert hdr["referrer-policy"] == "no-referrer" and hdr["x-frame-options"] == "DENY"


def test_the_qr_code_works_once_and_then_a_new_one_appears(env):
    _, acc = env
    first, _ = acc.pair_code()
    pair(acc)
    second, _ = acc.pair_code()
    assert second != first
    assert req(acc, "/p?c=" + first)[0] == 403                                # the used code is dead
    assert acc.status()["url"].endswith("/p?c=" + second)


def test_the_qr_code_expires_after_five_minutes(env):
    _, acc = env
    code, _ = acc.pair_code()
    acc.clock_ctl.t += phone.PAIR_SECONDS - 1
    assert acc.status()["seconds_left"] in (0, 1)
    acc.clock_ctl.t += 2
    assert req(acc, "/p?c=" + code)[0] == 403                                 # too late
    st = acc.status()
    assert st["url"].endswith("/p?c=" + acc.pair_code()[0]) and not st["url"].endswith(code)
    assert st["seconds_left"] >= phone.PAIR_SECONDS - 2


def test_a_session_has_no_time_limit(env):
    _, acc = env
    cookie = pair(acc)
    acc.clock_ctl.t += 3 * 24 * 3600                                           # days later
    assert req(acc, "/m", cookie=cookie)[0] == 200


def test_unknown_sessions_and_wrong_codes_lock_the_address_out(env):
    _, acc = env
    for _ in range(phone.MAX_FAILS):
        assert req(acc, "/m", cookie="rb_s=guess")[0] == 403
    status, _, hdr = req(acc, "/p?c=" + acc.pair_code()[0])                   # even the right code waits now
    assert status == 429 and "retry-after" in hdr


def test_garbage_cookies_do_not_crash_it(env):
    _, acc = env
    for c in ("", ";;;", "rb_s", "rb_s=", "x=y; rb_s=\x00", "rb_s=" + "A" * 5000):
        assert req(acc, "/m", cookie=c)[0] in (403, 429)


def test_the_pc_can_disconnect_devices(env):
    _, acc = env
    a, b = pair(acc), pair(acc, ua="Mozilla/5.0 (Linux; Android 14)")
    devs = acc.devices()
    assert [d["device"] for d in devs] == ["iPhone", "Android"] and all(d["ip"] == "127.0.0.1" for d in devs)
    acc.configure(disconnect=devs[0]["id"])
    assert req(acc, "/m", cookie=a)[0] == 403 and req(acc, "/m", cookie=b)[0] == 200
    acc.configure(disconnect_all=True)
    assert req(acc, "/m", cookie=b)[0] == 403 and acc.devices() == []


def test_turning_it_off_disconnects_everyone_and_closes_the_port(env):
    _, acc = env
    cookie = pair(acc)
    port = acc.port
    acc.configure(enabled=False)
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", port), timeout=1)
    acc.configure(enabled=True)
    assert req(acc, "/m", cookie=cookie)[0] == 403                             # sessions never outlive the server


def test_sessions_are_not_stored_on_disk(env):
    app, acc = env
    pair(acc)
    for f in app.home.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".tmp", ".log"):
            assert b"rb_s" not in f.read_bytes() and b"session" not in f.read_bytes().lower().replace(b"sessions", b"")


def test_only_so_many_devices_at_once(env):
    _, acc = env
    cookies_ = [pair(acc) for _ in range(phone.MAX_SESSIONS + 3)]
    assert len(acc.devices()) == phone.MAX_SESSIONS
    assert req(acc, "/m", cookie=cookies_[-1])[0] == 200


def test_host_header_is_checked(env):
    _, acc = env
    cookie = pair(acc)
    assert req(acc, "/m", cookie=cookie, host="evil.example.com")[0] == 403
    assert req(acc, "/m", cookie=cookie, host="127.0.0.1:1")[0] == 403
    assert req(acc, "/m", cookie=cookie, host=f"localhost:{acc.port}")[0] == 200


def test_viewing_is_read_only_by_default(env):
    _, acc = env
    cookie = pair(acc)
    assert acc.edit is False
    assert req(acc, "/", cookie=cookie)[0] == 303 and req(acc, "/", cookie=cookie)[2]["location"] == "/m"
    for path in ("/api/state", "/api/layout", "/api/quit", "/api/phone", "/api/preview.png"):
        assert req(acc, path, cookie=cookie)[0] == 404, path
        assert req(acc, path, "POST", cookie=cookie, body={}, headers=W_HDR)[0] == 403, path
    for method in ("PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"):
        assert req(acc, "/m", method, cookie=cookie)[0] == 405, method


# ---------------------------------------------------------------- editing from the phone
def test_editing_has_its_own_switch_and_serves_the_same_panel(env):
    app, acc = env
    cookie = pair(acc)
    acc.configure(edit=True)
    status, html, hdr = req(acc, "/", cookie=cookie)
    assert status == 200 and b"window.RB_REMOTE=true" in html and b"Rhino's Buddy Supervisor" in html
    assert "script-src 'self' 'unsafe-inline'" in hdr["content-security-policy"]
    assert html.count(b"RB_REMOTE=true") == 1 and html.index(b"RB_REMOTE=true") < html.index(b"<style>")
    status, body, _ = req(acc, "/api/state", cookie=cookie)
    st = json.loads(body)
    assert status == 200 and st["layout"]["pages"] and st["catalog"]["modules"] and st["home"] == "" and st["whatsnew"]["show"] is False
    assert isinstance(st["rev"], int) and st["autostart"]["supported"] is False
    assert str(app.home) not in body.decode("utf-8")                            # no folder paths leave the PC
    for path in ("/api/status", "/api/sensors"):
        assert req(acc, path, cookie=cookie)[0] == 200, path
    assert req(acc, "/api/preview.png", cookie=cookie)[2]["content-type"] == "image/png"
    assert "slots" in json.loads(req(acc, "/api/template?name=vazio&orientation=landscape", cookie=cookie)[1])
    assert req(acc, "/api/template?name=nope", cookie=cookie)[0] == 400
    assert req(acc, "/api/media/..%2F..%2Fui.json", cookie=cookie)[0] == 404
    acc.configure(edit=False)                                                    # switching it off takes effect at once
    assert req(acc, "/api/state", cookie=cookie)[0] == 404 and req(acc, "/", cookie=cookie)[0] == 303


def test_the_phone_cannot_reach_anything_dangerous(env):
    _, acc = env
    cookie = pair(acc)
    acc.configure(edit=True)
    for path in ("/api/quit", "/api/autostart", "/api/reset", "/api/upload?name=x.png", "/api/phone", "/api/reconnect", "/api/lang",
                 "/api/whatsnew", "/api/notify_test", "/api/ports"):
        assert req(acc, path, "POST", cookie=cookie, body={}, headers=W_HDR)[0] == 404, path
        assert req(acc, path, cookie=cookie)[0] == 404, path
    assert req(acc, "/api/layout", "POST", cookie=cookie, body={})[0] == 403    # the editor header is required for any change


def test_the_phone_saves_the_layout_and_stale_saves_are_refused(env):
    app, acc = env
    cookie = pair(acc)
    acc.configure(edit=True)
    st = json.loads(req(acc, "/api/state", cookie=cookie)[1])
    lay, rev = st["layout"], st["rev"]
    lay["pages"][0]["name"] = "From phone"
    status, body, _ = req(acc, f"/api/layout?rev={rev}", "POST", cookie=cookie, body=lay, headers=W_HDR)
    out = json.loads(body)
    assert status == 200 and out["rev"] == rev + 1 and out["layout"]["pages"][0]["name"] == "From phone"
    assert appdata.load_layout(app.home)["pages"][0]["name"] == "From phone"      # stored for the next start
    lay["pages"][0]["name"] = "Stale"                                             # saved with the old revision: another device got there first
    status, body, _ = req(acc, f"/api/layout?rev={rev}", "POST", cookie=cookie, body=lay, headers=W_HDR)
    out = json.loads(body)
    assert status == 409 and out["conflict"] is True and out["layout"]["pages"][0]["name"] == "From phone" and out["rev"] == rev + 1
    assert appdata.load_layout(app.home)["pages"][0]["name"] == "From phone"
    assert req(acc, "/api/layout", "POST", cookie=cookie, body="not a layout", headers=W_HDR)[0] == 400
    assert req(acc, "/api/focus", "POST", cookie=cookie, body={"page": 0}, headers=W_HDR)[0] == 200
    assert json.loads(req(acc, "/api/status", cookie=cookie)[1])["rev"] == rev + 1  # the PC editor sees this number change and reloads


def test_the_pc_editor_and_the_phone_share_the_revision(env, tmp_path):
    app, acc = env
    a, _ = app.save_layout(app.runner.layout)
    r0 = app.rev
    out, code = app.save_layout(app.runner.layout, rev=r0)
    assert code == 200 and app.rev == r0 + 1
    out, code = app.save_layout(app.runner.layout, rev=r0)
    assert code == 409 and out["layout"] == app.runner.layout
    out, code = app.save_layout(app.runner.layout)                                # no rev given (old clients): still accepted
    assert code == 200


def test_phone_status_for_the_pc_panel(env):
    app, acc = env
    pair(acc)
    st = app.phone_status()
    assert st["running"] and st["edit"] is False and st["svg"].startswith("<svg") and "/p?c=" in st["url"] and "t=" not in st["url"].split("?", 1)[1].replace("c=", "")
    assert st["pair_seconds"] == 300 and 0 < st["seconds_left"] <= 300 and len(st["devices"]) == 1
    assert st["devices"][0]["device"] == "iPhone" and "ip" in st["devices"][0] and "id" in st["devices"][0]
    assert st["svg"] == qr.to_svg(qr.encode(st["url"]))                              # the QR on screen is the pairing link


def test_prefs_remember_the_switches_but_never_a_session_or_code(tmp_path):
    acc = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", main_port=free_port(), bind_ip="127.0.0.1")
    assert acc.enabled is False and acc.edit is False                              # both off by default
    acc.configure(enabled=True, edit=True)
    acc.stop()
    again = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", main_port=free_port(), bind_ip="127.0.0.1")
    assert again.enabled and again.edit and again.devices() == []
    raw = (tmp_path / appdata.PREFS_FILE).read_text("utf-8")
    assert "token" not in raw and "rb_s" not in raw and "pair" not in raw


def test_no_local_network_is_reported_not_crashed(tmp_path):
    a = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", ip_finder=lambda: None)
    a.configure(enabled=True)
    assert not a.running and "rede local" in a.error and a.status()["url"] == ""


def test_it_never_binds_every_interface(tmp_path):
    seen = []

    class Spy(phone._PhoneServer):
        def __init__(self, addr, handler):
            seen.append(addr[0])
            super().__init__(("127.0.0.1", addr[1]), handler)

    orig, phone._PhoneServer = phone._PhoneServer, Spy
    try:
        a = phone.PhoneAccess(tmp_path, frame=lambda: b"x", page=b"p", main_port=free_port(), ip_finder=lambda: "192.168.1.50")
        a.configure(enabled=True)
        a.stop()
    finally:
        phone._PhoneServer = orig
    assert seen == ["192.168.1.50"]                                                 # the LAN address, never 0.0.0.0 / ""


def test_editor_endpoints_for_phone_access(server):
    app, base = server
    app.phone._bind_ip = "127.0.0.1"
    code, st = call(base + "/api/phone")
    assert code == 200 and st["enabled"] is False and st["running"] is False and st["url"] == "" and st["devices"] == []
    assert call(base + "/api/phone", "POST", {"enabled": True})[0] == 403          # needs the editor header like every change
    code, st = call(base + "/api/phone", "POST", {"enabled": True, "edit": True}, W)
    assert code == 200 and st["enabled"] and st["running"] and st["edit"] and "/p?c=" in st["url"] and st["svg"].startswith("<svg")
    assert call(base + "/api/status")[1]["phone_on"] is True
    code, st2 = call(base + "/api/phone", "POST", {"renew": True}, W)
    assert st2["url"] != st["url"]
    cookie = pair(app.phone)
    code, st3 = call(base + "/api/phone")
    assert len(st3["devices"]) == 1
    code, st4 = call(base + "/api/phone", "POST", {"disconnect": st3["devices"][0]["id"]}, W)
    assert st4["devices"] == [] and req(app.phone, "/m", cookie=cookie)[0] == 403
    code, st5 = call(base + "/api/phone", "POST", {"enabled": False}, W)
    assert st5["running"] is False and st5["svg"] == "" and call(base + "/api/status")[1]["phone_on"] is False
    # the editor port does not serve the phone page, and with a foreign Host nothing works
    assert call(base + "/m")[0] == 404 and call(base + "/p?c=x")[0] == 404
    assert call(base + "/api/phone", host="192.168.0.5:8765")[0] == 403


def test_the_real_pages(env):
    _, acc = env
    cookie = pair(acc)
    acc.configure(edit=True)
    viewer = req(acc, "/m", cookie=cookie)[1]
    assert b"fetch(" in viewer and b"http://" not in viewer and b"https://" not in viewer and b"same-origin" in viewer
    assert b'href="/"' in viewer                                                    # the link to the panel
    editor = req(acc, "/", cookie=cookie)[1]
    assert b"http://" not in editor.replace(b"http://www.w3.org", b"").replace(b"https://github.com/yungrhino", b"")
    assert b"RB_REMOTE" in editor and b'id="viewlink"' in editor and b"@media (max-width:760px)" in editor


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
