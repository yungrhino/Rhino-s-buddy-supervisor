import numpy as np
import pytest
from pathlib import Path

from rhinos_buddy import layout as L, notifications as N
from rhinos_buddy.devices import SimulatorDisplay
from rhinos_buddy.engine import Engine
from rhinos_buddy.metrics import Metrics


class Clock:
    t = 1000.0

    def __call__(self):
        return self.t


def notifier(**kw):
    n = N.Notifier(clock=Clock(), **kw)
    n.start = lambda: None  # no polling thread in unit tests (it would race with the test)
    n.configure(True, "", 6, True)
    return n


# --------------------------------------------------------------------------- the service
def test_first_snapshot_is_only_a_baseline_then_new_items_alert():
    n = notifier()
    old = {"id": "1", "app": "WhatsApp", "title": "Ana", "body": "oi"}
    assert n.ingest([old]) == 0 and n.active() is None          # already in the notification center: not news
    new = {"id": "2", "app": "WhatsApp", "title": "Bia", "body": "e aí?"}
    assert n.ingest([old, new]) == 1
    ev = n.active()
    assert ev["title"] == "Bia" and ev["app"] == "WhatsApp"
    assert n.ingest([old, new]) == 0                            # same snapshot again: no duplicate


def test_alert_expires_after_the_configured_seconds():
    n = notifier()
    n.ingest([])
    n.ingest([{"id": "a", "app": "X", "title": "t"}])
    assert n.active() is not None
    n.clock.t += 5.9
    assert n.active() is not None
    n.clock.t += 0.2
    assert n.active() is None
    assert len(n.recent()) == 1                                  # ... but stays in the history


def test_app_filter_and_privacy_mode():
    n = notifier()
    n.configure(True, "whatsapp, discord", 6, True)
    n.ingest([])
    n.ingest([{"id": "1", "app": "Steam", "title": "Oferta"}, {"id": "2", "app": "WhatsApp Web", "title": "Ana", "body": "segredo"}])
    assert [e["app"] for e in n.recent()] == ["WhatsApp Web"]     # Steam filtered out
    n.configure(True, "", 6, False)                               # hide the message text
    n.ingest([{"id": "3", "app": "WhatsApp Web", "title": "Ana", "body": "segredo 2"}])
    ev = n.recent(1)[0]
    assert ev["title"] == "Nova notificação" and ev["body"] == "" and "segredo" not in str(ev)


def test_disabled_notifier_ignores_everything_but_the_test_button():
    n = N.Notifier(clock=Clock())
    assert n.push("X", "t") is None and n.active() is None        # off by default
    ev = n.push("Rhino", "Teste", force=True)
    assert ev and n.active() == ev                                # the "Testar" button works before enabling
    n.configure(True, "", 6, True)
    n.configure(False)
    assert n.status()["state"] == "off"
    n._stop.set()


def test_title_counter_parsing_and_growth():
    assert N.parse_title_counter("(3) WhatsApp") == ("WhatsApp", 3)
    assert N.parse_title_counter("(12) WhatsApp Web - Google Chrome") == ("WhatsApp", 12)
    assert N.parse_title_counter("WhatsApp") is None and N.parse_title_counter("(2) Receita de bolo") is None
    titles = [["(1) WhatsApp"]]
    src = N.TitleCounterSource(titles=lambda: titles[0])
    ids = lambda: [i["id"] for i in src.fetch()]
    a = ids()
    assert ids() == a                                             # unchanged count -> same id
    titles[0] = ["(2) WhatsApp"]
    b = ids()
    assert b != a                                                 # grew: a new message
    titles[0] = ["(1) WhatsApp"]
    assert ids() == b                                             # read one: not a new message
    titles[0] = []
    assert ids() == []
    titles[0] = ["(1) WhatsApp"]
    assert ids() != b                                             # back after being read: new again


def test_polling_with_an_injected_source():
    snaps = [[{"id": "1", "app": "A", "title": "x"}], [{"id": "1", "app": "A", "title": "x"}, {"id": "2", "app": "A", "title": "y"}]]
    n = N.Notifier(fetch=lambda: snaps.pop(0), clock=Clock())
    n.configure(True, "", 6, True)
    n._stop.set()
    n.poll_once(); n.poll_once()
    assert n.active()["title"] == "y" and n.status()["state"] == "ok"


def test_access_denied_falls_back_to_tab_titles(monkeypatch):
    def deny():
        raise N.AccessDenied()
    monkeypatch.setattr(N, "winrt_toasts", deny)
    n = N.Notifier(clock=Clock())
    n._titles = N.TitleCounterSource(titles=lambda: ["(1) WhatsApp"])
    n.configure(True, "", 6, True)
    n._stop.set()
    n.poll_once()
    assert n.status()["state"] == "denied" and "Privacidade" in n.status()["message"]
    n._titles = N.TitleCounterSource(titles=lambda: ["(2) WhatsApp"])
    n.poll_once()
    assert n.active() and n.active()["app"] == "WhatsApp"


def test_missing_winrt_packages_report_instead_of_crashing(monkeypatch):
    def boom():
        raise ImportError("no winrt")
    monkeypatch.setattr(N, "winrt_toasts", boom)
    n = N.Notifier(clock=Clock())
    n._titles = N.TitleCounterSource(titles=lambda: [])
    n.configure(True, "", 6, True)
    n._stop.set()
    n.poll_once()
    assert n.status()["state"] == "fallback" and "requirements-extras" in n.status()["message"]


# --------------------------------------------------------------------------- layout
def test_every_card_gets_the_notification_option_and_device_settings_are_clamped(tmp_path):
    assert any(o["key"] == "notify" for o in L.COMMON_OPTIONS)
    d = L.normalize({"device": {"notify": "yes", "notify_seconds": 999, "notify_apps": "WhatsApp, <b>x</b>;DROP", "notify_text": 0}})["device"]
    assert d["notify"] is False and d["notify_seconds"] == 30 and d["notify_text"] is True
    assert "<" not in d["notify_apps"] and ";" not in d["notify_apps"] and "WhatsApp" in d["notify_apps"]
    cfg = L.to_config(L.normalize({"device": {"notify": True, "notify_seconds": 8, "notify_apps": "Discord"}}), tmp_path)
    assert cfg["notifications"] == {"enabled": True, "seconds": 8, "apps": "Discord", "show_text": True}


def test_notify_option_adds_an_overlay_after_the_card_widgets(tmp_path):
    def widgets(module, **o):
        lay = L.normalize({"pages": [{"slots": [{"module": module, "col": 0, "row": 0, "w": 4, "h": 2, "options": o}]}]}, tmp_path)
        return L.to_config(lay, tmp_path)["page"][0]["widget"]
    for mod in ("cpu", "clock", "musica", "visualizador", "image", "text", "net"):
        assert not any(w["type"] == "notice" for w in widgets(mod))
        w = widgets(mod, notify=True)
        assert w[-1]["type"] == "notice" and w[-1]["mode"] == "alert"    # last = on top
        assert (w[-1]["x"], w[-1]["y"], w[-1]["w"], w[-1]["h"]) == (2, 2, 156, 76)
    assert [w["mode"] for w in widgets("notificacao") if w["type"] == "notice"] == ["list"]
    assert [w["mode"] for w in widgets("notificacao", notify=True) if w["type"] == "notice"] == ["list"]  # no overlay on itself


# --------------------------------------------------------------------------- on screen
class FakeAudio:
    def levels(self, n, sens=50):
        return np.ones(n)

    def beat_strength(self):
        return 0.0


def screen(tmp_path, slots, n):
    lay = L.normalize({"pages": [{"slots": slots}]}, tmp_path)
    disp = SimulatorDisplay(orientation="landscape", output=tmp_path / "o.png")
    eng = Engine(L.to_config(lay, tmp_path), disp, metrics=Metrics({"nvidia_smi": False, "lhm": False}))
    eng.ctx.audio, eng.ctx.notifier = FakeAudio(), n
    disp.open()
    return eng, disp


def region(disp, x0=0, y0=0, x1=160, y1=80):
    return np.asarray(disp.frame.convert("RGB"))[y0:y1, x0:x1].astype(int)


def test_alert_covers_the_card_then_gives_it_back(tmp_path):
    n = notifier()
    eng, disp = screen(tmp_path, [{"module": "visualizador", "col": 0, "row": 0, "w": 4, "h": 2, "options": {"notify": True, "color": "#ff0000"}}], n)
    t = 0.0
    for _ in range(3):
        eng.step(t); t += 1
    red = lambda r: ((r[..., 0] > 200) & (r[..., 1] < 60)).sum()
    assert red(region(disp)) > 300                              # the visualizer is showing
    n.ingest([])
    n.ingest([{"id": "w1", "app": "WhatsApp", "title": "Ana", "body": "Vamos jogar hoje à noite?"}])
    for _ in range(2):
        eng.step(t); t += 1
    covered = region(disp)
    assert red(covered) < 20                                    # visualizer hidden under the notification card
    assert (np.abs(covered - np.array([0x16, 0x1b, 0x26])).sum(axis=2) < 12).sum() > 4000   # opaque card fill
    assert (covered.sum(axis=2) > 600).sum() > 100              # some light text was drawn
    n.clock.t += 7                                              # the alert time is over
    for _ in range(3):
        eng.step(t); t += 1
    assert red(region(disp)) > 300                              # ... and the visualizer is back by itself


def test_cards_without_the_option_are_not_covered(tmp_path):
    n = notifier()
    eng, disp = screen(tmp_path, [{"module": "visualizador", "col": 0, "row": 0, "w": 4, "h": 2, "options": {"color": "#ff0000"}}], n)
    n.ingest([]); n.ingest([{"id": "1", "app": "X", "title": "t"}])
    for t in range(4):
        eng.step(float(t))
    assert ((region(disp)[..., 0] > 200) & (region(disp)[..., 1] < 60)).sum() > 300


def test_notification_list_card_shows_history_and_placeholder(tmp_path):
    n = notifier()
    eng, disp = screen(tmp_path, [{"module": "notificacao", "col": 0, "row": 0, "w": 6, "h": 4, "options": {}}], n)
    eng.step(0.0); eng.step(1.0)
    empty = region(disp, 0, 0, 240, 160).copy()
    n.ingest([])
    n.ingest([{"id": "1", "app": "Discord", "title": "Servidor", "body": "alguém te mencionou"},
              {"id": "2", "app": "WhatsApp", "title": "Ana", "body": "oi"}])
    eng.step(2.0); eng.step(3.0)
    assert (region(disp, 0, 0, 240, 160) != empty).any()


def test_long_notification_text_never_leaves_its_box(tmp_path):
    n = notifier()
    eng, disp = screen(tmp_path, [{"module": "cpu", "col": 1, "row": 1, "w": 3, "h": 2, "options": {"notify": True}}], n)
    n.ingest([])
    n.ingest([{"id": "1", "app": "Aplicativo com nome enorme demais para caber", "title": "T" * 200, "body": "palavra " * 80}])
    for t in range(3):
        eng.step(float(t))
    full = np.asarray(disp.frame.convert("RGB")).astype(int)
    outside = full.copy()
    outside[40:120, 40:160] = 0
    # nothing bright outside the card's box (the rest of the screen is the dark background)
    assert (outside.sum(axis=2) > 300).sum() == 0


# --------------------------------------------------------------------------- unread list, filters, retry

def test_list_shows_what_is_already_waiting_in_the_notification_center():
    n = notifier()
    waiting = [{"id": "1", "app": "Google Chrome", "title": "Ana", "body": "oi", "created": 10.0},
               {"id": "2", "app": "Discord", "title": "#geral", "body": "alguém te chamou", "created": 20.0}]
    assert n.ingest(waiting) == 0 and n.active() is None        # not "new": no pop-up over the cards...
    shown = n.listing(3)
    assert [e["title"] for e in shown] == ["#geral", "Ana"]     # ...but listed, newest first
    n.ingest([waiting[0]])                                      # the Discord one was opened -> gone from the list
    assert [e["title"] for e in n.listing(3)] == ["Ana"]
    n.ingest([])
    assert n.listing(3) == []                                   # nothing pending, nothing arrived since start


def test_list_falls_back_to_what_arrived_when_nothing_is_pending():
    n = notifier()
    n.ingest([])
    n.push("WhatsApp", "Bia", "e aí?")
    assert [e["title"] for e in n.listing(3)] == ["Bia"]


def test_app_filter_also_matches_title_and_text_because_web_apps_arrive_as_the_browser():
    n = notifier()
    n.configure(True, "whatsapp", 6, True)
    assert n.push("Google Chrome", "WhatsApp Web", "Ana: oi") is not None
    assert n.push("Google Chrome", "Outro site", "nada a ver") is None
    n.ingest([{"id": "1", "app": "Google Chrome", "title": "Outro site", "body": "x"},
              {"id": "2", "app": "Google Chrome", "title": "Ana", "body": "WhatsApp: oi"}])
    assert [e["id"] for e in n.listing(3)] == ["2"]


def test_privacy_mode_also_hides_the_text_in_the_list():
    n = notifier()
    n.configure(True, "", 6, False)
    n.ingest([{"id": "1", "app": "WhatsApp", "title": "Ana Souza", "body": "segredo"}])
    e = n.listing(3)[0]
    assert e["title"] == "Nova notificação" and e["body"] == "" and "segredo" not in str(n.listing(3))


def test_windows_source_is_tried_again_after_the_permission_is_granted(monkeypatch):
    calls = {"n": 0, "allow": False}

    def toasts():
        calls["n"] += 1
        if not calls["allow"]:
            raise N.AccessDenied()
        return [{"id": "9", "app": "Discord", "title": "oi", "body": ""}]
    monkeypatch.setattr(N, "winrt_toasts", toasts)
    clock = Clock()
    n = N.Notifier(clock=clock)
    n._titles = N.TitleCounterSource(titles=lambda: [])
    n.start = lambda: None
    n.configure(True, "", 6, True)
    n.poll_once()
    assert n.status()["state"] == "denied" and n.status()["source"] == "title"
    n.poll_once()
    assert calls["n"] == 1                                      # does not hammer Windows on every poll
    calls["allow"] = True
    clock.t += N.WINRT_RETRY + 1
    n.poll_once()
    assert n.status()["state"] == "ok" and n.status()["source"] == "toast" and n.status()["pending"] == 1


def test_tab_title_counter_complements_toasts_from_other_apps(monkeypatch):
    monkeypatch.setattr(N, "winrt_toasts", lambda: [{"id": "1", "app": "Discord", "title": "x", "body": ""}])
    n = N.Notifier(clock=Clock())
    n._titles = N.TitleCounterSource(titles=lambda: ["(2) WhatsApp - Google Chrome", "(1) Discord | Servidor"])
    n.start = lambda: None
    n.configure(True, "", 6, True)
    n.poll_once()
    apps = sorted(e["app"] for e in n.listing(5))
    assert apps == ["Discord", "WhatsApp"]                      # Discord is not duplicated by its tab counter


def test_status_reports_the_failure_reason_for_the_screen(monkeypatch):
    def boom():
        raise RuntimeError("falhou de verdade")
    monkeypatch.setattr(N, "winrt_toasts", boom)
    n = N.Notifier(clock=Clock())
    n._titles = N.TitleCounterSource(titles=lambda: [])
    n.start = lambda: None
    n.configure(True, "", 6, True)
    n.poll_once()
    st = n.status()
    assert st["state"] == "error" and "RuntimeError" in st["error"] and "falhou de verdade" in st["message"]
