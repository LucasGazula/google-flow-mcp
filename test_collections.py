import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock
from unittest.mock import patch
from uuid import uuid4
from flow_collections import collection_operation, move_assets, parse_collections


class CollectionOperationTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_renames_once_and_confirms_returned_collection(self):
        async def reply(rpc, *, params):
            collection_id = params[1][0] if rpc == "Uxbujd" else params[0][0]
            title = "Untitled collection" if rpc == "Uxbujd" else params[0][2][0]
            return [collection_id, None, [title]]

        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=reply), close=AsyncMock())
        result = await collection_operation("conta-a", "project-a", "Requested",
                                            parent_collection_id="parent-a", client=client)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["title"], "Requested")
        self.assertEqual([call.args[0] for call in client.rpc.await_args_list],
                         ["Uxbujd", "O2COMe"])
        collection_id = result["collection_id"]
        self.assertEqual(client.rpc.await_args_list[0].kwargs["params"], [
            "projects/project-a", [collection_id, "parent-a", ["Untitled collection"], "project-a"]])
        self.assertEqual(client.rpc.await_args_list[1].kwargs["params"], [
            [collection_id, "parent-a", ["Requested"], "project-a"], [["metadata.display_name"]]])
        client.close.assert_not_awaited()

    async def test_unknown_create_stops_without_retry_or_rename(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=["other", None, []]),
                                 close=AsyncMock())
        result = await collection_operation("conta-a", "project-a", "Requested", client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual([call.args[0] for call in client.rpc.await_args_list],
                         ["Uxbujd", "Zzl0ze"])

    async def test_rename_confirms_id_and_title_without_retry(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=["collection-a", None, ["New"]]),
                                 close=AsyncMock())
        result = await collection_operation("conta-a", "project-a", "New",
                                            collection_id="collection-a", client=client)
        self.assertEqual(result["status"], "ok")
        client.rpc.assert_awaited_once_with("O2COMe", params=[
            ["collection-a", None, ["New"], "project-a"], [["metadata.display_name"]]])

        client.rpc.side_effect = TimeoutError("private")
        result = await collection_operation("conta-a", "project-a", "New",
                                            collection_id="collection-a", client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertNotIn("private", str(result))
        self.assertEqual(client.rpc.await_count, 3)

    async def test_empty_collection_listing_and_uncertain_create_readback(self):
        project_id = "project-a"
        def payload(collection_id):
            return [[[collection_id, None, ["Untitled collection"], project_id]],
                    [], [], [], None, None, None, []]

        async def reply(rpc, *, params=None, project_id=None):
            if rpc == "Uxbujd":
                reply.collection_id = params[1][0]
                raise TimeoutError("private")
            if rpc == "Zzl0ze":
                return payload(reply.collection_id)
            return [reply.collection_id, None, ["Requested"]]

        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=reply), close=AsyncMock())
        result = await collection_operation("conta-a", project_id, "Requested", client=client)
        self.assertEqual(result["status"], "ok")
        self.assertEqual([call.args[0] for call in client.rpc.await_args_list],
                         ["Uxbujd", "Zzl0ze", "O2COMe"])
        self.assertEqual(parse_collections(payload(reply.collection_id), project_id), [{
            "collection_id": reply.collection_id, "parent_collection_id": None,
            "title": "Untitled collection", "project_id": project_id}])
        duplicated = parse_collections([[payload(reply.collection_id)[0][0]] * 2,
                                        [], [], [], None, None, None, []], project_id)
        self.assertEqual(len(duplicated), 1)
        self.assertEqual(parse_collections([None, None, None, None, None, None, None, None], project_id), [])

    async def test_validation_prevents_unsafe_mutations(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(), close=AsyncMock())
        for kwargs in (
            {"title": " "},
            {"title": "x" * 201},
            {"title": "x", "collection_id": "../other"},
            {"title": "x", "parent_collection_id": "../other"},
            {"title": "x", "collection_id": "existing", "parent_collection_id": "parent"},
        ):
            title = kwargs.pop("title")
            with self.assertRaises(ValueError):
                await collection_operation("conta-a", "project-a", title, client=client, **kwargs)
        client.rpc.assert_not_awaited()

    async def test_move_uses_project_workflows_and_batch_collection_rpc(self):
        media_id, workflow_id = str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[["assets"], []]),
                                 close=AsyncMock())
        with patch("flow_assets.parse_assets", return_value=[
            {"media_id": media_id, "workflow_id": workflow_id, "kind": "image"},
        ]):
            result = await move_assets("conta-a", "project-a", [media_id], "collection-a", client=client)
        self.assertEqual(result["status"], "submitted")
        self.assertFalse(result["verified"])
        self.assertEqual(client.rpc.await_args_list[0].args, ("Zzl0ze",))
        self.assertEqual(client.rpc.await_args_list[0].kwargs, {"project_id": "project-a"})
        self.assertEqual(client.rpc.await_args_list[1].args, ("kVdhHf",))
        self.assertEqual(client.rpc.await_args_list[1].kwargs["params"], [
            "project-a", ["collection-a"], [workflow_id], [], None, None, [], []])

    async def test_move_out_targets_project_root_and_checks_membership_before_sending(self):
        media_id, workflow_id = str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[["assets"], []]),
                                 close=AsyncMock())
        with patch("flow_assets.parse_assets", return_value=[
            {"media_id": media_id, "workflow_id": workflow_id, "kind": "video"},
        ]):
            result = await move_assets("conta-a", "project-a", [media_id], None, client=client)
        self.assertEqual(result["status"], "submitted")
        self.assertEqual(client.rpc.await_args_list[1].kwargs["params"], [
            "project-a", None, [workflow_id], [], None, [], [], []])

        client.rpc.reset_mock()
        client.rpc.side_effect = [["assets"]]
        with patch("flow_assets.parse_assets", return_value=[]):
            with self.assertRaises(ValueError):
                await move_assets("conta-a", "project-a", [media_id], None, client=client)
        client.rpc.assert_awaited_once_with("Zzl0ze", project_id="project-a")

    async def test_uncertain_move_is_not_retried(self):
        media_id, workflow_id = str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[["assets"], TimeoutError("private")]),
                                 close=AsyncMock())
        with patch("flow_assets.parse_assets", return_value=[
            {"media_id": media_id, "workflow_id": workflow_id},
        ]):
            result = await move_assets("conta-a", "project-a", [media_id], "collection-a", client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertNotIn("private", str(result))
        self.assertEqual(client.rpc.await_count, 3)
        self.assertFalse(result["verified"])

    async def test_move_readback_confirms_only_explicit_associations_without_resending(self):
        media_id, workflow_id = str(uuid4()), str(uuid4())
        asset = {"media_id": media_id, "workflow_id": workflow_id}
        for target in ("collection-a", None):
            for reply in ([], TimeoutError("private")):
                for rows, expected in (
                    ([[workflow_id, target, None, ["Name"], "project-a"]], True),
                    ([], False),
                    ([[workflow_id, "other", None, ["Name"], "project-a"]], False),
                ):
                    with self.subTest(target=target, reply=type(reply).__name__, rows=rows):
                        client = SimpleNamespace(account_id="conta-a", close=AsyncMock(),
                            rpc=AsyncMock(side_effect=[[], reply, [None, rows, []]]))
                        with patch("flow_assets.parse_assets", return_value=[asset]):
                            result = await move_assets("conta-a", "project-a", [media_id],
                                                       target, client=client)
                        self.assertEqual(result["verified"], expected)
                        self.assertEqual(result["unconfirmed_asset_ids"], [] if expected else [media_id])
                        self.assertEqual(result["status"], "ok" if expected else
                                         "submission_unknown" if isinstance(reply, Exception) else "submitted")
                        self.assertNotIn("private", str(result))
                        self.assertEqual([call.args[0] for call in client.rpc.await_args_list],
                                         ["Zzl0ze", "kVdhHf", "Zzl0ze"])
