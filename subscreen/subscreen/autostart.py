"""Start with Windows: a value in HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.

Per-user, needs no administrator rights, and is exactly what Task Manager's "Startup apps" tab lists.
"""

from __future__ import annotations

import sys
from pathlib import Path, PureWindowsPath

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Subscreen"


def supported() -> bool:
    return sys.platform == "win32"


def command_line(frozen: bool | None = None, executable: str | None = None, script: str | None = None) -> str:
    """Command Windows runs at login.  Always starts hidden in the background (--background)."""
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    exe = executable or sys.executable
    if frozen:  # PyInstaller build: the .exe itself
        return f'"{exe}" --background'
    # running from source: use pythonw.exe (no console window)
    p = PureWindowsPath(exe) if ("\\" in exe or exe[1:2] == ":") else Path(exe)
    pyw = p.with_name("pythonw.exe") if p.name.lower() == "python.exe" else p
    script = script or str(Path(__file__).resolve().parent.parent / "run_app.py")
    return f'"{pyw}" "{script}" --background'


def _winreg():
    import winreg  # noqa: PLC0415 - only exists on Windows

    return winreg


def is_enabled() -> bool:
    if not supported():
        return False
    wr = _winreg()
    try:
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_READ) as k:
            wr.QueryValueEx(k, VALUE_NAME)
        return True
    except OSError:
        return False


def set_enabled(enabled: bool) -> None:
    if not supported():
        raise RuntimeError("Iniciar com o Windows só está disponível no Windows.")
    wr = _winreg()
    with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
        if enabled:
            wr.SetValueEx(k, VALUE_NAME, 0, wr.REG_SZ, command_line())
        else:
            try:
                wr.DeleteValue(k, VALUE_NAME)
            except FileNotFoundError:
                pass
