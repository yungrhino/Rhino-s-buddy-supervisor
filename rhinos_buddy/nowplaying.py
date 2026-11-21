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


FRESH_AGE = 5.0  # a position stamped less than this long ago is trusted as "the player just told us"


def timeline_age(last_updated, now=None) -> float | None:
    """Seconds since Windows took the position snapshot, or None when the stamp cannot be trusted
    (missing, in another time zone, from the future, absurdly old)."""
    if last_updated is None:
        return None
    try:
        from datetime import datetime, timezone

        if getattr(last_updated, "tzinfo", None) is None:   # naive stamp: assume the PC's local clock
            age = ((now or datetime.now()) - last_updated).total_seconds()
        else:
            age = ((now or datetime.now(timezone.utc)) - last_updated).total_seconds()
    except Exception:
        return None
    if -2.0 <= age < 0:
        return 0.0   # small clock skew
    return age if 0 <= age <= 6 * 3600.0 else None


def pick_order(current, sessions) -> list:
    """Sessions to look at, the system's current one first, then the others (no duplicates, same-object test)."""
    out = [current] if current is not None else []
    for s in sessions or []:
        if s is not None and not any(s is o for o in out):
            out.append(s)
    return out


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
        sessions = []
        try:
            sessions = list(mgr.get_sessions())
        except Exception as e:
            log.debug("session list unavailable: %s", e)
        ses = props = info = None
        cur = mgr.get_current_session()
        # The "current" session is only the one Windows last favoured: a paused player (or another browser tab) can
        # hold that spot while a browser plays YouTube.  So look at all of them and take one that is really playing.
        for cand in pick_order(cur, sessions):
            try:
                cand_info = cand.get_playback_info()
                if cand_info.playback_status != Status.PLAYING:
                    continue
                cand_props = await cand.try_get_media_properties_async()
            except Exception as e:
                log.debug("session skipped: %s", e)
                continue
            if cand_props.title or cand_props.artist:
                ses, props, info = cand, cand_props, cand_info
                break
        if ses is None:
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
                stamp = tl.last_updated_time
                out["position"] = max(0.0, min(pos, end))            # the snapshot, exactly as the player reported it
                out["duration"] = end
                out["pos_age"] = timeline_age(stamp)                 # how old that snapshot is (None: unknown)
                out["pos_rate"] = rate if rate > 0 else 1.0
                try:
                    out["pos_sig"] = (round(pos, 2), stamp.timestamp())  # changes only when the player publishes a new one
                except Exception:
                    out["pos_sig"] = (round(pos, 2), None)
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
        log.warning("media session read failed: %s", e)
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
        self.error = ""
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
                try:
                    data = self._smooth(self.data, data)
                except Exception:
                    # never lose the track because the progress smoothing choked on odd player data
                    log.warning("progress smoothing failed; showing the raw reading", exc_info=True)
                    for k in ("pos_age", "pos_rate", "pos_sig", "position", "duration"):
                        data.pop(k, None)
            self.data = data if data.get("playing") else {}
            self.error = ""
        except Exception as e:
            self.error = f"{type(e).__name__}: {e}"
            if self.error != getattr(self, "_logged_error", None):
                self._logged_error = self.error
                log.warning("now playing fetch failed: %s", self.error)
            self.data = {}

    SEEK_TOLERANCE = 2.0   # seconds: a bigger difference than this is a real seek, not reading noise
    BLIND_TOLERANCE = 5.0  # same, when the snapshot has no usable timestamp (it may simply be old)

    def _smooth(self, prev: dict, new: dict) -> dict:
        """Turn the player's coarse snapshots into a steady counter.

        Between polls the widget runs its own clock from ``position`` + ``fetched_at``.  A new reading only moves
        that clock when the player really published something new (``pos_sig`` changed), and then only by the
        small difference - unless it is a seek (big jump) or a new track.  Re-reading the same stale snapshot
        never touches the counter."""
        age, rate = new.pop("pos_age", None), new.pop("pos_rate", 1.0) or 1.0
        if "position" not in new:
            return new
        raw = new["position"]
        fresh = raw + age * rate if age is not None and age <= FRESH_AGE else None
        dur = new.get("duration") or 1e9
        same_track = (prev and "position" in prev and (prev.get("title"), prev.get("artist")) == (new.get("title"), new.get("artist")))
        if not same_track:
            guess = fresh if fresh is not None else (raw + age * rate if age is not None and 0 < age < dur else raw)
            new["position"] = max(0.0, min(guess, dur))
            return new
        predicted = min(prev["position"] + max(0.0, new["fetched_at"] - prev.get("fetched_at", new["fetched_at"])) * rate, dur)
        sig = new.get("pos_sig")
        if sig is not None and sig == prev.get("pos_sig"):
            new["position"] = predicted           # the same old snapshot again: nothing new, keep counting
            return new
        cand = fresh if fresh is not None else raw
        delta = cand - predicted
        tol = self.SEEK_TOLERANCE if fresh is not None else self.BLIND_TOLERANCE
        if abs(delta) > tol:
            new["position"] = max(0.0, min(cand, dur))  # the user seeked (or the track restarted)
        else:
            new["position"] = predicted + (delta * 0.3 if delta > 0 else delta * 0.05)
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
