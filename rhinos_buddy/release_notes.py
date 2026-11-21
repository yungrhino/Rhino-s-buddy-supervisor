"""Short "what's new" notes shown once, in a pop-up, the first time a new version is opened.

The full notes (for the GitHub release) live in ``docs/releases/``; these are the few lines that matter to a user.
Add an entry here with every version: a version without notes simply shows no pop-up.
"""

from __future__ import annotations

NOTES: dict[str, dict] = {
    "1.2.0": {
        "title": "English language and quick exit",
        "items": [
            "Novo idioma: Inglês. Escolha entre Português e English neste primeiro aviso; dá para trocar a qualquer momento no topo da página ou em Sistema → Idioma.",
            "A troca vale na hora: editor, nomes dos módulos, mensagens e até os textos que aparecem na tela (dias e meses da data, avisos).",
            "Novo botão “Encerrar” no topo da página, ao lado do status da tela, com uma confirmação antes de fechar o programa.",
            "A mesma confirmação vale para Sistema → Encerrar programa.",
        ],
        "items_en": [
            "New language: English. Pick Portuguese or English in this first window; you can switch at any time at the top of the page or in System → Language.",
            "The change is instant: the editor, module names, messages and even the texts shown on the screen (weekdays and months in the date, alerts).",
            "New “Quit” button at the top of the page, next to the screen status, with a confirmation before the program closes.",
            "The same confirmation is used by System → Quit program.",
        ],
    },
    "1.1.0": {
        "title": "modo claro e cards em teste",
        "items": [
            "Modo claro e modo escuro: o botão fica no topo da página.",
            "Nova categoria “Em teste” (expansível) na lista de módulos, com o card de Notificações dentro.",
            "O card de Notificações ganhou alinhamento do texto (esquerda, centro ou direita).",
            "Preview: clique fora do card para desmarcar; agora dá para redimensionar puxando qualquer canto.",
            "Trocar entre paisagem e retrato não bagunça mais os cards: cada orientação guarda o seu próprio arranjo.",
            "Esta janela de novidades aparece só uma vez por versão e pode ser desligada.",
            "O zip inclui um desinstalador e as notas da versão.",
        ],
    },
}


def notes_for(version: str, lang: str = "pt") -> dict | None:
    """Notes for ``version`` in ``lang`` (falls back to Portuguese when a version has no English text)."""
    n = NOTES.get(version)
    if not n:
        return None
    items = n.get("items_en") if lang == "en" and n.get("items_en") else n["items"]
    return {"version": version, "title": n["title"], "items": list(items)}


def should_show(version: str, prefs: dict) -> bool:
    """Only for a version that has notes, that this user has not seen yet, unless they turned the pop-up off."""
    return bool(notes_for(version)) and not prefs.get("hide_notes") and prefs.get("seen_version") != version
