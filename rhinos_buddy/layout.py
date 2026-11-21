"""Slot-based layout model used by the editor.

A *layout* is plain JSON (saved by the app, edited by the web UI)::

    {"device": {...}, "sensors": {...}, "theme": {...},
     "pages": [{"name": "Principal", "duration": 12, "slots": [
         {"module": "cpu", "col": 0, "row": 2, "w": 6, "h": 3, "options": {...}}]}]}

The screen is divided in a grid of 40 px cells (12 x 8 in landscape).  A slot is a
rectangle of cells holding one *module* (CPU, relógio, imagem...).  Because every cell is a
multiple of 8 px, all updates also respect the panel's alignment needs.

``to_config`` turns a layout into the widget configuration the engine already understands.
"""

from __future__ import annotations

import copy
import re
from pathlib import Path

from . import i18n
from . import protocol as P
from .widgets import date_names, load_font

CELL = 40
MAX_PAGES = 8
MAX_SLOTS = 32
BETA_GROUP = "Em teste"  # modules still being polished; the editor lists them in an expandable category
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

# label -> (regular, bold) font files (Windows names first; the renderer falls back to DejaVu)
FONTS = {
    "Segoe UI": ("segoeui.ttf", "segoeuib.ttf"),
    "Bahnschrift": ("bahnschrift.ttf", "bahnschrift.ttf"),
    "Calibri": ("calibri.ttf", "calibrib.ttf"),
    "Arial": ("arial.ttf", "arialbd.ttf"),
    "Consolas": ("consola.ttf", "consolab.ttf"),
    "Verdana": ("verdana.ttf", "verdanab.ttf"),
    "DejaVu Sans": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
}

ROTATIONS = [
    ["landscape", "Paisagem"],
    ["reverse_landscape", "Paisagem invertida (180°)"],
    ["portrait", "Retrato"],
    ["reverse_portrait", "Retrato invertido"],
]

DEFAULT_THEME = {
    "font": "Segoe UI",
    "text": "#ffffff",
    "muted": "#8b95a7",
    "temp": "#f2b84b",
    "warn": "#e5484d",
    "accent": "#4dabf7",
    "bar_style": "barra",  # default indicator for modules that have one: "barra" or "radial"
    "colorful": True,  # a different colour per module instead of one accent
    "decimal_comma": True,
    "background": {"color": "#0b0f1a", "image": "", "dim": 35, "fit": "cover"},
    "card": {"enabled": False, "color": "#161b26", "opacity": 70, "radius": 10},
}
DEFAULT_DEVICE = {
    "port": "auto", "orientation": "landscape", "brightness": 100,
    "fps": 20, "refresh": 2, "invert_brightness": True, "stability": 2, "align": 8, "rotate": True,
    "notify": False, "notify_seconds": 6, "notify_apps": "", "notify_text": True,
}
DEFAULT_SENSORS = {"nvidia_smi": True, "lhm": True, "lhm_url": "http://127.0.0.1:8085/data.json"}


def orientation_family(orientation: str) -> str:
    """"portrait" for both portrait rotations, "landscape" for both landscape ones (same grid)."""
    return "portrait" if "portrait" in orientation else "landscape"


def grid_size(orientation: str) -> tuple[int, int]:
    w, h = P.screen_size(orientation)
    return w // CELL, h // CELL


# =========================================================================== modules
def O(key, label, kind, default, choices=None, **kw):
    d = {"key": key, "label": label, "kind": kind, "default": default}
    if choices is not None:
        d["choices"] = [list(c) for c in choices]
    d.update(kw)
    return d


COMMON_OPTIONS = [
    O("card", "Cartão de fundo", "choice", "tema",
      [("tema", "Seguir o tema"), ("sim", "Sempre"), ("nao", "Nunca")]),
    O("notify", "Mostrar avisos de notificação neste card", "bool", False),
]


def _stat_opts(label, bar=True, temp=False, graph=False):
    o = [O("label", "Rótulo", "text", label)]
    if temp:
        o.append(O("show_sub", "Mostrar temperatura", "bool", True))
    if bar:
        o.append(O("bar_style", "Estilo do indicador", "choice", "tema",
                   [("tema", "Seguir o tema"), ("barra", "Barra horizontal"), ("radial", "Radial (círculo)")]))
    o.append(O("show_bar", "Mostrar barra", "bool", bar))
    o.append(O("show_graph", "Mostrar gráfico", "bool", graph))
    o.append(O("align", "Posição do texto", "choice", "padrao",
                   [("padrao", "Padrão"), ("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]))
    o.append(O("color", "Cor (vazio = padrão)", "color", ""))
    return o


MODULES: dict[str, dict] = {
    "clock": dict(label="Relógio", group="Data e hora", size=(5, 2), color="text", options=[
        O("format", "Formato", "choice", "%H:%M", [("%H:%M", "13:45"), ("%H:%M:%S", "13:45:09")]),
        O("align", "Alinhamento", "choice", "left", [("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "date": dict(label="Data", group="Data e hora", size=(6, 2), color="muted", options=[
        O("style", "Estilo", "choice", "completo", [
            ("completo", "Quarta-feira + 11 de novembro de 2026"),
            ("extenso", "11 de novembro de 2026"),
            ("curto", "11/11/2026"),
            ("semana_curto", "qua, 11 nov")]),
        O("align", "Alinhamento", "choice", "right", [("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "cpu": dict(label="CPU (uso)", group="Processador", size=(6, 3), color="#4dabf7",
                options=_stat_opts("CPU", temp=True)),
    "cpu_temp": dict(label="CPU (temperatura)", group="Processador", size=(3, 2), color="#f2b84b",
                     options=_stat_opts("Temp. CPU", graph=False)),
    "gpu": dict(label="GPU (uso)", group="Placa de vídeo", size=(6, 3), color="#35c46d",
                options=_stat_opts("GPU", temp=True)),
    "gpu_temp": dict(label="GPU (temperatura)", group="Placa de vídeo", size=(3, 2), color="#f2b84b",
                     options=_stat_opts("Temp. GPU", graph=False)),
    "vram": dict(label="Memória de vídeo", group="Placa de vídeo", size=(4, 2), color="#38d9c0",
                 options=_stat_opts("VRAM", temp=False)),
    "ram": dict(label="Memória RAM", group="Memória e disco", size=(6, 2), color="#b197fc",
                options=_stat_opts("RAM")),
    "disk": dict(label="Disco (uso)", group="Memória e disco", size=(4, 2), color="#ffa94d",
                 options=_stat_opts("Disco")),
    "net": dict(label="Rede (download + upload)", group="Rede", size=(12, 2), color="#4dabf7", options=[
        O("show_graph", "Mostrar gráfico", "bool", False),
        O("align", "Posição do texto", "choice", "padrao",
                   [("padrao", "Padrão"), ("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "net_down": dict(label="Download", group="Rede", size=(4, 2), color="#4dabf7",
                     options=_stat_opts("↓ Download", bar=False)),
    "net_up": dict(label="Upload", group="Rede", size=(4, 2), color="#35c46d",
                   options=_stat_opts("↑ Upload", bar=False)),
    "musica": dict(label="Música (visualizador)", group="Música", size=(6, 3), color="#b197fc", options=[
        O("show_track", "Mostrar o que está tocando", "bool", True),
        O("track_layout", "Aparência do que está tocando", "choice", "texto", [
            ("texto", "Compacto (título e artista)"), ("capa", "Card expandido (capa + progresso)")]),
        O("show_cover", "Card: mostrar a capa", "bool", True),
        O("show_progress", "Card: mostrar barra de progresso e tempo", "bool", True),
        O("show_artist", "Mostrar o artista", "bool", True),
        O("marquee", "Rolar títulos longos (como nos MP3 antigos)", "bool", True),
        O("show_viz", "Mostrar visualizador de áudio", "bool", True),
        O("viz_style", "Estilo do visualizador", "choice", "barras", [
            ("barras", "Barras"), ("espelho", "Barras espelhadas"), ("circular", "Circular"), ("pulso", "Pulso (batida)")]),
        O("bars", "Quantidade de barras", "int", 12, min=4, max=32),
        O("sensitivity", "Sensibilidade", "int", 50, min=1, max=100),
        O("align", "Alinhamento do texto", "choice", "left", [("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "visualizador": dict(label="Visualizador de áudio", group="Música", size=(4, 2), color="#b197fc", options=[
        O("viz_style", "Estilo", "choice", "barras", [
            ("barras", "Barras"), ("espelho", "Barras espelhadas"), ("circular", "Circular"), ("pulso", "Pulso (batida)")]),
        O("bars", "Quantidade de barras", "int", 12, min=4, max=32),
        O("sensitivity", "Sensibilidade", "int", 50, min=1, max=100),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "notificacao": dict(label="Notificações (lista)", group=BETA_GROUP, size=(4, 3), color="#4dabf7", options=[
        O("rows", "Quantas mostrar", "int", 3, min=1, max=6),
        O("align", "Alinhamento do texto", "choice", "left", [("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("idle_text", "Texto quando não há nenhuma", "text", "Sem notificações"),
    ]),
    "text": dict(label="Texto livre", group="Outros", size=(4, 1), color="text", options=[
        O("text", "Texto (aceita {cpu:.0f} {gpu_temp:.0f} ...)", "text", "Meu texto"),
        O("size", "Tamanho (0 = automático)", "int", 0, min=0, max=90),
        O("align", "Alinhamento", "choice", "left", [("left", "Esquerda"), ("center", "Centro"), ("right", "Direita")]),
        O("color", "Cor (vazio = padrão)", "color", ""),
    ]),
    "image": dict(label="Imagem / GIF", group="Outros", size=(4, 3), color="text", options=[
        O("image", "Arquivo", "file", ""),
        O("fit", "Ajuste", "choice", "contain", [("contain", "Inteira"), ("cover", "Preencher"), ("stretch", "Esticar")]),
    ]),
}

# ================================================================== normalisation
def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _color(v, default=""):
    return v if isinstance(v, str) and HEX.match(v) else default


def _media_name(v, home: Path | None) -> str:
    """Only files that live in the app's media folder are allowed (no arbitrary paths)."""
    if not isinstance(v, str) or not v:
        return ""
    name = Path(v.replace("\\", "/")).name
    if home is not None and not (Path(home) / "media" / name).is_file():
        return ""
    return name


def _option_value(spec: dict, raw, home):
    kind, default = spec["kind"], spec["default"]
    if kind == "bool":
        return bool(raw) if isinstance(raw, bool) else default
    if kind == "choice":
        allowed = [c[0] for c in spec["choices"]]
        return raw if raw in allowed else default
    if kind == "int":
        return _clamp(raw, spec.get("min", 0), spec.get("max", 1000), default)
    if kind == "color":
        return _color(raw, default)
    if kind == "file":
        return _media_name(raw, home)
    return str(raw)[:120] if isinstance(raw, str) else default


def normalize(layout: dict | None, home: Path | None = None) -> dict:
    """Fill defaults, clamp everything into range and drop what is unknown.  Never raises."""
    src = layout if isinstance(layout, dict) else {}
    out: dict = {"version": 1}

    dev = src.get("device") if isinstance(src.get("device"), dict) else {}
    d = dict(DEFAULT_DEVICE)
    port = dev.get("port", "auto")
    d["port"] = port if isinstance(port, str) and re.fullmatch(r"auto|COM\d{1,3}|/dev/[\w./-]+", port) else "auto"
    d["orientation"] = dev.get("orientation") if dev.get("orientation") in dict(ROTATIONS) else DEFAULT_DEVICE["orientation"]
    d["brightness"] = _clamp(dev.get("brightness"), 0, 100, 100)
    d["fps"] = _clamp(dev.get("fps"), 2, 30, 20)
    d["refresh"] = _clamp(dev.get("refresh"), 1, 10, 2)
    d["invert_brightness"] = dev.get("invert_brightness") if isinstance(dev.get("invert_brightness"), bool) else True
    st = dev.get("stability")
    d["stability"] = st if isinstance(st, int) and not isinstance(st, bool) and 0 <= st <= 2 else 2
    al = dev.get("align")
    d["align"] = al if isinstance(al, int) and not isinstance(al, bool) and al in (1, 2, 4, 8, 16) else 8
    d["rotate"] = dev.get("rotate") if isinstance(dev.get("rotate"), bool) else True
    d["notify"] = dev.get("notify") if isinstance(dev.get("notify"), bool) else False
    d["notify_seconds"] = _clamp(dev.get("notify_seconds"), 2, 30, 6)
    apps = dev.get("notify_apps")
    d["notify_apps"] = re.sub(r"[^\w ,.\-+]", "", apps)[:120] if isinstance(apps, str) else ""
    d["notify_text"] = dev.get("notify_text") if isinstance(dev.get("notify_text"), bool) else True
    out["device"] = d

    sen = src.get("sensors") if isinstance(src.get("sensors"), dict) else {}
    url = sen.get("lhm_url", DEFAULT_SENSORS["lhm_url"])
    out["sensors"] = {
        "nvidia_smi": sen.get("nvidia_smi") if isinstance(sen.get("nvidia_smi"), bool) else True,
        "lhm": sen.get("lhm") if isinstance(sen.get("lhm"), bool) else True,
        "lhm_url": url if isinstance(url, str) and re.match(r"^http://(127\.0\.0\.1|localhost)(:\d+)?/", url) else DEFAULT_SENSORS["lhm_url"],
    }

    th_in = src.get("theme") if isinstance(src.get("theme"), dict) else {}
    th = copy.deepcopy(DEFAULT_THEME)
    th["font"] = th_in.get("font") if th_in.get("font") in FONTS else th["font"]
    for k in ("text", "muted", "temp", "warn", "accent"):
        th[k] = _color(th_in.get(k), th[k])
    th["bar_style"] = th_in.get("bar_style") if th_in.get("bar_style") in ("barra", "radial") else th["bar_style"]
    for k in ("colorful", "decimal_comma"):
        th[k] = th_in.get(k) if isinstance(th_in.get(k), bool) else th[k]
    bg_in = th_in.get("background") if isinstance(th_in.get("background"), dict) else {}
    th["background"] = {
        "color": _color(bg_in.get("color"), th["background"]["color"]),
        "image": _media_name(bg_in.get("image"), home),
        "dim": _clamp(bg_in.get("dim"), 0, 95, th["background"]["dim"]),
        "fit": bg_in.get("fit") if bg_in.get("fit") in ("cover", "contain", "stretch") else "cover",
    }
    c_in = th_in.get("card") if isinstance(th_in.get("card"), dict) else {}
    th["card"] = {
        "enabled": c_in.get("enabled") if isinstance(c_in.get("enabled"), bool) else th["card"]["enabled"],
        "color": _color(c_in.get("color"), th["card"]["color"]),
        "opacity": _clamp(c_in.get("opacity"), 0, 100, th["card"]["opacity"]),
        "radius": _clamp(c_in.get("radius"), 0, 30, th["card"]["radius"]),
    }
    out["theme"] = th

    cols, rows = grid_size(d["orientation"])
    family = orientation_family(d["orientation"])

    def norm_slots(raw, cols: int, rows: int) -> list[dict]:
        slots = []
        for sl in (raw if isinstance(raw, list) else [])[:MAX_SLOTS]:
            if not isinstance(sl, dict) or sl.get("module") not in MODULES:
                continue
            mod = MODULES[sl["module"]]
            w = _clamp(sl.get("w"), 1, cols, mod["size"][0])
            h = _clamp(sl.get("h"), 1, rows, mod["size"][1])
            raw_opts = sl.get("options") if isinstance(sl.get("options"), dict) else {}
            opts = {sp["key"]: _option_value(sp, raw_opts.get(sp["key"], sp["default"]), home)
                    for sp in mod["options"] + COMMON_OPTIONS}
            slot = {
                "module": sl["module"],
                "col": _clamp(sl.get("col"), 0, cols - w, 0),
                "row": _clamp(sl.get("row"), 0, rows - h, 0),
                "w": w, "h": h, "options": opts, "hidden": sl.get("hidden") is True,
            }
            # where this card sat in the *other* screen orientation, so rotating back restores it exactly
            other = "landscape" if family == "portrait" else "portrait"
            ocols, orows = (8, 12) if other == "portrait" else (12, 8)
            mem = sl.get("alt", {}).get(other) if isinstance(sl.get("alt"), dict) else None
            if isinstance(mem, dict):
                mw, mh = _clamp(mem.get("w"), 1, ocols, 1), _clamp(mem.get("h"), 1, orows, 1)
                slot["alt"] = {other: {"col": _clamp(mem.get("col"), 0, ocols - mw, 0), "row": _clamp(mem.get("row"), 0, orows - mh, 0),
                                       "w": mw, "h": mh}}
            slots.append(slot)
        return slots

    def norm_page(pg: dict, index: int) -> dict:
        name = pg.get("name") if isinstance(pg.get("name"), str) and pg["name"].strip() else f"Página {index}"
        page = {"name": name.strip()[:30], "duration": _clamp(pg.get("duration"), 3, 300, 12),
                "slots": norm_slots(pg.get("slots"), cols, rows)}
        return page

    pages = [norm_page(pg, i + 1) for i, pg in
             enumerate(p for p in (src.get("pages") if isinstance(src.get("pages"), list) else [])[:MAX_PAGES]
                       if isinstance(p, dict))]
    if not pages:
        pages = [norm_page({"name": "Principal", "slots": template("completo", cols, rows)}, 1)]
    out["pages"] = pages
    return out


# ============================================================================ templates
def _s(module, col, row, w, h, **options):
    return {"module": module, "col": col, "row": row, "w": w, "h": h, "options": options}


TEMPLATES = {
    "completo": "Completo (hora, CPU, GPU, RAM, rede)",
    "minimo": "Mínimo (hora e temperaturas)",
    "aneis": "Anéis (CPU, GPU, VRAM e RAM em círculos)",
    "foto": "Foto de fundo (cartões translúcidos)",
    "vazio": "Em branco",
}


def template(name: str, cols: int = 12, rows: int = 8) -> list[dict]:
    landscape = cols >= rows
    if name == "vazio":
        return []
    if name == "minimo":
        if landscape:
            return [_s("clock", 0, 0, 7, 3), _s("date", 7, 0, 5, 3),
                    _s("cpu_temp", 0, 4, 6, 4), _s("gpu_temp", 6, 4, 6, 4)]
        return [_s("clock", 0, 0, 8, 3), _s("date", 0, 3, 8, 1),
                _s("cpu_temp", 0, 5, 8, 3), _s("gpu_temp", 0, 8, 8, 3)]
    if name == "aneis":  # the four gauges as rings, each on its own so it works whatever the theme says
        if landscape:
            slots = [_s("clock", 0, 0, 5, 2), _s("date", 5, 0, 7, 2),
                     _s("cpu", 0, 2, 3, 4), _s("gpu", 3, 2, 3, 4), _s("vram", 6, 2, 3, 4), _s("ram", 9, 2, 3, 4),
                     _s("net", 0, 6, 12, 2)]
        else:
            slots = [_s("clock", 0, 0, 8, 2), _s("date", 0, 2, 8, 1),
                     _s("cpu", 0, 3, 4, 3), _s("gpu", 4, 3, 4, 3), _s("vram", 0, 6, 4, 3), _s("ram", 4, 6, 4, 3),
                     _s("net", 0, 9, 8, 3)]
        for sl in slots:
            if sl["module"] in ("cpu", "gpu", "vram", "ram"):
                sl["options"]["bar_style"] = "radial"
        return slots
    if name == "foto":  # same arrangement as "completo", every slot on a translucent card
        slots = template("completo", cols, rows)
        for sl in slots:
            sl["options"]["card"] = "sim"
        return slots
    # "completo"
    if landscape:
        return [_s("clock", 0, 0, 5, 2), _s("date", 6, 0, 6, 2),
                _s("cpu", 0, 2, 6, 3), _s("gpu", 6, 2, 6, 3),
                _s("ram", 0, 5, 12, 1), _s("net", 0, 6, 12, 2)]
    return [_s("clock", 0, 0, 8, 2), _s("date", 0, 2, 8, 1),
            _s("cpu", 0, 3, 8, 3), _s("gpu", 0, 6, 8, 3),
            _s("ram", 0, 9, 8, 1), _s("net", 0, 10, 8, 2)]


def default_layout() -> dict:
    return normalize({})


# ================================================================= module rendering
def fit_size(font_file: str, sample: str, max_w: float, max_h: float, hi: int = 64, lo: int = 9) -> int:
    """Largest font size at which ``sample`` still fits in max_w x max_h pixels."""
    for size in range(hi, lo - 1, -1):
        l, t, r, b = load_font(font_file, size, None).getbbox(sample)
        if r - l <= max_w and b - t <= max_h:
            return size
    return lo


def text_w(font_file: str, size: int, sample: str) -> float:
    return load_font(font_file, size, None).getlength(sample)


def _rgba(hex_color: str, opacity: int) -> str:
    return f"{hex_color}{round(255 * opacity / 100):02x}"


class _Ctx:
    def __init__(self, theme: dict, device: dict):
        self.th = theme
        self.refresh = device["refresh"]
        self.font, self.bold = FONTS[theme["font"]]


def _text(c: _Ctx, x, y, w, h, text, size, color, align="left", bold=False, valign="middle", interval=None):
    return {"type": "text", "x": int(x), "y": int(y), "w": max(1, int(w)), "h": max(1, int(h)),
            "text": text, "size": int(size), "font": c.bold if bold else c.font, "color": color,
            "align": align, "valign": valign, "interval": interval or c.refresh}


def _module_color(c: _Ctx, module: str, opts: dict) -> str:
    if opts.get("color"):
        return opts["color"]
    default = MODULES[module]["color"]
    if default in ("text", "muted"):
        return c.th[default]
    return default if c.th["colorful"] else c.th["accent"]


def _gradient_end(hex_color: str) -> str:
    """Second colour of a ring's gradient: the same colour rotated a little around the hue wheel."""
    import colorsys

    r, g, b = (int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5))
    hh, ll, ss = colorsys.rgb_to_hls(r, g, b)
    r, g, b = colorsys.hls_to_rgb((hh + 0.15) % 1.0, min(0.68, ll + 0.04), ss)
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _ring(c: _Ctx, x, y, d, *, bar, bar_range, warn_at, color, thick):
    lo, hi = bar_range
    return {"type": "radial", "x": int(x), "y": int(y), "w": int(d), "h": int(d), "metric": bar, "min": lo, "max": hi,
            "color": color, "color2": _gradient_end(color), "warn_at": warn_at, "warn_color": c.th["warn"],
            "thickness": thick, "track": "#ffffff", "track_alpha": 38, "interval": c.refresh}


def _stat_radial(c: _Ctx, x, y, w, h, *, label, value, sample, sub, sub_sample, bar, bar_range, warn_at, color, sub_color,
                 align="padrao"):
    """Circular gauge version of ``_stat``: the number sits inside the ring."""
    th, out = c.th, []
    sub = sub or None
    if h < 52:  # one row: small ring, then label and value beside it
        d = int(h)
        out.append(_ring(c, x, y, d, bar=bar, bar_range=bar_range, warn_at=warn_at, color=color, thick=max(3, round(d * 0.14))))
        rx, rw = x + d + 8, w - d - 8
        size = fit_size(c.bold, sample, rw * 0.5, h, hi=24)
        vw = min(text_w(c.bold, size, sample) + 8, rw * 0.7)
        room = rw - vw
        lsize = 13 if text_w(c.font, 13, label) <= room else 11
        if text_w(c.font, lsize, label) <= room:  # no room for the label: the ring and number say enough
            out.append(_text(c, rx, y, room, h, label, lsize, th["muted"]))
        out.append(_text(c, x + w - vw, y, vw, h, value, size, th["text"], "right", bold=True))
        return out
    d = int(min(w, h))
    thick = max(4, round(d * 0.12))
    inner = d - 2 * thick - 6
    wide = w >= 1.8 * d
    tw_wide = w - d - 14
    if wide:
        est = max([text_w(c.font, 15, label)] + ([text_w(c.bold, 24, sub_sample)] if sub else []))
        if align == "right":
            rx = x + w - d
        elif align == "center":
            rx = x + (w - (d + 14 + min(est, tw_wide))) / 2
        else:
            rx = x
    else:
        rx = x if align == "left" else x + w - d if align == "right" else x + (w - d) / 2
    ry = y + (h - d) / 2
    out.append(_ring(c, rx, ry, d, bar=bar, bar_range=bar_range, warn_at=warn_at, color=color, thick=thick))
    cx, cy = rx + d / 2, ry + d / 2
    stack = []  # (text, size, color, bold) from top to bottom inside the ring
    vsize = fit_size(c.bold, sample, inner * 0.8, inner * 0.36, hi=44)
    if not wide and d >= 72 and sub:
        ssize = fit_size(c.font, sub_sample, inner * 0.66, inner * 0.17, hi=14)
        stack.append((sub, ssize, sub_color or th["temp"], False))
    stack.append((value, vsize, th["text"], True))
    if not wide:
        lsize = fit_size(c.font, label, inner * 0.62, inner * 0.18, hi=16)
        stack.append((label, lsize, th["muted"], False))
    heights = [round(s * 1.25) for _, s, _, _ in stack]
    top = cy - sum(heights) / 2
    for (text, size, col, bold), hh in zip(stack, heights):
        out.append(_text(c, cx - inner * 0.45, top, inner * 0.9, hh, text, size, col, "center", bold=bold))
        top += hh
    if wide:  # label and the secondary reading to the right of the ring
        tx, tw = rx + d + 14, tw_wide
        t_align = "left"
        if align == "right":
            tx, t_align = x, "right"
        elif align == "center":
            tw = min(est, tw_wide) + 2
        rows = [(label, 15, th["muted"], False)] + ([(sub, fit_size(c.bold, sub_sample, tw, 28, hi=24), sub_color or th["temp"], True)] if sub else [])
        hs = [round(s * 1.3) for _, s, _, _ in rows]
        t = cy - sum(hs) / 2
        for (text, size, col, bold), hh in zip(rows, hs):
            out.append(_text(c, tx, t, tw, hh, text, size, col, t_align, bold=bold))
            t += hh
    return out


def _stat(c: _Ctx, x, y, w, h, *, label, value, sample, sub=None, sub_sample="", bar=None, bar_range=(0, 100),
          warn_at=90, graph=None, color, show_bar=True, show_graph=False, sub_color=None, radial=False, align="padrao"):
    """Label row + big value (+ graph) (+ bar), adapting to the slot's height."""
    if radial and bar:
        return _stat_radial(c, x, y, w, h, label=label, value=value, sample=sample, sub=sub or None, sub_sample=sub_sample,
                            bar=bar, bar_range=bar_range, warn_at=warn_at, color=color, sub_color=sub_color, align=align)
    th, out = c.th, []
    sub = sub or None
    if h < 52:  # compact one-liner: label left, "sub   value" right
        right = f"{sub}   {value}" if sub and w >= 200 else value
        right_sample = f"{sub_sample}   {sample}" if sub and w >= 200 else sample
        lab_size = 12 if w < 220 else 14
        lw = text_w(c.font, lab_size, label) + 10  # the label keeps the room it needs
        size = fit_size(c.bold, right_sample, max(w - lw, w * 0.4), h, hi=24)
        rw = min(text_w(c.bold, size, right_sample) + 8, w * 0.65)
        if align == "padrao":  # label at one edge, number at the other
            out.append(_text(c, x, y, w - rw, h, label, lab_size, th["muted"]))
            out.append(_text(c, x + w - rw, y, rw, h, right, size, th["text"], "right", bold=True))
        else:  # label and number side by side, as one block placed left / centre / right
            rw = min(rw, max(20, w - lw))
            block = lw + rw
            bx = x if align == "left" else x + (w - block) / 2 if align == "center" else x + w - block
            out.append(_text(c, bx, y, lw, h, label, lab_size, th["muted"]))
            out.append(_text(c, bx + lw, y, rw, h, right, size, th["text"], "left", bold=True))
        return out
    al = "left" if align == "padrao" else align
    label_h = 18
    lab_size = 13 if h < 90 else 15
    sub_w = 0
    if sub:
        sub_size = fit_size(c.font, sub_sample, w * 0.6, label_h, hi=lab_size + 3)
        sub_w = min(text_w(c.font, sub_size, sub_sample) + 6, w * 0.6)
        sub_x, sub_al = (x, "left") if al == "right" else (x + w - sub_w, "right")  # temperature on the far side
        out.append(_text(c, sub_x, y, sub_w, label_h, sub, sub_size, sub_color or th["temp"], sub_al))
    gap_ = sub_w + (4 if sub else 0)
    lx, lwid = (x + gap_, w - gap_) if al == "right" else (x, w - gap_)
    if al == "center" and sub:  # keep the label centred on the slot without touching the temperature
        lx, lwid = x + gap_, w - 2 * gap_
    out.append(_text(c, lx, y, lwid, label_h, label, lab_size, th["muted"], al))
    cur = y + label_h + 2
    remaining = y + h - cur
    bar_h = 8 if (show_bar and bar) else 0
    graph_h = 0
    if show_graph and graph:
        graph_h = min(70, int(remaining * 0.45))
        if remaining - graph_h - (bar_h + 6) - 6 < 24:
            graph_h = 0
    value_h = remaining - (bar_h + 6 if bar_h else 0) - (graph_h + 6 if graph_h else 0)
    size = fit_size(c.bold, sample, w, value_h * 0.95, hi=56)
    out.append(_text(c, x, cur, w, value_h, value, size, th["text"], al, bold=True))
    cur += value_h
    if graph_h:
        out.append({"type": "graph", "x": int(x), "y": int(cur + 6), "w": int(w), "h": int(graph_h),
                    "metric": graph, "color": color, "background": "#00000040", "interval": c.refresh})
    if bar_h:
        lo, hi = bar_range
        out.append({"type": "bar", "x": int(x), "y": int(y + h - bar_h), "w": int(w), "h": bar_h,
                    "metric": bar, "min": lo, "max": hi, "color": color, "warn_at": warn_at,
                    "warn_color": th["warn"], "track": "#ffffff26", "interval": c.refresh})
    return out


USB_BUDGET = 90_000  # bytes/s of the ~128 KB/s link a visualizer may use


def _viz_widget(c: _Ctx, o: dict, x, y, w, h, col) -> dict:
    """Visualizer sized for the link: the bigger the area, the slower it may redraw."""
    style = o["viz_style"]
    if style in ("circular", "pulso"):  # round shapes: a square box keeps the redraw area small
        d = int(min(w, h))
        x, y, w, h = x + (w - d) / 2, y + (h - d) / 2, d, d
    interval = round(min(1.0, max(0.1, w * h * 2 / USB_BUDGET)), 2)
    return {"type": "visualizer", "x": int(x), "y": int(y), "w": max(8, int(w)), "h": max(8, int(h)),
            "style": style, "bars": max(4, min(o["bars"], int(w // 6))), "sensitivity": o["sensitivity"],
            "color": col, "color2": _gradient_end(col), "interval": interval}


def _build_music(c: _Ctx, o: dict, x, y, w, h, col) -> list[dict]:
    th, out = c.th, []
    track, viz = o["show_track"], o["show_viz"]
    if not track and not viz:
        return out

    def track_widget(tx, ty, tw, th_):
        size = max(11, min(22, int(th_ / (2.4 if o["show_artist"] else 1.5))))
        wd = {"type": "nowplaying", "x": int(tx), "y": int(ty), "w": max(1, int(tw)), "h": max(1, int(th_)),
                "size": size, "font": c.font, "font_bold": c.bold, "color": th["text"], "muted": th["muted"],
                "align": o["align"], "show_artist": o["show_artist"], "marquee": o["marquee"],
                "interval": 0.125 if o["marquee"] else 2}
        if o["track_layout"] == "capa":
            wd.update(mode="capa", show_cover=o["show_cover"], show_progress=o["show_progress"], accent=col,
                      interval=0.125 if o["marquee"] else 0.25)  # polled 4x a second so no second is skipped; it only redraws when the second changes
            wd.pop("size")
        return wd

    if track and o["track_layout"] == "capa":
        vh = min(48, h * 0.25) if viz else 0
        if viz and h - vh - 6 < 80:  # no room for the cover card plus a strip: card only
            vh = 0
        out.append(track_widget(x, y, w, h - (vh + 6 if vh else 0)))
        if vh:
            out.append(_viz_widget(c, o, x, y + h - vh, w, vh, col))
    elif track and viz:
        if w >= 2.2 * h and h < 90:  # wide and short: text on the left, visualizer on the right
            vw = min(h * 1.8, w * 0.4)
            out.append(track_widget(x, y, w - vw - 10, h))
            out.append(_viz_widget(c, o, x + w - vw, y, vw, h, col))
        else:
            tH = min(52, h * 0.45)
            out.append(track_widget(x, y, w, tH))
            out.append(_viz_widget(c, o, x, y + tH + 6, w, h - tH - 6, col))
    elif track:
        out.append(track_widget(x, y, w, h))
    else:
        out.append(_viz_widget(c, o, x, y, w, h, col))
    return out




_LONG_DATE = {"pt": "{dia} de {mes} de {ano}", "en": "{mes} {dia}, {ano}"}


def _widest(font_file: str, samples) -> str:
    """The sample that is widest in this font (names differ a lot: "sex" vs "seg", "maio" vs "setembro")."""
    f = load_font(font_file, 40, None)
    return max(samples, key=lambda t: f.getlength(t))


def _long_date_samples() -> list[str]:
    """Every "<day> <month> <year>" the long date can show, in the interface language (sizing uses the widest)."""
    months = date_names()[2]
    if i18n.lang() == "en":
        return [f"{m} 00, 2026" for m in months]
    return [f"00 de {m} de 2026" for m in months]


def _fit_long_date(c: _Ctx, w, h, hi) -> int:
    """Font size for the long date that fits the box for the widest month in this font."""
    return min(fit_size(c.font, sample, w, h, hi=hi) for sample in _long_date_samples())


def _opt_default(module: str, key: str):
    for sp in MODULES[module]["options"] + COMMON_OPTIONS:
        if sp["key"] == key:
            return sp["default"]
    return None


def _localized(module: str, o: dict) -> dict:
    """Texts the program itself put there (default labels, "Nothing playing"...) follow the language; text the
    user typed is never touched."""
    if i18n.lang() == "pt":
        return o
    o = dict(o)
    for k in ("label", "text", "idle_text"):
        if k in o and o[k] == _opt_default(module, k):
            o[k] = i18n.t(o[k])
    return o


def _build_module(c: _Ctx, module: str, o: dict, x, y, w, h) -> list[dict]:
    th = c.th
    o = _localized(module, o)
    if module == "notificacao":  # history of the latest notifications, always visible
        return [{"type": "notice", "mode": "list", "x": int(x), "y": int(y), "w": max(1, int(w)), "h": max(1, int(h)),
                 "rows": o["rows"], "idle_text": o["idle_text"], "align": o["align"], "size": max(12, min(18, int(h / 4.2))), "font": c.font,
                 "font_bold": c.bold, "color": th["text"], "muted": th["muted"], "accent": th["accent"], "interval": 1}]
    if module == "visualizador":  # just the spectrum, as a card of its own
        return [_viz_widget(c, o, x, y, w, h, _module_color(c, module, o))]
    if module == "musica":
        return _build_music(c, o, x, y, w, h, _module_color(c, module, o))
    col = _module_color(c, module, o)
    style = o.get("bar_style", "tema")
    stat = dict(color=col, show_bar=o.get("show_bar", False), show_graph=o.get("show_graph", False), align=o.get("align", "padrao"),
                radial=(th["bar_style"] if style == "tema" else style) == "radial")
    if module == "cpu":
        return _stat(c, x, y, w, h, label=o["label"], value="{cpu:.0f}%", sample="100%",
                     sub="{cpu_temp:.0f} °C" if o["show_sub"] else None, sub_sample="88 °C",
                     bar="cpu", graph="cpu", **stat)
    if module == "gpu":
        return _stat(c, x, y, w, h, label=o["label"], value="{gpu:.0f}%", sample="100%",
                     sub="{gpu_temp:.0f} °C" if o["show_sub"] else None, sub_sample="88 °C",
                     bar="gpu", graph="gpu", **stat)
    if module in ("cpu_temp", "gpu_temp"):
        m = module
        return _stat(c, x, y, w, h, label=o["label"], value="{%s:.0f} °C" % m, sample="88 °C",
                     bar=m, bar_range=(20, 100), warn_at=80, graph=m, **stat)
    if module == "vram":
        return _stat(c, x, y, w, h, label=o["label"], value="{gpu_mem:.0f}%", sample="100%",
                     sub="{gpu_mem_used_gb:.1f} / {gpu_mem_total_gb:.0f} GB", sub_sample="11,9 / 12 GB", sub_color=th["text"],
                     bar="gpu_mem", graph="gpu_mem", **stat)
    if module == "ram":
        return _stat(c, x, y, w, h, label=o["label"], value="{ram:.0f}%", sample="100%",
                     sub="{ram_used_gb:.1f} / {ram_total_gb:.0f} GB", sub_sample="31,9 / 32 GB", sub_color=th["text"],
                     bar="ram", graph="ram", **stat)
    if module == "disk":
        return _stat(c, x, y, w, h, label=o["label"], value="{disk:.0f}%", sample="100%",
                     bar="disk", graph="disk", **stat)
    if module in ("net_down", "net_up"):
        k = "net_down" if module == "net_down" else "net_up"
        return _stat(c, x, y, w, h, label=o["label"], value="{%s_h}" % k, sample="999,9 MB/s",
                     graph=k + "_kbs", **stat)
    if module == "net":
        gap = 12
        half = (w - gap) / 2
        left = _stat(c, x, y, half, h, label="↓ Download", value="{net_down_h}", sample="999,9 MB/s",
                     graph="net_down_kbs", color=col if o["color"] else ("#4dabf7" if th["colorful"] else th["accent"]),
                     show_bar=False, show_graph=o["show_graph"], align=o["align"])
        right = _stat(c, x + half + gap, y, half, h, label="↑ Upload", value="{net_up_h}", sample="999,9 MB/s",
                      graph="net_up_kbs", color=col if o["color"] else ("#35c46d" if th["colorful"] else th["accent"]),
                      show_bar=False, show_graph=o["show_graph"], align=o["align"])
        return left + right
    if module == "clock":
        size = fit_size(c.bold, "00:00:00" if o["format"].endswith("%S") else "00:00", w, h * 0.95, hi=90)
        wd = {"type": "clock", "x": int(x), "y": int(y), "w": int(w), "h": int(h), "format": o["format"],
              "size": size, "font": c.bold, "color": col, "align": o["align"], "valign": "middle", "interval": 1}
        return [wd]
    if module == "date":
        st, al = o["style"], o["align"]
        two = st == "completo" and h >= 52
        if st == "completo" and not two:
            st = "semana_curto"
        if two:
            h1 = h * 0.52
            wd_names, wd_short, mo_names, mo_short = date_names()
            s1 = fit_size(c.font, _widest(c.font, [d.capitalize() for d in wd_names]), w, h1 * 0.9, hi=30)
            s2 = _fit_long_date(c, w, (h - h1) * 0.9, 24)
            top = _text(c, x, y, w, h1, "{dia_semana_cap}", s1, th["text"] if not o["color"] else col, al, interval=60)
            bottom = _text(c, x, y + h1, w, h - h1, _LONG_DATE[i18n.lang()], s2, th["muted"] if not o["color"] else col, al, interval=60)
            top["fit"] = bottom["fit"] = True
            return [top, bottom]
        wd_names, wd_short, mo_names, mo_short = date_names()
        en = i18n.lang() == "en"
        tpl, sample = {
            "extenso": (_LONG_DATE[i18n.lang()], "00 de fevereiro de 2026"),
            "curto": ("{now:%m/%d/%Y}" if en else "{now:%d/%m/%Y}", "00/00/0000"),
            "semana_curto": ("{dia_semana_curto}, {mes_curto} {dia}" if en else "{dia_semana_curto}, {dia} {mes_curto}", "qua, 28 set"),
        }[st]
        if st == "extenso":
            size = _fit_long_date(c, w, h * 0.9, 30)
        elif st == "semana_curto":
            wide = _widest(c.font, [f"{d}, {m} 00" if en else f"{d}, 00 {m}" for d in wd_short for m in mo_short])
            size = fit_size(c.font, wide, w, h * 0.9, hi=30)
        else:
            size = fit_size(c.font, sample, w, h * 0.9, hi=30)
        wd = _text(c, x, y, w, h, tpl, size, col, al, interval=60)
        wd["fit"] = True
        return [wd]
    if module == "text":
        size = o["size"] or fit_size(c.bold, o["text"] or " ", w, h * 0.95, hi=48)
        d = _text(c, x, y, w, h, o["text"], size, col, o["align"], bold=True)
        d["wrap"] = True
        return [d]
    if module == "image":
        if not o["image"]:
            return []
        return [{"type": "image", "x": int(x), "y": int(y), "w": int(w), "h": int(h),
                 "path": f"media/{o['image']}", "fit": o["fit"]}]
    return []


def slot_widgets(slot: dict, c: _Ctx) -> list[dict]:
    th = c.th
    x, y, w, h = slot["col"] * CELL, slot["row"] * CELL, slot["w"] * CELL, slot["h"] * CELL
    o = slot["options"]
    use_card = {"sim": True, "nao": False}.get(o.get("card"), th["card"]["enabled"])
    out = []
    pad = 4
    if use_card and slot["module"] != "image":
        card = th["card"]
        out.append({"type": "rect", "x": x + 2, "y": y + 2, "w": w - 4, "h": h - 4, "radius": card["radius"],
                    "fill": _rgba(card["color"], card["opacity"])})
        pad = 10
    if slot["module"] == "image":
        pad = 0
    px, py = x + pad, y + pad
    pw, ph = w - 2 * pad, h - 2 * pad
    out += _build_module(c, slot["module"], o, px, py, pw, ph)
    if o.get("notify") and slot["module"] != "notificacao":
        # drawn last, so it covers the card while a notification is fresh and is invisible otherwise
        out.append({"type": "notice", "mode": "alert", "x": x + 2, "y": y + 2, "w": max(1, w - 4), "h": max(1, h - 4),
                    "size": max(12, min(18, int(h / 6.5))), "font": c.font, "font_bold": c.bold, "color": th["text"],
                    "muted": th["muted"], "accent": th["accent"], "fill": th["card"]["color"],
                    "radius": th["card"]["radius"], "interval": 0.5,
                    "align": o.get("align") if o.get("align") in ("left", "center", "right") else "left"})
    return out


def to_config(layout: dict, home: Path) -> dict:
    """Layout -> engine configuration (pages of absolute-positioned widgets)."""
    lay = normalize(layout, home)
    th, dev = lay["theme"], lay["device"]
    c = _Ctx(th, dev)
    bg = th["background"]
    pages = []
    for pg in lay["pages"]:
        widgets = []
        for slot in pg["slots"]:
            if not slot["hidden"]:  # hidden modules stay in the layout but are not drawn
                widgets += slot_widgets(slot, c)
        page = {"duration": pg["duration"], "widget": widgets, "background_color": bg["color"],
                "background": f"media/{bg['image']}" if bg["image"] else bg["color"],
                "background_dim": bg["dim"], "background_fit": bg["fit"]}
        pages.append(page)
    return {
        "device": {"type": "rev_a", "port": dev["port"], "orientation": dev["orientation"],
                   "brightness": dev["brightness"], "fps": dev["fps"], "invert_brightness": dev["invert_brightness"],
                   "align": dev["align"], "stability": dev["stability"], "rotate": dev["rotate"]},
        "notifications": {"enabled": dev["notify"], "seconds": dev["notify_seconds"], "apps": dev["notify_apps"],
                          "show_text": dev["notify_text"]},
        "sensors": lay["sensors"],
        "display": {"background": bg["color"], "decimal": "," if th["decimal_comma"] and i18n.lang() == "pt" else "."},
        "page": pages,
        "_base_dir": Path(home),
    }


def _t_spec(sp: dict) -> dict:
    sp = dict(sp)
    sp["label"] = i18n.t(sp["label"])
    if sp.get("hint"):
        sp["hint"] = i18n.t(sp["hint"])
    if sp.get("choices"):
        sp["choices"] = [[c[0], i18n.t(c[1])] for c in sp["choices"]]
    if sp.get("kind") == "text" and isinstance(sp.get("default"), str):
        sp["default_pt"] = sp["default"]       # layouts store defaults as Portuguese; the editor shows them translated
        sp["default"] = i18n.t(sp["default"])  # e.g. "Nada tocando" -> "Nothing playing" (typed text is stored, never translated)
    return sp


def catalog() -> dict:
    """Everything the UI needs to build its forms, in the interface language."""
    return {
        "modules": [{"id": k, "label": i18n.t(v["label"]), "group": i18n.t(v["group"]), "size": list(v["size"]),
                     "options": [_t_spec(sp) for sp in v["options"]]} for k, v in MODULES.items()],
        "common_options": [_t_spec(sp) for sp in COMMON_OPTIONS],
        "beta_group": i18n.t(BETA_GROUP),
        "fonts": list(FONTS),
        "rotations": [[k, i18n.t(v)] for k, v in ROTATIONS],
        "templates": [[k, i18n.t(v)] for k, v in TEMPLATES.items()],
        "cell": CELL,
    }
