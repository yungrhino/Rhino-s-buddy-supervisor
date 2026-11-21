"""Interface language (Portuguese / English).

The program's source strings are Portuguese.  ``t(text)`` returns the English version when the language is
English: exact matches first, then templates such as ``"Página {n}"`` (so already formatted messages like
``"Página 3"`` or ``"Capturando o áudio de: Speakers"`` translate too).  Anything that has no entry is returned
unchanged, so a missing translation shows Portuguese instead of breaking.  User data (page names, typed labels,
file names) is never translated: only the program's own texts are.

The same dictionary is served to the browser (``/api/i18n``), so there is a single place to edit.
"""

from __future__ import annotations

import re

LANGS = ("pt", "en")
DEFAULT = "pt"
_lang = DEFAULT


def lang() -> str:
    return _lang


def set_lang(value: str) -> str:
    global _lang
    _lang = value if value in LANGS else DEFAULT
    return _lang


# --------------------------------------------------------------------------- dictionary (PT -> EN)
EN: dict[str, str] = {
    # ---- module catalog: names, groups, options
    "Relógio": "Clock", "Data e hora": "Date and time", "Formato": "Format", "Alinhamento": "Alignment",
    "Esquerda": "Left", "Centro": "Center", "Direita": "Right", "Cor (vazio = padrão)": "Color (empty = default)",
    "Data": "Date", "Estilo": "Style",
    "Quarta-feira + 11 de novembro de 2026": "Wednesday + November 11, 2026",
    "11 de novembro de 2026": "November 11, 2026", "qua, 11 nov": "Wed, Nov 11",
    "CPU (uso)": "CPU (usage)", "Processador": "Processor", "Rótulo": "Label",
    "Mostrar temperatura": "Show temperature", "Estilo do indicador": "Indicator style",
    "Seguir o tema": "Follow the theme", "Barra horizontal": "Horizontal bar", "Radial (círculo)": "Radial (circle)",
    "Mostrar barra": "Show bar", "Mostrar gráfico": "Show graph", "Posição do texto": "Text position", "Padrão": "Default",
    "CPU (temperatura)": "CPU (temperature)", "Temp. CPU": "CPU temp.",
    "GPU (uso)": "GPU (usage)", "Placa de vídeo": "Graphics card", "GPU (temperatura)": "GPU (temperature)",
    "Temp. GPU": "GPU temp.", "Memória de vídeo": "Video memory", "Memória RAM": "RAM memory",
    "Memória e disco": "Memory and disk", "Disco (uso)": "Disk (usage)", "Disco": "Disk", "Rede": "Network",
    "Rede (download + upload)": "Network (download + upload)",
    "Música (visualizador)": "Music (visualizer)", "Música": "Music",
    "Mostrar o que está tocando": "Show what is playing", "Aparência do que está tocando": "Now-playing appearance",
    "Compacto (título e artista)": "Compact (title and artist)",
    "Card expandido (capa + progresso)": "Expanded card (cover + progress)",
    "Card: mostrar a capa": "Card: show the cover", "Card: mostrar barra de progresso e tempo": "Card: show progress bar and time",
    "Mostrar o artista": "Show the artist", "Mostrar visualizador de áudio": "Show audio visualizer",
    "Estilo do visualizador": "Visualizer style", "Barras": "Bars", "Barras espelhadas": "Mirrored bars",
    "Circular": "Circular", "Pulso (batida)": "Pulse (beat)", "Quantidade de barras": "Number of bars",
    "Sensibilidade": "Sensitivity", "Alinhamento do texto": "Text alignment", "Visualizador de áudio": "Audio visualizer",
    "Notificações (lista)": "Notifications (list)", "Em teste": "Testing", "Quantas mostrar": "How many to show",
    "Texto quando não há nenhuma": "Text when there are none", "Sem notificações": "No notifications",
    "Texto livre": "Free text", "Outros": "Other", "Texto (aceita {cpu:.0f} {gpu_temp:.0f} ...)": "Text (accepts {cpu:.0f} {gpu_temp:.0f} ...)",
    "Meu texto": "My text", "Tamanho (0 = automático)": "Size (0 = automatic)", "Imagem / GIF": "Image / GIF",
    "Arquivo": "File", "Ajuste": "Fit", "Inteira": "Whole", "Preencher": "Fill", "Esticar": "Stretch",
    "Cartão de fundo": "Background card", "Sempre": "Always", "Nunca": "Never",
    "Mostrar avisos de notificação neste card": "Show notification alerts on this card",
    "Completo (hora, CPU, GPU, RAM, rede)": "Full (time, CPU, GPU, RAM, network)",
    "Mínimo (hora e temperaturas)": "Minimal (time and temperatures)",
    "Anéis (CPU, GPU, VRAM e RAM em círculos)": "Rings (CPU, GPU, VRAM and RAM as circles)",
    "Foto de fundo (cartões translúcidos)": "Background photo (translucent cards)", "Em branco": "Blank",
    "Paisagem": "Landscape", "Paisagem invertida (180°)": "Landscape flipped (180°)", "Retrato": "Portrait",
    "Retrato invertido": "Portrait flipped",
    "Principal": "Main", "Página {n}": "Page {n}",
    # ---- on-screen texts
    "Nada tocando": "Nothing playing", "Nova mensagem": "New message", "{n} mensagens não lidas": "{n} unread messages",
    "Notificação": "Notification", "Nova notificação": "New notification",
    "Teste de notificação": "Notification test",
    "Se você está vendo este aviso, os cards com notificação funcionam.": "If you can see this alert, the cards with notifications work.",
    # ---- messages from the program
    "Tela não encontrada. Conecte o cabo USB ou escolha a porta manualmente na aba Tela.":
        "Screen not found. Plug in the USB cable or choose the port manually in the Screen tab.",
    "Não foi possível abrir a porta. Feche o UsbMonitor.exe original (ou outro programa que use a tela).":
        "Could not open the port. Close the original UsbMonitor.exe (or any other program using the screen).",
    "Falta o pacote pyserial (pip install pyserial).": "The pyserial package is missing (pip install pyserial).",
    "Falha ao conectar: {text}": "Could not connect: {text}",
    "Modo pré-visualização (sem tela).": "Preview mode (no screen).", "Procurando a tela…": "Looking for the screen…",
    "Reconectando…": "Reconnecting…", "Tela desconectada. Tentando reconectar…": "Screen disconnected. Trying to reconnect…",
    "Tela conectada.": "Screen connected.",
    "Host não permitido": "Host not allowed", "Arquivo não encontrado": "File not found", "Modelo inválido": "Invalid template",
    "Não encontrado": "Not found", "Requisição não permitida": "Request not allowed",
    "Corpo inválido ou grande demais": "Invalid or too large body", "Arquivo muito grande (máximo 25 MB).": "File too large (25 MB maximum).",
    "JSON inválido": "Invalid JSON", "Idioma inválido": "Invalid language", "Formato não suportado (use PNG, JPG, GIF, WebP ou BMP).": "Unsupported format (use PNG, JPG, GIF, WebP or BMP).",
    "O arquivo não é uma imagem válida.": "The file is not a valid image.",
    "Iniciar com o Windows só está disponível no Windows.": "Starting with Windows is only available on Windows.",
    "Notificações desligadas.": "Notifications are off.", "Lendo as notificações.": "Reading notifications.",
    "Lendo as notificações do Windows.": "Reading Windows notifications.",
    "O Windows não deixou ler as notificações. Ative em Configurações → Privacidade e segurança → Notificações → “Permitir que aplicativos acessem suas notificações”. Enquanto isso, só o contador no título da aba (ex.: “(3) WhatsApp”) é usado.":
        "Windows did not allow reading notifications. Turn it on in Settings → Privacy & security → Notifications → “Allow apps to access your notifications”. Meanwhile, only the unread counter in the tab title (e.g. “(3) WhatsApp”) is used.",
    "Pacotes de notificação ausentes (veja requirements-extras.txt). Usando só o contador no título da aba, ex.: “(3) WhatsApp”.":
        "Notification packages are missing (see requirements-extras.txt). Using only the counter in the tab title, e.g. “(3) WhatsApp”.",
    "Não foi possível ler as notificações do Windows ({error}). Usando o contador do título da aba.":
        "Could not read Windows notifications ({error}). Using the tab-title counter.",
    "acesso negado pelo Windows": "access denied by Windows", "pacote ausente: {pkg}": "missing package: {pkg}",
    # ---- editor: static texts
    "Alternar modo claro e escuro": "Switch between light and dark mode",
    "Conectando…": "Connecting…", "Pré-visualização da tela": "Screen preview",
    "Esta página está vazia.": "This page is empty.", "Adicione módulos ao lado ou escolha um modelo abaixo.": "Add modules on the side or pick a template below.",
    "Mostrar grade": "Show grid",
    "Arraste para mover · puxe qualquer canto azul para redimensionar · clique fora para desmarcar · Alt+clique seleciona o de baixo · setas movem · Delete remove":
        "Drag to move · pull any blue corner to resize · click outside to deselect · Alt+click picks the one below · arrows move · Delete removes",
    "Módulos": "Modules", "Aparência": "Appearance", "Tela": "Screen", "Sistema": "System",
    "🌙 Modo escuro": "🌙 Dark mode", "☀ Modo claro": "☀ Light mode",
    "Encerrar": "Quit", "Idioma / Language": "Language / Idioma", "Idioma": "Language",
    # ---- editor: status
    "Salvando…": "Saving…", "Salvo ✓": "Saved ✓", "Erro ao salvar": "Save failed", "Não foi possível salvar: {msg}": "Could not save: {msg}",
    "Tela conectada": "Screen connected", "Sem tela · pré-visualização": "No screen · preview", "Programa não responde": "Program is not responding",
    "● Conectada": "● Connected", "● Sem tela": "● No screen",
    "Não foi possível falar com o programa: {msg}": "Could not talk to the program: {msg}",
    # ---- editor: pages
    "Duplo clique para renomear": "Double-click to rename", "Nome da página:": "Page name:", "+ Página": "+ Page",
    "Aplicar modelo…": "Apply template…", "Substituir os módulos desta página pelo modelo escolhido?": "Replace this page's modules with the chosen template?",
    "Esta página": "This page", "Nome": "Name", "Duração (segundos)": "Duration (seconds)", "Duração (só 1 página)": "Duration (only 1 page)",
    "Modelo": "Template", "Duplicar página": "Duplicate page", "Excluir página": "Delete page",
    "Trocar de página automaticamente": "Switch pages automatically",
    "Crie mais de uma página para alternar informações.": "Create more than one page to rotate information.",
    "Desligado: a tela fica sempre na primeira página (a que abre ao ligar).": "Off: the screen always stays on the first page (the one that opens at power-on).",
    "Máximo de 8 páginas.": "Maximum of 8 pages.", "{name} (cópia)": "{name} (copy)",
    "Excluir a página “{name}”?": "Delete the page “{name}”?",
    "Máximo de 32 módulos por página.": "Maximum of 32 modules per page.",
    # ---- editor: modules tab
    "sem arquivo": "no file", "em": "at", "(oculto)": "(hidden)", "Selecionar este módulo": "Select this module",
    "Mostrar na tela": "Show on screen", "Ocultar da tela (sem remover)": "Hide from the screen (without removing)",
    "Mostrar": "Show", "Ocultar": "Hide", "Trazer para frente": "Bring to front", "Enviar para trás": "Send to back",
    "Nesta página ({n})": "On this page ({n})", "De cima para baixo = da frente para o fundo. Clique para selecionar.":
        "Top to bottom = front to back. Click to select.",
    "Estilo dos indicadores": "Indicator style", "▬ Barras": "▬ Bars", "◔ Radial (círculos)": "◔ Radial (circles)",
    "Vale para CPU, GPU, VRAM, RAM e disco. Para mudar só um módulo, selecione-o e use “Estilo do indicador”. Para a disposição em anéis, use Modelo → “Anéis”.":
        "Applies to CPU, GPU, VRAM, RAM and disk. To change only one module, select it and use “Indicator style”. For the ring layout, use Template → “Rings”.",
    "Módulo selecionado": "Selected module", "Conteúdo": "Content", "Coluna": "Column", "Linha": "Row", "Largura": "Width", "Altura": "Height",
    "Medidas em células (1 célula = 40 px na tela).": "Sizes in cells (1 cell = 40 px on the screen).",
    "Duplicar": "Duplicate", "Trazer p/ frente": "Bring to front", "Enviar p/ trás": "Send to back", "Remover": "Remove",
    "Desenhar por cima dos outros": "Draw above the others",
    "Clique em um módulo na pré-visualização para editar, ou adicione um novo abaixo.": "Click a module in the preview to edit it, or add a new one below.",
    "Já há {n} na página: este botão adiciona mais um. Para editar o existente, use a lista “Nesta página”.":
        "There are already {n} on the page: this button adds another one. To edit the existing one, use the “On this page” list.",
    "Adicionar à página": "Add to page", "Adicionar módulo": "Add module", " (beta)": " (beta)", "card": "card", "cards": "cards",
    "Recursos ainda em ajuste: podem não funcionar em todos os computadores. Dentro desta categoria:":
        "Features still being tuned: they may not work on every computer. Inside this category:",
    "padrão": "default", "Usar padrão": "Use default", "Trocar imagem…": "Change image…", "Escolher imagem…": "Choose image…",
    "Usar uma imagem já enviada…": "Use an already uploaded image…",
    # ---- editor: appearance tab
    "Fundo": "Background", "Cor de fundo": "Background color", "Imagem de fundo": "Background image", "Escurecer a imagem": "Darken the image",
    "Ajuste da imagem": "Image fit", "Preencher (corta as bordas)": "Fill (crops the edges)", "Inteira (com bordas)": "Whole (with borders)",
    "Dica: com foto de fundo, ative os cartões translúcidos abaixo para manter o texto legível.":
        "Tip: with a background photo, turn on the translucent cards below to keep the text readable.",
    "Cartões atrás dos módulos": "Cards behind the modules", "Usar cartões": "Use cards", "Cor do cartão": "Card color", "Opacidade": "Opacity",
    "Cantos arredondados": "Rounded corners", "Cada módulo pode ignorar o tema em “Cartão de fundo”.": "Each module can ignore the theme under “Background card”.",
    "Texto e cores": "Text and colors", "Fonte": "Font", "Precisa estar instalada no Windows; se não estiver, uma fonte padrão é usada.":
        "It must be installed in Windows; if it is not, a default font is used.",
    "Texto principal": "Main text", "Texto secundário": "Secondary text", "Temperaturas": "Temperatures", "Alerta (uso acima de 90%)": "Alert (usage above 90%)",
    "Indicador dos módulos (CPU, GPU, RAM…)": "Module indicator (CPU, GPU, RAM…)", "Barras horizontais": "Horizontal bars", "Radial (círculos)": "Radial (circles)",
    "Vale para todos os módulos; cada módulo pode ter o seu próprio estilo nas opções dele (“Seguir o tema”, barra ou radial).":
        "Applies to all modules; each module can have its own style in its options (“Follow the theme”, bar or radial).",
    "Uma cor diferente por módulo": "A different color per module", "Cor de destaque única": "Single accent color",
    "Números com vírgula (11,4 GB)": "Decimal comma (11,4 GB) — Portuguese only",
    # ---- editor: screen tab
    "Envio médio para a tela: {n} KB/s (limite ≈ 128 KB/s).": "Average sent to the screen: {n} KB/s (limit ≈ 128 KB/s).",
    "central do Windows": "Windows notification center", "título da aba": "tab title",
    " Fonte: {src} · {n} pendente(s) agora.": " Source: {src} · {n} pending now.",
    "Automático (recomendado)": "Automatic (recommended)", " — {desc}": " — {desc}", "  ★ tela detectada": "  ★ screen detected",
    "{port} (não encontrada)": "{port} (not found)",
    "Reconectar": "Reconnect", "Atualizar portas": "Refresh ports", "Conexão": "Connection", "Porta": "Port", "Imagem": "Image",
    "Rotação da tela": "Screen rotation",
    "Se a imagem aparecer de cabeça para baixo, escolha a opção “invertida”. Ao mudar entre paisagem e retrato, os cards são reorganizados sem sobreposição e cada orientação lembra onde cada card ficou: voltar restaura o arranjo anterior.":
        "If the image appears upside down, choose the “flipped” option. When switching between landscape and portrait, cards are rearranged without overlapping and each orientation remembers where each card was: switching back restores the previous arrangement.",
    "Brilho": "Brightness", "Frequência de atualização dos números": "Number refresh rate",
    "Rápida (1 s)": "Fast (1 s)", "Normal (2 s) — recomendado": "Normal (2 s) — recommended", "Econômica (3 s)": "Economy (3 s)", "Lenta (5 s)": "Slow (5 s)",
    "Trocar de página automaticamente (com mais de uma página)": "Switch pages automatically (with more than one page)",
    "Desligado, a tela fica sempre na primeira página. O tempo de cada página é definido em “Esta página → Duração”.":
        "When off, the screen always stays on the first page. Each page's time is set in “This page → Duration”.",
    "Estabilidade dos números": "Number stability", "Tempo real (muda a cada leitura)": "Real time (changes on every reading)", "Suave": "Smooth",
    "Calma — menos redesenhos (recomendado)": "Calm — fewer redraws (recommended)",
    "A conexão USB desta tela é lenta (~130 KB/s): cada número que muda é redesenhado aos poucos na tela. “Calma” ignora oscilações pequenas (ex.: CPU 3%→4%) e muda os números só quando a diferença importa.":
        "This screen's USB link is slow (~130 KB/s): each number that changes is redrawn piece by piece. “Calm” ignores small fluctuations (e.g. CPU 3%→4%) and only changes the numbers when the difference matters.",
    "Notificações": "Notifications", "Mostrar notificações do Windows na tela": "Show Windows notifications on the screen",
    "Desligado por padrão: o texto das notificações pode ser privado. Ligado, o programa lê as notificações do Windows (WhatsApp Web no navegador, Discord, e-mail…) e mostra um aviso por alguns segundos por cima dos cards que tiverem “Mostrar avisos de notificação” marcado nas opções deles. Nada é gravado nem enviado para fora do computador.":
        "Off by default: notification text can be private. When on, the program reads Windows notifications (WhatsApp Web in the browser, Discord, e-mail…) and shows an alert for a few seconds over the cards that have “Show notification alerts” ticked in their options. Nothing is saved or sent outside the computer.",
    "Duração do aviso (segundos)": "Alert duration (seconds)", "Só destes aplicativos (separe por vírgula; vazio = todos)": "Only these apps (comma-separated; empty = all)",
    "Mostrar o texto da mensagem (desligado: só “Nova notificação” e o app)": "Show the message text (off: only “New notification” and the app)",
    "Testar aviso": "Test alert", "Aviso de teste enviado.": "Test alert sent.", "Avançado": "Advanced",
    "Brilho com escala invertida (se o brilho agir ao contrário)": "Inverted brightness scale (if brightness works backwards)",
    "Alinhamento das atualizações parciais (px)": "Partial-update alignment (px)", "8 — seguro (padrão)": "8 — safe (default)",
    "Menor = menos dados enviados, mas algumas telas desenham errado em áreas não alinhadas. Se a imagem quebrar, volte para 8.":
        "Smaller = less data sent, but some screens draw wrongly in unaligned areas. If the image breaks, go back to 8.",
    "Quadros por segundo (máx.)": "Frames per second (max.)",
    # ---- editor: system tab
    "CPU uso": "CPU usage", "CPU temperatura": "CPU temperature", "GPU uso": "GPU usage", "GPU temperatura": "GPU temperature",
    "Lendo sensores…": "Reading sensors…", "{name}: funcionando": "{name}: working", "{name}: não encontrado": "{name}: not found",
    "Inicialização": "Startup", "Iniciar com o Windows (em segundo plano)": "Start with Windows (in the background)",
    "O Rhino's Buddy Supervisor vai iniciar com o Windows.": "Rhino's Buddy Supervisor will start with Windows.", "Início automático desativado.": "Automatic start turned off.",
    "Ao ligar o PC, a tela passa a funcionar sozinha, sem abrir esta janela. Para editar, abra o Rhino's Buddy Supervisor novamente pelo atalho.":
        "When the PC starts, the screen works on its own without opening this window. To edit, open Rhino's Buddy Supervisor again from the shortcut.",
    "Disponível apenas no Windows (este computador não é Windows).": "Only available on Windows (this computer is not running Windows).",
    "Sensores de hardware": "Hardware sensors", "GPU NVIDIA via nvidia-smi": "NVIDIA GPU via nvidia-smi",
    "LibreHardwareMonitor (temperatura da CPU, GPU AMD/Intel)": "LibreHardwareMonitor (CPU temperature, AMD/Intel GPU)",
    "Para a temperatura da CPU: abra o LibreHardwareMonitor como administrador e ative Options → Remote Web Server → Run.":
        "For CPU temperature: open LibreHardwareMonitor as administrator and turn on Options → Remote Web Server → Run.",
    "Novidades": "What's new", "Mostrar as novidades na primeira abertura de cada versão": "Show what's new the first time each version is opened",
    "As novidades voltam a aparecer a cada atualização.": "What's new will show again after each update.", "As novidades não aparecem mais.": "What's new will no longer show.",
    "Ver novidades desta versão": "See what's new in this version", "Esta versão não tem novidades registradas.": "This version has no recorded notes.",
    "Programa": "Program", "Restaurar padrões": "Restore defaults", "Encerrar programa": "Quit program",
    "Restaurar o layout e a aparência padrão? Suas imagens enviadas são mantidas.": "Restore the default layout and appearance? Your uploaded images are kept.",
    "Padrões restaurados.": "Defaults restored.",
    "Versão {v}": "Version {v}", " · Seus dados ficam em ": " · Your data is stored in ",
    # ---- editor: pop-ups
    "Novidades da versão {v}": "What's new in version {v}", "Novidades": "What's new", "Não mostrar novamente": "Do not show again", "Entendi": "Got it",
    "Escolha o idioma": "Choose your language", "Você pode mudar depois no topo da página ou em Sistema → Idioma.":
        "You can change it later at the top of the page or in System → Language.",
    "Encerrar o Rhino's Buddy Supervisor?": "Quit Rhino's Buddy Supervisor?",
    "A tela deixará de ser atualizada e o programa será fechado. Para voltar a usar, abra-o novamente pelo atalho.":
        "The screen will stop updating and the program will close. To use it again, open it from the shortcut.",
    "Cancelar": "Cancel", "Rhino's Buddy Supervisor encerrado. Você pode fechar esta janela.": "Rhino's Buddy Supervisor has quit. You can close this window.",
}

# ---- templates: entries with {name} placeholders also match already formatted text
_PH = re.compile(r"\{(\w+)\}")


def _compile() -> list[tuple[re.Pattern, str]]:
    out = []
    for pt, en in EN.items():
        if not _PH.search(pt):
            continue
        parts, pos = [], 0
        for m in _PH.finditer(pt):
            parts.append(re.escape(pt[pos:m.start()]))
            parts.append(f"(?P<{m.group(1)}>.*?)")
            pos = m.end()
        parts.append(re.escape(pt[pos:]))
        out.append((re.compile("".join(parts), re.S), en))
    out.sort(key=lambda p: -len(p[0].pattern))  # most specific first
    return out


_TEMPLATES = _compile()


def _fill(template: str, values: dict) -> str:
    return _PH.sub(lambda m: str(values.get(m.group(1), m.group(0))), template)


def t(text, **values):
    """Translate a Portuguese source text (or fill ``{name}`` values into it).  Non-strings pass through."""
    if not isinstance(text, str) or not text:
        return text
    if values:
        return _fill(EN.get(text, text) if _lang == "en" else text, values)
    if _lang != "en":
        return text
    hit = EN.get(text)
    if hit is not None:
        return hit
    for rx, en in _TEMPLATES:
        m = rx.fullmatch(text)
        if m:
            return _fill(en, m.groupdict())
    return text


def t_deep(obj):
    """``t`` over every string inside dicts / lists (used for status messages)."""
    if isinstance(obj, str):
        return t(obj)
    if isinstance(obj, dict):
        return {k: t_deep(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [t_deep(v) for v in obj]
    return obj
