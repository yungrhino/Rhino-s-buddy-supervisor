"""What is playing right now (title, artist), for the music module.

Sources, tried in order (all optional, none of them touches the player):

1. Windows "media session" (the same info the volume flyout shows): works for Spotify, YouTube Music
   and most players/browsers.  Needs the ``winrt-Windows.Media.Control`` package.
2. Fallback without packages: the Spotify desktop window title ("Artist - Song").

Nothing playing -> an empty dict.  Reading is done on a background thread every few seconds and only
while a music module with the track line is on the visible page.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

log = logging.getLogger("rhinos_buddy.nowplaying")

POLL_SECONDS = 2.0
IDLE_SECONDS = 8.0
_SPOTIFY_IDLE = ("spotify", "spotify free", "spotify premium")


def parse_spotify_title(title: str) -> dict:
    """The Spotify window title is 'Artist - Song' while playing and 'Spotify...' otherwise."""
    t = (title or "").strip()
    if not t or t.lower() in _SPOTIFY_IDLE or " - " not in t:
        return {}
    artist, song = t.split(" - ", 1)
    return {"title": song.strip(), "artist": artist.strip(), "app": "Spotify", "playing": True}


def _winrt_fetch() -> dict:
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )
    except ImportError:
        from winsdk.windows.media.control import (  # older projection, same API
            GlobalSystemMediaTransportControlsSessionManager as Manager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as Status,
        )
    import asyncio

    async def go() -> dict:
        mgr = await Manager.request_async()
        ses = mgr.get_current_session()
        if ses is None:
            return {}
        props = await ses.try_get_media_properties_async()
        playing = ses.get_playback_info().playback_status == Status.PLAYING
        if not playing or not (props.title or props.artist):
            return {}
        app = (ses.source_app_user_model_id or "").split("!")[0].replace(".exe", "")
        out = {"title": props.title or "", "artist": props.artist or "", "app": app, "playing": True}
        try:  # progress: position/length of the track (not every player reports them)
            tl = ses.get_timeline_properties()
            pos, end = tl.position.total_seconds(), (tl.end_time - tl.start_time).total_seconds()
            if end > 1:
                out["position"], out["duration"] = max(0.0, min(pos, end)), end
        except Exception as e:
            log.debug("timeline unavailable: %s", e)
        key = (out["title"], out["artist"])
        if key not in _art_cache:  # album cover, read once per track
            _art_cache.clear()
            _art_cache[key] = await _read_thumbnail(props)
        if _art_cache[key]:
            out["art"] = _art_cache[key]
        return out

    return asyncio.run(go())


_art_cache: dict = {}


async def _read_thumbnail(props) -> bytes:
    """Cover image bytes (JPEG/PNG) from the media session, or b'' when there is none."""
    try:
        ref = props.thumbnail
        if ref is None:
            return b""
        from winrt.windows.storage.streams import DataReader

        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0 or size > 8_000_000:
            return b""
        reader = DataReader(stream)
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        return bytes(buf)
    except Exception as e:
        log.debug("cover unavailable: %s", e)
        return b""


def _spotify_window_fetch() -> dict:
    if sys.platform != "win32":
        return {}
    import ctypes
    from ctypes import wintypes

    import psutil

    user32 = ctypes.windll.user32
    found: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            try:
                if psutil.Process(pid.value).name().lower() == "spotify.exe":
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    found.append(buf.value)
            except Exception:
                pass
        return True

    user32.EnumWindows(cb, 0)
    for t in found:
        r = parse_spotify_title(t)
        if r:
            return r
    return {}


def default_fetch() -> dict:
    try:
        return _winrt_fetch()
    except ImportError:
        pass
    except Exception as e:
        log.debug("media session read failed: %s", e)
    try:
        return _spotify_window_fetch()
    except Exception as e:
        log.debug("window title read failed: %s", e)
        return {}


class NowPlaying:
    def __init__(self, fetch=None, poll: float = POLL_SECONDS):
        self.fetch = fetch or default_fetch
        self.poll = poll
        self.data: dict = {}
        self.last_touch = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.clock = time.monotonic

    def get(self) -> dict:
        self.last_touch = self.clock()
        if self._thread is None or not self._thread.is_alive():
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="nowplaying", daemon=True)
            self._thread.start()
        return self.data

    def poll_once(self) -> None:
        try:
            data = dict(self.fetch() or {})
            data["fetched_at"] = self.clock()  # lets the widget advance the progress between polls
            self.data = data if data.get("playing") else {}
        except Exception as e:
            log.debug("now playing fetch failed: %s", e)
            self.data = {}

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.clock() - self.last_touch <= IDLE_SECONDS:
                self.poll_once()
            self._stop.wait(self.poll)

    def stop(self) -> None:
        self._stop.set()


_instance: NowPlaying | None = None
_lock = threading.Lock()


def get_nowplaying() -> NowPlaying:
    global _instance
    with _lock:
        if _instance is None:
            _instance = NowPlaying()
        return _instance


def shutdown() -> None:
    if _instance is not None:
        _instance.stop()
