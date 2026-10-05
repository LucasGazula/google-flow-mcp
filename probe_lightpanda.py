"""Sonda experimental: cookies da conta (só em memória/pipe) -> Lightpanda via CDP. Não gera nada.
Windows:  python probe_lightpanda.py dump <conta>   (JSON no stdout)
WSL:      ... | python probe_lightpanda.py probe     (lê cookies do stdin)"""
import asyncio, json, sys
from playwright.async_api import async_playwright

from playwright.async_api import Locator
async def _dom_click(self, **kw):
    # ponytail: sem layout no Lightpanda; clique por evento DOM em vez de coordenadas.
    return await self.dispatch_event("click", timeout=kw.get("timeout", 5000))
Locator.click = _dom_click

async def dump(account):
    from flow_browser import FlowBrowser
    fb = FlowBrowser(account, headless=True)
    try:
        async with fb.page() as p:
            await p.goto("https://flow.google.com", wait_until="domcontentloaded", timeout=25000)
            print(json.dumps(await fb.context.cookies()))
    finally:
        await fb.close()

async def probe(project):
    import time
    cookies = json.load(sys.stdin)
    async with async_playwright() as pw:
        b = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        ctx = b.contexts[0] if b.contexts else await b.new_context()
        first = True
        for i in range(int(sys.argv[3]) if len(sys.argv) > 3 else 3):
            pg = await ctx.new_page()
            await pg.add_init_script("window.requestAnimationFrame = cb => setTimeout(() => cb(performance.now()), 16); window.cancelAnimationFrame = id => clearTimeout(id);"
                                   "try { DOMTokenList.prototype.supports = function() { return false; }; } catch (e) {} "
                                   "if (!window.trustedTypes) { const mk = n => ({name: n, createHTML: s => s, createScript: s => s, createScriptURL: s => s}); window.trustedTypes = {createPolicy: (n, p) => Object.assign(mk(n), p || {}), isHTML: () => false, isScript: () => false, isScriptURL: () => false, emptyHTML: '', emptyScript: '', defaultPolicy: null, getAttributeType: () => null, getPropertyType: () => null}; }")
            if first:
                await ctx.add_cookies(cookies); first = False
            print("page", i, flush=True)
            print("  viewport antes:", await pg.evaluate("[innerWidth, innerHeight, matchMedia('(min-width: 1024px)').matches]"), flush=True)
            try:
                await pg.set_viewport_size({"width": 1440, "height": 900})
                print("  viewport depois:", await pg.evaluate("[innerWidth, innerHeight, matchMedia('(min-width: 1024px)').matches]"), flush=True)
            except Exception as e:
                print("  set_viewport FALHOU:", str(e)[:150], flush=True)
            T0 = time.monotonic()
            t0 = time.monotonic()
            try:
                await asyncio.wait_for(pg.goto("https://flow.google.com/project/" + project, wait_until="commit", timeout=45000), 60)
                await pg.wait_for_function("window.grecaptcha && window.grecaptcha.enterprise", timeout=30000, polling=200)
                t1 = time.monotonic() - t0
                await asyncio.sleep(10)
                print('  apos 10s: editor', await pg.locator('[contenteditable=true]').count(), 'texto', await pg.evaluate('document.body.innerText.length'), flush=True)
                ed = pg.locator("[contenteditable=true]").first
                print("  editor visible:", await ed.is_visible(), "bbox:", await ed.bounding_box(), flush=True)
                print("  texto:", (await pg.evaluate("document.body.innerText")).replace("\n"," | ")[:350], flush=True)
                print("  ancestrais:", await pg.evaluate("""() => { let t=document.querySelector('.settings-trigger-button'); const o=[]; while(t && o.length<12){ const cs=getComputedStyle(t); o.push(t.tagName.toLowerCase()+':'+cs.display); t=t.parentElement } return o.join(' < ') }"""), flush=True)
                print("  folhas de estilo:", await pg.evaluate("[document.styleSheets.length, document.querySelectorAll('link[rel=stylesheet]').length, document.querySelectorAll('style').length]"), flush=True)
                await pg.evaluate("(document.querySelector(\"button.agent-mode-chip[aria-pressed='true']\")||{click(){}}).click()")
                await asyncio.sleep(3)
                print("  painel agent presente:", await pg.locator("flow-agent-panel").count(), "| trigger display:", await pg.evaluate("(()=>{const t=document.querySelector('.settings-trigger-button');return t?getComputedStyle(t).display:'ausente'})()"), flush=True)
                from gflow_cli.api.transports.migrated_composer import MigratedComposer
                comp = MigratedComposer()
                try:
                    pane = await asyncio.wait_for(comp._open_pane(pg), 40)
                    print("  _open_pane OK", flush=True)
                    await comp._select(pg, pane, axis="mode", lig="videocam")
                    print("  _select modo video OK", flush=True)
                    await comp._close_pane(pg, strict=False)
                    print("  _close_pane OK", flush=True)
                except Exception as e:
                    print("  _open_pane FALHOU:", type(e).__name__, str(e)[:250].replace("\n"," "), flush=True)
                async def estado():
                    return await pg.evaluate("""() => { const b=[...document.querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'').includes('Start generation')||b.innerText.includes('arrow_forward'));
                        return JSON.stringify({texto: document.querySelector('[contenteditable=true]').innerText.trim().slice(0,40), gerar_disabled: b ? (b.disabled || b.getAttribute('aria-disabled')) : 'sem botao'}) }""")
                print("  antes:", await estado(), flush=True)
                print("  chaves proprias do editor:", await pg.evaluate("""() => { const e=document.querySelector('[contenteditable=true]'); const ks=Object.getOwnPropertyNames(e).filter(k=>!['__proto__'].includes(k)); return JSON.stringify({own: ks.slice(0,30), editor: typeof e.editor, pmViewDesc: typeof e.pmViewDesc, view: e.pmViewDesc ? Object.keys(e.pmViewDesc).slice(0,15) : null, sel: (()=>{try{return typeof getSelection().rangeCount}catch(x){return 'erro'}})()}) }"""), flush=True)
                await pg.evaluate("""() => { const e=document.querySelector('[contenteditable=true]'); e.focus();
                    const p=e.querySelector('p'); p.textContent='teste de preparo; nao enviar';
                    try { const r=document.createRange(); r.selectNodeContents(p); r.collapse(false); const s=getSelection(); s.removeAllRanges(); s.addRange(r); } catch(x) {}
                    e.dispatchEvent(new InputEvent('input',{inputType:'insertText',data:'teste',bubbles:true}));
                    e.dispatchEvent(new KeyboardEvent('keyup',{key:'e',bubbles:true})); }""")
                await asyncio.sleep(1.5)
                print("  apos texto+input:", await estado(), flush=True)
                pg.on("console", lambda m: print("    [console]", m.type, m.text[:160].replace("\n"," "), flush=True) if m.type in ("error", "warning") else None)
                try:
                    submit = await asyncio.wait_for(comp._pre_submit_gate(pg), 30)
                    print("  _pre_submit_gate OK", flush=True)
                    import json as _j
                    from urllib.parse import parse_qs, urlsplit
                    found = asyncio.get_running_loop().create_future()
                    async def block(route):
                        r = route.request; u = urlsplit(r.url)
                        if r.method in ("GET", "HEAD") or (u.hostname in ("www.google.com", "www.recaptcha.net") and u.path.startswith("/recaptcha/")):
                            return await route.continue_()
                        try:
                            print(f"    [bloqueado] {r.method} {r.url.split('?')[0][-50:]}", flush=True)
                            if "batchexecute" in r.url:
                                env = _j.loads(parse_qs(r.post_data or "").get("f.req", ["[]"])[0])
                                calls = [c for batch in env for c in batch]
                                ids = [c[0] for c in calls]
                                print("      rpcs:", ids, [c[1][:260] for c in calls], flush=True)
                                gen = [c for c in calls if c[0] in ("MZZa6b", "ogiZ0b", "YhhmEf", "jIps6", "eb1hJf", "nprQif")]
                                if gen and not found.done():
                                    par = _j.loads(gen[0][1])
                                    ctx_ = par[1]
                                    tok = ctx_[10][0]
                                    hdr = sorted(k.lower() for k in r.headers)
                                    found.set_result({"rpc": gen[0][0], "n_calls": len(calls), "projeto_confere": ctx_[5] == sys.argv[2], "token_len": len(tok) if isinstance(tok, str) else None, "token_prefixo_ok": isinstance(tok, str) and tok[:2] in ("03", "0c", "0a", "0d"), "headers": hdr, "tem_f_sid": "f.sid=" in r.url, "tem_at": "at=" in (r.post_data or "")})
                        except Exception as ex:
                            if not found.done(): found.set_exception(ex)
                        finally:
                            await route.abort()
                    await pg.route("**/*", block)
                    t3 = time.monotonic()
                    print("  estado antes do clique:", await estado(), "| 'Prompt must' ja na pagina:", "Prompt must be provided" in await pg.evaluate("document.body.innerText"), flush=True)
                    await submit.click(timeout=5000)
                    await asyncio.sleep(3)
                    print("  estado 3s depois:", await estado(), "| texto pagina:", (await pg.evaluate("document.body.innerText")).replace("\n"," | ")[-250:], flush=True)
                    cap = await asyncio.wait_for(found, 25)
                    print(f"  ENVIO CAPTURADO (e abortado) em {time.monotonic()-t3:.1f}s:", cap, flush=True)
                except Exception as e:
                    print("  _pre_submit_gate FALHOU:", type(e).__name__, str(e)[:250].replace("\n"," "), flush=True)
            except Exception as e:
                print(f"run{i}: ERR {type(e).__name__} {str(e)[:120]} apos {time.monotonic()-t0:.1f}s; texto {await pg.evaluate('document.body.innerText.length')}")
            await pg.close()

asyncio.run(dump(sys.argv[2]) if sys.argv[1] == "dump" else probe(sys.argv[2]))
