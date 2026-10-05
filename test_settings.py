"""Testes das preferências de conta sem sessão Google."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, call, patch

from flow_settings import get_user_settings, parse_user_settings, update_user_settings


class UserSettingsTest(unittest.IsolatedAsyncioTestCase):
    def test_parser_reads_fields_and_rejects_unknown_values(self):
        payload = [None] * 12
        payload[5:12] = [True, False, True, "batch", True, None, True]
        settings = parse_user_settings(payload)
        self.assertEqual(settings, {
            "clear_prompt_on_submit": True,
            "sound_on_hover": False,
            "show_tile_details": True,
            "view_mode": "batch",
            "return_silent_videos": True,
            "agent_mode_enabled": True,
        })
        with self.assertRaises(ValueError):
            parse_user_settings([None] * 8 + [[]])

    async def test_get_reads_only_settings_rpc(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[]))
        result = await get_user_settings("conta-a", client=client)
        client.rpc.assert_awaited_once_with("Yizz8d")
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["settings"]["view_mode"], "grid")

    async def test_update_sends_sparse_fields_once_and_confirms_by_readback(self):
        payload = [None] * 12
        payload[7:9] = [True, "batch"]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[[], payload]))
        result = await update_user_settings("conta-a", show_tile_details=True,
                                           view_mode="batch", client=client)

        fields = [None] * 9
        fields[7:9] = [1, "batch"]
        self.assertEqual(client.rpc.await_args_list, [
            call("DA4VGb", params=[fields, [["is_tile_details_always_visible", "tiles_display_mode"]]]),
            call("Yizz8d"),
        ])
        self.assertEqual(result["status"], "updated")

    async def test_silent_video_preference_requires_credit_confirmation(self):
        with patch("flow_http.FlowHTTP") as factory:
            result = await update_user_settings("conta-a", return_silent_videos=True)
        self.assertEqual(result["status"], "confirmation_required")
        factory.assert_not_called()

    async def test_uncertain_update_is_read_back_without_resending(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(
            side_effect=[RuntimeError("uncertain"), []]))
        result = await update_user_settings("conta-a", sound_on_hover=True, client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(client.rpc.await_args_list, [
            call("DA4VGb", params=[[None] * 6 + [1], [["has_sound_on_tile_hover"]]]),
            call("Yizz8d"),
        ])


if __name__ == "__main__":
    unittest.main()
