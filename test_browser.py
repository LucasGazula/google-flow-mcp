"""Ciclo do navegador residente: perfil isolado, páginas descartadas e lease liberada."""

from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from flow_browser import FlowBrowser


class BrowserTest(unittest.IsolatedAsyncioTestCase):
    async def test_headless_context_survives_pages_and_releases_profile_on_shutdown_or_launch_failure(self):
        pages = [SimpleNamespace(close=AsyncMock()) for _ in range(2)]
        context = SimpleNamespace(pages=[], new_page=AsyncMock(side_effect=pages), close=AsyncMock())
        launch = AsyncMock(return_value=context)
        playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch))
        leases = []

        @asynccontextmanager
        async def lease(path):
            leases.append("enter")
            try:
                yield
            finally:
                leases.append("exit")

        @asynccontextmanager
        async def start_playwright():
            yield playwright

        with tempfile.TemporaryDirectory() as root:
            profile = Path(root) / "profile_conta-a"
            profile.mkdir()
            with patch("gflow_cli.auth.profile_dir", return_value=profile), patch(
                    "gflow_cli.config.get_settings", return_value=SimpleNamespace(home=Path(root))), patch(
                    "gflow_cli.browser_manager.resolved_chrome_binary", return_value="chrome"), patch(
                    "gflow_cli.profile_lease.ProfileLease", lease), patch(
                    "playwright.async_api.async_playwright", start_playwright):
                browser = FlowBrowser("conta-a")
                async with browser.page() as page:
                    self.assertIs(page, pages[0])
                with self.assertRaises(ValueError):
                    async with browser.page() as page:
                        self.assertIs(page, pages[1])
                        raise ValueError("Preparo interrompido")
                launch.assert_awaited_once()
                self.assertTrue(launch.call_args.kwargs["headless"])
                self.assertEqual(launch.call_args.kwargs["user_data_dir"], str(profile.resolve()))
                self.assertEqual(launch.call_args.kwargs["service_workers"], "block")
                for page in pages:
                    page.close.assert_awaited_once()
                context.close.assert_not_awaited()
                self.assertEqual(leases, ["enter"])
                await browser.close()
                context.close.assert_awaited_once()
                self.assertEqual(leases, ["enter", "exit"])
                self.assertIsNone(browser.context)
                launch.side_effect = RuntimeError("Falha ao iniciar Chrome")
                with self.assertRaises(RuntimeError):
                    async with browser.page():
                        self.fail("Navegador não iniciou")
                self.assertEqual(leases, ["enter", "exit", "enter", "exit"])


if __name__ == "__main__":
    unittest.main()
