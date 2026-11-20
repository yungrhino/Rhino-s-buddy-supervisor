# Guia: instalar o LibreHardwareMonitor, publicar no Git e respeitar os direitos

Passo a passo para Windows (PowerShell). Faça na ordem. Onde aparecer `SEU-USUARIO`, use o seu nome de usuário do GitHub.

> Este guia reúne boas práticas comuns para projetos de código aberto. Não é aconselhamento jurídico: se for vender,
> registrar a marca ou usar em empresa, vale uma consulta com um advogado.

---

## Parte 1 — Instalar o LibreHardwareMonitor (temperaturas da CPU e outros sensores)

O programa já mostra uso de CPU, RAM, disco e rede sozinho, e uso/temperatura de GPU NVIDIA pelo `nvidia-smi`. Para a **temperatura da CPU**
(e sensores de GPU AMD/Intel) você precisa do LibreHardwareMonitor, um programa separado, gratuito e de código aberto (licença MPL-2.0).

1. **Baixe só pelo site oficial**: https://github.com/LibreHardwareMonitor/LibreHardwareMonitor → aba **Releases** → baixe o `.zip` da versão mais recente.
   O projeto avisa que o site *librehardwaremonitor.com* **não** é afiliado a ele e deve ser evitado.
2. Extraia o zip numa pasta fixa, por exemplo `C:\Program Files\LibreHardwareMonitor` ou `Documentos\LibreHardwareMonitor`.
3. Clique com o botão direito em `LibreHardwareMonitor.exe` → **Executar como administrador**. Sem administrador, vários sensores de CPU não aparecem.
4. No menu, vá em **Options → Remote Web Server → Run** (deixe marcado). A porta padrão é **8085**.
5. Se o Firewall do Windows perguntar, **não libere para nenhuma rede** (clique em Cancelar). O Rhino's Buddy Supervisor lê pelo próprio computador
   (`127.0.0.1`), então não precisa de acesso externo, e assim a página de sensores não fica visível para outros aparelhos da sua rede.
6. Teste: abra no navegador `http://127.0.0.1:8085/data.json`. Deve aparecer um texto grande em JSON.
7. No Rhino's Buddy Supervisor, abra **Sistema** (ou rode `python -m rhinos_buddy sensors`): CPU temperatura deve mostrar um número.
8. Para abrir sozinho com o Windows: no LibreHardwareMonitor, **Options → Run On Windows Startup** (e, se quiser, *Start Minimized* e *Minimize To Tray*).

Observações:
- O LibreHardwareMonitor usa um driver para ler os sensores. Versões antigas do driver (WinRing0) são marcadas como ameaça pelo Windows Defender
  e já causaram avisos de antivírus em vários programas de monitoramento. Use sempre a versão mais recente e leia as notas da versão se o Windows reclamar.
- Nada do LibreHardwareMonitor vai dentro do seu projeto: o usuário instala por conta própria. Por isso não há obrigação de redistribuir o código dele.

---

## Parte 2 — Antes de publicar: o que pode e o que não pode ir para o repositório

**Pode (já está pronto):** todo o código em `rhinos_buddy/`, `tests/`, `tools/`, `examples/`, os `.bat`, `README.md`, `LICENSE`, `THIRD_PARTY_NOTICES.md`, `rhinos_buddy.ico`.

**Não pode / não deve ir (o `.gitignore` já bloqueia a maioria):**

| Item | Por quê |
|---|---|
| A pasta/zip do software original da tela (`35inchENG`, `UsbMonitor.exe`, temas, imagens dele) | é de terceiros; o projeto foi escrito do zero e não deve conter nada dali |
| Capas de álbum, logos de jogos (CS2 etc.), prints com conteúdo de terceiros | direitos autorais e marcas; em prints do README use imagens suas ou fundos genéricos |
| Seu `layout.json`, fotos de fundo, GIFs e vídeos pessoais | dados pessoais; ficam em `%APPDATA%\RhinosBuddySupervisor`, fora do projeto |
| O `.exe` e a pasta `dist/` | binários vão na aba **Releases**, não no histórico do Git |
| Senhas, tokens, e-mail pessoal | nunca em arquivos; veja a Parte 3 sobre o e-mail dos commits |

**Conferências rápidas (5 minutos):**
1. Abra o `LICENSE`. Está com "Rhino's Buddy Supervisor contributors". Se preferir, troque pelo seu nome ou apelido (`Copyright (c) 2026 Seu Nome`): é você quem detém os direitos do que escreveu.
2. Pesquise o nome **Rhino's Buddy Supervisor** antes de divulgar: no GitHub (para não duplicar repositório) e na busca de marcas do INPI. Nome em uso por outra empresa na mesma área pode dar problema; se for só um projeto pessoal, o risco é baixo.
3. Confirme que não há dados seus nos arquivos: `Get-ChildItem -Recurse -File | Select-String -SimpleMatch "seu-email@exemplo.com","C:\Users\"` (não deve achar nada).
4. A licença **MIT** permite que qualquer pessoa use, copie, modifique e venda o código, desde que mantenha o aviso de copyright. Se você prefere impedir uso comercial fechado, outra licença (por exemplo GPL) seria melhor; a decisão é sua.

**Sobre as bibliotecas:** elas ficam fora do repositório (instaladas pelo `pip`). O arquivo `THIRD_PARTY_NOTICES.md` lista cada uma e a licença. Ao distribuir o `.exe`, as licenças delas exigem que o texto acompanhe o programa:
o `build_exe.bat` já faz isso gerando `THIRD_PARTY_LICENSES.txt` na pasta do executável.

---

## Parte 3 — Instalar e configurar o Git

1. Instale o Git: https://git-scm.com/download/win (ou, no PowerShell, `winget install --id Git.Git -e`). Feche e reabra o PowerShell.
2. Crie a conta no GitHub (https://github.com) se ainda não tiver.
3. **Proteja o seu e-mail:** no GitHub, **Settings → Emails**, marque *Keep my email addresses private* e *Block command line pushes that expose my email*.
   Anote o endereço `NUMEROS+SEU-USUARIO@users.noreply.github.com` que aparece ali.
4. Configure a identidade do Git usando esse endereço (assim seu e-mail real não fica gravado no histórico público):
   ```powershell
   git config --global user.name "Seu Nome ou Apelido"
   git config --global user.email "NUMEROS+SEU-USUARIO@users.noreply.github.com"
   git config --global init.defaultBranch main
   ```

---

## Parte 4 — Primeiro commit

1. Entre na pasta do projeto (a que contém `README.md`, `rhinos_buddy/` e `run_app.py`):
   ```powershell
   cd "C:\caminho\para\RhinosBuddySupervisor"
   ```
2. (Opcional, recomendado) rode os testes: `python -m pip install -r requirements.txt pytest` e `python -m pytest tests -q` (devem passar todos).
3. Crie o repositório local e veja o que será incluído:
   ```powershell
   git init
   git status
   ```
   Confira a lista: **não pode** aparecer `dist/`, `build/`, `layout.json`, `.exe`, vídeos ou a pasta do software original. Se aparecer, pare e me avise (ou ajuste o `.gitignore`).
4. Adicione e confira:
   ```powershell
   git add .
   git status
   git diff --cached --stat
   ```
5. Faça o commit:
   ```powershell
   git commit -m "Versão inicial do Rhino's Buddy Supervisor" -m "Editor visual com slots, monitor de hardware em português, módulo de música, anéis radiais, início com o Windows."
   ```
6. Confira o autor gravado: `git log -1 --format="%an <%ae>"` deve mostrar o e-mail `noreply`.

---

## Parte 5 — Publicar no GitHub

1. No GitHub: **New repository**. Nome sugerido: `rhinos-buddy-supervisor`. Deixe **vazio**: não marque *Add a README*, *.gitignore* nem *license* (já existem no projeto). Escolha **Public** para código aberto.
2. Conecte e envie:
   ```powershell
   git remote add origin https://github.com/SEU-USUARIO/rhinos-buddy-supervisor.git
   git push -u origin main
   ```
   Na primeira vez abre uma janela do navegador para entrar na conta (Git Credential Manager). Não use a senha da conta em linha de comando.
3. No repositório, **About** (engrenagem): descrição curta e tópicos (`python`, `usb-display`, `hardware-monitor`). O GitHub reconhece a licença MIT sozinho pelo `LICENSE`.
4. Aba **Actions**: o arquivo `.github/workflows/tests.yml` roda os testes a cada push, no Windows e no Linux. O ícone verde indica que está tudo certo.

---

## Parte 6 — Publicar uma versão com o `.exe` (Release)

1. No Windows, dê duplo clique em `build_exe.bat`. Ele instala as dependências, gera `dist\RhinosBuddySupervisor\RhinosBuddySupervisor.exe` e coloca `LICENSE`,
   `THIRD_PARTY_NOTICES.md` e `THIRD_PARTY_LICENSES.txt` na mesma pasta. Teste abrindo o `.exe` antes de publicar.
2. Compacte a pasta inteira `dist\RhinosBuddySupervisor` em `RhinosBuddySupervisor-v1.0.6-windows.zip`.
3. Crie a marca de versão:
   ```powershell
   git tag -a v1.0.6 -m "Versão 1.0.6"
   git push origin v1.0.6
   ```
4. No GitHub: **Releases → Draft a new release**, escolha a tag `v1.0.6`, escreva as novidades e **anexe o zip**. Avise que o Windows (SmartScreen) pode mostrar
   "aplicativo não reconhecido" porque o executável não é assinado; isso é normal para programas novos e independentes.

---

## Parte 7 — No dia a dia

```powershell
git status                      # o que mudou
git add rhinos_buddy tests      # escolha o que entra (ou: git add .)
git commit -m "Descreve o que mudou"
git push
```
- Faça commits pequenos, um assunto por vez. Para testar algo arriscado: `git switch -c minha-ideia`, e depois abra um Pull Request.
- Nova versão: aumente `version` em `pyproject.toml` e `__version__`/`__version_title__` em `rhinos_buddy/__init__.py` (o título curto aparece na aba Sistema), faça commit, gere o `.exe` e repita a Parte 6 com a tag nova.
- A cada versão há um arquivo `docs/releases/vX.Y.Z.md` com as notas prontas: copie o conteúdo para o campo de descrição da Release no GitHub e atualize `docs/releases/HISTORICO.md`.
- Se alguém mandar código para o projeto, ele passa a ser licenciado sob a MIT também (é o padrão do GitHub); confira de onde veio antes de aceitar.
- Se um dia você commitar algo por engano (senha, arquivo de terceiros), **não basta apagar no commit seguinte**: o histórico guarda. Avise-me e eu explico como remover.

---

## Checklist final antes do primeiro `git push`

- [ ] `git status` não mostra `dist/`, `build/`, `layout.json`, `.exe`, vídeos nem arquivos do software original da tela
- [ ] Nenhuma imagem de terceiros (capas de álbum, logos de jogos) nos arquivos nem nos prints do README
- [ ] `git log -1 --format="%ae"` mostra o e-mail `noreply`, não o pessoal
- [ ] `LICENSE` com o nome/apelido que você quer
- [ ] Nome do projeto pesquisado
- [ ] Testes passando (`python -m pytest tests -q`)
- [ ] Na Release: o zip contém `LICENSE`, `THIRD_PARTY_NOTICES.md` e `THIRD_PARTY_LICENSES.txt`
