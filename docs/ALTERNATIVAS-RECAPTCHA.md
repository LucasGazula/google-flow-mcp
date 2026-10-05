# Alternativas para reduzir a dependência do reCAPTCHA

Pesquisa em 30/09/2026, sem geração, contratação de solver ou alteração
do caminho de produção. A sonda local reutilizou a sessão dedicada existente;
nenhuma credencial foi registrada no relatório ou enviada a um solver.
Objetivo: usar a conta e os créditos do Flow para gerar
imagens e vídeos com menos intervenção e menos aberturas do Chrome.

## Conclusão

Atualização após a pesquisa: Chrome headless residente foi implementado e passou
na geração/download/recuperação de imagem e vídeo no Windows, usando o mesmo
contexto. O preparo normal permanece; reCAPTCHA não foi removido. Consulte o
registro mais recente em [IMPLEMENTACAO-FLOW.md](IMPLEMENTACAO-FLOW.md).
O restante deste relatório registra a evidência disponível durante a pesquisa.

O próximo caminho mais sustentado pela evidência local é **reutilizar um navegador
autenticado, com preparo pelo fluxo normal do site**, em vez de abri-lo e fechá-lo
para cada geração. Isso reduz a fricção; não elimina a verificação do Google.
Um navegador num computador próprio remoto também pode atender o MCP, mas continua
existindo e exige validação da comunicação e do ciclo da sessão.

Não encontramos comprovação, para esta conta e o protocolo atual, de uma opção que
elimine reCAPTCHA e preserve os créditos Flow. Isso é uma ausência de validação,
não uma prova de impossibilidade. Solvers externos são candidatos documentados;
suporte a Enterprise v3 não comprova aceitação pelo Flow.

## O que já funciona neste projeto

O diário [IMPLEMENTACAO-FLOW.md](IMPLEMENTACAO-FLOW.md) registra geração e download
HTTP de imagens, edição e quatro modos de vídeo. Chrome prepara autenticação e
reCAPTCHA pelo fluxo normal; seu envio é abortado, ele fecha, e Python envia um
único pedido real. Consultas HTTP reutilizam a sessão em memória. A última consulta
sem gasto retornou 942; o gasto registrado permanece 148/500 créditos.

Chamadas diretas a `enterprise.execute` produziram marcação pelo frontend e RPC 7.
Elas não devem ser repetidas conforme AGENTS.md. A extensão local captura cookies
com ação do usuário; não é uma ponte residente de geração comprovada. Sessão
portátil, geração sem navegador e reutilização contínua de Chrome na geração
continuam pendentes.

Experimento local adicional no Windows em 30/09/2026: um mesmo contexto Chrome
residente preparou `IMAGE_GENERATION` e `VIDEO_GENERATION` pelo fluxo normal de
`FlowHTTP.prepare`, em duas páginas sucessivas. Ambos retornaram token; os envios
de geração foram abortados e nenhum `send_submit` foi executado. Houve uma abertura
separada anterior para consultar/selecionar projeto; a contagem de uma abertura
refere-se apenas à etapa dos dois preparos. Isso comprova reutilização do contexto
para preparar, ainda não aceitação em geração real, estabilidade prolongada ou
remoção do CAPTCHA. Sonda local ignorada: `.probe_session_resident.py`.

O Google documenta tokens de uso único, expiração em dois minutos e avaliação
servidora de validade/score; recomenda contexto adicional como ação, IP e agente
do navegador. Portanto sessão persistente não significa token de geração
reutilizável. Não sabemos quais sinais o backend do Flow efetivamente confere.
[Google: avaliações de reCAPTCHA](https://docs.cloud.google.com/recaptcha/docs/create-assessment-website).

## Comparação

| Alternativa | Créditos Flow | Navegador/verificação | Evidência e limite |
|---|---|---|---|
| Chrome residente + fluxo normal do Flow | Preserva | Continua, sem abrir por pedido | Dois preparos normais no mesmo contexto comprovados; envio real nesse ciclo e estabilidade ainda pendentes |
| Navegador residente em computador próprio remoto | Preserva em princípio | Continua no host remoto | Hipótese de organização; não comprova portabilidade de cookies para Raspberry |
| Extensão como ponte para aba autenticada | Preserva em princípio | Aba e verificação continuam | Flow Kit implementa ponte; seu mecanismo interfere em scripts de reCAPTCHA, não copiar sem análise |
| 2Captcha, Anti-Captcha ou CapSolver | Em princípio, se Flow aceitar | Token vem de serviço externo; login continua necessário | Enterprise v3 documentado; aceitação real pelo Flow não demonstrada neste repo; cobrança adicional |
| Trocar por flow2api | Projetado para conta Flow | Modos browser/personal ou solver | Protocolo atual presente upstream; não substitui validação local nem elimina dependência automaticamente |
| Trocar por gflow-cli/flow-mcp | Projetado para conta Flow | Geração ainda depende de navegador nas implementações consultadas | Não fornece prova de solução sem navegador para nossa conta |
| Gemini API oficial | Não usa o saldo Flow | API autenticada para modelos disponíveis | Cobrança API separada; resolve outro contrato de geração |

## Implementações públicas: o que realmente dizem

**gflow-cli correto:** a distribuição 0.79.1 pertence a `ffroliva/gflow-cli`;
há outro projeto homônimo em `swissmarley`, que não deve ser confundido com a
dependência deste repo. A documentação atual de autenticação do ffroliva descreve
Chrome visível como transporte de produção e Xvfb para ambiente sem monitor.
A rejeição de headless descrita ali é observação upstream, não impossibilidade
universal. Atualizar a versão por si só não demonstra remoção do reCAPTCHA.
[Distribuição fixada](https://pypi.org/project/gflow-cli/0.79.1/),
[autenticação upstream](https://github.com/ffroliva/gflow-cli/blob/develop/docs/AUTHENTICATION.md).

**flow2api:** o README oferece navegador `browser`/`personal`, solvers e extensão
para atualizar login. A inspeção do commit
`760f7155e8d4afcef8db6ad46f4fce4c5221c25e` encontrou URLs `flow.google.com`, bootstrap
`/projects` e cliente declarado sobre a camada RPC atual: não é correto descartá-lo
como exclusivamente legado. Também há chamadas diretas a `enterprise.execute`;
esse detalhe conflita com o caminho rejeitado e proibido de repetir localmente.
O projeto é evidência de abordagens existentes, não de êxito com nossa conta.
[README](https://github.com/TheSmallHanCat/flow2api/blob/main/README.md),
[cliente no commit consultado](https://github.com/TheSmallHanCat/flow2api/blob/760f7155e8d4afcef8db6ad46f4fce4c5221c25e/src/services/flow_client.py),
[navegador personal no mesmo commit](https://github.com/TheSmallHanCat/flow2api/blob/760f7155e8d4afcef8db6ad46f4fce4c5221c25e/src/services/browser_captcha_personal.py).

**flow-mcp, alarconcesar:** anuncia pool persistente e geração headless. Porém o
`generator.py` consultado em `master` ainda contém `labs.google/fx/tools/flow` e
`aisandbox-pa.googleapis.com/v1/projects`; isso enfraquece sua aplicação à conta
migrada. O pool realmente abre navegador headless: headless não significa ausência
de navegador. Não adotamos sua promessa de ausência de limites de quota.
[README](https://github.com/alarconcesar/flow-mcp),
[gerador](https://github.com/alarconcesar/flow-mcp/blob/master/src/flow_mcp/generator.py),
[pool](https://github.com/alarconcesar/flow-mcp/blob/master/src/flow_mcp/browser_pool.py).

**Flow Kit:** declara migração para `flow.google.com`/`batchexecute` em setembro,
com extensão e aba autenticada residente. Mas o manifesto carrega
`hijack_bypass.js` e scripts de substituição de reCAPTCHA no contexto principal da
página; não é somente reaproveitamento passivo de sessão. Sua afirmação de que
pedidos não podem sair do navegador contradiz a geração HTTP já comprovada aqui,
assim como a exigência de projeto preexistente não invalida nossa criação HTTP
validada. Essas são limitações/afirmações da implementação upstream.
[README](https://github.com/crisng95/flowkit),
[manifesto](https://github.com/crisng95/flowkit/blob/main/extension/manifest.json).

## Solvers: suporte não equivale a compatibilidade

**2Captcha:** documenta reCAPTCHA v3 Enterprise com tarefa proxyless, ação e score
solicitado. Entrega token; não autentica a conta Flow nem garante que o backend
aceitará seu contexto. O custo do serviço é adicional ao consumo Flow; não foi
contratado nem medido. [Documentação](https://2captcha.com/api-docs/recaptcha-v3).

**Anti-Captcha:** documenta Enterprise dentro da tarefa v3 e filas por score,
com processamento em IPs próprios/dos trabalhadores e agente do navegador no
resultado. Isso explicita contexto diferente do nosso host; impacto no Flow é
desconhecido. Preço varia com fila, sem cotação nesta pesquisa.
[Documentação](https://anti-captcha.com/apidoc/task-types/RecaptchaV3TaskProxyless).

**CapSolver:** documenta Enterprise v3, modalidades com/sem proxy e modo de sessão.
Sua própria referência avisa que variantes M1 exigem adaptação por site e podem
funcionar bem somente em alguns sites, com custo maior. Nenhum desses mecanismos
foi testado localmente; não há garantia de eliminar Chrome/renovação de login.
[Documentação](https://docs.capsolver.com/en/guide/captcha/ReCaptchaV3/).

## Alternativa oficial e próximos critérios

Gemini API oferece um contrato oficial para geração programática nos modelos
disponíveis, mas os benefícios Google AI na interface AI Studio e a cobrança API
são separados; Google One AI credits são outro sistema. Portanto mudar para a API
não consome os 942 créditos observados no Flow. Eventuais créditos Cloud do Google
Developer Program também não são esse saldo.
[Google AI plans](https://ai.google.dev/gemini-api/docs/google-ai-plans).

Prioridade local: investigar a reutilização do preparo normal do Flow em navegador
residente, preservando envio único, orçamento por catálogo, recuperação sem reenvio,
isolamento de conta e segredos somente em memória. Uma opção só deve ser promovida
a funcional após geração de imagem e vídeo no protocolo atual, download confirmado,
conferência do gasto e observação de que não houve pedido duplicado. A pesquisa
não executou esses testes e não promete operação sem CAPTCHA.
