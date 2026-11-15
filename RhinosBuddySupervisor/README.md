# Rhino's Buddy Supervisor

Programa de código aberto (MIT) para telas secundárias USB de 3,5" (família Turing Smart Screen): você decide o que aparece na telinha.

## Aplicativo com janela (recomendado)

Um programa com editor visual: pré-visualização ao vivo, **módulos em slots** que você arrasta e redimensiona,
**imagem de fundo**, várias páginas, escolha da porta/rotação/brilho e **início com o Windows**.

**Gerar o executável** (uma vez, no Windows, com Python instalado): dê duplo clique em `build_exe.bat`.
Ele cria `dist\RhinosBuddySupervisor\RhinosBuddySupervisor.exe` (e, se quiser, um atalho na Área de Trabalho).
Sem gerar o `.exe`, `Iniciar Rhinos Buddy Supervisor.bat` abre o mesmo programa direto do código.

- Abrir o programa: a janela do editor aparece; abrir de novo apenas traz a janela do que já está rodando.
- **Sistema → Iniciar com o Windows** liga a tela sozinha no login, em segundo plano (sem janela).
- Suas configurações ficam em `%APPDATA%\RhinosBuddySupervisor` (`layout.json`, `media\`, `rhinos_buddy.log`).
- A tela é redesenhada com o que você montou; se o cabo for desconectado, ela reconecta sozinha.
- Segurança: o editor só atende em `127.0.0.1`, recusa outros sites (Host/CSRF) e só aceita imagens.

- **Aba Tela → Estabilidade dos números:** cada número que muda é redesenhado aos poucos (o link USB é lento),
  então o padrão "Calma" ignora oscilações pequenas (CPU 3%→4%, ±1 °C, rede ±50%). No teste simulado de
  mesa ociosa isso caiu de ~2,8 para ~0,2 atualizações/s. "Tempo real" mostra toda leitura.
  Ainda aparece o redesenho progressivo quando um número muda de fato: é o limite do hardware, não tem como zerar.

- **Indicador radial:** em **Aparência → Indicador dos módulos** escolha barras horizontais ou círculos para todos os
  módulos (CPU, GPU, VRAM, RAM, disco); cada módulo ainda pode ter o seu próprio estilo nas opções dele. Há também o botão "Radial" no topo da aba Módulos e o modelo **Anéis** (Modelo → Anéis).
- **Módulo Música:** mostra o que está tocando (título e artista) e/ou um visualizador de áudio (barras, espelhado,
  circular ou pulso na batida), com tamanho livre na grade. Cada parte liga/desliga nas opções do módulo.
  Ele só funciona com os pacotes opcionais de `requirements-extras.txt` (`build_exe.bat` já tenta instalá-los):
  `soundcard` captura o que sai nas caixas/fones (qualquer player) e `winrt-*` lê a música atual do Windows.
  Sem eles, o Spotify ainda é lido pelo título da janela e o visualizador fica parado, com um aviso.
  No módulo, "Aparência do que está tocando" tem o modo **Card expandido**: capa do álbum, título, artista e barra
  de progresso com os tempos (capa e tempos vêm do Windows e dependem do player informá-los; o Spotify informa).
  O **Visualizador de áudio** também existe como card separado (grupo "Música" na lista de módulos), só com o espectro, sem o título da música.
  O visualizador acompanha o dispositivo de saída padrão do Windows: ao conectar um fone Bluetooth ou trocar de caixa, a captura muda sozinha em cerca de 1 segundo.
  A captura só roda enquanto há um visualizador visível na tela. Por causa do link USB lento, o programa limita
  sozinho a taxa de redesenho pelo tamanho da área: slots pequenos (ex. 2x1 células) são mais fluidos que grandes.

- **Notificações (WhatsApp Web, Discord etc.):** desligadas por padrão, porque o texto de um aviso pode ser privado.
  Ligue em **Tela → Mostrar notificações do Windows na tela**. Todo card tem a opção **Mostrar avisos de notificação neste card** (nas opções dele): quando chega um
  aviso, o card dá lugar a um cartão com o app, o título e a mensagem por alguns segundos e depois volta sozinho ao
  que estava mostrando (o visualizador volta a tocar, por exemplo). O módulo **Notificações** mostra a lista dos
  avisos recentes. Nada é enviado para fora do computador.
  - De onde vêm: da central de notificações do Windows (precisa dos pacotes de `requirements-extras.txt` e de
    *Configurações → Privacidade e segurança → Notificações → "Permitir que aplicativos acessem suas notificações"*).
    Para o WhatsApp Web, ative as notificações do site no navegador.
  - Sem permissão ou pacotes, o programa usa só o contador do título da aba (ex.: "(3) WhatsApp"), que vê apenas a
    aba visível e não mostra quem escreveu. A mensagem em **Tela → Notificações** diz qual modo está ativo.
  - Use **Testar aviso** para ver como fica sem esperar uma mensagem real. Também dá para filtrar por app e
    esconder o texto (mostrar só "Nova notificação").

- **Lista "Nesta página"** (aba Módulos): mostra tudo o que está na tela, da frente para o fundo. Clique para
  selecionar (mesmo que um módulo de tela cheia cubra os outros), reordene com ▲▼ ou use **Ocultar** para tirar
  um módulo da tela sem apagar. Alt+clique na pré-visualização seleciona o módulo que está embaixo.
- **Trocar de página automaticamente:** a chave fica no cartão "Esta página". Desligada, a tela fica sempre na primeira página.

**Veio do nome antigo ("Subscreen")?** Na primeira abertura o programa copia suas configurações e imagens da pasta antiga e troca a entrada de "Iniciar com o Windows" para a nova; nada é apagado. Depois de gerar o novo `.exe`, você pode apagar a pasta `dist\Subscreen` antiga.

Linha de comando (avançado): `python run_app.py [--background] [--no-hardware] [--port N]`.

---

# Versão por linha de comando

Software open source (MIT) para telas secundárias USB de 3,5" (família Turing Smart Screen): **você decide o que aparece na telinha**.

Escrito do zero em Python. Nenhum código, tema ou imagem do software que acompanha a tela foi copiado.

## Instalação

```
pip install -r requirements.txt
```

## Testar sem a tela (simulador)

```
python -m rhinos_buddy run -c examples/config.toml --simulator --http 8080
```

Abra http://127.0.0.1:8080 para ver a tela ao vivo (ou o arquivo `preview.png`).

## Usar na tela real

1. **Feche o `UsbMonitor.exe` original** (só um programa pode abrir a porta COM).
2. Descubra a porta: `python -m rhinos_buddy ports` (o Windows 10 não precisa de driver).
3. Edite `[device]` em `examples/config.toml` (`port = "COM5"`) e rode:
   ```
   python -m rhinos_buddy run -c examples/config.toml
   ```

Comandos soltos: `image foto.png`, `clear`, `brightness 40`, `hello`.

## O que pode ir na tela

| `type`       | O que faz |
|--------------|-----------|
| `text`       | texto com variáveis: `"CPU {cpu:.0f}%"`, `{ram}`, `{ram_used_gb}`, `{disk}`, `{net_down_kbs}`, `{net_up_kbs}`, `{cpu_temp}`, `{battery}`, `{now:%H:%M}` |
| `clock`      | hora/data (`format` strftime) |
| `bar`, `graph` | barra e gráfico de qualquer métrica |
| `image`      | PNG/JPG/GIF animado; se outro programa sobrescrever o arquivo, a tela atualiza |
| `web_image`  | imagem de uma URL a cada N segundos (câmera, mapa, Grafana) |
| `command`    | roda **qualquer comando/script** e mostra a saída (texto, ou imagem com `mode = "image"`) |
| `file`       | últimas linhas de um arquivo de texto/log |
| `http_json`  | valor de uma API JSON |
| `plugin`     | seu próprio Python com Pillow (veja `examples/plugins/hello_plugin.py`) |
| `rect`       | cartões/painéis |

Várias `[[page]]` alternam sozinhas (`duration`). Só as áreas que mudaram são enviadas por USB, o que deixa tudo fluido.

## Monitor em português (CPU/GPU, temperaturas, RAM, rede, data e hora)

```
python -m rhinos_buddy run -c examples/config_pt.toml
```

- **GPU NVIDIA:** uso e temperatura via `nvidia-smi` (já vem com o driver), sem instalar nada.
- **Temperatura da CPU (e GPU AMD/Intel):** instale o [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor),
  abra **como administrador** e ative *Options > Remote Web Server > Run* (porta 8085).
- `python -m rhinos_buddy sensors` mostra o que foi encontrado. Sensor indisponível aparece como `--`.
- Textos aceitam `{dia_semana}`, `{dia_semana_cap}`, `{mes}`, `{dia}`, `{ano}` em português e `decimal = ","`.

## Velocidade e "scanlines"

Medido em uma tela real: **~128 KB/s fixos** (um quadro 480x320 inteiro = 2,4 s), igual para qualquer
`baud` e `chunk_lines`. As "scanlines" são o próprio quadro sendo transferido. Para reduzir:

1. Envie menos pixels: fundo estático e só pequenas áreas dinâmicas (relógio, barras, texto).
2. GIFs/vídeos: use áreas pequenas (`w`/`h`) e `fit = "contain"`. Orçamento: ~64 mil pixels/s
   (ex.: 120x120 a ~4 quadros/s). O GIF toca em tempo real, descartando quadros se o link não der conta.
3. Só os pixels que mudaram são enviados (automático).

`python -m rhinos_buddy bench` mede a velocidade da sua tela; `rotate` (retrato + giro por software) existe
mas não ajuda neste hardware.

## Protocolo (resumo)

Serial USB-CDC, pacotes de 6 bytes com coordenadas de 10 bits empacotadas e comando no último byte (`0xC5` = desenhar bitmap, seguido de pixels RGB565 little-endian; `0x79` orientação; `0x6E` brilho). Está em `rhinos_buddy/protocol.py`, coberto por testes.

## Estado e limitações

- O protocolo foi validado em uma tela real (Turing 3,5" Rev A, porta COM, serial `USB35INCHIPSV2`). Outras revisões de painel podem ter protocolos ligeiramente diferentes: se a imagem sair torta, com cores trocadas ou nada aparecer, rode `python -m rhinos_buddy ports` e `python -m rhinos_buddy hello` e abra uma issue com a saída.
- Temperatura de CPU só funciona onde o `psutil` expõe sensores (Linux). No Windows, use um `plugin`/`command` lendo o LibreHardwareMonitor.

## Testes

```
pip install pytest && python -m pytest tests
```

## Licença, marcas e privacidade

- **Licença:** MIT (arquivo `LICENSE`). As bibliotecas de terceiros e os programas externos citados estão em
  [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md); o `.exe` gerado leva os textos completos em `THIRD_PARTY_LICENSES.txt`.
- **Marcas:** "Turing Smart Screen", "UsbMonitor", "Spotify", "Windows", "NVIDIA" etc. pertencem aos seus donos e são citadas só para
  identificar produtos compatíveis. O projeto não é afiliado a nenhum deles.
- **Privacidade:** tudo roda no seu computador. O editor só atende em `127.0.0.1`, não há telemetria, conta ou envio de dados. A única
  conexão de rede opcional é a leitura do LibreHardwareMonitor local (`127.0.0.1:8085`) e os widgets de URL que você mesmo configurar.
- **Publicar no GitHub e instalar o LibreHardwareMonitor:** veja [`docs/GUIA_GIT_E_LICENCAS.md`](docs/GUIA_GIT_E_LICENCAS.md).
