"""Operações de conta isoladas em subprocesso; somente resultados seguros saem."""

import asyncio
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import json
import os
import re
import sys


ACCOUNT_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}")


def validate_account(account_id: str) -> str:
    if not ACCOUNT_ID.fullmatch(account_id):
        raise ValueError("Use um apelido de até 64 letras, números, hífens ou sublinhados.")
    return account_id


async def account_operation(action: str, account_id: str = "", session: dict | None = None) -> dict:
    from gflow_cli import auth, profile_store
    from gflow_cli.auth.verification import verify_flow_profile

    if action == "list":
        return {"accounts": [
            {"account_id": p.name, "email": p.google_account, "session_saved": p.cookies_present}
            for p in profile_store.list_profiles() if ACCOUNT_ID.fullmatch(p.name)
        ], "generation_enabled": False}

    validate_account(account_id)
    if action not in {"connect", "status", "import", "credits", "generate", "images", "job", "jobs", "recover", "project", "projects", "capabilities", "assets", "upload_image", "download_asset", "edit_image", "get_asset"}:
        raise ValueError("Operação de conta inválida.")
    if action in {"edit_image", "get_asset"}:
        from flow_edit import edit_image, get_asset

        return await {"edit_image":edit_image, "get_asset":get_asset}[action](account_id, **session)
    if action in {"assets", "upload_image", "download_asset"}:
        from flow_assets import list_assets, upload_image, download_asset

        operation = {"assets": list_assets, "upload_image": upload_image, "download_asset": download_asset}[action]
        return await operation(account_id, **session)
    if action == "projects":
        from flow_projects import list_projects

        return await list_projects(account_id)
    if action == "capabilities":
        from flow_capabilities import read_capabilities

        return await read_capabilities(account_id, **session)
    if action == "project":
        from flow_projects import project_operation

        return await project_operation(account_id, **session)
    if action in {"generate", "images", "job", "jobs", "recover"}:
        from flow_video import generate_video, generate_images, get_job, list_jobs, recover_job

        if action == "jobs":
            return list_jobs(account_id, **session)
        if action == "job":
            return get_job(account_id, session["job_id"])
        if action == "recover":
            return await recover_job(account_id, session["job_id"])
        if action == "images":
            return await generate_images(account_id, **session)
        return await generate_video(account_id, **session)
    if action == "credits":
        from flow_http import FlowHTTP, http_operation

        client = FlowHTTP(account_id)
        try:
            return await http_operation(client, "credits", {})
        finally:
            await client.close()
    if action == "connect":
        # Chrome e MCP devem executar no mesmo sistema operacional.
        await auth.login(account_id, browser="chrome", headless=False)
    if action == "import":
        await import_session(account_id, session)
    local = auth.status(account_id)
    result = {
        "account_id": account_id,
        "status": "needs_login",
        "authenticated": False,
        "generation_enabled": False,
        "observed_at": datetime.now(timezone.utc).isoformat(),
    }
    if local["exists"] and local["cookies_present"]:
        pdir = auth.profile_dir(account_id)
        session = await verify_flow_profile(pdir, source="flow_mcp")
        result.update(status=session.outcome.value, authenticated=session.authenticated)
        if session.authenticated and session.user_email:
            result["email"] = session.user_email
            if profile_store.read_account_file(pdir) is None:
                # Identifica o perfil pelo e-mail; não substitui um registro existente.
                (pdir / profile_store.ACCOUNT_FILE).write_text(session.user_email, encoding="utf-8")
    return result


async def import_session(account_id: str, session: dict | None) -> None:
    from gflow_cli import auth
    from gflow_cli.auth.internal_chromium import login_launch_kwargs, poll_session_until_authenticated
    from gflow_cli.auth.verification import verify_flow_profile
    from gflow_cli.browser_manager import resolved_chrome_binary
    from gflow_cli.profile_lease import ProfileLease
    from gflow_cli.config import get_settings
    from gflow_cli.winsec import ACL_MARKER, ensure_profile_hardened
    from playwright.async_api import async_playwright
    from flow_session import normalize_cookies

    cookies = normalize_cookies(session)
    pdir = auth.profile_dir(validate_account(account_id))
    if not pdir.resolve().is_relative_to(get_settings().home.resolve()):
        raise ValueError("Perfil fora do diretório configurado.")
    pdir.mkdir(parents=True, exist_ok=True, mode=0o700)
    hardened = ensure_profile_hardened(pdir)
    if os.name == "nt" and not hardened and not (pdir / ACL_MARKER).exists():
        raise RuntimeError("Não foi possível proteger o perfil de destino.")
    executable = resolved_chrome_binary()
    if not executable:
        raise RuntimeError("Chrome/Chromium não encontrado.")
    # ponytail: guard exclusivo; após queda abrupta, recuperar manualmente ou usar outro apelido.
    # Trocar por lease reentrante se recuperação automática passar a ser necessária.
    lock = pdir / ".flow_session_import.lock"
    fd = os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(fd)
    try:
        if (pdir / ".gflow_account").exists():
            raise ValueError("A conta já possui sessão; escolha outro apelido.")
        async with ProfileLease(pdir), async_playwright() as pw:
            kwargs = login_launch_kwargs(pdir, False)
            kwargs["executable_path"] = executable
            ctx = await pw.chromium.launch_persistent_context(**kwargs)
            try:
                await ctx.add_cookies(cookies)
                page = ctx.pages[0] if ctx.pages else await ctx.new_page()
                await page.goto(
                    "https://accounts.google.com/AccountChooser?continue="
                    "https%3A%2F%2Flabs.google%2Ffx%2Ftools%2Fflow&hl=pt-BR",
                    wait_until="domcontentloaded", timeout=60000,
                )
                await poll_session_until_authenticated(ctx, page, 600, "flow_mcp_import", raise_on_close=False)
            finally:
                await ctx.close()
        # Mantém o leitor no mesmo Chrome/Chromium usado na importação.
        (pdir / ".gflow_browser_strategy").write_text("chrome", encoding="utf-8")
        verified = await verify_flow_profile(pdir, source="flow_mcp_import")
        if verified.authenticated and verified.user_email:
            (pdir / ".gflow_account").write_text(verified.user_email, encoding="utf-8")
    finally:
        lock.unlink(missing_ok=True)



if __name__ == "__main__":
    # Não encaminhar logs, cookies, tokens ou mensagens de exceção ao cliente MCP.
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
        try:
            payload = asyncio.run(asyncio.wait_for(
                account_operation(*sys.argv[1:], session=json.loads(sys.stdin.buffer.read(1024 * 1024 + 1))
                                  if sys.argv[1] in {"import", "generate", "images", "job", "jobs", "recover", "project", "capabilities", "assets", "upload_image", "download_asset", "edit_image", "get_asset"} else None),
                timeout=1200 if sys.argv[1] in {"generate", "images", "edit_image"} else 180 if sys.argv[1] in {"recover", "upload_image", "download_asset"} else 620 if sys.argv[1] in {"connect", "import"} else 75,
            ))
        except asyncio.TimeoutError:
            payload = {"status": "timeout", "generation_enabled": False,
                       "message": "Tempo esgotado; consulte a conta antes de tentar novamente."}
        except Exception:
            payload = {"status": "backend_error", "generation_enabled": False,
                       "message": "Falha no backend. Verifique Chrome, tela gráfica e sessão local."}
    print(json.dumps(payload))
