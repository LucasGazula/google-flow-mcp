# Implementação e validação do Flow

Objetivo: cobrir os recursos de `FLOW-RECURSOS.md` na conta conectada.
Somente operações implementadas aparecem como ferramentas MCP.

## Orçamento autorizado de validação

- Teto total desta etapa: **500 créditos**.
- Saldo inicial observado: **1040 créditos**.
- Gasto confirmado nesta etapa: **345 créditos** (inclui 7 créditos de geração
  não intencional durante desenvolvimento do Agent). Uma submissão de vídeo com
  referência por ID teve custo cotado de 7, resposta incerta e saldo contraditório
  (**884→877**, depois **884**); manter esses 7 reservados no teto por cautela.
  Total contabilizado conservadoramente: **352/500**, restam **148 créditos**.
  Último saldo observado: **827**. Também seguem sem explicação diferenças
  históricas de saldo **856→906** e **892→942**.
- Revisão de sessão em 30/09/2026: consulta HTTP retornou **942 créditos**,
  sem geração. A diferença em relação a 892 não foi reconciliada; não altera
  o gasto registrado nem o teto restante desta etapa.
- O teste anterior de Veo Lite (10 créditos) ocorreu antes desta autorização.
- Registrar cada novo envio e reservar seu custo antes de clicar em gerar;
  resultado incerto continua contando no orçamento até reconciliação.

| Teste | Teto reservado | Custo observado | Resultado |
|---|---:|---:|---|
| Recuperação do clipe anterior | 0 | 0 | MP4 original recuperado |
| Criar/renomear projeto de testes | 0 | 0 | Confirmado |
| Nano Banana 2, 16:9, uma imagem | 0 | 0 | JPG gerado e baixado |
| Nano Banana 2 com referência, 1:1, duas imagens | 0 | 0 | Duas saídas baixadas, saldo inalterado |
| Veo Fast, 9:16, 8 segundos | 20 | 20 | MP4 gerado e baixado; saldo 1040 → 1020 |
| Veo Lite com quadro inicial, 16:9, 8 segundos | 10 | 10 | MP4 gerado e baixado |
| Omni Flash, 16:9, 720p, 4 segundos | 7 | 7 | MP4 gerado e baixado; saldo final 1003 |
| Edição de imagem existente, Nano Banana 2 | 0 | 0 | Primeira edição reconciliada sem reenvio; segunda edição completou pelo MCP, JPG de 516.911 bytes |
| Veo Lite, lote nativo de dois vídeos 16:9, 8s/720p | 20 | 20 no painel | Dois MP4s baixados em um único envio pelo MCP; saldo final 983 |
| Recuperação do lote de dois vídeos e da edição de imagem | 0 | 0 | Sem reenvio; lote MP4 recuperado com 3.789.671 bytes |
| Nano Banana 2 por HTTP, uma imagem 1:1 | 0 | 0 | JPG 1024×1024; navegador fechado antes do envio |
| Nano Banana 2 por HTTP, duas imagens 1:1 com referência | 0 | 0 | Lote gerado pelo MCP; recuperação original de 258.074 bytes; saldo 983 |
| Edição Nano Banana 2 por HTTP, uma imagem 1:1 | 0 | 0 | Validada pelo MCP; histórico preservado e recuperação de JPG 1024×1024 |
| Veo Lite por HTTP, lote de dois vídeos 16:9, 8s/720p | 20 | 20 | Envio, acompanhamento e download HTTP; dois MP4s, recuperação de 14.886.328 bytes; saldo 963 |
| Veo Lite por HTTP com quadro inicial 16:9, 8s/720p | 10 | 10 | Um MP4 gerado e recuperado pelo MCP: 1.486.221 bytes |
| Omni Flash por HTTP, 16:9, 4s/720p | 7 | 7 | Um MP4 gerado e recuperado pelo MCP: 1.535.543 bytes; saldo final 946 |
| Criar e renomear projeto por HTTP | 0 | 0 | Pelo MCP; título confirmado em listagem de oito projetos |
| Upload de imagem por HTTP | 0 | 0 | Arquivo confirmado na listagem; primeiro resultado reconciliado sem reenvio |
| Nano Banana 2 com upload HTTP de referência, 1:1 | 0 | 0 | Upload e geração por HTTP pelo MCP; JPG baixado, saldo 946 |
| Consultar saldo por HTTP, duas chamadas | 0 | 0 | `nzlxg` retornou 946; segunda consulta reutilizou sessão do worker |
| Veo Lite com novo upload HTTP do quadro inicial, 8s/720p/16:9 | 10 | 10 | Upload, envio `eb1hJf`, acompanhamento e download HTTP pelo MCP; saldo 936 |
| Nano Banana 2 em Chrome headless residente, 1:1 | 0 | 0 | JPG 1024×1024 de 160.929 bytes, download e recuperação sem reenvio |
| Veo Lite em Chrome headless residente, 8s/720p/16:9 | 10 | 10 | MP4 H.264/AAC de 2.168.427 bytes, download e recuperação; saldo 942 → 932 |
| Edição e extensão de vídeo via HTTP | 40 | 40 | Operações concluídas e recuperação por `as29s`; saldo 932 → 922 → 902 |
| Omni Flash por HTTP, 8s/360p/16:9 | 6 | 6 | MP4 H.264 640×360, 670.865 bytes, gerado, baixado e recuperado sem novo envio; saldo 902 → 896 |
| Upload de vídeo local | 0 | 0 | MP4 confirmado na listagem após aceite manual do primeiro aviso de direitos; segundo upload reconciliado sem reenvio |
| Edição textual de vídeo enviado | 20 | 20 | MP4 H.264 1280×720, 1.388.046 bytes, gerado, baixado e recuperado; saldo 896 → 876 |
| Edição anotada de imagem com referência | 0 | 0 | Seleção/desenho, dois uploads e um envio; download e recuperação, histórico preservado |
| Edição de vídeo enviado com referência | 20 | 20 | Trecho 1–5 s, Omni Flash 8s/720p; MP4 de 981.898 bytes, download e recuperação; saldo 876 → 856 |
| Omni Flash 4s/360p com imagem e voz Achernar | 4 | 4 | MP4 H.264 640×360 com áudio AAC, 4,011 s, decodificado por FFmpeg; saldo 842 → 838 |
| Omni Flash 4s/360p com personagem como ingrediente | 4 | 4 | MP4 H.264/AAC 640×360, 4,011 s, decodificado por FFmpeg; saldo 838 → 834 |
| Geração de vídeo não intencional durante desenvolvimento do Agent | 7 | 7 | Omni Flash 4s/720p disparado ao testar envio do Agent; saldo 834 → 827 |

## Cobertura

| Recurso | Situação |
|---|---|
| Conta, login, saldo | Implementado e validado na conta conectada |
| Vídeo por texto Veo Lite 8s/720p/16:9, uma saída | Implementado e validado, custo 10 |
| Vídeo por texto Veo Fast 8s/720p/9:16, uma saída | Implementado e validado, custo 20 |
| Vídeo por texto Omni Flash 4s/720p/16:9, uma saída | Implementado e validado por HTTP no Windows, custo 7 |
| Vídeo Veo Lite com quadro inicial 8s/720p/16:9 | Implementado e validado por HTTP no Windows, custo 10 |
| Tarefa persistida e leitura local | Implementado e testado |
| Listar tarefas locais por conta | Implementado e testado; não lista tarefas criadas fora do MCP |
| Recuperar download sem reenviar geração | Vídeo validado no Windows: MP4 original, 4.467.164 bytes, saldo inalterado. Geração de imagem com POST incerto agora confere IDs/workflows esperados na listagem e baixa a saída sem reenviar; teste local passou, validação Windows pendente |
| Demais modelos, proporções, durações e 360p de vídeo | Catálogo e teto impedem opção indisponível ou cara; Omni Flash 8s/360p/16:9 e 10s/720p/16:9 validados no Windows. O vídeo de 10 s foi recuperado como MP4 H.264 1280×720, 4.870.295 bytes; custo 15, saldo 906→891 |
| Quantidade de vídeos por pedido | Implementado: 1–4; lote de dois Veo Lite validado por HTTP pelo MCP no Windows, custo total 20 |
| Quadro inicial/final em vídeo | Omni Flash 4s/720p/16:9 validado com corpo nativo e recuperação, custo 7 |
| Referências em vídeo | Omni Flash 4s/720p/16:9 com imagem local validado via upload/corpo nativos e recuperação, custo 7. Referência por `reference_asset_ids` de imagem do projeto também validada no Windows: MP4 H.264 1280×720 de 1.347.410 bytes, custo 7. Referência de vídeo por ID cotou 7, mas retornou `submission_unknown`; listagem e `as29s` não localizaram a saída. Sem reenvio; recuperação ampliada para reconciliar IDs/workflows esperados. Upload local de vídeo como ingrediente segue sem validação Windows |
| Imagens por texto Nano Banana 2 | Validado no Windows: navegador em 16:9 e HTTP em 1:1, custo 0 |
| Nano Banana 2, referências locais, lote de duas imagens 1:1 | Validado via HTTP pelo MCP no Windows, dois JPGs 1024×1024, custo 0; `reference_asset_ids` validados na geração, edição simples e edição em lote no Windows, custo 0 |
| Nano Banana Pro e Nano Banana 2 Lite | Pro validado por HTTP no Windows com lote de três JPGs 1:1; Lite com um JPG 1:1. Ambos cotados em zero créditos, saldo 906 antes/depois. Pro `count=4` tem teste local que confirma um POST e quatro downloads; validação Windows pendente. Lite é selecionado pelo `model_id` do catálogo, independente do rótulo exibido |
| Edição textual de uma imagem atual, Nano Banana 2 | Implementado e validado por HTTP pelo MCP no Windows, custo 0; histórico preservado |
| Detalhes de ativo e versões de imagem/vídeo | Implementado no worker HTTP/MCP via `Zzl0ze`, agrupando versões observadas pelo workflow; somente resposta inicial, `complete=false`, sem URLs assinadas; histórico completo e paginação pendentes |
| Variações de uma imagem por edição (1–4 resultados) | `count=2` completo no Windows: ambas as saídas 1024×1024 lidas de volta e baixadas no workflow de origem, custo zero. `count=4` retornou `partial_result`: três saídas 1024×1024 foram lidas de volta e baixadas no mesmo workflow; a consulta do quarto ID esperado retornou `http_error`. Sem reenvio, custo zero e saldo 856 antes/depois. `count=3` e quatro saídas completas por edição pendentes; geração Nano Pro `count=3` foi validada separadamente |
| Edição simultânea de 2–10 imagens com o mesmo prompt | Lote de duas imagens com referência por ID validado via worker HTTP no Windows, custo 0; lotes de 3–10 imagens ainda não validados |
| Edição localizada/desenho | Seleção, desenho e referência local validados no Windows; referências por ID validadas separadamente na edição simples/em lote; anotação + ID validados no Windows por HTTP, uma edição, download e leitura de retorno, orçamento/custo cotado zero e saldo 856 antes/depois; a anotação orienta o modelo e não garante preservação exata fora da região |
| Recorte de imagem | Validado no Windows. A primeira saída 1024×1024→512×512 foi recuperada por `flow_download_asset` após falha inicial do download (142.689 bytes). `crop_image` agora relê `Zzl0ze` após o envio e resolve a URL pela resposta do projeto; um segundo recorte independente concluiu e baixou automaticamente, workflow preservado, custo zero e saldo 856 antes/depois |
| Edição textual Omni e extensão Veo Lite | Implementadas e validadas por HTTP no Windows, inclusive recuperação; 40 créditos no total |
| Upload de vídeo local | Validado no Windows após aceite manual do aviso de direitos; confirmação em duas etapas por `flow_confirm_upload` implementada e testada localmente, ainda sem novo aviso real |
| Modos de câmera/objetos e refinamento contextual | `flow_refine_video` agora encadeia de 1–3 edições Omni Flash, reutiliza a última mídia/workflow e aplica um orçamento total; equivalência contextual ainda sem validação remota. Controles dedicados de câmera/inserção/remoção seguem pendentes |
| Salvar quadro, upscale e GIF | Implementado (`flow_save_frame`, `flow_export_gif`, `flow_upscale` local e `flow_upscale_image` nativo para imagem). `flow_upscale_video` validado no Windows para Omni 360p→720p e Veo Lite 720p→1080p; 4K exige plano Ultra e 50 créditos, indisponível na conta Pro atual |
| Criar e renomear projetos | Validado por HTTP pelo MCP no Windows, projeto exclusivo de testes; capa preservada |
| Upload de imagem local e referências | Upload HTTP validado no Windows; Nano Banana 2 com referência validado pelo MCP |
| Listar e pesquisar projetos remotos, incluindo IDs legados | Validado: sete projetos retornados pelo Flow; `query` filtra ID/título sem distinção de caixa e `complete` preserva a incerteza da paginação |
| Excluir projeto | Implementado como `flow_delete_project`: confirmação explícita, RPC `QI2zvc` enviado uma vez e reconciliação por `UpteDb`; testes locais passam, validação remota Windows pendente |
| Pesquisar ativos entre projetos | Implementado por leitura de `UpteDb` e `Zzl0ze`; limitado a 100 projetos/500 resultados e informa projetos com falha; `complete=false` porque a paginação de mídia ainda não foi validada |
| Download de projeto em lote e resumo | Implementado (flow_download_project, flow_project_summary) |
| Coleções | Listar inclusive vazias pela resposta `Zzl0ze`; criar subcoleção, renomear (`O2COMe`), mover ativos (`kVdhHf`) e download recursivo validados no Windows. Criação `Uxbujd` reconcilia resposta inconclusiva por leitura; paginação remota pendente |
| Histórico completo | Pendente; ativos podem ser arquivados por workflow com confirmação explícita |
| Cenas: sequência, corte e exportação local | Implementados com ffmpeg; persistência/exportação do Scenebuilder implementadas via gflow-cli, validação Windows pendente |
| Personagens e vozes | Listagem/CRUD de personagem e catálogo fixo de presets implementados; referência/criação de voz ainda pendentes de payload validado; validação Windows pendente |
| Avatar pessoal | Pendente; cadastro biométrico exige interação humana |
| Flow Agent e sessões | Brief por projeto e CRUD básico de sessões implementados localmente; listagem, criação e renomeação validadas no Windows, com leitura de confirmação e `complete=false`. Exclusão, paginação e mensagens pendentes |
| Flow Tools | Pendente |
| Publicação e compartilhamento | Pendente; teste de publicação depende de autorização específica |
| Catálogo e preços por conta/projeto | HTTP `HTrJv`, plano e restrições validados; cotação exata sem selecionar configuração no compositor |

A suíte WSL completa passou com 125 testes em 30/09/2026. Três caminhos
de `reference_asset_ids` passaram no worker HTTP do Windows, todos com orçamento
e custo cotado zero e saldo 856 antes/depois: geração Nano Banana 2 1:1, uma
referência/uma saída (job `7f65da45-99ef-48fc-9a3a-03969c7df605`, mídia
`7ebbe800-d345-45a1-95af-4707bfc7860c`); edição simples (job
`94db1c32-daa3-4d99-be88-6758b027c9fd`, mídia `60cfac69-4fb8-4a0c-9fc5-a3a1d3052b92`);
e lote de duas origens/workflows distintos (job `153cefe6-5c77-4e94-bdac-2f23644a1dde`,
mídias `08aaa719-5ddd-4934-afd1-53338c685659` e
`9a9109c2-b84a-45cb-8d1c-86640f2c6612`). Os arquivos foram baixados e existem.
Lotes maiores e a combinação com seleção/desenho continuam sem validação. O MCP
expõe 55 ferramentas. Gasto acumulado 244/500 créditos; a segunda conta foi
adiada pelo usuário. A cobertura total ainda não foi alcançada.

## Edição anotada de imagens e vídeo com referências — 30/09/2026

`flow_edit_image` aceita referências locais ou IDs de imagens já existentes no
mesmo projeto, seleção poligonal normalizada e traços. IDs são validados contra
as imagens retornadas para o projeto e usados sem novo upload; esse caminho
acabou de ser implementado localmente e ainda requer teste e validação Windows. Para
referências locais, o MCP faz o upload normal. Com seleção/desenho, baixa a
imagem original e renderiza as anotações em uma cópia,
envia essa cópia pelo upload HTTP normal e a usa como base da edição. O
workflow e o histórico originais são preservados. A anotação orienta o modelo;
ela não garante que os pixels fora da região permaneçam idênticos. Validação
Windows: dois uploads, um envio de edição, download e recuperação, custo zero.

`flow_edit_video` aceita referências locais ou IDs de imagens do mesmo projeto,
além do intervalo do trecho, duração e resolução selecionadas no catálogo. O
trecho precisa caber no vídeo de origem e ter até dez segundos. Vídeo enviado
usa 30 FPS na conversão do intervalo para quadros; vídeos gerados usam 24 FPS.
Validação Windows: vídeo enviado, trecho de 1–5 s, uma referência, Omni Flash
8s/720p; envio único, MP4 de 981.898 bytes baixado e recuperado. Custo: 20
créditos, saldo 876 → 856. Referências de voz, modos dedicados de câmera ou
objetos e refinamento contextual continuam pendentes. Nenhuma mutação incerta
é reenviada.

## Cenas persistentes e personagens — 30/09/2026

`flow_manage_scene` cria, consulta e atualiza cenas existentes no Flow. A ordem
dos clipes vem da lista `clips`; cortes usam segundos e só podem referir os
workflow IDs que já pertencem à cena. `flow_export_scene` lê a sequência e
envia uma concatenação remota, salva MP4 validado no diretório de saída e não
reenviará uma exportação incerta. `flow_build_scene` continua sendo a montagem
local via ffmpeg.

`flow_list_characters` retorna IDs estáveis, referências, voz e personalidade,
sem URLs assinadas. `flow_manage_character` cria/edita personagens com uma ou
duas referências de imagem existentes e presets de voz; exclusão exige
`confirm_delete=true` após pedido explícito do usuário. Criação, PATCH e
exclusão usam um único envio e as alterações são verificadas por leitura.

Ambos os recursos reutilizam a página autenticada pelo worker gflow-cli para
evitar uma segunda lease do mesmo perfil. Os fluxos foram testados localmente,
mas ainda não foram validados em conta real no Windows.

## Brief do Flow Agent — 30/09/2026

`flow_get_agent_brief` lê o estado do brief e cartões de instrução do projeto.
`flow_update_agent_brief` altera o estado e/ou substitui cartões; a substituição
da lista exige `confirm_replace_instructions=true`. Atualização incerta faz
somente uma leitura de reconciliação, sem repetir o PATCH. Isso não controla o
toggle da interface nem implementa sessões ou envio de mensagens ao Agent.
Os métodos vêm do gflow-cli 0.79.1 e reutilizam a página autenticada do worker.
Testes locais cobrem leitura, confirmação, eco do PATCH e reconciliação; validação
em conta real no Windows pendente.

## Validação de HTTP direto

1. Consulta de projetos `UpteDb`: validada via HTTP direto (`httpx`) no worker persistente (7 projetos retornados).
2. Consulta de ativos `Zzl0ze`: validada via HTTP direto (`httpx`).
3. Download de imagens: validado via HTTP direto (`httpx`).
4. Download de vídeos (`as29s`): diagnóstico e correção concluídos em `flow_http.py`, com download real validado no Windows em 29/09/2026. O RPC `as29s` foi desacoplado de falsos templates POST e passa a ser capturado diretamente na rota de carregamento do clipe e cacheado por `media_id`. O binário é baixado via `httpx` após fechamento do Chrome, com validação de magic bytes `ftyp`, tamanho esperado e cada host de redirecionamento.
5. Suíte completa: 34 testes passando em WSL (`uv run --locked python -m unittest -v`), incluindo o protocolo MCP, lotes fora de ordem, recuperação parcial, prompt traduzido, envio HTTP único, bloqueio de gasto após falha, correlação por workflow e encerramento dos workers.
6. Execução nativa Windows de `.validate_http_worker.py` concluída com `conta-ponte-a`: sete projetos em duas consultas consecutivas (8,25s e 1,16s), sete ativos (7,27s), JPG de 57.319 bytes (3,00s) e MP4 de 1.133.876 bytes (8,59s). Todas as operações retornaram sucesso; não houve envio de geração nem gasto de créditos. A segunda consulta de projetos reutilizou o worker e a sessão HTTP em memória.

Os seis testes acima cobrem consultas e downloads no Windows. Não comprovam sessão
portátil, geração por HTTP, paginação completa nem funcionamento no Raspberry Pi.

## Retomada: geração de imagens por HTTP

Geração `ogiZ0b` validada nativamente no Windows: uma imagem por texto e um lote
de duas imagens com referência. O navegador confere modelo, proporção, quantidade
e custo, prepara a autenticação e tem seu envio interceptado e abortado. Somente
após fechar o Chrome ocorre um único POST por `httpx`. As chamadas normais do
reCAPTCHA permanecem permitidas durante a preparação; bloqueá-las fazia o envio
retornar erro RPC 7. Não houve reenvio automático dos testes inconclusivos.

A recuperação de imagens via `lh3.googleusercontent.com` foi corrigida: o URL
sem transformação entregava uma miniatura de 512×512, embora o registro informasse
1024×1024. A transformação `=s0`, aplicada somente nesse host, retornou o original
de 1024×1024, confirmado por `ffprobe`. Geração, edição e recuperação compartilham
essa correção. Os downloads continuam validando cada redirecionamento e o formato.

Após gerar e recuperar o lote HTTP, `flow_get_credits` confirmou **983 créditos**
em 30/09/2026 às 01:32:42 UTC; o gasto da etapa permanece **57/500**.
Detalhes de ativos e versões também passam pelo worker HTTP persistente.
Edição textual de imagem validada via HTTP pelo MCP: uma nova versão foi criada,
o original permaneceu na pilha, e a recuperação retornou JPG 1024×1024.

## Retomada: geração e acompanhamento de vídeos por HTTP

Um único `YhhmEf` gerou dois Veo Lite; `as29s` acompanhou cada workflow por HTTP
depois de fechar o navegador. Essa consulta recebe o **ID do workflow**,
distinto do ID de mídia. Cada resposta precisa corresponder à mídia, ao workflow
e ao projeto esperados antes do download. O orçamento é conferido no compositor,
e a quantidade do corpo capturado precisa corresponder à quantidade autorizada.

O teste pelo protocolo MCP completou e recuperou dois MP4s H.264/AAC,
1280×720, 8 segundos: 6.456.136 e 8.430.192 bytes. Saldo 983 → **963**,
custo total **20**, gasto acumulado **77/500**. Recuperar downloads reutiliza
a consulta HTTP da listagem para preparar o status, sem novo envio de geração.

O navegador continua necessário para autenticação, configuração e custo;
criar/renomear projetos, upload e capacidades ainda usam a interface.
Outros modos de vídeo por HTTP e os demais recursos do inventário continuam em
validação ou pendentes. Isso não comprova migração integral nem portabilidade.

Veo Lite com quadro inicial e Omni Flash 4s também passaram pelo MCP usando HTTP,
inclusive recuperação individual sem reenvio. `ffprobe` confirmou H.264/AAC,
1280×720, 8s e 4s respectivamente. Esses testes consumiram mais 17 créditos;
saldo final **946**, gasto acumulado **94/500**. Capturas bloqueadas de uma e duas
saídas confirmaram que a quantidade de vídeo é o tamanho de `params[0]`; o valor
`2` no campo final é constante do protocolo, não a quantidade solicitada.

## Retomada: projetos, uploads e saldo por HTTP

`jHPbke` cria o projeto com título; `o8DA4` renomeia usando a capa atual lida
por `ngNC2`. Os três RPCs reutilizam a autenticação em memória capturada na
preparação da sessão, sem cliques para cada alteração. Criar/renomear pelo MCP
no Windows retornou sucesso, confirmado na listagem remota de oito projetos.
A criação automática de projetos em geração também usa esse caminho. Resposta
incerta interrompe a geração e preserva a informação no estado local.

Uploads `maseQ` agora têm o envio do navegador abortado, conferem projeto, nome,
MIME e os bytes exatos do arquivo, fecham Chrome e fazem um único POST HTTP.
A primeira resposta foi inicialmente classificada como incerta porque o
registro vem aninhado; a listagem confirmou o upload aceito, sem reenvio.
O reconhecimento foi corrigido e um novo teste confirmou ID/nome na listagem.
Referências e quadros usam esse upload antes de abrir o compositor para vincular
os IDs. Nano Banana 2 com referência passou pelo MCP, gerou e baixou uma imagem
1:1 com teto zero. Veo Lite com quadro inicial passou pelo novo fluxo HTTP de
upload, envio `eb1hJf`, acompanhamento e download, com teto/custo 10. `ffprobe`
confirmou MP4 H.264/AAC, 1280×720 e 8s. Quadro final e ingredientes de vídeo
permanecem sem validação real.

O saldo passa pelo RPC `nzlxg`, sem a API antiga de labs nem leitura do texto
da interface. Chrome prepara a sessão quando necessário; consultas posteriores
reutilizam o worker. Duas chamadas reais pelo MCP retornaram **946**, a última
em 30/09/2026 às **02:20:39 UTC**. Campos privados permanecem omitidos; zero é
distinto de resposta indisponível. Projetos, uploads, saldo e imagem com referência
tiveram custo zero. O novo teste de vídeo com quadro inicial consumiu 10 créditos:
saldo **936** confirmado por HTTP em **02:29:16 UTC**, gasto acumulado **104/500**.

Suíte completa: **42 testes passaram** (`uv run --locked python -m unittest -v`).
Capacidades, configuração/custo de geração e preparação de autenticação/recaptcha
ainda dependem do navegador. A migração integral e portabilidade seguem pendentes.
O catálogo `HTrJv` foi implementado em `flow_capabilities.py`, com preços por
plano, restrições e configuração exata. A retomada seguinte valida os corpos
nativos e preserva o navegador somente para preparar autenticação.


## Retomada: corpos nativos e autenticação normal do Flow

`flow_requests.py` monta upload, imagem, edição e os quatro modos implementados de
vídeo. Configuração e custo são cotados em `HTrJv` por plano, sem configurar
modelo, proporção ou quantidade no compositor. Referências entram tanto nos
campos de entrada quanto no prompt estruturado, com IDs e nomes dos uploads.
Os IDs previstos são derivados das sementes UUID e gravados antes do POST.
Respostas de outro pedido/projeto/workflow e duplicatas não são aceitas.

Imagens e uploads usam sementes workflow/mídia; a edição reutiliza o workflow
no campo 5 do contexto, sem preencher o campo de coleção nem criar outro
workflow. Vídeo tem a mesma ordem de sementes nos campos 5/6 dos metadados.
A troca incorreta dessas sementes no primeiro lote de vídeo desta retomada foi
reconciliada pela listagem remota; os dois MP4s originais foram recuperados pelo
MCP, com 7.466.704 bytes no total, sem novo envio. O gasto foi de 20 créditos.

O frontend marca chamadas diretas a `grecaptcha.enterprise.execute` com outra
ação. As sondagens nativas de imagem/edição usando esse caminho retornaram RPC 7,
sem IDs encontrados na listagem para a imagem por referência. Esses pedidos não
foram repetidos. A preparação de imagem/vídeo agora usa o fluxo normal do Flow:
seleciona apenas o modo, fornece um prompt de preparação e aborta o envio do
navegador. Somente a autenticação e o envelope HTTP são reaproveitados; corpo,
modelo, custo, prompt, entradas e quantidade do pedido real vêm do Python e do
catálogo. Chrome fecha antes do único POST real. Upload nativo também foi validado.
Isso ainda exige navegador e não comprova portabilidade.

Validação real via MCP no Windows nesta retomada:

| Operação | Custo | Evidência |
|---|---:|---|
| Upload nativo | 0 | Primeiro upload aceito e reconciliado; próximo upload de referência confirmado com a ordem corrigida |
| Duas Nano Banana 2 com referência, 1:1 | 0 | Dois JPGs 1024×1024 gerados e recuperados |
| Edição textual nativa da primeira imagem | 0 | JPG 1024×1024 de 538.365 bytes; duas versões no histórico e recuperação confirmada |
| Dois Veo Lite por texto, 8s/720p/16:9 | 20 | Lote aceito em um único envio e recuperado após reconciliação dos IDs |
| Veo Lite com quadro inicial, 8s/720p/16:9 | 10 | Envio, acompanhamento, download e recuperação concluídos no novo caminho |
| Omni Flash inicial/final, 4s/720p/16:9 | 7 | Dois uploads, envio nativo `nprQif`, acompanhamento e recuperação confirmados |
| Omni Flash com referência, 4s/720p/16:9 | 7 | Upload, prompt estruturado, envio nativo `MZZa6b`, acompanhamento e recuperação confirmados |

Os quatro modos foram confirmados. `ffprobe` verificou H.264/AAC e 1280×720:
8s para Veo Lite e 4s para Omni Flash. Listagem e download antigos também foram
encaminhados ao cliente HTTP, inclusive para chamadas diretas desses helpers.
As sondagens inconclusivas de custo zero continuam no diário; não são evidência
de geração concluída. Gasto confirmado nesta retomada: **44 créditos**; total
**148/500**, saldo **892**. Nenhuma geração foi reenviada.

Suíte atual: **51 testes passaram no WSL e no Windows**, incluindo preço por
plano, preço zero/ausente, teto, configuração exata, corpos e sementes, origem e
histórico da edição, autenticação normal com envio abortado, encerramento do
navegador, lote fora de ordem e ausência de reenvio automático. Uma comparação
com caminho literal POSIX no teste antigo foi normalizada para rodar no Windows.

## Retomada: reutilização da sessão autenticada

Conferido no Windows: `conta-ponte-a` usa `profiles/profile_conta-ponte-a`, com
sessão salva, o mesmo perfil dedicado do login assistido. O Chrome habitual é
outro perfil. O login persistente evita nova autenticação humana; o preparo do
contexto HTTP e do reCAPTCHA por operação ainda abre Chrome na implementação.

A consulta `nzlxg` tem parâmetros vazios, confirmados na captura real. Quando
`UpteDb` já preparou a sessão, o saldo agora reutiliza seu envelope HTTP em memória
sem abrir o menu da conta. A mudança é compartilhada pelo saldo e pelo catálogo.
Teste real: listar projetos, ler catálogo e consultar saldo completaram com
uma única abertura do Chrome, sem geração; o saldo retornou 942. Essa observação
não explica a diferença em relação ao último saldo pago registrado de 892.
Gasto da etapa permanece 148/500; nenhuma nova geração foi enviada.

Suíte: **52 testes passaram no WSL e no Windows**, incluindo regressão que
impede abrir Chrome novamente para consultar saldo usando a sessão de projetos.
Geração/edição continuam preparando o reCAPTCHA normal por operação; não foi
validada execução sem navegador nem portabilidade de sessão.

## Retomada: navegador headless residente

O worker da conta agora mantém um contexto Chrome autenticado em headless,
aberto sob demanda e reutilizado em consultas, uploads, geração/edição e
recuperação. Cada preparo abre uma página nova, permite o reCAPTCHA normal do
Flow e bloqueia seu envio. A página fecha antes do POST HTTP real, descartando
suas rotas e eventuais retries; o contexto continua ativo. Não há alteração dos
scripts de reCAPTCHA nem chamadas diretas adicionais de geração.

As operações da conta passam pelo mesmo worker serializado. Referências usam o
mesmo cliente HTTP/contexto, sem tentar adquirir outra lease do perfil. Login,
importação e verificação liberam o contexto e descartam o cliente HTTP antes de
acessar o perfil. Login humano permanece visível. O encerramento do worker fecha
HTTP, Chrome e lease. `FLOW_MCP_HEADLESS=false` permite diagnóstico visível após
reiniciar o servidor; não há fallback automático nem reenvio de pedidos incertos.

Validação Windows: uma Nano Banana 2 1:1 e um Veo Lite 8s/720p/16:9 foram gerados,
baixados e recuperados usando o mesmo contexto headless. Antes de cada POST foi
conferido que nenhuma página de preparo permanecia aberta. Houve exatamente um
POST de geração por pedido, dois no total, e nenhum na recuperação. `ffprobe`
confirmou JPG 1024×1024 e MP4 H.264/AAC 1280×720 com 8s.
Tarefas: `eaacda51-c178-437a-bf6f-6fa193f582f8` e
`68ffc689-0de3-4862-9d88-d87ca3033d95`. O contexto fechou ao encerrar a validação.
O protocolo MCP stdio também confirmou recuperação das duas tarefas pelo worker
headless e consultas de saldo antes/depois, ambas em 932, sem novos envios.

Custo observado: imagem zero, vídeo 10. Saldo 942 → **932**, gasto total
**158/500**, restantes **342** do teto. A diferença anterior de 50 créditos
entre os saldos 892 e 942 continua sem explicação; não foi usada para reduzir
o gasto registrado. Suíte: **55 testes passaram no WSL e no Windows**, cobrindo
reutilização, headless, páginas fechadas, release da lease após falha de abertura
e encerramento, despacho de operações para o cliente da conta e envio único.
Isso valida o ciclo testado no Windows, sem estabelecer estabilidade contínua,
renovação automática de login ou portabilidade Linux/ARM64/Raspberry Pi.

## Retomada: quadros, exportação GIF, Scenebuilder e robustez de ativos

Em 30/09/2026, foram implementadas as funcionalidades multimídia faltantes e corrigido o parse de URLs de imagens recortadas:

1. **Robustez de download de imagens (`flow_assets.py`)**: `image_download_url` agora faz fallback recursivo seguro varrendo a linha de mídia por URLs Google Photos/CDN (`https://lh3.googleusercontent.com/`), resolvendo falhas de índice fixo em imagens transformadas (`sAVZzc`).
2. **Captura de quadro (`flow_save_frame`)**: extrai quadros de vídeos MP4 locais ou remotos em alta qualidade via `ffmpeg` no segundo especificado (`timestamp_seconds`). Suporta `upload_to_flow=True` para registrar o quadro instantaneamente como asset utilizável em novos pedidos sem reenvio.
3. **Exportação GIF (`flow_export_gif`)**: converte vídeos ou trechos em GIFs animados utilizando pipeline com paleta de duas passagens (`palettegen`/`paletteuse`), garantindo tamanho leve e fidelidade de cores.
4. **Scenebuilder (`flow_build_scene`)**: monta sequências de múltiplos clipes com suporte a pontos de corte (`trim_start`/`trim_end`), normalizando resolução e framerate para concatenação fluida em um único MP4.
5. **Cancelamento de tarefas (`flow_cancel_job`)**: marca tarefas pendentes locais como `cancelled`, prevenindo recuperações acidentais.
6. **Filtro de mídia (`flow_list_assets`)**: suporte a `kind="image"` ou `kind="video"` para filtragem rápida de projetos populosos.

Suíte: **65 testes passaram no WSL** (`uv run --locked python -m unittest -v`), cobrindo validações de entrada, despacho pelo worker, concatenação ffmpeg, geração de GIF e protocolo MCP com 28 ferramentas.
 
## Retomada: Upscale, gerenciamento e download de projetos, e filtros avançados

Em 30/09/2026, implementado o novo lote de ferramentas MCP e recursos complementares:

1. **Upscale de mídia (`flow_upscale`)**: aumenta a resolução de vídeos e imagens para 720p, 1080p ou 4K utilizando filtro Lanczos combinado com realce de nitidez (`unsharp`). Suporta imagens e vídeos, preservando proporções (inclusive verticais 9:16) e `upload_to_flow=True` envia os resultados ao Flow; vídeo pode exigir confirmação explícita de direitos.
2. **Download em lote de projeto (`flow_download_project`)**: transfere todos os ativos de um projeto para um diretório local com suporte a filtros por tipo (`kind="image"` ou `"video"`) e texto de pesquisa (`query`). Tolerante a falhas parciais (continua baixando demais ativos se algum falhar).
3. **Resumo estruturado de projeto (`flow_project_summary`)**: consolida metadados, contagem de ativos, tipos (imagens vs vídeos), total de bytes e títulos, sem consumir créditos.
4. **Filtros e ordenação avançados em ativos (`flow_list_assets`)**: suporte a `min_bytes`, `max_bytes`, `sort_by` ("name", "bytes", "revision"), `sort_order` ("asc", "desc") e `limit`.
5. **Alias inicial de upload de mídia (`flow_upload_asset`)**: disponibilizou `flow_upload_asset` para imagens; posteriormente ampliado para vídeo pela interface do Flow.
6. **Limpeza de tarefas locais (`flow_clean_jobs`)**: permite purgar registros de tarefas finalizadas ou canceladas (`status_filter`), liberando espaço em disco sem afetar tarefas em andamento.

Suíte: **74 testes passaram no WSL** (`uv run --locked python -m unittest -v`), com **33 ferramentas MCP** expostas.

## Retomada: resolução de geração de vídeo e conciliação do orçamento

A implementação inicial de `flow_generate_video` aceitava `resolution="360p"`
ou `"720p"`. A opção 360p
segue o catálogo e o preço observados na conta; se a variante não existir ou
custar acima de `max_credits`, o envio é bloqueado. O padrão continua 720p.
Testes locais verificam seleção da variante, custo e propagação da resolução
até a tarefa. A suíte completa passou com **76 testes no WSL** após o novo fluxo de upload.

Atualização de 01/10/2026: a ferramenta também aceita `1080p` e `4k`, mas só
envia se o catálogo HTTP da conta oferecer a combinação exata e o custo ficar
dentro de `max_credits`. A seleção usa a chave da variante retornada pelo
catálogo. Essas duas resoluções para geração ainda não foram validadas em geração
real; o upscale nativo 1080p foi validado separadamente abaixo.

Validação real no Windows: catálogo retornou a variante
`abra_t2v_8s_360p` com custo 6; um único envio gerou e baixou MP4 H.264
640×360 de 670.865 bytes. A tarefa `eceb6055-ca33-40be-87c0-bb8127468e08`
foi recuperada após reiniciar o cliente, sem novo envio. Saldo 902 → 896.

O registro de 158/500 acima é um marco anterior: a validação de edição/extensão
de vídeo elevou o gasto confirmado a **198/500**, saldo **902**, restantes
**302** do teto antes do teste 360p. Após esse teste e a edição de vídeo
enviado, total atual: **224/500**, saldo **876**, restantes **276**.

`flow_upload_asset` usa `maseQ` para imagem e o seletor de arquivo normal do
Flow para vídeo MP4/MOV/AVI/WMV de até 1 GB. A ferramenta escolhe o arquivo uma
vez e só confirma sucesso quando surge exatamente um vídeo novo com o nome
esperado na listagem do projeto. Resultado ambíguo não é reenviado. No primeiro
teste Windows, o Flow abriu o aviso “Direitos de uso deste vídeo”. O usuário
aceitou-o pessoalmente; o vídeo foi confirmado na listagem. A edição textual
desse vídeo enviado custou 20 créditos e foi concluída e recuperada sem reenvio.
O diálogo agora produz `confirmation_required` e um `confirmation_id`; após
autorização explícita do usuário, `flow_confirm_upload` aceita ou recusa o
mesmo diálogo pendente. Essa confirmação em duas etapas passou nos testes
locais, ainda sem novo aviso real. Um segundo upload retornou
`submission_unknown` porque o Flow exibiu o nome sem `.mp4`; a listagem remota
confirmou o ativo e o comparador de nome foi corrigido, sem repetir o envio.
Para vídeo enviado, a edição assume 24 FPS; outras taxas ainda precisam de teste.
Suíte ampliada: **102 testes passaram no WSL**. O MCP expõe **48 ferramentas**. `flow_delete_project` tem confirmação explícita, envio único e reconciliação de leitura; a implementação tem cobertura local, ainda sem validação remota no Windows e sem gasto de créditos. Criar/renomear coleções usa `Uxbujd`/`O2COMe`, com ID/título confirmados; mover ativos usa lote `kVdhHf`; a ferramenta ainda não faz readback da associação. Os payloads ainda não foram validados no Windows. Busca de projetos/ativos tem cobertura local e ainda requer validação remota no Windows; a busca de ativos limita o escopo à resposta inicial de cada projeto. Cenas têm testes locais de criação com resultado incerto, atualização de ordem/cortes, exportação e descoberta MCP. Personagens têm testes locais de criação, envio único e confirmação antes da exclusão. O brief do Agent tem testes de leitura, substituição confirmada e reconciliação sem reenvio. Cenas, personagens, arquivo de ativos e brief do Agent ainda precisam de validação remota no Windows. Nenhum crédito foi gasto nesta implementação.

## Retomada: associação e download direto de coleções

`flow_list_assets` agora retorna `collection_id` por workflow e pode filtrar por
associação direta; `flow_download_collection` baixa esses ativos em uma pasta
local. Download recursivo de subcoleções não está incluído. A ferramenta de
listagem de coleções vazias/metadados segue pendente porque a resposta da RPC
observada no frontend não revelou um esquema confiável. Verificação local:
**103 testes passaram no WSL**, com **49 ferramentas MCP**. Sem validação no
Windows nesta retomada e sem gasto de créditos.

## Retomada: confirmação de movimentação de ativos

`flow_move_assets` agora relê `Zzl0ze` depois do único envio `kVdhHf`,
inclusive quando a resposta do envio é incerta. Confirma cada ativo somente
quando a resposta contém seu workflow e a associação direta esperada. Retorna
`unconfirmed_asset_ids` para qualquer resultado não comprovado; não reenvia a
mutação. A suíte WSL passou com **126 testes**. Ainda sem validação Windows;
nenhum crédito foi gasto nesta alteração.

Uma sondagem Windows encontrou a sessão autenticada e leu três projetos de teste.
A criação de uma coleção em um deles retornou `submission_unknown`; a leitura
seguinte do projeto não mostrou o título solicitado. A criação não foi repetida
e nenhum ativo foi movido. O esquema e a validação real desse fluxo seguem
pendentes; a sondagem não gastou créditos.

## Retomada: coleções observadas no Windows

A coleção criada acima apareceu na interface com o título inicial
`Untitled collection`; a busca anterior pelo título solicitado não a encontrou
porque a renomeação ainda não havia sido enviada. `Zzl0ze` contém as coleções
em sua primeira seção, inclusive vazias. `flow_list_collections` agora expõe
ID, título e coleção pai, com `complete=false` para paginação não verificada.

Uma captura do frontend, com envio bloqueado, mostrou que a máscara de campos
de `O2COMe` exige um nível adicional de lista. Após a correção, a coleção
existente foi renomeada no Windows e o título confirmado por nova leitura.
Um ativo do projeto de teste foi movido para a coleção e de volta à raiz;
as duas associações foram confirmadas por `Zzl0ze`. A criação de uma nova
coleção após a correção ainda não foi executada; seu resultado inconclusivo
anterior agora seria reconciliado por ID antes da renomeação. Nenhum crédito
foi gasto nesta validação. A suíte WSL passou com **127 testes** e o MCP expõe
**57 ferramentas**.

## Retomada: subcoleções e download recursivo

`flow_download_collection(recursive=true)` percorre os vínculos pai/filho da
primeira resposta `Zzl0ze`, filtra os ativos dessas coleções e baixa os arquivos
na pasta indicada. O resultado retorna `collection_ids` e `complete=false`, pois
a paginação remota não foi comprovada. No Windows, uma subcoleção foi criada e
confirmada sob a coleção de teste; um ativo foi movido para ela, baixado pelo
download recursivo da coleção pai e movido de volta à raiz. O arquivo baixado
existia e ambas as associações foram confirmadas por leitura. Sem gasto de
créditos. A suíte WSL completa passou com **128 testes**.

## Retomada: preferências da conta

`flow_get_user_settings` lê as preferências da conta; `flow_update_user_settings`
atualiza campos selecionados por `DA4VGb` e confirma o resultado com `Yizz8d`.
Se a resposta da mutação for incerta, faz somente a leitura de reconciliação e
nunca reenvia. Ativar `return_silent_videos` exige `confirm_credit_impact=true`,
pois o Flow pode cobrar créditos por vídeos retornados sem áudio. Testes locais
cobrem parse, atualização parcial, confirmação e envio incerto. A leitura foi
validada no Windows pelo worker HTTP e retornou seis campos; os valores não foram
registrados. A atualização ainda não foi validada no Windows. A suíte WSL mais
recente passou com **125 testes**; a leitura não gastou créditos.

## Retomada: sessões do Flow Agent

`flow_list_agent_sessions` usa `mrlkwd` para retornar IDs e títulos da primeira
resposta do projeto. `flow_create_agent_session` envia `csbIsb` com o projeto e
o seed UUID/ID derivados pelo helper já compatível com o frontend; a resposta
confirma o ID ou a listagem inicial reconcilia resultado incerto. `flow_rename_agent_session`
usa `TunYMc`; `flow_delete_agent_session` usa `Dcn2Le`, exige
`confirm_delete=true` e avisa que o histórico é apagado permanentemente. Rename
e delete só atuam em sessões presentes na resposta inicial; as mutações são
enviadas uma vez e reconciliadas por leitura. A listagem foi validada no Windows
em projeto sem sessões: `mrlkwd` retornou `[]`, agora tratado como lista válida;
`complete=false` mantém explícita a paginação não verificada. Criação,
renomeação e exclusão ainda não foram validadas no Windows. A suíte WSL passou
com **125 testes**, e o MCP expõe **55 ferramentas**. Não houve gasto de créditos.

## Retomada: criação e renomeação de sessão do Agent — 01/10/2026

Uma sessão de teste foi criada por `csbIsb` e renomeada por `TunYMc` no
Windows, no mesmo contexto HTTP residente. A leitura posterior `mrlkwd`
confirmou a presença da sessão; a renomeação retornou `updated` após conferir
o título. Cada mutação foi enviada uma vez, sem geração de mídia e sem gasto
de créditos. A sessão de teste foi preservada; exclusão, paginação e mensagens
continuam pendentes. A suíte completa WSL passou novamente com 128 testes.

A suíte Windows também passou com 128 testes. A primeira execução teve seis
erros por ausência de ffmpeg no PATH; repetir com o diretório da instalação
WinGet já existente no PATH do processo resolveu os seis erros. Nenhuma
dependência foi instalada e o PATH permanente não foi alterado.

## Refinamento de vídeo em até três turnos — 01/10/2026

`flow_refine_video` encadeia de um a três prompts como edições Omni Flash. Cada
turno usa a mídia anterior e o workflow retornado pelo Flow, aplica a cota que
resta de `max_credits` e interrompe a cadeia se um resultado ficar incerto ou
incompleto. Referências locais são enviadas no primeiro turno e reutilizadas
por ID nos seguintes. Testes WSL: 134 passaram; MCP: 57 ferramentas. A
equivalência com o refinamento conversacional da interface ainda não foi
validada no Windows. Nenhum crédito foi gasto; total permanece 244/500.

## Upscale nativo de imagem — 01/10/2026

`flow_upscale_image(account_id, project_id, media_id, target_resolution,
upload_to_flow=False)` usa `HTTP/upsampleImage` para gerar 2K ou 4K a partir de
uma imagem do projeto e salva a resposta localmente. Com `upload_to_flow=True`,
envia a saída pelo upload de imagem existente e retorna o estado e o ID do novo
asset; falha de upload preserva o arquivo local concluído. O gflow-cli fixado
documenta 2K sem créditos e 4K restrito ao plano Ultra. O MCP envia uma única
mutação de upscale e não repete resultado incerto. A tentativa remota pelo MCP
parou antes do POST por falta do bearer Aisandbox na conta migrada; o detalhe
está na subseção seguinte. A suíte WSL passou com 142 testes e o MCP registra
58 ferramentas.
`flow_upscale` segue sendo o filtro local FFmpeg, e o upscale nativo de vídeo
continua pendente. Nenhum crédito foi gasto; total permanece 244/500.

## Autenticação do upscale nativo de imagem — 01/10/2026

O teste remoto pelo worker Windows não chegou ao POST. A tentativa inicial
falhou ao preparar autenticação no host migrado; após trocar para o preparo
normal do Flow, a construção dos headers Aisandbox falhou porque a sessão
migrada não fornece o bearer esperado pelo endpoint `upsampleImage`. Ambas as
falhas ocorreram antes do envio e não devem ser repetidas pelo mesmo caminho.
O saldo foi 906 antes e depois; nenhum crédito foi gasto. A passagem anterior
de 856 para 906 continua sem explicação e não altera o gasto registrado.

A interface do clipe de teste carregou, mas não expôs um controle de upscale
na tela inspecionada; chamadas novas foram bloqueadas e nenhum upscale foi
acionado. Ainda não há corpo HTTP confirmado para upscale nativo de vídeo nem
para os controles dedicados de câmera e inserção/remoção de objetos. A edição
por prompt continua disponível, mas não substitui esses controles. A suíte WSL
passou com **140 testes**; o MCP mantém **58 ferramentas**.

Uma inspeção estática da dependência fixada gflow-cli 0.79.1 encontrou suporte
nativo de upscale somente para imagem e nenhum método/rota para upscale de vídeo
ou para os controles de câmera/objetos. A documentação da própria dependência
classifica os transports experimentais evaluate_fetch, bearer e sapisidhash
como incompatíveis com mutações/geração diante do anti-bot; não há fallback de
autenticação validado para reutilizar.

## Envio ao Flow de vídeo com upscale local — 01/10/2026

`flow_upscale(upload_to_flow=true)` agora passa arquivos MP4 resultantes pelo
`flow_upload_asset` já existente. Se o Flow mostrar a confirmação de direitos,
a tarefa retorna `confirmation_required` e o usuário precisa chamar
`flow_confirm_upload`; o upscale local continua concluído e seu arquivo fica
disponível mesmo antes dessa confirmação. O caminho reutiliza o upload normal,
sem novo endpoint e sem gasto de créditos. Teste local cobre o estado pendente;
validação Windows desta combinação ainda pendente. Suíte WSL: **141 testes**;
MCP: **58 ferramentas**.

## Upload opcional da imagem com upscale nativo — 01/10/2026

`flow_upscale_image(upload_to_flow=true)` envia a saída 2K/4K pelo upload de
imagem existente e retorna o estado e o ID do novo asset. Se esse upload falhar,
o upscale concluído e seu arquivo local continuam disponíveis. Testes WSL cobrem
sucesso e falha do upload; o endpoint nativo de upscale segue bloqueado antes
do POST nesta conta, então o encadeamento não tem validação Windows. Suíte WSL:
**142 testes**; MCP: **58 ferramentas**. Sem gasto; acumulado 244/500.

## Referências de projeto na geração de vídeo — 01/10/2026

`flow_generate_video` expõe `reference_asset_ids` para reutilizar imagens e
vídeos já listados no mesmo projeto/conta. A validação local confere tipo e
pertencimento do asset; o builder HTTP associa os UUIDs no campo nativo de
referências. Testes cobrem asset de vídeo, esquema MCP e parada sem reenvio
após submissão incerta. Esta nova entrada por ID ainda não foi validada no
Windows; os ingredientes por imagem local já tinham validação remota. Suíte
WSL: **143 testes**; MCP: **58 ferramentas**. Sem gasto; acumulado 244/500.

## Quadros de vídeo por ID de asset — 01/10/2026

`flow_generate_video` aceita `start_image_asset_id` e, opcionalmente,
`end_image_asset_id` para usar imagens do projeto como primeiro e último quadro.
O MCP relê os assets do projeto, exige tipo imagem e coloca seus IDs nos campos
nativos do pedido sem upload adicional; caminhos locais continuam aceitos. Testes
confirmam primeiro+último quadro, rejeição de asset de vídeo e envio único após
resultado incerto. A validação remota está pendente: a verificação WSL retornou
`verification_error`, o perfil Windows `no_session` e a consulta de créditos
ficou indisponível. Suíte WSL: **144 testes**; MCP: **58 ferramentas**. Sem
gasto; acumulado 244/500. Os três testes direcionados também passaram no
Python do Windows; validação real da conta permanece pendente.

## Inspeção da interface de criação — 01/10/2026

Em uma sessão visível do Chrome, o Flow exibiu Omni 1.1 Flash, Veo 3.1 Lite,
Fast e Quality. Com Omni selecionado, os controles eram 360p/720p, 4/6/8/10 s,
16:9/9:16 e 1–4 saídas. O seletor de referências listava imagens, vídeos,
vozes, personagens, avatares e envios. Isso confirma opções da interface da
conta, não a integração dessas entradas no MCP. Nenhuma geração foi enviada e
nenhum crédito foi gasto. A sessão do Chrome não foi transferida para o worker;
vozes/personagens, upscale nativo de vídeo e controles dedicados de câmera e
objetos continuam sem payload HTTP validado. A suíte local segue em 144 testes.

## Vídeo local como referência de geração e edição — 01/10/2026

`flow_generate_video` e `flow_edit_video` aceitam `reference_video_paths` para
enviar arquivos MP4, MOV, AVI ou WMV de até 1 GB pelo upload existente e
vinculá-los como ingredients no pedido HTTP nativo. Se aparecer confirmação de
direitos, a chamada retorna
`reference_confirmation_required` e o `confirmation_id` necessário a
`flow_confirm_upload`; não envia a criação/edição. O identificador de confirmação
é retornado ao chamador, mas não é gravado no arquivo local da tarefa. Upload
inconclusivo também interrompe o fluxo, sem reenvio automático. Testes locais
cobrem a confirmação pendente e o vínculo do asset no pedido; a nova combinação
ainda não foi validada de ponta a ponta no Windows. Nenhum crédito foi gasto;
acumulado registrado permanece 244/500. A suíte local passou com 147 testes;
MCP continua com 58 ferramentas.

## Upscale nativo de vídeo Omni 360p→720p — 01/10/2026

No editor autenticado, o download de um clipe Omni 360p ofereceu “720p
Aprimorada”. A requisição `p0UkFb` foi capturada com o envio do navegador
bloqueado; os IDs de mídia, workflow e projeto foram conferidos antes de um
único POST HTTP. O Flow aceitou o pedido. A resposta `Zzl0ze` trouxe o novo ID
com sufixo `_720p_upsampled`; a validação compartilhada e o decoder de vídeo
agora aceitam exatamente esse formato. O arquivo recuperado tem 2.108.109
bytes e o ffprobe confirmou H.264, 1280×720. Saldo antes/depois: 906; custo
observado zero, também descrito na [ajuda oficial do Flow](https://support.google.com/flow/answer/16352836?hl=en).

Na primeira implementação, `flow_upscale_video` expunha somente essa
combinação. A seção de 1080p abaixo registra a extensão posterior e sua
validação no Windows. Hoje 720p e 1080p estão implementados; 4K e controles de
câmera/objetos permanecem pendentes. Gasto registrado naquele ponto: 244/500;
restavam 256. MCP: 59 ferramentas.

## Primeira tentativa da captura de upscale — 01/10/2026

A sessão Windows permaneceu autenticada, com saldo inicial 906. O único clipe
Omni 360p registrado nas tarefas locais já tem a saída aprimorada na listagem
remota; não houve novo envio nem geração de outra origem nesta retomada.

O menu de download de um Veo Lite 720p apresentou GIF 270p, original 720p,
1080p Aprimorada e 4K Aprimorada. A opção 1080p produziu um pedido `p0UkFb`
capturado com a mutação bloqueada antes da rede. O payload observado usa o
valor 2 nos índices `[0][0][2]` e `[0][0][6]`; sessão e token ficaram apenas em
memória. Naquele ponto, isso comprovava o pedido do frontend, não geração,
custo ou download 1080p. A captura da opção 4K terminou em timeout sem POST
HTTP; esse destino segue pendente. A implementação e validação posteriores de
1080p estão registradas abaixo.

O teste de inventário MCP foi atualizado para incluir `flow_upscale_video`.
Um novo teste verifica que uma submissão incerta não é reenviada e que a saída
posteriormente listada é baixada, concluindo a tarefa. A suíte WSL completa
passou com 148 testes; os dois testes direcionados passaram no Windows.
Saldo 906 antes/depois. Nenhum crédito foi gasto; acumulado 244/500.

## Upscale nativo de vídeo em 1080p — implementação e validação Windows

`flow_upscale_video(target_resolution="1080p")` seleciona o controle nativo
capturado no editor, valida os IDs de mídia/workflow/projeto e os dois campos
de resolução observados antes de enviar uma única requisição HTTP. O Flow
retorna a mídia com sufixo `_upsampled`; o parser aceita esse ID e a recuperação
não reenvia a mutação. Validação Windows: origem Veo Lite 1280×720, vídeo
aprimorado recuperado como MP4 H.264 1920×1080, 6.003.074 bytes, saldo 906
antes/depois e custo zero. A suíte WSL completa passou com 149 testes. 4K
permanece pendente até capturar e confirmar seu pedido.

## Geração Lite/Pro de imagem e Omni Flash 10 s — validação Windows — 02/10/2026

O catálogo HTTP da conta identifica Nano Banana 2 Lite como `harbor_seal` e
mostra o rótulo com um emoji de banana. A cotação usava o texto do rótulo sem
emoji e bloqueava esse modelo. `quote_configuration` agora seleciona Lite pelo
`model_id`; um teste cobre o rótulo real.

`flow_generate_images` concluiu uma saída Nano Banana 2 Lite 1:1 em JPEG de
739.567 bytes, e três saídas Nano Banana Pro 1:1 em JPEG. A cotação de ambos
foi zero e o saldo permaneceu em 906. `flow_generate_video` concluiu Omni
Flash 10 s, 720p, 16:9 em MP4 H.264 1280×720 de 4.870.295 bytes. A cotação foi
15 créditos e o saldo passou de 906 para 891. Em seguida, um vídeo Omni Flash
4 s/720p/16:9 usou uma imagem do projeto por `reference_asset_ids`; o MP4 H.264
1280×720 baixado tem 1.347.410 bytes. Custo 7, saldo 891→884. Gasto
acumulado: 266/500; restam 234. A suíte WSL passou com 149 testes.

Uma geração Omni Flash 4 s/720p com um vídeo do projeto em
`reference_asset_ids` foi cotada em 7, mas terminou como `submission_unknown`.
O saldo lido logo depois mudou de 884 para 877; leituras posteriores voltaram
a 884. A saída não apareceu na listagem do projeto nem na consulta `as29s`.
Não houve reenvio. Para reconciliar sem duplicar cobranças, `flow_recover_job`
agora compara a listagem com os IDs e workflows persistidos antes do POST e
consulta `as29s` para cada vídeo esperado; se encontrar vídeo concluído, valida
e baixa o MP4 original. O teste cobre ausência inicial na listagem e recuperação
posterior por workflow, sem segundo POST. Neste caso real, o estado continua
`not_listed`. Suíte WSL: 150 testes. Teto contabilizado conservadoramente:
273/500, restam 227; os 7 adicionais são reserva diante da cobrança incerta,
não gasto confirmado. Naquele ponto, a suíte completa tinha 150 testes; a
ampliação seguinte elevou-a para 152.

A mesma falha de reconciliação existia para geração de imagem: a tarefa tinha
IDs esperados, mas `flow_recover_job` não os comparava com a listagem. Agora
aceita somente correspondência exata de mídia, workflow e projeto antes de
baixar a imagem; não reenvia o POST. Um teste cobre essa recuperação. O teste
de geração Pro `count=4` também confirma quatro IDs/resultados com uma única
submissão e downloads locais. Suíte WSL completa: 152 testes. Esses dois
caminhos ainda não foram validados no Windows.

Em 02/10/2026, a suíte Windows completa também passou com 152 testes, após
incluir no `PATH` do processo o FFmpeg instalado pelo WinGet. Isso valida os
testes locais, não a operação remota `count=4`. Os perfis do worker MCP
retornaram `no_session` e `google_session_only` no Windows e
`verification_error` no WSL; a sessão visível no navegador não foi transferida.
Nenhuma geração foi enviada e nenhum crédito foi gasto.

## Limite de upscale 4K na conta atual — 02/10/2026

A [ajuda oficial de créditos do Flow](https://support.google.com/flow/answer/16526234?co=GENIE.Platform%3DDesktop&hl=pt)
indica que o upscale de vídeo em 4K exige plano Ultra e custa 50 créditos;
planos Pro não têm acesso. Como a conta deste projeto é Pro, não há validação
de 4K a fazer nela. O código segue limitado às resoluções nativas confirmadas
em Windows: 720p e 1080p.

## Retomada multimídia e acompanhamento — 03/10/2026

O perfil Windows `conta-ponte-a` voltou a confirmar `authenticated`; não foi
necessário importar a sessão do Chrome habitual. Saldo inicial HTTP: 906.
A variação em relação à leitura anterior de 884 não foi atribuída a nenhuma
operação. O catálogo Pro oferece geração 360p/720p; o upsampler de vídeo 1080p
está disponível a custo zero e o 4K está indisponível por plano. A geração
1080p/4K continua sem uma variante compatível confirmada nesta conta.

Validações reais pelo worker MCP Windows, sem reenvio:

- Nano Banana Pro `count=4`: quatro JPEGs 1024×1024 baixados.
- Edição Nano Banana 2 Lite `count=3`: três JPEGs 1024×1024 baixados e leitura
  posterior de resultado confirmada.
- Edição Nano Banana 2 `count=4`: quatro JPEGs 1024×1024 baixados e leitura
  posterior confirmada; nesta tentativa o resultado foi completo.
- As três operações de imagem tiveram cotação zero, com saldo 906 antes/depois.
- Omni Flash 4s/360p/16:9 com quadros inicial/final por IDs do mesmo projeto:
  geração e download concluídos, custo 4.
- Dois turnos de `flow_refine_video` sobre essa saída: cada turno concluiu e
  baixou um MP4, custo 10 por turno, sem novo upload de referência. Os três MP4
  foram decodificados integralmente por FFmpeg: H.264/AAC, 640×360, 4,011s,
  com 897.826, 734.255 e 697.861 bytes. Workflow preservado e encadeamento
  de cada saída como origem do turno seguinte conferidos nas tarefas locais.
- A tarefa antiga de referência por ID de vídeo continua `not_listed` após
  uma consulta de `flow_wait_job(timeout_seconds=0)`; nenhum reenvio.

Gasto desta retomada: 24 créditos; saldo 906→882. Gasto confirmado acumulado:
290/500. Mantida a reserva anterior de 7 créditos pelo envio incerto de vídeo:
297/500 contabilizados, 203 restantes do teto autorizado.

`flow_wait_job` foi implementado para acompanhamento por reconciliação e
download dos IDs da tarefa original. Espera de 0–600s, intervalo de 2–60s;
zero faz uma consulta. O prazo impede novas consultas após seu vencimento,
sem interromper uma consulta/download já em andamento. `wait_status` é
separado do estado persistido; timeout não transforma resultado incerto em
falha nem autoriza geração adicional. Cancelamento local é observado antes
da recuperação e entre consultas; não cancela o trabalho no serviço.

A inicialização do MCP agora fixa `GFLOW_CLI_HOME` no `FLOW_MCP_HOME` resolvido,
assim as ferramentas locais e os workers usam as mesmas tarefas mesmo quando
o processo herda configuração gflow de outro projeto. O teste stdio exerce
explicitamente essa configuração divergente.

Suítes completas WSL e Windows: 159 testes aprovados; MCP: 60 ferramentas.
No Windows, o FFmpeg do WinGet foi incluído no PATH do processo. As inspeções
do editor não confirmaram controles dedicados de câmera/objetos nem um caminho
novo para upscale de imagem; o endpoint antigo com bearer ausente não foi
tentado. Referência de vídeo local, refinamento com três turnos, paginação e
upscale nativo de imagem continuam pendentes. Esta validação de refinamento
comprova o encadeamento e workflow; não prova equivalência contextual com a
conversa da interface.

## 03/10/2026 — upscale migrado de imagem e referências no refinamento

A interface de download de imagem Pro confirmou `SPrCad` para 2K. O envio do
navegador foi bloqueado e o pedido nativo capturado; após fechar a página e
conferir novamente o catálogo, uma única requisição HTTP foi enviada. O caminho
Aisandbox legado não foi repetido. A resposta traz registro de ativo e JPEG em
base64; somente o arquivo e metadados sanitizados são persistidos.

`flow_upscale_image` agora utiliza esse caminho 2K, com tarefa determinística
por conta/projeto/origem/resolução. Repetições reutilizam o resultado e o upload;
envio incerto não é repetido. Falha de gravação ou upload preserva os metadados
locais e não autoriza novo envio. 4K permanece bloqueado porque o corpo nativo
não foi validado e o plano atual não oferece esse recurso.

Duas operações 2K concluíram no Windows, uma pela sondagem e outra pela
ferramenta MCP. Esta última gerou JPEG 2048×2048 de 4.099.799 bytes, totalmente
decodificado por FFmpeg; upload ao projeto e leitura 2048×2048 confirmados.
Uma segunda chamada à ferramenta reutilizou a mesma tarefa e o mesmo upload.
A listagem passou a devolver o ativo nativo sem dimensões: o parser agora
reconhece o formato observado e informa `dimensions=null`, incluindo no
histórico, sem impedir a leitura dos demais ativos.

`flow_refine_video` aceita `reference_video_paths`, envia os arquivos apenas
no primeiro turno e reutiliza seus IDs nos demais. Aviso de direitos expõe o
ID de confirmação no turno e interrompe a cadeia sem descontar geração não
enviada do orçamento. Dois testes cobrem reutilização em três turnos e aviso;
validação remota com referência local ainda pendente. Inspeção do editor não
confirmou controles dedicados de câmera/objetos.

Sem novos créditos gastos; saldo 882 antes/depois. Confirmado acumulado
290/500; reserva de 7 mantida: 297/500 contabilizados, 203 restantes.
Suítes completas WSL e Windows: 163 testes; MCP: 60 ferramentas.

## 03/10/2026 — edição em novo histórico e refinamento com três turnos

A captura bloqueada do compositor mostrou que anexar um vídeo prepara `jIps6`
com o vídeo como origem e sementes para um novo workflow, sem ID de histórico
existente. Um segundo vídeo selecionado não apareceu no pedido dessa sondagem.
Isso não confirma vídeo como ingredient de `MZZa6b`; a tarefa antiga incerta
continua preservada, sem reenvio. Não foram gravados corpos autenticados.

`flow_edit_video(create_new_workflow=True)` agora reproduz o pedido nativo
para editar em um histórico separado. O padrão False mantém o histórico de
origem. O orçamento e as configurações continuam conferidos no catálogo;
origem, workflow esperado e novo media ID ficam na tarefa antes do POST.
A opção aceita apenas edição e booleano estrito. Dois testes novos cobrem
metadados, IDs esperados, validação e envio único em resposta incerta.

Validação pelo MCP Windows: edição Omni Flash 4s/360p/16:9 em novo histórico,
custo 10, seguida de três turnos de `flow_refine_video`, custo 10 cada. Os três
refinamentos concluíram no workflow criado e usaram a última saída como origem.
Quatro MP4 H.264/AAC 640×360 de 4,011s foram decodificados integralmente por
FFmpeg: 670.483, 915.420, 870.932 e 890.257 bytes. Isso comprova encadeamento,
workflow e arquivos; equivalência contextual com a conversa da interface não
foi demonstrada. Recuperação da edição em novo histórico passou sem reenviar a mutação;
leitura posterior confirmou os quatro resultados e seus workflows.
Referências de vídeo como ingredientes continuam pendentes.

Gasto desta etapa: 40 créditos; saldo 882→842. Confirmado acumulado 330/500;
reserva anterior de 7 mantida: contabilizados 337/500, restantes 163.
Suítes completas WSL e Windows: 165 testes; MCP: 60 ferramentas.

## 03/10/2026 — cenas no Flow migrado

`flow_list_scenes` lista IDs e títulos pela quinta seção de `Zzl0ze`, inclusive
cenas vazias; pesquisa por título/ID, `complete=false` por paginação não
verificada. `flow_manage_scene(create)` sem workflow_ids cria uma cena vazia
pela interface normal: captura `rqZuUc` com envio bloqueado, fecha a página,
envia uma única requisição HTTP e confirma a cena na leitura posterior.
A tentativa inicial com template de consulta retornou `submission_unknown`,
sem ID confirmado; não foi reenviada. A operação independente pelo caminho
capturado concluiu no Windows pelo MCP, apareceu na listagem e no filtro por ID.

A sondagem de inclusão de um clipe capturou `oWTRd`, com project_id, scene_id,
lista de workflow_ids e posição. Um envio único incluiu um clipe; essa inclusão
ainda não foi integrada à ferramenta MCP. A composição foi localizada na
sétima seção de `Zzl0ze`. `flow_manage_scene(read)` agora lê os clipes clonados,
valida vídeo/projeto e devolve ordem, início/fim e duração. Leitura pelo MCP
Windows confirmou um clipe na posição 0, corte 0–4s e duração total 4s.

Criação com clipes, atualização de cortes/ordem e exportação remota ainda usam
código legado sem validação na conta migrada. Montagem local via FFmpeg já
existe e não substitui a cena persistida no Flow. A paginação permanece incerta.
Nenhum crédito gasto: saldo 842 antes/depois; confirmado 330/500, reserva 7,
contabilizados 337/500, restantes 163. MCP: 61 ferramentas.

## 03/10/2026 — inclusão, ordem e cortes de cena nativos

`flow_manage_scene(operation="add")` inclui vídeos do projeto numa cena
existente por uma única RPC HTTP `oWTRd`, com corpo contendo projeto, cena,
workflow IDs e posição (padrão ao final). O registro local da tarefa é gravado
antes do envio. O resultado é decidido exclusivamente por leitura posterior
de `Zzl0ze` (até 6 leituras com intervalo de 2s, sem novos envios); qualquer
incerteza é mantida como `submission_unknown` sem reenvio automático.

A cena armazena clones: cada clipe incluído recebe um novo `workflow_id`
(retornado em `added_workflow_ids`). Portanto, a confirmação ocorre pela
contagem de novos clipes e pelas posições na cena, e não pelo ID de origem
enviado. Duas tentativas reais iniciais concluíram no Flow, mas a confirmação
anterior por ID reportou `submission_unknown`; não houve reenvio e a lógica
foi corrigida. Validado no Windows pelo MCP: inclusão ao final, inserção na
posição 0 (confirmada pela ordem de criação dos clones) e na posição 1,
formando cena com 4 clipes nas posições 0–3.

`flow_manage_scene(operation="update")` agora utiliza a RPC nativa `GoMJte`
(`UpdateSceneWorkflows`), capturada no editor de cena com envio bloqueado ao
arrastar a alça de corte. O corpo envia projeto, cena e a lista completa dos
clipes com posições e cortes (início/fim em segundos e frações). A confirmação
é feita por leitura posterior da ordem e dos cortes em `Zzl0ze`, sem reenvio.
Validado no Windows: reordenação de 4 clipes e corte de 0,5–6,25s confirmados.

`flow_manage_scene(operation="create", workflow_ids=[...])` agora cria a cena
vazia via `rqZuUc` e inclui os clipes via `oWTRd`; validado no Windows com 2
clipes. O caminho legado Aisandbox foi removido de create e update.
`flow_export_scene` permanece no caminho legado e sem validação na conta
migrada (pendente).

Nenhum crédito gasto: saldo 842 antes/depois. Gasto confirmado acumulado:
330/500; reserva anterior de 7 mantida: contabilizados 337/500, restantes 163.
Suíte WSL completa: 173 testes passaram; MCP: 61 ferramentas. A suíte Windows
não foi executada nesta etapa.

## 03/10/2026 — exportação nativa de cena

`flow_export_scene` agora utiliza RPCs nativas pelo cliente HTTP: `GjQLTd`
recebe a mídia de cada clipe com início e fim na ordem da cena e devolve um
identificador de operação; `IxdSwd` acompanha o processamento (estado 2 em
andamento; ao concluir, o MP4 chega codificado em base64 no quinto campo).
O binário é validado pela assinatura `ftyp` e salvo em `downloads/`.
O registro local da tarefa é gravado antes do envio; falha após a submissão
resulta em `submission_unknown` sem reenvio automático. O caminho legado
Aisandbox foi totalmente removido da exportação.

O fluxo foi observado pela interface normal (botão "Baixar cena"), onde o
frontend converte o base64 em download de blob. A operação foi validada no
Windows pelo MCP: uma cena com 4 clipes (um deles aparado de 0,5 a 6,25 s) foi
exportada como MP4 H.264/AAC 1280×720 de 29,79 s (8 + 8 + 8 + 5,75 s) e
28.240.589 bytes, totalmente decodificado por FFmpeg. Saldo: 842 antes e depois.

Com essa validação, todo o ciclo de cenas (criar, listar, ler, incluir,
reordenar, aparar e exportar) está comprovado na conta migrada. Pendências
remanescentes em cenas: remoção individual de clipe da cena e exclusão de cena
(a RPC `BatchDeleteScenes` existe no bundle, mas não foi integrada ao MCP),
além da paginação remota.

Nenhum crédito gasto: saldo mantido em 842. Gasto confirmado: 330/500; reserva
de 7 mantida (337/500 contabilizados, 163 restantes). Suíte WSL completa: 173
testes passaram; MCP: 61 ferramentas. Documentação e o teste de exportação
desta etapa foram produzidos por um agente auxiliar (Antigravity CLI) sob
coordenação via Orca e revisados antes de aceitos.

## 03/10/2026 — remover clipe, renomear e arquivar cena

`flow_manage_scene` incorporou três operações adicionais, todas gravando o
registro local da tarefa antes do envio, realizando uma única mutação e
decidindo o resultado exclusivamente por leitura posterior de `Zzl0ze` (até 6
leituras intervaladas); qualquer incerteza vira `submission_unknown` sem
reenvio automático:

- `remove`: recebe os `workflow_ids` dos clipes a remover da cena; a interface
  trata a remoção reenviando a lista restante via `GoMJte` com posições
  renumeradas de 0 a n e cortes preservados. Esvaziar integralmente a cena é
  bloqueado antes do envio (cena vazia via `GoMJte` não foi capturada).
- `rename`: recebe o novo `title` e envia a RPC `BpMsoe` (`UpdateScene`) com a
  máscara de campos `display_name`.
- `archive`: exige `confirm=true` e envia `BpMsoe` com a máscara
  `scene_metadata.is_archived` e `parent_collection_id`, capturada na ação
  "Mover para a lixeira" no card da cena. A cena permanece na resposta do
  projeto com a marcação `scene_metadata = [true]`. `flow_list_scenes` passou a
  informar `archived=true/false` em cada cena.

Durante a captura com envio bloqueado, a interface removeu o card da lista de
forma otimista; a leitura HTTP seguinte comprovou que a cena continuava intacta.

Validação no Windows pelo MCP em cena de teste com 2 clipes: `rename` e `remove`
concluíram e foram confirmados por leitura (1 clipe restante na posição 0 com
corte preservado). `archive` retornou inicialmente `submission_unknown` porque a
confirmação esperava a remoção completa da linha; a leitura posterior confirmou
`archived=true`. Não houve reenvio e a confirmação foi corrigida para checar a
flag. A RPC `BatchDeleteScenes` (exclusão definitiva) não foi integrada, pois a
interface opera via lixeira.

Nenhum crédito gasto: saldo mantido em 842. Gasto confirmado: 330/500; reserva
de 7 mantida (337/500 contabilizados, 163 restantes). Suítes completas WSL e
Windows: 175 testes passaram; MCP: 61 ferramentas. No Windows, o FFmpeg do
pacote WinGet precisa estar no PATH do processo (pasta bin do pacote
Gyan.FFmpeg). Os testes desta etapa foram escritos pelo agente auxiliar
(Antigravity) e revisados/ajustados pelo coordenador.

## 03/10/2026 — vídeo como referência, ferramentas e Agent

A hipótese de vídeo como referência/ingrediente de geração foi comprovada como
não suportada pelo Flow:
1. Captura com envio bloqueado revelou que escolher um vídeo do projeto com `@` no
   compositor gera a RPC `jIps6` em modo de edição (`abra_edit`), usando o vídeo
   como origem e criando um novo workflow. Trata-se de edição e não de ingrediente
   para geração `MZZa6b`. Além disso, um segundo vídeo selecionado não entra no
   pedido.
2. Em teste real autorizado pelo usuário (Omni Flash 4s/360p r2v, cotação de 4
   créditos com teto 10) usando um vídeo do projeto em `reference_asset_ids`, a
   submissão `MZZa6b` foi recusada pelo backend (`failure_stage=submitting`,
   `submission_unknown`), nada foi listado no projeto e o saldo permaneceu 842
   (sem cobrança), repetindo o comportamento da tentativa anterior sem qualquer
   reenvio.
3. Conforme decisão do usuário, o parâmetro `reference_video_paths` foi removido
   de `flow_generate_video`, `flow_edit_video` e `flow_refine_video`. Passar IDs
   de vídeo em `reference_asset_ids` passa a ser recusado antes de qualquer
   envio (`failed_pre_submit`), com orientação explícita para o uso de
   `flow_edit_video(create_new_workflow=True)`. Cinco testes legados foram
   removidos e um novo teste cobre a rejeição pré-envio.
4. Contabilidade: a reserva de 7 créditos referente à tentativa incerta anterior
   permanece mantida por cautela (confirmado 330/500; contabilizados 337/500;
   restantes 163). O teste desta etapa não consumiu créditos.

Ferramentas (Tools) do Flow foram mapeadas como applets (`FlowAppletAgentService`):
- `flow_list_tools(category=all|mine|templates|community, query)` lê
  `ListApplets` (`tRARke`) por HTTP sem mutação. As categorias correspondem a:
  1 = Minhas ferramentas, 2 = Modelos (Google), 3 = Comunidade (com autor e
  tags).
- Validado no Windows: 69 ferramentas listadas (34 da comunidade, 34 modelos e 1
  própria), com funcionamento do filtro por texto. `complete=false` sinaliza
  paginação não verificada. A execução de applets (`RunAppletAgent` `Z8KLDf`)
  não foi implementada.

Agent do Flow:
- `flow_get_agent_brief` retorna `http_error` na conta migrada porque ainda usa
  o endpoint legado Aisandbox; necessita migração.
- `GetSession` (`GN0Bre`) retorna somente metadados da sessão (título, datas,
  estado), sem mensagens. O botão "Agente" do compositor não ativou o modo no
  frontend (`aria-pressed=false`) e o envio virou geração normal `YhhmEf`
  (bloqueada). Mapear mensagens exigiria submeter mensagens reais ao Agent, o que
  pode gerar mídia e gastar créditos, permanecendo pendente.

Suíte WSL completa: 172 testes passaram; MCP: 62 ferramentas. Sem créditos
gastos nesta validação (saldo 842).

Inspeção do editor de vídeo na conta migrada, com envios bloqueados: a tela
oferece somente o campo "Descreva como editar este vídeo…" com Omni 1.1 Flash e
o botão de anexos. Não há controles dedicados de câmera nem de inserir/remover
objetos; essas mudanças são pedidas no prompt de `flow_edit_video`, caminho já
validado. O seletor de anexos do editor lista apenas imagens, além das
categorias Personagens, Avatares e Vozes; nenhum vídeo aparece, reforçando que
vídeo não é referência nem na edição.

## 03/10/2026 — voz pronta em geração de vídeo

1. Captura com envio bloqueado revelou que o seletor "+" do compositor possui as
   categorias Imagens, Personagens, Avatares, Vozes e Envios. A conta possui 30
   vozes prontas disponíveis e nenhum personagem ou avatar cadastrado.
2. Quando apenas a voz é selecionada no compositor, o frontend envia texto→vídeo
   comum (`YhhmEf`) sem incluir a voz. Quando combinada com ao menos uma imagem
   como ingrediente, envia `MZZa6b` (r2v) com o identificador da voz em minúsculas
   no campo 7 da linha do pedido.
3. `flow_generate_video` recebeu o parâmetro `voice` (preset listado por
   `flow_list_voice_presets`, comparado sem distinguir maiúsculas/minúsculas). O
   uso de voz exige `model="omni-flash"` e ao menos uma referência de imagem
   (local ou `reference_asset_ids`); combinações divergentes são recusadas
   antes de qualquer envio (`failed_pre_submit`). O job registra a voz utilizada
   e testes unitários cobrem o corpo do pedido e as validações pré-envio.
4. Validado no Windows pelo MCP: geração Omni Flash 4s/360p/16:9 com uma imagem
   do projeto e a voz "Achernar". A operação concluiu e baixou um MP4 H.264
   640×360 com áudio AAC audível (nível médio de −22,7 dB), duração de 4,011 s,
   integralmente decodificado por FFmpeg. Custo: 4 créditos (conforme cotado);
   saldo observado passou de 842 para 838. A identidade e consistência do timbre
   não foram verificadas objetivamente.
5. Contabilidade: gasto confirmado acumulado de 334/500 créditos; mantida a
   reserva de 7 créditos por cautela (341/500 contabilizados, 159 restantes do
   teto autorizado).
6. Suíte WSL completa: 173 testes passaram; MCP: 62 ferramentas.
7. Pendências: personagens e avatares como ingredientes de geração (a conta não
   possui nenhum cadastrado; avatar exige celular), vozes personalizadas e
   aplicação de voz em edição de vídeo.

## 03/10/2026 — restaurar e excluir cena

Capturas com envio bloqueado na página Lixeira do projeto revelaram os pedidos
nativos de gerenciamento de cenas arquivadas:
- "Restaurar" utiliza a RPC `BpMsoe` (`UpdateScene`) com `scene_metadata` vazio
  e máscara `scene_metadata.is_archived` e `parent_collection_id`, retornando
  a cena ao estado ativo (`archived=False`).
- "Excluir permanentemente" abre um diálogo modal de confirmação
  (Cancelar/Excluir) e dispara `cz8Z4b` (`BatchDeleteAssets`) passando o ID da
  cena na lista de ativos a excluir.

`flow_manage_scene` foi estendida com as operações `restore` e `delete`:
- `restore`: envia `BpMsoe` uma vez e confirma quando a cena aparece na listagem
  com `archived=False`.
- `delete`: exige `confirm=True` (senão levanta `ValueError` antes de qualquer
  RPC) e verifica se a cena está arquivada na listagem inicial (senão retorna
  `failed_pre_submit` sem envio à rede); envia uma única vez `cz8Z4b` com o ID da
  cena e confirma o status `"deleted"` quando a cena não mais consta em `Zzl0ze`.
  Respostas incertas retornam `submission_unknown` sem reenvio automático.

Validação no Windows pelo MCP na cena de teste criada nesta sessão:
`restore` (confirmado com `archived=False`), novo arquivamento (`archived=True`)
e `delete` definitivo (cena removida da listagem do projeto). A interface não
utiliza `BatchDeleteScenes` (RPC existente no bundle mas não acionada pela UI).

Nenhum crédito foi gasto nesta validação (saldo mantido em 838; gastos confirmados:
334/500, contabilizados: 341/500 com a reserva de 7, restantes: 159).

Pendências remanescentes em cenas: esvaziamento total de cena via `GoMJte`
e paginação remota.

## 03/10/2026 — personagens nativos

A página "Novo personagem" da conta migrada oferece três métodos: criar por
descrição (Nano Banana 2), enviar arquivo local ou "Adicionar do projeto".
As requisições foram capturadas com o envio bloqueado pelo frontend e depois
liberadas uma a uma:
- "Adicionar do projeto" executa sequencialmente `CreateEntity` (`C4BZMd`) e
  `CopyProjectMedia` (`Sc7aEb`). A primeira cria o registro do personagem no
  projeto e a segunda vincula a imagem escolhida como referência (slot 0).
- "Renomear" executa `UpdateEntity` (`rzMKMb`) com a máscara
  `entity_info.display_name`.
- "Excluir" abre um diálogo modal de confirmação no editor e dispara `cz8Z4b`
  (`BatchDeleteAssets`) passando o ID do personagem.
- Personagens constam na sexta seção (`payload[5]`) de `Zzl0ze`. A RPC
  `ListEntities` não é acionada pela interface do Flow.

`flow_list_characters` e `flow_manage_character` foram migrados do transporte
legado (Aisandbox/tRPC) para o cliente HTTP nativo:
- `create`: recebe `display_name` e `image_media_id` de uma imagem do projeto.
- `rename`: recebe `entity_id` e `display_name`.
- `delete`: exige `entity_id` e `confirm_delete=true` (retorna
  `confirmation_required` antes de qualquer RPC se omitido).
- Os parâmetros legados `voice` e `personality` foram removidos até que seus
  pedidos nativos sejam mapeados no editor de personagem.

Correção de compatibilidade em `parse_assets`: a vinculação de imagem ao
personagem (`Sc7aEb`) cria uma cópia interna sem indicador de revisão (`row[3]
= None`). Anteriormente isso causava `ValueError` invalidando a leitura de todos
os ativos do projeto. `parse_assets` agora ignora essas cópias (capa e mídias de
referência presentes em `payload[5]`), replicando o comportamento da interface.

Validação no Windows pelo MCP: criação de personagem a partir de imagem do
projeto (1 referência confirmada por leitura), renomeação e exclusão definitiva
(incluindo a limpeza de dois personagens criados nas sondagens anteriores);
listagem final confirmada como vazia.

Nenhum crédito gasto (saldo mantido em 838; gastos confirmados acumulados:
334/500, contabilizados: 341/500, restantes: 159). Suíte completa WSL: 176
testes aprovados; MCP: 62 ferramentas.

Pendências remanescentes em personagens: personagens como ingredientes de
geração de vídeo/imagem, configuração de voz e personalidade no personagem,
segunda imagem de referência e cadastro de avatar.

## 03/10/2026 — personagem como ingrediente

1. Captura com envio bloqueado revelou que, ao escolher um personagem no menu
   "+" > "Personagens" do compositor, o frontend envia `MZZa6b` (r2v) sem imagem
   de referência nos campos padrão de mídia, posicionando o identificador do
   personagem no campo 9 da linha do pedido. A voz, quando informada, é colocada
   no campo 7.
2. `flow_generate_video` recebeu o parâmetro `character_ids` (aceita de 1 a 3
   IDs de personagens obtidos por `flow_list_characters`, conferidos na resposta
   do projeto antes da submissão). O uso exige `model="omni-flash"` em modo de
   geração (rejeitado em edição ou quadros inicial/final). Além disso, o parâmetro
   `voice` passou a aceitar personagens como ingrediente válido (exige imagem
   OU personagem). Testes unitários cobrem a validação pré-envio e a estrutura
   do corpo nativo capturado.
3. Validado no Windows pelo MCP: criação do personagem de teste "Lake keeper" a
   partir de uma imagem do projeto (sem custo de créditos) e seu uso isolado
   como ingrediente em geração Omni Flash 4s/360p/16:9. A operação concluiu e
   baixou um MP4 H.264/AAC 640×360 de 4,011 s, decodificado com sucesso por
   FFmpeg. Custo observado: 4 créditos (conforme cotado no catálogo); saldo
   passou de 838 para 834. Como a referência visual era uma paisagem com cabana,
   o resultado gerou uma pessoa caminhando no píer; a consistência da identidade
   do personagem não foi avaliada. O personagem de teste foi mantido no projeto.
4. Contabilidade: gasto confirmado acumulado de 338/500 créditos; mantida a
   reserva de 7 créditos por cautela (345/500 contabilizados, 155 restantes do
   teto autorizado).
5. Suíte WSL completa: 176 testes; MCP: 62 ferramentas.
6. Pendências de personagens: voz e personalidade configuradas no personagem,
   segunda imagem de referência, cadastro de avatar (exige dispositivo móvel),
   criação de personagem por descrição (Nano Banana 2) e consistência da face
   com referência humana real.

## 03/10/2026 — Flow Agent por HTTP, preferências e incidente

1. **Protocolo do Agent**: O Flow Agent opera via POST HTTP para o endpoint
   `FlowCreationAgentService/StreamChat` utilizando payload de formulário com
   parâmetro `f.req` e resposta em fluxo `wrb.fr`. O stream carrega chamadas a
   ferramentas internas do projeto (ex.: `list_project_artifacts`) e a resposta
   textual final formatada em blocos JSON A2UI contendo `literalString`.
2. **Ferramenta exposta**: Implementada a ferramenta
   `flow_agent_request(account_id, project_id, message, allow_media_changes=false)`.
   Por padrão, `allow_media_changes` é mantido como falso para proteger o projeto
   contra mutações não intencionais geradas pelo assistente.
3. **Validação no Windows**: Três requisições reais com perguntas sobre o projeto
   foram validadas no Windows sem custo de créditos. O Agent respondeu
   corretamente sobre o total de imagens no projeto, mas indicou erroneamente que
   não havia vídeos no projeto (quando existiam 16). Respostas do Agent estão
   sujeitas a erros e alucinações.
4. **Incidente de consumo e mitigação**: Durante o desenvolvimento do preparo de
   sessão no navegador, o texto de exemplo do compositor foi acidentalmente
   enviado, e a ativação do modo Agent via clique na UI ocasionou o envio de
   um comando de geração de vídeo padrão (Omni Flash 4s/720p) ao pressionar Enter.
   Isso consumiu 7 créditos não intencionais, reduzindo o saldo de 834 para 827.
   Três proteções foram introduzidas: (a) o preparo do navegador agora bloqueia e
   aborta ativamente requisições RPC de geração de mídia (`MZZa6b`, `jIps6`,
   `eb1hJf`, etc.), (b) a submissão HTTP exige a verificação de que o modo Agent
   está ativado antes do preparo, e (c) `agent_request` ativa o modo Agent via
   preferências HTTP (`flow_update_user_settings`) antes do preparo e o restaura
   ao valor original após a execução.
5. **Correção nas preferências do usuário**: O método `flow_update_user_settings`
   foi corrigido para enviar o campo `update_mask` como lista e valores booleanos
   representados como inteiros (1/0), permitindo a correta atualização remota.
6. **Ferramentas do Flow**: As ferramentas retornadas por `flow_list_tools` utilizam
   o construtor `RunAppletAgent` ("Crie sua ferramenta"), não permitindo execução
   direta genérica; `flow_list_tools` permanece como a ferramenta exposta para
   catálogo e inspeção de applets disponíveis.
7. **Contabilidade e suíte**: Gastos confirmados acumulados passam a 345/500
   créditos (incluindo os 7 do incidente); com a reserva cautelar de 7 créditos
   de submissão incerta anterior, totaliza-se 352/500 contabilizados, restando
   148 créditos do teto autorizado. Saldo atual confirmado: 827. Suíte WSL: 178
   testes aprovados; MCP expõe 63 ferramentas.


## 03/10/2026 — continuação de sessão do Agent e despacho restaurado

`flow_agent_request(session_id=...)` continua uma conversa existente: a sessão é
conferida na listagem do projeto, o preparo não abre sessão nova e o pedido
retido passa a usar a sessão indicada. Validado no Windows: a pergunta de
continuação foi respondida com o contexto da conversa anterior, na mesma
sessão, sem ferramentas e sem custo; a preferência do modo Agente voltou ao
estado original.

Regressão encontrada: `create_agent_session` e `delete_agent_session` não
estavam no despacho do worker, e as ferramentas MCP correspondentes falhavam
com `http_error`. O despacho foi restaurado e um teste agora exige que toda
ação usada por `flow_mcp.py` tenha tratamento no worker. Criação e exclusão
de sessão foram validadas no Windows pelo MCP (sessão vazia de teste removida;
o pedido nativo de exclusão capturado na interface é o mesmo `Dcn2Le`).
Sem créditos gastos; saldo 827. Suíte WSL: 179 testes.

## 03/10/2026 — brief do Agent nativo

1. **Protocolo e migração**: O painel do Agent contém a seção "Instruções para o
   agente" (Adicionar instrução / Concluir). Ao salvar, a interface envia
   `/AiSandbox.UpdateAgentInfo` (`Kcr7Ub`) com máscara `project_brief`. O brief
   completo do projeto é lido na oitava seção (`payload[7]`) de `Zzl0ze`
   (`agentInfo`). A interface também dispara `Kcr7Ub` ao abrir o painel ou
   alternar o modo do Agent; sondagens prévias liberaram essa requisição
   supondo leitura, correspondendo ao comportamento nativo da UI.
2. **Ferramentas MCP**: `flow_get_agent_brief` e `flow_update_agent_brief` foram
   migrados do transporte legado Aisandbox (que resultava em `http_error`) para
   o cliente HTTP nativo. Os cartões de instrução suportam `id`, `title`, `text`
   e `enabled`; referências de imagem e personagem em cartões ainda não são
   suportadas pelo editor nativo. `update_agent_brief` exige
   `confirm_replace_instructions=True` para substituir a lista de instruções,
   envia `Kcr7Ub` uma única vez e confirma a mutação comparando leituras de
   `Zzl0ze` (sem reenvio em caso incerto).
3. **Validação no Windows**: Leitura do brief (incluindo cartão de sondagem),
   substituição por dois cartões (um desativado) com o brief ativado, e
   restauração ao estado original (brief desativado, sem cartões) foram
   validados no Windows pelo MCP e confirmados por leitura subsequente. Nenhum
   crédito foi gasto (saldo mantido em 827; gastos confirmados: 345/500,
   contabilizados: 352/500, restantes: 148).
4. **Pendências remanescentes do Agent**: referências visuais/personagens em
   cartões de instrução e paginação remota de sessões (a pendência de brief
   nativo foi resolvida). Suíte WSL: 181 testes aprovados; MCP: 63 ferramentas.

## 03/10/2026 — voz e personalidade do personagem

1. **Editor de personagens**: Na conta migrada, o editor do personagem oferece
   campos para nome, "Selecionar uma voz" (presets de voz), "Personalidade do
   personagem" (texto de até 2.000 caracteres), imagens de referência (Upload e
   Adicionar do projeto) e botões de geração (Criar retrato/Criar corpo). Com
   o envio bloqueado, constatou-se que alterações de voz e personalidade são
   salvas por `UpdateEntity` (`rzMKMb`) utilizando respectivamente as máscaras
   `entity_info.character_info.audio_references` e
   `entity_info.character_info.personality_notes`.
2. **Estrutura de dados e correções**: A estrutura de `character_info` na 6ª
   seção (`payload[5]`) de `Zzl0ze` é organizada como
   `[imagens [[id], ...], vozes [[_, preset]], personalidade]`. O parser de
   personagens (`parse_characters`) foi expandido para extrair `voice`,
   `personality` e `reference_media_ids`. O filtro de exclusão de cópias
   internas em `parse_assets` foi ajustado para inspecionar `character_info[0]`,
   evitando interpretar voz e personalidade como listas de mídias.
3. **Validação no Windows**: `flow_manage_character(operation="update")` com
   `voice` ("Achernar") e `personality` ("Guardião calmo") foi validado no
   Windows no personagem de teste existente ("Lake keeper"). Os dados foram
   salvos via `rzMKMb`, confirmados por releitura de `Zzl0ze`, e `flow_list_assets`
   permaneceu operando perfeitamente. Nenhum crédito foi gasto (saldo mantido
   em 827; gastos confirmados: 345/500, contabilizados: 352/500, restantes: 148).
4. **Pendências remanescentes de personagens**: segunda imagem de referência,
   cadastro de avatar pessoal (exige dispositivo móvel) e criação de personagem
   por descrição/retrato/corpo. Suíte WSL: 184 testes aprovados; MCP: 63 ferramentas.



## 03/10/2026 — esvaziar cena

Captura com envio bloqueado: remover o último clipe no editor de cena envia
`GoMJte` apenas com projeto e cena, sem a lista de clipes. `flow_manage_scene`
(`remove`) deixou de recusar a remoção de todos os clipes e gera esse formato,
confirmando por leitura a cena sem clipes. Validado no Windows pelo MCP numa cena
de teste criada com um clipe: esvaziada, enviada à lixeira e excluída. Sem
créditos; saldo 827. Pendência de cena restante: paginação.

## 03/10/2026 — imagens adicionais do personagem (não reproduzido)

No editor do personagem, "Adicionar do projeto" com retrato já existente envia
o mesmo `Sc7aEb` (cópia com `[personagem, [0]]`) da criação, sem outro pedido
capturado; a tela passa a mostrar "Retrato" e "Criar corpo". Repetido por HTTP,
o envio não alterou referências nem capa na leitura (três tentativas, sem
reenvio automático, sem créditos; podem ter ficado cópias de imagem ocultas no
projeto). A operação não foi exposta. Trocar retrato e definir corpo seguem
pendentes; "Criar retrato/corpo" geram mídia e não foram usados.

## 03/10/2026 — personagem por descrição e voz personalizada

1. **Criação por descrição**: Na interface, "Novo personagem" por descrição cria
   o personagem (`C4BZMd`) e em seguida gera o retrato via `ogiZ0b` (Nano Banana
   2), com a imagem vinculada ao retrato na posição 0 do último elemento do pedido
   (`[uuid, None, [entity_id, [0]]]`).
2. **Implementação e validação**: `flow_manage_character(create, description=..., max_credits=...)`
   reaproveita a geração de imagem cotada no catálogo. Foi validado no Windows:
   personagem "Faroleiro" criado com retrato gerado e vinculado (1 referência),
   custo zero e saldo mantido em 827; em seguida excluído. Um personagem vazio
   deixado pela sondagem também foi excluído, restando apenas "Lake keeper".
3. **Voz personalizada**: O seletor de voz de personagem e compositor oferece
   exclusivamente presets fixos (com prévia em áudio); não há criação de voz
   personalizada disponível na conta/interface observada.
4. **Tempos limite do worker**: Ajustados para 1.260 s em `manage_character` com
   descrição e 660 s para `agent_request`.
5. **Pendências de personagens restantes**: Trocar retrato/definir corpo e avatar
   pessoal (exige aplicativo em dispositivo móvel).

## 03/10/2026 — retrato e corpo do personagem

1. Capturas com envio bloqueado: "Adicionar do projeto" envia `Sc7aEb` com
   `[entidade, [0]]` no Retrato e `[entidade, [1]]` no Corpo; "Excluir imagem"
   envia `rzMKMb` com a máscara `entity_info.character_info.image_references` e a
   lista posicional `[retrato, corpo]`, usando `[]` no slot esvaziado.
2. `Sc7aEb` em slot ocupado retorna RPC não reconhecida (explica as tentativas
   anteriores sem efeito). `flow_manage_character` ganhou `set_image` (limpa o
   slot ocupado antes de adicionar; aceita `description` + `max_credits` para
   gerar com Nano Banana 2) e `remove_image`; `parse_characters` passou a expor
   `portrait_media_id` e `body_media_id` e a aceitar entradas vazias.
3. O slot do Corpo cria outra cópia interna sem revisão que não é capa nem
   referência, e quebrava `parse_assets`; linhas de imagem sem versão são
   ignoradas quando o projeto tem personagens (sem personagens continua erro).
4. Validado no Windows pelo MCP: corpo por imagem, troca de retrato e de corpo,
   remoção dos dois slots e corpo gerado por descrição (`ogiZ0b` com
   `[entidade, [1]]`). Personagens de teste excluídos. Nenhum crédito gasto
   (saldo 827; gasto confirmado 345/500, contabilizado 352/500).

## 03/10/2026 — arquivamento nativo de ativos

1. `flow_delete_asset` usava o PATCH Aisandbox, sem bearer na conta migrada
   (`http_error`). Captura com envio bloqueado de "Mover para a lixeira" revelou
   `pGCYOe`: `[[[workflow, None, None, [None, None, 1], projeto]], [["metadata.archived"]]]`.
   O RPC foi incluído na lista de parâmetros explícitos do worker.
2. A listagem `Zzl0ze` continua trazendo o item arquivado, com `true` no terceiro
   campo dos metadados do workflow; `parse_assets` agora expõe `archived` e a
   confirmação lê essa marca. Envio único, sem reenvio automático.
3. Validado no Windows: o vídeo "Preparação MCP; envio bloqueado." foi arquivado
   (status `archived`). A exclusão definitiva usa `cz8Z4b` com o item já na lixeira
   (não exposta para ativos). Nenhum crédito gasto (saldo 827).
4. Nota de sondagem: um campo de texto errado (título do projeto) e um clique no
   personagem foram bloqueados pelo bloqueio de envios; usar a caixa de busca real.


- Geração por pedido do usuário (04/10/2026): Omni Flash 6s/720p/16:9 por texto na
  conta-ponte-a, cotação `abra_t2v_6s` 10 créditos, MP4 H.264/AAC 1280×720 6,016s
  decodificado integralmente. Duração 5s é recusada localmente (Omni aceita 4/6/8/10).
  Gasto: 355/500 confirmados, 362 contabilizados. Segunda conta `conta-b` conectada
  (saldo 1050), sem gasto.
- Edição a pedido do usuário (04/10/2026): mesmo workflow, Omni Flash `abra_edit`
  6s/720p, 20 créditos; MP4 decodificado. Gasto: 375/500 confirmados, 382 contabilizados.
- Edições a pedido do usuário (04/10/2026): mudança de comportamento (cachorro
  agressivo) por `abra_edit` não alterou a ação, apenas variação mínima; estilo
  cartoon por `abra_edit` 6s/720p, 20 créditos. Gasto: 395/500 confirmados,
  402 contabilizados.

- Edição Cuphead e sonda Lightpanda (04/10/2026): `conta-ponte-a` editou o vídeo
  original do cachorro (Omni Flash 6s/720p) em estilo Cuphead; cotação 20, saldo
  827→807, MP4 baixado em `downloads/61b895d3-6351-477d-bae4-fd399b02fe20.mp4`.
  Contabilizados 422/700. Lightpanda (nightly 1.1.0, branch `experimento/lightpanda`,
  `probe_lightpanda.py`) aceita cookies da conta-b (lidos do Chrome Windows por pipe)
  e renderiza o editor: com `wait_until="commit"` o reCAPTCHA Enterprise carrega em
  ~2-3 s e o editor aparece em ~10 s; RSS 13 MB ocioso, ~115 MB com o Flow. Pontos:
  `load`/`domcontentloaded` podem demorar >200 s; `wait_for_function` precisa de
  `polling=<ms>` (sem rAF); `--load-resources iframe|stylesheet|worker` desligado por
  padrão; a conta abre em modo Agent (clique DOM no chip resolve). Bloqueio: o
  compositor do gflow usa cliques Playwright, cujo check "estável" depende de
  requestAnimationFrame e hit-testing; no Lightpanda o clique expira (caixas 5x5).
  `execute()` direto do reCAPTCHA falha (site key não carregada) e já é marcado pelo
  site. Binário arm64 exige glibc 2.38; a Banana Pi (Ubuntu 20.04, glibc 2.31) não o
  executa. Geração/preparo completo via Lightpanda NÃO funciona sem reescrever o
  compositor com cliques DOM. Projeto de teste vazio na conta-b.
- Lightpanda, segunda rodada (04/10/2026, sem gasto, nada enviado): com polyfill de
  `requestAnimationFrame` (`add_init_script`) o check "estável" do Playwright passa;
  `Locator.click` trocado por `dispatch_event("click")` contorna o hit-testing. Com isso
  funcionam `_open_pane`, `_select(mode=videocam)` e `_close_pane` do gflow, e
  `page.route` bloqueia POST corretamente. Falta: entrada de texto no ProseMirror
  (`fill` recusa o contenteditable, `insert_text`/`keyboard.type` não inserem,
  `document.execCommand` não existe; `textContent` no `<p>` habilita o botão, mas o
  envio acaba em "Prompt must be provided" e o RPC de geração nunca sai). Sem isso o
  preparo (token reCAPTCHA no corpo do envio) não foi comprovado. Binário arm64
  exige glibc 2.38 (Banana Pi tem 2.31).
- Lightpanda, terceira rodada (04/10/2026, sem gasto, nada enviado): o reCAPTCHA
  Enterprise falhava porque `DOMTokenList.supports` lança TypeError para tokens de
  `sandbox` e `window.trustedTypes` não existe; polyfills via `add_init_script`
  (`supports=()=>false`, `trustedTypes` mínimo, `requestAnimationFrame` por setTimeout)
  registraram os clientes e `execute()` devolveu token. Com `Locator.click` por
  `dispatch_event`, texto no ProseMirror via `p.textContent` + evento `input`, painel
  de configurações/modo vídeo pelo gflow e `page.route` bloqueando POST, o app emitiu
  `YhhmEf` em ~3 s: projeto confere, token reCAPTCHA de ~2300 caracteres, cabeçalhos,
  `f.sid` e `at` presentes (conteúdo não registrado). O envio foi abortado. Falta
  provar que o Google aceita o token gerado no Lightpanda (exige um POST real, com
  custo) e integrar ao worker (cookies vêm do Chrome do Windows por pipe).
- Lightpanda, geração real (05/10/2026 UTC): `lightpanda_run.py` (adaptador
  `LightpandaBrowser` com a mesma interface de `FlowBrowser`, cookies por stdin) usou
  o `FlowHTTP`/`generate_video` reais. Cotação e geração passaram só com o preparo no
  Lightpanda; Omni Flash 4s/360p/16:9 por texto na conta-b: cotação 4, saldo 1050→1046,
  MP4 baixado em `downloads/8e150ab7-a3cf-4f57-868d-d995c7990ed1.mp4`, ~62 s no total
  (cotação ~19 s). Primeira tentativa parou em `failed_pre_submit` (fill de
  contenteditable), sem envio e sem gasto. Ressalvas: UA `Lightpanda/x` (o binário proíbe
  UA com "Mozilla"), cookies ainda vêm do Chrome do Windows, sem perfil persistente e
  sem Banana Pi (glibc). Contabilizados 426/700.

- Deploy na Banana Pi (05/10/2026): Banana Pi M5, Ubuntu 20.04 aarch64, kernel 4.9,
  `pi@192.168.0.52` (chave `id_ed25519_win`). Tudo no SSD em `/mnt/ssd/flow-mcp/`
  (`app/` código da main via `git archive`, `venv/`, `python/`, `cache/`, `browsers/`,
  `home/` perfis, `env.sh`, `run-mcp.sh`); o cartão SD tem ~680 MB livres, não usar.
  `uv` 0.12 + Python 3.11 e Chromium 149 do Playwright (glibc 2.25 ok); apt: libs
  gráficas, `xvfb`, `xauth`. `CHROME_BINARY` em `env.sh`. Chromium abre sem
  `--no-sandbox` (0,7–5,6 s), carrega o Flow em 2–5 s, ~730–930 MB RSS somados.
  Sessões: cookies lidos do Chrome Windows (filtrados para DOMAINS, formato da
  extensão) e enviados por pipe SSH para arquivo 0600 no SSD, importados e apagados.
  `flow_session.py import` trava no seletor de contas sem usuário (Xvfb); usado um
  importador direto que troca só a etapa do seletor. `verify_flow_profile` retorna
  `google_session_only` no Linux mesmo com a sessão válida (screenshot do Flow
  logado, selo PRO); o teste confiável é o saldo HTTP do worker: conta-b 1046 e
  conta-ponte-a 1050 na Banana Pi, iguais ao Windows (1050 = reinício mensal).
  `.gflow_account` gravado manualmente. MCP via SSH: `/mnt/ssd/flow-mcp/run-mcp.sh`,
  64 ferramentas. Sem gasto de créditos neste deploy; estabilidade prolongada e
  durabilidade da sessão (Google pode revogar cookies em outro dispositivo) pendentes.
- Repositório (05/10/2026): GitHub privado `LucasGazula/google-flow-mcp` (main);
  experimento Lightpanda na branch `experimento/lightpanda`. Servidor registrado como
  `google-flow` no Claude Code (escopo usuário), Antigravity CLI e Codex, executando
  no Windows via `powershell.exe` (`.venv-windows`).
