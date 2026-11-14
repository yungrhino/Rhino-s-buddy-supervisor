"""Where the app keeps its files: layout.json and the uploaded pictures (media/)."""

from __future__ import annotations

import json
import os
import re
import sys
import uuid
from pathlib import Path

from . import layout as L

MAX_MEDIA_BYTES = 25 * 1024 * 1024
MEDIA_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}


def app_home() -> Path:
    """%APPDATA%\\Subscreen on Windows, ~/.config/subscreen elsewhere (override: SUBSCREEN_HOME)."""
    env = os.environ.get("SUBSCREEN_HOME")
    if env:
        home = Path(env)
    elif sys.platform == "win32":
        home = Path(os.environ.get("APPDATA", Path.home())) / "Subscreen"
    else:
        home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "subscreen"
    (home / "media").mkdir(parents=True, exist_ok=True)
    return home


def load_layout(home: Path) -> dict:
    f = Path(home) / "layout.json"
    try:
        raw = json.loads(f.read_text("utf-8"))
    except (OSError, ValueError):
        raw = {}
    return L.normalize(raw, home)


def save_layout(home: Path, layout: dict) -> None:
    f = Path(home) / "layout.json"
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(layout, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(f)  # atomic: a crash never leaves a half-written file


def save_media(home: Path, filename: str, data: bytes) -> str:
    """Store an uploaded picture; returns the safe stored name (only images, size-limited)."""
    ext = Path(filename or "").suffix.lower()
    if ext not in MEDIA_EXT:
        raise ValueError("Formato não suportado (use PNG, JPG, GIF, WebP ou BMP).")
    if len(data) > MAX_MEDIA_BYTES:
        raise ValueError("Arquivo muito grande (máximo 25 MB).")
    from io import BytesIO

    from PIL import Image

    try:
        with Image.open(BytesIO(data)) as im:
            im.verify()  # really an image, not just a renamed file
    except Exception:
        raise ValueError("O arquivo não é uma imagem válida.") from None
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", Path(filename).stem)[:40].strip("_") or "imagem"
    name = f"{stem}-{uuid.uuid4().hex[:6]}{ext}"
    (Path(home) / "media").mkdir(parents=True, exist_ok=True)
    (Path(home) / "media" / name).write_bytes(data)
    return name


def list_media(home: Path) -> list[str]:
    d = Path(home) / "media"
    if not d.is_dir():
        return []
    return sorted(p.name for p in d.iterdir() if p.suffix.lower() in MEDIA_EXT)
