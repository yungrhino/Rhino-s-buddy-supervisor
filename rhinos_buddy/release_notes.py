"""Short "what's new" notes shown once, in a pop-up, the first time a new version is opened.

The full notes (for the GitHub release) live in ``docs/releases/``; these are the few lines that matter to a user.
Add an entry here with every version: a version without notes simply shows no pop-up.
"""

from __future__ import annotations

NOTES: dict[str, dict] = {
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


def notes_for(version: str) -> dict | None:
    n = NOTES.get(version)
    return {"version": version, "title": n["title"], "items": list(n["items"])} if n else None


def should_show(version: str, prefs: dict) -> bool:
    """Only for a version that has notes, that this user has not seen yet, unless they turned the pop-up off."""
    return bool(notes_for(version)) and not prefs.get("hide_notes") and prefs.get("seen_version") != version
