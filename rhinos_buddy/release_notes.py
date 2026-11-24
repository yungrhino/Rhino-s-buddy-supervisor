"""Short "what's new" notes shown once, in a pop-up, the first time a new version is opened.

The full notes (for the GitHub release) live in ``docs/releases/``; these are the few lines that matter to a user.
Add an entry here with every version: a version without notes simply shows no pop-up.
"""

from __future__ import annotations

NOTES: dict[str, dict] = {
    "1.7.0": {
        "title": "Storage card and easier pairing",
        "items": [
            "Novo card “Armazenamento”: mostra o uso das unidades de disco (percentual, usado/total, livre, temperatura, leitura e escrita), como cartão de uma unidade ou como lista de todas. Tudo é opcional: você escolhe a unidade, o que aparece e o estilo (barra ou anel).",
            "Celular sem leitor de QR? Abaixo do QR agora há o código curto (8 caracteres), o endereço para digitar e o link completo com o botão “Copiar link”. O código vale 5 minutos, só funciona uma vez e tem o mesmo bloqueio contra tentativas. O QR ficou menor e mais fácil de ler.",
            "Visão da tela no celular: a imagem gira sozinha para o lado em que aparece maior (respeitando retrato ou paisagem do seu layout), com o botão “Giro” para escolher auto, não ou sim. Em tela cheia no Android a orientação é travada no formato da imagem.",
            "Novo histórico de novidades: em Sistema → Novidades dá para abrir as novidades de qualquer versão anterior.",
            "Correção para o Windows: o servidor do celular não divide mais a porta com outro programa, e os testes automáticos do GitHub passam a mostrar mais detalhes quando algo falha.",
        ],
        "items_en": [
            "New “Storage” card: shows disk drive usage (percent, used/total, free, temperature, read and write speed), as a card for one drive or as a list of all of them. Everything is optional: you choose the drive, what is shown and the style (bar or ring).",
            "Phone without a QR reader? Under the QR there is now the short code (8 characters), the address to type and the full link with a “Copy link” button. The code lasts 5 minutes, works only once and has the same lock-out against guessing. The QR is smaller and easier to scan.",
            "Phone screen view: the picture turns by itself to the side where it appears biggest (respecting your layout's portrait or landscape), with a “Rotate” button to pick auto, off or on. In fullscreen on Android the orientation is locked to the picture's shape.",
            "New what's-new history: in System → What's new you can open the notes of any earlier version.",
            "Windows fix: the phone server no longer shares its port with another program, and the automatic GitHub tests now show more detail when something fails.",
        ],
    },
    "1.6.0": {
        "title": "Phone panel and volume",
        "items": [
            "Novo: o painel completo no celular. Escaneie o QR code em Sistema → Acesso pelo celular e o mesmo painel abre no navegador do celular, adaptado à tela pequena, para editar a telinha. Ligue “Permitir também editar o painel pelo celular” para poder alterar (desligado por padrão); o botão “Ver tela” mostra só a imagem em tela cheia.",
            "Pareamento mais seguro: o QR vale 5 minutos e só funciona uma vez (depois aparece um novo), com contagem regressiva. Quem conecta fica conectado até fechar o navegador ou você desconectar. A lista de aparelhos conectados fica no PC, com botão Desconectar.",
            "PC e celular ficam sincronizados: o que você muda em um aparece no outro e na tela. Se os dois salvarem ao mesmo tempo, vale o que foi salvo primeiro e o outro é atualizado com um aviso.",
            "Pelo celular não dá para encerrar o programa, mexer no início com o Windows, restaurar padrões nem enviar imagens (isso continua só no PC).",
            "Card de música: nova opção “Mostrar o volume do PC (%) no canto”, com ícone e porcentagem num canto reservado, sem interferir no título rolante. Mostra “Mudo” quando o som está silenciado.",
        ],
        "items_en": [
            "New: the full panel on your phone. Scan the QR code in System → Phone access and the same panel opens in the phone's browser, adapted to the small screen, so you can edit the little screen. Turn on “Also allow editing the panel from the phone” to make changes (off by default); the “View screen” button shows just the picture, fullscreen.",
            "Safer pairing: the QR code is valid for 5 minutes and works only once (then a new one appears), with a countdown. Whoever connects stays connected until they close the browser or you disconnect them. The list of connected devices is on the PC, with a Disconnect button.",
            "PC and phone stay in sync: what you change in one shows up in the other and on the screen. If both save at the same time, the one saved first wins and the other is refreshed with a notice.",
            "From the phone you cannot quit the program, change Windows start-up, restore defaults or upload images (those stay PC-only).",
            "Music card: new option “Show the PC volume (%) in the corner”, with an icon and percentage in a reserved corner that never touches the scrolling title. It shows “Muted” when the sound is muted.",
        ],
    },
    "1.5.0": {
        "title": "Stable repository checks",
        "items": [
            "Correção para quem publica no GitHub: os testes automáticos falhavam quando restava no repositório o desinstalador com o nome antigo (“Desinstalar …”) ou notas de versões antigas, o que acontece ao extrair o zip novo por cima da pasta antiga. As verificações agora toleram esses arquivos.",
            "O programa em si não mudou.",
        ],
        "items_en": [
            "Fix for GitHub users: the automated tests failed when the old-named uninstaller (“Desinstalar …”) or older release notes were left in the repository, which happens when a new zip is extracted over the old folder. The checks now tolerate those files.",
            "The program itself did not change.",
        ],
    },
    "1.4.0": {
        "title": "Phone view with QR code",
        "items": [
            "Novo: veja a tela no celular pelo mesmo Wi-Fi. Em Sistema → Acesso pelo celular, ligue o interruptor e escaneie o QR code (Android e iOS, sem instalar nada).",
            "A página do celular mostra a mesma imagem da tela, com botões para girar e (no Android) tela cheia. É só para olhar: nada pode ser alterado por lá.",
            "Segurança: vem desligado; usa um servidor separado que escuta só no endereço da sua rede local; exige um código secreto (dentro do QR) que dá para trocar a qualquer momento; só aceita aparelhos da rede local e bloqueia quem tenta adivinhar.",
            "Atenção: a conexão não é criptografada. Quem estiver na sua rede e tiver o link vê a tela (inclusive notificações). Desligue quando não precisar.",
        ],
        "items_en": [
            "New: see the screen on your phone over the same Wi-Fi. In System → Phone access, turn the switch on and scan the QR code (Android and iOS, nothing to install).",
            "The phone page shows the same picture as the screen, with buttons to rotate and (on Android) go fullscreen. It is view-only: nothing can be changed from there.",
            "Security: it is off by default; it uses a separate server that listens only on your local-network address; it requires a secret code (inside the QR) that you can replace at any time; it only accepts devices on the local network and locks out anyone guessing.",
            "Note: the connection is not encrypted. Anyone on your network who has the link can see the screen (including notifications). Turn it off when you do not need it.",
        ],
    },
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
        "title": "Light mode and test cards",
        "items": [
            "Modo claro e modo escuro: o botão fica no topo da página.",
            "Nova categoria “Em teste” (expansível) na lista de módulos, com o card de Notificações dentro.",
            "O card de Notificações ganhou alinhamento do texto (esquerda, centro ou direita).",
            "Preview: clique fora do card para desmarcar; agora dá para redimensionar puxando qualquer canto.",
            "Trocar entre paisagem e retrato não bagunça mais os cards: cada orientação guarda o seu próprio arranjo.",
            "Esta janela de novidades aparece só uma vez por versão e pode ser desligada.",
            "O zip inclui um desinstalador e as notas da versão.",
        ],
        "items_en": [
            "Light and dark mode: the button is at the top of the page.",
            "New “In testing” category (expandable) in the module list, with the Notifications card inside.",
            "The Notifications card gained text alignment (left, center or right).",
            "Preview: click outside a card to deselect it; you can now resize by dragging any corner.",
            "Switching between landscape and portrait no longer scrambles the cards: each orientation keeps its own arrangement.",
            "This what's-new window shows only once per version and can be turned off.",
            "The zip includes an uninstaller and the version notes.",
        ],
    },
    "1.0.10": {
        "title": "Accurate song time",
        "items": [
            "Versões 1.0.x (resumo): contador de tempo da música preciso, sem pular nem repetir segundos.",
            "Notificações aparecem sobre qualquer card, com card próprio de Notificações; a lista mostra o que está na central do Windows e o filtro olha título e texto.",
            "Visualizador de áudio que acompanha o dispositivo de saída; data sem cortes (o texto encolhe em vez de cortar).",
        ],
        "items_en": [
            "1.0.x versions (summary): accurate song time counter, with no skipped or repeated seconds.",
            "Notifications appear over any card, with a dedicated Notifications card; the list shows what is in the Windows notification center and the filter checks title and text.",
            "Audio visualizer that follows the output device; the date no longer gets cut off (the text shrinks instead).",
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


def history(lang: str = "pt") -> list[dict]:
    """Every version that has notes, newest first (for the "see past what's-new" list)."""
    def key(v: str):
        return tuple(int(x) for x in v.split(".") if x.isdigit())

    return [notes_for(v, lang) for v in sorted(NOTES, key=key, reverse=True)]


def should_show(version: str, prefs: dict) -> bool:
    """Only for a version that has notes, that this user has not seen yet, unless they turned the pop-up off."""
    return bool(notes_for(version)) and not prefs.get("hide_notes") and prefs.get("seen_version") != version
