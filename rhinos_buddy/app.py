"""The desktop app: a small local web server + the editor window.

    python run_app.py                 open the editor (and run the screen)
    python run_app.py --background    run the screen only (used by "start with Windows")

Running it a second time just opens the editor of the instance that is already running.

Security: the server listens on 127.0.0.1 only, rejects foreign ``Host`` headers (DNS rebinding)
and requires a custom header on every write (browsers cannot send it cross-site without a
CORS pre-flight, which this server never approves).
"""

from __future__ import annotations

import argparse
import json
import logging
import logging.handlers
import math
import mimetypes
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import phone as phone_mod
from . import __version__, __version_title__, appdata, autostart, i18n, release_notes
from . import layout as L
from .runner import Runner

DEFAULT_PORT = 8765
def _web_dir() -> Path:
    here = Path(__file__).resolve().parent / "web"
    if here.is_dir():
        return here
    meipass = getattr(sys, "_MEIPASS", None)  # PyInstaller bundle
    return Path(meipass) / "rhinos_buddy" / "web" if meipass else here


WEB_DIR = _web_dir()
log = logging.getLogger("rhinos_buddy.app")


class _Server(ThreadingHTTPServer):
    """On Windows http.server enables SO_REUSEADDR, which lets a *second* instance bind the same
    port; ask for exclusive use there so "already running" detection works."""

    allow_reuse_address = sys.platform != "win32"
    daemon_threads = True

    def server_bind(self):
        if sys.platform == "win32":
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def _clean(o):
    """JSON cannot carry NaN: sensors that are not available become null."""
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


class App:
    def __init__(self, home: Path, runner: Runner, port: int):
        self.home, self.runner, self.port = home, runner, port
        self.server: _Server | None = None
        self.current = runner.layout      # the last saved layout (the runner applies it on its next tick, so it can lag a moment)
        self.rev = 0                      # bumped on every saved layout: editors compare it to notice each other's changes
        self._layout_lock = threading.Lock()
        self.phone = phone_mod.PhoneAccess(home, frame=runner.preview_jpeg, main_port=port, api=self)
        i18n.set_lang(appdata.load_prefs(home)["lang"])  # the saved interface language

    # ------------------------------------------------------------------ data for the UI
    def state(self) -> dict:
        return _clean({
            "version": __version__,
            "version_title": __version_title__,
            "layout": self.current,
            "catalog": L.catalog(),
            "status": self.runner.status(),
            "lang": i18n.lang(),
            "lang_chosen": appdata.load_prefs(self.home)["lang_chosen"],
            "i18n": i18n.EN,  # the English texts, for the editor page
            "media": appdata.list_media(self.home),
            "autostart": {"supported": autostart.supported(), "enabled": autostart.is_enabled()},
            "home": str(self.home),
            "whatsnew": self.whatsnew(),
            "rev": self.rev,
        })

    # ------------------------------------------------------------------ shared by the PC editor and the phone editor
    def save_layout(self, layout, rev=None) -> tuple[dict, int]:
        """Apply + store a layout.  ``rev`` (what the editor last saw) must still be current, or someone else changed it."""
        if not isinstance(layout, dict):
            return {"error": i18n.t("Layout inválido")}, 400
        with self._layout_lock:
            if rev is not None and str(rev) != str(self.rev):
                return {"error": i18n.t("O layout foi alterado em outro aparelho. Os dados foram atualizados."), "conflict": True, "rev": self.rev,
                        "layout": self.current}, 409
            norm = self.runner.apply(layout)
            appdata.save_layout(self.home, norm)
            self.current = norm
            self.rev += 1
            return {"layout": norm, "rev": self.rev}, 200

    def remote_state(self) -> dict:
        """The editor's state as the phone gets it: no folder paths, nothing about Windows start-up or the phone switch."""
        st = self.state()
        st.update(home="", autostart={"supported": False, "enabled": False}, whatsnew={"show": False, "hide": True, "notes": None},
                  lang_chosen=True)
        return st

    def remote_status(self) -> dict:
        return {**self.runner.status(), "rev": self.rev}

    def media(self, name: str):
        f = self.home / "media" / name
        if name and f.is_file() and f.suffix.lower() in appdata.MEDIA_EXT:
            return f.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream"
        return None

    def template(self, name: str, orient: str):
        if name not in L.TEMPLATES or orient not in dict(L.ROTATIONS):
            return None
        cols, rows = L.grid_size(orient)
        return {"slots": L.template(name, cols, rows)}

    def phone_status(self) -> dict:
        st = self.phone.status()
        if st["error"]:
            st["error"] = i18n.t(st["error"])
        return st

    def whatsnew(self) -> dict:
        prefs = appdata.load_prefs(self.home)
        notes = release_notes.notes_for(__version__, i18n.lang())
        return {"show": release_notes.should_show(__version__, prefs), "hide": prefs["hide_notes"], "notes": notes,
                "history": release_notes.history(i18n.lang())}

    def ports(self) -> list[dict]:
        try:
            from .devices import KNOWN_SERIALS, list_ports

            return [{"device": p["device"], "description": p["description"],
                     "is_screen": p["serial_number"] in KNOWN_SERIALS} for p in list_ports()]
        except Exception:
            return []

    def sensors(self) -> dict:
        m = self.runner.metrics
        data = m.get() if m else {}
        keys = ("cpu", "cpu_temp", "gpu", "gpu_temp", "gpu_mem", "ram", "ram_used_gb", "ram_total_gb",
                "disk", "net_down_h", "net_up_h")
        return _clean({"values": {k: data.get(k) for k in keys},
                       "sources": [{"name": p.label, "ok": p.ok} for p in (m.pollers if m else [])]})


def make_handler(app: App):
    allowed_hosts = {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "Rhino's Buddy Supervisor"
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):  # silence the default stderr logging
            pass

        # -- helpers
        def _send(self, code, body: bytes, ctype="application/json; charset=utf-8", extra=None):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(_clean(obj), ensure_ascii=False).encode("utf-8"))

        def _error(self, code, message):
            self._json({"error": i18n.t(message)}, code)

        def _host_ok(self) -> bool:
            return (self.headers.get("Host") or "") in allowed_hosts

        def _body(self, limit: int) -> bytes | None:
            try:
                n = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                return None
            if n < 0 or n > limit:
                return None
            return self.rfile.read(n)

        # -- GET
        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._error(403, "Host não permitido")
            u = urlparse(self.path)
            path = u.path
            try:
                if path in ("/", "/index.html"):
                    return self._send(200, (WEB_DIR / "index.html").read_bytes(), "text/html; charset=utf-8",
                                      {"Content-Security-Policy": "default-src 'self'; img-src 'self' data: blob:; "
                                       "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'"})
                if path == "/api/ping":
                    return self._json({"app": "rhinos_buddy", "version": __version__})
                if path == "/api/state":
                    return self._json(app.state())
                if path == "/api/status":
                    return self._json({**app.runner.status(), "phone_on": app.phone.running, "rev": app.rev})
                if path == "/api/phone":
                    return self._json(app.phone_status())
                if path == "/api/ports":
                    return self._json(app.ports())
                if path == "/api/sensors":
                    return self._json(app.sensors())
                if path == "/api/preview.png":
                    return self._send(200, app.runner.preview_png(), "image/png")
                if path.startswith("/api/media/"):
                    name = Path(unquote(path[len("/api/media/"):])).name
                    f = app.home / "media" / name
                    if name and f.is_file() and f.suffix.lower() in appdata.MEDIA_EXT:
                        return self._send(200, f.read_bytes(), mimetypes.guess_type(name)[0] or "application/octet-stream")
                    return self._error(404, "Arquivo não encontrado")
                if path == "/api/autostart":
                    return self._json({"supported": autostart.supported(), "enabled": autostart.is_enabled()})
                if path == "/api/template":
                    q = parse_qs(u.query)
                    name = q.get("name", ["vazio"])[0]
                    orient = q.get("orientation", ["landscape"])[0]
                    if name not in L.TEMPLATES or orient not in dict(L.ROTATIONS):
                        return self._error(400, "Modelo inválido")
                    cols, rows = L.grid_size(orient)
                    return self._json({"slots": L.template(name, cols, rows)})
                return self._error(404, "Não encontrado")
            except Exception as e:  # never kill the connection thread silently
                log.exception("GET %s failed", path)
                return self._error(500, str(e))

        # -- POST
        def do_POST(self):  # noqa: N802
            if not self._host_ok():
                return self._error(403, "Host não permitido")
            if self.headers.get("X-Rhinos-Buddy") != "1":
                return self._error(403, "Requisição não permitida")
            u = urlparse(self.path)
            try:
                if u.path == "/api/layout":
                    raw = self._body(2_000_000)
                    if raw is None:
                        return self._error(413, "Corpo inválido ou grande demais")
                    layout = json.loads(raw.decode("utf-8"))
                    out, code = app.save_layout(layout, parse_qs(u.query).get("rev", [None])[0])
                    return self._json(out, code)
                if u.path == "/api/upload":
                    raw = self._body(appdata.MAX_MEDIA_BYTES + 1024)
                    if raw is None:
                        return self._error(413, "Arquivo muito grande (máximo 25 MB).")
                    name = parse_qs(u.query).get("name", ["imagem.png"])[0]
                    try:
                        stored = appdata.save_media(app.home, name, raw)
                    except ValueError as e:
                        return self._error(400, str(e))
                    return self._json({"name": stored, "media": appdata.list_media(app.home)})
                if u.path == "/api/focus":
                    page = json.loads((self._body(1000) or b"{}").decode("utf-8")).get("page", 0)
                    app.runner.focus(page if isinstance(page, int) else 0)
                    return self._json({"ok": True})
                if u.path == "/api/whatsnew":  # the pop-up was closed (optionally: "do not show again")
                    body = json.loads((self._body(1000) or b"{}").decode("utf-8"))
                    prefs = appdata.load_prefs(app.home)
                    if body.get("seen") is True:
                        prefs["seen_version"] = __version__
                    if isinstance(body.get("hide"), bool):
                        prefs["hide_notes"] = body["hide"]
                    appdata.save_prefs(app.home, prefs)
                    return self._json(app.whatsnew())
                if u.path == "/api/lang":  # the language picked in the first window, the top bar or System
                    body = json.loads((self._body(1000) or b"{}").decode("utf-8"))
                    if body.get("lang") not in i18n.LANGS:
                        return self._error(400, "Idioma inválido")
                    prefs = appdata.load_prefs(app.home)
                    prefs["lang"], prefs["lang_chosen"] = body["lang"], True
                    appdata.save_prefs(app.home, prefs)
                    i18n.set_lang(body["lang"])
                    app.runner.reapply()  # texts drawn on the screen (dates, alerts, labels) follow the language
                    return self._json(app.state())
                if u.path == "/api/phone":  # phone access: on/off and "new link" (only from the editor, i.e. this PC)
                    body = json.loads((self._body(1000) or b"{}").decode("utf-8"))
                    en, ed = body.get("enabled"), body.get("edit")
                    dc = body.get("disconnect")
                    app.phone.configure(enabled=en if isinstance(en, bool) else None, edit=ed if isinstance(ed, bool) else None,
                                        renew=body.get("renew") is True, disconnect=dc if isinstance(dc, str) else None,
                                        disconnect_all=body.get("disconnect_all") is True)
                    return self._json(app.phone_status())
                if u.path == "/api/notify_test":
                    app.runner.notify_test()
                    return self._json({"ok": True})
                if u.path == "/api/reconnect":
                    app.runner.reconnect()
                    return self._json({"ok": True})
                if u.path == "/api/autostart":
                    raw = self._body(1000) or b"{}"
                    enabled = bool(json.loads(raw.decode("utf-8")).get("enabled"))
                    try:
                        autostart.set_enabled(enabled)
                    except RuntimeError as e:
                        return self._error(400, str(e))
                    return self._json({"supported": True, "enabled": autostart.is_enabled()})
                if u.path == "/api/reset":
                    out, code = app.save_layout(L.default_layout())
                    return self._json(out, code)
                if u.path == "/api/quit":
                    self._json({"ok": True})
                    threading.Thread(target=app.server.shutdown, daemon=True).start()
                    return
                return self._error(404, "Não encontrado")
            except json.JSONDecodeError:
                return self._error(400, "JSON inválido")
            except Exception as e:
                log.exception("POST %s failed", u.path)
                return self._error(500, str(e))

    return Handler


# =================================================================== window / launching
def find_app_browser() -> str | None:
    """Edge or Chrome, to open the editor as a standalone app window (no address bar)."""
    names = ["msedge", "chrome", "google-chrome", "chromium"]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    if sys.platform == "win32":
        roots = [os.environ.get(k) for k in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")]
        rel = [r"Microsoft\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        for root in filter(None, roots):
            for r in rel:
                if (Path(root) / r).is_file():
                    return str(Path(root) / r)
    return None


def open_window(url: str) -> None:
    exe = find_app_browser()
    if exe:
        try:
            subprocess.Popen([exe, f"--app={url}", "--window-size=1240,800"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            pass
    import webbrowser

    webbrowser.open(url)


def running_instance(port: int) -> dict | None:
    """The ping answer of a Rhino's Buddy Supervisor already listening on ``port`` (None: nothing of ours there)."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ping", timeout=1.5) as r:
            info = json.load(r)
        return info if isinstance(info, dict) and info.get("app") == "rhinos_buddy" else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def already_running(port: int) -> bool:
    return running_instance(port) is not None


def replace_running_instance(port: int, timeout: float = 8.0) -> bool:
    """Ask the copy listening on ``port`` to quit and wait until the port is free again.

    Opening a new version while an old one is still running (it was started with Windows, say) must not just show the
    old window: the old process keeps the old code, so none of the new features would appear."""
    req = urllib.request.Request(f"http://127.0.0.1:{port}/api/quit", data=b"{}", method="POST",
                                 headers={"X-Rhinos-Buddy": "1", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=3).read()
    except (urllib.error.URLError, OSError):
        return False
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if running_instance(port) is None:
            return True
        time.sleep(0.25)
    return False


def setup_logging(home: Path, verbose: bool) -> None:
    handlers: list[logging.Handler] = [
        logging.handlers.RotatingFileHandler(home / "rhinos_buddy.log", maxBytes=500_000, backupCount=2, encoding="utf-8")
    ]
    if sys.stderr is not None and not getattr(sys, "frozen", False):
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="rhinos-buddy-app", description=__doc__)
    ap.add_argument("--background", action="store_true", help="run the screen without opening the editor")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--home", help="folder for layout.json and media (default: %%APPDATA%%\\RhinosBuddySupervisor)")
    ap.add_argument("--no-hardware", action="store_true", help="preview only, never open the serial port")
    ap.add_argument("--no-window", action="store_true", help="do not open the editor window")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args(argv)

    if a.home:
        os.environ["RHINOS_BUDDY_HOME"] = a.home
    home = appdata.app_home()
    setup_logging(home, a.verbose)
    appdata.migrate_legacy_home(home)
    if autostart.supported():
        try:
            autostart.migrate_legacy()
        except Exception:
            log.exception("could not migrate the old start-with-Windows entry")
    url = f"http://127.0.0.1:{a.port}/"

    for attempt in range(2):
        try:
            server = _Server(("127.0.0.1", a.port), BaseHTTPRequestHandler)
            break
        except OSError:
            info = running_instance(a.port)
            if info is None:
                log.error("Port %d is in use by another program", a.port)
                print(f"A porta {a.port} está em uso por outro programa. Use --port.", file=sys.stderr)
                return 1
            if info.get("version") == __version__ or attempt:
                if not a.background and not a.no_window:
                    open_window(url)  # same version: just bring up the editor of the running instance
                return 0
            # another version is running (the old one after an update): replace it with this one
            log.info("Version %s is running; replacing it with %s", info.get("version"), __version__)
            if not replace_running_instance(a.port):
                log.warning("Could not close the running copy; opening its window instead")
                if not a.background and not a.no_window:
                    open_window(url)
                return 0
    server.server_close()

    runner = Runner(home, hardware=not a.no_hardware)
    app = App(home, runner, a.port)
    server = _Server(("127.0.0.1", a.port), make_handler(app))
    app.server = server
    runner.start()
    app.phone.apply()  # only if the user left phone access on
    log.info("Rhino's Buddy Supervisor %s running at %s (home: %s)", __version__, url, home)
    if not a.background and not a.no_window:
        threading.Timer(0.6, open_window, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.phone.stop()
        runner.stop()
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
