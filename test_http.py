"""Testes para o cliente e worker HTTP de flow_http.py."""

import asyncio
from contextlib import asynccontextmanager
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, call, patch
from uuid import uuid4

import httpx

from flow_http import FlowHTTP, http_operation, close_workers


class FlowHTTPTest(unittest.IsolatedAsyncioTestCase):
    async def test_refine_video_action_dispatches_with_resident_client(self):
        client = SimpleNamespace(account_id="conta-a")
        payload = {"project_id":"project", "media_id":"source",
                   "refinements":["follow up"], "max_credits":20}
        with patch("flow_video.refine_video", new_callable=AsyncMock,
                   return_value={"status":"completed"}) as refine:
            result = await http_operation(client, "refine_video", payload)
        self.assertEqual(result, {"status":"completed"})
        refine.assert_awaited_once_with("conta-a", **payload, client=client)

    async def test_native_image_upscale_dispatches_with_resident_client(self):
        client = SimpleNamespace(account_id="conta-a")
        payload = {"project_id":"project", "media_id":"source", "target_resolution":"2k"}
        with patch("flow_edit.upscale_image_native", new_callable=AsyncMock,
                   return_value={"status":"completed"}) as upscale:
            result = await http_operation(client, "upscale_image_native", payload)
        self.assertEqual(result, {"status":"completed"})
        upscale.assert_awaited_once_with("conta-a", **payload, client=client)

    async def test_project_search_filters_remote_ids_and_titles_without_hiding_incompleteness(self):
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[
            [["abc-123", ["Meu Projeto"]], ["xyz-456", ["Outro"]]],
            "next-page",
        ]))
        result = await http_operation(client, "projects", {"query": "MEU"})
        self.assertEqual(result["projects"], [{"project_id": "abc-123", "title": "Meu Projeto"}])
        self.assertFalse(result["complete"])
        client.rpc.assert_awaited_once_with("UpteDb")

        client.rpc.reset_mock()
        with self.assertRaises(ValueError):
            await http_operation(client, "projects", {"query": 42})
        client.rpc.assert_not_awaited()

    async def test_gflow_api_borrows_the_resident_worker_page(self):
        from contextlib import asynccontextmanager

        client = FlowHTTP("conta-a", resident=True)
        page = SimpleNamespace(context=object())
        closed = False

        @asynccontextmanager
        async def page_context():
            nonlocal closed
            try:
                yield page
            finally:
                closed = True

        client.browser.page = page_context
        api = SimpleNamespace()
        with patch("gflow_cli.api.client.FlowApiClient", return_value=api), patch(
                "gflow_cli.auth.profile_dir", return_value=Path("/profile")) as profile:
            async with client.gflow_api_page() as (borrowed, borrowed_page):
                self.assertIs(borrowed, api)
                self.assertIs(borrowed_page, page)
                self.assertIs(api._page, page)
                self.assertIs(api._context, page.context)
                profile.assert_called_once_with("conta-a")
                self.assertFalse(closed)
        self.assertTrue(closed)

    async def test_worker_reuses_resident_client_for_generation_and_closes_on_exit(self):
        from io import StringIO
        from flow_http import worker

        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())
        source = StringIO(' {"action":"images","payload":{}}\n{"action":"generate","payload":{}}\n')
        output = StringIO()
        async def operation(session, action, payload):
            self.assertIs(session, client)
            client.close.assert_not_awaited()
            return {"status":"checked", "action":action}
        with patch("flow_http.FlowHTTP", return_value=client) as factory, patch(
                "flow_http.http_operation", side_effect=operation):
            await worker("conta-a", source, output)
        factory.assert_called_once_with("conta-a", resident=True)
        client.close.assert_awaited_once()
        self.assertEqual([json.loads(line)["action"] for line in output.getvalue().splitlines()], ["images", "generate"])

    async def test_worker_dispatch_passes_session_to_generation_upload_and_recovery(self):
        client = FlowHTTP("conta-a")
        for action, target in (("generate","flow_video.generate_video"), ("images","flow_video.generate_images"),
                               ("recover","flow_video.recover_job"), ("edit_image","flow_edit.edit_image"),
                               ("upload_image","flow_assets.upload_image"),
                               ("upscale", "flow_scene.upscale_media"),
                               ("download_project", "flow_projects.download_project"),
                               ("project_summary", "flow_projects.project_summary"),
                               ("delete_asset", "flow_assets.delete_asset"),
                               ("list_characters", "flow_character.list_characters"),
                               ("manage_character", "flow_character.manage_character"),
                               ("get_agent_brief", "flow_agent.get_agent_brief"),
                               ("update_agent_brief", "flow_agent.update_agent_brief"),
                               ("list_agent_sessions", "flow_agent.list_agent_sessions"),
                               ("list_tools", "flow_agent.list_tools"),
                               ("rename_agent_session", "flow_agent.rename_agent_session"),
                               ("create_agent_session", "flow_agent.create_agent_session"),
                               ("delete_agent_session", "flow_agent.delete_agent_session"),
                               ("manage_scene", "flow_scene.manage_scene"),
                               ("export_scene", "flow_scene.export_scene")):
            with patch(target, AsyncMock(return_value={"status":"checked"})) as operation:
                self.assertEqual(await http_operation(client, action, {}), {"status":"checked"})
                operation.assert_awaited_once_with("conta-a", client=client)

    async def test_credit_rpc_reuses_project_session_without_opening_browser(self):
        from urllib.parse import parse_qs

        client = FlowHTTP("conta-a")
        template = {"url":"https://flow.google.com/_/Ui/data/batchexecute?rpcids=UpteDb",
            "call":["UpteDb", "[]", None, "generic"], "form":{"at":["private"]}, "headers":{}}
        client.templates["UpteDb"] = template
        client.client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200,text="frames")))
        with patch("flow_browser.account_page", side_effect=AssertionError("Chrome desnecessário")), patch(
                "gflow_cli.api.transports.batchexecute.parse_frames", return_value=[("nzlxg",[942,1,2,2,None,942,None])]):
            for _ in range(2):
                result = await http_operation(client, "credits", {})
                self.assertEqual(result["credits"], 942)
        self.assertEqual(client.client.post.await_count, 2)
        for request in client.client.post.call_args_list:
            form = parse_qs(request.kwargs["content"])
            call = json.loads(form["f.req"][0])[0][0]
            self.assertEqual(call[:2], ["nzlxg", "[]"])
        self.assertEqual(template["call"][0], "UpteDb")

    async def test_settings_update_rpc_uses_explicit_parameter_allowlist(self):
        client = FlowHTTP("conta-a")
        client.templates["UpteDb"] = {
            "url":"https://flow.google.com/_/Ui/data/batchexecute?rpcids=UpteDb",
            "call":["UpteDb", "[]", None, "generic"], "form":{"at":["private"]}, "headers":{},
        }
        client.prepare = AsyncMock()
        client.client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(
            status_code=200, text="frames")))
        request = {"url":"https://flow.google.com/_/Ui/data/batchexecute",
                   "body":"encoded", "headers":{}}
        with patch("flow_http.encode_rpc", return_value=request) as encode, patch(
                "gflow_cli.api.transports.batchexecute.parse_frames", return_value=[("DA4VGb", [])]):
            result = await client.rpc("DA4VGb", params=[[None] * 6 + [True], ["has_sound_on_tile_hover"]])
        self.assertEqual(result, [])
        client.prepare.assert_awaited_once_with("UpteDb")
        encode.assert_called_once_with(client.templates["UpteDb"], "DA4VGb",
                                       [[None] * 6 + [True], ["has_sound_on_tile_hover"]])
        client.client.post.assert_awaited_once_with(request["url"], content="encoded", headers={})

    async def test_agent_session_rpc_ids_use_explicit_parameter_allowlist(self):
        client = FlowHTTP("conta-a")
        client.templates["UpteDb"] = {
            "url":"https://flow.google.com/_/Ui/data/batchexecute?rpcids=UpteDb",
            "call":["UpteDb", "[]", None, "generic"], "form":{"at":["private"]}, "headers":{},
        }
        client.prepare = AsyncMock()
        client.client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(
            status_code=200, text="frames")))
        request = {"url":"https://flow.google.com/_/Ui/data/batchexecute",
                   "body":"encoded", "headers":{}}
        with patch("flow_http.encode_rpc", return_value=request) as encode, patch(
                "gflow_cli.api.transports.batchexecute.parse_frames",
                return_value=[("mrlkwd", [[]]), ("TunYMc", []),
                              ("csbIsb", [["sessao-1"]]), ("Dcn2Le", [])]):
            self.assertEqual(await client.rpc("mrlkwd", params=["projeto-a"]), [[]])
            self.assertEqual(await client.rpc("TunYMc", params=["sessao-1", "Título", "projeto-a"]), [])
            self.assertEqual(await client.rpc("csbIsb", params=["projeto-a", None, "seed"]), [["sessao-1"]])
            self.assertEqual(await client.rpc("Dcn2Le", params=["sessao-1"]), [])
        self.assertEqual(client.prepare.await_args_list, [call("UpteDb")] * 4)
        self.assertEqual(encode.call_args_list, [
            call(client.templates["UpteDb"], "mrlkwd", ["projeto-a"]),
            call(client.templates["UpteDb"], "TunYMc", ["sessao-1", "Título", "projeto-a"]),
            call(client.templates["UpteDb"], "csbIsb", ["projeto-a", None, "seed"]),
            call(client.templates["UpteDb"], "Dcn2Le", ["sessao-1"]),
        ])
        self.assertEqual(client.client.post.await_count, 4)

    async def test_credit_session_bootstrap_closes_browser_and_reuses_rpc(self):
        opened = False
        listeners = {}
        response = SimpleNamespace(url="https://flow.google.com/_/Ui/data/batchexecute",
            text=AsyncMock(return_value="frames"), request=SimpleNamespace(
                url="https://flow.google.com/_/Ui/data/batchexecute",
                post_data="f.req="+json.dumps([[["UpteDb","[]",None,"generic"]]]), headers={}))
        async def goto(*args, **kwargs):
            await listeners["response"](response)  # a própria página lista os projetos ao carregar
        button = SimpleNamespace(click=AsyncMock(),wait_for=AsyncMock())
        page = SimpleNamespace(goto=AsyncMock(side_effect=goto),get_by_role=lambda *args, **kwargs:button,
            on=lambda name,cb:listeners.update({name:cb}),remove_listener=lambda name,cb:listeners.pop(name))
        @asynccontextmanager
        async def browser(account):
            nonlocal opened
            opened = True
            try: yield page
            finally: opened = False
        client = FlowHTTP("conta-a")
        async def post(*args, **kwargs):
            self.assertFalse(opened)
            return SimpleNamespace(status_code=200, text="frames")
        async def session(page):
            client.client = SimpleNamespace(post=AsyncMock(side_effect=post))
        with patch("flow_browser.account_page",browser), patch.object(client,"session_from_page",session), \
             patch("gflow_cli.api.transports.batchexecute.parse_frames",return_value=[("nzlxg",[946,1,2,2,None,946,None])]):
            first = await http_operation(client,"credits",{})
            second = await http_operation(client,"credits",{})
        self.assertEqual(first["credits"],946)
        self.assertEqual(second["source"],"HTTP/nzlxg")
        self.assertEqual(client.client.post.await_count,2)
        button.click.assert_not_awaited()  # saldo sem clicar no menu da conta
        page.goto.assert_awaited_once()

    async def test_native_prepare_gets_fresh_captcha_and_closes_before_post(self):
        listeners = {}
        opened = False
        project = str(uuid4())
        response = SimpleNamespace(url="https://flow.google.com/_/Ui/data/batchexecute",
            text=AsyncMock(return_value="frames"), request=SimpleNamespace(
                url="https://flow.google.com/_/Ui/data/batchexecute?rpcids=Zzl0ze",
                post_data="f.req="+json.dumps([[["Zzl0ze",json.dumps([project]),None,"generic"]]]),headers={}))
        async def goto(*args, **kwargs):
            await listeners["response"](response)
        page=SimpleNamespace(goto=goto,wait_for_function=AsyncMock(),evaluate=AsyncMock(return_value="captcha"),
            locator=lambda selector:SimpleNamespace(fill=AsyncMock()),
            on=lambda name,cb:listeners.update({name:cb}),remove_listener=lambda name,cb:listeners.pop(name))
        @asynccontextmanager
        async def browser(account):
            nonlocal opened
            opened=True
            try:yield page
            finally:opened=False
        client=FlowHTTP("conta-a")
        async def post(*args, **kwargs):
            self.assertFalse(opened)
            return SimpleNamespace(status_code=200,text="frames")
        async def capture(page, submit, rpcs):
            rpc="ogiZ0b" if "ogiZ0b" in rpcs else "YhhmEf"
            context=[None,22,None,None,None,project,None,None,None,None,["captcha",1]]
            params=[None,[],1,context,[]] if rpc=="ogiZ0b" else [[],context,[]]
            return {"params":params,"url":response.url,"headers":{},
                "body":"f.req="+json.dumps([[[rpc,json.dumps(params),None,"generic"]]])}
        with patch("flow_browser.account_page",browser), patch.object(client,"session_from_page",AsyncMock()), patch.object(
                client,"capture_submit",AsyncMock(side_effect=capture)) as captured, patch(
                "gflow_cli.api.transports.migrated_composer.MigratedComposer._open_pane",AsyncMock()), patch(
                "gflow_cli.api.transports.migrated_composer.MigratedComposer.ensure_editor",AsyncMock()) as editor, patch(
                "gflow_cli.api.transports.migrated_composer.MigratedComposer._close_pane",AsyncMock()), patch(
                "gflow_cli.api.transports.migrated_composer.MigratedComposer._select",AsyncMock()) as select, patch(
                "gflow_cli.api.transports.migrated_composer.MigratedComposer._pre_submit_gate",AsyncMock()), patch(
                "gflow_cli.api.transports.batchexecute.parse_frames",return_value=[("Zzl0ze",[])]) as frames:
            for action in ("IMAGE_GENERATION","VIDEO_GENERATION","UPLOAD_IMAGE"):
                self.assertEqual(await client.prepare("Zzl0ze",project_id=project,captcha_action=action),"captcha")
                if action=="UPLOAD_IMAGE":
                    page.evaluate.assert_awaited_with(unittest.mock.ANY,action)
                self.assertFalse(opened)
                self.assertEqual(listeners,{})
            self.assertEqual(page.evaluate.await_count,1)
            self.assertEqual(captured.await_count,2)
            self.assertEqual([c.kwargs["axis"] for c in select.call_args_list],["mode","mode"])
            self.assertEqual([c.args[1:] for c in editor.call_args_list],[(project,),(project,)])
            captured=client.request("ogiZ0b",[None,[],1])
            client.client=SimpleNamespace(post=AsyncMock(side_effect=post))
            frames.return_value=[("ogiZ0b",["accepted"])]
            self.assertEqual(await client.send_submit(captured),["accepted"])
            client.client.post.assert_awaited_once()

    async def test_project_rpc_reuses_session_and_sends_only_requested_mutation(self):
        from urllib.parse import parse_qs

        client = FlowHTTP("conta-a")
        template = {"url":"https://flow.google.com/_/Ui/data/batchexecute?rpcids=UpteDb",
            "call":["UpteDb", "[]", None, "generic"],
            "form":{"f.req":["private read envelope"],"at":["private"]}, "headers":{}}
        client.templates["UpteDb"] = template
        client.client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200, text="frames")))
        params = ["projects/*", [None, ["Requested"]], [None, 22]]
        with patch("gflow_cli.api.transports.batchexecute.parse_frames",return_value=[("jHPbke",["new",["Requested"]])]), \
             patch("flow_browser.account_page",side_effect=AssertionError("Chrome must remain closed")):
            self.assertEqual(await client.rpc("jHPbke",params=params), ["new",["Requested"]])
        sent = client.client.post.call_args
        self.assertEqual(parse_qs(sent.args[0].split("?",1)[1])["rpcids"],["jHPbke"])
        envelope = json.loads(parse_qs(sent.kwargs["content"])["f.req"][0])
        self.assertEqual(len(envelope[0]),1)
        self.assertEqual(json.loads(envelope[0][0][1]),params)
        self.assertEqual(template["call"][0],"UpteDb")
        client.client.post.reset_mock()
        with patch("gflow_cli.api.transports.batchexecute.parse_frames",return_value=[("QI2zvc",[])]):
            self.assertEqual(await client.rpc("QI2zvc",params=["projects/existing_backfill"]), [])
        sent = client.client.post.call_args
        self.assertEqual(parse_qs(sent.args[0].split("?",1)[1])["rpcids"],["QI2zvc"])
        envelope = json.loads(parse_qs(sent.kwargs["content"])["f.req"][0])
        self.assertEqual(json.loads(envelope[0][0][1]),["projects/existing_backfill"])
        client.client.post.reset_mock()
        for rpc_id, params in (
            ("Uxbujd", ["projects/project-a", ["collection-a", None, ["Untitled collection"], "project-a"]]),
            ("O2COMe", [["collection-a", None, ["Renamed"], "project-a"], [["metadata.display_name"]]]),
        ):
            with patch("gflow_cli.api.transports.batchexecute.parse_frames", return_value=[(rpc_id, ["accepted"])]):
                self.assertEqual(await client.rpc(rpc_id, params=params), ["accepted"])
            sent = client.client.post.call_args
            self.assertEqual(parse_qs(sent.args[0].split("?", 1)[1])["rpcids"], [rpc_id])
            envelope = json.loads(parse_qs(sent.kwargs["content"])["f.req"][0])
            self.assertEqual(json.loads(envelope[0][0][1]), params)
            client.client.post.reset_mock()
        client.client.post.side_effect = TimeoutError("private")
        with self.assertRaises(TimeoutError):
            await client.rpc("jHPbke",params=params)
        client.client.post.assert_awaited_once()

    async def test_http_video_status_uses_workflow_and_never_repeats_generation(self):
        from urllib.parse import parse_qs

        first, second = str(uuid4()), str(uuid4())
        captured = {"url":"https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute?rpcids=YhhmEf",
            "body":"f.req="+json.dumps([[["YhhmEf",json.dumps(["generation"]),None,"generic"]]])+"&at=private",
            "headers":{"content-type":"application/x-www-form-urlencoded"}}
        client = FlowHTTP("conta-a")
        client.client = SimpleNamespace(post=AsyncMock(return_value=SimpleNamespace(status_code=200,text="frames")))
        client.status_from_submit(captured,first)
        with patch("gflow_cli.api.transports.batchexecute.parse_frames",return_value=[("as29s",["status"])]):
            self.assertEqual(await client.rpc("as29s",workflow_id=second),["status"])
        request=client.client.post.call_args
        self.assertEqual(parse_qs(request.args[0].split("?",1)[1])["rpcids"],["as29s"])
        call=json.loads(parse_qs(request.kwargs["content"])["f.req"][0])[0][0]
        self.assertEqual(call[0],"as29s")
        self.assertEqual(json.loads(call[1]),[second])
        self.assertNotIn("generation",call[1])

    async def test_capture_blocks_browser_submissions_and_http_sends_only_once(self):
        routes = []
        client = FlowHTTP("conta-a")
        url = "https://flow.google.com/_/AiSandboxAngularFrontend/data/batchexecute"
        body = "f.req=" + json.dumps([[["ogiZ0b",json.dumps([None,[],1]),None,"generic"]]])
        blocked = SimpleNamespace(request=SimpleNamespace(method="POST",url=url,post_data=body,
            headers={"content-type":"application/x-www-form-urlencoded","cookie":"private"}),abort=AsyncMock())
        allowed = SimpleNamespace(request=SimpleNamespace(method="GET",url=url),continue_=AsyncMock())
        captcha = SimpleNamespace(request=SimpleNamespace(method="POST",url="https://www.google.com/recaptcha/enterprise/reload"),
            continue_=AsyncMock())
        async def route(pattern, handler):
            routes.append(handler)
        async def click(**kwargs):
            await routes[0](allowed)
            await routes[0](captcha)
            await routes[0](blocked)
            await routes[0](blocked)  # Retry do frontend também é abortado.
        page = SimpleNamespace(route=route)
        with patch.object(client,"session_from_page",AsyncMock()):
            captured = await client.capture_submit(page,SimpleNamespace(click=click),{"ogiZ0b"})
        self.assertEqual(blocked.abort.await_count,2)
        allowed.continue_.assert_awaited_once()
        captcha.continue_.assert_awaited_once()
        self.assertNotIn("cookie",captured["headers"])
        client.client=SimpleNamespace(post=AsyncMock(side_effect=TimeoutError("private")))
        with self.assertRaises(TimeoutError):
            await client.send_submit(captured)
        client.client.post.assert_awaited_once()
        client.client.post.reset_mock()
        captured["url"]="https://user:private@flow.google.com/_/data/batchexecute"
        with self.assertRaises(ValueError):
            await client.send_submit(captured)
        client.client.post.assert_not_awaited()

    async def test_shutdown_closes_workers_and_discards_session_handles(self):
        import sys
        from flow_http import _workers, _locks

        process = await asyncio.create_subprocess_exec(sys.executable,"-c","import sys; sys.stdin.read()",
            stdin=asyncio.subprocess.PIPE)
        _workers["conta-teste"] = process
        _locks["conta-teste"] = asyncio.Lock()
        try:
            await close_workers()
            self.assertEqual(process.returncode,0)
            self.assertEqual(_workers,{})
            self.assertEqual(_locks,{})
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()

    async def test_download_validates_hosts_and_follows_redirects(self):
        client = FlowHTTP("conta-a")
        mock_http = AsyncMock()

        # Resposta com redirect 302 para host permitido, seguido de 200
        redirect_resp = MagicMock(status_code=302, headers={"location": "https://flow-content.google/storage/media.mp4"})
        ok_resp = MagicMock(status_code=200, content=b"1234ftypmp42video")
        mock_http.get.side_effect = [redirect_resp, ok_resp]
        client.client = mock_http

        body = await client.download("https://flow.google.com/download/clip", "media-1")
        self.assertEqual(body, b"1234ftypmp42video")
        self.assertEqual(mock_http.get.call_count, 2)

        # Host não autorizado
        with self.assertRaises(ValueError) as ctx:
            await client.download("https://malicious.evil.com/video.mp4", "media-1")
        self.assertIn("Host de download não autorizado", str(ctx.exception))

        # URL com credenciais (user:pass)
        with self.assertRaises(ValueError) as ctx:
            await client.download("https://user:pass@flow.google.com/video.mp4", "media-1")
        self.assertIn("Host de download não autorizado", str(ctx.exception))

        # Redirecionamento sem destino
        mock_http.get.reset_mock()
        mock_http.get.side_effect = [MagicMock(status_code=302, headers={})]
        with self.assertRaises(ValueError) as ctx:
            await client.download("https://flow.google.com/download/clip", "media-1")
        self.assertIn("Redirecionamento sem destino", str(ctx.exception))

        # Limite de redirecionamentos excedido
        mock_http.get.reset_mock()
        mock_http.get.side_effect = [
            MagicMock(status_code=302, headers={"location": "https://flow.google.com/1"}),
            MagicMock(status_code=302, headers={"location": "https://flow.google.com/2"}),
            MagicMock(status_code=302, headers={"location": "https://flow.google.com/3"}),
            MagicMock(status_code=302, headers={"location": "https://flow.google.com/4"}),
        ]
        with self.assertRaises(ValueError) as ctx:
            await client.download("https://flow.google.com/download/clip", "media-1")
        self.assertIn("Limite de redirecionamentos excedido", str(ctx.exception))

    async def test_prepare_and_rpc_as29s_captures_response_record(self):
        media_id_1 = str(uuid4())
        media_id_2 = str(uuid4())
        project_id = str(uuid4())
        workflow_id = str(uuid4())
        video_url_1 = "https://flow-content.google/video1.mp4"
        video_url_2 = "https://flow-content.google/video2.mp4"

        generation_rec_1 = SimpleNamespace(
            media_id=media_id_1,
            workflow_id=workflow_id,
            project_id=project_id,
            is_done=True,
            video_url=video_url_1,
            size_bytes=16,
        )
        generation_rec_2 = SimpleNamespace(
            media_id=media_id_2,
            workflow_id=workflow_id,
            project_id=project_id,
            is_done=True,
            video_url=video_url_2,
            size_bytes=32,
        )

        listeners = {}
        requested_targets = []

        async def fake_goto(target, **kwargs):
            requested_targets.append(target)
            curr_media = media_id_1 if media_id_1 in target else media_id_2
            resp = SimpleNamespace(
                url="https://flow.google.com/_/FlowUi/data/batchexecute",
                text=AsyncMock(return_value="fake_frames"),
                request=SimpleNamespace(
                    url="https://flow.google.com/_/FlowUi/data/batchexecute",
                    post_data='f.req=%5B%5B%5B%22as29s%22%2C%22%5B%5D%22%2Cnull%2C%22generic%22%5D%5D%5D',
                    headers={"content-type": "application/x-www-form-urlencoded"},
                ),
            )
            await listeners["response"](resp)

        mock_page = SimpleNamespace(
            on=lambda name, callback: listeners.update({name: callback}),
            remove_listener=lambda name, callback: listeners.pop(name, None),
            goto=fake_goto,
            context=SimpleNamespace(cookies=AsyncMock(return_value=[{"name": "SID", "value": "xyz", "domain": ".google.com", "path": "/"}])),
            evaluate=AsyncMock(return_value="Mozilla/5.0"),
        )

        @asynccontextmanager
        async def fake_account_page(account_id):
            yield mock_page

        def fake_parse_frames(text):
            return [("as29s", ["mock_payload"])]

        def fake_gen_record(rpcid, payload):
            # Retorna o registro correspondente à navegação mais recente
            target = requested_targets[-1]
            return generation_rec_1 if media_id_1 in target else generation_rec_2

        client = FlowHTTP("conta-a")
        with patch("flow_browser.account_page", fake_account_page), \
             patch("gflow_cli.api.transports.batchexecute.parse_frames", fake_parse_frames), \
             patch("flow_assets.video_record", fake_gen_record):
            # 1. Primeira mídia: navega e captura
            payload = await client.rpc("as29s", project_id=project_id, media_id=media_id_1)
            self.assertEqual(payload, ["mock_payload"])
            self.assertEqual(client.video_records[media_id_1], generation_rec_1)
            self.assertEqual(len(requested_targets), 1)

            # 2. Segunda chamada para a MESMA mídia: reusa o cache sem abrir navegador
            payload_cached = await client.rpc("as29s", project_id=project_id, media_id=media_id_1)
            self.assertEqual(payload_cached, ["mock_payload"])
            self.assertEqual(len(requested_targets), 1)

            # 3. Segunda mídia DISTINTA: deve acionar prepare da nova rota e NÃO sequestrar via template POST
            payload_2 = await client.rpc("as29s", project_id=project_id, media_id=media_id_2)
            self.assertEqual(payload_2, ["mock_payload"])
            self.assertEqual(client.video_records[media_id_2], generation_rec_2)
            self.assertEqual(len(requested_targets), 2)
            self.assertIn(f"/project/{project_id}/edit/{media_id_2}", requested_targets[-1])

        await client.close()

    async def test_prepare_as29s_edge_cases(self):
        project_id = str(uuid4())
        media_id = str(uuid4())
        client = FlowHTTP("conta-a")

        # 1. Chamar prepare com rpc_id as29s sem media_id ou project_id levanta ValueError
        with self.assertRaises(ValueError) as ctx:
            await client.prepare("as29s", project_id=None, media_id=media_id)
        self.assertIn("Identificadores de projeto e mídia necessários", str(ctx.exception))

        with self.assertRaises(ValueError) as ctx:
            await client.prepare("as29s", project_id=project_id, media_id=None)
        self.assertIn("Identificadores de projeto e mídia necessários", str(ctx.exception))

        # 2. Observador tolera erros de rede em response.text() sem propagar exceção não tratada
        listeners = {}

        async def fake_goto_with_network_error(target, **kwargs):
            error_resp = SimpleNamespace(
                url="https://flow.google.com/_/FlowUi/data/batchexecute",
                text=AsyncMock(side_effect=Exception("net::ERR_ABORTED")),
            )
            # Não deve lançar erro
            await listeners["response"](error_resp)

            # Resposta com envelope no request contendo as29s, mas resposta NÃO contém as29s
            # Não deve resolver found prematuramente!
            empty_resp = SimpleNamespace(
                url="https://flow.google.com/_/FlowUi/data/batchexecute",
                text=AsyncMock(return_value="unrelated_frames"),
                request=SimpleNamespace(
                    url="https://flow.google.com/_/FlowUi/data/batchexecute",
                    post_data='f.req=%5B%5B%5B%22as29s%22%2C%22%5B%5D%22%2Cnull%2C%22generic%22%5D%5D%5D',
                    headers={"content-type": "application/x-www-form-urlencoded"},
                ),
            )
            await listeners["response"](empty_resp)

            # Finalmente resposta com as29s real
            valid_resp = SimpleNamespace(
                url="https://flow.google.com/_/FlowUi/data/batchexecute",
                text=AsyncMock(return_value="valid_frames"),
                request=SimpleNamespace(
                    url="https://flow.google.com/_/FlowUi/data/batchexecute",
                    post_data="",
                    headers={},
                ),
            )
            await listeners["response"](valid_resp)

        mock_page = SimpleNamespace(
            on=lambda name, callback: listeners.update({name: callback}),
            remove_listener=lambda name, callback: listeners.pop(name, None),
            goto=fake_goto_with_network_error,
            context=SimpleNamespace(cookies=AsyncMock(return_value=[])),
            evaluate=AsyncMock(return_value="Mozilla/5.0"),
        )

        @asynccontextmanager
        async def fake_account_page(account_id):
            yield mock_page

        gen_rec = SimpleNamespace(
            media_id=media_id,
            is_done=True,
            video_url="https://flow-content.google/vid.mp4",
        )

        def mock_parse(text):
            if text == "valid_frames":
                return [("as29s", ["valid_payload"])]
            return [("other", [])]

        with patch("flow_browser.account_page", fake_account_page), \
             patch("gflow_cli.api.transports.batchexecute.parse_frames", mock_parse), \
             patch("flow_assets.video_record", return_value=gen_rec):
            payload = await client.rpc("as29s", project_id=project_id, media_id=media_id)
            self.assertEqual(payload, ["valid_payload"])

        # 3. Timeout em prepare("as29s") levanta ValueError("Vídeo original ainda não disponível.")
        async def fake_goto_timeout(target, **kwargs):
            # Não emite nenhuma resposta, causando timeout
            pass

        mock_page.goto = fake_goto_timeout
        with patch("flow_browser.account_page", fake_account_page), \
             patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            with self.assertRaises(ValueError) as ctx:
                await client.rpc("as29s", project_id=project_id, media_id=str(uuid4()))
            self.assertIn("Vídeo original ainda não disponível", str(ctx.exception))

        await client.close()

    async def test_http_operation_download_asset_video(self):
        project_id = str(uuid4())
        media_id = str(uuid4())
        workflow_id = str(uuid4())
        video_body = b"1234ftypmp42video"

        # Mock client Zzl0ze retornando ativo de vídeo
        video_record = SimpleNamespace(
            media_id=media_id,
            workflow_id=workflow_id,
            status=3,
            size_bytes=len(video_body),
        )

        row = [workflow_id, project_id, media_id, "CAE", None, [None] * 14, None, [None]]
        payload_zzl = [None, [[workflow_id, None, None, ["Meu Video"], project_id]], [row], [], None, None, None, []]

        gen_rec = SimpleNamespace(
            media_id=media_id,
            project_id=project_id,
            workflow_id=workflow_id,
            is_done=True,
            video_url="https://flow-content.google/video.mp4",
            size_bytes=len(video_body),
        )

        client = FlowHTTP("conta-a")
        client.rpc = AsyncMock()

        async def fake_rpc(rpc_id, project_id=None, media_id=None, workflow_id=None):
            if rpc_id == "Zzl0ze":
                return payload_zzl
            if rpc_id == "as29s":
                self.assertEqual(workflow_id,video_record.workflow_id)
                return ["mock_as29s_payload"]
            raise ValueError(f"Unknown rpc {rpc_id}")

        client.rpc.side_effect = fake_rpc
        client.download = AsyncMock(return_value=video_body)

        with tempfile.TemporaryDirectory() as outdir, patch.dict(os.environ, {"FLOW_MCP_OUTPUT": outdir}), \
             patch("flow_assets.video_record", side_effect=[video_record, gen_rec]):
            result = await http_operation(client, "download_asset", {"project_id": project_id, "media_id": media_id})
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["bytes"], len(video_body))
            out_file = Path(result["path"])
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.read_bytes(), video_body)
            gen_rec.project_id=str(uuid4())
            client.download.reset_mock()
            with patch("flow_assets.video_record",side_effect=[video_record,gen_rec]):
                with self.assertRaises(ValueError):
                    await http_operation(client,"download_asset",{"project_id":project_id,"media_id":media_id})
            client.download.assert_not_awaited()

        await client.close()

    async def test_http_operation_download_asset_image(self):
        project_id = str(uuid4())
        media_id = str(uuid4())
        workflow_id = str(uuid4())
        image_body = b"\x89PNG\r\n\x1a\nfakeimage"

        image_rec = SimpleNamespace(
            media_id=media_id,
            workflow_id=workflow_id,
            project_id=project_id,
            image_url="https://flow-content.google/image.png",
            dimensions=(1024,768), prompt="Uma montanha",
        )

        row = [media_id, project_id, workflow_id, "CAE", None, [None] * 14, [None, None, [1024, 768]]]
        row[6][0]=[None]*14
        row[6][0][13]=image_rec.image_url
        payload_zzl = [None, [[workflow_id, None, None, ["Minha Imagem"], project_id]], [row], [], None, None, None, []]

        client = FlowHTTP("conta-a")
        client.rpc = AsyncMock(return_value=payload_zzl)
        client.download = AsyncMock(return_value=image_body)

        with tempfile.TemporaryDirectory() as outdir, patch.dict(os.environ, {"FLOW_MCP_OUTPUT": outdir}), \
             patch("gflow_cli.api.transports.batchexecute.image_records", return_value=[image_rec]):
            result = await http_operation(client, "download_asset", {"project_id": project_id, "media_id": media_id})
            self.assertEqual(result["status"], "downloaded")
            self.assertEqual(result["bytes"], len(image_body))
            out_file = Path(result["path"])
            self.assertTrue(out_file.exists())
            self.assertEqual(out_file.suffix, ".png")
            self.assertEqual(out_file.read_bytes(), image_body)

            details = await http_operation(client,"get_asset",{"project_id":project_id,"media_id":media_id})
            self.assertEqual(details["source"],"HTTP/Zzl0ze")
            self.assertEqual(details["versions"][0]["media_id"],media_id)
            self.assertNotIn("https://",json.dumps(details))

        await client.close()

    async def test_http_operation_edge_cases(self):
        project_id = str(uuid4())
        media_id = str(uuid4())
        workflow_id = str(uuid4())

        row = [workflow_id, project_id, media_id, "CAE", None, [None] * 14, None, [None]]
        payload_zzl = [None, [[workflow_id, None, None, ["Video"], project_id]], [row], [], None, None, None, []]

        video_record = SimpleNamespace(
            media_id=media_id,
            workflow_id=workflow_id,
            status=3,
            size_bytes=100,
        )

        client = FlowHTTP("conta-a")
        client.rpc = AsyncMock(return_value=payload_zzl)

        # Caso 1: Ação inválida
        with self.assertRaises(ValueError) as ctx:
            await http_operation(client, "invalid_action", {"project_id": project_id})
        self.assertIn("Operação HTTP inválida", str(ctx.exception))

        # Caso 2: Mídia ausente na listagem inicial
        client.rpc.return_value = payload_zzl
        with patch("flow_assets.video_record", return_value=video_record):
            with self.assertRaises(ValueError) as ctx:
                await http_operation(client, "download_asset", {"project_id": project_id, "media_id": str(uuid4())})
            self.assertIn("Mídia ausente da resposta inicial", str(ctx.exception))

        # Caso 3: Vídeo não concluído (is_done=False) ou sem URL
        not_done_rec = SimpleNamespace(
            media_id=media_id,
            workflow_id=workflow_id,
            is_done=False,
            video_url=None,
            size_bytes=100,
        )
        client.rpc.side_effect = [payload_zzl, ["as29s_raw"]]
        with patch("flow_assets.video_record", side_effect=[video_record, not_done_rec]):
            with self.assertRaises(ValueError) as ctx:
                await http_operation(client, "download_asset", {"project_id": project_id, "media_id": media_id})
            self.assertIn("Vídeo original ainda não disponível", str(ctx.exception))

        # Caso 4: Bytes baixados não conferem tamanho ou formato MP4 (_verify levanta WireFormatError)
        done_rec = SimpleNamespace(
            media_id=media_id,
            project_id=project_id,
            workflow_id=workflow_id,
            is_done=True,
            video_url="https://flow-content.google/video.mp4",
            size_bytes=100,
        )
        client.rpc.side_effect = [payload_zzl, ["as29s_raw"]]
        client.download = AsyncMock(return_value=b"not_an_mp4_file")
        with patch("flow_assets.video_record", side_effect=[video_record, done_rec]):
            from gflow_cli.errors import WireFormatError
            with self.assertRaises(WireFormatError):
                await http_operation(client, "download_asset", {"project_id": project_id, "media_id": media_id})

        await client.close()


if __name__ == "__main__":
    unittest.main()


class DispatchCoverageTest(unittest.TestCase):
    def test_every_mcp_worker_action_is_dispatched(self):
        import inspect
        import re
        import flow_http

        tools = Path(__file__).with_name("flow_mcp.py").read_text(encoding="utf-8")
        actions = set(re.findall(r'run_account_operation\("([a-z_]+)"', tools)) - {"list", "job", "jobs"}
        dispatch = inspect.getsource(flow_http)  # http_operation e laço do worker (connect/import)
        self.assertEqual(sorted(a for a in actions if f'"{a}"' not in dispatch), [])


class PrepareGenerationTest(unittest.IsolatedAsyncioTestCase):
    async def test_agent_only_composer_is_reset_by_toggling_agent_mode_once(self):
        from unittest.mock import AsyncMock, patch
        from types import SimpleNamespace
        from flow_http import AgentOnlyComposer, prepare_generation

        client = SimpleNamespace(account_id="conta-a", prepare=AsyncMock(side_effect=[AgentOnlyComposer("só Agent"), "token"]))
        update = AsyncMock(return_value={"status": "updated"})
        with patch("flow_settings.update_user_settings", update):
            self.assertEqual(await prepare_generation(client, "projeto", "VIDEO_GENERATION"), "token")
        self.assertEqual([c.kwargs["agent_mode_enabled"] for c in update.await_args_list], [True, False])
        self.assertEqual(client.prepare.await_count, 2)

        client.prepare = AsyncMock(side_effect=AgentOnlyComposer("só Agent"))
        with patch("flow_settings.update_user_settings", update), self.assertRaises(AgentOnlyComposer):
            await prepare_generation(client, "projeto", "IMAGE_GENERATION")
