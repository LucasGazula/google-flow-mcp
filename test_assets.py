import unittest
import base64
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from flow_assets import parse_assets, media_revision, delete_asset


class HTTPUploadTest(unittest.IsolatedAsyncioTestCase):
    async def test_archive_asset_requires_confirmation_and_sends_native_trash_once(self):
        project, media, workflow = str(uuid4()), str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[]))
        listed = [{"media_id": media, "workflow_id": workflow, "kind": "video"}]
        with patch("flow_assets.parse_assets", side_effect=[listed, [{**listed[0], "archived": True}]]):
            guarded = await delete_asset("conta-a", project, media, client=client)
            self.assertEqual(guarded["status"], "confirmation_required")
            client.rpc.assert_not_awaited()
            result = await delete_asset("conta-a", project, media, confirm_delete=True, client=client)
        self.assertEqual(result["status"], "archived")
        client.rpc.assert_any_await("pGCYOe", params=[[[workflow, None, None, [None, None, 1], project]],
                                                      [["metadata.archived"]]])
        self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("pGCYOe"), 1)

    async def test_archive_asset_unconfirmed_is_not_retried(self):
        project, media, workflow = str(uuid4()), str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[]))
        listed = [{"media_id": media, "workflow_id": workflow, "kind": "image", "archived": False}]
        with patch("asyncio.sleep", AsyncMock()), patch("flow_assets.parse_assets", return_value=listed):
            result = await delete_asset("conta-a", project, media, confirm_delete=True, client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual([c.args[0] for c in client.rpc.await_args_list].count("pGCYOe"), 1)

    async def test_video_upload_requires_human_terms_or_confirms_one_new_asset(self):
        from flow_assets import confirm_video_upload, upload_asset

        project, media = str(uuid4()), str(uuid4())
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "clip.mp4"
            source.write_bytes(b"video")
            for dialog_count, expected in ((1, "confirmation_required"), (0, "uploaded")):
                chooser = SimpleNamespace(set_files=AsyncMock())
                page = SimpleNamespace(goto=AsyncMock())
                button = SimpleNamespace(click=AsyncMock())
                page.locator = lambda selector: SimpleNamespace(first=button,
                    all_inner_texts=AsyncMock(return_value=["Direitos de uso deste vídeo"] if dialog_count else []))

                @asynccontextmanager
                async def chooser_context():
                    yield SimpleNamespace(value=AsyncMock(return_value=chooser)())

                @asynccontextmanager
                async def page_context():
                    yield page

                page.expect_file_chooser = lambda **kwargs: chooser_context()
                browser = SimpleNamespace(page=page_context)
                client = SimpleNamespace(account_id="conta-a", browser=browser,
                                         pending_upload=None, rpc=AsyncMock())
                seen = [] if dialog_count else [
                    {"media_id": media, "kind": "video", "name": source.stem}]
                with patch("flow_assets.parse_assets", side_effect=[[], seen]):
                    result = await upload_asset("conta-a", project, str(source), client=client)
                self.assertEqual(result["status"], expected)
                if dialog_count:
                    self.assertIsNotNone(client.pending_upload)
                    denied = await confirm_video_upload("conta-a", result["confirmation_id"], False,
                                                       client=client)
                    self.assertEqual(denied["status"], "cancelled")
                    self.assertIsNone(client.pending_upload)
                else:
                    self.assertEqual(result["media_id"], media)
                chooser.set_files.assert_awaited_once_with(str(source))

    async def test_confirm_upload_needs_matching_pending_id_and_clicks_once(self):
        from flow_assets import confirm_video_upload

        page = SimpleNamespace(locator=lambda selector: SimpleNamespace(
            all_inner_texts=AsyncMock(return_value=["Direitos de uso deste vídeo"])))
        button = SimpleNamespace(click=AsyncMock())
        page.get_by_role = lambda *args, **kwargs: button
        context = SimpleNamespace(__aexit__=AsyncMock())
        pending = {"confirmation_id": "pending-token", "page_context": context,
                   "page": page, "project_id": "project", "name": "clip.mp4", "before": set()}
        client = SimpleNamespace(account_id="conta-a", pending_upload=pending)
        with self.assertRaises(ValueError):
            await confirm_video_upload("conta-a", "wrong-token", True, client=client)
        button.click.assert_not_awaited()
        with patch("flow_assets._uploaded_video", AsyncMock(return_value={
            "status": "uploaded", "kind": "video", "media_id": str(uuid4())})):
            result = await confirm_video_upload("conta-a", "pending-token", True, client=client)
        self.assertEqual(result["status"], "uploaded")
        button.click.assert_awaited_once()
        context.__aexit__.assert_awaited_once()
        self.assertIsNone(client.pending_upload)

    async def test_upload_closes_browser_checks_exact_bytes_and_never_retries(self):
        from flow_assets import upload_image
        from flow_http import FlowHTTP

        project, media, workflow = (str(uuid4()) for _ in range(3))
        async def send(captured):
            self.assertEqual(captured["rpc_id"],"maseQ")
            params=captured["params"]
            self.assertEqual(params[0][5],project)
            self.assertEqual(params[0][10],["captcha",1])
            self.assertEqual(base64.b64decode(params[1]),body)
            self.assertEqual(params[2],"image/png")
            self.assertEqual(params[8],"unique.png")
            return [[media, project, workflow, "CAE"]]

        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "input.png"
            body = b"\x89PNG\r\n\x1a\nimage"
            source.write_bytes(body)
            with patch("gflow_cli.api.client.validate_image_file", AsyncMock()), \
                 patch("gflow_cli.api.transports.migrated_composer._unique_display_name", return_value="unique.png"), \
                 patch("flow_requests._seed",side_effect=lambda: next(seeds)), \
                 patch.object(FlowHTTP,"prepare",AsyncMock(return_value="captcha")) as prepare, \
                 patch.object(FlowHTTP,"request",side_effect=lambda rpc,params: {"rpc_id":rpc,"params":params}), \
                 patch.object(FlowHTTP,"capture_submit",AsyncMock(side_effect=AssertionError("No compositor"))), \
                 patch.object(FlowHTTP,"close",AsyncMock()), \
                 patch.object(FlowHTTP, "send_submit", AsyncMock(side_effect=send)) as submit:
                seeds=iter([("seed",media),("seed",workflow)])
                result = await upload_image("conta-a", project, str(source))
                self.assertEqual(result["media_id"], media)
                self.assertEqual(result["source"], "HTTP/maseQ")
                submit.assert_awaited_once()
                prepare.assert_awaited_once_with("Zzl0ze",project_id=project,captcha_action="UPLOAD_IMAGE")
                submit.reset_mock()
                seeds=iter([("seed",media),("seed",workflow)])
                prepare.side_effect=ValueError("Missing authentication")
                with self.assertRaises(ValueError):
                    await upload_image("conta-a", project, str(source))
                submit.assert_not_awaited()
                prepare.side_effect=None
                submit.side_effect = TimeoutError("private session")
                result = await upload_image("conta-a", project, str(source))
                self.assertEqual(result["status"], "submission_unknown")
                self.assertEqual(result["request_media_ids"],[media])
                submit.assert_awaited_once()
                self.assertNotIn("private session", str(result))
                seeds=iter([("seed",media),("seed",workflow)])
                submit.reset_mock()
                submit.side_effect=None
                submit.return_value=[[str(uuid4()),project,workflow,"CAE"]]
                result=await upload_image("conta-a", project, str(source))
                self.assertEqual(result["status"],"submission_unknown")
                submit.assert_awaited_once()


class AssetTest(unittest.TestCase):
    def test_native_upscaled_image_can_omit_dimensions(self):
        project, image, workflow = (str(uuid4()) for _ in range(3))
        info = [None] * 17
        info[13], info[14], info[16] = "https://lh3.googleusercontent.com/test", 1, [None, 1]
        row = [image, project, workflow, "CAE", None, [None] * 14, [info]]
        payload = [None, [], [row], [], None, None, None, []]
        asset = parse_assets(payload, project)[0]
        self.assertEqual(asset["kind"], "image")
        self.assertIsNone(asset["dimensions"])
        self.assertEqual(asset["media_id"], image)
        from flow_edit import asset_details
        with patch("gflow_cli.api.transports.batchexecute.image_records", return_value=[]):
            details = asset_details(payload, "conta-a", project, image)
        self.assertIsNone(details["versions"][0]["dimensions"])
        for malformed in ([], [None], [[None] * 17]):
            row[6] = malformed
            with self.assertRaises(ValueError):
                parse_assets(payload, project)

    def test_image_ids_are_not_swapped_with_video_workflow_ids(self):
        project, image, workflow = (str(uuid4()) for _ in range(3))
        row = [image, project, workflow, "CAE", None, [None] * 14,
               [None, None, [1024, 768]]]
        payload = [None, [[workflow, "collection-a", None, ["Imagem"], project]], [row], [], None, None, None, []]
        assets = parse_assets(payload, project)
        self.assertEqual(assets[0]["media_id"], image)
        self.assertEqual(assets[0]["workflow_id"], workflow)
        self.assertEqual(assets[0]["kind"], "image")
        self.assertEqual(assets[0]["name"], "Imagem")
        self.assertEqual(assets[0]["collection_id"], "collection-a")
        self.assertNotIn("url", assets[0])
        row[3] = "CAI"
        edited = parse_assets(payload, project)
        self.assertEqual(edited[0]["kind"], "image")
        self.assertEqual(edited[0]["workflow_id"], workflow)
        for marker,revision in (("CAE",1),("CAI",2),("CAM",3),("CAQ",4),("CIAB",128)):
            row[3]=marker
            self.assertEqual(parse_assets(payload,project)[0]["revision"],revision)
        for marker in ("CAA","CAEA","invalid",None):
            with self.assertRaises(ValueError):
                media_revision(marker)
        row[3] = "unknown"
        with self.assertRaises(ValueError):
            parse_assets(payload, project)
        row[3] = "CAE"
        for invalid in (None, [], [None, [], []]):
            with self.assertRaises(ValueError):
                parse_assets(invalid, project)
        with self.assertRaises(ValueError):
            parse_assets(payload, str(uuid4()))

    def test_parse_assets_marks_archived_based_on_workflow_metadata(self):
        project, image1, wf1, image2, wf2 = (str(uuid4()) for _ in range(5))
        row1 = [image1, project, wf1, "CAE", None, [None] * 14, [None, None, [1024, 768]]]
        row2 = [image2, project, wf2, "CAE", None, [None] * 14, [None, None, [1024, 768]]]
        workflows = [
            [wf1, None, None, ["Img1", None, True], project],
            [wf2, None, None, ["Img2", None, False], project],
        ]
        payload = [None, workflows, [row1, row2], [], None, None, None, []]
        assets = parse_assets(payload, project)
        asset_map = {a["media_id"]: a for a in assets}
        self.assertTrue(asset_map[image1]["archived"])
        self.assertFalse(asset_map[image2]["archived"])


    def test_parse_assets_ignores_character_unversioned_copy_and_rejects_other_none_revision(self):
        project, normal_img, normal_wf = (str(uuid4()) for _ in range(3))
        char_ref_img, char_wf, entity_id = (str(uuid4()) for _ in range(3))
        normal_row = [normal_img, project, normal_wf, "CAE", None, [None] * 14, [None, None, [1024, 1024]]]
        char_copy_row = [char_ref_img, project, char_wf, None, None, [None] * 14, [None, None, [1024, 1024]]]
        char_row = [project, entity_id, None, [1, "Kai", [[[char_ref_img]]]], None, None]
        payload_with_char = [None, [], [normal_row, char_copy_row], [], None, [char_row], None, []]
        assets = parse_assets(payload_with_char, project)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["media_id"], normal_img)

        payload_without_char = [None, [], [normal_row, char_copy_row], [], None, [], None, []]
        with self.assertRaises(ValueError):
            parse_assets(payload_without_char, project)


class HTTPAssetListingTest(unittest.IsolatedAsyncioTestCase):
    async def test_global_asset_search_scans_returned_projects_and_marks_unverified_pages(self):
        from flow_http import http_operation

        project_ids = ["proj-a", "proj-b"]
        ids = [str(uuid4()), str(uuid4())]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            [[[project_ids[0], ["Primeiro"]], [project_ids[1], ["Segundo"]]], "next-page"],
            ["assets-a"], ["assets-b"],
        ]))
        rows = [
            [{"media_id": ids[0], "workflow_id": str(uuid4()), "kind": "video", "name": "Café final"}],
            [{"media_id": ids[1], "workflow_id": str(uuid4()), "kind": "image", "name": "Capa"}],
        ]
        with patch("flow_assets.parse_assets", side_effect=rows):
            result = await http_operation(client, "search_assets", {
                "query": "CAFÉ", "kind": "video", "limit": 10,
            })
        self.assertEqual([asset["media_id"] for asset in result["results"]], [ids[0]])
        self.assertEqual(result["results"][0]["project_title"], "Primeiro")
        self.assertEqual(result["projects_scanned"], 2)
        self.assertFalse(result["complete"])
        self.assertEqual(client.rpc.await_count, 3)

    async def test_assets_advanced_filtering_and_sorting(self):
        from flow_http import http_operation, FlowHTTP

        project_id = str(uuid4())
        client = FlowHTTP("conta-a")
        client.rpc = AsyncMock(return_value=["mock_data"])

        sample_assets = [
            {"media_id": str(uuid4()), "kind": "video", "name": "Zebra", "bytes": 5000, "revision": 1, "collection_id": "collection-a"},
            {"media_id": str(uuid4()), "kind": "video", "name": "Arara", "bytes": 2000, "revision": 3, "collection_id": "collection-b"},
            {"media_id": str(uuid4()), "kind": "image", "name": "Baleia", "bytes": 800, "revision": 2, "collection_id": None},
        ]

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test kind filter
            res = await http_operation(client, "assets", {"project_id": project_id, "kind": "image"})
            self.assertEqual(len(res["assets"]), 1)
            self.assertEqual(res["assets"][0]["name"], "Baleia")

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            res = await http_operation(client, "assets", {
                "project_id": project_id, "collection_id": "collection-a"})
            self.assertEqual([asset["name"] for asset in res["assets"]], ["Zebra"])

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test min_bytes filter
            res = await http_operation(client, "assets", {"project_id": project_id, "min_bytes": 2000})
            self.assertEqual(len(res["assets"]), 2)

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test max_bytes filter
            res = await http_operation(client, "assets", {"project_id": project_id, "max_bytes": 2000})
            self.assertEqual(len(res["assets"]), 2)

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test sort_by name asc
            res = await http_operation(client, "assets", {"project_id": project_id, "sort_by": "name", "sort_order": "asc"})
            names = [a["name"] for a in res["assets"]]
            self.assertEqual(names, ["Arara", "Baleia", "Zebra"])

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test sort_by bytes desc
            res = await http_operation(client, "assets", {"project_id": project_id, "sort_by": "bytes", "sort_order": "desc"})
            bytes_list = [a["bytes"] for a in res["assets"]]
            self.assertEqual(bytes_list, [5000, 2000, 800])

        with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
            # Test sort_by revision asc with limit
            res = await http_operation(client, "assets", {"project_id": project_id, "sort_by": "revision", "limit": 2})
            self.assertEqual(len(res["assets"]), 2)
            revs = [a["revision"] for a in res["assets"]]
            self.assertEqual(revs, [1, 2])

        # Test validation errors
        for bad_payload in [
            {"project_id": project_id, "min_bytes": -1},
            {"project_id": project_id, "max_bytes": -10},
            {"project_id": project_id, "min_bytes": 5000, "max_bytes": 1000},
            {"project_id": project_id, "min_bytes": True},
            {"project_id": project_id, "limit": True},
            {"project_id": project_id, "sort_by": "unsupported"},
            {"project_id": project_id, "sort_order": "diagonal"},
            {"project_id": project_id, "limit": 0},
            {"project_id": project_id, "limit": -1},
        ]:
            with patch("flow_assets.parse_assets", return_value=list(sample_assets)):
                with self.assertRaises(ValueError):
                    await http_operation(client, "assets", bad_payload)

        await client.close()

    def test_parse_assets_ignores_character_copy_without_revision_with_voice_and_personality(self):
        project, wf_id, real_img, copy_img, entity_id, thumb_id = (str(uuid4()) for _ in range(6))
        workflows = [[wf_id, None, None, ["Imagem Real"], project]]
        media_rows = [
            [real_img, project, wf_id, "CAE", None, None, [[None] * 13 + ["https://lh3.googleusercontent.com/img"], None, [1024, 1024], 1500]],
            [copy_img, project, wf_id, None, None, None, []],
        ]
        char_row = [project, entity_id, None, [1, "Lake keeper", [[[copy_img]], [[None, "achernar"]], "Guardião do lago"]], thumb_id, [1024, 1024]]
        payload = [None, workflows, media_rows, [], None, [char_row], None, None]

        assets = parse_assets(payload, project)
        self.assertEqual(len(assets), 1)
        self.assertEqual(assets[0]["media_id"], real_img)
        self.assertEqual(assets[0]["name"], "Imagem Real")


if __name__ == "__main__":
    unittest.main()

