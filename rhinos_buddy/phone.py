"""Phone access: look at (and optionally edit) the screen from a phone on the same Wi-Fi.

Security model.  This is the only part of the program that listens on the network, so it is deliberately small:

* OFF by default.  Nothing but 127.0.0.1 is reachable until the user turns it on in System.
* A *separate* server from the editor's own one (port + 1), bound to the PC's private LAN address only - never
  ``0.0.0.0``.  The editor on 127.0.0.1 and its full API are not reachable from the network.
* **Pairing, not a fixed link.**  The QR code holds a one-time pairing code that is valid for 5 minutes and dies when
  it is used (a new one appears at once).  Scanning it gives that phone a *session*: a random 256-bit id kept in a
  browser session cookie (HttpOnly, SameSite=Strict, no expiry date - closing the browser ends it).  Sessions live in
  memory only: closing the program, turning phone access off, or "Disconnect" on the PC ends them.
* Viewing is the default.  **Editing needs its own switch** (off by default) and then only a small allow-list of the
  editor's calls works (read state, save the layout, show the page): nothing that quits the program, touches Windows
  start-up, restores defaults or uploads files.
* Only private-network clients are served and the Host header must be one of this PC's addresses.  Wrong pairing
  codes / unknown session ids lock that address out for a while.  Changing calls need the custom header the editor
  sends (a plain cross-site form cannot) on top of SameSite=Strict.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import socket
import sys
import threading
import time
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import appdata, mdns, qr

log = logging.getLogger("rhinos_buddy.phone")

PAIR_SECONDS = 300.0   # how long a QR code can be used to connect
MAX_FAILS = 8          # wrong codes / unknown sessions allowed ...
FAIL_WINDOW = 60.0     # ... within this many seconds, before the address is locked out
LOCK_SECONDS = 300.0
MAX_SESSIONS = 20
COOKIE = "rb_s"


CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no 0/O/1/I: easy to read and to type
CODE_LENGTH = 8                                      # 32**8 = 40 bits; single use, 5 minutes, and a lock-out on wrong tries


def new_secret() -> str:
    """The short pairing code (QR link and typed entry share it). Sessions use 32 random bytes."""
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def normalize_code(text: str) -> str:
    """What a person typed -> the canonical code (any case, spaces and dashes ignored)."""
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())[:32]


def pretty_code(code: str) -> str:
    return f"{code[:4]}-{code[4:]}" if len(code) == CODE_LENGTH else code


def lan_ip() -> str | None:
    """The PC's private address on the local network (Wi-Fi/Ethernet), or None when there is none."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))  # UDP: nothing is sent, it only makes the OS pick the outgoing interface
        ip = s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()
    return ip if is_private_client(ip) and not ipaddress.ip_address(ip).is_loopback else None


_LOCAL_NETS = [ipaddress.ip_network(n) for n in (
    "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "169.254.0.0/16", "127.0.0.0/8", "fc00::/7", "fe80::/10", "::1/128")]


def is_private_client(ip: str) -> bool:
    """Home/office LAN, link-local or loopback addresses only - never anything routable on the internet.
    (An explicit list: Python's ``is_private`` also accepts documentation ranges and similar odd blocks.)"""
    try:
        a = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if a.version == 6 and a.ipv4_mapped:
        a = a.ipv4_mapped
    return any(a.version == n.version and a in n for n in _LOCAL_NETS)


def short_ua(ua: str) -> str:
    u = ua or ""
    for key, name in (("iPhone", "iPhone"), ("iPad", "iPad"), ("Android", "Android"), ("Windows", "Windows"), ("Macintosh", "Mac"), ("Linux", "Linux")):
        if key in u:
            return name
    return (u[:24] or "?")


class Lockout:
    """Counts wrong secrets per client address."""

    def __init__(self, clock=time.monotonic):
        self.clock, self._fails, self._locked = clock, {}, {}
        self._lock = threading.Lock()

    def blocked(self, ip: str) -> bool:
        with self._lock:
            until = self._locked.get(ip)
            if until is None:
                return False
            if self.clock() >= until:
                self._locked.pop(ip, None)
                self._fails.pop(ip, None)
                return False
            return True

    def fail(self, ip: str) -> None:
        now = self.clock()
        with self._lock:
            hits = [t for t in self._fails.get(ip, []) if now - t < FAIL_WINDOW] + [now]
            self._fails[ip] = hits
            if len(hits) >= MAX_FAILS:
                self._locked[ip] = now + LOCK_SECONDS
            if len(self._fails) > 512:  # never grow without bound
                self._fails = {k: v for k, v in self._fails.items() if k == ip}

    def ok(self, ip: str) -> None:
        with self._lock:
            self._fails.pop(ip, None)


def graceful_finish(handler) -> None:
    """Close a connection the polite way: flush, send FIN, then wait briefly for the client to finish reading.
    Closing with unread bytes still in the socket makes Windows reset the connection, and the client then loses the
    answer it was about to read (WinError 10053)."""
    try:
        handler.wfile.flush()
        conn = handler.connection
        conn.shutdown(socket.SHUT_WR)
        conn.settimeout(0.5)
        while conn.recv(4096):
            pass
    except (OSError, ValueError):
        pass


class _PhoneServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second program bind a port that is already in use (and receive some connections),
    # so it must stay off there; elsewhere it only allows a quick restart.
    allow_reuse_address = sys.platform != "win32"


_ENTRY_PAGE = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rhino's Buddy Supervisor</title>
<body style="background:#000;color:#e6e6e6;font:16px system-ui;padding:24px;text-align:center;max-width:420px;margin:0 auto">
<h2 style="font-size:18px">Conectar ao PC / Connect to the PC</h2>
<p style="color:#9aa">Digite o código mostrado no painel do PC.<br>Type the code shown on the PC panel.</p>
<form method="get" action="/p" autocomplete="off">
<input name="c" autofocus maxlength="12" autocapitalize="characters" autocorrect="off" spellcheck="false" inputmode="text"
 placeholder="ABCD-2345" style="width:100%;box-sizing:border-box;font:600 28px ui-monospace,monospace;letter-spacing:.12em;text-transform:uppercase;text-align:center;padding:12px;border-radius:10px;border:1px solid #444;background:#111;color:#fff">
<button style="margin-top:14px;width:100%;font:600 18px system-ui;padding:12px;border:0;border-radius:10px;background:#4dabf7;color:#000">Conectar / Connect</button>
</form></body>""".encode("utf-8")

_DENIED_PAGE = (b'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                b'<body style="background:#000;color:#ff8787;font:16px system-ui;padding:24px;text-align:center">'
                b'<p>Sess\xc3\xa3o inv\xc3\xa1lida ou encerrada. Escaneie o QR code de novo no PC.</p>'
                b'<p>Invalid or ended session. Scan the QR code on the PC again.</p>'
                b'<p><a style="color:#4dabf7" href="/p">C\xc3\xb3digo / Code</a></p>')

EDITOR_CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'")
VIEWER_CSP = "default-src 'none'; img-src blob:; connect-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'"


def _make_handler(access: "PhoneAccess"):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RhinosBuddy-Phone"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def finish(self):
            graceful_finish(self)
            super().finish()

        def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _text(self, code: int, msg: str):
            self._send(code, msg.encode("utf-8"), "text/plain; charset=utf-8")

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _redirect(self, where: str, extra: dict | None = None):
            self._send(303, b"", "text/plain", {"Location": where, **(extra or {})})

        def _method_not_allowed(self):
            self._send(405, b"method not allowed", "text/plain; charset=utf-8", {"Allow": "GET, POST"})

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed  # noqa: N815

        # -- common gate: network, host, lock-out, session
        def _gate(self, need_session: bool = True):
            ip = self.client_address[0]
            if not is_private_client(ip) or not access.host_ok(self.headers.get("Host") or ""):
                self._text(403, "forbidden")
                return None
            if access.lockout.blocked(ip):
                self._send(429, b"too many attempts", "text/plain; charset=utf-8", {"Retry-After": str(int(LOCK_SECONDS))})
                return None
            if not need_session:
                return ip
            raw = self.headers.get("Cookie") or ""
            sid = ""
            try:
                jar = cookies.SimpleCookie()
                jar.load(raw)
                sid = jar[COOKIE].value if COOKIE in jar else ""
            except cookies.CookieError:
                sid = ""
            ses = access.session(sid)
            if ses is None:
                if sid:                       # a cookie we do not know: someone guessing (or an ended session)
                    access.lockout.fail(ip)
                u = urlparse(self.path).path
                if u in ("/", "/m"):
                    self._send(403, _DENIED_PAGE, "text/html; charset=utf-8")
                else:
                    self._text(403, "forbidden")
                return None
            ses.touch(ip, self.headers.get("User-Agent") or "")
            return ses

        def do_GET(self):  # noqa: N802
            u = urlparse(self.path)
            q = parse_qs(u.query)
            if u.path == "/p":                                   # pairing: the QR code points here
                ip = self._gate(need_session=False)
                if ip is None:
                    return
                typed = normalize_code((q.get("c") or [""])[0])
                if not typed:                                    # no code yet: the typing page (not a failed attempt)
                    return self._send(200, _ENTRY_PAGE, "text/html; charset=utf-8")
                sid = access.redeem(typed, ip, self.headers.get("User-Agent") or "")
                if not sid:
                    access.lockout.fail(ip)
                    return self._send(403, _DENIED_PAGE, "text/html; charset=utf-8")
                access.lockout.ok(ip)
                return self._redirect("/", {"Set-Cookie": f"{COOKIE}={sid}; Path=/; HttpOnly; SameSite=Strict"})  # session cookie: no Max-Age
            ses = self._gate()
            if ses is None:
                return
            try:
                if u.path == "/m":
                    return self._send(200, access.page(), "text/html; charset=utf-8", {"Content-Security-Policy": VIEWER_CSP})
                if u.path == "/m/frame.jpg":
                    return self._send(200, access.frame(), "image/jpeg")
                if u.path in ("/", "/index.html"):
                    if not access.edit_allowed():
                        return self._redirect("/m")
                    return self._send(200, access.editor_page(), "text/html; charset=utf-8", {"Content-Security-Policy": EDITOR_CSP})
                if u.path.startswith("/api/") and access.edit_allowed() and access.api is not None:
                    return self._editor_get(u.path, q)
                return self._text(404, "not found")
            except Exception:
                log.exception("phone GET failed")
                return self._text(500, "error")

        def _editor_get(self, path, q):
            api = access.api
            if path == "/api/state":
                return self._json(api.remote_state())
            if path == "/api/status":
                return self._json(api.remote_status())
            if path == "/api/sensors":
                return self._json(api.sensors())
            if path == "/api/preview.png":
                return self._send(200, api.runner.preview_png(), "image/png")
            if path.startswith("/api/media/"):
                data = api.media(Path(unquote(path[len("/api/media/"):])).name)
                return self._send(200, data[0], data[1]) if data else self._json({"error": "Arquivo não encontrado"}, 404)
            if path == "/api/template":
                r = api.template((q.get("name") or ["vazio"])[0], (q.get("orientation") or ["landscape"])[0])
                return self._json(r) if r is not None else self._json({"error": "Modelo inválido"}, 400)
            return self._text(404, "not found")

        def do_POST(self):  # noqa: N802
            try:                                   # read the body first: answering with it unread resets the connection on Windows
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                n = -1
            pre = None
            if 0 <= n <= 2_000_000:
                pre = self.rfile.read(n) if n else b""
            else:
                self.close_connection = True
            ses = self._gate()
            if ses is None:
                return
            if self.headers.get("X-Rhinos-Buddy") != "1":
                return self._text(403, "forbidden")
            if not access.edit_allowed() or access.api is None:
                return self._text(403, "editing from the phone is off")
            u = urlparse(self.path)
            if pre is None:
                return self._json({"error": "Corpo inválido ou grande demais"}, 413)
            raw = pre
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except ValueError:
                return self._json({"error": "JSON inválido"}, 400)
            try:
                if u.path == "/api/layout":
                    rev = (parse_qs(u.query).get("rev") or [None])[0]
                    return self._json(*access.api.save_layout(body, rev))
                if u.path == "/api/focus":
                    access.api.runner.focus(body.get("page") if isinstance(body.get("page"), int) else 0)
                    return self._json({"ok": True})
                return self._text(404, "not found")
            except Exception:
                log.exception("phone POST failed")
                return self._text(500, "error")

    return Handler


class _Session:
    def __init__(self, ip: str, ua: str, clock):
        self.created = self.last = clock()
        self.ip, self.ua = ip, short_ua(ua)
        self._clock = clock

    def touch(self, ip: str, ua: str) -> None:
        self.last = self._clock()


class PhoneAccess:
    """Owns the optional LAN server, the pairing code and the sessions; the editor drives it through ``configure``."""

    def __init__(self, home: Path, frame, page: bytes | None = None, main_port: int = 8765, bind_ip=None, ip_finder=lan_ip,
                 api=None, clock=time.monotonic, editor_page: bytes | None = None):
        self.home, self.frame, self.main_port, self.api = Path(home), frame, main_port, api
        self.port = main_port + 1
        self._page, self._editor_page = page, editor_page
        self._bind_ip, self._ip_finder, self.clock = bind_ip, ip_finder, clock
        self.lockout = Lockout(clock)
        self.server: _PhoneServer | None = None
        self.thread: threading.Thread | None = None
        self.error = ""
        self.ip = ""
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._pair_code, self._pair_expires = "", 0.0
        prefs = appdata.load_prefs(self.home)
        self.enabled, self.edit, self.friendly = prefs["phone_enabled"], prefs["phone_edit"], prefs["phone_friendly"]
        self.responder: mdns.Responder | None = None
        self.friendly_error = ""

    # -- pairing and sessions
    def _fresh_pair(self) -> tuple[str, float]:
        now = self.clock()
        if not self._pair_code or now >= self._pair_expires:
            self._pair_code, self._pair_expires = new_secret(), now + PAIR_SECONDS
        return self._pair_code, self._pair_expires - now

    def pair_code(self) -> tuple[str, float]:
        with self._lock:
            return self._fresh_pair()

    def renew_pair(self) -> None:
        with self._lock:
            self._pair_code = ""
            self._fresh_pair()

    def redeem(self, code: str, ip: str, ua: str) -> str:
        """Use the pairing code: returns a new session id, or '' when the code is wrong, expired or already used."""
        with self._lock:
            cur, _ = self._fresh_pair()
            if not code or not hmac.compare_digest(code.encode("utf-8"), cur.encode("utf-8")):
                return ""
            sid = secrets.token_urlsafe(32)
            if len(self._sessions) >= MAX_SESSIONS:  # drop the one unused for longest
                self._sessions.pop(min(self._sessions, key=lambda k: self._sessions[k].last))
            self._sessions[sid] = _Session(ip, ua, self.clock)
            self._pair_code = ""                     # single use: the next QR code is a different one
            self._fresh_pair()
            return sid

    def session(self, sid: str) -> _Session | None:
        if not sid:
            return None
        with self._lock:
            return self._sessions.get(sid)

    def devices(self) -> list[dict]:
        now = self.clock()
        with self._lock:
            return [{"id": sid[:8], "ip": s.ip, "device": s.ua, "since": int(now - s.created), "idle": int(now - s.last)}
                    for sid, s in sorted(self._sessions.items(), key=lambda kv: kv[1].created)]

    def disconnect(self, short_id: str) -> bool:
        with self._lock:
            hit = [sid for sid in self._sessions if sid[:8] == short_id]
            for sid in hit:
                del self._sessions[sid]
            return bool(hit)

    def disconnect_all(self) -> None:
        with self._lock:
            self._sessions.clear()

    def edit_allowed(self) -> bool:
        return self.edit

    # -- checks used by the handler
    def host_ok(self, host: str) -> bool:
        h = host.strip().lower()
        if not h.endswith(f":{self.port}"):
            return False
        name = h[: -len(f":{self.port}")]
        return name in ("127.0.0.1", "localhost") or name == self.ip or (self.friendly_ok and name == mdns.NAME)

    def page(self) -> bytes:
        if self._page is not None:
            return self._page
        from .app import WEB_DIR

        return (WEB_DIR / "mobile.html").read_bytes()

    def editor_page(self) -> bytes:
        if self._editor_page is not None:
            return self._editor_page
        from .app import WEB_DIR

        html = (WEB_DIR / "index.html").read_bytes()
        return html.replace(b"<head>", b"<head><script>window.RB_REMOTE=true;</script>", 1)  # tells the page it is the phone's copy

    # -- lifecycle
    def _save(self) -> None:
        prefs = appdata.load_prefs(self.home)
        prefs["phone_enabled"], prefs["phone_edit"], prefs["phone_friendly"] = self.enabled, self.edit, self.friendly
        appdata.save_prefs(self.home, prefs)

    def start(self) -> bool:
        self.stop()
        self.error = ""
        ip = self._bind_ip or self._ip_finder()
        if not ip:
            self.error = "Não encontrei uma rede local (Wi-Fi ou cabo). Conecte o PC a uma rede e tente de novo."
            return False
        try:
            self.server = _PhoneServer((ip, self.port), _make_handler(self))
        except OSError as e:
            self.server = None
            self.error = f"Não consegui abrir a porta {self.port} ({e.strerror or e})."
            log.warning("phone access could not start: %s", e)
            return False
        self.ip = ip
        self._start_name()
        self.thread = threading.Thread(target=self.server.serve_forever, name="phone-access", daemon=True)
        self.thread.start()
        log.info("Phone access listening on %s:%d", ip, self.port)
        return True

    def _start_name(self) -> None:
        """The friendly ``rhinos-buddy.local`` name (optional); on failure the IP link keeps working."""
        self._stop_name()
        self.friendly_error = ""
        if self.friendly and self.ip:
            r = mdns.Responder(self.ip)
            if r.start():
                self.responder = r
            else:
                self.friendly_error = r.error or "?"

    def _stop_name(self) -> None:
        r, self.responder = self.responder, None
        if r is not None:
            r.stop()

    @property
    def friendly_ok(self) -> bool:
        return self.responder is not None and self.responder.running

    def stop(self) -> None:
        self._stop_name()
        srv, self.server = self.server, None
        self.disconnect_all()                    # sessions never outlive the server
        if srv is not None:
            srv.shutdown()
            srv.server_close()
            log.info("Phone access stopped")

    def configure(self, enabled: bool | None = None, edit: bool | None = None, renew: bool = False,
                  disconnect: str | None = None, disconnect_all: bool = False, friendly: bool | None = None) -> None:
        if edit is not None:
            self.edit = edit
        if friendly is not None:
            self.friendly = friendly
        if enabled is not None:
            self.enabled = enabled
        self._save()
        if disconnect:
            self.disconnect(disconnect)
        if disconnect_all:
            self.disconnect_all()
        if renew:
            self.renew_pair()
        if self.enabled:
            if self.server is None:
                self.start()
            elif friendly is not None:
                self._start_name()
        else:
            self.stop()
            self.error = ""

    def apply(self) -> None:
        """Called at program start: bring the server up only if it was left on."""
        if self.enabled:
            self.start()

    @property
    def running(self) -> bool:
        return self.server is not None

    def host(self) -> str:
        """What the phone is told to open: the friendly name when it is on and working, else the IP."""
        return mdns.NAME if self.friendly_ok else self.ip

    def url(self) -> str:
        """The address inside the QR code (one-time pairing link)."""
        return f"http://{self.host()}:{self.port}/p?c={self.pair_code()[0]}" if self.running else ""

    def status(self) -> dict:
        out = {"enabled": self.enabled, "running": self.running, "edit": self.edit, "port": self.port, "error": self.error,
               "ip": self.ip if self.running else "", "url": "", "code": "", "manual_url": "", "ip_url": "", "svg": "",
               "friendly": self.friendly, "friendly_ok": self.friendly_ok, "friendly_name": mdns.NAME, "friendly_error": self.friendly_error, "seconds_left": 0, "pair_seconds": int(PAIR_SECONDS),
               "devices": self.devices() if self.running else []}
        if self.running:
            code, left = self.pair_code()
            out["url"] = f"http://{self.host()}:{self.port}/p?c={code}"
            out["code"] = pretty_code(code)
            out["manual_url"] = f"http://{self.host()}:{self.port}/p"
            out["ip_url"] = f"http://{self.ip}:{self.port}/p?c={code}"
            out["seconds_left"] = max(0, int(left))
            out["svg"] = qr.to_svg(qr.encode(out["url"]))
        return out
