# Pesquisa: integração local com Google Flow

> Escopo atualizado em 29/09/2026: o projeto atual é um MCP independente e abrangente do Flow, com múltiplas contas. A integração com MoneyPrinterTurbo será posterior. Esta pesquisa inicial permanece como histórico das bases; o inventário atual e a análise de contas ficam em `docs/FLOW-RECURSOS.md` e `docs/9ROUTER-CONTAS.md`.

Data: 2026-09-29. Verificação documental e leitura de código público; nenhuma instalação, execução de projeto externo, geração ou consumo de créditos.

## Objetivo confirmado

Um agente ou a automação local do usuário deve criar vídeos no Google Flow usando os créditos da própria conta, acompanhar o processamento, baixar o resultado e entregá-lo ao fork de MoneyPrinterTurbo. O plano informado é **Google AI Pro**. Geração de imagens é secundária. O projeto roda localmente; MCP local é uma opção adequada. As respostas desta sessão devem ser em português do Brasil. O usuário pediu registro no AI Memory, com workspace/project `google_flow_mcp`; a gravação nessa memória é tratada pelo agente principal.

Pendências para implementação: cliente/agente MCP; acesso efetivo da conta ao Flow; navegador e fronteira Windows/WSL; interface da conta (compositor clássico ou somente agente); regra de autorização e limite de gasto por execução. O agente principal localizou um clone do fork em diretório de trabalho dedicado com muitas alterações preexistentes; elas devem ser preservadas.

## Resultado

Já existem MCPs comunitários para o Flow. A premissa de ausência de um MCP oficial não impede uma conexão: estes projetos operam a sessão autenticada do site. A disponibilidade e a compatibilidade na conta do usuário continuam sem teste.

**A escolha depende da interface da conta; ainda não há vencedor validado.** Se ela oferecer o compositor clássico, o primeiro candidato é uma versão publicada e fixada do **gflow-cli**: já oferece MCP, jobs persistentes e downloads, além de tratar dois hosts do Flow. Se a conta só oferecer agente, gflow pode abortar antes de gerar; **miyakejima/google-flow-mcp** passa a ser o candidato mais enxuto, mas exige rever sua alteração automática das confirmações de gasto. Não recomendo começar copiando um servidor inteiro ou escrevendo um MCP do zero antes dessa validação.

## API oficial e créditos

A API Gemini oferece geração de vídeo com Veo e acompanhamento de operações. Porém, os planos Google AI e a API Gemini têm faturamento separado: utilizar a API oficial não significa utilizar os créditos do Flow da assinatura. Como o usuário confirmou que os créditos do Flow são requisito, a API oficial permanece uma alternativa apenas se ele aceitar outra cobrança. [Planos Google AI e API Gemini](https://ai.google.dev/gemini-api/docs/google-ai-plans?hl=pt-br), [geração de vídeo na API Gemini](https://ai.google.dev/gemini-api/docs/video), [créditos do Flow](https://support.google.com/flow/answer/16526234?hl=pt-BR).

## Comparação das bases

| Base | Caminho observado | Autenticação | Jobs e arquivos | Dependências principais | Avaliação |
| --- | --- | --- | --- | --- | --- |
| [gflow-cli](https://github.com/ffroliva/gflow-cli) | Playwright/UI; observação de respostas internas e download autenticado | Chrome real/perfil persistente; login próprio documentado | Fila SQLite, IDs de tarefas, opção `wait=false`, arquivos locais | Python ≥3.11; Playwright, SDK MCP, HTTPX, FastAPI e outras | Primeiro candidato a validação; mais amplo e maior |
| [miyakejima](https://github.com/miyakejima/google-flow-mcp) | Playwright/UI; download pela URL da mídia | Extensão transfere cookies para perfil isolado; CDP localhost opcional | JSON persistente por job, polling e downloads rastreados | Node ≥20; SDK MCP, Playwright, Zod | Boa base compacta, com revisão do gasto e da extensão |
| [GabrielGargiuloDev](https://github.com/GabrielGargiuloDev/google-flow-mcp) | Playwright/CDP; geração pelo agente do site; download tRPC | Sessão Chrome autenticada via CDP | Fila em memória e metadados em disco; geração bloqueante | Node ≥18; SDK MCP, Playwright, Zod | Simples, mas frágil para automação recuperável e pt-BR |
| [roshanarnav25-sloth](https://github.com/roshanarnav25-sloth/google-flow-mcp) | tRPC para leitura/download; geração ainda via DOM | Sessão Chrome via CDP | Ledger e orçamento em disco; coleta por diferença de IDs | Node ≥20; SDK MCP, Playwright-core, Zod | Ideias de orçamento úteis; garantia de custo exige revisão |

As quatro bases contêm licença MIT. Isso cobre o código do projeto, não concede autorização ou estabilidade de integração com o serviço do Google. [Licença gflow-cli](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/LICENSE), [licença miyakejima](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/LICENSE), [licença Gabriel](https://github.com/GabrielGargiuloDev/google-flow-mcp/blob/aae58a79aecd640a00f853e454e16e101bb7a756/LICENSE), [licença roshan](https://github.com/roshanarnav25-sloth/google-flow-mcp/blob/0e4c8b36e844860dea7c41a315524fd7d652b32c/LICENSE).

## Evidências que mudam a escolha

### gflow-cli

O MCP `gflow_generate_video` realmente valida parâmetros e passa pelo fluxo de tarefas. A fila usa SQLite e transações para reivindicar uma tarefa pendente; não é só uma lista de ferramentas prometida no README. O transporte de vídeo tem roteamento específico para `flow.google.com`, além do caminho `labs.google`. Esse cuidado é relevante porque outras bases examinadas fixam a origem antiga. [Ferramenta de vídeo](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L993), [fila persistente](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/worker/queue.py#L99), [transporte de vídeo](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/api/transports/ui_automation_video.py#L3970).

Há uma limitação decisiva: `gflow_generate_video` rejeita explicitamente `ui_mode="agentic"`; não podemos assumir que funcione no modo com agente disponível na conta do usuário. Também não há parâmetro obrigatório de confirmação de gasto na assinatura dessa ferramenta. O modo `--no-spend` remove as ferramentas de geração do registro e é apropriado para a inspeção inicial; não resolve sozinho a autorização de uma geração paga. [Validação de modo](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L1118), [política no-spend](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/server.py#L126).

O projeto declara estado alpha, limitações por interface e versões de Playwright restritas. Seu guia MCP documenta falha na interface somente agente sem acesso ao compositor clássico; a leitura de créditos por endpoint antigo também pode falhar em conta migrada, sem solução por novo login. A branch padrão é `develop`: para validação, selecionar uma release publicada e fixar a versão, sem confundir documentação dessa branch com uma release testada por nós. Não precisamos do HTTP, armazenamento remoto, criação de personagens ou composição de filmes no primeiro teste. [Manifesto de dependências](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/pyproject.toml#L55), [limitações documentadas](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/KNOWN_ISSUES.md), [guia MCP](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/docs/MCP.md).

### miyakejima/google-flow-mcp

O código cria um job em disco antes de submeter, registra a linha de base das mídias e permite acompanhar o mesmo job. Faz download das identidades rastreadas, sem simplesmente escolher o último cartão da galeria. Isso atende diretamente ao ciclo geração → processamento → arquivo. [Fluxo de geração e polling](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/flow-adapter.ts#L327), [persistência](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/store.ts#L231), [download rastreado](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/flow-adapter.ts#L1240).

O guard do MCP exige `confirmCreditSpend: true`, mas o adaptador chama `ensureAgentAutoApprove`, grava `AUTO_APPROVE` nas configurações do Flow e seleciona aprovação persistente se necessário. Isso altera a preferência de confirmação da conta/perfil e não representa um teto numérico de gasto. Não adotar esse comportamento automaticamente. A extensão lê cookies Google, embora o bridge restrinja o destino a localhost e valide o payload; essa superfície merece revisão. [Guard MCP](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/index.ts#L66), [AUTO_APPROVE](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/flow-adapter.ts#L887), [bridge de cookies](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/cookie-bridge.ts).

README e package.json apontam para `retrolyze52/google-flow-mcp`, enquanto a URL pesquisada é `miyakejima/google-flow-mcp`. Confirmar procedência antes da instalação. O detector separa Windows e Linux; não inferir suporte automático a Chrome Windows a partir de Node executado em WSL. [Manifesto](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/package.json), [detecção de navegador](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/browser-manager.ts#L26).

### GabrielGargiuloDev/google-flow-mcp

A geração de vídeo coloca modelo e duração num prompt em italiano para o agente do Flow. `auto_confirm` impede submissão enquanto falso, mas a aprovação paga usa texto italiano fixo `Approva` e não compara um teto de custo. Os resultados são identificados por IDs novos e baixados pelo endpoint privado `media.getMediaUrlRedirect`. A fila de jobs é um `Map` em memória; salvar metadados do resultado não equivale a recuperar um job interrompido. O script indicado em `npm test` não consta na árvore examinada. [Geração](https://github.com/GabrielGargiuloDev/google-flow-mcp/blob/aae58a79aecd640a00f853e454e16e101bb7a756/src/tools/generate-video.js), [fila](https://github.com/GabrielGargiuloDev/google-flow-mcp/blob/aae58a79aecd640a00f853e454e16e101bb7a756/src/queue/job-queue.js), [manifesto](https://github.com/GabrielGargiuloDev/google-flow-mcp/blob/aae58a79aecd640a00f853e454e16e101bb7a756/package.json).

### roshanarnav25-sloth/google-flow-mcp

Apesar de priorizar tRPC no transporte, a geração observada usa teclado/Enter e cliques em Approve/Reject. O projeto oferece ledger e orçamento. Contudo, `awaitQuote` lê a última ocorrência de um número seguido de `credits` no texto global da página; não observei vínculo explícito à nova proposta, embora um comentário prometa isso. A coleta aceita qualquer ID novo do projeto. Essas heurísticas são insuficientes para tratar o gate de custo e a correlação entre pedido e vídeo como garantias fortes. [Geração e parsing de custo](https://github.com/roshanarnav25-sloth/google-flow-mcp/blob/0e4c8b36e844860dea7c41a315524fd7d652b32c/src/services/generate.ts), [transporte tRPC](https://github.com/roshanarnav25-sloth/google-flow-mcp/blob/0e4c8b36e844860dea7c41a315524fd7d652b32c/src/services/transport.ts), [orçamento](https://github.com/roshanarnav25-sloth/google-flow-mcp/blob/0e4c8b36e844860dea7c41a315524fd7d652b32c/src/services/ledger.ts).

## Próximo MVP local

Arquitetura proposta: **agentes → MCP stdio → sessão Flow**; **MoneyPrinterTurbo → provider `google_flow` → CLI/núcleo da mesma base → sessão Flow**. O MoneyPrinterTurbo recebe caminhos locais dos vídeos gerados e reutiliza sua composição, narração e legendas existentes; não precisa virar cliente MCP. Essa costura foi identificada pelo agente principal em `task.get_video_materials` e `material.download_videos` do clone local, ainda sem alteração de código.

1. Confirmar a interface da conta e o cliente MCP. Manter navegador e processo MCP inicialmente no mesmo sistema operacional, com perfil dedicado.
2. Validar uma versão fixada da base sem gastar créditos: inicialização MCP, lista de ferramentas, sessão, origem/interface do Flow e diretório de saída.
3. Se compatível, usar as ferramentas existentes para um pedido autorizado de um único vídeo, sem upscale, com acompanhamento pelo mesmo ID e download do resultado correto. Nunca reenviar automaticamente após timeout; recuperar o job primeiro.
4. Integrar a entrega como provider `google_flow` no MoneyPrinterTurbo, retornando arquivos locais ao pipeline existente. Adicionar apenas o adaptador necessário; não criar outro servidor MCP se o existente atender. Preservar as alterações preexistentes do fork.

Não estão autorizados por esta pesquisa gastos ou alterações nas confirmações do Flow. Se a conta só tiver interface agentic, reavaliar miyakejima com revisão explícita desse comportamento ou um adaptador mínimo sobre navegador autenticado.

## Limites da verificação

As conclusões de código foram obtidas por leitura estática dos arquivos citados, não por auditoria completa. Nenhuma conta real foi conectada, nenhum teste de geração/download foi executado, nenhuma dependência foi instalada e nenhuma estabilidade operacional foi comprovada. Afirmações de testes reais feitas pelos mantenedores continuam sendo relatos deles. Endpoints internos, origem, idiomas, controles, modelos e regras de crédito podem variar por conta ou mudar.

O diretório local não foi indexado: ele não era um repositório Git selecionado. Arquivos externos usados apenas para leitura ficaram em `/tmp/flow-mcp-research/`; não fazem parte da implementação do projeto.
