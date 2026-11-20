# Rhino's Buddy Supervisor v1.0.10 — tempo da música preciso

Substituto de código aberto (MIT) para o software da tela Turing Smart Screen 3,5": coloque o que quiser na segunda tela
(hardware, relógio, música, notificações, imagens) com um editor visual no navegador.

## Correções

- **Contador de tempo da música preciso.** Os segundos agora passam um a um, sem pular nem repetir:
  - o card de capa passou a conferir o tempo 4 vezes por segundo (antes, 1 vez), o que causava um segundo pulado ou repetido de vez em quando;
  - o programa só aceita um novo tempo do player quando ele realmente publicou um novo, e só confia na hora do Windows quando ela é recente e plausível (se vier em outro fuso ou atrasada, é ignorada);
  - pequenas diferenças são absorvidas aos poucos; avançar ou voltar a música é seguido na hora, e o contador nunca anda para trás por correção.

## Como atualizar

1. Baixe `RhinosBuddySupervisor-v1.0.10-windows.zip` abaixo e extraia numa pasta (pode ser por cima da anterior).
2. Abra `RhinosBuddySupervisor.exe`. Seu layout, imagens e configurações ficam em `%APPDATA%\RhinosBuddySupervisor` e são mantidos.
3. Para as funções de música e notificações, as dependências opcionais já vêm no executável. Rodando pelo código-fonte: `pip install -r requirements.txt -r requirements-extras.txt`.

## Requisitos e avisos

- Windows 10/11 e a tela Turing Smart Screen 3,5" (USB). Temperatura da CPU exige o LibreHardwareMonitor (instalação guiada em `docs/GUIA_GIT_E_LICENCAS.md`).
- O executável não é assinado: o Windows (SmartScreen) pode mostrar "aplicativo não reconhecido". É normal para programas novos e independentes.
- Recursos que dependem do Windows (música atual, notificações, captura de áudio, início automático) foram testados com simulações nos testes automáticos; se algo se comportar diferente no seu PC, abra uma *issue* com a versão (aba **Sistema**) e o que aconteceu.

## Licença

MIT. As bibliotecas de terceiros e suas licenças acompanham o programa em `THIRD_PARTY_NOTICES.md` e `THIRD_PARTY_LICENSES.txt`.
