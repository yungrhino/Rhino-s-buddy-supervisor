"""Notifications for the screen: "you got a WhatsApp message" over any card for a few seconds.

Where the notifications come from (all optional, all read-only, nothing is ever sent anywhere):

1. **Windows notification center** (the toasts that pop up at the corner of the screen: WhatsApp Web in the
   browser, Discord, Telegram, e-mail...).  Needs the ``winrt-*`` packages and the Windows permission
   *Settings > Privacy > Notifications > "Allow apps to access your notifications"*.
2. Fallback without permission or packages: the unread counter that web apps put in the browser tab title,
   e.g. ``(3) WhatsApp``.  It only sees the tab that is currently visible and cannot tell who wrote.

The feature is **off by default** (notification text can be private).  ``Notifier.configure`` turns it on.
"""

from __future__ import annotations

import logging
import re
import sys
import threading
import time
from collections import deque

log = logging.getLogger("rhinos_buddy.notifications")

POLL_SECONDS = 1.5
HISTORY = 20
# Web apps that show "(3) Name" in the tab / window title when something is unread.
TITLE_APPS = ("WhatsApp", "Telegram", "Discord", "Messenger", "Instagram", "Gmail", "Outlook", "Slack", "Teams")
_TITLE_RE = re.compile(r"^\((\d{1,3})\+?\)\s*(.*)$")


class AccessDenied(Exception):
    """Windows did not allow reading notifications (the user has not enabled the permission)."""


def parse_title_counter(title: str) -> tuple[str, int] | None:
    """'(3) WhatsApp' -> ('WhatsApp', 3); titles without a counter or from other apps -> None."""
    m = _TITLE_RE.match((title or "").strip())
    if not m:
        return None
    n, rest = int(m.group(1)), m.group(2)
    for app in TITLE_APPS:
        if app.lower() in rest.lower():
            return app, n
    return None


class TitleCounterSource:
    """Turns unread counters in window titles into notification-like items (new id only when the count grows)."""

    def __init__(self, titles=None):
        self.titles = titles or visible_window_titles
        self._state: dict[str, tuple[int, str]] = {}

    def fetch(self) -> list[dict]:
        seen: dict[str, int] = {}
        for t in self.titles():
            parsed = parse_title_counter(t)
            if parsed:
                app, n = parsed
                seen[app] = max(n, seen.get(app, 0))
        out = []
        for app, n in seen.items():
            count, ident = self._state.get(app, (0, f"{app}-{n}"))
            if n > count:
                ident = f"{app}-{n}-{time.monotonic():.3f}"  # it grew: a new message
            self._state[app] = (n, ident)
            out.append({"id": ident, "app": app, "title": "Nova mensagem" if n == 1 else f"{n} mensagens não lidas", "body": ""})
        for app in list(self._state):
            if app not in seen:
                del self._state[app]  # read or closed: next unread counts as new
        return out


def visible_window_titles() -> list[str]:
    if sys.platform != "win32":
        return []
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles: list[str] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        n = user32.GetWindowTextLengthW(hwnd)
        if n and user32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            user32.GetWindowTextW(hwnd, buf, n + 1)
            titles.append(buf.value)
        return True

    user32.EnumWindows(cb, 0)
    return titles


def winrt_toasts() -> list[dict]:
    """Current toasts of the Windows notification center: [{id, app, title, body}]."""
    try:
        from winrt.windows.ui.notifications import KnownNotificationBindings, NotificationKinds
        from winrt.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
    except ImportError:
        from winsdk.windows.ui.notifications import KnownNotificationBindings, NotificationKinds  # older projection
        from winsdk.windows.ui.notifications.management import UserNotificationListener, UserNotificationListenerAccessStatus
    import asyncio

    allowed = UserNotificationListenerAccessStatus.ALLOWED

    async def go() -> list[dict]:
        listener = UserNotificationListener.current
        status = listener.get_access_status()
        if status != allowed:
            status = await listener.request_access_async()
        if status != allowed:
            raise AccessDenied()
        try:
            generic = KnownNotificationBindings.toast_generic
        except AttributeError:
            generic = KnownNotificationBindings.get_toast_generic()
        out = []
        for n in await listener.get_notifications_async(NotificationKinds.TOAST):
            try:
                app = n.app_info.display_info.display_name
            except Exception:
                app = "Notificação"
            texts: list[str] = []
            try:
                binding = n.notification.visual.get_binding(generic)
                texts = [t.text for t in binding.get_text_elements()]
            except Exception:
                pass
            out.append({"id": str(n.id), "app": app or "Notificação", "title": texts[0] if texts else "",
                        "body": " ".join(texts[1:])})
        return out

    return asyncio.run(go())


class Notifier:
    """Keeps the recent notifications and tells widgets which one is "on screen right now"."""

    def __init__(self, fetch=None, clock=time.monotonic, poll: float = POLL_SECONDS):
        self.fetch = fetch          # None: choose Windows toasts, falling back to tab-title counters
        self.clock = clock
        self.poll = poll
        self.enabled = False
        self.apps: list[str] = []   # lower-case filters; empty = every app
        self.seconds = 6.0
        self.show_text = True
        self.history: deque = deque(maxlen=HISTORY)
        self.state = "off"          # off | ok | fallback | denied | error
        self.message = "Notificações desligadas."
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self._baseline = False
        self._counter = 0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._source = None         # "toast" | "title"
        self._titles = TitleCounterSource()

    # ---- configuration
    def configure(self, enabled: bool, apps: str | list[str] = "", seconds: float = 6.0, show_text: bool = True) -> None:
        if isinstance(apps, str):
            apps = apps.split(",")
        with self._lock:
            self.apps = [a.strip().lower() for a in apps if a and a.strip()]
            self.seconds = max(1.0, float(seconds))
            self.show_text = bool(show_text)
            was, self.enabled = self.enabled, bool(enabled)
            if not self.enabled:
                self.state, self.message = "off", "Notificações desligadas."
        if self.enabled and not was:
            self._baseline, self._seen = False, set()  # what is already in the notification center is not "new"
            self.start()
        elif not self.enabled:
            self._stop.set()

    # ---- events
    def _wanted(self, app: str) -> bool:
        return not self.apps or any(a in (app or "").lower() for a in self.apps)

    def push(self, app: str, title: str = "", body: str = "", force: bool = False) -> dict | None:
        """Register a notification.  ``force`` (the "Testar" button) shows it even when the feature is off."""
        if not force and not (self.enabled and self._wanted(app)):
            return None
        if not self.show_text and not force:
            title, body = "Nova notificação", ""
        with self._lock:
            self._counter += 1
            ev = {"id": self._counter, "app": app or "Notificação", "title": title or "", "body": body or "",
                  "t": self.clock(), "forced": bool(force)}
            self.history.appendleft(ev)
        return ev

    def ingest(self, items: list[dict]) -> int:
        """Take a snapshot of a source.  The first one is only a baseline (what is already in the notification
        center is not "new"); afterwards every id that was not there before becomes an event."""
        current = {str(i.get("id")) for i in items}
        new = 0
        if self._baseline:
            for it in items:
                if str(it.get("id")) not in self._seen and self.push(it.get("app", ""), it.get("title", ""), it.get("body", "")):
                    new += 1
        self._seen, self._baseline = current, True
        return new

    def active(self, now: float | None = None) -> dict | None:
        """The newest notification that arrived less than ``seconds`` ago, else None."""
        now = self.clock() if now is None else now
        with self._lock:
            if self.history:
                ev = self.history[0]
                if (self.enabled or ev["forced"]) and now - ev["t"] < self.seconds:
                    return ev
        return None

    def recent(self, n: int = 3) -> list[dict]:
        with self._lock:
            return list(self.history)[:n]

    def status(self) -> dict:
        return {"enabled": self.enabled, "state": self.state, "message": self.message}

    # ---- polling thread
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._stop.clear()
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="notifications", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> None:
        try:
            if self.fetch is not None:  # injected (tests)
                self.ingest(self.fetch())
                self.state, self.message = "ok", "Lendo as notificações."
                return
            if self._source != "title":
                try:
                    items = winrt_toasts()
                    if self._source != "toast":
                        self._source = "toast"
                        self._baseline = False
                    self.state, self.message = "ok", "Lendo as notificações do Windows."
                    self.ingest(items)
                    return
                except AccessDenied:
                    self.state = "denied"
                    self.message = ("O Windows não deixou ler as notificações. Ative em Configurações → Privacidade → "
                                    "Notificações → “Permitir que aplicativos acessem suas notificações”. "
                                    "Enquanto isso, só o contador no título da aba (ex.: “(3) WhatsApp”) é usado.")
                except ImportError:
                    self.state = "fallback"
                    self.message = ("Pacotes de notificação ausentes (veja requirements-extras.txt). "
                                    "Usando só o contador no título da aba, ex.: “(3) WhatsApp”.")
                except Exception as e:
                    self.state, self.message = "error", f"Não foi possível ler as notificações do Windows: {str(e)[:80]}"
                    log.debug("winrt notifications failed: %s", e)
            # fallback: unread counters in window titles
            if self._source != "title":
                self._source, self._baseline = "title", False
            self.ingest(self._titles.fetch())
        except Exception as e:
            log.debug("notification poll failed: %s", e)

    def _run(self) -> None:
        while not self._stop.is_set():
            if self.enabled:
                self.poll_once()
            self._stop.wait(self.poll)


_instance: Notifier | None = None
_lock = threading.Lock()


def get_notifier() -> Notifier:
    global _instance
    with _lock:
        if _instance is None:
            _instance = Notifier()
        return _instance


def shutdown() -> None:
    if _instance is not None:
        _instance.stop()
