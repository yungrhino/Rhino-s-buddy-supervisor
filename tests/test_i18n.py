"""Version 1.2.0: Portuguese / English interface."""
import datetime
import re
from pathlib import Path

import pytest

from rhinos_buddy import __version__, __version_title__, appdata, i18n, layout as L, release_notes
from rhinos_buddy import widgets as W
from tests.test_app import W as HDR, call, server  # noqa: F401  (fixture + helpers)
from tests.test_notifications import notifier

# words that are the same in both languages (technical names, numbers)
NEUTRAL = {"CPU", "GPU", "RAM", "VRAM", "Download", "Upload", "↓ Download", "↑ Upload", "13:45", "13:45:09", "11/11/2026", "Circular"}


def catalog_strings():
    c = L.catalog()
    out = set()
    for m in c["modules"]:
        out |= {m["label"], m["group"]}
        for o in m["options"] + c["common_options"]:
            out |= {o["label"], *(x[1] for x in o.get("choices") or [])}
            if o.get("hint"):
                out.add(o["hint"])
            if o["kind"] == "text":
                out.add(o["default"])
    out |= {t[1] for t in c["templates"]} | {r[1] for r in c["rotations"]}
    return {s for s in out if isinstance(s, str) and s}


def test_every_text_of_the_catalog_has_an_english_version():
    pt = catalog_strings()
    i18n.set_lang("en")
    missing = sorted(s for s in pt if i18n.t(s) == s and s not in NEUTRAL)
    assert not missing, missing


def test_catalog_follows_the_language_and_keeps_ids():
    pt = L.catalog()
    i18n.set_lang("en")
    en = L.catalog()
    assert [m["id"] for m in pt["modules"]] == [m["id"] for m in en["modules"]]
    clock = next(m for m in en["modules"] if m["id"] == "clock")
    assert clock["label"] == "Clock" and clock["group"] == "Date and time"
    assert en["beta_group"] == "Testing" and en["rotations"][0][1] == "Landscape" and en["rotations"][0][0] == "landscape"
    idle = next(o for o in next(m for m in en["modules"] if m["id"] == "notificacao")["options"] if o["key"] == "idle_text")
    assert idle["default"] == "No notifications" and idle["default_pt"] == "Sem notificações"
    assert [c[0] for c in clock["options"][0].get("choices", [])] == [c[0] for c in pt["modules"][0]["options"][0].get("choices", [])]


def test_templates_translate_already_formatted_messages():
    i18n.set_lang("en")
    assert i18n.t("Falha ao conectar: boom") == "Could not connect: boom"
    assert i18n.t("Página 3") == "Page 3"
    assert i18n.t("12 mensagens não lidas") == "12 unread messages"
    assert i18n.t("Texto que ninguém traduziu") == "Texto que ninguém traduziu"   # unknown text is left alone
    assert i18n.t("Page {n}") == "Page {n}" and i18n.t("Página {n}", n=2) == "Page 2"
    i18n.set_lang("pt")
    assert i18n.t("Página {n}", n=2) == "Página 2" and i18n.t("Falha ao conectar: boom") == "Falha ao conectar: boom"


def test_user_text_is_never_translated():
    i18n.set_lang("en")
    lay = L.normalize({"pages": [{"slots": [{"module": "text", "col": 0, "row": 0, "w": 4, "h": 1, "options": {"text": "Disco"}},
                                             {"module": "text", "col": 4, "row": 0, "w": 4, "h": 1, "options": {}}]}]})
    texts = [w["text"] for w in L.to_config(lay, Path("."))["page"][0]["widget"] if w["type"] == "text"]
    assert "Disco" in texts and "My text" in texts      # typed text stays; the program's own default follows the language


def test_default_labels_on_the_screen_follow_the_language():
    lay = L.normalize({"pages": [{"slots": [{"module": "disk", "col": 0, "row": 0, "w": 4, "h": 2, "options": {}}]}]})
    pt_texts = [w["text"] for w in L.to_config(lay, Path("."))["page"][0]["widget"] if w["type"] == "text"]
    i18n.set_lang("en")
    en_texts = [w["text"] for w in L.to_config(lay, Path("."))["page"][0]["widget"] if w["type"] == "text"]
    assert "Disco" in pt_texts and "Disk" in en_texts and "Disco" not in en_texts


def test_dates_use_english_names_and_formats():
    d = datetime.datetime(2026, 11, 21)   # a Saturday
    assert W.pt_date_fields(d)["dia_semana_cap"] == "Sábado" and W.pt_date_fields(d)["mes"] == "novembro"
    i18n.set_lang("en")
    f = W.pt_date_fields(d)
    assert (f["dia_semana_cap"], f["mes"], f["mes_curto"], f["dia_semana_curto"]) == ("Saturday", "November", "Nov", "Sat")
    lay = L.normalize({"pages": [{"slots": [{"module": "date", "col": 0, "row": 0, "w": 5, "h": 2, "options": {}}]}]})
    tpls = [w["text"] for w in L.to_config(lay, Path("."))["page"][0]["widget"] if w["type"] == "text"]
    assert tpls == ["{dia_semana_cap}", "{mes} {dia}, {ano}"]


def test_english_date_text_fits_every_weekday_and_month(tmp_path):
    i18n.set_lang("en")
    days = [datetime.datetime(2026, 1, 1) + datetime.timedelta(days=i) for i in range(366)]
    fmts = {"{dia_semana_cap}": lambda f: f["dia_semana_cap"], "{mes} {dia}, {ano}": lambda f: f"{f['mes']} {f['dia']}, {f['ano']}",
            "{now:%m/%d/%Y}": lambda f: "00/00/0000", "{dia_semana_curto}, {mes_curto} {dia}": lambda f: f"{f['dia_semana_curto']}, {f['mes_curto']} {f['dia']}"}
    for font in ("Verdana", "Arial"):
        for style in ("completo", "extenso", "semana_curto", "curto"):
            for w, h in [(4, 2), (3, 2), (4, 1), (2, 1), (6, 3)]:
                lay = L.normalize({"theme": {"font": font}, "pages": [{"slots": [{"module": "date", "col": 0, "row": 0, "w": w, "h": h, "options": {"style": style}}]}]}, tmp_path)
                for wd in [x for x in L.to_config(lay, tmp_path)["page"][0]["widget"] if x["type"] == "text"]:
                    f = W.load_font(wd["font"], wd["size"], None)
                    widest = max(f.getlength(fmts[wd["text"]](W.pt_date_fields(d))) for d in days)
                    if wd["size"] > 9:
                        assert widest <= wd["w"], (font, style, w, h, wd["text"], wd["size"])


def test_decimal_comma_is_only_for_portuguese():
    lay = L.normalize({})
    assert L.to_config(lay, Path("."))["display"]["decimal"] == ","
    i18n.set_lang("en")
    assert L.to_config(lay, Path("."))["display"]["decimal"] == "."


def test_notification_texts_follow_the_language():
    i18n.set_lang("en")
    n = notifier()
    n.configure(True, "", 6, False)
    n.push("WhatsApp", "Ana", "oi")
    assert n.active()["title"] == "New notification"
    src = __import__("rhinos_buddy.notifications", fromlist=["x"]).TitleCounterSource(titles=lambda: ["(3) WhatsApp"])
    assert src.fetch()[0]["title"] == "3 unread messages"


def test_release_notes_exist_in_both_languages_and_the_title_is_english():
    assert re.fullmatch(r"[A-Za-z0-9 ,'\-]+", __version_title__), "the version title is written in English"
    pt, en = release_notes.notes_for(__version__, "pt"), release_notes.notes_for(__version__, "en")
    assert pt and en and pt["items"] != en["items"] and len(pt["items"]) == len(en["items"])


def test_prefs_keep_the_language():
    assert appdata.load_prefs(Path("/nonexistent"))["lang"] == "pt"


# ---- through the HTTP API
def test_language_api_switches_everything_and_is_remembered(server, tmp_path):
    app, base = server
    st = call(base + "/api/state")[1]
    assert st["lang"] == "pt" and st["lang_chosen"] is False and st["i18n"]["Relógio"] == "Clock"
    code, body = call(base + "/api/lang", "POST", {"lang": "en"}, HDR)
    assert code == 200 and body["lang"] == "en" and body["lang_chosen"] is True
    assert next(m for m in body["catalog"]["modules"] if m["id"] == "clock")["label"] == "Clock"
    assert body["whatsnew"]["notes"]["items"] == release_notes.notes_for(__version__, "en")["items"]
    assert "Looking for the screen" in body["status"]["message"] or "Preview mode" in body["status"]["message"]
    assert appdata.load_prefs(tmp_path)["lang"] == "en"
    assert call(base + "/api/nope", "POST", {}, HDR)[1]["error"] == "Not found"             # API errors follow too
    assert call(base + "/api/lang", "POST", {"lang": "fr"}, HDR)[0] == 400
    call(base + "/api/lang", "POST", {"lang": "pt"}, HDR)
    assert call(base + "/api/state")[1]["catalog"]["beta_group"] == "Em teste"


def test_app_starts_in_the_saved_language(tmp_path):
    from rhinos_buddy.runner import Runner
    from rhinos_buddy import app as A
    appdata.save_prefs(tmp_path, {"lang": "en", "lang_chosen": True})
    runner = Runner(tmp_path, hardware=False)
    A.App(tmp_path, runner, 0)
    assert i18n.lang() == "en"


def test_screen_text_changes_after_switching_language(server):
    app, base = server
    call(base + "/api/lang", "POST", {"lang": "en"}, HDR)
    cfg = __import__("rhinos_buddy.layout", fromlist=["x"]).to_config(app.runner.layout, app.home)
    assert any("{mes} {dia}, {ano}" == w.get("text") for p in cfg["page"] for w in p["widget"])


# ---- the editor page: every Portuguese text it contains has an English version
def test_every_text_in_the_editor_page_is_in_the_dictionary():
    src = (Path(i18n.__file__).parent / "web" / "index.html").read_text("utf-8")
    script = src[src.index('<script>\n"use strict"'):]
    literals = set(re.findall(r'"((?:[^"\\\n]|\\.)*)"', script))
    markup = set(re.findall(r'data-t(?:a)?="([^"]+)"', src))
    pt_words = re.compile(r"[áàâãéêíóôõúçÁÉÍÓÚÇ]|\b(Mostrar|Usar|Nome|Esta|Adicionar|Clique|Máximo|Desligado|Duração|Texto|Fundo|Testar|"
                          r"Restaurar|Cancelar|Reconectar|Atualizar|Porta|Brilho|Fonte|Programa|Módulo|Remover|Duplicar|Ocultar|Selecionar)\b")
    ignore = {"Português", "Página", "Você pode mudar depois no topo da página ou em Sistema → Idioma. · You can change it later at the top of the page or in System → Language.",
              "<p style='padding:40px'>Não foi possível falar com o programa: ", "Escolha o idioma · Choose your language"}
    missing = sorted(l for l in (literals | markup) if len(l) > 2 and pt_words.search(l) and l not in i18n.EN and l not in ignore)
    assert not missing, missing
