"""Experimento: worker HTTP com o preparo feito no Lightpanda (CDP) em vez do Chrome.

Cookies da conta chegam por stdin (JSON, só em memória). Uso:
  python lightpanda_run.py <conta> <quote|generate> <args.json>   < cookies.json
"""
import asyncio, json, os, sys
from contextlib import asynccontextmanager
from pathlib import Path

from playwright.async_api import Locator, async_playwright

CDP = "http://127.0.0.1:9222"
INIT = (
    "window.requestAnimationFrame = cb => setTimeout(() => cb(performance.now()), 16);"
    "window.cancelAnimationFrame = id => clearTimeout(id);"
    "try { DOMTokenList.prototype.supports = function() { return false; }; } catch (e) {}"
    "if (!window.trustedTypes) { const mk = n => ({name: n, createHTML: s => s, createScript: s => s,"
    " createScriptURL: s => s}); window.trustedTypes = {createPolicy: (n, p) => Object.assign(mk(n), p || {}),"
    " isHTML: () => false, isScript: () => false, isScriptURL: () => false, emptyHTML: '', emptyScript: '',"
    " defaultPolicy: null, getAttributeType: () => null, getPropertyType: () => null}; }"
)

async def _dom_click(self, **kw):
    # ponytail: Lightpanda não tem layout; clique por evento DOM em vez de coordenadas.
    return await self.dispatch_event("click", timeout=kw.get("timeout", 5000))
Locator.click = _dom_click


async def _dom_fill(self, value, **kw):
    # ponytail: Lightpanda não reconhece contenteditable em fill(); o ProseMirror aceita texto no <p> + input.
    await self.evaluate("""(el, v) => { el.focus(); const p = el.querySelector('p') || el; p.textContent = v;
        try { const r = document.createRange(); r.selectNodeContents(p); r.collapse(false);
              const s = getSelection(); s.removeAllRanges(); s.addRange(r); } catch (x) {}
        el.dispatchEvent(new InputEvent('input', {inputType: 'insertText', data: v, bubbles: true}));
        el.dispatchEvent(new KeyboardEvent('keyup', {key: 'e', bubbles: true})); }""", value)
Locator.fill = _dom_fill


class LightpandaBrowser:
    """Mesma interface de FlowBrowser (page/close), mas conectada a um Lightpanda já em execução."""

    def __init__(self, cookies):
        self.cookies, self.pw, self.ctx = cookies, None, None

    async def close(self):
        if self.pw:
            await self.pw.stop()
        self.pw = self.ctx = None

    @asynccontextmanager
    async def page(self):
        if self.ctx is None:
            self.pw = await async_playwright().start()
            browser = await self.pw.chromium.connect_over_cdp(CDP)
            self.ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
            first = await self.ctx.new_page()
            await self.ctx.add_cookies(self.cookies)
            await first.close()
        page = await self.ctx.new_page()
        await page.add_init_script(INIT)
        real_goto = page.goto

        async def goto(url, **kw):  # 'load'/'domcontentloaded' podem pendurar por minutos
            kw["wait_until"] = "commit"
            return await real_goto(url, **kw)
        page.goto = goto
        try:
            yield page
        finally:
            await page.close()


async def main(account, action, args_path):
    import flow_http
    from flow_http import FlowHTTP, http_operation

    cookies = json.load(sys.stdin)
    client = FlowHTTP(account, resident=False)
    client.browser = LightpandaBrowser(cookies)
    import flow_video
    _orig = FlowHTTP.prepare
    async def _prepare(self, *a, **k):
        try:
            return await _orig(self, *a, **k)
        except BaseException as e:
            print("PREPARE FALHOU:", type(e).__name__, str(e)[:500].replace("\n", " "), file=sys.stderr, flush=True)
            raise
    FlowHTTP.prepare = _prepare
    try:
        result = await http_operation(client, {"quote": "quote_video", "generate": "generate"}[action],
                                      json.load(open(args_path)))
        print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    finally:
        await client.close()

if __name__ == "__main__":
    home = str(Path(__file__).parent / "profiles")
    os.environ.setdefault("FLOW_MCP_HOME", home); os.environ.setdefault("GFLOW_CLI_HOME", home)
    asyncio.run(main(*sys.argv[1:4]))
