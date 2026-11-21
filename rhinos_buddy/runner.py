"""Runs the screen in the background and lets the editor change the layout live.

* One thread owns the engine and the panel.  Layout changes are handed over (``apply``) and
  taken at the start of the next tick, so the editor never waits for a slow USB transfer.
* The panel is optional: without it (not plugged in, port busy...) the preview keeps working and
  the runner retries every few seconds, so unplugging/replugging the cable just works.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from . import appdata, notifications
from . import layout as L
from .devices import RevADisplay, TeeDisplay
from .engine import Engine
from .metrics import Metrics

log = logging.getLogger("rhinos_buddy.runner")
RETRY_SECONDS = 5.0
FOCUS_SECONDS = 45.0  # how long the editor's page choice holds the screen after its last ping


def friendly_error(e: Exception) -> str:
    text = str(e)
    if isinstance(e, ModuleNotFoundError) and "serial" in text:
        return "Falta o pacote pyserial (pip install pyserial)."
    if "Could not auto-detect" in text:
        return "Tela não encontrada. Conecte o cabo USB ou escolha a porta manualmente na aba Tela."
    if isinstance(e, PermissionError) or "could not open port" in text.lower() or "access is denied" in text.lower():
        return "Não foi possível abrir a porta. Feche o UsbMonitor.exe original (ou outro programa que use a tela)."
    return f"Falha ao conectar: {text[:120]}"


class Runner:
    def __init__(self, home: Path | None = None, layout: dict | None = None, hardware: bool = True):
        self.home = Path(home) if home else appdata.app_home()
        self.hardware = hardware
        self.layout = L.normalize(layout if layout is not None else appdata.load_layout(self.home), self.home)
        self._lock = threading.Lock()
        self._pending: dict | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = {"connected": False, "port": None,
                        "message": "Modo pré-visualização (sem tela)." if not hardware else "Procurando a tela…"}
        self._next_retry = 0.0
        self.metrics: Metrics | None = None
        self.tee: TeeDisplay | None = None
        self.engine: Engine | None = None
        self._build_all()

    # ------------------------------------------------------------------ construction
    def _build_all(self) -> None:
        self.metrics = Metrics(self.layout["sensors"])
        self.metrics.set_stability(self.layout["device"]["stability"])
        self._configure_notifier(self.layout["device"])
        self.tee = TeeDisplay(self.layout["device"]["orientation"])
        self._build_engine()

    @staticmethod
    def _configure_notifier(d: dict) -> None:
        notifications.get_notifier().configure(d["notify"], d["notify_apps"], d["notify_seconds"], d["notify_text"])

    def notify_test(self) -> None:
        """The "Testar" button: shows a sample notification even if the feature is still switched off."""
        notifications.get_notifier().push("Rhino's Buddy Supervisor", "Teste de notificação",
                                          "Se você está vendo este aviso, os cards com notificação funcionam.", force=True)

    def _build_engine(self) -> None:
        cfg = L.to_config(self.layout, self.home)
        self.engine = Engine(cfg, self.tee, metrics=self.metrics)

    # ------------------------------------------------------------------ public API
    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="screen", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=8)
        hw = self.tee.hw if self.tee else None
        if hw is not None:
            try:
                hw.close()
            except Exception:
                pass
        if self.metrics:
            self.metrics.stop()
        notifications.shutdown()

    def apply(self, layout: dict) -> dict:
        """Validate ``layout``, schedule it for the screen thread, return the normalised version."""
        norm = L.normalize(layout, self.home)
        with self._lock:
            self._pending = norm
        return norm

    def focus(self, page: int) -> None:
        """The editor is looking at ``page``: show it on the screen (rotation resumes when it goes quiet)."""
        with self._lock:
            self._focus = (int(page), time.monotonic())

    def reconnect(self) -> None:
        with self._lock:
            self._reconnect_requested = True

    def status(self) -> dict:
        with self._lock:
            st = dict(self._status)
        st["usb_kbs"] = round(self._usb_kbs, 1)
        st["notifications"] = notifications.get_notifier().status()
        return st

    def preview_png(self) -> bytes:
        from io import BytesIO

        buf = BytesIO()
        self.tee.snapshot().save(buf, "PNG")
        return buf.getvalue()

    # ------------------------------------------------------------------ screen thread
    _reconnect_requested = False
    _usb_kbs = 0.0
    _usb_mark: tuple[float, int] | None = None
    _focus: tuple[int, float] | None = None

    def _set_status(self, connected: bool, message: str, port: str | None = None) -> None:
        with self._lock:
            self._status = {"connected": connected, "message": message, "port": port}

    def _take_pending(self) -> dict | None:
        with self._lock:
            p, self._pending = self._pending, None
            return p

    def _apply_now(self, new: dict) -> None:
        old, self.layout = self.layout, new
        od, nd = old["device"], new["device"]
        if old["sensors"] != new["sensors"]:
            self.metrics.stop()
            self.metrics = Metrics(new["sensors"])
        self.metrics.set_stability(nd["stability"])
        self._configure_notifier(nd)
        if od["orientation"] != nd["orientation"]:
            hw = self.tee.hw
            hw_bytes = self.tee.hw_bytes
            self.tee = TeeDisplay(nd["orientation"])
            self.tee.hw_bytes = hw_bytes
            self.tee.hw = None
            if hw is not None:
                try:
                    hw.close()
                except Exception:
                    pass
            self._set_status(False, "Reconectando…")
            self._next_retry = 0.0
        elif (od["port"], od["invert_brightness"]) != (nd["port"], nd["invert_brightness"]):
            self._drop_hardware("Reconectando…")
        elif od["brightness"] != nd["brightness"] and self.tee.hw is not None:
            try:
                self.tee.hw.set_brightness(nd["brightness"])
            except Exception as e:
                self.tee.hw_error = e
        self._build_engine()

    def _drop_hardware(self, message: str) -> None:
        hw, self.tee.hw = self.tee.hw, None
        if hw is not None:
            try:
                hw.close()
            except Exception:
                pass
        self._set_status(False, message)
        self._next_retry = 0.0

    def _service_hardware(self, now: float) -> None:
        if not self.hardware:
            return
        if self._reconnect_requested:
            self._reconnect_requested = False
            self._drop_hardware("Reconectando…")
        if self.tee.hw_error is not None:
            log.warning("panel lost: %s", self.tee.hw_error)
            self.tee.hw_error = None
            self._set_status(False, "Tela desconectada. Tentando reconectar…")
            self._next_retry = now + RETRY_SECONDS
        if self.tee.hw is None and now >= self._next_retry:
            self._connect(now)

    def _connect(self, now: float) -> None:
        d = self.layout["device"]
        try:
            hw = RevADisplay(port=d["port"], orientation=d["orientation"], brightness=d["brightness"],
                             invert_brightness=d["invert_brightness"])
            hw.open()
        except Exception as e:
            self._set_status(False, friendly_error(e))
            self._next_retry = now + RETRY_SECONDS
            return
        self.tee.hw = hw
        self.engine.invalidate()  # repaint everything on the freshly connected panel
        self._set_status(True, "Tela conectada.", getattr(hw, "port_name", None))
        log.info("panel connected")

    def _track_usb(self, now: float) -> None:
        """Average pixel bytes/s sent to the panel over the last ~10 s (shown in the Tela tab)."""
        b = self.tee.hw_bytes
        if self._usb_mark is None or b < self._usb_mark[1]:
            self._usb_mark = (now, b)
            return
        t0, b0 = self._usb_mark
        if now - t0 >= 10.0:
            self._usb_kbs = (b - b0) / (now - t0) / 1024
            self._usb_mark = (now, b)

    def _loop(self) -> None:
        while not self._stop.is_set():
            t0 = time.monotonic()
            try:
                pending = self._take_pending()
                if pending is not None:
                    self._apply_now(pending)
                self._service_hardware(t0)
                with self._lock:
                    f = self._focus
                self.engine.pin_page(f[0] if f and t0 - f[1] < FOCUS_SECONDS else None)
                self.engine.step(t0)
                self._track_usb(t0)
            except Exception:
                log.exception("screen loop error")
                self._stop.wait(1.0)
            period = 1.0 / max(2, self.layout["device"]["fps"])
            self._stop.wait(max(0.01, period - (time.monotonic() - t0)))
