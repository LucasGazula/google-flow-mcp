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

    def test_account_with_recent_mcp_generation_is_not_reopened(self):
        import json, tempfile, time
        from datetime import datetime, timezone
        from pathlib import Path
        import keepalive

        def at(ago):
            return datetime.fromtimestamp(time.time() - ago, timezone.utc).isoformat(timespec="seconds")

        with tempfile.TemporaryDirectory() as root:
            log = Path(root) / "operations.jsonl"
            rows = [{"at": at(60), "account_id": "ddv1", "action": "images", "status": "completed"},
                    {"at": at(60), "account_id": "ddv2", "action": "images", "status": "failed_pre_submit"},
                    {"at": at(60), "account_id": "ddv3", "action": "list"},
                    {"at": at(7200), "account_id": "ddv4", "action": "generate", "status": "completed"},
                    {"at": at(30), "account_id": "ddv5", "action": "upload_image", "status": "uploaded"}]
            log.write_text("cortada}\n" + "\n".join(map(json.dumps, rows)) + "\n")
            self.assertEqual(keepalive.recently_used(log, time.time()), {"ddv1", "ddv5"})
            self.assertEqual(keepalive.recently_used(Path(root) / "ausente.jsonl", time.time()), set())
        state = {"ddv1": {"failures": 1, "last_ok": None, "last_fp": None, "rotations": 0}}
        r = {"at": at(0), "account_id": "ddv1", "status": "in_use", "rotation_fp": None}
        self.assertFalse(keepalive.update_state(state, r)["needs_login"])
        self.assertEqual(state["ddv1"]["failures"], 0)


if __name__ == "__main__":
    unittest.main()
