"""Reune os textos de licença das bibliotecas instaladas, para distribuir junto do .exe.

As licenças BSD/MIT/HPND das dependências exigem que o aviso de copyright e o texto da licença
acompanhem as cópias binárias.  Uso (depois de instalar as dependências e gerar o executável):

    python tools/collect_licenses.py dist/RhinosBuddySupervisor

Grava ``THIRD_PARTY_LICENSES.txt`` e copia ``LICENSE`` e ``THIRD_PARTY_NOTICES.md`` para a pasta.
"""

from __future__ import annotations

import importlib.metadata as md
import re
import shutil
import sys
from pathlib import Path

PACKAGES = [
    "pyserial", "Pillow", "numpy", "psutil",                      # obrigatórias
    "soundcard", "winrt-runtime", "winrt-Windows.Foundation",       # módulo Música (opcionais)
    "winrt-Windows.Foundation.Collections", "winrt-Windows.Storage.Streams", "winrt-Windows.Media.Control",
]
_LICENSE_FILE = re.compile(r"(^|/)(licen[cs]e|copying|notice|authors)[^/]*$", re.I)


def license_texts(dist: md.Distribution) -> list[tuple[str, str]]:
    out, seen = [], set()
    for f in dist.files or []:
        if _LICENSE_FILE.search(str(f).replace("\\", "/")):
            try:
                text = Path(dist.locate_file(f)).read_text("utf-8", errors="replace").strip()
            except OSError:
                continue
            if text and text not in seen:  # wheels often repeat the same text
                seen.add(text)
                out.append((str(f), text))
    return out


def collect(names: list[str] | None = None) -> tuple[str, list[str]]:
    """Returns (text, missing_package_names)."""
    parts, missing = [], []
    for name in names or PACKAGES:
        try:
            dist = md.distribution(name)
        except md.PackageNotFoundError:
            missing.append(name)
            continue
        meta = dist.metadata
        lic = meta.get("License-Expression") or meta.get("License") or "ver textos abaixo"
        parts.append("=" * 78 + f"\n{meta.get('Name', name)} {dist.version}  -  {str(lic).splitlines()[0][:100]}\n" + "=" * 78)
        texts = license_texts(dist)
        parts += [f"--- {fname} ---\n{text}" for fname, text in texts] or ["(o pacote não inclui arquivo de licença; consulte a página dele no PyPI)"]
    return "\n\n".join(parts) + "\n", missing


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python tools/collect_licenses.py <pasta do executavel>", file=sys.stderr)
        return 2
    dest, root = Path(argv[0]), Path(__file__).resolve().parent.parent
    dest.mkdir(parents=True, exist_ok=True)
    text, missing = collect()
    (dest / "THIRD_PARTY_LICENSES.txt").write_text(text, "utf-8")
    for name in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copy2(root / name, dest / name)
    print(f"Licenças gravadas em {dest}")
    if missing:
        print("Não instalados (ignorados): " + ", ".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
