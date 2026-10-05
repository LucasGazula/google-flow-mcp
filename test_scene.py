"""Testes de extração de quadro, exportação GIF e montagem de cenas."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from uuid import uuid4
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

from flow_scene import save_video_frame, export_video_gif, build_scene, cancel_job, upscale_media, clean_jobs, manage_scene, export_scene, parse_scenes, list_scenes, parse_native_scene
from flow_video import save_job, get_job
from gflow_cli.config import get_settings
from gflow_cli.api.scene import Scene, SceneWorkflow, SceneWorkflowMetadata


class SceneTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_patch = patch.dict(os.environ, {
            "GFLOW_CLI_HOME": self.temp_dir.name,
            "FLOW_MCP_OUTPUT": self.temp_dir.name,
        })
        self.env_patch.start()
        get_settings.cache_clear()

    def tearDown(self):
        self.env_patch.stop()
        self.temp_dir.cleanup()
        get_settings.cache_clear()

    def test_native_scene_listing_includes_empty_scenes_and_rejects_unknown_shapes(self):
        project, scene = str(uuid4()), str(uuid4())
        row = [scene, "Empty scene", None, [1, 0], [1, 0], 2, None, []]
        payload = [None, [], [], [], [row], None, None, None]
        self.assertEqual(parse_scenes(payload, project), [{"scene_id":scene, "project_id":project, "title":"Empty scene", "archived":False}])
        payload[4] = [row[:7] + [[True]]]
        self.assertTrue(parse_scenes(payload, project)[0]["archived"])
        payload[4] = [row]
        for rows in ([row, row], [[scene, "title", None, None, None, True, None, []]], "bad"):
            payload[4] = rows
            with self.assertRaises(ValueError):
                parse_scenes(payload, project)
        payload[4] = None
        self.assertEqual(parse_scenes(payload, project), [])

    async def test_native_scene_search_is_incomplete_and_checks_account(self):
        project, scene = str(uuid4()), str(uuid4())
        row = [scene, "Cena vazia", None, [1, 0], [1, 0], 2, None, []]
        payload = [None, [], [], [], [row], None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=payload))
        result = await list_scenes("conta-a", project, "VAZIA", client=client)
        self.assertEqual(result["count"], 1)
        self.assertFalse(result["complete"])
        self.assertEqual((await list_scenes("conta-a", project, "missing", client=client))["count"], 0)
        with self.assertRaises(ValueError):
            await list_scenes("conta-b", project, client=client)

    def test_native_scene_composition_checks_video_project_order_and_trim(self):
        project, scene, workflow, media = (str(uuid4()) for _ in range(4))
        scene_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        workflow_row = [workflow, None, None, ["clip", [1, 0], None, None, media], project]
        metadata = [None, [4], [], [4], [1]]
        payload = [None, [], [], [], [scene_row], None, [[workflow_row, scene, metadata]], None]
        with patch("flow_assets.parse_assets", return_value=[{"media_id":media,"workflow_id":workflow,"kind":"video"}]):
            result = parse_native_scene(payload, project, scene)
            self.assertEqual(result.workflows[0].metadata, SceneWorkflowMetadata(0, 0, 4, 4))
            self.assertEqual(result.workflows[0].media_id, media)
            for invalid in ([True, [4], [], [4]], [0, [4], [4], [4]], [0, [4], [], [4, 1_000_000_000]]):
                payload[6] = [[workflow_row, scene, invalid]]
                with self.assertRaises(ValueError):
                    parse_native_scene(payload, project, scene)
            payload[6] = [[workflow_row, scene, metadata]] * 2
            with self.assertRaises(ValueError):
                parse_native_scene(payload, project, scene)
            payload[6] = [[workflow_row, scene, metadata]]
            workflow_row[4] = str(uuid4())
            with self.assertRaises(ValueError):
                parse_native_scene(payload, project, scene)
            workflow_row[4] = project
        with patch("flow_assets.parse_assets", return_value=[]):
            with self.assertRaises(ValueError):
                parse_native_scene(payload, project, scene)

    async def test_native_empty_scene_read_uses_only_project_query(self):
        project, scene = str(uuid4()), str(uuid4())
        row = [scene, "Empty scene", None, [1, 0], [1, 0], 2, None, []]
        payload = [None, [], [], [], [row], None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=payload))
        result = await manage_scene("conta-a", project, "read", scene_id=scene, client=client)
        self.assertEqual(result["clips"], [])
        self.assertFalse(result["complete"])
        client.rpc.assert_awaited_once_with("Zzl0ze", project_id=project)
        with self.assertRaises(ValueError):
            await manage_scene("conta-a", project, "read", scene_id=str(uuid4()), client=client)

    async def test_scene_add_sends_once_and_confirms_by_readback(self):
        project, scene, workflow, media = (str(uuid4()) for _ in range(4))
        scene_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        clone, clone_media = str(uuid4()), str(uuid4())
        workflow_row = [clone, None, None, ["clip", [1, 0], None, None, clone_media, media], project]
        before = [None, [], [], [], [scene_row], None, None, None]
        after = [None, [], [], [], [scene_row], None, [[workflow_row, scene, [None, [4], [], [4], [1]]]], None]
        assets = [{"media_id":media, "workflow_id":workflow, "kind":"video"},
                  {"media_id":clone_media, "workflow_id":clone, "kind":"video"}]
        with patch("flow_assets.parse_assets", return_value=assets):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, after]))
            result = await manage_scene("conta-a", project, "add", scene_id=scene,
                                        workflow_ids=[workflow], client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["added_workflow_ids"], [clone])
            self.assertEqual(result["clips"][0]["workflow_id"], clone)
            client.rpc.assert_any_await("oWTRd", params=[project, scene, [workflow], 0])
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, before, after]))
            with patch("flow_scene.asyncio.sleep", AsyncMock()):
                result = await manage_scene("conta-a", project, "add", scene_id=scene,
                                            workflow_ids=[workflow], client=client)
                self.assertEqual(result["status"], "updated")
                for mutation in (TimeoutError("private"), {}):
                    client = SimpleNamespace(account_id="conta-a",
                        rpc=AsyncMock(side_effect=[before, mutation] + [before] * 6))
                    result = await manage_scene("conta-a", project, "add", scene_id=scene,
                                                workflow_ids=[workflow], client=client)
                    self.assertEqual(result["status"], "submission_unknown")
                    self.assertFalse(result["retry_automatically"])
                    self.assertNotIn("private", str(result))
                    self.assertEqual([call.args[0] for call in client.rpc.await_args_list].count("oWTRd"), 1)
            for payload, ids, position in ((before, [str(uuid4())], None), (before, [workflow], 1)):
                client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=payload))
                result = await manage_scene("conta-a", project, "add", scene_id=scene,
                                            workflow_ids=ids, position=position, client=client)
                self.assertEqual(result["status"], "failed_pre_submit")
                client.rpc.assert_awaited_once_with("Zzl0ze", project_id=project)
        with self.assertRaises(ValueError):
            await manage_scene("conta-a", project, "add", scene_id=scene, workflow_ids=[workflow, workflow])

    async def test_native_scene_wrong_project_capture_blocks_http_submission(self):
        project = str(uuid4())
        @asynccontextmanager
        async def page_context():
            yield SimpleNamespace(goto=AsyncMock(), get_by_role=lambda *args, **kwargs: SimpleNamespace(click=AsyncMock()))
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[None, [], [], [], [], None, None, None]),
            browser=SimpleNamespace(page=page_context),
            capture_submit=AsyncMock(return_value={"rpc_id":"rqZuUc", "params":[f"projects/{uuid4()}",None,None,None,2]}),
            send_submit=AsyncMock())
        result = await manage_scene("conta-a", project, "create", client=client)
        self.assertEqual(result["status"], "failed_pre_submit")
        client.send_submit.assert_not_awaited()

    async def test_native_empty_scene_is_saved_before_single_submission_and_reconciled(self):
        project, scene = str(uuid4()), str(uuid4())
        row = [scene, "Empty scene", None, [1, 0], [1, 0], 2, None, []]
        initial = [None, [], [], [], [], None, None, None]
        final = [None, [], [], [], [row], None, None, None]
        @asynccontextmanager
        async def page_context():
            yield page
        page = SimpleNamespace(goto=AsyncMock(),
            get_by_role=lambda *args, **kwargs: SimpleNamespace(click=AsyncMock()))
        captured = {"rpc_id":"rqZuUc", "params":[f"projects/{project}", None, None, None, 2]}
        async def send(packet):
            self.assertEqual(packet, captured)
            page.goto.assert_awaited_once()
            jobs = list((Path(self.temp_dir.name) / "jobs").glob("*.json"))
            self.assertEqual(json.loads(jobs[0].read_text())["status"], "submitting")
            return [row]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[initial, final]),
            browser=SimpleNamespace(page=page_context), capture_submit=AsyncMock(return_value=captured),
            send_submit=AsyncMock(side_effect=send))
        result = await manage_scene("conta-a", project, "create", client=client)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["scene_id"], scene)
        self.assertEqual(get_job("conta-a", result["job_id"])["status"], "completed")
        client.send_submit.assert_awaited_once()

    async def test_native_scene_unknown_submission_and_readback_never_resubmit(self):
        project, scene = str(uuid4()), str(uuid4())
        row = [scene, "Empty scene", None, [1, 0], [1, 0], 2, None, []]
        initial = [None, [], [], [], [], None, None, None]
        @asynccontextmanager
        async def page_context():
            yield SimpleNamespace(goto=AsyncMock(),
                get_by_role=lambda *args, **kwargs: SimpleNamespace(click=AsyncMock()))
        captured = {"rpc_id":"rqZuUc", "params":[f"projects/{project}", None, None, None, 2]}
        for mutation, readback in ((TimeoutError("private"), initial), ([row], initial)):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[initial, readback]),
                browser=SimpleNamespace(page=page_context), capture_submit=AsyncMock(return_value=captured),
                send_submit=AsyncMock(side_effect=mutation if isinstance(mutation, Exception) else None,
                                      return_value=mutation))
            result = await manage_scene("conta-a", project, "create", workflow_ids=[], client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertFalse(result["retry_automatically"])
            self.assertNotIn("private", str(result))
            client.send_submit.assert_awaited_once()

    async def test_scene_update_sends_full_order_once_and_confirms_trim(self):
        project, scene = str(uuid4()), str(uuid4())
        first, second, media_a, media_b = (str(uuid4()) for _ in range(4))
        scene_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        def row(workflow, media, metadata):
            return [[workflow, None, None, ["clip", [1, 0], None, None, media], project], scene, metadata]
        def payload(*rows):
            return [None, [], [], [], [scene_row], None, list(rows), None]
        before = payload(row(first, media_a, [None, [8], [], [8]]), row(second, media_b, [1, [8], [], [8]]))
        after = payload(row(second, media_b, [None, [8], [], [8]]),
                        row(first, media_a, [1, [8], [None, 500000000], [6, 9803922]]))
        assets = [{"media_id":media_a, "workflow_id":first, "kind":"video"},
                  {"media_id":media_b, "workflow_id":second, "kind":"video"}]
        order = [{"workflow_id":second}, {"workflow_id":first, "start_time":0.5, "end_time":6.009803922}]
        expected = [project, scene, [
            [[second, None, None, [None, None, None, None, media_b]], scene, [None, [8], [], [8]]],
            [[first, None, None, [None, None, None, None, media_a]], scene, [1, [8], [None, 500000000], [6, 9803922]]]]]
        with patch("flow_assets.parse_assets", return_value=assets), \
                patch("flow_scene.asyncio.sleep", AsyncMock()):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, before, after]))
            result = await manage_scene("conta-a", project, "update", scene_id=scene, clips=order, client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual([clip["workflow_id"] for clip in result["clips"]], [second, first])
            client.rpc.assert_any_await("GoMJte", params=expected)
            client = SimpleNamespace(account_id="conta-a",
                rpc=AsyncMock(side_effect=[before, TimeoutError("private")] + [before] * 6))
            result = await manage_scene("conta-a", project, "update", scene_id=scene, clips=order, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertNotIn("private", str(result))
            self.assertEqual([call.args[0] for call in client.rpc.await_args_list].count("GoMJte"), 1)
            for clips in ([{"workflow_id":first}], order[:1] + [{"workflow_id":first, "end_time":9}]):
                client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=before))
                result = await manage_scene("conta-a", project, "update", scene_id=scene, clips=clips, client=client)
                self.assertEqual(result["status"], "failed_pre_submit")
                client.rpc.assert_awaited_once_with("Zzl0ze", project_id=project)

    async def test_scene_create_with_clips_creates_empty_then_adds(self):
        project, scene, workflow = str(uuid4()), str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a")
        created = {"job_id":"c", "status":"created", "scene_id":scene, "title":"T"}
        with patch("flow_scene._create_empty_scene", AsyncMock(return_value=created)), \
                patch("flow_scene._add_scene_clips", AsyncMock(return_value={"status":"updated", "clips":[]})) as add:
            result = await manage_scene("conta-a", project, "create", workflow_ids=[workflow], client=client)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["create_job_id"], "c")
        add.assert_awaited_once_with(client, project, scene, [workflow], None)

    async def test_scene_export_uses_native_rpcs_once_and_saves_mp4(self):
        import base64
        project, scene, workflow, media = (str(uuid4()) for _ in range(4))
        scene_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        workflow_row = [workflow, None, None, ["clip", [1, 0], None, None, media], project]
        payload = [None, [], [], [], [scene_row], None,
                   [[workflow_row, scene, [None, [8], [None, 500000000], [6, 250000000]]]], None]
        assets = [{"media_id":media, "workflow_id":workflow, "kind":"video"}]
        video_bytes = b"\x00\x00\x00\x00ftypvideo"
        encoded = base64.b64encode(video_bytes).decode()
        bad_encoded = base64.b64encode(b"not-mp4").decode()
        expected = [[[media, None, [None, 500000000], [6, 250000000]]]]

        with patch("flow_assets.parse_assets", return_value=assets), \
                patch("flow_scene.asyncio.sleep", AsyncMock()):
            client = SimpleNamespace(account_id="conta-a",
                rpc=AsyncMock(side_effect=[payload, [None, [["op1"]]], [2], [3, "", "", 5, encoded]]))
            result = await export_scene("conta-a", project, scene, client=client)
            self.assertEqual(result["status"], "exported")
            self.assertEqual(Path(result["path"]).read_bytes(), video_bytes)
            client.rpc.assert_any_await("GjQLTd", params=expected)
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("GjQLTd"), 1)

            client = SimpleNamespace(account_id="conta-a",
                rpc=AsyncMock(side_effect=[payload, [None, [["op1"]]], [3, "", "", 5, bad_encoded]]))
            result = await export_scene("conta-a", project, scene, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertEqual(result["files"], [])
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("GjQLTd"), 1)

            client = SimpleNamespace(account_id="conta-a",
                rpc=AsyncMock(side_effect=[payload, TimeoutError("private")]))
            result = await export_scene("conta-a", project, scene, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertNotIn("private", str(result))

    async def test_scene_remove_resends_remaining_clips_once(self):
        project, scene = str(uuid4()), str(uuid4())
        first, second, media_a, media_b = (str(uuid4()) for _ in range(4))
        scene_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        def row(workflow, media, metadata):
            return [[workflow, None, None, ["clip", [1, 0], None, None, media], project], scene, metadata]
        before = [None, [], [], [], [scene_row], None, [
            row(first, media_a, [None, [8], [], [8]]),
            row(second, media_b, [1, [8], [None, 500000000], [6, 250000000]])], None]
        after = [None, [], [], [], [scene_row], None, [
            row(second, media_b, [None, [8], [None, 500000000], [6, 250000000]])], None]
        assets = [{"media_id":media_a, "workflow_id":first, "kind":"video"},
                  {"media_id":media_b, "workflow_id":second, "kind":"video"}]
        expected = [project, scene, [
            [[second, None, None, [None, None, None, None, media_b]], scene,
             [None, [8], [None, 500000000], [6, 250000000]]]]]

        with patch("flow_assets.parse_assets", return_value=assets), \
                patch("flow_scene.asyncio.sleep", AsyncMock()):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, before, after]))
            result = await manage_scene("conta-a", project, "remove", scene_id=scene,
                                        workflow_ids=[first], client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(len(result["clips"]), 1)
            self.assertEqual(result["clips"][0]["workflow_id"], second)
            client.rpc.assert_any_await("GoMJte", params=expected)
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("GoMJte"), 1)

            emptied = [None, [], [], [], [scene_row], None, [], None]
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, emptied]))
            result = await manage_scene("conta-a", project, "remove", scene_id=scene,
                                        workflow_ids=[first, second], client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["clips"], [])
            client.rpc.assert_any_await("GoMJte", params=[project, scene])

    async def test_scene_rename_and_archive_confirm_by_listing(self):
        project, scene = str(uuid4()), str(uuid4())
        old_row = [scene, "Old Title", None, [1, 0], [1, 0], 2, None, []]
        new_row = [scene, "New Title", None, [1, 0], [1, 0], 2, None, []]
        before = [None, [], [], [], [old_row], None, None, None]
        renamed = [None, [], [], [], [new_row], None, None, None]
        archived = [None, [], [], [], [[scene, "Old Title", None, [1, 0], [1, 0], 2, None, [True]]], None, None, None]
        rename_params = [project, scene, [None, "New Title"], [["display_name"]]]
        archive_params = [project, scene, [scene, None, None, None, None, None, None, [1]],
                          [["scene_metadata.is_archived", "parent_collection_id"]]]

        with patch("flow_scene.asyncio.sleep", AsyncMock()):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, before, renamed]))
            result = await manage_scene("conta-a", project, "rename", scene_id=scene, title="  New Title  ", client=client)
            self.assertEqual(result["status"], "updated")
            self.assertEqual(result["title"], "New Title")
            client.rpc.assert_any_await("BpMsoe", params=rename_params)

            with self.assertRaises(ValueError):
                await manage_scene("conta-a", project, "archive", scene_id=scene, confirm=False, client=client)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}] + [before] * 6))
            result = await manage_scene("conta-a", project, "archive", scene_id=scene, confirm=True, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertFalse(result["retry_automatically"])
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("BpMsoe"), 1)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[before, {}, archived]))
            result = await manage_scene("conta-a", project, "archive", scene_id=scene, confirm=True, client=client)
            self.assertEqual(result["status"], "updated")
            client.rpc.assert_any_await("BpMsoe", params=archive_params)

    async def test_scene_restore_and_permanent_delete(self):
        project, scene = str(uuid4()), str(uuid4())
        active_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, []]
        archived_row = [scene, "Scene", None, [1, 0], [1, 0], 2, None, [True]]
        active = [None, [], [], [], [active_row], None, None, None]
        archived = [None, [], [], [], [archived_row], None, None, None]
        empty = [None, [], [], [], [], None, None, None]
        restore_params = [project, scene, [scene, None, None, None, None, None, None, []],
                          [["scene_metadata.is_archived", "parent_collection_id"]]]
        delete_params = [None, None, project, None, [scene]]

        with patch("flow_scene.asyncio.sleep", AsyncMock()):
            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[archived, {}, active]))
            result = await manage_scene("conta-a", project, "restore", scene_id=scene, client=client)
            self.assertEqual(result["status"], "updated")
            client.rpc.assert_any_await("BpMsoe", params=restore_params)

            with self.assertRaises(ValueError):
                await manage_scene("conta-a", project, "delete", scene_id=scene, confirm=False, client=client)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=active))
            result = await manage_scene("conta-a", project, "delete", scene_id=scene, confirm=True, client=client)
            self.assertEqual(result["status"], "failed_pre_submit")
            client.rpc.assert_awaited_once_with("Zzl0ze", project_id=project)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[archived, {}, empty]))
            result = await manage_scene("conta-a", project, "delete", scene_id=scene, confirm=True, client=client)
            self.assertEqual(result["status"], "deleted")
            client.rpc.assert_any_await("cz8Z4b", params=delete_params)

            client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[archived, {}] + [archived] * 6))
            result = await manage_scene("conta-a", project, "delete", scene_id=scene, confirm=True, client=client)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("cz8Z4b"), 1)

    async def test_save_video_frame_validates_inputs(self):
        project = str(uuid4())
        media = str(uuid4())
        for bad_time in [-1, -0.1, "zero"]:
            with self.assertRaises(ValueError):
                await save_video_frame("conta-a", project, media, bad_time)

    async def test_save_video_frame_extracts_and_optionally_uploads(self):
        project = str(uuid4())
        media = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        # Criar dummy video local
        dummy_video = Path(self.temp_dir.name) / f"{media}.mp4"
        dummy_video.write_bytes(b"dummy_mp4_bytes")

        async def fake_proc(*args, **kwargs):
            # Cria o frame no target esperado
            target = args[-1]
            Path(target).write_bytes(b"\x89PNGdummy")
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc), \
             patch("flow_assets.upload_image", new_callable=AsyncMock) as mock_upload:
            mock_upload.return_value = {"media_id": str(uuid4()), "status": "uploaded"}

            # Sem upload
            res = await save_video_frame("conta-a", project, media, 2.5, upload_to_flow=False, client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["timestamp_seconds"], 2.5)
            self.assertTrue(Path(res["frame_path"]).exists())
            mock_upload.assert_not_called()

            # Com upload
            res2 = await save_video_frame("conta-a", project, media, 1.0, upload_to_flow=True, client=client)
            self.assertEqual(res2["status"], "ok")
            mock_upload.assert_awaited_once()
            self.assertIn("flow_upload", res2)

    async def test_export_video_gif_validates_and_executes(self):
        project = str(uuid4())
        media = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        dummy_video = Path(self.temp_dir.name) / f"{media}.mp4"
        dummy_video.write_bytes(b"dummy_mp4_bytes")

        with self.assertRaises(ValueError):
            await export_video_gif("conta-a", project, media, fps=0, client=client)
        with self.assertRaises(ValueError):
            await export_video_gif("conta-a", project, media, width=50, client=client)

        async def fake_proc(*args, **kwargs):
            target = args[-1]
            Path(target).write_bytes(b"GIF89adummy")
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc):
            res = await export_video_gif("conta-a", project, media, start_time=0.5, duration=3.0, fps=12, width=360, client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["fps"], 12)
            self.assertEqual(res["width"], 360)
            self.assertTrue(Path(res["gif_path"]).exists())

    async def test_build_scene_concatenates_multiple_clips(self):
        project = str(uuid4())
        media1 = str(uuid4())
        media2 = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        (Path(self.temp_dir.name) / f"{media1}.mp4").write_bytes(b"clip1")
        (Path(self.temp_dir.name) / f"{media2}.mp4").write_bytes(b"clip2")

        with self.assertRaises(ValueError):
            await build_scene("conta-a", project, [], client=client)

        with self.assertRaises(ValueError):
            await build_scene("conta-a", project, [{"media_id": media1, "trim_start": 5.0, "trim_end": 2.0}], client=client)

        captured_args = []
        async def fake_proc(*args, **kwargs):
            captured_args.extend(args)
            target = args[-1]
            Path(target).write_bytes(b"dummy_scene_mp4")
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc):
            clips = [
                {"media_id": media1, "trim_start": 0.0, "trim_end": 4.0},
                {"media_id": media2, "trim_start": 1.0, "trim_end": 5.0},
            ]
            res = await build_scene("conta-a", project, clips, scene_title="Batalha Espacial", client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["clip_count"], 2)
            self.assertEqual(res["title"], "Batalha Espacial")
            self.assertTrue(Path(res["scene_path"]).exists())
            self.assertIn("concat=n=2:v=1:a=1[outv][outa]", " ".join(captured_args))

    async def test_build_scene_audio_and_silent_clips(self):
        project = str(uuid4())
        media_audio = str(uuid4())
        media_silent = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        (Path(self.temp_dir.name) / f"{media_audio}.mp4").write_bytes(b"clip_with_audio")
        (Path(self.temp_dir.name) / f"{media_silent}.mp4").write_bytes(b"clip_silent")

        captured_args = []
        async def fake_proc(*args, **kwargs):
            cmd_str = " ".join(args)
            proc = MagicMock()
            proc.returncode = 0
            if "ffprobe" in args[0] and "-select_streams" in args:
                # Se for o media_audio, finge que tem audio
                if media_audio in cmd_str:
                    proc.communicate = AsyncMock(return_value=(b"audio\n", b""))
                else:
                    proc.communicate = AsyncMock(return_value=(b"\n", b""))
                return proc
            if "ffprobe" in args[0] and "format=duration" in args:
                proc.communicate = AsyncMock(return_value=(b"3.500\n", b""))
                return proc
            captured_args.extend(args)
            target = args[-1]
            Path(target).write_bytes(b"dummy_scene_mp4")
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc):
            clips = [
                {"media_id": media_audio, "trim_start": 0.0, "trim_end": 2.0},
                {"media_id": media_silent},
            ]
            res = await build_scene("conta-a", project, clips, client=client)
            self.assertEqual(res["status"], "ok")
            all_cmd = " ".join(captured_args)
            # Clip 0 tem audio -> usa aformat
            self.assertIn("[0:a]aformat=sample_rates=44100", all_cmd)
            # Clip 1 nao tem audio -> usa aevalsrc com duracao de ffprobe (3.5s)
            self.assertIn("aevalsrc=0:d=3.500,aformat=sample_rates=44100", all_cmd)

    def test_cancel_job(self):
        job_id = str(uuid4())
        save_job({"job_id": job_id, "account_id": "conta-a", "status": "preparing"})
        res = cancel_job("conta-a", job_id)
        self.assertEqual(res["status"], "cancelled")
        self.assertEqual(get_job("conta-a", job_id)["status"], "cancelled")

        # Job já completado não muda
        job2 = str(uuid4())
        save_job({"job_id": job2, "account_id": "conta-a", "status": "completed"})
        res2 = cancel_job("conta-a", job2)
        self.assertEqual(res2["status"], "completed")
        self.assertEqual(get_job("conta-a", job2)["status"], "completed")

        # Job inexistente levanta ValueError
        with self.assertRaises(ValueError):
            cancel_job("conta-a", str(uuid4()))

    async def test_upscale_media_validates_inputs(self):
        project = str(uuid4())
        media = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())
        for bad_res in ["144p", "8k", "ultra", ""]:
            with self.assertRaises(ValueError):
                await upscale_media("conta-a", project, media, target_resolution=bad_res, client=client)

    async def test_upscale_media_video(self):
        project = str(uuid4())
        media = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        dummy_video = Path(self.temp_dir.name) / f"{media}.mp4"
        dummy_video.write_bytes(b"dummy_video_bytes")

        captured_cmd = []
        async def fake_proc(*args, **kwargs):
            captured_cmd.extend(args)
            target = args[-1]
            Path(target).write_bytes(b"upscaled_video_mp4")
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc):
            res = await upscale_media("conta-a", project, media, target_resolution="1080p", client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["kind"], "video")
            self.assertEqual(res["target_resolution"], "1080p")
            self.assertTrue(Path(res["output_path"]).exists())
            cmd_str = " ".join(captured_cmd)
            self.assertIn("scale='if(gte(a,1),1920,-2)':'if(gte(a,1),-2,1920)':flags=lanczos,unsharp", cmd_str)

    async def test_upscale_video_upload_uses_existing_rights_confirmation(self):
        project, media = str(uuid4()), str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())
        source = Path(self.temp_dir.name) / f"{media}.mp4"
        source.write_bytes(b"video")

        async def fake_proc(*args, **kwargs):
            Path(args[-1]).write_bytes(b"upscaled_video")
            proc = MagicMock(returncode=0)
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        pending = {"kind":"video", "status":"confirmation_required",
                   "confirmation_id":"pending", "project_id":project}
        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc), \
             patch("flow_assets.upload_asset", new_callable=AsyncMock,
                   return_value=pending) as upload:
            result = await upscale_media("conta-a", project, media, target_resolution="720p",
                                         upload_to_flow=True, client=client)

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["kind"], "video")
        self.assertEqual(result["flow_upload"], pending)
        self.assertEqual(result["flow_upload_status"], "confirmation_required")
        self.assertNotIn("asset_media_id", result)
        upload.assert_awaited_once_with(
            "conta-a", project, result["output_path"], client=client)

    async def test_upscale_media_image_and_upload(self):
        project = str(uuid4())
        media = str(uuid4())
        client = MagicMock(account_id="conta-a", close=AsyncMock())

        dummy_img = Path(self.temp_dir.name) / f"{media}.png"
        dummy_img.write_bytes(b"\x89PNGdummyimage")

        captured_cmd = []
        async def fake_proc(*args, **kwargs):
            captured_cmd.extend(args)
            target = args[-1]
            Path(target).write_bytes(b"\x89PNGupscaledimage")
            proc = MagicMock()
            proc.returncode = 0
            proc.communicate = AsyncMock(return_value=(b"", b""))
            return proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_proc), \
             patch("flow_assets.upload_image", new_callable=AsyncMock) as mock_upload:
            uploaded_id = str(uuid4())
            mock_upload.return_value = {"media_id": uploaded_id, "status": "uploaded"}

            res = await upscale_media("conta-a", project, media, target_resolution="4k", upload_to_flow=True, client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["kind"], "image")
            self.assertEqual(res["target_resolution"], "4k")
            self.assertEqual(res["asset_media_id"], uploaded_id)
            self.assertIn("flow_upload", res)
            mock_upload.assert_awaited_once()
            cmd_str = " ".join(captured_cmd)
            self.assertIn("scale='if(gte(a,1),3840,-2)':'if(gte(a,1),-2,3840)':flags=lanczos,unsharp", cmd_str)

    def test_clean_jobs(self):
        job1 = str(uuid4())
        job2 = str(uuid4())
        job3 = str(uuid4())
        save_job({"job_id": job1, "account_id": "conta-a", "status": "completed"})
        save_job({"job_id": job2, "account_id": "conta-a", "status": "cancelled"})
        save_job({"job_id": job3, "account_id": "conta-a", "status": "submitting"})

        # Limpa default: completed e cancelled
        res = clean_jobs("conta-a")
        self.assertEqual(res["cleaned_count"], 2)
        self.assertEqual(res["remaining_count"], 1)

        # Job ativo permanece
        self.assertEqual(get_job("conta-a", job3)["status"], "submitting")

        # Teste com filtro "failed" e "uncertain" (aliases que mapeiam para status reais de job)
        job_fail = str(uuid4())
        job_unc = str(uuid4())
        save_job({"job_id": job_fail, "account_id": "conta-a", "status": "failed_pre_submit"})
        save_job({"job_id": job_unc, "account_id": "conta-a", "status": "submission_unknown"})

        res_fail = clean_jobs("conta-a", status_filter="failed")
        self.assertEqual(res_fail["cleaned_count"], 1)
        self.assertIn("failed_pre_submit", res_fail["target_statuses"])

        res_unc = clean_jobs("conta-a", status_filter="uncertain")
        self.assertEqual(res_unc["cleaned_count"], 1)
        self.assertIn("submission_unknown", res_unc["target_statuses"])

        # Filtro inválido
        with self.assertRaises(ValueError):
            clean_jobs("conta-a", status_filter="invalid_status")


if __name__ == "__main__":
    unittest.main()
