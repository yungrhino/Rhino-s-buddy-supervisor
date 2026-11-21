"""Short "what's new" notes shown once, in a pop-up, the first time a new version is opened.

The full notes (for the GitHub release) live in ``docs/releases/``; these are the few lines that matter to a user.
Add an entry here with every version: a version without notes simply shows no pop-up.
"""

from __future__ import annotations

NOTES: dict[str, dict] = {
    "1.3.1": {
        "title": "All artists on screen",
        "items": [
            "Correção: no Spotify, o card de música mostrava só o primeiro artista. Agora mostra todos (por exemplo “kouth, Cashley, Necroez, SYMSESH”); se a lista for longa, ela rola como o título.",
        ],
        "items_en": [
            "Fix: with Spotify, the music card showed only the first artist. It now shows all of them (for example “kouth, Cashley, Necroez, SYMSESH”); if the list is long, it scrolls like the title.",
        ],
    },
    "1.3.0": {
        "title": "Scrolling song titles",
        "items": [
            "Card de música: títulos (e artistas) grandes demais agora rolam pela tela, como nos MP3 players antigos, para mostrar o nome completo. Dá para desligar na opção “Rolar títulos longos”.",
            "Reconhecimento de mídia mais robusto: agora o programa olha todas as sessões de mídia do Windows e escolhe a que está tocando (por exemplo, YouTube no navegador), em vez de só a “atual”. Falhas de leitura passam a ser registradas no log.",
            "Seu GitHub (yungrhino) aparece ao lado da versão, no topo da página e na aba Sistema.",
        ],
        "items_en": [
            "Music card: titles (and artists) too wide for the card now scroll past, like on old MP3 players, to show the full name. You can turn it off with the “Scroll long titles” option.",
            "More robust media detection: the program now looks at all Windows media sessions and picks the one that is playing (for example YouTube in the browser), instead of only the “current” one. Read failures are now written to the log.",
            "The author's GitHub (yungrhino) is shown next to the version, at the top of the page and in the System tab.",
        ],
    },
    "1.2.1": {
        "title": "Smooth updates and English file names",
        "items": [
            "Correção: ao abrir uma versão nova, o programa agora fecha a cópia antiga que ainda estava rodando e assume o lugar. Antes, a cópia antiga continuava aberta e esta janela de novidades não aparecia.",
            "A versão agora aparece no topo da página, ao lado do nome.",
            "Os arquivos .bat agora têm nomes em inglês: “Uninstall Rhinos Buddy Supervisor.bat” e “Start Rhinos Buddy Supervisor.bat” (o desinstalador também fala inglês).",
        ],
        "items_en": [
            "Fix: opening a new version now closes the old copy that was still running and takes its place. Before, the old copy stayed open and this what's-new window never showed up.",
            "The version is now shown at the top of the page, next to the name.",
            "The .bat files now have English names: “Uninstall Rhinos Buddy Supervisor.bat” and “Start Rhinos Buddy Supervisor.bat” (the uninstaller speaks English too).",
        ],
    },
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
