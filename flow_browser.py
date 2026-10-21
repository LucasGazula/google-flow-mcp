"""Chrome dedicado, residente no worker, com lease e páginas de preparo descartáveis."""

import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
import fcntl
import os
from pathlib import Path
import tempfile

# Páginas leves (padrão): o preparo só precisa do JavaScript do Flow e do reCAPTCHA. Imagens, vídeos e fontes
# (miniaturas do projeto) são bloqueados: na Pi eram o grosso da memória. FLOW_MCP_LIGHT_PAGES=0 desliga.
LIGHT_PAGES = os.environ.get("FLOW_MCP_LIGHT_PAGES", "1") != "0"
HEAVY_TYPES = {"image", "media", "font"}
# Quantas páginas de preparo podem carregar ao mesmo tempo na máquina, somando todas as contas (cada conta é um
# processo). As demais esperam a vez em vez de levar a Pi ao swap. ponytail: fila por arquivo + polling de 0,5 s.
PREPARE_SLOTS = max(1, int(os.environ.get("FLOW_MCP_PREPARE_SLOTS", "2")))
SLOT_WAIT_SECONDS = 300
# Chrome sem página aberta fecha após estes segundos, mesmo no meio de uma operação longa (acompanhar vídeo,
# baixar): parado ele ainda ocupa ~600 MB na Pi. Reabrir custa só o início do processo; o preparo navega sempre.
IDLE_CLOSE_SECONDS = float(os.environ.get("FLOW_MCP_BROWSER_IDLE_SECONDS", "45"))


async def _skip_heavy(route):
    request = route.request
    if request.resource_type in HEAVY_TYPES and "/recaptcha/" not in request.url:
        await route.abort()
    else:
        await route.fallback()


@asynccontextmanager
async def prepare_slot(folder=None):
    """Uma das PREPARE_SLOTS vagas da máquina (flock em <tmp>/flow-mcp-prepare-slots/N.lock), liberada ao sair."""
    folder = folder or Path(tempfile.gettempdir()) / "flow-mcp-prepare-slots"
    folder.mkdir(exist_ok=True)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + SLOT_WAIT_SECONDS
    while True:
        for k in range(PREPARE_SLOTS):
            handle = open(folder / f"{k}.lock", "a")
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                handle.close()
                continue
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)
                handle.close()
            return
        if loop.time() > deadline:
            raise ValueError(f"Máquina do MCP ocupada: {PREPARE_SLOTS} preparos de outras contas em andamento "
                             f"há mais de {SLOT_WAIT_SECONDS} s; nada foi enviado. Tente de novo em instantes.")
        await asyncio.sleep(0.5)


class FlowBrowser:
    """Um contexto autenticado por worker; cada preparo usa uma página descartável."""

    def __init__(self, account_id, *, headless=True):
        self.account_id = account_id
        self.headless = headless
        self.context = None
        self.stack = AsyncExitStack()
        self.open_pages = 0
        self.idle_task = None
        self.gate = asyncio.Lock()  # Abrir página e fechar por ociosidade não se cruzam.

    async def _close_when_idle(self):
        await asyncio.sleep(IDLE_CLOSE_SECONDS)
        async with self.gate:
            if not self.open_pages:
                self.idle_task = None
                await self.close()

    async def close(self):
        task, self.idle_task = self.idle_task, None
        if task is not None and task is not asyncio.current_task():
            task.cancel()
        try:
            await self.stack.aclose()
        finally:
            self.context = None

    @asynccontextmanager
    async def page(self):
        async with prepare_slot():
            async with self._page() as page:
                yield page

    @asynccontextmanager
    async def _page(self):
        async with self.gate:
            if self.idle_task is not None:
                self.idle_task.cancel()
                self.idle_task = None
            page = await self._new_page()
            self.open_pages += 1
        try:
            yield page
        finally:
            self.open_pages -= 1
            await page.close()  # Fecha também rotas e retries do preparo antes do POST HTTP.
            if not self.open_pages and self.context is not None:
                self.idle_task = asyncio.create_task(self._close_when_idle())

    async def _new_page(self):
        if self.context is None:
            from flow_accounts import validate_account
            from gflow_cli import auth
            from gflow_cli.auth.internal_chromium import login_launch_kwargs
            from gflow_cli.browser_manager import resolved_chrome_binary
            from gflow_cli.config import get_settings
            from gflow_cli.profile_lease import ProfileLease
            from playwright.async_api import async_playwright

            validate_account(self.account_id)
            if not auth.profile_dir(self.account_id).is_dir():
                import platform

                raise ValueError(f"A conta '{self.account_id}' não tem perfil nesta máquina ({platform.node()}); "
                                 "use um e-mail/apelido de flow_list_accounts ou conecte a conta.")
            pdir = auth.profile_dir(self.account_id).resolve(strict=True)
            if not pdir.is_relative_to(get_settings().home.resolve(strict=True)):
                raise ValueError("Perfil fora do diretório configurado.")
            executable = resolved_chrome_binary()
            if not executable:
                raise RuntimeError("Chrome/Chromium não encontrado.")
            try:
                await self.stack.enter_async_context(ProfileLease(pdir))
                pw = await self.stack.enter_async_context(async_playwright())
                kwargs = login_launch_kwargs(pdir, self.headless)
                kwargs.update(executable_path=executable, service_workers="block")
                self.context = await pw.chromium.launch_persistent_context(**kwargs)
                self.stack.push_async_callback(self.context.close)
                if LIGHT_PAGES and self.headless:
                    await self.context.route("**/*", _skip_heavy)
                for page in self.context.pages:
                    await page.close()
            except BaseException:
                await self.close()
                raise
        return await self.context.new_page()


@asynccontextmanager
async def account_page(account_id: str):
    browser = FlowBrowser(account_id, headless=False)
    try:
        async with browser.page() as page:
            yield page
    finally:
        await browser.close()
