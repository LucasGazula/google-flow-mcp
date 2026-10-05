"""Windows: faz um login Google ISOLADO (perfil temporário, sem relação com o do MCP) e emite os cookies.

Os cookies saem só no stdout (última linha, JSON) para seguir por pipe até importar_sessao.py na Banana Pi.
O perfil temporário é apagado ao fim; a sessão no servidor continua valendo (não faz logout).
Uso:  python deploy/login_para_pi.py | grep '^{"cookies"' | ssh pi@... importar_sessao.py <conta>
"""
import asyncio, json, shutil, sys, tempfile
from pathlib import Path

from playwright.async_api import async_playwright

SAME = {"Strict": "strict", "Lax": "lax", "None": "no_restriction"}


async def main():
    from flow_session import DOMAINS, normalize_cookies
    from gflow_cli.auth.internal_chromium import login_launch_kwargs, poll_session_until_authenticated
    from gflow_cli.browser_manager import resolved_chrome_binary
    from gflow_cli.config import get_settings

    tmp = Path(tempfile.mkdtemp(prefix="_login_tmp_", dir=get_settings().home))
    try:
        async with async_playwright() as pw:
            kwargs = login_launch_kwargs(tmp, False)
            kwargs["executable_path"] = resolved_chrome_binary()
            ctx = await pw.chromium.launch_persistent_context(**kwargs)
            try:
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                print("Faça o login na janela do Chrome que abriu (até 10 min).", file=sys.stderr, flush=True)
                await page.goto("https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fflow.google.com%2F&hl=pt-BR",
                                wait_until="domcontentloaded", timeout=60000)
                await poll_session_until_authenticated(ctx, page, 600, "login_para_pi", raise_on_close=False)
                await page.goto("https://flow.google.com", wait_until="domcontentloaded", timeout=60000)
                # Conta nova mostra um popup de primeiro acesso; sem aceitá-lo o Flow não libera o painel.
                print("Se aparecer um popup do Flow, aceite-o; a janela fecha em 1 min.", file=sys.stderr, flush=True)
                raw = await ctx.cookies()
                for _ in range(12):  # lê a cada 5 s; se o usuário fechar a janela antes, fica a última leitura
                    await asyncio.sleep(5)
                    try:
                        raw = await ctx.cookies()
                    except Exception:
                        break
            finally:
                await ctx.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    cookies = []
    for c in raw:
        d = c.get("domain", "")
        if d.lstrip(".") not in DOMAINS or d not in DOMAINS | {"." + x for x in DOMAINS} or "partitionKey" in c:
            continue
        item = {"name": c["name"], "value": c["value"], "domain": d, "path": c["path"],
                "secure": bool(c.get("secure")), "httpOnly": bool(c.get("httpOnly")), "hostOnly": not d.startswith("."),
                "sameSite": SAME.get(c.get("sameSite"), "unspecified"),
                "expirationDate": c["expires"] if c.get("expires", -1) != -1 else -1}
        if item["sameSite"] == "no_restriction" and not item["secure"]:
            item["sameSite"] = "lax"
        cookies.append(item)
    payload = {"cookies": cookies}
    normalize_cookies(payload)
    print(f"{len(cookies)} cookies válidos de {len(raw)}.", file=sys.stderr, flush=True)
    print(json.dumps(payload))


asyncio.run(main())
