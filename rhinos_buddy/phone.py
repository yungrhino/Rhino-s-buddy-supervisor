"""Phone access: look at the screen from a phone on the same Wi-Fi.

Security model (this is the only part of the program that listens on the network, so it is deliberately tiny):

* OFF by default.  Nothing but 127.0.0.1 is reachable until the user turns it on in System.
* It is a *separate* server from the editor (own port, ``port + 1``), bound to the PC's private LAN address only -
  never ``0.0.0.0`` - and it serves just two things: the viewer page and the current frame as an image.
  The editor and its API (layout, uploads, quit...) stay on 127.0.0.1 and are not reachable from the network.
* Every request needs the secret ``t`` token (128 bits, compared in constant time).  The token is shown only in the QR
  code / link on the PC and can be replaced at any time, which invalidates the old link at once.
* Only clients with a private or loopback address are served (so a router that forwards the port to the internet
  still gets nothing), and the Host header must be one of this PC's own addresses.
* Read-only (GET): no way to change anything from the phone.  Repeated wrong tokens lock that address out for a while.
"""

from __future__ import annotations

import hmac
import ipaddress
import json
import logging
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import appdata, qr

log = logging.getLogger("rhinos_buddy.phone")

MAX_FAILS = 8          # wrong tokens allowed ...
FAIL_WINDOW = 60.0     # ... within this many seconds, before the address is locked out
LOCK_SECONDS = 300.0


def new_token() -> str:
    return secrets.token_urlsafe(16)  # 128 bits


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


class Lockout:
    """Counts wrong tokens per client address."""

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


class _PhoneServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


_DENIED_PAGE = (b'<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
                b'<body style="background:#000;color:#ff8787;font:16px system-ui;padding:24px;text-align:center">'
                b'<p>Link inv\xc3\xa1lido ou trocado. Escaneie o QR code de novo no PC.</p>'
                b'<p>Invalid or replaced link. Scan the QR code on the PC again.</p>')


def _make_handler(access: "PhoneAccess"):
    class Handler(BaseHTTPRequestHandler):
        server_version = "RhinosBuddy-Phone"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

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

        def _method_not_allowed(self):
            self._send(405, b"read-only", "text/plain; charset=utf-8", {"Allow": "GET"})

        do_POST = do_PUT = do_DELETE = do_PATCH = do_HEAD = do_OPTIONS = _method_not_allowed  # noqa: N815

        def do_GET(self):  # noqa: N802
            ip = self.client_address[0]
            if not is_private_client(ip):
                return self._text(403, "forbidden")
            if not access.host_ok(self.headers.get("Host") or ""):
                return self._text(403, "forbidden")
            if access.lockout.blocked(ip):
                return self._send(429, b"too many attempts", "text/plain; charset=utf-8", {"Retry-After": str(int(LOCK_SECONDS))})
            u = urlparse(self.path)
            token = (parse_qs(u.query).get("t") or [""])[0]
            if not access.token_ok(token):
                access.lockout.fail(ip)
                if u.path == "/m":  # a stale QR code: say what to do (the same answer for any wrong token)
                    return self._send(403, _DENIED_PAGE, "text/html; charset=utf-8")
                return self._text(403, "forbidden")
            access.lockout.ok(ip)
            try:
                if u.path == "/m":
                    return self._send(200, access.page(), "text/html; charset=utf-8", {
                        "Content-Security-Policy": "default-src 'none'; img-src blob:; connect-src 'self'; "
                                                   "style-src 'unsafe-inline'; script-src 'unsafe-inline'"})
                if u.path == "/m/frame.jpg":
                    return self._send(200, access.frame(), "image/jpeg")
                return self._text(404, "not found")
            except Exception:
                log.exception("phone GET failed")
                return self._text(500, "error")

    return Handler


class PhoneAccess:
    """Owns the optional LAN server and its token; the editor drives it through ``configure``."""

    def __init__(self, home: Path, frame, page: bytes | None = None, main_port: int = 8765, bind_ip=None, ip_finder=lan_ip):
        self.home, self.frame, self.main_port = Path(home), frame, main_port
        self.port = main_port + 1
        self._page = page
        self._bind_ip, self._ip_finder = bind_ip, ip_finder   # bind_ip: fixed address (tests); else the LAN address
        self.lockout = Lockout()
        self.server: _PhoneServer | None = None
        self.thread: threading.Thread | None = None
        self.error = ""
        self.ip = ""
        prefs = appdata.load_prefs(self.home)
        self.enabled = prefs["phone_enabled"]
        self.token = prefs["phone_token"] or new_token()

    # -- checks used by the handler
    def token_ok(self, given: str) -> bool:
        return bool(given) and hmac.compare_digest(given.encode("utf-8"), self.token.encode("utf-8"))

    def host_ok(self, host: str) -> bool:
        h = host.strip().lower()
        if not h.endswith(f":{self.port}"):
            return False
        name = h[: -len(f":{self.port}")]
        return name in ("127.0.0.1", "localhost") or name == self.ip

    def page(self) -> bytes:
        if self._page is not None:
            return self._page
        from .app import WEB_DIR

        return (WEB_DIR / "mobile.html").read_bytes()

    # -- lifecycle
    def _save(self) -> None:
        prefs = appdata.load_prefs(self.home)
        prefs["phone_enabled"], prefs["phone_token"] = self.enabled, self.token
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
        self.thread = threading.Thread(target=self.server.serve_forever, name="phone-access", daemon=True)
        self.thread.start()
        log.info("Phone access listening on %s:%d", ip, self.port)
        return True

    def stop(self) -> None:
        srv, self.server = self.server, None
        if srv is not None:
            srv.shutdown()
            srv.server_close()
            log.info("Phone access stopped")

    def configure(self, enabled: bool | None = None, rotate: bool = False) -> None:
        if rotate:
            self.token = new_token()
        if enabled is not None:
            self.enabled = enabled
        self._save()
        if self.enabled:
            if self.server is None:
                self.start()
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

    def url(self) -> str:
        return f"http://{self.ip}:{self.port}/m?t={self.token}" if self.running else ""

    def status(self) -> dict:
        out = {"enabled": self.enabled, "running": self.running, "port": self.port, "error": self.error,
               "ip": self.ip if self.running else "", "url": self.url(), "svg": ""}
        if out["url"]:
            out["svg"] = qr.to_svg(qr.encode(out["url"]))
        return out
