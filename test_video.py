"""Orçamento antes do envio e persistência de tarefas sem credenciais."""

import os
import json
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from gflow_cli.api.transports.migrated_composer import MigratedComposer

from flow_video import BudgetedComposer, download_bytes, get_job, image_suffix, job_path, list_jobs, parse_generation_cost, recover_clip, recover_job, save_job


class VideoTest(unittest.IsolatedAsyncioTestCase):
    def test_1080p_upscale_capture_checks_source_project_and_resolution(self):
        from flow_video import _validate_upscale_capture

        media, workflow, project = (str(uuid4()) for _ in range(3))
        params = [[[[None, media], None, 2, None, [None, workflow], None, 2]],
                  [None, None, None, None, None, project]]
        _validate_upscale_capture(params, media, workflow, project, "1080p")
        params[0][0][6] = 1
        with self.assertRaises(ValueError):
            _validate_upscale_capture(params, media, workflow, project, "1080p")

    async def test_native_video_upscale_reconciles_uncertain_submission_without_resending(self):
        from flow_video import upscale_video

        project, media, workflow = (str(uuid4()) for _ in range(3))
        source = {"media_id": media, "workflow_id": workflow, "kind": "video"}
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(),
                                 capture_submit=AsyncMock(), send_submit=AsyncMock())
        with tempfile.TemporaryDirectory() as root:
            marker = Path(root) / "job.json"
            marker.touch()
            with patch("flow_video.job_path", return_value=marker), patch(
                    "flow_video.get_job", return_value={"status": "submission_unknown"}), patch(
                    "flow_video.save_job") as save, patch(
                    "flow_assets.parse_assets", return_value=[source]) as assets, patch(
                    "flow_http.http_operation", AsyncMock(return_value={
                        "status": "downloaded", "path": "result.mp4", "bytes": 100})) as download:
                result = await upscale_video("conta-a", project, media, client=client)
                self.assertEqual(result["status"], "submission_unknown")
                download.assert_not_awaited()
                assets.return_value = [source, {"media_id": media + "_720p_upsampled"}]
                result = await upscale_video("conta-a", project, media, client=client)
                self.assertEqual(result["status"], "downloaded")
                download.assert_awaited_once()
                self.assertEqual(save.call_args.args[0]["status"], "completed")
        client.capture_submit.assert_not_awaited()
        client.send_submit.assert_not_awaited()

    async def test_prepared_uploads_bind_each_duplicate_path_and_fail_closed(self):
        project, first, second = (str(uuid4()) for _ in range(3))
        records = [{"path":str(Path("/reference.png")), "project_id":project, "media_id":mid, "name":name}
                   for mid, name in ((first, "first.png"), (second, "second.png"))]
        composer = BudgetedComposer(0, records)
        self.assertEqual(await composer._upload_via_toolbar(None, project, Path("/reference.png")),
                         (first, "first.png"))
        with self.assertRaises(ValueError):
            await composer._upload_via_toolbar(None, "other-project", Path("/reference.png"))
        self.assertEqual(await composer._upload_via_toolbar(None, project, Path("/reference.png")),
                         (second, "second.png"))
        with self.assertRaises(ValueError):
            await composer._upload_via_toolbar(None, project, Path("/reference.png"))

    async def test_uncertain_project_creation_stops_both_generation_paths(self):
        from flow_video import generate_images, generate_video

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GFLOW_CLI_HOME":root}), \
             patch("flow_projects.project_operation", AsyncMock(return_value={
                 "project_id":None, "status":"submission_unknown"})) as create, \
             patch("flow_video.account_page", side_effect=AssertionError("Generation must not prepare")), \
             patch("flow_http.FlowHTTP.send_submit", AsyncMock()) as send:
            for operation in (generate_video, generate_images):
                job = await operation("conta-a", "A landscape", 10)
                self.assertEqual(job["status"], "failed_pre_submit")
                self.assertEqual(job["project_creation_status"], "submission_unknown")
            self.assertEqual(create.await_count, 2)
            send.assert_not_awaited()

    async def test_video_reference_asset_id_rejects_video_kind_before_submission(self):
        from gflow_cli.config import get_settings
        from flow_video import generate_video

        project, video_ref = str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a",
            rpc=AsyncMock(return_value=[None, None, []]),
            prepare=AsyncMock(), send_submit=AsyncMock())

        get_settings.cache_clear()
        try:
            with patch("flow_assets.parse_assets", return_value=[{
                "media_id": video_ref, "kind": "video", "name": "clip.mp4", "project_id": project
            }]):
                job = await generate_video("conta-a", "Uma paisagem", 0,
                    project_id=project, model="omni-flash",
                    reference_asset_ids=[video_ref], client=client)
            self.assertEqual(job["status"], "failed_pre_submit")
            self.assertEqual(job["error_type"], "ValueError")
            client.send_submit.assert_not_awaited()
            client.prepare.assert_not_awaited()
        finally:
            get_settings.cache_clear()

    async def test_http_image_generation_closes_browser_and_never_retries_unknown_submit(self):
        from gflow_cli.config import get_settings
        from flow_http import FlowHTTP
        from flow_video import generate_images

        project, media, workflow = (str(uuid4()) for _ in range(3))
        record = SimpleNamespace(media_id=media, workflow_id=workflow, project_id=project,
            image_url="https://lh3.googleusercontent.com/private-image", dimensions=(1024,1024))
        async def quote(client, job, features):
            job["quoted_credits"] = 0
            return {"model_key":"NARWHAL"}
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
            {"GFLOW_CLI_HOME":root,"FLOW_MCP_OUTPUT":root}), patch(
            "flow_video.generation_quote", side_effect=quote) as quoting, patch(
            "flow_requests._seed", side_effect=lambda: ("seed", media) if seed_toggle.pop(0) else ("seed", workflow)), patch.object(
            FlowHTTP,"prepare",AsyncMock(return_value="captcha")), patch.object(
            FlowHTTP,"request",side_effect=lambda rpc,params: {"rpc_id":rpc,"params":params}), patch.object(
            FlowHTTP,"close",AsyncMock()), patch.object(
            FlowHTTP,"capture_submit",AsyncMock(side_effect=AssertionError("No compositor"))), patch.object(
            FlowHTTP,"download",AsyncMock(return_value=b"\xff\xd8\xfforiginal")) as download, patch(
            "gflow_cli.api.transports.batchexecute.image_records",return_value=[record]), patch.object(
            FlowHTTP,"send_submit",new_callable=AsyncMock) as send:
            get_settings.cache_clear()
            try:
                async def http_send(packet):
                    job=json.loads(next((Path(root)/"jobs").glob("*.json")).read_text())
                    self.assertEqual(job["status"],"submitting")
                    self.assertEqual(job["request_media_ids"],[media])
                    self.assertNotIn("captcha",json.dumps(job))
                    self.assertEqual(packet["params"][1][0][5],"NARWHAL")
                    return []
                seed_toggle = [True, False]
                send.side_effect=http_send
                result=await generate_images("conta-a","Uma montanha",0,project_id=project)
                self.assertEqual(result["status"],"completed")
                self.assertEqual(result["media_ids"],[media])
                send.assert_awaited_once()
                download.assert_awaited_once_with("https://lh3.googleusercontent.com/private-image=s0",media)
                send.reset_mock()
                seed_toggle = [True, False]
                send.side_effect=TimeoutError("private token")
                result=await generate_images("conta-a","Uma montanha",0,project_id=project)
                self.assertEqual(result["status"],"submission_unknown")
                self.assertEqual(result["files"],[])
                self.assertNotIn("private",json.dumps(result))
                send.assert_awaited_once()
                send.reset_mock()
                quoting.side_effect=ValueError("Unknown price")
                result=await generate_images("conta-a","Uma montanha",0,project_id=project)
                self.assertEqual(result["status"],"failed_pre_submit")
                send.assert_not_awaited()
                quoting.side_effect=quote
                seed_toggle = [True, False]
                send.side_effect=http_send
                record.workflow_id=str(uuid4())
                result=await generate_images("conta-a","Uma montanha",0,project_id=project)
                self.assertEqual(result["status"],"submission_unknown")
                send.assert_awaited_once()
            finally:
                get_settings.cache_clear()

    async def test_image_generation_count_four_submits_once_and_downloads_all_outputs(self):
        from types import SimpleNamespace
        from gflow_cli.config import get_settings
        from flow_requests import image_request as build_image_request
        from flow_video import generate_images

        project_id = str(uuid4())
        request = {}
        client = SimpleNamespace(account_id="conta-a", prepare=AsyncMock(return_value="captcha"),
            request=lambda rpc, params:{"rpc_id":rpc, "params":params},
            send_submit=AsyncMock(return_value=[]),
            download=AsyncMock(return_value=b"\xff\xd8\xffimage"), close=AsyncMock())
        async def quote(client, job, features):
            job["quoted_credits"] = 0
            return {"model_key":"GEM_PIX_2"}
        def build_request(*args, **kwargs):
            packet = build_image_request(*args, **kwargs)
            request.update(packet)
            return packet
        def image_records(rpc, payload):
            return [SimpleNamespace(media_id=media_id, workflow_id=workflow_id,
                project_id=project_id, image_url=f"https://lh3.googleusercontent.com/{i}",
                dimensions=(1024,1024)) for i, (media_id, workflow_id) in enumerate(zip(
                    request["request_media_ids"], request["request_workflow_ids"]))]

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
            {"GFLOW_CLI_HOME":root,"FLOW_MCP_OUTPUT":root}), patch(
            "flow_video.generation_quote", side_effect=quote), patch(
            "flow_requests.image_request", side_effect=build_request), patch(
            "gflow_cli.api.transports.batchexecute.image_records", side_effect=image_records):
            get_settings.cache_clear()
            try:
                result = await generate_images("conta-a", "Uma paisagem", 0,
                    project_id=project_id, model="nano-pro", aspect="1:1", count=4, client=client)
            finally:
                get_settings.cache_clear()
        self.assertEqual(result["status"], "completed")
        self.assertEqual(len(result["media_ids"]), 4)
        self.assertEqual(len(result["files"]), 4)
        self.assertEqual(len(request["request_media_ids"]), 4)
        client.send_submit.assert_awaited_once()
        self.assertEqual(client.download.await_count, 4)
        client.close.assert_not_awaited()

    def test_original_image_url_keeps_cdn_tokens_and_normalizes_resize(self):
        from flow_video import original_image_url

        for suffix in ("","=w512-h512","=s0"):
            self.assertEqual(original_image_url("https://lh3.googleusercontent.com/media"+suffix+"?signature=private"),
                "https://lh3.googleusercontent.com/media=s0?signature=private")
        url="https://flow-content.google/media?signature=private"
        self.assertEqual(original_image_url(url),url)

    async def test_batch_recovery_downloads_all_ids_and_preserves_state_on_failure(self):
        from gflow_cli.config import get_settings
        from flow_http import FlowHTTP

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,{"GFLOW_CLI_HOME":root}):
            get_settings.cache_clear()
            try:
                ids=[str(uuid4()),str(uuid4())]
                job={"job_id":str(uuid4()),"account_id":"conta-a","kind":"image","count":2,
                     "status":"download_failed","project_id":str(uuid4()),"media_ids":ids,"files":[]}
                save_job(job)
                with patch("flow_http.http_operation",new_callable=AsyncMock) as download, patch.object(
                    FlowHTTP,"close",new_callable=AsyncMock
                ) as close:
                    download.side_effect=[{"path":"first.jpg","bytes":10},ValueError("private URL")]
                    failed=await recover_job("conta-a",job["job_id"])
                    self.assertEqual(failed["status"],"download_failed")
                    self.assertEqual(failed["files"],[])
                    self.assertNotIn("private",str(failed))
                    download.reset_mock()
                    download.side_effect=[{"path":"first.jpg","bytes":10},{"path":"second.jpg","bytes":20}]
                    result=await recover_job("conta-a",job["job_id"])
                    self.assertEqual(result["status"],"completed")
                    self.assertEqual(result["bytes"],30)
                    self.assertEqual([c.args[2]["media_id"] for c in download.call_args_list],ids)
                    self.assertEqual(close.await_count,2)
            finally:
                get_settings.cache_clear()

    async def test_video_batch_tracks_every_id_and_waits_for_all_outputs(self):
        from gflow_cli.config import get_settings
        from gflow_cli.api.transports.batchexecute import GenerationRecord
        from flow_http import FlowHTTP
        from flow_video import generate_video

        ids=[str(uuid4()),str(uuid4())]
        workflows=[str(uuid4()),str(uuid4())]
        project=str(uuid4())
        body=b"1234ftypmp42original"
        resolutions=[]
        async def quote(client, job, features):
            resolutions.append(job["resolution"])
            job["quoted_credits"]=10*job["count"]
            return {"model_key":"veo-key"}
        submitted=[GenerationRecord(workflows[i],project,ids[i],6) for i in range(2)]
        rows=[[ids[i],project,workflows[i],"CAE",None,[]] for i in range(2)]
        polls=[]
        async def poll(rpc,**kwargs):
            media=kwargs["media_id"]
            polls.append(media)
            i=ids.index(media)
            done=(i==1 or polls.count(media)>1)
            return GenerationRecord(workflows[i],project,media,3 if done else 2,
                video_url=f"https://flow-content.google/{media}.mp4" if done else None,size_bytes=len(body))
        async def send(_):
            return list(reversed(rows))
        with tempfile.TemporaryDirectory() as root,patch.dict(os.environ,{"GFLOW_CLI_HOME":root,"FLOW_MCP_OUTPUT":root}), patch(
            "flow_video.generation_quote",side_effect=quote), patch("flow_requests._seed",side_effect=lambda: next(seeds)), patch.object(
            FlowHTTP,"prepare",AsyncMock(return_value="captcha")), patch.object(
            FlowHTTP,"request",side_effect=lambda rpc,params: {"rpc_id":rpc,"params":params}), patch.object(
            FlowHTTP,"capture_submit",AsyncMock(side_effect=AssertionError("No compositor"))), patch.object(
            FlowHTTP,"send_submit",AsyncMock(side_effect=send)) as submit, patch.object(FlowHTTP,"status_from_submit"), patch.object(
            FlowHTTP,"rpc",AsyncMock(side_effect=poll)), patch.object(FlowHTTP,"download",AsyncMock(return_value=body)), patch.object(
            FlowHTTP,"close",AsyncMock()), patch("flow_video.asyncio.sleep",AsyncMock()), patch(
            "flow_assets.video_record",side_effect=lambda rpc,row:submitted[ids.index(row[0])] if rpc=="YhhmEf" else row):
            get_settings.cache_clear()
            try:
                seeds=iter([("seed",v) for pair in zip(ids,workflows) for v in pair])
                job=await generate_video("conta-a","Uma paisagem",20,project_id=project,count=2)
                self.assertEqual(job["status"],"completed")
                self.assertEqual(job["media_ids"],list(reversed(ids)))
                self.assertEqual(job["workflow_ids"],list(reversed(workflows)))
                self.assertEqual(len(job["files"]),2)
                self.assertEqual(polls,[ids[1],ids[0],ids[0]])
                submit.assert_awaited_once()
                # O campo final "2" é constante do protocolo, não a quantidade.
                rows[:]=rows[:1]
                seeds=iter([("seed",ids[0]),("seed",workflows[0])])
                submit.reset_mock()
                job=await generate_video("conta-a","Uma paisagem",20,project_id=project,count=1,
                                         resolution="360p",model="omni-flash")
                self.assertEqual(job["status"],"completed")
                self.assertEqual(job["resolution"],"360p")
                self.assertEqual(resolutions[-2:],["360p","360p"])
                self.assertEqual(job["media_ids"],[ids[0]])
                self.assertEqual(len(job["files"]),1)
                submit.assert_awaited_once()
            finally:get_settings.cache_clear()

    async def test_recovery_ignores_listing_thumbnail_and_verifies_original(self):
        listeners = {}
        media_id = str(uuid4())
        body = b"1234ftypmp42original"
        record = SimpleNamespace(media_id=media_id, is_done=True,
            video_url="https://flow-content.google/video/clip", size_bytes=len(body), workflow_id=str(uuid4()))

        async def goto(*args, **kwargs):
            await listeners["response"](SimpleNamespace(url="https://flow.google.com/batchexecute", text=AsyncMock(return_value="frames")))

        page = SimpleNamespace(on=lambda name, callback: listeners.update({name: callback}),
            remove_listener=lambda name, callback: listeners.pop(name), goto=goto)
        with tempfile.TemporaryDirectory() as root, patch(
            "gflow_cli.api.transports.batchexecute.parse_frames", return_value=[("Zzl0ze", "thumbnail"), ("as29s", "video")]
        ), patch("gflow_cli.api.transports.batchexecute.generation_record", return_value=record) as decode, patch(
            "flow_video.download_bytes", AsyncMock(return_value=body)
        ):
            clip = await recover_clip(page, project_id=str(uuid4()), media_id=media_id, out_dir=Path(root))
            decode.assert_called_once_with("as29s", "video")
            self.assertEqual(clip.path.read_bytes(), body)
            self.assertEqual(listeners, {})

    async def test_redirect_validates_each_host_before_request(self):
        redirect = SimpleNamespace(status=302, headers={"location": "https://cdn.googleusercontent.com/clip"})
        success = SimpleNamespace(status=200, body=AsyncMock(return_value=b"media"))
        with patch("gflow_cli.api.transports._common.get_signed_media", new_callable=AsyncMock) as fetch:
            fetch.side_effect = [redirect, success]
            self.assertEqual(await download_bytes(None, "https://flow-content.google/video/1", "id"), b"media")
            self.assertEqual(fetch.call_count, 2)
            fetch.reset_mock()
            fetch.side_effect = [SimpleNamespace(status=302, headers={"location": "https://google.com.evil.test/token"})]
            with self.assertRaises(ValueError):
                await download_bytes(None, "https://flow-content.google/video/1", "id")
            self.assertEqual(fetch.call_count, 1)
            fetch.reset_mock()
            with self.assertRaises(ValueError):
                await download_bytes(None, "https://user:secret@google.com/clip", "id")
            fetch.assert_not_called()

    def test_image_download_rejects_video_and_html(self):
        self.assertEqual(image_suffix(b"\x89PNG\r\n\x1a\nimage"), ".png")
        self.assertEqual(image_suffix(b"\xff\xd8\xffimage"), ".jpg")
        self.assertEqual(image_suffix(b"RIFF1234WEBPimage"), ".webp")
        for body in (b"1234ftypmp42video", b"<html>error</html>", b""):
            with self.assertRaises(ValueError):
                image_suffix(body)

    async def test_recovery_preserves_uncertain_state_and_never_resubmits(self):
        from gflow_cli.config import get_settings
        from flow_http import FlowHTTP

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GFLOW_CLI_HOME": root}):
            get_settings.cache_clear()
            try:
                job = {"job_id": str(uuid4()), "account_id": "conta-a",
                       "status": "generation_unknown", "project_id": str(uuid4()),
                       "media_id": str(uuid4()), "files": []}
                save_job(job)
                with patch("flow_http.http_operation", new_callable=AsyncMock) as recover, patch.object(
                    FlowHTTP,"close",AsyncMock()), patch.object(FlowHTTP,"send_submit",new_callable=AsyncMock) as submit:
                    recover.side_effect = RuntimeError("sensitive signed URL")
                    result = await recover_job("conta-a", job["job_id"])
                    self.assertEqual(result["status"], "generation_unknown")
                    self.assertEqual(result["recovery_status"], "unavailable")
                    self.assertNotIn("sensitive", str(result))
                    recover.side_effect = None
                    recover.return_value = {"path":str(Path(root)/"clip.mp4"),"bytes":123}
                    result = await recover_job("conta-a", job["job_id"])
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(result["bytes"], 123)
                    submit.assert_not_awaited()
                    with self.assertRaises(ValueError):
                        await recover_job("conta-b", job["job_id"])
            finally:
                get_settings.cache_clear()

    async def test_unknown_submission_reconciles_expected_ids_without_resubmitting(self):
        from types import SimpleNamespace
        from gflow_cli.config import get_settings

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GFLOW_CLI_HOME": root}):
            get_settings.cache_clear()
            try:
                project_id, media_id, workflow_id = (str(uuid4()) for _ in range(3))
                job = {"job_id": str(uuid4()), "account_id": "conta-a", "kind": "video",
                       "video_id_schema": "media-workflow-v1", "status": "submission_unknown",
                       "project_id": project_id, "count": 1, "request_media_ids": [media_id],
                       "request_workflow_ids": [workflow_id], "media_ids": [], "workflow_ids": [],
                       "files": []}
                save_job(job)
                client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(), send_submit=AsyncMock(),
                    templates={}, status_from_submit=AsyncMock(),
                    download=AsyncMock(return_value=b"mp4 body"))
                complete = SimpleNamespace(media_id=media_id, workflow_id=workflow_id,
                    project_id=project_id, is_done=True, is_failed=False,
                    video_url="https://flow-content.google/video", size_bytes=8)
                with patch.dict(os.environ, {"FLOW_MCP_OUTPUT": root}), patch(
                    "flow_assets.parse_assets", return_value=[]), patch(
                    "flow_assets.video_record", side_effect=[ValueError("not listed"), complete]), patch(
                    "gflow_cli.api.transports.migrated_recover._verify"), patch(
                    "flow_http.http_operation", new_callable=AsyncMock,
                ) as download:
                    pending = await recover_job("conta-a", job["job_id"], client=client)
                    self.assertEqual(pending["status"], "submission_unknown")
                    self.assertEqual(pending["recovery_status"], "not_listed")
                    download.assert_not_awaited()

                    recovered = await recover_job("conta-a", job["job_id"], client=client)
                    self.assertEqual(recovered["status"], "completed")
                    self.assertEqual(recovered["media_ids"], [media_id])
                    self.assertEqual(recovered["bytes"], 8)
                    client.download.assert_awaited_once_with("https://flow-content.google/video", media_id)
                    download.assert_not_awaited()
                    client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_unknown_image_and_edit_submissions_reconcile_without_resubmit(self):
        from types import SimpleNamespace
        from gflow_cli.config import get_settings

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GFLOW_CLI_HOME": root}):
            get_settings.cache_clear()
            try:
                for kind in ("image", "image_edit"):
                    project_id, media_id, workflow_id = (str(uuid4()) for _ in range(3))
                    job = {"job_id":str(uuid4()), "account_id":"conta-a", "kind":kind,
                           "status":"submission_unknown", "project_id":project_id, "count":1,
                           "request_media_ids":[media_id], "request_workflow_ids":[workflow_id],
                           "media_ids":[], "workflow_ids":[], "files":[]}
                    save_job(job)
                    client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(), send_submit=AsyncMock())
                    asset = {"media_id":media_id, "workflow_id":workflow_id,
                             "project_id":project_id, "kind":"image"}
                    with patch.dict(os.environ, {"FLOW_MCP_OUTPUT":root}), patch(
                        "flow_assets.parse_assets", return_value=[asset]), patch(
                        "flow_http.http_operation", new_callable=AsyncMock,
                        return_value={"path":str(Path(root)/"image.jpg"), "bytes":123}) as download:
                        result = await recover_job("conta-a", job["job_id"], client=client)
                    self.assertEqual(result["status"], "completed")
                    self.assertEqual(result["media_ids"], [media_id])
                    self.assertEqual(result["workflow_ids"], [workflow_id])
                    self.assertEqual(result["bytes"], 123)
                    download.assert_awaited_once_with(client, "download_asset",
                        {"project_id":project_id, "media_id":media_id})
                    client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_quote_guard_refuses_unknown_and_excess_cost(self):
        pane = SimpleNamespace(inner_text=AsyncMock())
        with patch("gflow_cli.api.transports.migrated_composer.MigratedComposer._select", new_callable=AsyncMock):
            for label, valid in (("A geração vai usar 10 créditos", True),
                                 ("A geração vai usar 20 créditos", False),
                                 ("50 additional credits daily", False)):
                pane.inner_text.return_value = label
                composer = BudgetedComposer(10)
                if valid:
                    await composer._select(None, pane, axis="count", text="x1")
                    self.assertEqual(composer.quoted_credits, 10)
                else:
                    with self.assertRaises(ValueError):
                        await composer._select(None, pane, axis="count", text="x1")
        self.assertEqual(parse_generation_cost("Generation will use 0 credits"), 0)
        with self.assertRaises(ValueError):
            parse_generation_cost("A geração vai usar 10 créditos\nA geração vai usar 20 créditos")

    def test_jobs_survive_restart_and_keep_account_scope(self):
        from gflow_cli.config import get_settings

        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {"GFLOW_CLI_HOME": root}):
            get_settings.cache_clear()
            try:
                job_id = str(uuid4())
                job = {"job_id": job_id, "account_id": "conta-a", "status": "submitting"}
                save_job(job)
                get_settings.cache_clear()
                self.assertEqual(get_job("conta-a", job_id)["status"], "submitting")
                job["status"] = "accepted"
                save_job(job)
                self.assertEqual(get_job("conta-a", job_id)["status"], "accepted")
                self.assertFalse(list((Path(root) / "jobs").glob("*.tmp")))
                with self.assertRaises(ValueError):
                    get_job("conta-b", job_id)
                with self.assertRaises(ValueError):
                    job_path("../cookies")
                save_job({"job_id": str(uuid4()), "account_id": "conta-b", "status": "accepted"})
                (Path(root) / "jobs" / "invalid.json").write_text("invalid", encoding="utf-8")
                self.assertEqual(list_jobs("conta-a")["total"], 1)
                self.assertEqual(list_jobs("conta-a")["jobs"][0]["job_id"], job_id)
                self.assertNotIn("prompt", list_jobs("conta-a")["jobs"][0])
                with self.assertRaises(ValueError):
                    list_jobs("conta-a", 0)
            finally:
                get_settings.cache_clear()


if __name__ == "__main__":
    unittest.main()
