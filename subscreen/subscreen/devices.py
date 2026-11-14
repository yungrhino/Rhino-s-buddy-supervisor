"""Display back-ends.  Everything the engine needs is the small ``Display`` API."""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from PIL import Image

from . import protocol as P

log = logging.getLogger("subscreen.device")

# Serial-number string reported by the 3.5" Turing panel's USB CDC interface
# (community-documented; override with `port = "COMx"` if auto-detect misses).
KNOWN_SERIALS = ("USB35INCHIPSV2",)


class Display:
    """Minimal interface the engine talks to."""

    width: int
    height: int

    def open(self) -> None: ...
    def close(self) -> None: ...
    def set_brightness(self, percent: float) -> None: ...
    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None: ...
    def clear(self) -> None: ...

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


def list_ports() -> list[dict]:
    """Serial ports with the identifying info useful for `subscreen ports`."""
    from serial.tools import list_ports as lp

    return [
        {
            "device": p.device,
            "description": p.description,
            "vid": p.vid,
            "pid": p.pid,
            "serial_number": p.serial_number,
            "manufacturer": p.manufacturer,
        }
        for p in lp.comports()
    ]


def find_port() -> str:
    ports = list_ports()
    for p in ports:
        if p["serial_number"] in KNOWN_SERIALS:
            return p["device"]
    seen = ", ".join(f"{p['device']} ({p['description']})" for p in ports) or "none"
    raise RuntimeError(
        "Could not auto-detect the screen. Close the original UsbMonitor.exe, run "
        "`subscreen ports`, and set `port = \"COMx\"` in the config. "
        f"Ports seen: {seen}"
    )


class RevADisplay(Display):
    """Real hardware over USB-CDC serial."""

    def __init__(
        self,
        port: str = "auto",
        orientation: str = "landscape",
        brightness: float | None = None,
        chunk_lines: int = 8,
        baudrate: int = 115200,
        invert_brightness: bool = True,
        rotate: str | None = None,
    ):
        self.port = port
        self.orientation = orientation
        self.brightness = brightness
        self.invert_brightness = invert_brightness
        self.chunk_lines = max(1, chunk_lines)
        self.baudrate = baudrate
        self.rotate = rotate or None
        self.width, self.height = P.screen_size(orientation)
        if self.rotate:
            if P.ORIENTATIONS[orientation] > 1:
                raise ValueError("with `rotate`, orientation must be portrait or reverse_portrait")
            # The panel stays in its native portrait mode; we expose a landscape canvas
            # and turn every picture in software so writes follow the panel's scan order.
            self.width, self.height = P.NATIVE_HEIGHT, P.NATIVE_WIDTH
        self._ser = None
        self.port_name: str | None = None
        self._lock = threading.Lock()

    # -- lifecycle ---------------------------------------------------------
    def open(self) -> None:
        import serial

        port = find_port() if self.port in ("auto", "", None) else self.port
        self.port_name = port
        log.info("Opening %s", port)
        self._ser = serial.Serial(port, self.baudrate, timeout=1, write_timeout=2)
        try:  # Windows only: a big TX buffer lets the OS stream while we compose the next frame
            self._ser.set_buffer_size(rx_size=4096, tx_size=1 << 20)
        except Exception:
            pass
        # The vendor app sends SCREEN_OFF when it exits, so wake the panel first.
        self.screen_on()
        self._write(P.orientation_packet(self.orientation))
        self.set_brightness(60 if self.brightness is None else self.brightness)

    def close(self) -> None:
        if self._ser is not None:
            try:
                self._ser.close()
            finally:
                self._ser = None

    # -- helpers -----------------------------------------------------------
    def _write(self, data: bytes) -> None:
        with self._lock:
            if self._ser is None:
                raise RuntimeError("display not open")
            self._ser.write(data)

    def hello(self) -> bytes:
        """Send the identification probe used by newer panels; may return b''."""
        with self._lock:
            self._ser.reset_input_buffer()
            self._ser.write(bytes([P.CMD_HELLO] * 6))
            return self._ser.read(6)

    # -- Display API -------------------------------------------------------
    def set_brightness(self, percent: float) -> None:
        self._write(P.brightness_packet(percent, self.invert_brightness))

    def screen_on(self) -> None:
        self._write(P.screen_on_packet())

    def screen_off(self) -> None:
        self._write(P.screen_off_packet())

    def clear(self) -> None:
        self.blit(Image.new("RGB", (self.width, self.height), "black"))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        w, h = image.size
        if x < 0 or y < 0 or x + w > self.width or y + h > self.height:
            raise ValueError(f"rect {(x, y, w, h)} outside {self.width}x{self.height}")
        if self.rotate:
            image, x, y = P.rotate_region(image, x, y, self.rotate, self.width, self.height)
            w, h = image.size
        data = P.rgb565_le(image)
        with self._lock:
            if self._ser is None:
                raise RuntimeError("display not open")
            self._ser.write(P.bitmap_header(x, y, w, h))
            step = w * 2 * self.chunk_lines
            for i in range(0, len(data), step):
                self._ser.write(data[i : i + step])


class SimulatorDisplay(Display):
    """No hardware: keeps a frame buffer and writes it to a PNG on every blit.

    Open the PNG (or the optional HTTP preview) to see exactly what the screen shows.
    """

    def __init__(
        self,
        orientation: str = "landscape",
        output: str | Path = "preview.png",
        http_port: int | None = None,
        **_ignored,
    ):
        self.width, self.height = P.screen_size(orientation)
        self.output = Path(output)
        self.http_port = http_port
        self.frame = Image.new("RGB", (self.width, self.height), "black")
        self.blits: list[tuple[int, int, int, int]] = []
        self._server = None

    def open(self) -> None:
        if self.http_port:
            self._start_http()
        self._save()

    def close(self) -> None:
        if self._server:
            self._server.shutdown()

    def set_brightness(self, percent: float) -> None:
        pass

    def screen_on(self) -> None:
        pass

    def screen_off(self) -> None:
        pass

    def hello(self) -> bytes:
        return b""

    def clear(self) -> None:
        self.frame.paste((0, 0, 0), (0, 0, self.width, self.height))
        self._save()

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        self.frame.paste(image.convert("RGB"), (x, y))
        self.blits.append((x, y, image.width, image.height))
        self._save()

    def _save(self) -> None:
        tmp = self.output.with_suffix(".tmp.png")
        self.frame.save(tmp)
        tmp.replace(self.output)

    def _start_http(self) -> None:
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

        sim = self

        class H(BaseHTTPRequestHandler):
            def do_GET(self):  # noqa: N802
                if self.path.startswith("/frame.png"):
                    body = sim.output.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                else:
                    body = (
                        "<!doctype html><title>subscreen preview</title>"
                        "<body style='margin:0;background:#222;display:grid;place-items:center;height:100vh'>"
                        f"<img id=i src='/frame.png' width={sim.width * 2}>"
                        "<script>setInterval(()=>i.src='/frame.png?'+Date.now(),500)</script>"
                    ).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", self.http_port), H)
        threading.Thread(target=self._server.serve_forever, daemon=True).start()
        log.info("Preview at http://127.0.0.1:%d", self.http_port)


class TeeDisplay(Display):
    """Always keeps an in-memory copy of the frame (for the editor preview) and, when a real
    panel is attached, forwards every blit to it.  A hardware error never propagates: the
    panel is dropped and ``hw_error`` is set so the owner can reconnect."""

    def __init__(self, orientation: str = "landscape"):
        self.width, self.height = P.screen_size(orientation)
        self.frame = Image.new("RGB", (self.width, self.height), "black")
        self.hw: Display | None = None
        self.hw_error: Exception | None = None
        self.hw_bytes = 0  # pixel bytes sent to the real panel so far
        self._lock = threading.Lock()

    def open(self) -> None:  # lifecycle is managed by the owner
        pass

    def close(self) -> None:
        pass

    def set_brightness(self, percent: float) -> None:
        if self.hw:
            self.hw.set_brightness(percent)

    def snapshot(self) -> Image.Image:
        with self._lock:
            return self.frame.copy()

    def clear(self) -> None:
        self.blit(Image.new("RGB", (self.width, self.height), "black"))

    def blit(self, image: Image.Image, x: int = 0, y: int = 0) -> None:
        with self._lock:
            self.frame.paste(image.convert("RGB"), (x, y))
        hw = self.hw
        if hw is not None:
            try:
                hw.blit(image, x, y)
                self.hw_bytes += image.width * image.height * 2
            except Exception as e:  # unplugged, port grabbed by another program...
                self.hw_error = e
                self.hw = None
                try:
                    hw.close()
                except Exception:
                    pass


def make_display(cfg: dict) -> Display:
    kind = cfg.get("type", "rev_a")
    opts = {k: v for k, v in cfg.items() if k != "type"}
    if kind == "rev_a":
        allowed = {"port", "orientation", "brightness", "chunk_lines", "baudrate", "invert_brightness", "rotate"}
        return RevADisplay(**{k: v for k, v in opts.items() if k in allowed})
    if kind == "simulator":
        allowed = {"orientation", "output", "http_port"}
        return SimulatorDisplay(**{k: v for k, v in opts.items() if k in allowed})
    raise ValueError(f"unknown device type {kind!r}")
