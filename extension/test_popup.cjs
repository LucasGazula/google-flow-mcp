// Verifica que a extensão só lê cookies após clique válido e só envia ao loopback.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const source = fs.readFileSync(__dirname + "/popup.js", "utf8");
async function run(url) {
  let click;
  let reads = 0;
  let sent;
  const status = {};
  const button = {addEventListener: (_, fn) => {click = fn;}};
  vm.runInNewContext(source, {
    document: {querySelector: selector => selector === "#connect" ? button : status},
    chrome: {
      tabs: {query: async () => [{url}]},
      cookies: {getAll: async () => {reads++; return [{name: "fixture", value: "test-only",
        domain: ".google.com", path: "/", storeId: "0"}];}}
    },
    URL, AbortSignal,
    fetch: async (url, options) => {sent = {url, options}; return {ok: true};}
  });
  assert.equal(reads, 0);
  await click();
  return {reads, sent, status};
}
(async () => {
  const token = "a".repeat(64);
  for (const url of ["https://attacker.test/pair#" + token,
                    "http://127.0.0.1:1234/other#" + token,
                    "http://127.0.0.1:1234/pair#invalid",
                    "http://attacker.test:1234/pair#" + token]) {
    const result = await run(url);
    assert.equal(result.reads, 0);
    assert.equal(result.sent, undefined);
  }
  const result = await run("http://127.0.0.1:1234/pair#" + token);
  assert.equal(result.reads, 5);
  assert.equal(result.sent.url, "http://127.0.0.1:1234/session");
  assert.equal(result.sent.options.headers["X-Flow-Pairing"], token);
  assert.equal(result.sent.options.redirect, "error");
  assert.equal(JSON.parse(result.sent.options.body).cookies.length, 1);
  assert.match(result.status.textContent, /Sessão enviada/);
  console.log("Extensão: clique explícito, destino local e pareamento verificados.");
})().catch(error => {console.error(error); process.exitCode = 1;});
