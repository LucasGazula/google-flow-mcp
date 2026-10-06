"""Teste do protocolo MCP por stdio, sem conta Google ou geração paga."""

import asyncio
from pathlib import Path
import sys
import os
import tempfile
import unittest
import json
from uuid import uuid4

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver.exceptions import ToolError
from unittest.mock import AsyncMock, patch

from flow_mcp import resolve_account, run_account_operation, INSTRUCTIONS, mcp


class MCPSmokeTest(unittest.IsolatedAsyncioTestCase):
    async def test_stdio_status(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            await self.check_server(home)

    async def check_server(self, home: str) -> None:
        server = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(__file__).with_name("flow_mcp.py"))],
            env={**os.environ, "FLOW_MCP_HOME": home, "GFLOW_CLI_HOME": str(Path(home) / "foreign")},
        )
        async with asyncio.timeout(60):
            async with Client(server) as client:
                tools = await client.list_tools()
                self.assertEqual({tool.name for tool in tools.tools}, {
                    "flow_status", "flow_list_accounts", "flow_connect_account", "flow_account_status",
                    "flow_begin_account_connection", "flow_complete_account_connection", "flow_get_credits",
                    "flow_generate_video", "flow_generate_images", "flow_get_job", "flow_recover_job", "flow_wait_job",
                    "flow_create_project", "flow_rename_project", "flow_delete_project", "flow_list_collections", "flow_create_collection", "flow_rename_collection", "flow_move_assets", "flow_get_capabilities", "flow_list_projects", "flow_list_jobs",
                    "flow_list_assets", "flow_search_assets", "flow_upload_image", "flow_upload_asset", "flow_confirm_upload", "flow_download_asset", "flow_delete_asset", "flow_get_asset", "flow_edit_image", "flow_edit_images",
                    "flow_edit_video", "flow_refine_video", "flow_extend_video", "flow_quote_video", "flow_quote_images", "flow_crop_image", "flow_upscale_image", "flow_upscale_video",
                    "flow_cancel_job", "flow_clean_jobs", "flow_save_frame", "flow_export_gif", "flow_build_scene",
                    "flow_manage_scene", "flow_list_scenes", "flow_export_scene", "flow_list_characters", "flow_list_voice_presets", "flow_manage_character",
                    "flow_get_agent_brief", "flow_update_agent_brief",
                    "flow_upscale", "flow_download_project", "flow_download_collection", "flow_project_summary",
                    "flow_get_user_settings", "flow_update_user_settings",
                    "flow_list_agent_sessions", "flow_create_agent_session",
                    "flow_rename_agent_session", "flow_delete_agent_session", "flow_list_tools", "flow_agent_request"
                })
                video_tool = next(tool for tool in tools.tools if tool.name == "flow_generate_video")
                self.assertEqual(video_tool.input_schema["properties"]["resolution"]["default"], "720p")
                self.assertIn("reference_asset_ids", video_tool.input_schema["properties"])
                self.assertNotIn("reference_video_paths", video_tool.input_schema["properties"])
                self.assertIn("start_image_asset_id", video_tool.input_schema["properties"])
                self.assertIn("end_image_asset_id", video_tool.input_schema["properties"])
                edit_tool = next(tool for tool in tools.tools if tool.name == "flow_edit_video")
                self.assertNotIn("reference_video_paths", edit_tool.input_schema["properties"])
                search_tool = next(tool for tool in tools.tools if tool.name == "flow_search_assets")
                self.assertEqual(search_tool.input_schema["properties"]["limit"]["default"], 100)
                self.assertIn("query", search_tool.input_schema["required"])
                result = await client.call_tool("flow_status", {})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["backend_status"], "accounts_available")
                self.assertTrue(result.structured_content["generation_enabled"])
                for key in ("host", "downloads_dir", "jobs_dir", "ffmpeg_available", "disk_free_mb"):
                    self.assertIn(key, result.structured_content)
                accounts = await client.call_tool("flow_list_accounts", {})
                self.assertFalse(accounts.is_error)
                self.assertEqual(accounts.structured_content["accounts"], [])
                status = await client.call_tool("flow_account_status", {"account_id": "conta-a"})
                self.assertFalse(status.is_error)
                self.assertEqual(status.structured_content["status"], "needs_login")
                credits = await client.call_tool("flow_get_credits", {"account_id": "conta-a"})
                self.assertFalse(credits.is_error)
                self.assertEqual(credits.structured_content["status"], "unavailable")
                self.assertIsNone(credits.structured_content["credits"])
                invalid = await client.call_tool("flow_connect_account", {"account_id": "../escape"})
                self.assertTrue(invalid.is_error)
                self.assertEqual(list(Path(home).iterdir()), [])
                job_id = str(uuid4())
                jobs = Path(home) / "jobs"
                jobs.mkdir()
                (jobs / f"{job_id}.json").write_text(json.dumps({
                    "job_id": job_id, "account_id": "conta-a", "status": "completed", "files": []
                }), encoding="utf-8")
                job = await client.call_tool("flow_get_job", {"account_id": "conta-a", "job_id": job_id})
                self.assertFalse(job.is_error)
                self.assertEqual(job.structured_content["status"], "completed")
                waited = await client.call_tool("flow_wait_job", {
                    "account_id": "conta-a", "job_id": job_id, "timeout_seconds": 0})
                self.assertFalse(waited.is_error)
                self.assertEqual(waited.structured_content["wait_status"], "completed")
                self.assertEqual(waited.structured_content["polls"], 0)

                # Test cancel_job over MCP
                job_active_id = str(uuid4())
                (jobs / f"{job_active_id}.json").write_text(json.dumps({
                    "job_id": job_active_id, "account_id": "conta-a", "status": "preparing", "files": []
                }), encoding="utf-8")
                cancel_res = await client.call_tool("flow_cancel_job", {"account_id": "conta-a", "job_id": job_active_id})
                self.assertFalse(cancel_res.is_error)
                self.assertEqual(cancel_res.structured_content["status"], "cancelled")

                # Test clean_jobs over MCP (deve limpar job_id (completed) e job_active_id (cancelled))
                clean_res = await client.call_tool("flow_clean_jobs", {"account_id": "conta-a"})
                self.assertFalse(clean_res.is_error)
                self.assertEqual(clean_res.structured_content["cleaned_count"], 2)
                self.assertFalse((jobs / f"{job_id}.json").exists())
                self.assertFalse((jobs / f"{job_active_id}.json").exists())

    def test_resolve_account_with_email_and_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root_path = Path(home)
            p1 = root_path / "profile_conta-x"
            p1.mkdir()
            (p1 / ".gflow_account").write_text("Pessoa@Example.com", encoding="utf-8")

            with patch("flow_mcp.root", root_path):
                # Email resolution is case-insensitive
                self.assertEqual(resolve_account("pessoa@example.com"), "conta-x")
                self.assertEqual(resolve_account("Pessoa@Example.com"), "conta-x")
                # Direct alias without '@' delegates to validate_account
                self.assertEqual(resolve_account("conta-x"), "conta-x")

                # Unknown email raises ValueError
                with self.assertRaises(ValueError):
                    resolve_account("desconhecido@example.com")

                # Duplicate email across two profiles raises ValueError
                p2 = root_path / "profile_conta-y"
                p2.mkdir()
                (p2 / ".gflow_account").write_text("pessoa@example.com", encoding="utf-8")
                with self.assertRaises(ValueError):
                    resolve_account("pessoa@example.com")

    async def test_run_account_operation_resolves_email_and_preserves_email_field(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            root_path = Path(home)
            p1 = root_path / "profile_conta-x"
            p1.mkdir()
            (p1 / ".gflow_account").write_text("pessoa@example.com", encoding="utf-8")

            with patch("flow_mcp.root", root_path), \
                 patch("flow_mcp._run_account_operation", AsyncMock(return_value={"status": "ok"})) as run_op:
                res = await run_account_operation("status", "pessoa@example.com")
                run_op.assert_awaited_once_with("status", "conta-x", None)
                self.assertEqual(res["status"], "ok")
                self.assertEqual(res["email"], "pessoa@example.com")

                # Existing email in result is not overwritten
                run_op.return_value = {"status": "ok", "email": "override@example.com"}
                res2 = await run_account_operation("status", "pessoa@example.com")
                self.assertEqual(res2["email"], "override@example.com")

                # Unknown email raises ToolError
                with self.assertRaises(ToolError):
                    await run_account_operation("status", "desconhecido@example.com")

    async def test_http_app_requires_bearer_token(self) -> None:
        from flow_mcp import http_app

        app = http_app("segredo")
        for headers in ([], [(b"authorization", b"Bearer errado")]):
            sent = []

            async def send(message):
                sent.append(message)

            await app({"type": "http", "path": "/mcp", "headers": headers}, AsyncMock(), send)
            self.assertEqual(sent[0]["status"], 401)

    async def test_local_jobs_are_read_in_process_with_clear_errors(self) -> None:
        from gflow_cli.config import get_settings
        from flow_mcp import flow_cancel_job

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home}):
            get_settings.cache_clear()
            try:
                profile = Path(home) / "profile_conta-x"
                profile.mkdir()
                (profile / ".gflow_account").write_text("pessoa@example.com", encoding="utf-8")
                job_id = str(uuid4())
                (Path(home) / "jobs").mkdir()
                (Path(home) / "jobs" / f"{job_id}.json").write_text(json.dumps(
                    {"job_id": job_id, "account_id": "conta-x", "kind": "image", "status": "submission_unknown"}))
                with patch("flow_mcp.root", Path(home)):
                    job = await run_account_operation("job", "pessoa@example.com", {"job_id": job_id})
                    self.assertEqual(job["status"], "submission_unknown")
                    self.assertIn("NÃO repita", job["next_step"])
                    listed = await run_account_operation("jobs", "conta-x", {"limit": 5})
                    self.assertEqual(listed["jobs"][0]["job_id"], job_id)
                    pending = await run_account_operation("jobs", "conta-x", {"limit": 5, "status": "pending"})
                    self.assertEqual([j["job_id"] for j in pending["jobs"]], [job_id])
                    done = await run_account_operation("jobs", "conta-x", {"limit": 5, "status": "completed"})
                    self.assertEqual(done["jobs"], [])
                    with self.assertRaises(ToolError) as ctx:
                        await run_account_operation("job", "conta-x", {"job_id": str(uuid4())})
                    self.assertIn("flow_list_jobs", str(ctx.exception))
                    self.assertEqual(flow_cancel_job("pessoa@example.com", job_id)["status"], "cancelled")
                    from flow_video import recover_job, save_job

                    unsent = {"job_id": str(uuid4()), "account_id": "conta-x", "kind": "video",
                              "video_id_schema": "media-workflow-v1", "status": "failed_pre_submit",
                              "project_id": None}
                    save_job(unsent)
                    recovered = await recover_job("conta-x", unsent["job_id"])
                    self.assertEqual(recovered["recovery_status"], "nothing_to_recover")
            finally:
                get_settings.cache_clear()

    async def test_account_listing_includes_keepalive_health_without_fingerprints(self) -> None:
        from flow_mcp import flow_list_accounts

        with tempfile.TemporaryDirectory() as home:
            state = Path(home) / "state.json"
            state.write_text(json.dumps({"ddv1": {"failures": 0, "last_ok": "t", "last_fp": "secretfp",
                                                  "needs_login": False, "rotations": 1}}))
            listing = {"accounts": [{"account_id": "ddv1"}, {"account_id": "ddv2"}]}
            with patch.dict(os.environ, {"FLOW_MCP_KEEPALIVE_STATE": str(state)}), \
                    patch("flow_mcp.run_account_operation", AsyncMock(return_value=listing)):
                result = await flow_list_accounts()
        self.assertFalse(result["accounts"][0]["keepalive"]["needs_login"])
        self.assertNotIn("secretfp", json.dumps(result))
        self.assertNotIn("keepalive", result["accounts"][1])

    async def test_operations_log_keeps_only_safe_fields(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            log = Path(home) / "ops.jsonl"
            reply = {"status": "http_error", "error": "Modelo inválido", "prompt": "segredo do usuário",
                     "files": ["/x"], "job_id": "j1"}
            with patch.dict(os.environ, {"FLOW_MCP_LOG": str(log)}), \
                    patch("flow_mcp._run_account_operation", AsyncMock(return_value=reply)):
                await run_account_operation("generate", "conta-a", {"prompt": "segredo do usuário"})
            entry = json.loads(log.read_text(encoding="utf-8"))
        self.assertEqual((entry["action"], entry["status"], entry["job_id"]), ("generate", "http_error", "j1"))
        self.assertNotIn("segredo", json.dumps(entry, ensure_ascii=False))

    def test_instructions_prompt_for_account_selection_before_spending_credits(self) -> None:
        self.assertIn("Antes de qualquer ferramenta que gaste créditos", INSTRUCTIONS)
        self.assertIn("Antes de qualquer ferramenta que gaste créditos", mcp.instructions)


if __name__ == "__main__":
    unittest.main()
