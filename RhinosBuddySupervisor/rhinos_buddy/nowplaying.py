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


def timeline_position(position: float, end: float, last_updated, now, rate: float = 1.0) -> float:
    """Where the track really is *now*.

    Windows reports the position as a snapshot taken at ``last_updated`` (players only refresh it every few
    seconds, or when you seek/pause), so the time elapsed since then must be added; otherwise the counter is
    always a bit behind and jumps every time it is re-read.
    """
    elapsed = 0.0
    if last_updated is not None:
        try:
            if getattr(last_updated, "tzinfo", None) is None and getattr(now, "tzinfo", None) is not None:
                last_updated = last_updated.replace(tzinfo=now.tzinfo)
            elapsed = (now - last_updated).total_seconds()
        except Exception:
            elapsed = 0.0
    elapsed = max(0.0, min(elapsed, 6 * 3600.0))  # a clock that went backwards / absurd stamps are ignored
    pos = position + elapsed * (rate if rate and rate > 0 else 1.0)
    return max(0.0, min(pos, end))


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
        info = ses.get_playback_info()
        playing = info.playback_status == Status.PLAYING
        if not playing or not (props.title or props.artist):
            return {}
        app = (ses.source_app_user_model_id or "").split("!")[0].replace(".exe", "")
        out = {"title": props.title or "", "artist": props.artist or "", "app": app, "playing": True}
        try:  # progress: position/length of the track (not every player reports them)
            tl = ses.get_timeline_properties()
            pos, end = (tl.position - tl.start_time).total_seconds(), (tl.end_time - tl.start_time).total_seconds()
            if end > 1:
                try:
                    rate = float(info.playback_rate) if info.playback_rate is not None else 1.0
                except Exception:
                    rate = 1.0
                from datetime import datetime, timezone

                out["position"] = timeline_position(pos, end, tl.last_updated_time, datetime.now(timezone.utc), rate)
                out["duration"] = end
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
            if data.get("playing"):
                data = self._smooth(self.data, data)
            self.data = data if data.get("playing") else {}
        except Exception as e:
            log.debug("now playing fetch failed: %s", e)
            self.data = {}

    SEEK_TOLERANCE = 2.0  # seconds: a bigger difference than this is a real seek, not reading noise

    def _smooth(self, prev: dict, new: dict) -> dict:
        """Keep the counter steady between polls: small disagreements with what we already extrapolated are
        mostly noise from the player (it reports its position in coarse steps), so they are only nudged in."""
        if (not prev or "position" not in prev or "position" not in new
                or (prev.get("title"), prev.get("artist")) != (new.get("title"), new.get("artist"))):
            return new
        predicted = prev["position"] + max(0.0, new["fetched_at"] - prev.get("fetched_at", new["fetched_at"]))
        predicted = min(predicted, new.get("duration") or predicted)
        delta = new["position"] - predicted
        if abs(delta) > self.SEEK_TOLERANCE:
            return new  # the user seeked (or the track restarted)
        new["position"] = predicted + (delta * 0.3 if delta > 0 else delta * 0.05)  # almost never goes backwards
        return new

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
