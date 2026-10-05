# Autenticação no PC e operação no Raspberry Pi

Requisito solicitado em 29/09/2026: o usuário usa Chrome no Windows; quer autenticar no computador, importar credenciais no Raspberry Pi e usar duas contas localmente, sem desktop permanente. Implementação experimental de captura por extensão e importação de cookies disponível; nenhuma sessão real foi transferida ao Raspberry ou validada com essa ponte.

## O que é transportável

No 9router, as integrações Gemini/Antigravity examinadas usam OAuth Google com access token e refresh token. O refresh token permite obter novos access tokens para o serviço e as permissões autorizadas. Isso explica a experiência de conectar uma conta e reutilizar suas credenciais no roteador; não comprova acesso ao Flow com as mesmas permissões. [Serviço Antigravity](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/src/lib/oauth/services/antigravity.js#L20), [renovação](https://github.com/decolua/9router/blob/f01fb909e37189008080632ddaf404f096345cde/open-sse/services/tokenRefresh/providers.js#L202).

A base Flow gflow-cli examinada opera perfis persistentes de Chromium/Chrome. O perfil inclui cookies, IndexedDB e armazenamento local; sua documentação não apresenta o mesmo login OAuth renovável do 9router como contrato Flow. [Perfil e autenticação](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/docs/AUTHENTICATION.md#L81).

Playwright permite salvar e restaurar estado autenticado, incluindo cookies e armazenamento local; IndexedDB exige a opção apropriada. O próprio guia ressalta que o conjunto necessário depende do modelo de autenticação da aplicação e que sessionStorage pode exigir tratamento separado. Esse recurso é um candidato para testar importação entre ambientes, não garantia de que a sessão Google/Flow será aceita no destino. [Estado autenticado](https://playwright.dev/python/docs/auth).

## Por que copiar a pasta do Chrome não basta como contrato

O Chrome no Windows protege cookies em disco com mecanismos ligados ao sistema e à aplicação; App-Bound Encryption liga a chave à máquina. O Google aponta expressamente incompatibilidade com perfis que transitam entre computadores nesse regime. Portanto, copiar diretamente a pasta Windows para Linux/ARM não estabelece uma sessão reutilizável. Uma exportação suportada pelo contexto do navegador é um mecanismo diferente de copiar arquivos cifrados em disco. [Chrome: proteção dos cookies Windows](https://security.googleblog.com/2024/07/improving-security-of-chrome-cookies-on.html).

Além da proteção em disco, DBSC pode vincular a renovação da sessão a uma chave do dispositivo. A fonte oficial descreve sua disponibilidade no Chrome Windows e renovação condicionada a prova de posse da chave. Não verificamos se as sessões Flow do usuário utilizam DBSC. Se utilizarem, a importação de cookies pode não sustentar autenticação no novo dispositivo. [Sessões vinculadas ao dispositivo](https://blog.google/security/protecting-cookies-with-device-bound-session-credentials/).

Não alterar proteções do Chrome para tornar uma sessão exportável. Se a sessão não for portátil, a alternativa operacional é autenticar no navegador que executará no Raspberry e visualizar temporariamente esse login a partir do computador do usuário.

## Experiência proposta

1. Criar um perfil dedicado por conta e abrir login assistido no computador escolhido.
2. Verificar que a identidade e o acesso ao Flow correspondem à conta cadastrada.
3. Se o teste de portabilidade funcionar, exportar estado necessário por um utilitário local para arquivo privado e importá-lo no destino. Utilizar APIs do contexto autorizado; não extrair segredos de perfis alheios ou inserir credenciais em respostas MCP.
4. Validar a sessão importada no Raspberry antes de habilitar geração, verificando autenticação, interface e opções disponíveis. Registrar apenas estado, identidade/apelido necessário e horário da verificação.
5. Manter sessão/perfil no Raspberry. Se a sessão expirar ou exigir nova autenticação, apresentar `needs_login` e reabrir login assistido. Não anunciar renovação automática OAuth sem suporte verificado para Flow.

Há agora comandos experimentais `flow_session.py export <apelido>` e `flow_session.py import <apelido> --file <arquivo>`, além do pareamento e conclusão por MCP. Eles capturam cookies, não o armazenamento completo do navegador. Veja [segurança da extensão](SEGURANCA-EXTENSAO.md). As respostas ao agente devem conter status da conta e da validação; os tokens, cookies e o arquivo de sessão permanecem sob controle local do usuário, fora de Git, logs e AI Memory.

Se importação não funcionar, o usuário pode abrir remotamente a sessão de navegador executada no Raspberry, completar o login ali e manter o perfil naquele dispositivo. Nesse caminho, a sessão nasce no destino; não depende de transportar cookies do Windows. A tecnologia de acesso remoto será escolhida apenas quando essa execução for necessária.

## Sem interface gráfica permanente

O gflow-cli documenta geração com navegador headed, inclusive limitações que encontrou em execução headless. Isso é relato do mantenedor, não teste nosso. Um Raspberry sem monitor pode fornecer tela virtual para esse navegador; Playwright documenta uso de Xvfb no Linux e distros Debian/Ubuntu ARM64 entre seus ambientes suportados. [Limitação da base](https://github.com/ffroliva/gflow-cli/blob/488dcc1b80ba935ef204b60ea9335c43614dca84/docs/AUTHENTICATION.md#L490), [Xvfb](https://playwright.dev/python/docs/ci#running-headed), [requisitos Linux/ARM64](https://playwright.dev/python/docs/intro#system-requirements).

Suporte Playwright em ARM64 não prova que uma release fixada do gflow-cli encontrará um navegador adequado nem que o Flow aceitará a sessão. Esses pontos precisam ser medidos no sistema de destino.

## Primeiro experimento necessário

Validar a base no Windows com um perfil dedicado; identificar estado necessário à sessão; testar importação num Linux suportado sem geração paga; verificar login após reinício e expiração. Depois testar no Raspberry real e, com um pedido concreto autorizado, validar geração e download. Sessão verificada sem geração não prova compatibilidade com a etapa de geração.

O inventário de recursos e o plano multi-conta podem avançar enquanto esse experimento é preparado. Autenticação portátil deve ser anunciada somente após esse resultado.
