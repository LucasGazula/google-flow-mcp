import os
import unittest
from unittest.mock import AsyncMock, patch


@unittest.skipIf(os.name == "nt", "keepalive roda só na Pi (fcntl)")
class KeepaliveTest(unittest.IsolatedAsyncioTestCase):
    async def test_profile_held_by_mcp_worker_is_busy_not_lost_session(self):
        import keepalive

        class Client:
            def __init__(self, *args, **kwargs):
                self.client = None

            async def close(self):
                pass

        reply = {"status": "unavailable", "credits": None, "error_type": "ProfileLockedError"}
        with patch("flow_http.FlowHTTP", Client), patch("flow_http.http_operation", AsyncMock(return_value=reply)):
            result = await keepalive.check("ddv1")
        self.assertEqual(result["status"], "busy")
        state = {}
        for _ in range(3):
            self.assertFalse(keepalive.update_state(state, result)["needs_login"])
        ok = {**result, "status": "ok", "credits": 1050, "rotation_fp": None}
        self.assertEqual(keepalive.update_state(state, ok)["last_credits"], 1050)
        result["status"] = "unavailable"
        keepalive.update_state(state, result)
        self.assertTrue(keepalive.update_state(state, result)["needs_login"])


if __name__ == "__main__":
    unittest.main()
