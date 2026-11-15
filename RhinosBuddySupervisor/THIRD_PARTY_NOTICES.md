# Avisos de terceiros

O código do Rhino's Buddy Supervisor é licenciado sob a licença MIT (arquivo `LICENSE`).
Ele usa as bibliotecas abaixo, cada uma com a sua própria licença. Elas **não são copiadas para este
repositório**: são instaladas pelo `pip` (veja `requirements.txt` e `requirements-musica.txt`). Quando você
distribui o `.exe`, o `build_exe.bat` reúne os textos completos em `THIRD_PARTY_LICENSES.txt`.

## Bibliotecas Python incluídas no executável

| Biblioteca | Para que serve | Licença |
|---|---|---|
| [pyserial](https://github.com/pyserial/pyserial) | conversa com a tela pela porta COM | BSD-3-Clause |
| [Pillow](https://github.com/python-pillow/Pillow) | desenha as imagens da tela | MIT-CMU (HPND) |
| [NumPy](https://numpy.org) | cálculo de imagens e do áudio | BSD-3-Clause (e licenças permissivas de componentes) |
| [psutil](https://github.com/giampaolo/psutil) | uso de CPU, RAM, disco e rede | BSD-3-Clause |
| [SoundCard](https://github.com/bastibe/SoundCard) *(opcional, módulo Música)* | captura o áudio que sai nas caixas | BSD-3-Clause |
| [pywinrt](https://github.com/pywinrt/pywinrt) (`winrt-*`) *(opcional, módulo Música)* | lê a música que está tocando no Windows | MIT |

## Ferramenta de empacotamento (não vai dentro do programa)

- [PyInstaller](https://pyinstaller.org/en/stable/license.html): GPL-2.0 com exceção que permite distribuir os executáveis gerados
  com a licença que você quiser (a licença do PyInstaller não passa para o seu programa).

## Programas externos que o usuário instala por conta própria (nada deles é distribuído aqui)

- **[LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor)** (MPL-2.0): fornece temperaturas e outros sensores.
  O Rhino's Buddy Supervisor apenas lê a página local que ele publica (`http://127.0.0.1:8085/data.json`);
  não contém, não modifica e não redistribui o código dele.
- **nvidia-smi** (vem com o driver da NVIDIA): usado para uso e temperatura da GPU NVIDIA; é só executado, não é distribuído.
- **Microsoft Windows** e **Spotify**: o programa lê, pelas funções públicas do Windows, o título/artista/capa que o próprio sistema
  mostra no controle de mídia; nenhum material do Spotify é incluído.

## Fontes de letra

Nenhuma fonte é distribuída com o programa. Ele usa as que já existem no seu computador (por exemplo, Segoe UI).

## Marcas

"Turing Smart Screen", "UsbMonitor", "Spotify", "Windows", "NVIDIA", "AMD", "Intel", "Steam" e outros nomes citados pertencem aos
seus respectivos donos e aparecem aqui apenas para identificar hardware e programas compatíveis. Este projeto **não é afiliado,
patrocinado nem endossado** por nenhum deles.
