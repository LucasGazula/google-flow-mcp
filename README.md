# Google Flow MCP

Projeto independente para disponibilizar Google Flow a agentes por MCP local,
usando as contas e os créditos do usuário. Vídeos são o foco principal.

## Estado atual

O servidor MCP por `stdio` oferece 63 ferramentas implementadas:

- Contas e sessão: `flow_status`, `flow_list_accounts`, `flow_connect_account`, `flow_account_status`, `flow_begin_account_connection`, `flow_complete_account_connection`, `flow_get_credits`.
- Projetos: `flow_list_projects`, `flow_create_project`, `flow_rename_project`, `flow_delete_project` (confirmação explícita), `flow_download_project`, `flow_project_summary`, `flow_get_capabilities`.
- Preferências da conta: `flow_get_user_settings`, `flow_update_user_settings`. A atualização confirma o estado por leitura; ativar vídeos silenciosos exige confirmação explícita porque pode consumir créditos.
- Coleções: `flow_list_collections`, `flow_create_collection`, `flow_rename_collection`, `flow_move_assets`, `flow_download_collection`. `flow_list_assets` filtra por associação direta; `flow_download_collection(recursive=true)` inclui subcoleções conhecidas.
- Ativos e Mídia: `flow_list_assets` (filtros por coleção, `kind`, tamanho, ordenação e limite), `flow_search_assets` (busca por nome/ID entre projetos), `flow_get_asset`, `flow_upload_image`, `flow_upload_asset`, `flow_confirm_upload`, `flow_download_asset`, `flow_delete_asset` (arquiva o workflow após confirmação explícita). Upload de vídeo usa a interface do Flow; se aparecer o aviso de direitos, a ferramenta solicita autorização explícita antes de confirmá-lo.
- Geração e Edição de Imagem: `flow_generate_images`, `flow_edit_image` (seleção, desenho e referências locais ou por ID do projeto), `flow_crop_image`, `flow_upscale_image` (upscale nativo de imagem).
- Geração e Edição de Vídeo: `flow_generate_video`, `flow_edit_video`, `flow_refine_video`, `flow_extend_video`, `flow_upscale_video`.
- Multimídia, Cenas, Personagens, Agent, Tools e Upscale: `flow_save_frame`, `flow_export_gif`, `flow_build_scene`, `flow_manage_scene`, `flow_list_scenes`, `flow_export_scene`, `flow_list_characters`, `flow_list_voice_presets`, `flow_manage_character`, `flow_get_agent_brief`, `flow_update_agent_brief`, `flow_list_agent_sessions`, `flow_create_agent_session`, `flow_rename_agent_session`, `flow_delete_agent_session`, `flow_agent_request`, `flow_list_tools`, `flow_upscale`.
- Tarefas e Recuperação: `flow_list_jobs`, `flow_get_job`, `flow_recover_job`, `flow_wait_job`, `flow_cancel_job`, `flow_clean_jobs`.

Validação de 03/10/2026: Pro com quatro imagens, edição Lite com três e edição
Nano Banana 2 com quatro concluíram no Windows, totalizando 11 imagens
1024×1024 a custo zero. Quadros inicial/final por IDs do projeto e dois turnos
de refinamento concluíram em Omni Flash 4s/360p, com downloads e workflow
preservado. Gasto confirmado 290/500; incluindo reserva de 7 por tarefa antiga
incerta, 297/500 contabilizados, 203 restantes. Saldo observado: 882.
Suítes WSL/Windows: 159 testes. Detalhes e pendências em
[IMPLEMENTACAO-FLOW.md](docs/IMPLEMENTACAO-FLOW.md).

O backend reutiliza `gflow-cli==0.79.1`, fixado no lockfile.
Consultas de projetos/ativos e downloads de imagem/vídeo por HTTP foram validados no Windows. O worker mantém o contexto autenticado em headless.
Upload de imagem usa um único POST HTTP após fechar a página de preparo;
upload de vídeo usa o seletor de arquivo do Flow.
Geração de vídeo, extensão, edição e geração de imagens usam HTTP com corpos montados em Python. Catálogo e preços por plano determinam modelo, formato e custo. A geração de vídeo aceita 360p ou 720p quando a variante está disponível na conta; Omni Flash 8s/360p foi validado no Windows. O navegador prepara a sessão e o reCAPTCHA pelo fluxo normal do site, com seu envio abortado; o POST nativo ocorre após fechar a página de preparo.
O acompanhamento dos vídeos, criação/renomeação de projetos e consulta de saldo
ocorrem por HTTP. Projetos e saldo reutilizam o worker da conta. A leitura de
capacidades e a conferência de configuração/custo usam o catálogo HTTP.
Vídeo por texto e download foram validados em uma conta Windows: Veo Lite
8s/720p/16:9 e Veo Fast 8s/720p/9:16. Imagem Nano Banana 2 e recuperação de
vídeo também foram validados. Roteamento automático ainda não existe.
Veo Lite com quadro inicial (10 créditos) e Omni Flash 4s/720p (7 créditos)
foram gerados e baixados no Windows. O gasto acumulado da etapa de validação
é 244 dos 500 créditos autorizados; o último saldo confirmado é 856.
Uma leitura posterior retornou 906 antes e depois de uma tentativa de upscale
que parou antes do envio; a diferença 856→906 segue sem explicação e não altera
o gasto contabilizado.
Um lote de dois vídeos Veo Lite foi validado em um único envio pelo MCP,
com custo total de 20 créditos, inclusive por HTTP. A edição textual de uma imagem Nano Banana 2
também foi validada, com custo zero e histórico de versões preservado.
Corpos nativos de imagem com referência, edição e vídeo foram validados pelo
MCP no Windows. Veo Lite com quadro inicial e Omni Flash 4s com inicial/final
ou referência passaram pelo envio, acompanhamento e recuperação, com custos
de 10 e 7 créditos respectivamente. Upload e edição textual de vídeo enviado
foram validados no Windows; a edição custou 20 créditos. A suíte completa
passou com 125 testes após a correção da resposta vazia do Agent. Nano Banana 2 e Veo
Lite foram gerados, baixados e recuperados no mesmo contexto Chrome headless no
Windows. A geração Nano Banana 2 com referência por ID do projeto foi validada
no Windows a custo zero; reuso de IDs na edição simples e em lote também foi
validado sem custo. A autenticação ainda depende do navegador.
Captura e importação de cookies são experimentais. A integração
com uma conta real foi validada no Chrome Windows: o perfil `conta-ponte-a`
retornou `authenticated` após login manual e fechamento do navegador. A captura
pela extensão recebeu cookies, mas não restaurou sozinha o acesso ao Flow.
MoneyPrinterTurbo e ChatGPT são etapas futuras.

## Executar

Requisitos: Python 3.11 ou superior e [uv](https://docs.astral.sh/uv/getting-started/installation/).
Na pasta do projeto:

```bash
uv sync --locked
uv run --locked python flow_mcp.py
```

O processo aguarda mensagens MCP pela entrada padrão. Para verificar a conexão
com um cliente real, listar as ferramentas e consultar uma conta sem sessão:

```bash
uv run --locked python -m unittest -v
```

## Conectar um cliente MCP

Exemplo para clientes que usam a configuração `mcpServers`:

```json
{
  "mcpServers": {
    "google-flow": {
      "command": "uv",
      "args": [
        "--directory", "/caminho/absoluto/google_flow_mcp",
        "run", "--locked", "python", "flow_mcp.py"
      ]
    }
  }
}
```

Substitua o caminho pelo diretório real. O cliente precisa encontrar `uv` no seu
ambiente; se necessário, use o caminho absoluto do executável em `command`.
No Windows nativo, use o caminho Windows com barras escapadas (`C:\\...`). Para
rodar no WSL, o cliente deve executar o comando dentro do WSL. Os testes locais
rodam em WSL e Windows. O login foi validado no Chrome Windows; Raspberry Pi
ainda precisa de validação.

## Desenvolvimento

[Plano e ferramentas propostas](PLANO-MCP.md), [pesquisa de bases](PESQUISA-FLOW-MCP.md)
e [autenticação e portabilidade](docs/AUTENTICACAO-PORTABILIDADE.md).
O [acompanhamento da implementação](docs/IMPLEMENTACAO-FLOW.md) registra a cobertura
e o orçamento autorizado dos testes. A segunda conta foi adiada pelo usuário.

## Conectar contas sem gastar créditos

Instale Chrome no mesmo sistema operacional do processo MCP. No cliente, chame
`flow_connect_account(account_id="conta-a")` e conclua o login na janela dedicada
(até dez minutos). Repita com `conta-b`. Cada apelido identifica um perfil separado;
confira a conta Google escolhida na janela. O MCP não acessa seu perfil pessoal.

`flow_list_accounts()` lista os perfis salvos, sem validar a sessão.
`flow_get_credits(account_id="conta-a")` consulta o saldo remoto sem geração.
`status="ok", credits=0` é saldo zero; `status="unavailable", credits=null`
é uma leitura inconclusiva. Não estima o custo de geração.
A consulta usa o RPC `nzlxg` do host atual. O Chrome headless dedicado prepara a sessão
quando necessário e fecha a página antes da consulta HTTP; leituras seguintes reutilizam
o worker. A resposta identifica a fonte e o horário. Duas consultas HTTP pelo
MCP confirmaram 946 créditos no Windows.
Formatos não reconhecidos continuam indisponíveis.
`flow_account_status(account_id="conta-a")` verifica a sessão no Flow. O resultado
`authenticated` confirma apenas a sessão, não suporte à geração ou saldo.
`needs_login` indica ausência de sessão salva; `no_session`, `google_session_only`
e `profile_marker_missing` exigem conferir/refazer o login. `verification_error`
indica que a consulta não foi conclusiva, sem assumir que a sessão expirou.

Perfis ficam em `profiles/` ao lado do servidor. Defina `FLOW_MCP_HOME` com um
caminho absoluto privado para usar outro local; mantenha-o fora do Git. Essa
variável precisa ser repassada ao processo pelo cliente MCP. Logs do backend e
mensagens de exceção não são encaminhados nas respostas MCP.

No Windows, execute MCP e Chrome no Windows; Chrome Windows não é detectado
como Chrome Linux pelo processo no WSL. Ao compartilhar esta pasta entre Windows
e WSL, use `$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"` no PowerShell antes
dos comandos `uv`; isso preserva o ambiente Linux em `.venv/`.
No Raspberry Pi, login exige navegador
compatível e uma tela acessível, física ou virtual. Esses ambientes e a
portabilidade das sessões continuam sem validação.

As operações de diagnóstico e conexão não geram mídia nem alteram a preferência
de aprovação de gastos. `flow_generate_video` consome créditos autorizados.
Não versionar cookies, tokens ou perfis de navegador.

## Gerar um vídeo com orçamento

Para acompanhar uma tarefa já enviada, use
`flow_wait_job(account_id, job_id, timeout_seconds=60, poll_interval_seconds=5)`.
A ferramenta consulta e recupera os arquivos da tarefa original, sem gerar outra
cópia. Aceita até 600 segundos de espera; zero realiza uma consulta. O prazo
limita novas consultas, mas um download em andamento pode ultrapassá-lo.
`wait_status=timeout` preserva o estado original para retomada posterior;
`unavailable` indica falha de consulta e `stopped` indica parada local ou falha
confirmada. Cancelar localmente não cancela a geração remota nem devolve créditos.

Após autorização de gasto, chame no cliente MCP:

```text
flow_generate_video(account_id="conta-ponte-a", prompt="Uma paisagem ao amanhecer", max_credits=10)
```

O padrão gera um único clipe Veo Lite, 8 segundos, 720p, 16:9.
Os argumentos `model`, `aspect`, `duration_seconds`, `start_image`, `end_image`,
`reference_images`, `reference_asset_ids`, `character_ids` e `voice` configuram
outros modos; `count=1–4` determina a quantidade. Um lote de duas saídas foi
validado com custo total de 20 créditos. `character_ids` recebe de 1 a 3 IDs de
personagens de `flow_list_characters` (exige `model="omni-flash"`), validado no
Windows com Omni Flash 4s/360p (custo 4 créditos). `voice` aceita um preset de
`flow_list_voice_presets`, exige `model="omni-flash"` e ao menos uma referência
de imagem ou personagem; Omni Flash 4s/360p com imagem e voz Achernar foi validado
no Windows com custo de 4 créditos.
Modelo/configuração ausentes do catálogo impedem o envio. Veo Fast vertical foi
validado com custo de 20 créditos. O custo por plano e quantidade é conferido antes
do envio; custo desconhecido ou acima de `max_credits` impede o envio. Não há troca
automática de modelo, conta ou configuração. `project_id` opcional reutiliza um
projeto; caso contrário cria um novo. O suporte atual usa `flow.google.com`.

O pedido aguarda geração e download, até 20 minutos. Configure o timeout do
cliente para pelo menos 21 minutos. Arquivos ficam em `downloads/`; use
`FLOW_MCP_OUTPUT` para configurar outro diretório absoluto. Tarefas ficam em
`profiles/jobs/`. A resposta traz `job_id`, conta, custo observado, IDs e arquivos.

`flow_get_job(account_id, job_id)` lê o último estado salvo, inclusive após
reiniciar o MCP. Não faz polling remoto nem reenfileira a tarefa.
`submission_unknown` e `generation_unknown` exigem conferir a geração original;
`download_failed` preserva os IDs. `flow_recover_job(account_id, job_id)` abre a
página da mídia existente e baixa os arquivos, inclusive lotes, sem reenviar
geração ou gastar créditos.
Exige IDs confirmados; falha preserva o estado anterior e retorna
`recovery_status="unavailable"`. Não reenviar geração para corrigir falha de download.
A recuperação foi validada no Windows: arquivo original de 4.467.164 bytes,
1280×720, 8 segundos, saldo inalterado. A resposta de status do clipe é usada
para evitar confundir a miniatura da listagem com o vídeo.

`flow_create_project(account_id, title)` cria um projeto privado;
`flow_rename_project(account_id, project_id, title)` altera o título. Ambas
foram validadas por HTTP pelo MCP no Windows e não geram mídia. Renomear preserva
a capa atual. Resultado inconclusivo retorna `submission_unknown`, sem reenvio.
`flow_list_projects(account_id, query="")` consulta IDs e títulos da conta no host atual;
sete projetos foram observados, incluindo um ID legado com sufixo `_backfill`.
Após criar o novo projeto de validação HTTP, a consulta retornou oito projetos.
Não usa o catálogo local como substituto da consulta remota. Formato desconhecido
falha; `query` filtra ID/título sem distinção de caixa, e campos adicionais na
resposta mantêm `complete=false` para sinalizar que a busca pode ser parcial.

`flow_delete_project(account_id, project_id, confirm_delete=true)` envia o RPC
`QI2zvc` uma vez, depois confirma a ausência em uma listagem completa. Em caso
incerto, não reenvia. Cobertura local implementada; validação remota no Windows
ainda pendente.

`flow_create_collection(account_id, project_id, title, parent_collection_id)`
cria com o nome inicial padrão do Flow e, se necessário, renomeia em uma segunda
chamada. `flow_rename_collection` atualiza o nome diretamente. Respostas
inconclusivas são reconciliadas por leitura do projeto, sem repetir a mutação.
`flow_list_collections` inclui coleções vazias na primeira resposta do projeto;
`complete=false` preserva a incerteza de paginação. Listagem e renomeação foram
validadas no Windows.
`flow_move_assets` aceita IDs de ativos de imagem/vídeo e uma coleção de destino;
sem `collection_id`, move para a raiz do projeto. Usa o workflow de cada ativo
e um único RPC em lote. Após o envio, relê o projeto e confirma cada associação
direta observada; ativos sem confirmação aparecem em `unconfirmed_asset_ids`.
Uma falha ambígua não é reenviada. Mover um ativo para a coleção e de volta à
raiz foi confirmado por leitura no Windows.
Uma criação no Windows retornou `submission_unknown` porque a resposta não foi
reconhecida; a leitura posterior mostrou a coleção com o título inicial padrão.
O pedido não foi repetido. A reconciliação por leitura foi adicionada ao código.

`flow_list_assets(collection_id=...)` filtra pela associação direta retornada no
workflow do projeto. `flow_download_collection` baixa esses ativos para uma
pasta local; por padrão inclui apenas ativos diretos.
`flow_download_collection(recursive=true)` percorre a árvore de coleções da
primeira resposta do projeto e baixa os ativos descendentes na mesma pasta.
Criação de subcoleção, movimento, download recursivo e retorno à raiz foram
validados no Windows. `complete=false` explicita a paginação não verificada.

`flow_get_user_settings` lê preferências globais da conta. `flow_update_user_settings`
atualiza somente os campos informados e confirma por leitura; uma resposta
incerta não provoca reenvio. Ativar `return_silent_videos` exige
`confirm_credit_impact=true` porque vídeos sem áudio podem consumir créditos.
A leitura foi validada no Windows pelo worker HTTP (seis campos; valores não
foram registrados). A atualização continua sem validação Windows.

`flow_list_agent_sessions` lista IDs e títulos da primeira resposta do projeto;
`flow_create_agent_session` usa `csbIsb` e o seed já usado pelo frontend;
`flow_rename_agent_session` confirma o título por leitura posterior;
`flow_delete_agent_session` exige `confirm_delete=true` e apaga o histórico
permanentemente. As mutações são reconciliadas sem reenvio, e rename/delete só
atuam em sessões presentes na primeira resposta. `flow_list_tools` consulta
applets internos do Flow (próprias, modelos Google ou comunidade) via HTTP
(`ListApplets`), validado no Windows com 69 ferramentas listadas e filtro textual.
Paginação e mensagens do Agent continuam pendentes. Listagem, criação e
renomeação com leitura de confirmação foram validadas no Windows. Exclusão,
paginação e mensagens ainda aguardam validação.

`flow_list_characters` e `flow_manage_character` gerenciam personagens do projeto
por HTTP nativo (`C4BZMd`, `Sc7aEb`, `rzMKMb`, `cz8Z4b`). `operation="create"`
recebe `display_name` e `image_media_id` de uma imagem do projeto; `operation="rename"`
recebe `entity_id` e `display_name`; `operation="delete"` exige `entity_id` e
`confirm_delete=true`. O ciclo completo de criação a partir de imagem do projeto,
renomeação e exclusão foi validado no Windows a custo zero. Cópias internas de
mídia de personagens são ignoradas por `flow_list_assets` como na interface.
Personagens do projeto podem ser utilizados como ingredientes na geração de
vídeo por `flow_generate_video(character_ids=[...])`.

`flow_list_jobs(account_id, limit=100)` lista as tarefas salvas desta conta,
inclusive pedidos cujo retorno foi interrompido. Não inclui tarefas criadas fora
do MCP e não repete gerações.

`flow_generate_images` implementa Nano Banana 2/Pro, 1–4 saídas, cinco proporções
e referências locais ou IDs de imagens do mesmo projeto (sem novo upload), com
teto de créditos conferido no catálogo HTTP. Nano Banana 2
foi validado com uma imagem 16:9 e duas imagens 1:1 com referência local,
custo observado zero e saldo inalterado.
Por HTTP, foram validados uma imagem 1:1 e um lote de duas imagens com referência,
inclusive recuperação dos originais em 1024×1024, sem gasto adicional.
As demais combinações estão em validação; consulte o acompanhamento.
O upload das referências e dos quadros usa HTTP; seus IDs e nomes entram no
corpo e no prompt estruturado montados em Python. Nano Banana 2 com esse fluxo completo foi validado com teto zero.
Veo Lite com quadro inicial também passou pelo novo upload HTTP, geração e
download: 8s/720p/16:9, custo 10, saldo final 936.

`flow_edit_image` edita por HTTP a versão atual, preserva o histórico e aceita
referências locais ou `reference_asset_ids` de imagens do mesmo projeto (sem
novo upload), até quatro resultados, um polígono `selection` normalizado
e traços `drawings` (`points`, `color`, `width`). Seleção e desenho são enviados
como imagem anotada que orienta o modelo; não garantem preservar exatamente os
pixels fora da região. Essa edição passou no Windows com seleção, desenho e
referência local: dois uploads, um envio, download e recuperação, custo zero.
`reference_asset_ids` permite reaproveitar imagens do mesmo projeto sem upload;
na geração Nano Banana 2 1:1, esse caminho passou no Windows com uma saída e custo
zero. Edição simples e lote de duas imagens também passaram no worker HTTP do
Windows, com orçamento e custo cotado zero; lotes maiores continuam pendentes.
Seleção anotada combinada com referência por ID também passou no Windows por HTTP,
com leitura do resultado e sem gasto de créditos.
`flow_crop_image` recorta sem geração por IA, preserva a origem e baixa a nova
versão. Foi validado no Windows com uma saída 512×512, sem custo.
`flow_upscale_image` usa a RPC nativa migrada do Flow para imagens do projeto
em 2K e salva o resultado local; `upload_to_flow=True` também envia a imagem
final ao projeto. Validado no Windows: JPEG 2048×2048, upload e leitura
posterior, cotação zero e saldo inalterado. Chamadas com os mesmos IDs
reutilizam a tarefa, o arquivo e o upload; resultados incertos não são reenviados.
4K continua bloqueado: exige Ultra e seu pedido nativo ainda não foi confirmado.
O antigo endpoint Aisandbox não é utilizado.
`flow_upscale` continua sendo o filtro local FFmpeg para mídia e pode enviar o
resultado ao projeto; uploads de vídeo podem exigir confirmação explícita de
direitos. `flow_upscale_video` usa o controle nativo do Flow para aprimorar
Omni 360p para 720p, sem créditos nesta conta. Chamar novamente com os mesmos
IDs recupera e baixa o resultado, sem reenviar a mutação. A recuperação foi
validada no Windows, assim como Veo Lite 720p→1080p sem custo; 4K exige Ultra
e continua indisponível nesta conta.
`flow_edit_image` aceita `count=1–4`; `count=2` foi validado no Windows com duas
saídas Nano Banana 2 1:1 em 1024×1024. Um pedido `count=4` retornou três saídas
confirmadas e baixadas (`partial_result`); ambos os fluxos tiveram custo zero.
Em validação posterior, Lite `count=3` e Nano Banana 2 `count=4` concluíram
com todas as saídas 1024×1024, leitura posterior e custo zero. Pro `count=4`
também concluiu com quatro imagens. `flow_edit_video` edita até dez segundos com Omni Flash,
aceita referências locais ou IDs de imagens do projeto
e confere duração, resolução e custo no catálogo. Um vídeo enviado foi editado
no trecho 1–5 s com uma referência, em 8s/720p; download e recuperação passaram
no Windows, custo 20 créditos. O Flow não aceita vídeo como ingrediente/referência
de geração (selecionar vídeo com `@` no compositor vira edição `jIps6` em novo
workflow; envio `MZZa6b` com vídeo é recusado). `flow_generate_video`,
`flow_edit_video` e `flow_refine_video` utilizam apenas referências de imagem;
IDs de vídeo em `reference_asset_ids` são rejeitados antes do envio
(`failed_pre_submit`), com orientação para `flow_edit_video(create_new_workflow=True)`.
`flow_refine_video` encadeia até três prompts, usando a última saída e o workflow
de cada turno, com orçamento total e parada em resultado incerto.
`flow_edit_video(create_new_workflow=True)` cria um histórico separado
para a edição, preservando o original; o padrão mantém o histórico de origem.
O novo histórico e três refinamentos encadeados foram validados no Windows
em 4s/360p, com quatro arquivos decodificados e custo total de 40 créditos.
Controles dedicados de câmera/inserção/remoção de objetos seguem
pendentes. `flow_get_asset` lê versões presentes na resposta inicial do projeto;
histórico completo e paginação seguem pendentes.

`flow_edit_images` aplica o mesmo prompt a 2–10 imagens em sequência e pode
reutilizar referências por ID já presentes no projeto. Cota o lote antes do
primeiro envio e interrompe se uma tarefa ficar incerta.

`flow_get_capabilities(account_id, project_id)` lê catálogo, preços por plano e
restrições remotas da conta por HTTP, com horário e escopo. Confirma o projeto
e não gera mídia. Disponibilidade no catálogo não equivale a implementação
ou geração validada pelo MCP.

Teste real em 29/09/2026: um MP4 com H.264/AAC, 1280×720 e 8 segundos foi
baixado. Custo exibido: 10 créditos; saldo observado passou de 1.050 para 1.040.

## Reutilizar a sessão do Chrome habitual

O MCP usa o perfil dedicado do apelido escolhido, por exemplo
`profiles/profile_conta-ponte-a`, e reaproveita o login salvo nele. Estar conectado
no Chrome habitual não conecta automaticamente esse perfil dedicado.
Abrir Chrome para preparar a sessão HTTP não significa refazer o login.
Consultas reutilizam cookies e contexto HTTP em memória enquanto o worker da
conta estiver ativo. Após listar projetos, saldo e catálogo também reutilizam
essa sessão sem abrir novamente o menu da conta. Reiniciar o MCP descarta essa
sessão HTTP, mas preserva o perfil autenticado em disco.
O worker abre um contexto Chrome headless por conta, sob demanda, e o reutiliza
para consultas, uploads, geração, edição e recuperação. Cada preparo usa uma
página nova, fechada antes do POST HTTP; os envios do navegador são abortados.
O reCAPTCHA continua sendo preparado pelo fluxo normal do site, mesmo com login
salvo. As operações da conta são serializadas para não misturar pedidos.
Ao encerrar o MCP, o contexto fecha e libera o perfil. Login, importação e
verificação de sessão liberam o contexto residente antes de acessar o perfil;
o login humano continua em janela visível.

O padrão é `FLOW_MCP_HEADLESS=true`. Para diagnóstico em janela visível, defina
`FLOW_MCP_HEADLESS=false` no ambiente do servidor MCP e reinicie-o. Não há troca
automática de modo nem reenvio automático quando uma operação falha.

Leia a [revisão de segurança](docs/SEGURANCA-EXTENSAO.md). A extensão tem acesso
à sessão Google e só a envia após um clique em um pareamento iniciado por você.

1. No Chrome habitual, abra `chrome://extensions`, ative **Modo do desenvolvedor**
   e use **Carregar sem compactação** para selecionar a pasta `extension/`.
2. No MCP, chame `flow_begin_account_connection(account_id="conta-ponte-a")`.
   Uma aba de pareamento será aberta no Chrome habitual. Use o perfil onde
   suas contas Google já estão conectadas.
3. Mantendo essa aba ativa, abra a extensão **Google Flow MCP — Conectar sessão**
   e clique em **Conectar sessão**. A chave de pareamento vale por cinco minutos.
4. Depois de “Sessão enviada”, chame
   `flow_complete_account_connection(account_id="conta-ponte-a")`.
5. Na janela dedicada, escolha a conta Google e conclua o acesso ao Flow.
   O navegador fecha e o MCP verifica a sessão. Não há geração ou gasto.

O pareamento envia a sessão Google do perfil habitual, que pode incluir várias
contas. Escolher uma conta identifica o perfil de destino, mas não elimina os
cookies das demais contas Google capturadas. A seleção correta e o acesso ao
Flow precisam ser validados antes de qualquer geração futura.

Sem cliente MCP, no PowerShell do Windows:

```powershell
$env:UV_PROJECT_ENVIRONMENT = ".venv-windows"
uv run --locked python flow_session.py connect conta-ponte-a
```

Esse comando abre a aba e aguarda a extensão; após o envio, abre o seletor Google.
Para outra conta, repita com outro apelido. Perfis já identificados como
conectados não são substituídos automaticamente.

## Capturar no PC e importar no Raspberry

A extensão pode ficar apenas no PC. Para capturar um arquivo de transporte:

```powershell
uv run --locked python flow_session.py export sessao-pc
```

O comando abre o pareamento e grava explicitamente um arquivo privado em
`exports/` após o clique. Ele contém cookies em texto claro: não envie na conversa
ou ao Git. Transfira por SSH/SCP e, no destino com navegador e tela acessível:

```bash
uv run --locked python flow_session.py import conta-a --file /caminho/privado/session.json
```

O utilitário valida o arquivo, importa em perfil dedicado, abre o seletor e
verifica a sessão. O Google pode pedir novo login; cookies não transportam chaves
de dispositivo nem todos os tipos de armazenamento. Raspberry/ARM64 e
portabilidade continuam sem teste real. Após validar, apague as cópias de
transporte. Não existe serviço de captura exposto à rede.

### Cenas no Flow migrado

`flow_list_scenes` lista e filtra cenas (incluindo flag `archived`).
`flow_manage_scene` cria cenas (`rqZuUc` ou `oWTRd`), inclui vídeos por posição
(`oWTRd`), lê composição/cortes, atualiza ordem e cortes (`GoMJte`), remove
clipes, renomeia, arquiva e restaura da lixeira (`BpMsoe`), e exclui
permanentemente (`cz8Z4b`, exigindo `confirm=true` e cena arquivada).
`flow_export_scene` renderiza e baixa a cena como MP4 via `GjQLTd` e `IxdSwd`.
Todo esse ciclo foi validado no Windows pelo HTTP nativo sem créditos. Clipes na
cena recebem IDs clonados. Paginação remota segue pendente. `flow_build_scene` realiza montagem local via FFmpeg
sem persistir a cena no Flow.

### Flow Agent e Tools internas

`flow_agent_request(account_id, project_id, message, allow_media_changes=false, session_id=null)`
envia consultas ao Agent do Flow via POST HTTP `StreamChat` com resposta em fluxo
`wrb.fr`. Extrai chamadas a ferramentas internas do projeto e a resposta textual em
`literalString` A2UI. Por padrão, `allow_media_changes=false` previne alterações
acidentais no projeto. A ferramenta ativa o modo Agent via preferências HTTP
(`flow_update_user_settings`) antes do preparo e restaura o valor original ao
término; o preparo no navegador bloqueia ativamente RPCs de geração de mídia.
`flow_list_agent_sessions`, `flow_create_agent_session`, `flow_rename_agent_session` e
`flow_delete_agent_session` gerenciam o ciclo de vida das conversas por projeto.
`flow_get_agent_brief(account_id, project_id)` lê as instruções do Agent na oitava
seção de `Zzl0ze`. `flow_update_agent_brief(account_id, project_id, enabled?, instructions?, confirm_replace_instructions=false)`
substitui o brief nativo via `Kcr7Ub` com máscara `project_brief` e confirma por leitura.
`flow_list_tools(account_id, category, query)` lista applets e miniapps por
categoria (`mine`, `templates`, `community`).

### Personagens e vozes

`flow_list_characters(account_id, project_id)` lista personagens do projeto,
incluindo `reference_media_ids`, `voice` e `personality`.
`flow_manage_character(account_id, project_id, operation="create"|"update"|"rename"|"set_image"|"remove_image"|"delete", display_name?, image_media_id?, voice?, personality?, slot="portrait"|"body", description?, max_credits?, confirm_delete=false)`
cria personagens a partir de uma imagem do projeto (`C4BZMd` + `Sc7aEb`) ou
por descrição textual com geração de retrato Nano Banana 2 (`C4BZMd` + `ogiZ0b`,
exigindo `max_credits`), atualiza nome, voz (preset) e personalidade (até 2.000
caracteres) via `rzMKMb`, e exclui permanentemente (`cz8Z4b`, exigindo `confirm_delete=true`).
`set_image` define o Retrato ou o Corpo (`slot`) com uma imagem do projeto
(`Sc7aEb`, posição 0/1) ou, com `description` + `max_credits`, gera a imagem do
slot (`ogiZ0b`); slot ocupado é esvaziado antes (`rzMKMb`, máscara
`image_references`). `remove_image` esvazia o slot. A listagem informa
`portrait_media_id` e `body_media_id`.
`flow_list_voice_presets()` lista o catálogo de vozes disponíveis. Vozes
personalizadas não estão disponíveis para criação na interface observada.




