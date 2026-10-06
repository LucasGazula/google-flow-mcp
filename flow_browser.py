"""Chrome dedicado, residente no worker, com lease e páginas de preparo descartáveis."""

from contextlib import AsyncExitStack, asynccontextmanager


class FlowBrowser:
    """Um contexto autenticado por worker; cada preparo usa uma página descartável."""

    def __init__(self, account_id, *, headless=True):
        self.account_id = account_id
        self.headless = headless
        self.context = None
        self.stack = AsyncExitStack()

    async def close(self):
        try:
            await self.stack.aclose()
        finally:
            self.context = None

    @asynccontextmanager
    async def page(self):
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
                for page in self.context.pages:
                    await page.close()
            except BaseException:
                await self.close()
                raise
        page = await self.context.new_page()
        try:
            yield page
        finally:
            await page.close()  # Fecha também rotas e retries do preparo antes do POST HTTP.


@asynccontextmanager
async def account_page(account_id: str):
    browser = FlowBrowser(account_id, headless=False)
    try:
        async with browser.page() as page:
            yield page
    finally:
        await browser.close()
