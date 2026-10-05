# Revisão da extensão e ponte de sessões

Revisão de código em 29/09/2026, limitada ao commit
`6826452a4a2e93bf7313d1be1626a9034fd7dc27` da base
[miyakejima/google-flow-mcp](https://github.com/miyakejima/google-flow-mcp/tree/6826452a4a2e93bf7313d1be1626a9034fd7dc27).
Não é auditoria independente do projeto inteiro, das dependências ou da conta real.

## Resultado da revisão original

A [extensão](https://github.com/miyakejima/google-flow-mcp/tree/6826452a4a2e93bf7313d1be1626a9034fd7dc27/extension)
usa Manifest V3, permissão `cookies` e hosts Google/loopback. Os cookies só são
lidos no clique do usuário. Não encontrei scripts remotos, leitura de senhas,
telemetria ou envio a servidores externos nesses arquivos examinados.

A [ponte](https://github.com/miyakejima/google-flow-mcp/blob/6826452a4a2e93bf7313d1be1626a9034fd7dc27/src/cookie-bridge.ts)
limita o listener a `127.0.0.1`, tamanho do corpo, quantidade e domínios dos cookies.
Isso reduz a exposição, mas há limites concretos:

- O POST aceita qualquer origem de extensão e também ausência de Origin. Não
  exige uma chave no envio; o `connectionId` protege outra etapa do MCP.
- O POST não exige que uma conexão esteja armada. Outro processo local pode
  colocar uma sessão na fila ou substituí-la antes de sua utilização.
- A extensão encontra serviços por portas conhecidas e pelo JSON `/status`.
  Um serviço local que imite esse protocolo pode receber os cookies no clique.
- Cookies de `google.com` incluem autenticação compartilhada com outros serviços
  Google e podem representar várias contas. Eles não são uma credencial restrita
  à geração de vídeos.

Esses são riscos de implementação observados no código, não evidência de ataque
ou de intenção maliciosa. Não classifico a base inteira como “segura” com essa
revisão parcial. O código possui licença MIT; nossa implementação é própria,
baseada no mesmo fluxo e nas APIs documentadas do navegador.

## Implementação deste projeto

- Captura explícita no clique, sem background, content scripts ou leitura de senhas.
- Hosts limitados a Google principal, accounts, www, labs e flow, além de loopback.
  Cookies específicos de Gmail e outros subdomínios não entram no payload.
- Uma aba aberta pelo MCP entrega uma chave aleatória de pareamento no fragmento
  da URL. Ela não é retornada ao agente, colocada no HTML ou enviada como URL HTTP.
- A ponte usa porta dinâmica, aceita somente `127.0.0.1` e valida Host, Origin e chave.
- A chave é válida por cinco minutos e aceita uma única sessão. Nova captura
  exige novo pareamento; reiniciar o processo perde o pareamento anterior.
- Payload limitado a 1 MiB e 1000 cookies; domínio, caminho, expiração, atributos
  e duplicatas são validados. Cookies particionados não são suportados.
- Cookies permanecem em memória na ponte e seguem para o worker por stdin.
  Não são retornados pelo MCP, nem registrados em logs ou AI Memory.
- O navegador habitual só fornece a sessão; a automação usa perfil dedicado.
  A importação abre o seletor Google e aguarda a ação humana. O diagnóstico
  subsequente consulta a sessão no servidor; não comprova suporte à geração.
- Perfis já identificados como conectados não são substituídos automaticamente.
  A aprovação de gastos do Flow permanece sob controle do usuário. No Windows,
  a importação recusa gravar cookies em um perfil sem proteção por ACL.

O pareamento protege nossa ponte contra envios sem a chave. Ele não certifica
criptograficamente um serviço local para a extensão: use a aba aberta pelo MCP.
Um processo malicioso executado como o mesmo usuário pode observar navegador,
memória e arquivos; este mecanismo não elimina comprometimento da máquina.
A extensão tem acesso sensível à sessão Google, mesmo sem conhecer a senha.

Se uma importação for interrompida por encerramento abrupto do processo, pode
restar `.flow_session_import.lock` no perfil. Use outro apelido ou remova esse
arquivo somente após confirmar que a importação e o navegador terminaram. Não
há recuperação automática desse guard; ele evita duas importações simultâneas.

## Raspberry Pi e arquivos

`flow_session.py export <apelido>` captura via extensão no PC e cria um arquivo
em `exports/`. Esse arquivo contém cookies em texto claro, é ignorado pelo Git
e usa modo 0600/0700 no POSIX ou diretório protegido por ACL no Windows. Se a
proteção do diretório Windows falhar, a exportação é recusada. A exportação é
explícita; conectar uma conta não cria esse arquivo.

Transfira o arquivo por um canal protegido, como SSH/SCP, e execute
`flow_session.py import <apelido> --file <arquivo>` no destino. Não cole o arquivo
na conversa. Apague as cópias de transporte após validar a sessão. O utilitário
não apaga automaticamente o arquivo fornecido pelo usuário.

A extensão não precisa estar instalada no Raspberry nesse caminho. O destino
precisa de Chrome/Chromium e uma tela física, virtual ou remota para selecionar
conta e lidar com verificações. `FLOW_MCP_HOME` configura o local dos perfis.

A captura contém cookies, não IndexedDB, localStorage, passkeys ou chaves do
dispositivo. A [documentação Playwright](https://playwright.dev/python/docs/auth)
explica que o estado necessário depende da aplicação. Uma sessão válida no PC
pode ser recusada ou expirar no Raspberry. Importação, renovação, ARM64 e geração
continuam sem validação real; se necessário, faça login diretamente no destino.

## Verificação realizada

Testes stdlib exercitam a ponte HTTP com cookies fictícios: envio sem chave,
origem web, Host indevido, corpo excessivo, dados inválidos, envio válido,
reutilização e expiração. A importação é testada com navegador simulado,
verificando perfil dedicado, seletor Google e proteção contra substituição.

`node extension/test_popup.cjs` verifica que não há leitura na inicialização,
que destinos fora do pareamento não recebem cookies e que um clique válido
usa loopback, chave e rejeição de redirecionamentos. Esses testes não substituem
instalação da extensão e validação com as contas reais do usuário.
