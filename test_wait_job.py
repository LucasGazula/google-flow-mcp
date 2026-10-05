"""Espera reconcilia a tarefa original sem submeter mídia novamente."""

import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from flow_mcp import flow_wait_job
from flow_video import recover_job
from mcp.server.mcpserver.exceptions import ToolError


class WaitJobTest(unittest.IsolatedAsyncioTestCase):
    def job(self, **changes):
        return {"job_id": str(uuid4()), "account_id": "conta-a", "status": "submission_unknown",
                "request_media_ids": [str(uuid4())], **changes}

    async def test_wait_recovers_original_job_until_complete(self):
        job = self.job()
        with patch("flow_video.get_job", return_value=job), patch(
                "flow_mcp.run_account_operation", AsyncMock(side_effect=[
                    {**job, "recovery_status": "not_listed"}, {**job, "status": "completed"}])) as recover, patch(
                "flow_mcp.asyncio.sleep", AsyncMock()):
            result = await flow_wait_job("conta-a", job["job_id"])
        self.assertEqual(result["wait_status"], "completed")
        self.assertEqual(result["polls"], 2)
        for call in recover.call_args_list:
            self.assertEqual(call.args, ("recover", "conta-a", {"job_id": job["job_id"]}))

    async def test_single_query_timeout_preserves_uncertain_state(self):
        job = self.job()
        with patch("flow_video.get_job", return_value=job), patch(
                "flow_mcp.run_account_operation", AsyncMock(return_value={
                    **job, "recovery_status": "not_listed"})) as recover:
            result = await flow_wait_job("conta-a", job["job_id"], timeout_seconds=0)
        self.assertEqual(result["wait_status"], "timeout")
        self.assertEqual(result["status"], "submission_unknown")
        recover.assert_awaited_once()

    async def test_completed_cancelled_or_unsent_jobs_do_not_poll(self):
        for status, expected in (("completed", "completed"), ("cancelled", "stopped"),
                                 ("failed_pre_submit", "stopped")):
            job = self.job(status=status)
            with patch("flow_video.get_job", return_value=job), patch(
                    "flow_mcp.run_account_operation", AsyncMock()) as recover:
                result = await flow_wait_job("conta-a", job["job_id"])
            self.assertEqual(result["wait_status"], expected)
            recover.assert_not_awaited()

    async def test_cancelled_recovery_never_contacts_backend(self):
        job = self.job(status="cancelled")
        with patch("flow_video.get_job", return_value=job), patch("flow_http.FlowHTTP") as client:
            self.assertEqual(await recover_job("conta-a", job["job_id"]), job)
        client.assert_not_called()

    async def test_wait_observes_local_cancellation_between_queries(self):
        job = self.job()
        cancelled = {**job, "status": "cancelled"}
        with patch("flow_video.get_job", side_effect=[job, cancelled]), patch(
                "flow_mcp.run_account_operation", AsyncMock(return_value=job)) as recover, patch(
                "flow_mcp.asyncio.sleep", AsyncMock()):
            result = await flow_wait_job("conta-a", job["job_id"])
        self.assertEqual(result["wait_status"], "stopped")
        self.assertEqual(result["status"], "cancelled")
        recover.assert_awaited_once()

    async def test_backend_error_stops_without_losing_job_state(self):
        job = self.job()
        with patch("flow_video.get_job", return_value=job), patch(
                "flow_mcp.run_account_operation", AsyncMock(return_value={"status": "http_worker_error"})):
            result = await flow_wait_job("conta-a", job["job_id"])
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(result["wait_status"], "unavailable")

    async def test_invalid_bounds_and_other_account_stop_before_poll(self):
        job = self.job()
        with patch("flow_mcp.run_account_operation", AsyncMock()) as recover:
            for bounds in ({"timeout_seconds": True}, {"timeout_seconds": 601},
                           {"poll_interval_seconds": 1}, {"poll_interval_seconds": 61}):
                with self.assertRaises(ToolError):
                    await flow_wait_job("conta-a", job["job_id"], **bounds)
            with patch("flow_video.get_job", side_effect=ValueError("A tarefa pertence a outra conta.")):
                with self.assertRaises(ToolError):
                    await flow_wait_job("conta-a", job["job_id"])
        recover.assert_not_awaited()
