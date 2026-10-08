"""Testes locais do brief e das sessões do Agent, sem sessão autenticada."""

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, call, patch

from flow_agent import (create_agent_session, delete_agent_session, get_agent_brief,
                        list_agent_sessions, rename_agent_session, update_agent_brief)
from gflow_cli.api.image import AgentInstruction, ProjectBrief


class AgentBriefTest(unittest.IsolatedAsyncioTestCase):
    async def test_read_agent_brief_with_and_without_brief(self):
        project = "projeto-a"
        payload_empty = [None] * 8
        payload_with_brief = [
            None, None, None, None, None, None, None,
            [None, [1, [["CARD-1", "Tom", "Manter tom conciso", 1], ["CARD-2", "Estilo", "Cinematográfico", 0]]]],
        ]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[payload_empty, payload_with_brief]))

        res_empty = await get_agent_brief("conta-a", project, client=client)
        self.assertEqual(res_empty["status"], "ok")
        self.assertEqual(res_empty["agent_brief"], {"enabled": False, "instructions": []})

        res_brief = await get_agent_brief("conta-a", project, client=client)
        self.assertEqual(res_brief["status"], "ok")
        self.assertEqual(res_brief["agent_brief"], {
            "enabled": True,
            "instructions": [
                {"id": "CARD-1", "title": "Tom", "text": "Manter tom conciso", "enabled": True},
                {"id": "CARD-2", "title": "Estilo", "text": "Cinematográfico", "enabled": False},
            ],
        })
        self.assertEqual(client.rpc.await_args_list, [
            call("Zzl0ze", project_id=project),
            call("Zzl0ze", project_id=project),
        ])



class AgentSessionsTest(unittest.IsolatedAsyncioTestCase):
    async def test_create_uses_frontend_seed_and_confirms_response_id(self):
        session_id = "12345678-1234-4234-8234-123456789abc"
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[[session_id]]))
        with patch("flow_requests._seed", return_value=("seed", session_id)):
            result = await create_agent_session("conta-a", "projeto-a", client=client)
        self.assertEqual(result["status"], "created")
        self.assertEqual(result["session_id"], session_id)
        client.rpc.assert_awaited_once_with("csbIsb", params=["projeto-a", None, "seed"])

    async def test_uncertain_create_reconciles_by_id_without_retry(self):
        session_id = "12345678-1234-4234-8234-123456789abc"
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            RuntimeError("uncertain"), [[[session_id, ["Nova sessão"]]]],
        ]))
        with patch("flow_requests._seed", return_value=("seed", session_id)):
            result = await create_agent_session("conta-a", "projeto-a", client=client)
        self.assertEqual(result["status"], "created")
        self.assertEqual(client.rpc.await_args_list, [
            call("csbIsb", params=["projeto-a", None, "seed"]),
            call("mrlkwd", params=["projeto-a"]),
        ])

    async def test_list_returns_only_session_ids_and_titles(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[[
            ["sessao-1", ["Rascunho", None, [1760000000, 0]]],
            ["sessao-2", ["", None, [1760000001, 0]]],
        ]]))
        result = await list_agent_sessions("conta-a", "projeto-a", client=client)
        self.assertEqual(result["sessions"], [
            {"session_id": "sessao-1", "title": "Rascunho"},
            {"session_id": "sessao-2", "title": ""},
        ])
        self.assertFalse(result["complete"])
        client.rpc.assert_awaited_once_with("mrlkwd", params=["projeto-a"])

    async def test_list_accepts_empty_rpc_result(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[]))
        result = await list_agent_sessions("conta-a", "projeto-a", client=client)
        self.assertEqual(result["sessions"], [])
        self.assertFalse(result["complete"])
        client.rpc.assert_awaited_once_with("mrlkwd", params=["projeto-a"])

    async def test_list_rejects_malformed_session_identity(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(
            return_value=[[["../unsafe", ["Title"]], ["sessao-1", ["Ok"]]]]))
        result = await list_agent_sessions("conta-a", "projeto-a", client=client)
        # ID inseguro nunca sai; a sessão válida continua listada.
        self.assertEqual(result["sessions"], [{"session_id": "sessao-1", "title": "Ok"}])
        client.rpc.return_value = [None]
        self.assertEqual((await list_agent_sessions("conta-a", "projeto-a", client=client))["sessions"], [])

    async def test_rename_sends_once_and_confirms_with_project_listing(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            [[["sessao-1", ["Antes"]]]], [], [[["sessao-1", ["Depois"]]]],
        ]))
        result = await rename_agent_session("conta-a", "projeto-a", "sessao-1", "Depois", client=client)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(client.rpc.await_args_list, [
            call("mrlkwd", params=["projeto-a"]),
            call("TunYMc", params=["sessao-1", "Depois", "projeto-a"]),
            call("mrlkwd", params=["projeto-a"]),
        ])

    async def test_uncertain_rename_is_reconciled_without_retry(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            [[["sessao-1", ["Antes"]]]], RuntimeError("uncertain"),
            [[["sessao-1", ["Depois"]]]],
        ]))
        result = await rename_agent_session("conta-a", "projeto-a", "sessao-1", "Depois", client=client)
        self.assertEqual(result["status"], "updated")
        self.assertEqual(client.rpc.await_count, 3)

    async def test_rename_does_not_mutate_session_outside_initial_page(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[[]]))
        result = await rename_agent_session("conta-a", "projeto-a", "sessao-1", "Depois", client=client)
        self.assertEqual(result["status"], "not_found_in_first_page")
        client.rpc.assert_awaited_once_with("mrlkwd", params=["projeto-a"])

    async def test_delete_requires_confirmation_without_network_call(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
        result = await delete_agent_session("conta-a", "projeto-a", "sessao-1", client=client)
        self.assertEqual(result["status"], "confirmation_required")
        client.rpc.assert_not_awaited()

    async def test_delete_does_not_mutate_session_outside_initial_page(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[[]]))
        result = await delete_agent_session("conta-a", "projeto-a", "sessao-1",
                                            confirm_delete=True, client=client)
        self.assertEqual(result["status"], "not_found_in_first_page")
        client.rpc.assert_awaited_once_with("mrlkwd", params=["projeto-a"])

    async def test_delete_reconciles_once_and_confirms_absence(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            [[ ["sessao-1", ["Rascunho"]] ]], [], [[]],
        ]))
        result = await delete_agent_session("conta-a", "projeto-a", "sessao-1",
                                            confirm_delete=True, client=client)
        self.assertEqual(result["status"], "deleted")
        self.assertEqual(client.rpc.await_args_list, [
            call("mrlkwd", params=["projeto-a"]),
            call("Dcn2Le", params=["sessao-1"]),
            call("mrlkwd", params=["projeto-a"]),
        ])

    async def test_uncertain_delete_keeps_session_and_is_not_retried(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            [[ ["sessao-1", ["Rascunho"]] ]], RuntimeError("uncertain"),
            [[]],
        ]))
        result = await delete_agent_session("conta-a", "projeto-a", "sessao-1",
                                            confirm_delete=True, client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(client.rpc.await_count, 3)


class AgentBriefMutationTest(unittest.IsolatedAsyncioTestCase):
    async def test_replacing_cards_requires_confirmation_without_rpc(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
        result = await update_agent_brief("conta-a", "projeto-a", instructions=[], client=client)
        self.assertEqual(result["status"], "confirmation_required")
        client.rpc.assert_not_awaited()

    async def test_cards_with_media_or_character_refs_raise_value_error(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock())
        with self.assertRaises(ValueError):
            await update_agent_brief(
                "conta-a", "projeto-a",
                instructions=[{"title": "Tom", "text": "x", "image_media_ids": ["00000000-0000-0000-0000-000000000000"]}],
                confirm_replace_instructions=True, client=client,
            )
        client.rpc.assert_not_awaited()

    async def test_update_success_sends_exact_params_and_confirms(self):
        project = "projeto-a"
        payload_before = [None] * 8
        card = {"id": "CARD-1", "title": "Tom", "text": "Manter tom conciso", "enabled": True}
        payload_after = [
            None, None, None, None, None, None, None,
            [None, [1, [["CARD-1", "Tom", "Manter tom conciso", 1]]]],
        ]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[payload_before, None, payload_after]))

        with patch("asyncio.sleep", AsyncMock()):
            result = await update_agent_brief(
                "conta-a", project, enabled=True, instructions=[card],
                confirm_replace_instructions=True, client=client,
            )

        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["agent_brief"]["enabled"], True)
        self.assertEqual(result["agent_brief"]["instructions"], [card])
        self.assertEqual(client.rpc.await_args_list, [
            call("Zzl0ze", project_id=project),
            call("Kcr7Ub", params=[project, [None, [1, [["CARD-1", "Tom", "Manter tom conciso", 1]]]], [["project_brief"]]]),
            call("Zzl0ze", project_id=project),
        ])

    async def test_uncertain_update_sends_once_and_returns_submission_unknown(self):
        project = "projeto-a"
        payload_old = [None] * 8
        card = {"id": "CARD-1", "title": "Tom", "text": "Manter tom conciso", "enabled": True}
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=[
            payload_old, RuntimeError("network hiccup"), payload_old, payload_old, payload_old, payload_old,
        ]))

        with patch("asyncio.sleep", AsyncMock()):
            result = await update_agent_brief(
                "conta-a", project, enabled=True, instructions=[card],
                confirm_replace_instructions=True, client=client,
            )

        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(result["agent_brief"], {"enabled": False, "instructions": []})
        self.assertEqual(client.rpc.await_args_list, [
            call("Zzl0ze", project_id=project),
            call("Kcr7Ub", params=[project, [None, [1, [["CARD-1", "Tom", "Manter tom conciso", 1]]]], [["project_brief"]]]),
            call("Zzl0ze", project_id=project),
            call("Zzl0ze", project_id=project),
            call("Zzl0ze", project_id=project),
            call("Zzl0ze", project_id=project),
        ])



if __name__ == "__main__":
    unittest.main()


class ToolsTest(unittest.IsolatedAsyncioTestCase):
    async def test_tools_listing_maps_categories_and_filters(self):
        from flow_agent import list_tools
        def row(title, category, creator=None):
            return ([f"id-{title}", -1, title, f"{title} description", None, "x", None,
                     [1790000000, 0], [1790000001, 0], None, None, f"applets/{title}", category,
                     None, None, "https://www.gstatic.com/t.png", None, creator])
        payload = [[row("Mine", 1), row("Template", 2), row("Spotlight", 3, "Creator")]]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=payload))
        result = await list_tools("conta-a", client=client)
        self.assertEqual([tool["category"] for tool in result["tools"]], ["mine", "templates", "community"])
        self.assertEqual(result["tools"][2]["creator"], "Creator")
        self.assertEqual(result["tools"][0]["tool_id"], "Mine")
        client.rpc.assert_awaited_with("tRARke", params=[])
        result = await list_tools("conta-a", "community", "spot", client=client)
        self.assertEqual([tool["title"] for tool in result["tools"]], ["Spotlight"])
        with self.assertRaises(ValueError):
            await list_tools("conta-a", "other", client=client)
        payload[0][0][12] = 9  # categoria nova do Flow: só essa ferramenta some
        self.assertNotIn("Mine", [tool["tool_id"] for tool in (await list_tools("conta-a", client=client))["tools"]])


class AgentStreamTest(unittest.TestCase):
    def test_stream_keeps_tools_and_final_a2ui_text(self):
        from flow_agent import parse_agent_stream
        def frame(payload):
            return json.dumps([["wrb.fr", None, json.dumps(payload)]])
        call = [[None, [["t", None, None, ["list_project_artifacts", "list_project_artifacts"]]], "turn"], None, True]
        delta = [[[[["text", [None, None, "Exist"]]]], None, "turn"], None, True]
        a2ui = '```json\n[{"Text": {"text": {"literalString": "Existem 47 imagens."}}}]\n```'
        final = [[[[["text", [None, None, a2ui]]]], None, "turn"]]
        body = ")]}'\n\n12\n" + "\n9\n".join(frame(x) for x in (call, delta, final)) + '\n27\n[["e",15,null,null,3395]]\n'
        result = parse_agent_stream(body)
        self.assertEqual(result, {"answer": "Existem 47 imagens.", "tools": ["list_project_artifacts"]})
        self.assertEqual(parse_agent_stream(")]}'\n" + frame(delta))["answer"], "Exist")


class AgentRequestTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_request_validates_message_and_restores_agent_mode(self):
        from flow_agent import agent_request

        with self.assertRaises(ValueError):
            await agent_request("conta-a", "projeto-a", "   ")

        @asynccontextmanager
        async def bad_page():
            raise RuntimeError("browser error")
            yield

        browser = SimpleNamespace(page=bad_page)
        http_client = SimpleNamespace(post=AsyncMock())
        client = SimpleNamespace(
            account_id="conta-a",
            rpc=AsyncMock(return_value=[900, None, None, None, None, None, None]),
            browser=browser,
            client=http_client,
        )

        with patch("flow_settings.get_user_settings", AsyncMock(return_value={"settings": {"agent_mode_enabled": False}})), \
             patch("flow_settings.update_user_settings", AsyncMock(return_value={"status": "updated"})) as update_mock:
            result = await agent_request("conta-a", "projeto-a", "Olá", client=client)
            self.assertEqual(result["status"], "failed_pre_submit")
            http_client.post.assert_not_awaited()
            self.assertEqual(update_mock.await_count, 2)
            update_mock.assert_has_awaits([
                call("conta-a", agent_mode_enabled=True, client=client),
                call("conta-a", agent_mode_enabled=False, client=client),
            ])




class AgentGenerationTest(unittest.IsolatedAsyncioTestCase):
    PROJECT = "adf1a9da-b94e-4218-b536-fdc406a054af"

    def held(self):
        from urllib.parse import urlencode

        inner = ["sessao-ui", [[[["Preparação"]]]], [f"projects/{self.PROJECT}", None, ["t" * 300, 1], None, None, 1]]
        return urlencode({"f.req": json.dumps([None, json.dumps(inner)]), "at": "x"})

    def inner(self, body):
        from urllib.parse import parse_qs

        return json.loads(json.loads(parse_qs(body)["f.req"][0])[1])

    def test_chat_form_mentions_and_approval_match_the_interface(self):
        from flow_agent import chat_form, mention

        parts = [["Use "], mention("ent-1", "Palito", character=True), [" no "], mention("med-1", "feira", character=False)]
        body, session = chat_form(self.held(), self.PROJECT, parts)
        inner = self.inner(body)
        self.assertEqual(session, "sessao-ui")
        self.assertEqual(inner[1], [[[["Use "], [None, [None, None, ["ent-1", "Palito"]]], [" no "], [None, [["med-1", "feira"]]]]],
                                    [["med-1", "feira"]], None, [["ent-1", "Palito"]]])
        body, session = chat_form(self.held(), self.PROJECT, [], session_id="s2", approve=True)
        inner = self.inner(body)
        self.assertEqual((inner[0], inner[1], inner[2][5], inner[3:]), ("s2", [[[["Aprovar"]]]], 2, [None, 1]))
        with self.assertRaises(ValueError):
            chat_form(self.held(), "outro-projeto", [["x"]])

    def test_agent_cost_reads_the_permission_question(self):
        from flow_agent import agent_cost

        self.assertEqual(agent_cost("Quer que eu inicie essa 1 geração de vídeo, que custa 4 créditos?"), 4)
        self.assertEqual(agent_cost("This will cost 15 credits."), 15)
        self.assertIsNone(agent_cost("Vou gerar as imagens."))

    async def test_agent_generate_approves_only_the_quoted_cost_and_finds_new_media(self):
        import flow_agent

        listings = [[{"media_id": "old", "kind": "video", "workflow_id": "w0"}],
                    [{"media_id": "old", "kind": "video", "workflow_id": "w0"}],
                    [{"media_id": "old", "kind": "video", "workflow_id": "w0"},
                     {"media_id": "new", "kind": "video", "workflow_id": "w1"}]]
        client = SimpleNamespace(rpc=AsyncMock(side_effect=lambda *a, **k: listings.pop(0)))
        chat = AsyncMock(side_effect=[{"session_id": "s", "answer": "Inicio? Custa 15 créditos.", "tools": []},
                                      {"session_id": "s", "answer": "Gerando.", "tools": []}])
        job, saved = {"project_id": self.PROJECT}, []
        with patch.object(flow_agent, "agent_chat", chat), patch("flow_assets.parse_assets", lambda p, _: p), \
                patch("asyncio.sleep", AsyncMock()):
            found = await flow_agent.agent_generate(client, job, [["x"]], kind="video", count=1,
                                                   expected_credits=15, save_job=saved.append)
        self.assertEqual([a["media_id"] for a in found], ["new"])
        self.assertTrue(chat.await_args_list[1].kwargs["approve"])
        self.assertEqual(job["status"], "accepted")

        chat = AsyncMock(return_value={"session_id": "s", "answer": "Custa 20 créditos.", "tools": []})
        client = SimpleNamespace(rpc=AsyncMock(return_value=[]))
        job = {"project_id": self.PROJECT}
        with patch.object(flow_agent, "agent_chat", chat), patch("flow_assets.parse_assets", lambda p, _: p):
            with self.assertRaisesRegex(ValueError, "nada foi aprovado"):
                await flow_agent.agent_generate(client, job, [["x"]], kind="video", count=1,
                                               expected_credits=15, save_job=lambda j: None)
        chat.assert_awaited_once()  # sem aprovação
        self.assertEqual(job["status"], "preparing")
