"""Widgets: small objects that own a rectangle of the screen.

Contract
--------
``update()``  -> bool   refresh data; return True when the picture must be redrawn
``render()``  -> RGBA   draw the widget at its own size (w x h)

The engine calls ``update`` every ``interval`` seconds, so a widget only pays for
what it shows.  Anything not covered by the built-ins can be added with the
``plugin`` widget (see README) - that is the "put whatever I want on the screen" path.
"""

from __future__ import annotations

import importlib.util
import io
import json
import math
import re
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont, ImageSequence

from .metrics import Metrics

_FONT_CANDIDATES = (
    "DejaVuSans.ttf",
    "segoeui.ttf",
    "arial.ttf",
    "Arial.ttf",
    "Helvetica.ttc",
    "LiberationSans-Regular.ttf",
)


@dataclass
class Context:
    metrics: Metrics
    base_dir: Path
    decimal: str = "."  # "," for Brazilian-style numbers (11,4 GB)
    audio: object = None       # audio.Analyzer (tests inject a fake; default is the shared one)
    nowplaying: object = None  # nowplaying.NowPlaying (same idea)
    notifier: object = None    # notifications.Notifier (same idea)


_font_cache: dict = {}


def load_font(name: str | None, size: int, base_dir: Path | None = None):
    key = (name, size, str(base_dir))
    if key in _font_cache:
        return _font_cache[key]
    names = [name] if name else []
    names += list(_FONT_CANDIDATES)
    font = None
    for n in names:
        for cand in ([base_dir / n] if base_dir else []) + [Path(n)]:
            try:
                font = ImageFont.truetype(str(cand), size)
                break
            except OSError:
                continue
        if font:
            break
    if font is None:
        font = ImageFont.load_default(size)
    _font_cache[key] = font
    return font


def color(value, default="white"):
    return ImageColor.getrgb(value or default)


class Widget:
    type_name = "widget"

    def __init__(self, cfg: dict, ctx: Context):
        self.cfg = cfg
        self.ctx = ctx
        self.x = int(cfg.get("x", 0))
        self.y = int(cfg.get("y", 0))
        self.w = int(cfg.get("w", 100))
        self.h = int(cfg.get("h", 30))
        self.interval = float(cfg.get("interval", 1.0))
        self.layer: Image.Image | None = None
        self.last_run = 0.0
        self.error: str | None = None

    @property
    def rect(self):
        return (self.x, self.y, self.x + self.w, self.y + self.h)

    def due(self, now: float) -> bool:
        return self.layer is None or now - self.last_run >= self.interval

    def update(self) -> bool:
        return True

    def render(self) -> Image.Image:
        return Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))

    def new_layer(self) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        return img, ImageDraw.Draw(img)

    def font(self, size_key="size", default=20):
        return load_font(self.cfg.get("font"), int(self.cfg.get(size_key, default)), self.ctx.base_dir)


class _Template(dict):
    def __missing__(self, key):
        return 0


WEEKDAYS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
WEEKDAYS_SHORT = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
MONTHS = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto",
          "setembro", "outubro", "novembro", "dezembro"]
MONTHS_SHORT = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]

_NAN_RE = re.compile(r"(?<![A-Za-z])-?(?:nan|inf)(?![A-Za-z])")
_DEC_RE = re.compile(r"(?<=\d)\.(?=\d)")


def pt_date_fields(now) -> dict:
    """Locale-independent Portuguese date names (Windows strftime would give English)."""
    return {
        "dia_semana": WEEKDAYS[now.weekday()],
        "dia_semana_cap": WEEKDAYS[now.weekday()].capitalize(),
        "dia_semana_curto": WEEKDAYS_SHORT[now.weekday()],
        "mes": MONTHS[now.month - 1],
        "mes_curto": MONTHS_SHORT[now.month - 1],
        "dia": now.day,
        "ano": now.year,
    }


# --------------------------------------------------------------------------- text
class TextWidget(Widget):
    """Static or live text.  ``text`` is a Python format string over the metrics:

        "CPU {cpu:.0f}%   RAM {ram_used_gb:.1f} GB"

    plus strftime tokens via ``{now:%H:%M}`` (``now`` is a datetime).
    """

    type_name = "text"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.template = str(cfg.get("text", ""))
        self._shown = None

    def current_text(self) -> str:
        import datetime

        data = _Template(self.ctx.metrics.get())
        now = datetime.datetime.now()
        data["now"] = now
        data.update(pt_date_fields(now))
        try:
            text = self.template.format_map(data)
        except (ValueError, KeyError, IndexError) as e:
            return f"<{e}>"
        text = _NAN_RE.sub("--", text)  # sensor not available
        if self.ctx.decimal != ".":
            text = _DEC_RE.sub(self.ctx.decimal, text)
        return text

    def update(self) -> bool:
        t = self.current_text()
        changed = t != self._shown
        self._shown = t
        return changed

    def render(self):
        img, d = self.new_layer()
        font = self.font()
        text = self._shown if self._shown is not None else self.current_text()
        if self.cfg.get("fit") and not self.cfg.get("wrap"):
            font = self._shrink_to_fit(font, text, d)
        if self.cfg.get("wrap"):
            text = self._wrap(text, font, d)
        fill = color(self.cfg.get("color", "white"))
        align = self.cfg.get("align", "left")
        valign = self.cfg.get("valign", "top")
        left, top, right, bottom = d.multiline_textbbox((0, 0), text, font=font)
        tw, th = right - left, bottom - top
        x = {"left": 0, "center": (self.w - tw) // 2, "right": self.w - tw}[align] - left
        y = {"top": 0, "middle": (self.h - th) // 2, "bottom": self.h - th}[valign] - top
        d.multiline_text((x, y), text, font=font, fill=fill, align=align)
        return img

    def _shrink_to_fit(self, font, text, d):
        """Never cut a single-line text at the edge: if today's text is wider than the box, use a smaller size."""
        size = int(self.cfg.get("size", 20))
        while size > 8 and d.textlength(text, font=font) > self.w:
            size -= 1
            font = load_font(self.cfg.get("font"), size, self.ctx.base_dir)
        return font

    def _wrap(self, text, font, d):
        out = []
        for para in text.split("\n"):
            line = ""
            for word in para.split(" "):
                trial = f"{line} {word}".strip()
                if d.textlength(trial, font=font) <= self.w or not line:
                    line = trial
                else:
                    out.append(line)
                    line = word
            out.append(line)
        return "\n".join(out)


class ClockWidget(TextWidget):
    type_name = "clock"

    def __init__(self, cfg, ctx):
        cfg = dict(cfg)
        cfg["text"] = "{now:" + cfg.get("format", "%H:%M:%S") + "}"
        super().__init__(cfg, ctx)


# ---------------------------------------------------------------------- bar/gauge
class BarWidget(Widget):
    """Horizontal progress bar for any numeric metric (or a fixed ``value``)."""

    type_name = "bar"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.metric = cfg.get("metric", "cpu")
        self.lo = float(cfg.get("min", 0))
        self.hi = float(cfg.get("max", 100))
        self._v = None

    def value(self) -> float:
        raw = self.cfg.get("value")
        if raw is None:
            raw = self.ctx.metrics.get().get(self.metric, 0)
        v = float(raw)
        return 0.0 if v != v else v  # nan (sensor missing) draws as empty

    def update(self) -> bool:
        v = round(self.value(), 1)
        changed = v != self._v
        self._v = v
        return changed

    def render(self):
        img, d = self.new_layer()
        frac = max(0.0, min(1.0, ((self._v or 0) - self.lo) / ((self.hi - self.lo) or 1)))
        r = int(self.cfg.get("radius", self.h // 2))
        d.rounded_rectangle((0, 0, self.w - 1, self.h - 1), r, fill=color(self.cfg.get("track", "#2a2f3a")))
        fw = int((self.w - 1) * frac)
        if fw > 0:
            fill = color(self.cfg.get("color", "#35c46d"))
            warn = self.cfg.get("warn_at")
            if warn is not None and (self._v or 0) >= float(warn):
                fill = color(self.cfg.get("warn_color", "#e5484d"))
            d.rounded_rectangle((0, 0, max(fw, 2 * r if r else 1), self.h - 1), r, fill=fill)
        return img


class GraphWidget(Widget):
    """Scrolling line graph of a metric's recent history."""

    type_name = "graph"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.metric = cfg.get("metric", "cpu")
        self.lo = float(cfg.get("min", 0))
        self.hi = cfg.get("max")

    def render(self):
        img, d = self.new_layer()
        d.rectangle((0, 0, self.w - 1, self.h - 1), fill=color(self.cfg.get("background", "#12161f")))
        hist = self.ctx.metrics.history.get(self.metric, [])[-self.w :]
        if len(hist) >= 2:
            hi = float(self.hi) if self.hi is not None else max(max(hist), 1.0)
            pts = [
                (i * (self.w - 1) / max(len(hist) - 1, 1),
                 self.h - 1 - (max(self.lo, min(hi, v)) - self.lo) / ((hi - self.lo) or 1) * (self.h - 1))
                for i, v in enumerate(hist)
            ]
            c = color(self.cfg.get("color", "#4dabf7"))
            d.polygon(pts + [(pts[-1][0], self.h - 1), (pts[0][0], self.h - 1)], fill=c + (60,))
            d.line(pts, fill=c, width=int(self.cfg.get("line_width", 2)))
        return img


# ----------------------------------------------------------------------- images
def _fit(img: Image.Image, w: int, h: int, mode: str) -> Image.Image:
    img = img.convert("RGBA")
    if mode == "stretch":
        return img.resize((w, h), Image.LANCZOS)
    scale = (max if mode == "cover" else min)(w / img.width, h / img.height)
    nw, nh = max(1, round(img.width * scale)), max(1, round(img.height * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(img, ((w - nw) // 2, (h - nh) // 2))
    return out


class ImageWidget(Widget):
    """PNG/JPG/GIF/WebP file.  Animated files play; the file is re-read if it changes,
    so another program can simply overwrite the image to update the screen."""

    type_name = "image"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.path = ctx.base_dir / cfg["path"]
        self.fit = cfg.get("fit", "contain")
        self.frames: list[tuple[Image.Image, float]] = []
        self._mtime = None
        self._i = 0
        self.interval = 0.04  # animated GIFs: the frame delay below is the real limit

    def _load(self):
        self._mtime = self.path.stat().st_mtime
        self.frames = []
        with Image.open(self.path) as im:
            for f in ImageSequence.Iterator(im):
                dur = max(f.info.get("duration", 100), 20) / 1000
                self.frames.append((_fit(f, self.w, self.h, self.fit), dur))
        self._i = 0
        self._t0 = time.monotonic()
        self._total = sum(d for _, d in self.frames)

    def _index_at(self, now: float) -> int:
        """Frame that should be on screen *now*, by wall-clock time.

        On a slow link frames are dropped instead of the animation playing in slow motion.
        """
        t = (now - self._t0) % self._total
        for i, (_, d) in enumerate(self.frames):
            if t < d:
                return i
            t -= d
        return len(self.frames) - 1

    def update(self) -> bool:
        if self.path.stat().st_mtime != self._mtime:
            self._load()
            return True
        if len(self.frames) > 1:
            i = self._index_at(time.monotonic())
            if i != self._i:
                self._i = i
                return True
        return False

    def render(self):
        return self.frames[self._i][0].copy() if self.frames else super().render()


class WebImageWidget(Widget):
    """Image fetched from a URL every ``interval`` s (camera snapshot, Grafana render, radar map...)."""

    type_name = "web_image"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.url = cfg["url"]
        self.fit = cfg.get("fit", "contain")
        self.interval = float(cfg.get("interval", 30))
        self._img = None

    def update(self) -> bool:
        req = urllib.request.Request(self.url, headers={"User-Agent": "rhinos_buddy/0.1"})
        with urllib.request.urlopen(req, timeout=10) as r:
            self._img = _fit(Image.open(io.BytesIO(r.read())), self.w, self.h, self.fit)
        return True

    def render(self):
        return self._img.copy() if self._img else super().render()


# ------------------------------------------------------------------ data sources
class CommandWidget(TextWidget):
    """Run any command; show its stdout as text, or as an image (``mode = "image"``,
    command must print PNG/JPG bytes).  Turns any script into a screen widget."""

    type_name = "command"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.command = cfg["command"]
        self.mode = cfg.get("mode", "text")
        self.interval = float(cfg.get("interval", 5))
        self.timeout = float(cfg.get("timeout", 10))
        self._out = ""
        self._img = None

    def update(self) -> bool:
        r = subprocess.run(
            self.command, shell=True, capture_output=True, timeout=self.timeout, cwd=self.ctx.base_dir
        )
        if self.mode == "image":
            self._img = _fit(Image.open(io.BytesIO(r.stdout)), self.w, self.h, self.cfg.get("fit", "contain"))
            return True
        out = r.stdout.decode("utf-8", "replace").strip()
        if r.returncode != 0 and not out:
            out = r.stderr.decode("utf-8", "replace").strip()[:200]
        changed = out != self._out
        self._out = out
        self._shown = out
        return changed

    def render(self):
        if self.mode == "image":
            return self._img.copy() if self._img else super(TextWidget, self).render()
        return super().render()


class FileTextWidget(TextWidget):
    """Show the (tail of a) text file, re-read when it changes."""

    type_name = "file"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.path = ctx.base_dir / cfg["path"]
        self.lines = int(cfg.get("lines", 5))
        self.interval = float(cfg.get("interval", 1))

    def update(self) -> bool:
        txt = "\n".join(self.path.read_text("utf-8", "replace").splitlines()[-self.lines :])
        changed = txt != self._shown
        self._shown = txt
        return changed


def _dig(obj, path: str):
    for part in path.split("."):
        obj = obj[int(part)] if isinstance(obj, list) else obj[part]
    return obj


class HttpJsonWidget(TextWidget):
    """GET a JSON URL and format fields into text.

        url = "https://api.example.com/price"
        text = "BTC {price}"
        fields = { price = "data.0.last" }
    """

    type_name = "http_json"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.url = cfg["url"]
        self.fields = cfg.get("fields", {})
        self.interval = float(cfg.get("interval", 60))
        self.headers = cfg.get("headers", {})

    def update(self) -> bool:
        req = urllib.request.Request(self.url, headers={"User-Agent": "rhinos_buddy/0.1", **self.headers})
        with urllib.request.urlopen(req, timeout=10) as r:
            doc = json.load(r)
        vals = {k: _dig(doc, p) for k, p in self.fields.items()}
        try:
            txt = self.template.format_map(_Template(vals))
        except (ValueError, KeyError, IndexError) as e:
            txt = f"<{e}>"
        changed = txt != self._shown
        self._shown = txt
        return changed


class PluginWidget(Widget):
    """Your own Python.  ``module = "my_widget.py"`` must define ``class Plugin`` with

        def __init__(self, cfg, ctx): ...
        def update(self) -> bool: ...                    # optional, default True
        def render(self, w, h) -> PIL.Image.Image: ...   # draw anything with Pillow
    """

    type_name = "plugin"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        path = ctx.base_dir / cfg["module"]
        spec = importlib.util.spec_from_file_location(f"rhinos_buddy_plugin_{path.stem}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.impl = mod.Plugin(cfg, ctx)

    def update(self) -> bool:
        return self.impl.update() if hasattr(self.impl, "update") else True

    def render(self):
        return self.impl.render(self.w, self.h).convert("RGBA")


class RadialWidget(BarWidget):
    """Circular gauge: a 270 degree arc (gap at the bottom) filled with a colour gradient.

    Same data contract as ``bar`` (``metric``/``min``/``max``/``warn_at``).  Drawn 3x larger and
    scaled down for smooth edges.  The value is rounded to whole units so the ring (and the
    USB traffic it causes) only changes when the number next to it changes."""

    type_name = "radial"
    SS = 3
    _grad_cache: dict = {}

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.start = float(cfg.get("start", 135))
        self.sweep = float(cfg.get("sweep", 270))

    def update(self) -> bool:
        v = round(self.value())
        changed = v != self._v
        self._v = v
        return changed

    @classmethod
    def _gradient(cls, w, h, c1, c2, start, sweep) -> Image.Image:
        key = (w, h, c1, c2, start, sweep)
        g = cls._grad_cache.get(key)
        if g is None:
            ys, xs = np.mgrid[0:h, 0:w]
            ang = (np.degrees(np.arctan2(ys - (h - 1) / 2, xs - (w - 1) / 2)) - start) % 360
            ang = np.where(ang > sweep + (360 - sweep) / 2, 0, ang)  # start cap sits just before 0
            t = np.clip(ang / sweep, 0, 1)[..., None]
            a, b = np.array(c1, float), np.array(c2, float)
            g = Image.fromarray((a + (b - a) * t).astype("uint8"), "RGB")
            if len(cls._grad_cache) > 32:
                cls._grad_cache.clear()
            cls._grad_cache[key] = g
        return g

    def _arc_mask(self, frac: float, thick: float) -> Image.Image:
        ss, w, h = self.SS, self.w, self.h
        m = Image.new("L", (w * ss, h * ss), 0)
        d = ImageDraw.Draw(m)
        D = min(w, h)
        x0, y0 = (w - D) / 2 * ss, (h - D) / 2 * ss
        box = (x0, y0, x0 + D * ss - 1, y0 + D * ss - 1)
        tw = thick * ss
        end = self.start + self.sweep * frac
        if frac > 0:
            d.arc(box, self.start, end, fill=255, width=int(tw))
            rm = (D * ss) / 2 - tw / 2  # radius of the ring's centre line; round caps on both ends
            cx, cy = w * ss / 2, h * ss / 2
            for a in (self.start, end):
                px, py = cx + rm * math.cos(math.radians(a)), cy + rm * math.sin(math.radians(a))
                d.ellipse((px - tw / 2, py - tw / 2, px + tw / 2, py + tw / 2), fill=255)
        return m.resize((w, h), Image.LANCZOS)

    def render(self):
        frac = max(0.0, min(1.0, ((self._v or 0) - self.lo) / ((self.hi - self.lo) or 1)))
        D = min(self.w, self.h)
        thick = float(self.cfg.get("thickness", max(4, round(D * 0.12))))
        c1 = color(self.cfg.get("color", "#35c46d"))
        c2 = color(self.cfg.get("color2") or self.cfg.get("color", "#35c46d"))
        warn = self.cfg.get("warn_at")
        if warn is not None and (self._v or 0) >= float(warn):
            c1 = c2 = color(self.cfg.get("warn_color", "#e5484d"))
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        track = Image.new("RGBA", (self.w, self.h), color(self.cfg.get("track", "#ffffff"))[:3] + (255,))
        ta = int(self.cfg.get("track_alpha", 38))
        track.putalpha(self._arc_mask(1.0, thick).point(lambda a: a * ta // 255))
        img.alpha_composite(track)
        if frac > 0:
            fg = self._gradient(self.w, self.h, c1, c2, self.start, self.sweep).convert("RGBA")
            fg.putalpha(self._arc_mask(frac, thick))
            img.alpha_composite(fg)
        return img


# --------------------------------------------------------------------------- music
def _ellipsize(d: ImageDraw.ImageDraw, text: str, font, width: int) -> str:
    if d.textlength(text, font=font) <= width:
        return text
    while text and d.textlength(text + "…", font=font) > width:
        text = text[:-1]
    return text.rstrip() + "…"


class VisualizerWidget(Widget):
    """Audio spectrum of whatever the computer is playing.

    ``style``: ``barras`` | ``espelho`` (bars grow both ways from the middle) | ``circular`` (bars
    around a ring) | ``pulso`` (one disc that swells with the beat).

    Bar heights are quantised to 1/16 so a flat or steady signal causes no USB traffic at all, and
    ``interval`` (set by the layout from the slot's area) caps the redraw rate."""

    type_name = "visualizer"
    STEPS = 16

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.style = cfg.get("style", "barras")
        self.n = max(3, min(48, int(cfg.get("bars", 12))))
        self.sens = int(cfg.get("sensitivity", 50))
        self.decay = float(cfg.get("decay", 0.72))
        self._lv = np.zeros(self.n)
        self._beat = 0.0
        self._shown: tuple | None = None

    def _source(self):
        if self.ctx.audio is not None:
            return self.ctx.audio
        from . import audio

        return audio.get_analyzer()

    def update(self) -> bool:
        src = self._source()
        new = np.asarray(src.levels(self.n, self.sens), dtype=float)
        self._lv = np.maximum(new, self._lv * self.decay)  # instant attack, smooth fall
        beat = float(src.beat_strength())
        self._beat = max(beat, self._beat * 0.6)
        q = np.round(self._lv * self.STEPS).astype(int)
        shown = (tuple(q.tolist()), round(self._beat * 8) if self.style == "pulso" else 0)
        if shown == self._shown:
            return False
        self._shown = shown
        return True

    def _levels(self) -> np.ndarray:
        q = self._shown[0] if self._shown else (0,) * self.n
        return np.array(q, dtype=float) / self.STEPS

    def render(self):
        img = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        c1 = color(self.cfg.get("color", "#35c46d"))
        c2 = color(self.cfg.get("color2") or self.cfg.get("color", "#35c46d"))
        lv = self._levels()
        if self.style == "pulso":
            return self._pulse(img, lv, c1, c2)
        if self.style == "circular":
            return self._circular(img, lv, c1, c2)
        d = ImageDraw.Draw(img)
        n, W, H = self.n, self.w, self.h
        gap = max(1, round(W / n * 0.22))
        bw = max(1, (W - gap * (n - 1)) / n)
        mirror = self.style == "espelho"
        for i in range(n):
            t = i / max(1, n - 1)
            col = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
            x0 = i * (bw + gap)
            half = H / 2
            bh = max(2.0, lv[i] * (half if mirror else H))
            y0, y1 = (half - bh, half + bh) if mirror else (H - bh, H)
            r = min(bw / 2, 4)
            d.rounded_rectangle((x0, y0, x0 + bw - 1, y1 - 1), r, fill=col + (255,))
        return img

    def _circular(self, img, lv, c1, c2):
        ss = 2
        big = Image.new("RGBA", (self.w * ss, self.h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        cx, cy = self.w * ss / 2, self.h * ss / 2
        R = min(self.w, self.h) * ss / 2 - 1
        r0 = R * 0.42
        n = self.n * 2  # mirrored left/right, so the ring is symmetric
        width = max(2, int(2 * math.pi * r0 / n * 0.55))
        for i in range(n):
            k = i if i < self.n else n - 1 - i
            t = k / max(1, self.n - 1)
            col = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
            ang = -math.pi / 2 + 2 * math.pi * (i + 0.5) / n
            r1 = r0 + max(width * 0.6, lv[k] * (R - r0))
            d.line((cx + r0 * math.cos(ang), cy + r0 * math.sin(ang), cx + r1 * math.cos(ang), cy + r1 * math.sin(ang)),
                   fill=col + (255,), width=width)
        return big.resize((self.w, self.h), Image.LANCZOS)

    def _pulse(self, img, lv, c1, c2):
        ss = 2
        big = Image.new("RGBA", (self.w * ss, self.h * ss), (0, 0, 0, 0))
        d = ImageDraw.Draw(big)
        cx, cy = self.w * ss / 2, self.h * ss / 2
        R = min(self.w, self.h) * ss / 2 - 1
        energy = float(lv.mean()) if lv.size else 0.0
        k = min(1.0, 0.25 + 0.55 * energy + 0.45 * (self._shown[1] / 8 if self._shown else 0))
        for step, a in ((1.0, 70), (0.78, 130), (0.56, 255)):
            r = R * (0.3 + 0.7 * k) * step
            t = 1 - step
            col = tuple(int(x + (y - x) * t) for x, y in zip(c1, c2))
            d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col + (a,))
        return big.resize((self.w, self.h), Image.LANCZOS)


def _wrap_lines(d, text: str, font, width: int, max_lines: int) -> list[str]:
    """Word wrap into at most ``max_lines`` lines; the last one ends with an ellipsis when text is left over."""
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if d.textlength(trial, font=font) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _ellipsize(d, lines[-1] + "…", font, width) if not lines[-1].endswith("…") else lines[-1]
    return [_ellipsize(d, ln, font, width) for ln in lines]


def _mmss(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}"


class NowPlayingWidget(Widget):
    """The current track.

    ``mode`` = ``texto``: title (bold) and artist, nothing else.
    ``mode`` = ``capa``: expanded card - album cover, title, artist and a progress bar with times,
    like a player.  Cover and progress need a player that reports them (the Windows media session
    does; the Spotify window-title fallback only knows the text, so the card shows a placeholder)."""

    type_name = "nowplaying"
    _cover_cache: dict = {}

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self._shown = None
        self._info: dict = {}
        self.clock = time.monotonic

    def _source(self):
        if self.ctx.nowplaying is not None:
            return self.ctx.nowplaying
        from . import nowplaying

        return nowplaying.get_nowplaying()

    # ---- data
    def _position(self, info: dict) -> float | None:
        if "position" not in info or not info.get("duration"):
            return None
        pos = float(info["position"]) + max(0.0, self.clock() - float(info.get("fetched_at", self.clock())))
        return min(pos, float(info["duration"]))

    def update(self) -> bool:
        info = self._source().get() or {}
        if not info.get("playing"):
            key, self._info = None, {}
        else:
            self._info = dict(info)
            pos = self._position(info) if self.cfg.get("show_progress", True) else None
            key = (info.get("title", ""), info.get("artist", ""), len(info.get("art") or b""),
                   None if pos is None else int(pos), info.get("duration"))
        changed = key != self._shown
        self._shown = key
        return changed

    # ---- drawing
    def _fonts(self, size: int):
        bold = load_font(self.cfg.get("font_bold") or self.cfg.get("font"), size, self.ctx.base_dir)
        reg = load_font(self.cfg.get("font"), max(9, round(size * 0.8)), self.ctx.base_dir)
        return bold, reg

    def render(self):
        if self.cfg.get("mode") == "capa":
            return self._render_card()
        img, d = self.new_layer()
        size = int(self.cfg.get("size", 18))
        bold, reg = self._fonts(size)
        fg, muted = color(self.cfg.get("color", "white")), color(self.cfg.get("muted", "#8b95a7"))
        align = self.cfg.get("align", "left")
        if self._shown is None:
            lines = [(self.cfg.get("idle_text", "Nada tocando"), reg, muted)]
        else:
            title, artist = self._shown[0], self._shown[1]
            lines = [(title, bold, fg)]
            if artist and self.cfg.get("show_artist", True):
                lines.append((artist, reg, muted))
        self._draw_lines(d, lines, 0, self.w, (self.h - sum(round(f.size * 1.3) for _, f, _ in lines)) // 2, align)
        return img

    def _draw_lines(self, d, lines, x0, width, y, align):
        for text, f, col in lines:
            text = _ellipsize(d, text, f, width)
            tw = d.textlength(text, font=f)
            x = x0 + {"left": 0, "center": (width - tw) / 2, "right": width - tw}[align]
            d.text((x, y), text, font=f, fill=col)
            y += round(f.size * 1.3)
        return y

    def _cover(self, art: bytes, size: int):
        key = (hash(art), size)
        img = self._cover_cache.get(key)
        if img is None:
            try:
                src = Image.open(io.BytesIO(art)).convert("RGB")
            except Exception:
                return None
            sq = min(src.size)  # centre-crop to a square
            src = src.crop(((src.width - sq) // 2, (src.height - sq) // 2, (src.width + sq) // 2, (src.height + sq) // 2))
            ss = 3
            img = src.resize((size, size), Image.LANCZOS).convert("RGBA")
            mask = Image.new("L", (size * ss, size * ss), 0)
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, size * ss - 1, size * ss - 1), size * ss * 0.07, fill=255)
            img.putalpha(mask.resize((size, size), Image.LANCZOS))
            if len(self._cover_cache) > 8:
                self._cover_cache.clear()
            self._cover_cache[key] = img
        return img

    def _render_card(self):
        img, d = self.new_layer()
        W, H = self.w, self.h
        fg, muted = color(self.cfg.get("color", "white")), color(self.cfg.get("muted", "#8b95a7"))
        accent = color(self.cfg.get("accent", "#b197fc"))
        align = self.cfg.get("align", "left")
        info = self._info if self._shown is not None else {}
        horizontal = W >= 1.5 * H
        show_cover = self.cfg.get("show_cover", True)
        gap = 14
        if show_cover:
            s = int(min(H if horizontal else W, W * 0.5 if horizontal else H * 0.62))
            cx, cy = (0, (H - s) // 2) if horizontal else ((W - s) // 2, 0)
            cover = self._cover(info["art"], s) if info.get("art") else None
            if cover is not None:
                img.alpha_composite(cover, (cx, cy))
            else:  # nothing to show: a quiet placeholder with a note
                ph = Image.new("RGBA", (s, s), (0, 0, 0, 0))
                pd = ImageDraw.Draw(ph)
                pd.rounded_rectangle((0, 0, s - 1, s - 1), s * 0.07, fill=color("#ffffff") + (28,))
                f = load_font(self.cfg.get("font"), max(12, s // 3), self.ctx.base_dir)
                pd.text((s / 2, s / 2), "♪", font=f, fill=muted + (255,), anchor="mm")
                img.alpha_composite(ph, (cx, cy))
            tx, tw = (s + gap, W - s - gap) if horizontal else (0, W)
            top, area_h = (0, H) if horizontal else (s + 8, H - s - 8)
        else:
            tx, tw, top, area_h = 0, W, 0, H
        size = max(12, min(30, int(area_h * (0.17 if horizontal or not show_cover else 0.2))))
        bold, reg = self._fonts(size)
        if self._shown is None:
            lines = [(self.cfg.get("idle_text", "Nada tocando"), reg, muted)]
        else:
            lines = [(info.get("title", ""), bold, fg)]
            if info.get("artist") and self.cfg.get("show_artist", True):
                lines.append((info["artist"], reg, muted))
        pos = self._position(info) if info and self.cfg.get("show_progress", True) else None
        bar_block = 0 if pos is None else 8 + max(14, round(reg.size * 1.3))
        text_h = sum(round(f.size * 1.3) for _, f, _ in lines)
        y = top + max(0, (area_h - text_h - bar_block) // 2)
        y = self._draw_lines(d, lines, tx, tw, y, align)
        if pos is not None:
            y += 8
            dur = float(info["duration"])
            tt_w = max(d.textlength(_mmss(dur), font=reg), d.textlength("0:00", font=reg)) + 8
            frac = 0.0 if dur <= 0 else max(0.0, min(1.0, pos / dur))
            row_h = max(14, round(reg.size * 1.3))
            d.text((tx, y + row_h / 2), _mmss(pos), font=reg, fill=muted, anchor="lm")
            d.text((tx + tw, y + row_h / 2), _mmss(dur), font=reg, fill=muted, anchor="rm")
            bx0, bx1, by = tx + tt_w, tx + tw - tt_w, y + row_h / 2
            if bx1 - bx0 > 20:
                d.rounded_rectangle((bx0, by - 3, bx1, by + 3), 3, fill=color("#ffffff") + (60,))
                fx = bx0 + (bx1 - bx0) * frac
                if fx > bx0 + 1:
                    d.rounded_rectangle((bx0, by - 3, fx, by + 3), 3, fill=accent + (255,))
        return img


class NoticeWidget(Widget):
    """Notifications.

    ``mode`` = ``alert``: an opaque card drawn **over** another card while a notification is fresh
    (``Notifier.seconds``), completely transparent otherwise - so the card underneath comes back by itself.
    ``mode`` = ``list``: the last few notifications, always visible."""

    type_name = "notice"

    def __init__(self, cfg, ctx):
        super().__init__(cfg, ctx)
        self.mode = cfg.get("mode", "alert")
        self._shown = None

    def _source(self):
        if self.ctx.notifier is not None:
            return self.ctx.notifier
        from . import notifications

        return notifications.get_notifier()

    def update(self) -> bool:
        n = self._source()
        if self.mode == "alert":
            ev = n.active()
            key = ev["id"] if ev else None
        else:
            key = tuple((e["app"], e["title"], e["body"]) for e in n.listing(int(self.cfg.get("rows", 3))))
        changed = key != self._shown
        self._shown = key
        return changed

    @staticmethod
    def _dot(d, x, y, r, app, accent):
        hue = sum(map(ord, app or "?")) % 360
        col = ImageColor.getrgb(f"hsl({hue}, 65%, 55%)") if app else accent
        d.ellipse((x, y, x + 2 * r, y + 2 * r), fill=col)
        d.text((x + r, y + r), (app or "?")[:1].upper(), font=load_font(None, max(8, int(r * 1.3))), fill=(255, 255, 255), anchor="mm")

    def render(self):
        n = self._source()
        img, d = self.new_layer()
        size = int(self.cfg.get("size", 16))
        bold = load_font(self.cfg.get("font_bold") or self.cfg.get("font"), size, self.ctx.base_dir)
        reg = load_font(self.cfg.get("font"), max(9, round(size * 0.8)), self.ctx.base_dir)
        fg, muted = color(self.cfg.get("color", "white")), color(self.cfg.get("muted", "#8b95a7"))
        accent = color(self.cfg.get("accent", "#4dabf7"))
        if self.mode == "alert":
            ev = n.active()
            if ev is None:
                return img  # fully transparent: the card underneath shows again
            d.rounded_rectangle((0, 0, self.w - 1, self.h - 1), int(self.cfg.get("radius", 10)),
                                fill=color(self.cfg.get("fill", "#161b26")) + (255,), outline=accent + (255,), width=2)
            self._draw_event(d, ev, 8, 6, self.w - 16, self.h - 12, bold, reg, fg, muted, accent, size)
            return img
        evs = n.listing(int(self.cfg.get("rows", 3)))
        if not evs:
            text = _ellipsize(d, self.cfg.get("idle_text", "Sem notificações"), reg, self.w)
            d.text((0, (self.h - reg.size) // 2), text, font=reg, fill=muted)
            return img
        row_h = round(bold.size * 1.3 + reg.size * 1.25) + 10
        for i, ev in enumerate(evs):
            y = i * row_h
            if y + row_h - 4 > self.h and i:
                break
            self._draw_row(d, ev, 0, y, self.w, row_h - 4, bold, reg, fg, muted, accent)
        return img

    def _draw_row(self, d, ev, x, y, w, h, bold, reg, fg, muted, accent):
        """History row: coloured initial, then "App · title" and, below, the message on one line."""
        r = max(8, h // 2 - 1)
        self._dot(d, x, y + (h - 2 * r) // 2, r, ev["app"], accent)
        tx = x + 2 * r + 8
        head = f"{ev['app']} · {ev['title']}" if ev["title"] else ev["app"]
        d.text((tx, y), _ellipsize(d, head, bold, w - (tx - x)), font=bold, fill=fg)
        if ev["body"]:
            d.text((tx, y + round(bold.size * 1.3)), _ellipsize(d, ev["body"], reg, w - (tx - x)), font=reg, fill=muted)

    def _draw_event(self, d, ev, x, y, w, h, bold, reg, fg, muted, accent, size, compact=False):
        app, title, body = ev["app"], ev["title"], ev["body"]
        if h < 40:  # one line: coloured initial, then "title body" (or the app name)
            r = max(7, int(h / 2) - 1)
            self._dot(d, x, y + (h - 2 * r) // 2, r, app, accent)
            text = " ".join(t for t in (title or app, body) if t)
            d.text((x + 2 * r + 8, y + h / 2), _ellipsize(d, text, bold, w - 2 * r - 8), font=bold, fill=fg, anchor="lm")
            return
        r = max(10, min(18, int(h * 0.22)))
        self._dot(d, x, y + 2, r, app, accent)
        tx = x + 2 * r + 10
        tw = w - (tx - x)
        d.text((tx, y + 2 + r), _ellipsize(d, app, reg, tw), font=reg, fill=muted, anchor="lm")
        used = y + 2 * r + 6
        if title:
            d.text((tx, used), _ellipsize(d, title, bold, tw), font=bold, fill=fg)
            used += round(bold.size * 1.3)
        if body:
            line_h = round(reg.size * 1.25)
            room = max(1, int((y + h - used) // line_h))
            for line in _wrap_lines(d, body, reg, tw, room):
                d.text((tx, used), line, font=reg, fill=muted)
                used += line_h


class RectWidget(Widget):
    """Filled rounded rectangle - cards, panels, dividers."""

    type_name = "rect"

    def update(self) -> bool:
        return self.layer is None

    def render(self):
        img, d = self.new_layer()
        d.rounded_rectangle(
            (0, 0, self.w - 1, self.h - 1),
            int(self.cfg.get("radius", 0)),
            fill=color(self.cfg.get("fill", "#161b26")),
            outline=color(self.cfg["outline"]) if self.cfg.get("outline") else None,
            width=int(self.cfg.get("outline_width", 1)),
        )
        return img


REGISTRY = {
    c.type_name: c
    for c in (
        TextWidget, ClockWidget, BarWidget, RadialWidget, VisualizerWidget, NowPlayingWidget, NoticeWidget, GraphWidget, ImageWidget, WebImageWidget,
        CommandWidget, FileTextWidget, HttpJsonWidget, PluginWidget, RectWidget,
    )
}


def make_widget(cfg: dict, ctx: Context) -> Widget:
    kind = cfg.get("type")
    if kind not in REGISTRY:
        raise ValueError(f"unknown widget type {kind!r}; available: {sorted(REGISTRY)}")
    return REGISTRY[kind](cfg, ctx)
