"""Verifica estados distintos de sessão e limites de entrada sem usar contas."""

from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from flow_accounts import account_operation, validate_account
from gflow_cli.auth.verification import FlowSessionOutcome


class AccountTest(unittest.IsolatedAsyncioTestCase):
    async def test_migrated_account_reads_balance_over_http(self):
        with patch("flow_http.FlowHTTP.rpc", AsyncMock(return_value=[1050,1,2,2,None,1050,None])) as reader, \
             patch("flow_http.FlowHTTP.close", AsyncMock()) as close:
            result = await account_operation("credits", "conta-a")
            self.assertEqual(result["status"], "ok")
            self.assertEqual(result["credits"], 1050)
            self.assertEqual(result["source"], "HTTP/nzlxg")
            reader.assert_awaited_once_with("nzlxg")
            reader.side_effect = RuntimeError("SECRET")
            result = await account_operation("credits", "conta-a")
            self.assertEqual(result["status"], "unavailable")
            self.assertIsNone(result["credits"])
            self.assertNotIn("SECRET", str(result))
            self.assertEqual(close.await_count, 2)

    async def test_credit_snapshot_masks_secrets_and_preserves_unknown_balance(self):
        with patch("flow_http.FlowHTTP.rpc", new_callable=AsyncMock) as inspect:
            for balance in (0, 120, None, True, -1):
                inspect.return_value = [balance, "PRIVATE", "SECRET", 2, None, balance, None]
                result = await account_operation("credits", "conta-a")
                valid = type(balance) is int and balance >= 0
                self.assertEqual(result["status"], "ok" if valid else "unavailable")
                self.assertEqual(result["credits"], balance if valid else None)
                self.assertNotIn("PRIVATE", str(result))
                self.assertNotIn("SECRET", str(result))
            inspect.side_effect = RuntimeError("SECRET")
            self.assertEqual((await account_operation("credits", "conta-a"))["status"], "unavailable")

    def test_account_boundary(self):
        self.assertEqual(validate_account("conta-a"), "conta-a")
        for name in ("", "../escape", "a/b", "--flag", "a" * 65):
            with self.assertRaises(ValueError):
                validate_account(name)

    async def test_connect_uses_dedicated_chrome_profile(self):
        with patch("gflow_cli.auth.login", new_callable=AsyncMock) as login, \
             patch("gflow_cli.auth.status", return_value={"exists": False, "cookies_present": False}):
            result = await account_operation("connect", "conta-b")
            login.assert_awaited_once_with("conta-b", browser="chrome", headless=False)
            self.assertEqual(result["status"], "needs_login")
            self.assertFalse(result["authenticated"])

    async def test_saved_session_requires_remote_verification(self):
        with tempfile.TemporaryDirectory() as profile, \
             patch("gflow_cli.auth.status", return_value={"exists": True, "cookies_present": True}), \
             patch("gflow_cli.auth.profile_dir", return_value=Path(profile)), \
             patch("gflow_cli.auth.verification.verify_flow_profile", new_callable=AsyncMock) as probe:
            for outcome in (FlowSessionOutcome.AUTHENTICATED, FlowSessionOutcome.VERIFICATION_ERROR,
                            FlowSessionOutcome.NO_SESSION):
                probe.return_value = SimpleNamespace(
                    outcome=outcome, authenticated=outcome == FlowSessionOutcome.AUTHENTICATED,
                    user_email="unused@example.com", cookies="SECRET",
                )
                result = await account_operation("status", "conta-a")
                self.assertEqual(result["status"], outcome.value)
                self.assertEqual(result["authenticated"], outcome == FlowSessionOutcome.AUTHENTICATED)
                self.assertFalse(result["generation_enabled"])
                self.assertNotIn("SECRET", str(result))
                # O e-mail identifica a conta ao usuário apenas quando a sessão foi confirmada.
                self.assertEqual(result.get("email"), "unused@example.com" if result["authenticated"] else None)

    async def test_account_operation_list_includes_email_and_saved_session(self):
        profiles = [
            SimpleNamespace(name="conta-a", google_account="user_a@example.com", cookies_present=True),
            SimpleNamespace(name="conta-b", google_account="user_b@example.com", cookies_present=False),
            SimpleNamespace(name="invalid/name", google_account="invalid@example.com", cookies_present=True),
        ]
        with patch("gflow_cli.profile_store.list_profiles", return_value=profiles):
            result = await account_operation("list")
            self.assertEqual(result["accounts"], [
                {"account_id": "conta-a", "email": "user_a@example.com", "session_saved": True},
                {"account_id": "conta-b", "email": "user_b@example.com", "session_saved": False},
            ])
            self.assertFalse(result["generation_enabled"])


if __name__ == "__main__":
    unittest.main()

