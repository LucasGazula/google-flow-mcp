"""Banana Pi: importa cookies (JSON no stdin, nunca em arquivo) num perfil, sem o seletor de contas.

O import oficial (flow_session.py import) espera alguém clicar na conta no Chrome visível; aqui só essa
etapa é trocada por uma navegação direta ao Flow. Uso (com xvfb-run): importar_sessao.py <conta> [--email E] [--fresh]
"""
import argparse, asyncio, json, shutil, sys

import gflow_cli.auth.internal_chromium as ic


async def direct(ctx, page, timeout, tag, raise_on_close=False):
    await page.goto("https://flow.google.com", wait_until="domcontentloaded", timeout=60000)
    await asyncio.sleep(10)


ic.poll_session_until_authenticated = direct


async def main(a):
    from gflow_cli import auth
    from flow_accounts import account_operation, validate_account

    validate_account(a.account)
    pdir = auth.profile_dir(a.account)
    payload = json.loads(sys.stdin.readline())  # lê antes de apagar: sem payload, o perfil existente é preservado
    if a.fresh:
        shutil.rmtree(pdir, ignore_errors=True)
    result = await account_operation("import", a.account, session=payload)
    if a.email:  # a verificação do gflow no Linux não grava o e-mail; é necessário para achar a conta por e-mail
        (pdir / ".gflow_account").write_text(a.email, encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k in {"account_id", "status", "authenticated"}}))


ap = argparse.ArgumentParser()
ap.add_argument("account"); ap.add_argument("--email"); ap.add_argument("--fresh", action="store_true")
asyncio.run(main(ap.parse_args()))
