# 9Router e múltiplas contas no Flow MCP

Pesquisa em 29/09/2026. Fontes: README e código dos próprios projetos. Apenas leitura de clones em `/tmp`; nenhum pacote instalado, código executado, login realizado ou crédito consumido.

Versões examinadas:

- 9Router: [`f01fb909e37189008080632ddaf404f096345cde`](https://github.com/decolua/9router/tree/f01fb909e37189008080632ddaf404f096345cde).
- gflow-cli: [`488dcc1b80ba935ef204b60ea9335c43614dca84`](https://github.com/ffroliva/gflow-cli/tree/488dcc1b80ba935ef204b60ea9335c43614dca84).

## Conclusão

O 9Router serve como referência para seleção de contas, prioridade, alternância e espera após erros. Não é necessário incorporá-lo ao projeto para atender duas contas Flow. O gflow-cli já oferece perfis separados, parâmetro `profile` nas ferramentas MCP e bloqueio por perfil; a adaptação mínima é escolher o perfil e preservar a conta escolhida durante toda a tarefa. [Seleção 9Router](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/sse/services/auth.js#L28), [execução gflow MCP](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L329).

Não encontrei integração de **Google Flow web com créditos da assinatura** no registro de provedores e nos fluxos de vídeo do 9Router examinados. Isso não significa ausência de vídeo: há adapters de Vertex AI/Veo e OpenRouter/Veo, além do formato padrão xAI. Esses caminhos são outros provedores e outras credenciais, sem uma ponte demonstrada para o saldo do Flow. [Adapters](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/handlers/videoProviders/index.js), [Vertex](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/handlers/videoProviders/vertex.js#L34), [registro Vertex](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/providers/registry/vertex.js#L30).

## O que o 9Router implementa

| Área | Evidência no código | Aplicação ao Flow |
| --- | --- | --- |
| Contas por provedor | Carrega conexões ativas e elimina contas excluídas ou bloqueadas por modelo. | Inventário de contas próprias, cada uma com sessão independente. |
| Prioridade | Estratégia padrão `fill-first`: primeira conexão disponível pela prioridade. | Preferir conta A; enviar novos trabalhos para B quando A estiver indisponível. |
| Alternância | `round-robin` escolhe a menos recentemente usada, com repetição configurável na conta atual; padrão de três usos consecutivos. | Alternância entre novos trabalhos, opcional; não alternar durante uma geração. |
| Preferência explícita | `preferredConnectionId` tenta fixar conexão disponível, mas pode cair na estratégia se ela não estiver disponível. | Usar `account_id` explícito; recomenda-se erro se a conta solicitada estiver indisponível, evitando gasto em outra conta sem intenção. |
| Seleção simultânea | Mutex protege somente a seleção e atualização de estado; é liberado antes da chamada ao provedor. | Reserva atômica da conta escolhida e bloqueio de navegador por perfil. |

Fonte da tabela: [`getProviderCredentials`](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/sse/services/auth.js#L28). O mutex observado não estabelece, por si, um limite de tarefas simultâneas por conta.

Erros geram bloqueios por conta/modelo. Regras distinguem cota, autenticação e falhas transitórias; existem atrasos progressivos. Um reset exato informado pelo Antigravity pode determinar a espera sem truncamento. Não copiar os tempos e interpretações automaticamente para Flow: cota de programação, limite de pedidos por minuto, saldo de créditos e limite diário de imagens são estados diferentes. [Classificação](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/services/accountFallback.js#L23), [estado persistido](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/sse/services/auth.js#L239), [configuração de erros](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/config/errorConfig.js#L32).

## Gemini e Antigravity: autenticação e limites

O serviço Gemini CLI constrói autorização Google OAuth, troca o código por tokens, consulta `loadCodeAssist` para obter projeto e persiste tokens e identidade da conta. O serviço Antigravity segue autorização Google e consulta Code Assist/onboarding. Isso descreve as integrações presentes no código; não prova que todos esses serviços estejam acessíveis hoje à conta do usuário. [Gemini OAuth](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/lib/oauth/services/gemini.js#L20), [Antigravity OAuth](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/lib/oauth/services/antigravity.js#L20).

A renovação Google usa `refresh_token`, mantém o token de renovação anterior quando não há outro e deduplica pedidos concorrentes. É renovação de credenciais daquelas integrações, não um login automático demonstrado para o site Flow. [Renovação](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/services/tokenRefresh/providers.js#L202).

A medição Gemini consulta buckets de Code Assist. A medição Antigravity lê informações por modelo e tenta complementar limites semanais; percentuais são convertidos para uma base normalizada de 1000. **Esse 1000 não representa créditos de vídeo nem créditos transferíveis.** [Gemini quota](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/services/usage/google.js#L22), [Antigravity quota](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/services/usage/google.js#L120).

No Flow, a base gflow-cli usa diretórios persistentes de navegador com cookies, IndexedDB e identidade da conta. Perfis devem permanecer fora do repositório e não devem aparecer em logs, respostas MCP ou AI Memory como conteúdo de credenciais. [Autenticação/perfis](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/docs/AUTHENTICATION.md#L81).

## Vídeos pagos exigem tratamento próprio

O código de vídeo do 9Router já contém uma distinção útil: criação só alterna conta após determinados erros de rejeição, enquanto uma falha de rede/5xx pode esconder uma criação aceita e não provoca reenvio automático. Criação retorna `x-connection-id`; consulta posterior recebe essa preferência. Para o Flow, o registro da tarefa deve preservar **obrigatoriamente** conta, projeto e identificação remota, em vez de depender de preferência que possa cair em outra conta. [Criação](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/sse/handlers/videoGeneration.js#L35), [consulta](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/sse/handlers/videoGeneration.js#L197), [limite de retries](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/handlers/videoCore.js#L11).

Não importar o gateway inteiro: há tradução entre formatos LLM, dashboard, combos e vários provedores que não atendem o requisito imediato. O projeto é MIT; eventual cópia substancial exige manter aviso de autoria/licença. [Escopo](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/CLAUDE.md#L5), [licença](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/LICENSE).

## O que já existe no gflow-cli

- `gflow_get_credits(profile, all_profiles)` consulta saldo de uma conta ou dos perfis salvos. A consulta conjunta é sequencial e mantém resultados parciais. A soma retornada é apresentação dos saldos consultados; não cria carteira compartilhada. [Ferramenta MCP](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L1275), [serviço](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/services/credits.py#L133).
- A documentação reporta limitação de leitura de saldo em contas migradas para `flow.google.com`, pelo caminho de token labs utilizado. Nesse caso, apresentar **saldo desconhecido**; uma leitura indisponível não comprova saldo zero nem sessão expirada. [Limitação registrada](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/docs/MCP.md#L98).
- No caminho MCP padrão `wait=true`, `_profile_lock` é por perfil e event loop; a execução cria um `FlowWorker` para o perfil escolhido. Contas/perfis distintos podem executar concorrentemente segundo essa estrutura; não há bloqueio global de geração nesse caminho. Chamadas para o mesmo perfil aguardam. Existe um limitador global de frequência de geração, distinto do bloqueio por conta. [Lock por perfil](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L73), [execução](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L329).
- `ProfileLease` dá exclusividade ao diretório canônico do perfil dentro e entre processos. A configuração MCP permite espera limitada por outro processo; isso protege o navegador quando CLI e MCP coexistem. [Lease](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/profile_lease.py#L229), [configuração MCP](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/server.py#L132).
- `wait=false` apenas insere na fila. O daemon UI observado inicia um worker para **um** perfil configurado. Não assumir execução multi-conta automática desse modo: usar execução direta em tarefas internas ou workers correspondentes a cada perfil. [Enfileiramento](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/mcp/tools.py#L291), [lifespan UI](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/src/gflow_cli/ui/app.py#L23).

As observações de paralelismo são revisão de código/documentação, não teste de geração nas duas contas do usuário. O comentário inicial de `mcp/tools.py` sobre remoção de lock está desatualizado frente à função `_profile_lock` implementada; a conclusão acima segue a execução real do arquivo.

## Adaptação mínima recomendada para este projeto

Esta seção é proposta de implementação, não capacidade já validada no Flow:

1. Cadastrar as duas contas com perfis de navegador diferentes e verificar a identidade em cada login. Deduplicar a mesma conta: dois perfis da mesma conta não representam dois saldos independentes.
2. Aceitar `account_id` em geração e em consultas. Escolha explícita deve permanecer fixa; `auto` seleciona conta apta antes de iniciar a tarefa.
3. Começar com prioridade A→B e opção de alternância simples entre novos trabalhos. Paralelismo inicial: uma geração ativa por conta, permitindo A e B simultaneamente; respeitar também os limites efetivos do Flow e o limitador da base.
4. Manter sessão, saldo observado, horário da observação, capacidades, estado e próxima tentativa por conta. Separar falta de saldo, limite temporário, limite de imagem, sessão expirada e modalidade não suportada. Se a leitura falhar, o valor é desconhecido.
5. Uma conta sem saldo confirmado sai da seleção automática para novos trabalhos até atualização de saldo; não fazer polling agressivo esperando que segundos de atraso restaurem créditos. Projetos e referências de uma conta não migram automaticamente para outra.
6. Vincular `job_id → account_id + profile + project_id + remote_job/media_id` antes do acompanhamento/download. Trocar a conta padrão não altera trabalhos existentes.
7. Trocar A→B automaticamente somente quando houver rejeição comprovada antes do envio/aceitação, e a solicitação usar `auto`. Se o envio pode ter sido aceito, marcar indeterminado e procurar o resultado na conta original; não gerar outro vídeo automaticamente.
8. Repetir download de um asset já identificado quando necessário, preservando conta e arquivo. Não repetir geração para resolver falha de download.

Ferramentas suficientes para o agente: listar contas com estado/capacidades, consultar saldo, escolher conta por chamada, iniciar geração, consultar tarefa e baixar resultado. A base já cobre vários desses elementos; acrescentar seleção automática sem duplicar os mecanismos existentes.

O usuário usa Chrome no Windows hoje e quer considerar Raspberry Pi sem interface gráfica depois. O gflow-cli documenta dependência atual de navegador visível e perfil autenticado. Rodar num dispositivo sem desktop pode exigir ambiente gráfico virtual e validação de navegador/ARM; não há demonstração nesta pesquisa de uma solução Flow somente por API, nem promessa de que o modo headless funcionará. [Dependência documentada](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/README.md#L32).

## Cobertura da pesquisa

O graph MCP foi usado primeiro nos clones Git explicitamente selecionados. Consultadas seleção, autenticação, refresh, limites, fluxos de vídeo, execução MCP e lease; verificada cobertura dos arquivos citados e escopos relevantes. A leitura direta complementou documentos/licença excluídos e a busca literal por `labs.google`, `flow.google`, `google.flow`, `veo` e geração de vídeo em `src`, `open-sse`, `cli`, `docs` e `gitbook/content/en` do 9Router. Metadados de cobertura são best effort, não garantia absoluta. A conclusão negativa limita-se à integração Flow nesses caminhos examinados, sem inferir ausência de trabalhos externos, forks ou suporte futuro.
