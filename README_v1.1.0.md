# Rhino's Buddy Supervisor v1.1.0 — modo claro e cards em teste

Substituto de código aberto (MIT) para o software da tela Turing Smart Screen 3,5": coloque o que quiser na segunda tela
(hardware, relógio, música, notificações, imagens) com um editor visual no navegador.

## Novidades

- **Modo claro e modo escuro** no editor. O botão fica no topo da página; a escolha é lembrada e, na primeira vez, segue o tema do seu sistema.
- **Categoria "Em teste"** na lista de módulos (aba Módulos → Adicionar módulo). É expansível e mostra o que tem dentro. Por enquanto guarda o card de **Notificações (lista)**, que ainda está em ajuste e pode não funcionar em todos os computadores.
- **Alinhamento do texto no card de Notificações** (esquerda, centro ou direita). O aviso que aparece por cima dos outros cards segue o alinhamento do próprio card.
- **Preview mais prático:**
  - clique fora do card (na área ao redor da tela) para desmarcá-lo;
  - dá para redimensionar o card puxando **qualquer um dos quatro cantos**, não só o inferior direito.
- **Pop-up de novidades** na primeira abertura de cada versão, com a opção "Não mostrar novamente". Ele não volta a aparecer quando você só abre o programa de novo sem atualizar. Dá para religar, ou rever as notas, em **Sistema → Novidades**.
- **Desinstalador incluído** (`Desinstalar Rhinos Buddy Supervisor.bat`): fecha o programa, remove o início automático e apaga a pasta do programa. Seus dados são mantidos por padrão, o que facilita atualizar (veja abaixo).

## Correções

- **Trocar a orientação da tela (paisagem ⇄ retrato) não bagunça mais os cards.** Eles são reorganizados para a nova grade sem se sobrepor nem sair da tela, e cada card lembra onde estava em cada orientação: voltar restaura o arranjo anterior exatamente.

## Como atualizar

1. Na pasta da versão antiga, dê duplo clique em **`Desinstalar Rhinos Buddy Supervisor.bat`** e escolha **1 (Atualizar)**. Seus dados (layout, imagens e configurações em `%APPDATA%\RhinosBuddySupervisor`) são mantidos.
2. Baixe `RhinosBuddySupervisor-v1.1.0-windows.zip` abaixo, extraia onde quiser e abra `RhinosBuddySupervisor.exe`.

Sem o desinstalador (versões anteriores): feche o programa, extraia o zip por cima ou em outra pasta e abra o novo executável; os dados continuam no mesmo lugar.

## Requisitos e avisos

- Windows 10/11 e a tela Turing Smart Screen 3,5" (USB). A temperatura da CPU exige o LibreHardwareMonitor (instalação guiada em `docs/GUIA_GIT_E_LICENCAS.md`).
- Para o card de Notificações ler o Windows: *Configurações → Privacidade e segurança → Notificações → "Permitir que aplicativos acessem suas notificações"*. Sem a permissão, só o contador no título da aba (ex.: "(3) WhatsApp") é usado.
- O executável não é assinado: o Windows (SmartScreen) pode mostrar "aplicativo não reconhecido". É normal para programas novos e independentes.
- O desinstalador e as funções que dependem do Windows (música atual, notificações, captura de áudio, início automático) ainda não foram executados num PC real: os testes automáticos só conferem o conteúdo do `.bat` e simulam o resto. Por segurança, o desinstalador só apaga a pasta se ela tiver o `RhinosBuddySupervisor.exe`, e pergunta antes de apagar qualquer coisa. Se algo se comportar diferente no seu PC, abra uma *issue* com a versão (aba **Sistema**) e o que aconteceu.

## Licença

MIT. As bibliotecas de terceiros e suas licenças acompanham o programa em `THIRD_PARTY_NOTICES.md` e `THIRD_PARTY_LICENSES.txt`.
