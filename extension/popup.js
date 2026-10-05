const button = document.querySelector("#connect");
const status = document.querySelector("#status");

// Nenhuma leitura de cookies na inicialização ou em segundo plano.
button.addEventListener("click", async () => {
  button.disabled = true;
  status.textContent = "Conectando…";
  try {
    const [tab] = await chrome.tabs.query({active: true, currentWindow: true});
    const target = new URL(tab.url);
    const token = target.hash.slice(1);
    if (target.protocol !== "http:" || target.hostname !== "127.0.0.1" ||
        !target.port || target.pathname !== "/pair" || target.username || target.password ||
        !/^[a-f0-9]{64}$/.test(token)) {
      throw new Error("Abra a aba de pareamento do MCP e clique na extensão nessa aba.");
    }
    const groups = await Promise.all([
      "https://google.com/", "https://www.google.com/", "https://accounts.google.com/",
      "https://labs.google/", "https://flow.google.com/"
    ].map(url => chrome.cookies.getAll({url})));
    const cookies = new Map();
    for (const cookie of groups.flat()) {
      if (cookie.partitionKey) continue;
      cookies.set(`${cookie.domain}|${cookie.path}|${cookie.name}`, cookie);
    }
    if (!cookies.size) throw new Error("Nenhum cookie Google encontrado neste perfil.");
    const response = await fetch(`${target.origin}/session`, {
      method: "POST", credentials: "omit", redirect: "error", cache: "no-store",
      headers: {"Content-Type": "application/json", "X-Flow-Pairing": token},
      body: JSON.stringify({cookies: [...cookies.values()]}),
      signal: AbortSignal.timeout(10000)
    });
    if (!response.ok) throw new Error("Pareamento recusado ou expirado. Reinicie a conexão no MCP.");
    status.textContent = "Sessão enviada. Volte ao agente e diga: conectei.";
  } catch (error) {
    // Mensagens HTTP/payload nunca são exibidas; não há console ou armazenamento.
    status.textContent = error instanceof TypeError ? "Não foi possível conectar ao MCP local." :
      error.name === "TimeoutError" ? "A conexão demorou demais. Reinicie o pareamento." : error.message;
    button.disabled = false;
  }
});
