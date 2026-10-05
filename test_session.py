"""Testes reais da fronteira HTTP e da importação, usando cookies fictícios."""

import http.client
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from flow_session import MAX_BODY, SessionBridge, normalize_cookies


def fixture():
    return {"cookies": [{"name": "example", "value": "fixture-only", "domain": ".google.com",
                         "path": "/", "secure": True, "httpOnly": True, "sameSite": "lax"}]}


class SessionSecurityTest(unittest.TestCase):
    def test_domain_scope_and_cookie_attributes(self):
        self.assertEqual(normalize_cookies(fixture())[0]["sameSite"], "Lax")
        for field, value in [("domain", "google.com.attacker.test"), ("domain", "mail.google.com"),
                             ("path", "invalid"), ("expirationDate", float("nan")),
                             ("httpOnly", "false"), ("name", "bad\nname"),
                             ("sameSite", "unknown"), ("partitionKey", {})]:
            data = fixture()
            data["cookies"][0][field] = value
            with self.assertRaises(ValueError):
                normalize_cookies(data)
        data = fixture()
        data["cookies"][0]["expirationDate"] = time.time() - 100
        with self.assertRaises(ValueError):
            normalize_cookies(data)

    def test_http_pairing_scope_and_replay(self):
        bridge = SessionBridge("conta-a")
        try:
            def request(headers, body=None, path="/session"):
                client = http.client.HTTPConnection("127.0.0.1", bridge.port, timeout=5)
                try:
                    client.request("POST", path, json.dumps(fixture()) if body is None else body,
                                   {"Content-Type": "application/json", **headers})
                    response = client.getresponse()
                    result = (response.status, response.read())
                    self.assertNotIn(b"fixture-only", result[1])
                    return result[0]
                finally:
                    client.close()
            self.assertEqual(bridge.server.server_address[0], "127.0.0.1")
            self.assertEqual(request({}), 403)
            self.assertEqual(request({"X-Flow-Pairing": "a" * 64}), 403)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token, "Origin": "https://attacker.test"}), 403)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token, "Host": "attacker.test"}), 403)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token, "Content-Length": str(MAX_BODY + 1)}, ""), 400)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token}, '{"cookies":[]}'), 400)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token,
                                      "Origin": "chrome-extension://" + "a" * 32}), 200)
            self.assertEqual(request({"X-Flow-Pairing": bridge.token}), 403)
            self.assertTrue(bridge.received.is_set())
            self.assertEqual(bridge.take(), fixture())
            self.assertIsNone(bridge.payload)
        finally:
            bridge.close()

    def test_expired_pairing_never_accepts_session(self):
        bridge = SessionBridge("conta-a")
        try:
            bridge.deadline = time.monotonic() - 1
            with self.assertRaises(ValueError):
                bridge.take()
        finally:
            bridge.close()


class SessionImportTest(unittest.IsolatedAsyncioTestCase):
    async def test_import_isolated_profile_and_account_chooser(self):
        from flow_accounts import import_session
        with tempfile.TemporaryDirectory() as directory:
            pdir = Path(directory) / "profile_conta-b"
            page = SimpleNamespace(goto=AsyncMock())
            context = SimpleNamespace(pages=[page], add_cookies=AsyncMock(), close=AsyncMock())
            chromium = SimpleNamespace(launch_persistent_context=AsyncMock(return_value=context))
            pw = AsyncMock()
            pw.__aenter__.return_value = SimpleNamespace(chromium=chromium)
            lease = AsyncMock()
            verified = SimpleNamespace(authenticated=True, user_email="fixture@example.test")
            with patch("gflow_cli.auth.profile_dir", return_value=pdir), \
                 patch("gflow_cli.config.get_settings", return_value=SimpleNamespace(home=Path(directory))), \
                 patch("gflow_cli.winsec.ensure_profile_hardened"), \
                 patch("gflow_cli.profile_lease.ProfileLease", return_value=lease), \
                 patch("playwright.async_api.async_playwright", return_value=pw), \
                 patch("gflow_cli.browser_manager.resolved_chrome_binary", return_value="fixture-chrome"), \
                 patch("gflow_cli.auth.internal_chromium.poll_session_until_authenticated", new_callable=AsyncMock), \
                 patch("gflow_cli.auth.verification.verify_flow_profile", new_callable=AsyncMock, return_value=verified):
                with patch("flow_accounts.os.name", "nt"), \
                     patch("gflow_cli.winsec.ensure_profile_hardened", return_value=False):
                    with self.assertRaises(RuntimeError):
                        await import_session("conta-b", fixture())
                    context.add_cookies.assert_not_awaited()
                await import_session("conta-b", fixture())
                context.add_cookies.assert_awaited_once_with(normalize_cookies(fixture()))
                self.assertIn("AccountChooser", page.goto.call_args.args[0])
                self.assertEqual(chromium.launch_persistent_context.call_args.kwargs["user_data_dir"], str(pdir))
                context.close.assert_awaited_once()
                self.assertEqual((pdir / ".gflow_account").read_text(), "fixture@example.test")
                with self.assertRaises(ValueError):
                    await import_session("conta-b", fixture())
                self.assertEqual(chromium.launch_persistent_context.await_count, 1)


if __name__ == "__main__":
    unittest.main()
