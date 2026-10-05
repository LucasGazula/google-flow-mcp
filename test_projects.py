import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from flow_projects import parse_projects, validate_project, project_operation, delete_project, download_project, project_summary


class HTTPProjectTest(unittest.IsolatedAsyncioTestCase):
    async def test_delete_project_requires_confirmation_and_reconciles_once(self):
        project = "existing_backfill"
        listing = [[[project, ["To remove"]]]]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[listing, [], [[]]]), close=AsyncMock())
        guarded = await delete_project("conta-a", project, client=client)
        self.assertEqual(guarded["status"], "confirmation_required")
        client.rpc.assert_not_awaited()

        result = await delete_project("conta-a", project, confirm_delete=True, client=client)
        self.assertEqual(result["status"], "deleted")
        self.assertEqual([call.args[0] for call in client.rpc.await_args_list],
                         ["UpteDb", "QI2zvc", "UpteDb"])
        self.assertEqual(client.rpc.await_args_list[1].kwargs["params"],
                         [f"projects/{project}"])

    async def test_uncertain_project_delete_is_reconciled_without_retry(self):
        project = "existing_backfill"
        listing = [[[project, ["To remove"]]]]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[listing, TimeoutError(), listing]), close=AsyncMock())
        result = await delete_project("conta-a", project, confirm_delete=True, client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(client.rpc.await_count, 3)
        client.close.assert_not_awaited()

    async def test_rename_preserves_cover_rejects_other_project_and_never_retries(self):
        project = "existing_backfill"
        cover = "ae194752-2b65-4472-b654-080b48c8d2ca"
        client = SimpleNamespace(account_id="conta-a", prepare=AsyncMock(),
            rpc=AsyncMock(side_effect=[[project, ["Old title", cover]], ["New title"]]), close=AsyncMock())
        result = await project_operation("conta-a", "New title", project, client=client)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(client.rpc.await_args_list[1].kwargs["params"],
                         ["projects/existing_backfill", ["New title", cover], [["project_title"]], [None, 22]])
        client.close.assert_not_awaited()
        client.rpc.reset_mock()
        client.rpc.side_effect = [["other", ["Title", cover]]]
        with self.assertRaises(ValueError):
            await project_operation("conta-a", "New title", project, client=client)
        self.assertEqual(client.rpc.await_count, 1)
        client.rpc.reset_mock()
        client.rpc.side_effect = [[project, ["Old title", cover]], TimeoutError("private")]
        uncertain = await project_operation("conta-a", "New title", project, client=client)
        self.assertEqual(uncertain["status"], "submission_unknown")
        self.assertEqual(client.rpc.await_count, 2)
        self.assertNotIn("private", str(uncertain))

    async def test_create_confirms_id_title_and_stops_on_ambiguous_result(self):
        client = SimpleNamespace(account_id="conta-a", prepare=AsyncMock(),
            rpc=AsyncMock(return_value=["new-project", ["Requested"]]), close=AsyncMock())
        result = await project_operation("conta-a", "Requested", client=client)
        self.assertEqual(result["project_id"], "new-project")
        self.assertEqual(result["status"], "ok")
        client.rpc.assert_awaited_once_with("jHPbke", params=["projects/*", [None, ["Requested"]], [None, 22]])
        client.rpc.reset_mock()
        client.rpc.return_value = ["new-project", ["Different"]]
        result = await project_operation("conta-a", "Requested", client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(result["project_id"], "new-project")
        client.rpc.assert_awaited_once()
        client.rpc.reset_mock()
        for title in ("", "  ", None, "a" * 201):
            with self.assertRaises(ValueError):
                await project_operation("conta-a", title, client=client)
        client.rpc.assert_not_awaited()
        with self.assertRaises(ValueError):
            await project_operation("conta-other", "Requested", client=client)

    async def test_download_project_downloads_assets_and_handles_failures(self):
        import tempfile
        import os
        from pathlib import Path
        from unittest.mock import patch
        from uuid import uuid4

        project = str(uuid4())
        media1 = str(uuid4())
        media2 = str(uuid4())
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())

        with tempfile.TemporaryDirectory() as tmpdir:
            src1 = Path(tmpdir) / f"{media1}.png"
            src1.write_bytes(b"\x89PNGfile1")

            async def fake_http_op(cl, action, payload):
                if action == "assets":
                    return {"assets": [
                        {"media_id": media1, "kind": "image", "name": "Foto 1"},
                        {"media_id": media2, "kind": "video", "name": "Video 1"}
                    ]}
                if action == "download_asset":
                    if payload["media_id"] == media1:
                        return {"status": "downloaded", "path": str(src1), "bytes": 8}
                    raise RuntimeError("Falha de rede ao baixar video")
                raise ValueError(f"Unknown action {action}")

            out_dir = Path(tmpdir) / "output"
            with patch("flow_http.http_operation", side_effect=fake_http_op):
                res = await download_project("conta-a", project, output_dir=str(out_dir), client=client)
                self.assertEqual(res["status"], "ok")
                self.assertEqual(res["total_assets"], 2)
                self.assertEqual(res["downloaded_count"], 1)
                self.assertEqual(res["failed_count"], 1)
                self.assertTrue((out_dir / f"{media1}.png").exists())
                self.assertEqual(len(res["failed"]), 1)
                self.assertEqual(res["failed"][0]["media_id"], media2)

    async def test_download_project_validates_inputs(self):
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", kind="audio", client=client)
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", output_dir="", client=client)
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", output_dir=123, client=client)
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", query=123, client=client)
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", query="a" * 201, client=client)
        with self.assertRaises(ValueError):
            await download_project("conta-a", "proj-1", collection_id="../other", client=client)

    async def test_download_collection_filters_assets_and_uses_collection_folder(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict("os.environ", {"FLOW_MCP_OUTPUT": tmpdir}), \
                 patch("flow_http.http_operation", AsyncMock(return_value={"assets": []})) as operation:
                result = await download_project("conta-a", "project-a", collection_id="abc123", client=client)
            self.assertEqual(result["collection_id"], "abc123")
            self.assertEqual(result["output_dir"], str(Path(tmpdir) / "collection_abc123"))
            operation.assert_awaited_once_with(client, "assets", {
                "project_id": "project-a", "kind": None, "query": "", "collection_id": "abc123",
            })
            self.assertTrue((Path(tmpdir) / "collection_abc123").is_dir())

    async def test_recursive_collection_download_follows_descendants_only(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())
        with tempfile.TemporaryDirectory() as tmpdir:
            calls = []

            async def operation(_, action, payload):
                calls.append(action)
                if action == "collections":
                    return {"collections": [
                        {"collection_id": "root", "parent_collection_id": None},
                        {"collection_id": "child", "parent_collection_id": "root"},
                        {"collection_id": "grandchild", "parent_collection_id": "child"},
                        {"collection_id": "other", "parent_collection_id": None},
                    ]}
                if action == "assets":
                    self.assertIsNone(payload["collection_id"])
                    return {"assets": [
                        {"media_id": str(i), "collection_id": collection, "kind": "image"}
                        for i, collection in enumerate(("root", "child", "grandchild", "other"))]}
                source = Path(tmpdir) / f"{payload['media_id']}.png"
                source.write_bytes(b"image")
                return {"path": str(source), "bytes": 5}

            with patch("flow_http.http_operation", side_effect=operation):
                result = await download_project("conta-a", "project-a", output_dir=str(Path(tmpdir) / "out"),
                                                collection_id="root", recursive=True, client=client)
            self.assertEqual(result["collection_ids"], ["child", "grandchild", "root"])
            self.assertEqual(result["downloaded_count"], 3)
            self.assertEqual(len(list((Path(tmpdir) / "out").glob("*.png"))), 3)
            self.assertEqual(calls, ["collections", "assets", "download_asset", "download_asset", "download_asset"])
            self.assertFalse(result["complete"])

    async def test_project_summary(self):
        from unittest.mock import patch
        from uuid import uuid4

        project = str(uuid4())
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())

        async def fake_http_op(cl, action, payload):
            if action == "projects":
                return {"projects": [{"project_id": project, "title": "Projeto Alfa"}]}
            if action == "assets":
                return {"assets": [
                    {"media_id": str(uuid4()), "kind": "image", "name": "Img 1"},
                    {"media_id": str(uuid4()), "kind": "image", "name": "Img 2"},
                    {"media_id": str(uuid4()), "kind": "video", "name": "Vid 1", "bytes": 5000},
                    {"media_id": str(uuid4()), "kind": "video", "name": "Vid Pending", "bytes": None}
                ]}
            raise ValueError(f"Unknown action {action}")

        with patch("flow_http.http_operation", side_effect=fake_http_op):
            res = await project_summary("conta-a", project, client=client)
            self.assertEqual(res["status"], "ok")
            self.assertEqual(res["title"], "Projeto Alfa")
            self.assertEqual(res["total_assets"], 4)
            self.assertEqual(res["image_count"], 2)
            self.assertEqual(res["video_count"], 2)
            self.assertEqual(res["total_video_bytes"], 5000)
            self.assertEqual(res["asset_names"], ["Img 1", "Img 2", "Vid 1", "Vid Pending"])


class ProjectTest(unittest.TestCase):
    def test_remote_listing_keeps_legacy_ids_and_drops_private_metadata(self):
        rows = [["legacy_backfill", ["Título", None, ["private token"], "https://host/?secret=1"]]]
        result = parse_projects([rows])
        self.assertEqual(result, {"projects": [{"project_id": "legacy_backfill", "title": "Título"}], "complete": True})
        self.assertFalse(parse_projects([rows, "cursor must stay private"])["complete"])
        self.assertEqual(parse_projects([[]])["projects"], [])
        for payload in (None, [], {}, [["bad row"]], [[["../escape", ["Title"]]]]):
            with self.assertRaises(ValueError):
                parse_projects(payload)

    def test_legacy_id_is_allowed_but_routes_cannot_escape(self):
        self.assertEqual(validate_project("4020285f-df1c-4e7c-8629-922df02_backfill"),
                         "4020285f-df1c-4e7c-8629-922df02_backfill")
        for value in (None, "", "../cookies", "id/edit/other", "id?token=secret", "id#fragment", "%2fetc", "a" * 129):
            with self.assertRaises(ValueError):
                validate_project(value)


if __name__ == "__main__":
    unittest.main()
