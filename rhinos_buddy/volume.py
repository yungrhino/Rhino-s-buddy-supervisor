"""The Windows master volume (what the speaker icon in the taskbar shows), for the music card.

No extra package: it talks to the Core Audio ``IAudioEndpointVolume`` interface of the default playback device
through ``ctypes``.  Anything that goes wrong (not Windows, no device, COM error) simply means "unknown" (None).
"""

from __future__ import annotations

import logging
import sys
import threading
import time

log = logging.getLogger("rhinos_buddy.volume")

CACHE_SECONDS = 0.4  # the card asks several times a second; Windows is asked at most this often


def percent(scalar: float) -> int:
    """0.0-1.0 -> whole percent, the way Windows rounds it for its own volume slider."""
    return max(0, min(100, int(round(float(scalar) * 100))))


def _read_windows() -> tuple[int, bool] | None:
    import ctypes
    from ctypes import POINTER, byref, c_float, c_int, c_void_p, c_ulong, windll
    from ctypes import wintypes

    class GUID(ctypes.Structure):
        _fields_ = [("a", wintypes.DWORD), ("b", wintypes.WORD), ("c", wintypes.WORD), ("d", ctypes.c_ubyte * 8)]

    def guid(s: str) -> GUID:
        import uuid

        u = uuid.UUID(s)
        g = GUID()
        g.a, g.b, g.c = u.time_low, u.time_mid, u.time_hi_version
        for i, byte in enumerate(u.bytes[8:]):
            g.d[i] = byte
        return g

    CLSID_ENUM = guid("BCDE0395-E52F-467C-8E3D-C4579291692E")
    IID_ENUM = guid("A95664D2-9614-4F35-A746-DE8DB63617E6")
    IID_VOL = guid("5CDF2C82-841E-4546-9722-0CF74078229A")

    def method(obj, index, *argtypes):
        vtbl = ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))
        return ctypes.WINFUNCTYPE(ctypes.HRESULT, c_void_p, *argtypes)(vtbl[index])

    def release(obj):
        if obj:
            vtbl = ctypes.cast(ctypes.cast(obj, POINTER(c_void_p))[0], POINTER(c_void_p))
            ctypes.WINFUNCTYPE(c_ulong, c_void_p)(vtbl[2])(obj)

    windll.ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED; "already initialised" (S_FALSE) is fine
    enum = c_void_p()
    windll.ole32.CoCreateInstance(byref(CLSID_ENUM), None, 1 | 4, byref(IID_ENUM), byref(enum))  # INPROC | LOCAL
    if not enum:
        return None
    dev, vol = c_void_p(), c_void_p()
    try:
        method(enum, 4, c_int, c_int, POINTER(c_void_p))(enum, 0, 1, byref(dev))     # GetDefaultAudioEndpoint(eRender, eMultimedia)
        method(dev, 3, POINTER(GUID), wintypes.DWORD, c_void_p, POINTER(c_void_p))(dev, byref(IID_VOL), 23, None, byref(vol))  # Activate
        level, muted = c_float(), wintypes.BOOL()
        method(vol, 9, POINTER(c_float))(vol, byref(level))                          # GetMasterVolumeLevelScalar
        method(vol, 15, POINTER(wintypes.BOOL))(vol, byref(muted))                   # GetMute
        return percent(level.value), bool(muted.value)
    finally:
        release(vol)
        release(dev)
        release(enum)


class Volume:
    """Cached reader.  ``get()`` -> ``(percent, muted)`` or None when it cannot be read."""

    def __init__(self, reader=None, clock=time.monotonic):
        self._reader = reader or (_read_windows if sys.platform == "win32" else (lambda: None))
        self._clock = clock
        self._at = -1e9
        self._value: tuple[int, bool] | None = None
        self._warned = False
        self._lock = threading.Lock()

    def get(self) -> tuple[int, bool] | None:
        with self._lock:
            now = self._clock()
            if now - self._at >= CACHE_SECONDS:
                self._at = now
                try:
                    self._value = self._reader()
                except Exception as e:
                    self._value = None
                    if not self._warned:
                        self._warned = True
                        log.warning("could not read the system volume: %s", e)
            return self._value


_default: Volume | None = None


def get_volume() -> Volume:
    global _default
    if _default is None:
        _default = Volume()
    return _default
