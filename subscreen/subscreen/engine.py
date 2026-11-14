"""Render loop: pages of widgets -> dirty rectangles -> display."""

from __future__ import annotations

import logging
import threading
import time
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

from . import protocol as P
from .devices import Display, make_display
from .metrics import Metrics
from .widgets import Context, Widget, color, make_widget

log = logging.getLogger("subscreen.engine")


def load_config(path: str | Path) -> dict:
    path = Path(path)
    with path.open("rb") as f:
        cfg = tomllib.load(f)
    cfg["_base_dir"] = path.resolve().parent
    return cfg


def _background_image(path, size, fit: str, dim: float) -> Image.Image:
    """Load a picture as page background: cover (fill+crop) / contain / stretch, optionally darkened."""
    with Image.open(path) as im:
        im = im.convert("RGB")
    W, H = size
    if fit == "stretch":
        out = im.resize(size, Image.LANCZOS)
    else:
        scale = (max if fit != "contain" else min)(W / im.width, H / im.height)
        nw, nh = max(1, round(im.width * scale)), max(1, round(im.height * scale))
        im = im.resize((nw, nh), Image.LANCZOS)
        out = Image.new("RGB", size, (0, 0, 0))
        out.paste(im, ((W - nw) // 2, (H - nh) // 2))
    if dim > 0:
        out = Image.blend(out, Image.new("RGB", size, (0, 0, 0)), min(dim, 100) / 100)
    return out


class Page:
    def __init__(self, cfg: dict, size: tuple[int, int], ctx: Context, default_bg: str):
        self.size = size
        self.duration = float(cfg.get("duration", 10))
        self.widgets: list[Widget] = [make_widget(w, ctx) for w in cfg.get("widget", [])]
        bg = cfg.get("background") or default_bg
        p = ctx.base_dir / str(bg)
        self.bg = None
        if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".gif") and p.is_file():
            try:
                self.bg = _background_image(p, size, cfg.get("background_fit", "cover"), float(cfg.get("background_dim", 0)))
            except Exception as e:  # unreadable image must not stop the screen
                log.warning("background %s failed: %s", p, e)
        if self.bg is None:
            fallback = bg if not p.suffix else cfg.get("background_color", default_bg)
            self.bg = Image.new("RGB", size, color(fallback))

    def compose(self, rect: tuple[int, int, int, int]) -> Image.Image:
        x0, y0, x1, y1 = rect
        out = self.bg.crop(rect).convert("RGBA")
        for w in self.widgets:
            if w.layer is None:
                continue
            ix0, iy0 = max(x0, w.x), max(y0, w.y)
            ix1, iy1 = min(x1, w.x + w.w), min(y1, w.y + w.h)
            if ix0 >= ix1 or iy0 >= iy1:
                continue
            part = w.layer.crop((ix0 - w.x, iy0 - w.y, ix1 - w.x, iy1 - w.y))
            out.alpha_composite(part, (ix0 - x0, iy0 - y0))
        return out.convert("RGB")


class Engine:
    def __init__(self, cfg: dict, display: Display | None = None, metrics: Metrics | None = None):
        self.cfg = cfg
        self.display = display or make_display(cfg.get("device", {}))
        self.size = (self.display.width, self.display.height)
        self.fps = float(cfg.get("device", {}).get("fps", 10))
        self.ctx = Context(
            metrics if metrics is not None else Metrics(cfg.get("sensors")),
            cfg.get("_base_dir", Path.cwd()),
            cfg.get("display", {}).get("decimal", "."),
        )
        default_bg = cfg.get("display", {}).get("background", "#0b0f1a")
        pages = cfg.get("page") or [{"widget": cfg.get("widget", [])}]
        self.pages = [Page(p, self.size, self.ctx, default_bg) for p in pages]
        self.page_index = 0
        self._page_started = 0.0
        self.tile = int(cfg.get("device", {}).get("tile", 32))
        self.rotate = bool(cfg.get("device", {}).get("rotate", True))  # False: never leave the current page
        self.align = int(cfg.get("device", {}).get("align", 8))  # snap partial updates to this grid
        self._sent: np.ndarray | None = None  # RGB565 of what the panel currently shows
        self.stop_event = threading.Event()
        self._owns_metrics = metrics is None
        self.pinned = False  # True: stay on the current page (the editor is showing it)

    def pin_page(self, index: int | None) -> None:
        """Hold the screen on page ``index`` (``None`` resumes the automatic rotation)."""
        if index is None:
            self.pinned = False
            return
        index = max(0, min(index, len(self.pages) - 1))
        self.pinned = True
        if index != self.page_index:
            self.page_index = index
            self._page_started = 0.0  # next step repaints the whole page
            self._sent = None

    def invalidate(self) -> None:
        """Forget what the panel shows (e.g. after a reconnect): next step repaints everything."""
        self._page_started = 0.0
        self._sent = None

    # ------------------------------------------------------------------
    def step(self, now: float | None = None) -> int:
        """Run one tick.  Returns the number of rectangles sent (handy for tests)."""
        now = time.monotonic() if now is None else now
        page = self.pages[self.page_index]
        sent = 0

        if not self.rotate and not self.pinned and self.page_index != 0 and self._page_started:
            self.page_index = 0  # rotation is off: the screen always rests on the first page
            self._enter(self.pages[0], now)
            return 1
        if len(self.pages) > 1 and self.rotate and not self.pinned and now - self._page_started >= page.duration and self._page_started:
            self.page_index = (self.page_index + 1) % len(self.pages)
            page = self.pages[self.page_index]
            self._enter(page, now)
            return 1
        if not self._page_started:
            self._enter(page, now)
            return 1

        dirty = []
        for w in page.widgets:
            if not w.due(now):
                continue
            w.last_run = now
            try:
                if w.update() or w.layer is None:
                    w.layer = w.render()
                    dirty.append(w.rect)
                    w.error = None
            except Exception as e:  # a broken widget must not kill the screen
                if str(e) != w.error:
                    log.warning("widget %s failed: %s", w.type_name, e)
                    w.error = str(e)
        for rect in self._merge(dirty):
            sent += self._send(page, rect)
        return sent

    def _send(self, page: Page, rect) -> int:
        """Compose ``rect`` and transmit only the pixels that differ from what the panel shows."""
        img = page.compose(rect)
        new = P.rgb565_array(img)
        x0, y0, x1, y1 = rect
        diff = new != self._sent[y0:y1, x0:x1]
        n = 0
        W, H = self.size
        for rx0, ry0, rx1, ry1 in P.changed_rects(diff, self.tile):
            box = P.align_rect((x0 + rx0, y0 + ry0, x0 + rx1, y0 + ry1), self.align, W, H)
            out = page.compose(box)
            self.display.blit(out, box[0], box[1])
            self._sent[box[1] : box[3], box[0] : box[2]] = P.rgb565_array(out)
            n += 1
        self._sent[y0:y1, x0:x1] = new
        return n

    def _enter(self, page: Page, now: float) -> None:
        self._page_started = now
        for w in page.widgets:
            w.layer = None
            w.last_run = 0.0
        for w in page.widgets:
            try:
                w.update()
                w.layer = w.render()
                w.last_run = now
            except Exception as e:
                log.warning("widget %s failed: %s", w.type_name, e)
                w.error = str(e)
        full = page.compose((0, 0, *self.size))
        self.display.blit(full)
        self._sent = P.rgb565_array(full)

    def _merge(self, rects):
        """Clip to the screen and merge overlapping rectangles."""
        W, H = self.size
        rs = []
        for x0, y0, x1, y1 in rects:
            r = (max(0, x0), max(0, y0), min(W, x1), min(H, y1))
            if r[0] < r[2] and r[1] < r[3]:
                rs.append(r)
        merged = True
        while merged:
            merged = False
            for i in range(len(rs)):
                for j in range(i + 1, len(rs)):
                    a, b = rs[i], rs[j]
                    if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                        rs[i] = (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))
                        del rs[j]
                        merged = True
                        break
                if merged:
                    break
        return rs

    def run(self) -> None:
        period = 1.0 / max(self.fps, 0.5)
        try:
            with self.display:
                while not self.stop_event.is_set():
                    t0 = time.monotonic()
                    self.step(t0)
                    self.stop_event.wait(max(0.0, period - (time.monotonic() - t0)))
        finally:
            if self._owns_metrics:
                self.ctx.metrics.stop()
