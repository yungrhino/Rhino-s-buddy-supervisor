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
    """%APPDATA%\\RhinosBuddySupervisor on Windows, ~/.config/rhinos-buddy-supervisor elsewhere (override: RHINOS_BUDDY_HOME)."""
    env = os.environ.get("RHINOS_BUDDY_HOME")
    if env:
        home = Path(env)
    elif sys.platform == "win32":
        home = Path(os.environ.get("APPDATA", Path.home())) / "RhinosBuddySupervisor"
    else:
        home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "rhinos-buddy-supervisor"
    (home / "media").mkdir(parents=True, exist_ok=True)
    return home


def legacy_homes() -> list[Path]:
    """Where the app kept its files before it was renamed (it was called "Subscreen")."""
    if sys.platform == "win32":
        return [Path(os.environ.get("APPDATA", Path.home())) / "Subscreen"]
    return [Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "subscreen"]


def migrate_legacy_home(home: Path, candidates: list[Path] | None = None) -> bool:
    """First run after the rename: copy the old layout and pictures so nothing is lost.

    Copies (never moves) and only when the new folder has no layout yet; returns True if it copied."""
    import shutil

    home = Path(home)
    if (home / "layout.json").exists():
        return False
    for old in (candidates if candidates is not None else legacy_homes()):
        if (old / "layout.json").is_file() and old.resolve() != home.resolve():
            try:
                shutil.copy2(old / "layout.json", home / "layout.json")
                if (old / "media").is_dir():
                    shutil.copytree(old / "media", home / "media", dirs_exist_ok=True)
                return True
            except OSError:
                return False
    return False


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


# ---- small interface preferences (not part of the screen layout): which release notes were seen, theme...
PREFS_FILE = "ui.json"


def load_prefs(home: Path) -> dict:
    try:
        raw = json.loads((Path(home) / PREFS_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        raw = {}
    raw = raw if isinstance(raw, dict) else {}
    seen = raw.get("seen_version")
    return {"seen_version": seen if isinstance(seen, str) and len(seen) <= 32 else "",
            "hide_notes": raw.get("hide_notes") is True,
            "lang": raw.get("lang") if raw.get("lang") in ("pt", "en") else "pt",
            "lang_chosen": raw.get("lang_chosen") is True}


def save_prefs(home: Path, prefs: dict) -> dict:
    clean = {"seen_version": str(prefs.get("seen_version") or "")[:32], "hide_notes": prefs.get("hide_notes") is True,
             "lang": prefs.get("lang") if prefs.get("lang") in ("pt", "en") else "pt",
             "lang_chosen": prefs.get("lang_chosen") is True}
    f = Path(home) / PREFS_FILE
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(clean, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(f)
    return clean
