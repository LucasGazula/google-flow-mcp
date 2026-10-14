# Google Flow MCP — instruções do projeto

## Regras fixas

- **Sempre responder em português do Brasil**, mesmo quando o usuário escrever em
  outro idioma.
- **Continuidade entre agentes/sessões via AI Memory** (`workspace=google_flow_mcp`,
  `project=google_flow_mcp`): no início, ler `memory_recent`, a página
  `projeto/em-andamento.md` e `projeto/estado-atual.md`. **Durante e ao fim** de
  cada etapa, atualizar `projeto/em-andamento.md` (o que está sendo feito agora,
  próximo passo, bloqueios) e, quando algo for concluído, `projeto/estado-atual.md`.
  Outro agente deve conseguir retomar só lendo essas páginas. Nunca gravar
  cookies, tokens, respostas autenticadas ou URLs assinadas.
- Gastar créditos só com conta confirmada pelo usuário (e-mail, saldo e cotação).

## Visão geral

MCP `stdio` (Python 3.11+, `uv`, `gflow-cli==0.79.1`) que expõe o Google Flow
(vídeo, imagem, cenas, personagens, Agent) a agentes, usando as contas e os
créditos de assinatura do usuário. Arquitetura: um worker por conta mantém um
Chrome headless autenticado só para preparar sessão/reCAPTCHA pelo fluxo normal
do site; o envio real é um único POST HTTP com os RPCs nativos do Flow. Mutações
incertas nunca são reenviadas; tarefas ficam persistidas e são recuperáveis.

| Arquivo | Papel |
| --- | --- |
| `flow_mcp.py` | Servidor MCP e registro das ferramentas |
| `flow_http.py` | Worker por conta: HTTP + Chrome residente |
| `flow_browser.py` | Chrome dedicado, páginas de preparo descartáveis |
| `flow_requests.py` | Corpos dos RPCs do Flow |
| `flow_video.py` | Geração de vídeo/imagem, orçamento, tarefas |
| `flow_edit.py`, `flow_annotations.py` | Edição de imagem e anotações |
| `flow_scene.py`, `flow_character.py`, `flow_agent.py` | Cenas, personagens, Agent/brief |
| `flow_projects.py`, `flow_assets.py`, `flow_collections.py` | Projetos, ativos, coleções |
| `flow_capabilities.py`, `flow_credits.py`, `flow_settings.py` | Catálogo/custos, saldo, preferências |
| `flow_accounts.py`, `flow_session.py`, `extension/` | Contas, login e ponte de sessão |
| `flow_errors.py` | Mensagens de erro seguras (`error`), `next_step` por status, leitura tolerante |
| `keepalive.py` | Consulta periódica de saldo por conta (mantém sessões e detecta queda) |
| `deploy/` | Login isolado no Windows → importação na Banana Pi |
| `test_*.py` | Suíte `uv run --locked python -m unittest -v`; `test_gflow_contract.py` confere os internos do gflow-cli usados |

Documentação: `PLANO-MCP.md` (requisitos), `docs/IMPLEMENTACAO-FLOW.md` (registro
detalhado e gastos), `docs/AUTENTICACAO-PORTABILIDADE.md`, `README.md`.

Ambientes: Windows (`.venv-windows`, onde o MCP está registrado no Claude Code,
Antigravity e Codex), WSL (testes) e Banana Pi (servidor local dedicado,
tudo em `/mnt/ssd/flow-mcp/`; carregar `env.sh`).
Perfis em `profiles/profile_<conta>` (Windows) e `/mnt/ssd/flow-mcp/home` (Pi).

## Histórico (mais antigo → mais recente)

- Responder em pt-BR. Este é um MCP independente; não modificar MoneyPrinterTurbo
  como parte deste projeto sem um pedido específico.
- Usar Python 3.11+ e `uv`. Servidor atual: `flow_mcp.py`, transporte `stdio`.
  Verificação: `uv run --locked python -m unittest -v`.
- Expor somente operações implementadas. Contas usam gflow-cli 0.79.1 fixado:
  listagem de perfis, login assistido e verificação de sessão. A ponte experimental
  usa `flow_session.py` e `extension/`; cookies só seguem em memória/stdin, ou em
  arquivo privado de `exports/` quando o usuário executar exportação explícita. A validação em contas
  reais confirmou autenticação no Windows após login manual. A extensão não
  restaurou sozinha o acesso ao Flow. `flow_get_credits` consulta saldo sem geração;
  `flow_generate_video` gera e baixa um clipe Veo Lite, 8s/720p/16:9, com teto
  explícito conferido no painel. Teste Windows confirmado com gasto de 10 créditos.
  `flow_get_job` lê estado persistido, sem polling remoto nem reenvio.
  `flow_recover_job` recupera o vídeo original sem gerar novamente, usando a
  resposta as29s e validando tamanho/MP4 e cada redirecionamento de download.
  Criar/renomear projetos foram validados no Windows. Imagens estão em validação.
  Listagem remota de projetos e listagem local de tarefas estão implementadas;
  projetos aceitam IDs opacos seguros, incluindo IDs legados com `_backfill`.
  Veo Lite com quadro inicial e Omni Flash 4s/720p foram validados no Windows.
  Geração por texto de dois Veo Lite, geração de imagens com referência e edição
  textual de imagem foram validadas por HTTP no Windows. O navegador prepara a
  sessão; custo/configuração vêm do catálogo HTTP. O envio do navegador é abortado, seguido
  de um único POST HTTP após fechá-lo. Acompanhamento de vídeo usa `as29s` por
  workflow, sem reenvio. Downloads de imagem no host lh3 usam `=s0` para obter
  as dimensões originais. Veo Lite com quadro inicial e Omni Flash 4s também
  passaram pela geração e recuperação HTTP. Gasto acumulado atual: 148 créditos;
  saldo confirmado: 892.
  Criação/renomeação de projetos e consulta de saldo `nzlxg` foram validadas
  por HTTP pelo MCP. Upload `maseQ` envia uma única requisição HTTP após fechar
  Chrome; resposta contém registro aninhado. Referências/quadros são enviados
  antes da geração; seus IDs são vinculados no corpo nativo. Imagem com referência
  validada nesse fluxo, custo zero; Veo Lite com quadro inicial também validado,
  custo 10. Renomeação preserva a capa observada por
  `ngNC2`. Resultados incertos nunca são reenviados automaticamente.
  Teto autorizado desta etapa: 500 créditos; registrar gastos em
  `docs/IMPLEMENTACAO-FLOW.md`. Roteamento não existe; segunda conta adiada.
- Preservar os requisitos e as limitações documentados em `PLANO-MCP.md`.
  Tokens/cookies não entram em logs, Git ou memória. Não supor que a sessão de
  Chrome pode ser transferida entre máquinas sem validação.
- Retomada HTTP nativa (30/09/2026 UTC): `flow_requests.py` monta upload,
  imagem, edição e vídeo; o catálogo `HTrJv` confere modelo/formato/custo por
  plano. O navegador prepara autenticação/reCAPTCHA pelo fluxo normal do site,
  com envio abortado; não configura modelo/proporção/quantidade do pedido real.
  Chamadas diretas a `enterprise.execute` foram marcadas pelo frontend e as
  sondagens de imagem/edição retornaram RPC 7; não repetir essas tentativas.
  Upload, lote de duas imagens com referência, edição/histórico e recuperação
  passaram no Windows. Vídeo por texto em lote foi reconciliado sem reenvio;
  Veo Lite com quadro inicial e Omni Flash 4s com inicial/final ou referência
  passaram no caminho nativo, inclusive recuperação. Gastos desta retomada:
  44 créditos; total 148/500, saldo 892, restantes 352 do teto. Suíte: 51 testes
  passaram em WSL e Windows. Sessão portátil e operação sem navegador pendentes.
- AI Memory: escopo explícito `workspace=google_flow_mcp`,
  `project=google_flow_mcp`, conforme `.ai-memory.toml`.
  No início de toda sessão, antes de responder ou executar trabalho, ler o
  AI Memory: consultar `memory_recent` e ler integralmente as páginas de estado
  atual, requisitos e decisões relevantes com `memory_read_page`. Conferir
  handoffs pendentes com `memory_handoff_list` quando não houver handoff já
  fornecido no contexto. Tratar a memória como histórico, validando-a contra
  as instruções atuais e o estado do repositório.
  Manter o AI Memory atualizado após implementações, validações, decisões,
  mudanças de pendências e gastos relevantes, distinguindo código implementado
  de operação comprovada. Nunca registrar segredos ou respostas autenticadas.
- Atualização posterior de 30/09/2026: worker por conta mantém Chrome headless
  autenticado, sob demanda, com operações serializadas. A página de preparo
  fecha antes do POST HTTP, mas o contexto permanece até encerrar o worker;
  esta regra substitui o fechamento integral anterior a cada envio. Login,
  importação e verificação liberam o contexto antes de acessar o perfil.
  Login humano continua visível; `FLOW_MCP_HEADLESS=false` habilita diagnóstico
  visível após reiniciar, sem fallback automático. Nano Banana 2 1:1 (custo 0)
  e Veo Lite 8s/720p/16:9 (custo 10), com download e recuperação, passaram no
  mesmo contexto headless Windows. Gasto atualizado: 158/500, saldo 932,
  restantes 342; diferença anterior 892 → 942 sem explicação. Suíte: 55 testes
  passaram em WSL e Windows. Sem prova de estabilidade prolongada ou portabilidade.
- Validação posterior de edição e extensão de vídeo consumiu mais 40 créditos:
  gasto acumulado 198/500, saldo 902, restantes 302. Upload de vídeo local
  e modos de câmera/objetos continuam pendentes.
- Omni Flash 8s/360p/16:9 gerou, baixou e recuperou MP4 H.264 640×360 no
  Windows, custo 6. Gasto acumulado 204/500, saldo 896, restantes 296.
  A resolução vem da variante do catálogo HTTP. `flow_upload_asset` agora
  encaminha vídeos pela interface normal; primeiro upload encontrou aviso
  de direitos; o usuário aceitou manualmente e o upload foi confirmado. Edição
  textual do vídeo enviado foi validada, custo 20, download e recuperação.
  Gasto atual 224/500, saldo 876, restantes 276. `flow_confirm_upload` agora
  permite autorização explícita em duas etapas quando aparecer novo aviso,
  testada localmente mas ainda sem validação num segundo aviso real. Um upload
  subsequente foi reconciliado pela listagem após `submission_unknown`, sem
  reenvio; o Flow omitiu `.mp4` do nome exibido. `flow_delete_project` agora
  exige confirmação, envia `QI2zvc` uma vez e reconcilia via `UpteDb`; testes
  locais passaram, validação Windows pendente. Coleções agora têm criação e
  renomeação (`Uxbujd`/`O2COMe`) e movimentação em lote (`kVdhHf`); somente
  criação/renomeação confirmam ID/título, readback do movimento está pendente.
  Testes locais cobrem os três fluxos; validação Windows pendente. A suíte WSL
  passa com 102 testes e o MCP expõe 48 ferramentas. Busca de projetos/ativos, cenas, personagens, brief
  do Agent e presets de voz usam os fluxos HTTP/gflow-cli do worker; mutações
  incertas não são repetidas. Nenhum crédito foi gasto nesta implementação.
- Atualização de coleções (30/09/2026): `flow_list_assets` expõe e filtra a
  associação direta `collection_id`; `flow_download_collection` baixa os ativos
  diretos em uma pasta, sem percorrer subcoleções. A suíte WSL passou com 103
  testes e o MCP expõe 49 ferramentas. Sem validação Windows ou gasto de
  créditos nesta retomada. Listagem de coleções vazias/metadados segue pendente:
  esquema da RPC ainda não foi verificado.
- Preferências da conta (30/09/2026): `flow_get_user_settings` lê via `Yizz8d`;
  `flow_update_user_settings` atualiza campos selecionados via `DA4VGb` e
  reconcilia por leitura, sem reenvio. Ativar vídeos silenciosos exige
  `confirm_credit_impact=true`. Leitura validada no Windows via worker HTTP;
  atualização ainda sem validação. Suíte WSL: 125 testes; MCP: 55 ferramentas.
  Nenhum crédito foi gasto.
- Sessões do Flow Agent (30/09/2026): listagem inicial por `mrlkwd`, criação
  por `csbIsb`, renomeação por `TunYMc` e exclusão por `Dcn2Le`. Exclusão exige
  confirmação explícita e remove o histórico permanentemente; mutações não são
  reenviadas se incertas. Rename/delete usam apenas a primeira resposta.
  Paginação e mensagens pendentes. A listagem vazia foi validada no Windows;
  criação/renomeação/exclusão ainda não. Suíte WSL: 125 testes; MCP: 55 ferramentas.
  Sem gasto de créditos nesta validação.
- Edição de imagem (30/09/2026): seleção anotada combinada com `reference_asset_ids`
  do mesmo projeto validada no Windows por HTTP. Uma anotação foi enviada, uma
  edição concluída, o resultado baixado e lido de volta; cotação zero e saldo
  856 antes/depois. Sem reenvio e sem outros créditos gastos.
- Recorte de imagem (30/09/2026): o primeiro resultado 1024×1024→512×512 foi
  recuperado por `flow_download_asset` sem reenviar a mutação; arquivo legível de
  142.689 bytes, workflow preservado e saldo 856. A verificação da sessão WSL
  falhou, mas a sessão Windows permaneceu autenticada. `flow_edit.crop_image`
  agora relê `Zzl0ze` após o envio e obtém a URL da nova versão pela resposta do
  projeto. Um segundo recorte em outra origem concluiu e baixou automaticamente:
  512×512, workflow preservado, cotação zero e saldo 856 antes/depois.
- Variações de imagem (30/09/2026): `flow_edit_image(count=2)` com Nano Banana 2
  1:1 validado no Windows. Duas saídas 1024×1024 foram lidas de volta e baixadas,
  ligadas ao workflow de origem; cotação zero e saldo 856 antes/depois. Um envio
  independente com `count=4` retornou `partial_result`: três saídas 1024×1024
  foram lidas de volta e baixadas no workflow, cotação zero e saldo inalterado.
  A consulta do quarto ID esperado retornou `http_error`; não houve reenvio.
  `count=3` e quatro saídas completas ainda pendentes. Nenhum ID, prompt ou
  resposta autenticada registrado.
- Coleções (30/09/2026): `flow_list_collections` lê também coleções vazias pela
  primeira seção de `Zzl0ze`, com `complete=false` por paginação não verificada.
  Uma criação retornou `submission_unknown`, mas apareceu na interface com o
  título padrão; o código agora reconcilia por ID, sem reenviar. O payload de
  renomeação `O2COMe` foi corrigido conforme captura do frontend com envio
  bloqueado. Renomeação e movimentação de um ativo para a coleção e de volta à
  raiz foram confirmadas por leitura no Windows. Download direto e nova criação
  após a correção ainda sem validação Windows; download recursivo pendente.
  Suíte WSL: 127 testes; MCP: 56 ferramentas. Nenhum crédito gasto.
- Subcoleções (01/10/2026): `flow_download_collection(recursive=true)` percorre
  os vínculos pai/filho da primeira resposta `Zzl0ze`; `complete=false` preserva
  a incerteza de paginação. Criação de subcoleção, movimento de ativo para ela,
  download pelo pai e retorno à raiz foram confirmados no Windows. Sem créditos
  gastos. Suíte WSL completa passou com 128 testes; MCP: 56 ferramentas.

<!-- codebase-memory-mcp:start -->
## Descoberta de código

Preferir as ferramentas do grafo MCP: `search_graph`, `trace_path`,
`get_code_snippet`, `query_graph` e `get_architecture`, nessa ordem conforme a tarefa.
Recorrer a busca textual para strings, configurações, arquivos não código ou
quando o grafo não fornecer resultados suficientes.

Chamar `index_repository` somente para um repositório Git explicitamente
selecionado, com sua raiz exata. Nunca indexar raízes de discos ou diretórios
pessoais, incluindo `/`, `/mnt/c`, `C:\\`, `/mnt/c/Users/<usuario>`,
`C:\\Users\\<usuario>` e `$HOME`. Sem repositório Git, não indexar.
<!-- codebase-memory-mcp:end -->

- Sessões do Agent (01/10/2026): criação e renomeação confirmadas no Windows
  pelo worker HTTP residente, com leitura posterior e sem reenvio. Sessão de
  teste preservada; exclusão, mensagens e paginação pendentes. Suíte completa:
  128 testes passaram em WSL e Windows (ffmpeg instalado via WinGet precisa
  estar no PATH do processo Windows). Sem créditos gastos; total 244/500.
- Refinamento de vídeo (01/10/2026): `flow_refine_video` encadeia até três
  prompts Omni Flash no mesmo workflow, reutiliza a saída anterior e referências
  locais já enviadas, aplica um orçamento total e interrompe resultados incertos.
  Testes WSL: 134; MCP: 57 ferramentas. Equivalência conversacional e validação
  Windows pendentes. Nenhum crédito gasto; total permanece 244/500.
- Upscale nativo de imagem (01/10/2026): `flow_upscale_image` usa uma única
  mutação HTTP para 2K/4K e salva o resultado local; 2K sem créditos, 4K restrito
  ao Ultra conforme gflow-cli fixado. Suíte WSL: 138 testes; MCP: 58 ferramentas.
  Validação remota pendente. Upscale nativo de vídeo segue faltando. Nenhum
  crédito gasto; gasto acumulado 244/500.
- Retomada de upscale e recursos principais (01/10/2026): a conta migrada não
  fornece o bearer Aisandbox exigido por `upsampleImage`; a tentativa parou antes
  do POST, sem gasto, e não deve ser repetida por esse caminho. Leitura de saldo
  906 antes/depois; diferença 856→906 segue sem explicação, gasto registrado
  continua 244/500. Upscale nativo de vídeo e controles dedicados de câmera e
  inserção/remoção de objetos seguem pendentes; a edição textual existe. Suíte
  WSL: 140 testes; MCP: 58 ferramentas.
- `flow_upscale(upload_to_flow=true)` agora envia vídeos gerados pelo FFmpeg
  usando `flow_upload_asset`; avisos de direitos continuam exigindo confirmação
  explícita por `flow_confirm_upload`. Teste local cobriu a resposta pendente;
  validação Windows desta combinação pendente. Suíte WSL: 141 testes; MCP: 58
  ferramentas. Sem gasto de créditos; gasto acumulado segue 244/500.
- `flow_upscale_image(upload_to_flow=true)` agora envia a saída do upscale nativo
  de imagem pelo upload HTTP existente e informa o estado/ID do novo asset; falha
  no upload preserva o arquivo local. Teste unitário cobre o caminho; endpoint
  nativo segue bloqueado antes do POST nesta conta, portanto sem validação Windows.
  Suíte WSL: 142 testes; MCP: 58 ferramentas. Sem gasto; acumulado 244/500.
- `flow_generate_video` agora expõe `reference_asset_ids` para reutilizar imagens
  e vídeos do mesmo projeto/conta. O teste local confirma tipo, payload de
  referência e envio único quando a resposta fica incerta; validação Windows
  dessa entrada por ID ainda pendente. Suíte WSL: 143 testes; MCP: 58 ferramentas.
  Sem gasto; acumulado 244/500.
- `flow_generate_video` também aceita `start_image_asset_id` e
  `end_image_asset_id` para usar imagens do projeto como quadros inicial/final.
  Testes locais cobrem ownership, tipo, corpo nativo e parada sem reenvio.
  WSL retornou `verification_error`; Windows `no_session`; consulta de créditos
  indisponível. Suíte WSL: 144 testes; três testes direcionados passaram no
  Windows; MCP: 58 ferramentas. Sem gasto; acumulado 244/500.
- Upscale nativo de vídeo (01/10/2026): `flow_upscale_video` cobre Omni 360p→720p
  e Veo Lite 720p→1080p. O Flow retorna `_720p_upsampled` para 720p e
  `_upsampled` para 1080p; a recuperação não reenvia a mutação. Ambos os fluxos
  foram validados no Windows. A saída 1080p baixada tem 6.003.074 bytes, MP4
  H.264 1920×1080. Saldo 906 antes/depois; gasto acumulado 244/500. Suíte WSL:
  149 testes; MCP: 59 ferramentas. 4K e controles dedicados de câmera/objetos
  seguem pendentes.
- Geração de imagem/vídeo (02/10/2026): a seleção do Nano Banana 2 Lite usa o
  `model_id=harbor_seal`, pois o rótulo real do catálogo contém um emoji. Lite
  gerou um JPEG 1:1; Nano Banana Pro gerou três JPEGs 1:1. Ambos tiveram custo
  zero e saldo 906 antes/depois. Omni Flash 10s/720p/16:9 concluiu no Windows
  como MP4 H.264 1280×720, 4.870.295 bytes; custo 15, saldo 906→891. Gasto
  acumulado 259/500, restantes 241. Depois, referência de imagem do projeto por
  ID concluiu Omni Flash 4s/720p/16:9 como MP4 H.264 1280×720, 1.347.410 bytes;
  custo 7, saldo 891→884. Uma tentativa com referência de vídeo por ID cotou
  mais 7, mas retornou `submission_unknown`; a listagem e `as29s` ainda não
  confirmaram o resultado. A leitura imediata foi 884→877 e as posteriores
  voltaram a 884; sem atribuir a diferença, reservar 273/500 no teto (227
  restantes). Nenhum reenvio. `flow_recover_job` agora consulta listagem e
  `as29s` pelos IDs/workflows esperados e baixa vídeo pronto sem nova geração;
  imagens incertas também reconciliam por correspondência exata de ID/workflow
  na listagem, sem novo envio. A tarefa real de referência de vídeo segue
  `not_listed`. Geração Pro `count=4` passa em teste local com um POST e quatro
  downloads; validação Windows ainda pendente. Suíte WSL: 152 testes; MCP: 59
  ferramentas.
- Verificação adicional (02/10/2026): `flow_recover_job` agora tem teste para
  `image_edit` além de `image`, confirmando recuperação por ID/workflow sem
  reenvio. A ajuda oficial informa que upscale de vídeo 4K custa 50 créditos e
  exige Ultra; a conta Pro deste projeto não tem acesso. A inspeção do navegador
  não iniciou geração, deixou o modo em vídeo e o campo de comando vazio. Sem
  gasto; suíte WSL: 152 testes.
- Suíte Windows completa também passou com 152 testes ao incluir o diretório
  FFmpeg do WinGet no `PATH` do processo. A operação remota Pro `count=4` segue
  sem validação: os perfis do worker MCP retornaram `no_session`/
  `google_session_only` no Windows e `verification_error` no WSL. A sessão do
  navegador visível não foi transferida; nenhuma geração nem gasto ocorreram.

- Retomada multimídia (03/10/2026): perfil Windows voltou a `authenticated`.
  Pro `count=4`, edição Lite `count=3` e edição Nano Banana 2 `count=4` concluíram:
  11 JPEGs 1024×1024, leitura posterior das edições, cotação zero e saldo 906.
  Omni Flash 4s/360p com quadros inicial/final por IDs e dois refinamentos no
  mesmo workflow concluíram e baixaram MP4 H.264/AAC 640×360, decodificados
  integralmente. Custo 24, saldo 906→882; gasto confirmado 290/500, reserva
  incerta anterior de 7 mantida: 297/500 contabilizados, 203 restantes.
  A tarefa antiga com referência por ID de vídeo continua `not_listed`, sem
  reenvio. `flow_wait_job` acompanha por recuperação dos IDs originais, preserva
  o status no timeout e respeita cancelamento local; não cancela no serviço.
  Inicialização fixa o diretório privado gflow ao `FLOW_MCP_HOME`, evitando
  divergência entre ferramentas locais e workers. Suítes WSL/Windows: 159
  testes; MCP: 60 ferramentas. Geração 1080p/4K não consta nas variantes
  compatíveis do catálogo Pro observado; upscale 4K indisponível por plano.

- Upscale de imagem migrado (03/10/2026): `flow_upscale_image` usa `SPrCad`
  capturado pela interface normal com envio bloqueado, seguido de um único POST
  HTTP após fechar a página. 2K validado no Windows: JPEG 2048×2048, upload,
  leitura e reutilização do mesmo resultado sem repetir envio/upload. Catálogo
  confere custo zero; saldo 882 inalterado. 4K bloqueado até validar corpo/plano;
  endpoint Aisandbox legado não utilizado. Listagem reconhece o ativo nativo
  sem dimensões e informa null. `flow_refine_video` aceita vídeos locais como
  referência, envia uma vez e reutiliza IDs; aviso de direitos interrompe sem
  descontar geração não enviada. Testes locais passaram; referência local ainda
  sem validação remota. Suítes WSL/Windows: 163 testes; MCP: 60 ferramentas.
  Confirmado 290/500; reserva 7: contabilizados 297/500, restantes 203.

- Edição em novo histórico (03/10/2026): `flow_edit_video` aceita
  `create_new_workflow=True`, corpo `jIps6` capturado com envio bloqueado e
  validado no Windows; padrão False preserva histórico da origem. Edição 4s/
  360p/16:9 em novo workflow e três refinamentos no mesmo workflow concluíram,
  quatro MP4 H.264/AAC 640×360 decodificados integralmente. Custo total 40;
  saldo 882→842. Confirmado 330/500, reserva 7: contabilizados 337/500,
  restantes 163. Suítes WSL/Windows: 165 testes; MCP: 60 ferramentas.
  Anexar um vídeo no compositor produziu edição, não MZZa6b; o segundo vídeo
  selecionado não entrou nessa captura. Ingredientes de vídeo continuam sem
  validação, tarefa antiga incerta não foi reenviada. Equivalência contextual
  da cadeia com a conversa da interface segue sem prova.

- Cenas nativas (03/10/2026): `flow_manage_scene` cria cenas (`rqZuUc`+`oWTRd`),
  inclui clipes (`oWTRd`), reordena/apara (`GoMJte`), remove clipes, renomeia e
  arquiva para lixeira (`BpMsoe`). Confirmações por leitura `Zzl0ze` sem reenvio.
  4 clipes, reordenação/corte 0,5–6,25s, remoção e lixeira validados no Windows.
  `flow_export_scene` nativo (`GjQLTd`+`IxdSwd`) validado: 4 clipes em MP4
  29,79s. Exclusão definitiva (`BatchDeleteScenes`), restaurar e paginação
  pendentes. Sem créditos gastos (saldo 842; 330/500 confirmados, 337
  contabilizados, 163 restantes). Suítes WSL/Windows: 175 testes nessa etapa.

- Vídeo como referência, ferramentas e Agent (03/10/2026): Flow não aceita vídeo
  como ingrediente (recusado em MZZa6b; @ vira edição jIps6); reference_video_paths
  removido e IDs de vídeo rejeitados pré-envio para flow_edit_video.
  flow_list_tools validado no Windows via tRARke (69 applets: 34 comunidade,
  34 modelos, 1 própria). flow_get_agent_brief retorna http_error no Aisandbox
  e precisa migrar; GetSession (GN0Bre) traz metadados sem mensagens. Sem gastos
  (saldo 842; 330/500 confirmados, 337 contabilizados, 163 restantes). Suíte WSL:
  172 testes; MCP: 62 ferramentas.

- Voz pronta em vídeo (03/10/2026): Flow envia voz apenas com imagem (MZZa6b r2v,
  campo 7); flow_generate_video aceita voice (omni-flash + imagem obrigatórios).
  Omni Flash 4s/360p com imagem e voz Achernar validado no Windows: MP4 640×360 com
  áudio AAC audível (−22,7 dB), custo 4, saldo 842→838. Gasto: 334/500 confirmados,
  341 contabilizados, 159 restantes. Suíte WSL: 173 testes; MCP: 62 ferramentas.

- Restaurar e excluir cena (03/10/2026): `flow_manage_scene` ganhou `restore`
  (`BpMsoe`) e `delete` permanente (`cz8Z4b`, exige `confirm=true` e cena na lixeira).
  Validados no Windows: restore, novo arquivamento e delete definitivo confirmados
  por leitura sem reenvio. Sem créditos gastos (saldo 838; 334/500 confirmados,
  341 contabilizados, 159 restantes). Suíte WSL: 174 testes; MCP: 62 ferramentas.

- Personagens nativos (03/10/2026): `flow_list_characters` e `flow_manage_character`
  migrados para HTTP nativo (`C4BZMd` + `Sc7aEb` para criar com imagem do projeto,
  `rzMKMb` para renomear e `cz8Z4b` para excluir com `confirm_delete=true`).
  Validados no Windows: criação a partir de imagem do projeto (1 referência),
  renomeação e exclusão definitiva confirmadas por leitura de `Zzl0ze`.
  `parse_assets` atualizado para ignorar cópias internas de mídias de personagens.
  Sem créditos gastos (saldo 838; 334/500 confirmados, 341 contabilizados,
  159 restantes). Suíte WSL: 176 testes; MCP: 62 ferramentas.

- Personagem como ingrediente (03/10/2026): `flow_generate_video` aceita
  `character_ids` (1–3 personagens de `flow_list_characters`), enviando `MZZa6b`
  com o personagem no campo 9; `voice` agora aceita imagem ou personagem.
  Validado no Windows: Omni Flash 4s/360p com personagem de teste concluiu e
  baixou MP4 640×360 (4,011s), custo 4, saldo 838→834. Gasto: 338/500 confirmados,
  345 contabilizados, 155 restantes. Suíte WSL: 176 testes; MCP: 62 ferramentas.

- Flow Agent por HTTP e incidente (03/10/2026): `flow_agent_request` conversa
  com o Flow Agent via `StreamChat` com streaming `wrb.fr` e extração de
  `literalString` A2UI. Três perguntas validadas no Windows sem créditos; Agent
  pode conter imprecisões/alucinações. Incidente de 7 créditos por submissão
  de placeholder em UI (Omni 4s/720p; saldo 834→827) mitigado por bloqueio de
  RPCs de geração no preparo e controle de preferências antes do envio.
  `flow_update_user_settings` corrigido para payload protobuf compatível.
  Gasto: 345/500 confirmados, 352/500 contabilizados, 148 restantes; saldo 827.
  Suíte WSL: 178 testes; MCP: 63 ferramentas.
- Agent (03/10/2026, cont.): `flow_agent_request(session_id=...)` continua
  conversas, validado sem custo. Despacho de `create/delete_agent_session`
  restaurado no worker (falhavam com http_error) e validado no Windows; teste
  novo exige despacho para toda ação MCP. Saldo 827. Suíte WSL: 179 testes.
- Brief do Agent nativo (03/10/2026): `flow_get_agent_brief` e
  `flow_update_agent_brief` migrados para HTTP nativo (leitura em `Zzl0ze`
  payload[7] e mutação `Kcr7Ub` com máscara `project_brief`). Validado no
  Windows pelo MCP: leitura, substituição por cartões e restauração confirmadas
  sem créditos (saldo 827). Suíte WSL: 181 testes; MCP: 63 ferramentas.
- Voz e personalidade do personagem (03/10/2026): `flow_manage_character(update)`
  aceita `voice` e `personality` via `rzMKMb`. Validado no Windows no
  personagem de teste "Lake keeper" (voz achernar e personalidade gravadas e
  lidas de volta; `flow_list_assets` preservado) sem créditos (saldo 827).
  Suíte WSL: 184 testes; MCP: 63 ferramentas.
- Cena vazia (03/10/2026): remover o último clipe envia `GoMJte` só com projeto
  e cena; `flow_manage_scene(remove)` permite esvaziar, validado no Windows.
  Brief nativo e voz/personalidade de personagem também validados. Suíte WSL: 184.
- Personagem (03/10/2026): trocar retrato/segunda imagem via `Sc7aEb` não
  reproduziu por HTTP (3 tentativas sem efeito, sem custo); não exposto.
- Personagem por descrição (03/10/2026): `flow_manage_character(create)` aceita
  `description` + `max_credits`, criando personagem (`C4BZMd`) e retrato gerado
  com `ogiZ0b` (Nano Banana 2). Validado no Windows: "Faroleiro" criado com
  retrato gerado e vinculado (1 referência), custo 0, saldo 827; depois excluído.
  Voz personalizada indisponível (apenas presets fixos). Suíte WSL: 186 testes;
  MCP: 63 ferramentas. Saldo mantido em 827.
- Retrato e corpo do personagem (03/10/2026): `flow_manage_character` ganhou
  `set_image` (imagem do projeto ou `description` + `max_credits`; slot ocupado é
  esvaziado antes) e `remove_image`, com `slot` portrait/body (`Sc7aEb` posição
  0/1, `rzMKMb` `image_references`, `ogiZ0b`). Validado no Windows, sem créditos
  (saldo 827; 345/500 confirmados, 352 contabilizados). `parse_assets` ignora a
  cópia interna do corpo. Suítes WSL/Windows: 192 testes; MCP: 63 ferramentas.
- Arquivamento de ativos (03/10/2026): `flow_delete_asset` migrado para `pGCYOe`
  (HTTP nativo, lixeira) com confirmação pela marca `archived` em `Zzl0ze`;
  `parse_assets` expõe `archived`. Validado no Windows no vídeo de teste não
  intencional. Sem créditos gastos (saldo 827; 345/500 confirmados).

- Cotação e saldo (04/10/2026): `flow_quote_video` cota geração/edição/extensão pelo
  catálogo `HTrJv` com as validações do envio real, sem prepare/POST e sem criar
  tarefa (`quote_only`). Gerações de vídeo/imagem gravam `credits_before`,
  `credits_after` e `credits_charged_observed` (leitura única de `nzlxg`; débito pode
  atrasar). Validado no Windows: edição 20, Omni 6s 10, Veo Lite 8s 10, sem envio.
  Segunda conta `conta-b` conectada (saldo 1050). Vídeos a pedido do usuário: 50
  créditos cotados (10+20+20); saldo seguiu 827 porque o Google concede 50
  créditos diários (informado pelo usuário): 827+50−50. Explica também 856→906 e 892→942. Contabilizados 402/700. Suítes WSL/Windows: 196; MCP: 64.
- Contas por e-mail (04/10/2026): `account_id` aceita o e-mail Google (resolvido pelo
  `.gflow_account` do perfil) ou o apelido; respostas incluem `email`; o status grava o
  e-mail só com sessão autenticada. O servidor envia `instructions` exigindo perguntar a
  conta (e-mail, saldo, cotação) antes de gastar quando houver mais de uma. Perfil
  `conta-b` foi movido da pasta padrão do gflow-cli para `profiles/` (login feito fora do
  ambiente do MCP). Validado no Windows: duas contas autenticadas, saldo consultado pelo
  e-mail. Suítes WSL/Windows: 200 testes; MCP: 64 ferramentas. Sem gasto.
  Perfil antigo `conta-a` (WSL) removido a pedido do usuário; 419 tarefas antigas dele em `profiles/jobs` preservadas.
- Banana Pi e keepalive (05/10/2026): sessão copiada do Chrome Windows caiu em ~11 h
  na Pi. Nova abordagem: `deploy/login_para_pi.py` abre Chrome limpo no Windows
  (perfil temporário, sessão própria), o usuário faz login e os cookies seguem por
  pipe SSH para `deploy/importar_sessao.py` na Pi (nunca em arquivo nem no log).
  `keepalive.py` ganhou trava, pausa com jitter, estado persistente, `needs_login`
  após 2 falhas e fingerprint da rotação do cookie. Objetivo: 9 contas na Pi.
  Andamento em AI Memory `projeto/em-andamento.md`.
- 9 contas na Pi (05/10/2026): contas configuradas com login limpo; saldo HTTP confirmado em todas.
  Nome do perfil = prefixo do identificador da conta. Conta que nunca abriu o Flow mostra popup
  de primeiro acesso e o saldo fica `unavailable` até aceitá-lo (aceite é da
  conta); `login_para_pi.py` deixa a janela 1 min após o Flow carregar e relê os
  cookies a cada 5 s. Uma janela por conta. Perfis antigos `conta-b`/
  `conta-ponte-a` removidos da Pi. Cron `*/30` roda `keepalive.py` com log/estado
  em `/mnt/ssd/flow-mcp/logs/`. Sem gasto de créditos.
- Mudanças do Flow (05/10/2026): catálogo com proporções repetidas/0 nas imagens;
  Nano Banana 2 substituído por 2.1 (`beluga_display`, `nano-banana-2` aponta
  para ele); mídias novas sem versão (versão 1 omitida); projeto vazio com listas
  nulas. Corrigido em `e938689`. Teste entre contas: ddv1 gerou vídeo (10),
  download + upload para ddv4 (aviso de direitos aprovado), ddv4 editou para
  anime (20). Flow não tem projeto compartilhado entre contas.
- Deploy contínuo (05/10/2026): `.github/workflows/deploy-pi.yml`. Push na `main`
  roda a suíte no GitHub (Ubuntu + ffmpeg) e, se passar, o runner self-hosted
  `banana-pi` (serviço systemd em `/mnt/ssd/flow-mcp/actions-runner`) faz rsync
  para `/mnt/ssd/flow-mcp/app`, `uv sync --locked` e grava o commit em
  `app/.deployed`. Perfis, logs e downloads ficam fora de `app/`.
- MCP por HTTP na LAN (06/10/2026): `flow_mcp.py --http` serve streamable HTTP em
  `0.0.0.0:8765/mcp`, exigindo `Authorization: Bearer` (`FLOW_MCP_HTTP_TOKEN`; sem
  ele não sobe). Na Pi roda como serviço `flow-mcp` (`deploy/flow-mcp.service`,
  token em `/mnt/ssd/flow-mcp/http.env`, modo 600); o deploy reinicia o serviço.
  A Pi passa a ser o MCP principal; caminhos de arquivo das ferramentas são da Pi.
- Estabilidade (06/10/2026): `flow_errors.error_fields` repassa ao agente só
  mensagens escritas pelo MCP (rede/backend viram dica); `next_step` por status.
  Leituras (ativos, projetos, coleções, personagens, ferramentas, cenas, catálogo
  HTrJv) ignoram linhas em formato novo em vez de falhar; mutações e composição
  de cena seguem estritas. Pipe do worker aceita respostas >64 KiB (antes
  derrubava o worker). Leitura com HTTP≠200 recopia cookies do Chrome e repete
  uma vez; mutação nunca. Workers esperam 45 s pelo lease do perfil; keepalive
  trata perfil ocupado como `busy`. `flow_status` mostra máquina, versão e
  pastas, Chrome/ffmpeg disponíveis. Worker fecha o Chrome após 15 min ocioso
  (`FLOW_MCP_WORKER_IDLE_SECONDS`). Conta ocupada por mais de 30 s responde
  `account_busy` (nada enviado); `flow_wait_job` continua esperando. Erro inesperado
  no próprio código traz `error_location` (arquivo:linha). `flow_list_accounts` traz
  `keepalive.needs_login` por conta (Pi). Saldo `nzlxg` e `Zzl0ze` aceitam campos/
  seções novas no fim. Deploy confere HTTP 401 em /mcp após reiniciar.
  Diagnóstico: `logs/operations.jsonl` na Pi (ou `FLOW_MCP_LOG`), só campos seguros.
  **Bug de deploy corrigido**: sem `FLOW_MCP_OUTPUT` na Pi os downloads ficam em
  `app/downloads`, que o `rsync --delete` apagava a cada push; agora o rsync protege
  downloads/profiles/exports/logs. `flow_status` mostra `disk_free_mb`.
  `flow_recover_job` passa a distinguir geração perdida no Flow: POST aceito, mas a
  mídia não aparece na listagem nem no `as29s` → `recovery_status=not_found` com
  orientação (antes tentava baixar e falhava com erro genérico). As duas tarefas Omni
  de 06/10 (c7a120a2, c15715a2) foram reclassificadas assim, sem reenvio.
  `flow_wait_job` para com `wait_status=not_found` após 3 consultas assim.
  `flow_account_status` confirma por HTTP (listagem de projetos) quando a checagem do
  navegador falha — no Linux ela dá `google_session_only` com sessão válida (ddv1 na
  Pi agora aparece `authenticated`, `verified_by=HTTP/UpteDb`). Saldo não clica mais no
  menu da conta (usa a sessão da listagem); conta deslogada é detectada em ~12 s.
  A Pi não tem ffmpeg (ferramentas locais de vídeo falham lá). Suítes WSL/Windows: 235 testes; MCP: 65 ferramentas (novo `flow_quote_images`).
- ffmpeg na Pi (06/10/2026): em máquina ARM só `flow_save_frame` usa ffmpeg (1 thread,
  `nice 19`); `flow_export_gif`, `flow_build_scene` e `flow_upscale` recusam antes de
  baixar e apontam as alternativas nativas (`flow_export_scene`, `flow_upscale_video`/
  `flow_upscale_image`). `flow_status` lista as indisponíveis. Suíte: 236 testes.
- Login nativo na Pi (06/10/2026): sessões importadas do Windows caíram em ~1 dia;
  login direto na Pi (`login-remoto.sh`, noVNC por HTTP na LAN) da ddv1 durou 16 h+.
  As 9 contas foram relogadas assim. O script reabre o navegador (até 3 vezes) quando
  o Flow abre antes de a sessão estar gravada. Não sobrescrever o script com uma janela
  aberta (bash lê o arquivo enquanto roda); trocar com `mv`.
- Teste ponta a ponta (06/10/2026, ddv1): 4 imagens Nano Banana 2.1 (custo 0),
  personagem com voz Charon, 3× Omni Flash 10s/720p r2v (45 créditos, 1050→1005),
  cena nativa exportada em MP4 30 s. Corrigido `parse_assets`: mídias sem versão
  em projeto com personagem eram ocultadas (listagem vazia, `reference_asset_ids`
  recusado); cópias agora só por IDs do personagem (`64d220a`, validado na Pi).
- Compositor só de Agent (08/10/2026): contas que nunca usaram o compositor clássico
  (ddv2, ddv3, ddv6, ddv7) abriam o Flow só com o Agent (`FlowAgentUiError`) e não
  geravam. Ligar e desligar `agent_mode_enabled` devolve o clássico de vez;
  `flow_http.prepare_generation` faz isso sozinho antes de desistir. O worker passou a
  rodar do módulo importado (como `__main__`, suas exceções não batiam com os `except`
  dos chamadores). Fallback de vídeo via Agent (`flow_agent.agent_generate`): aprova
  só se o custo informado pelo Agent for igual à cotação. Reaproveitar o reCAPTCHA do
  StreamChat num POST direto dá `PUBLIC_ERROR_UNUSUAL_ACTIVITY`; não repetir. As 7
  contas ativas geram. Suíte: 242 testes. Gasto de teste: 4 créditos (ddv2).
- Contas removidas (09/10/2026): o Google derrubou contas inativas; a
  pedido do usuário os perfis foram apagados da Pi (`home/profile_*`) e as entradas
  saíram de `logs/keepalive-state.json`. Restam as contas ativas, todas `authenticated`.
  Não relogar as contas removidas. Sem gasto de créditos.
