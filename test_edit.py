"""Edição correlacionada pela versão de origem, sem depender de prompt traduzido."""
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import os
import tempfile
from pathlib import Path
from uuid import uuid4

from flow_edit import image_edit_record


class EditTest(unittest.TestCase):
    def test_annotations_validate_geometry_and_uploaded_image_versions(self):
        from flow_annotations import validate_annotations
        from flow_edit import image_versions, asset_details
        selection = [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]
        validate_annotations(selection, [{"points": [[0, 0], [1, 1]], "color": "#ff0000"}])
        for region, drawings in (([[0, 0], [0, 0], [0, 0]], None),
                ([[0, 0], [1, 0], [float("nan"), 1]], None),
                (None, [{"points": [[0, 0], [1, 1]], "width": True}]),
                (None, [{"points": [[0, 0], [1, 1]], "color": "url(private)"}])):
            with self.assertRaises(ValueError):
                validate_annotations(region, drawings)
        project, source, workflow = (str(uuid4()) for _ in range(3))
        row = [source, project, workflow, "CAE", None, [],
               [None, [None, None, None, "https://lh3.googleusercontent.com/upload"], [1024, 1024]]]
        data = [None, [], [row], None, None, None, None, None]
        self.assertEqual(image_versions(data, source, project)[0].workflow_id, workflow)
        self.assertEqual(asset_details(data, "conta-a", project, source)["versions"][0]["media_id"], source)

    def test_translated_edit_ignores_existing_and_other_workflows(self):
        project, workflow, source, new = (str(uuid4()) for _ in range(4))
        old=SimpleNamespace(media_id=source,workflow_id=workflow,project_id=project,prompt="original")
        other=SimpleNamespace(media_id=str(uuid4()),workflow_id=str(uuid4()),project_id=project,prompt="irrelevant")
        translated=SimpleNamespace(media_id=new,workflow_id=workflow,project_id=project,prompt="Translated English prompt")
        with patch("gflow_cli.api.transports.batchexecute.image_records") as decode:
            for records, valid in (([old,other],False),([old,other,translated],True),([translated,translated],False)):
                decode.return_value=records
                kwargs=dict(project_id=project,workflow_id=workflow,previous_ids={source},workflows=[])
                if valid:
                    self.assertEqual(image_edit_record("ogiZ0b",[],**kwargs).media_id,new)
                else:
                    with self.assertRaises(ValueError):
                        image_edit_record("ogiZ0b",[],**kwargs)


class NativeEditTest(unittest.IsolatedAsyncioTestCase):
    async def test_annotation_and_reference_keep_original_workflow_and_stop_on_uncertain_upload(self):
        from flow_edit import edit_image
        from gflow_cli.config import get_settings
        project, source, workflow, annotated, reference, output = (str(uuid4()) for _ in range(6))
        selection = [[.1, .1], [.9, .1], [.9, .9], [.1, .9]]
        old = SimpleNamespace(media_id=source, workflow_id=workflow, project_id=project)
        new = SimpleNamespace(media_id=output, workflow_id=workflow, project_id=project,
                              image_url="https://lh3.googleusercontent.com/result")
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=[None, []]),
            prepare=AsyncMock(return_value="captcha"), download=AsyncMock(return_value=b"\xff\xd8\xffimage"),
            request=lambda rpc, params: {"rpc_id": rpc, "params": params}, send_submit=AsyncMock(return_value=[]))
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ,
                {"GFLOW_CLI_HOME": home, "FLOW_MCP_OUTPUT": home}), \
             patch("flow_edit.image_versions", return_value=[old]), \
             patch("flow_edit.parse_assets", return_value=[
                 {"media_id": source, "kind": "image", "name": "source.png"},
                 {"media_id": reference, "kind": "image", "name": "reference.png"}]), \
             patch("flow_assets.image_download_url", return_value="https://lh3.googleusercontent.com/source"), \
             patch("flow_edit.generation_quote", AsyncMock(return_value={"model_key": "NARWHAL"})), \
             patch("flow_annotations.upload_annotated_image", AsyncMock(return_value={
                 "status": "uploaded", "media_id": annotated})) as annotate, \
             patch("flow_video.prepare_reference_uploads", AsyncMock(return_value=[])) as upload, \
             patch("gflow_cli.api.transports.batchexecute.image_records", return_value=[old, new]):
            get_settings.cache_clear()
            try:
                for status in ("uploaded", "submission_unknown"):
                    annotate.return_value = {"status": status, "media_id": annotated}
                    client.send_submit.reset_mock(); upload.reset_mock()
                    with patch("flow_requests._seed", side_effect=[("seed", output), ("seed", str(uuid4()))]):
                        job = await edit_image("conta-a", project, source, "Editar região", 0,
                                               selection=selection,
                                               reference_asset_ids=[reference], client=client)
                    if status == "uploaded":
                        self.assertEqual(job["status"], "completed")
                        packet = client.send_submit.call_args.args[0]
                        self.assertEqual(packet["params"][1][0][2], [
                            [annotated, None, None, None, 2], [reference, None, None, None, 1]])
                        self.assertEqual(job["workflow_ids"], [workflow])
                        self.assertEqual(job["source_media_id"], source)
                        self.assertEqual(job["reference_asset_ids"], [reference])
                        upload.assert_awaited_once_with(job, [], client=client)
                        client.send_submit.assert_awaited_once()
                    else:
                        self.assertEqual(job["status"], "failed_pre_submit")
                        client.send_submit.assert_not_awaited()
                        upload.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_batch_edit_stops_after_uncertain_job_and_tracks_remaining_budget(self):
        from flow_edit import edit_images
        from flow_video import get_job
        from gflow_cli.config import get_settings

        project, *media_ids = (str(uuid4()) for _ in range(4))
        workflows = {media_id:str(uuid4()) for media_id in media_ids}
        results = [
            {"job_id":str(uuid4()),"status":"completed","media_ids":[str(uuid4())],
             "request_media_ids":[str(uuid4())],"files":["one.jpg"],"quoted_credits":10,
             "bytes":3},
            {"job_id":str(uuid4()),"status":"submission_unknown","media_ids":[],
             "request_media_ids":[str(uuid4())],"files":[],"quoted_credits":10},
        ]
        client = SimpleNamespace(account_id="conta-a",rpc=AsyncMock(return_value=[None,[]]),close=AsyncMock())
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ,{"GFLOW_CLI_HOME":home}), \
             patch("flow_edit.image_versions",side_effect=lambda _p,mid,_project:[
                 SimpleNamespace(workflow_id=workflows[mid])]), \
             patch("flow_capabilities.read_capabilities",AsyncMock(return_value={})) as capabilities, \
             patch("flow_capabilities.quote_configuration",return_value={
                 "model_key":"NARWHAL","credits_per_output":10,"quoted_credits":10}), \
             patch("flow_edit.edit_image",AsyncMock(side_effect=results)) as edit:
            get_settings.cache_clear()
            try:
                batch = await edit_images("conta-a",project,media_ids,"Make them monochrome",30,client=client)
                self.assertEqual(batch["status"],"submission_unknown")
                self.assertEqual(len(batch["subjobs"]),2)
                self.assertEqual(batch["reserved_credits"],20)
                self.assertEqual(batch["remaining_budget"],10)
                self.assertEqual([call.args[2] for call in edit.call_args_list],media_ids[:2])
                self.assertEqual(edit.call_args_list[1].args[4],20)
                self.assertEqual(get_job("conta-a",batch["job_id"])["status"],"submission_unknown")
                capabilities.assert_awaited_once()
            finally:
                get_settings.cache_clear()

    async def test_crop_and_uploaded_image_download_preserve_workflow_and_reject_bad_region(self):
        from flow_assets import image_download_url
        from flow_edit import crop_image
        from gflow_cli.config import get_settings

        project, source, workflow, new = (str(uuid4()) for _ in range(4))
        row=[source,project,workflow,'CAE',None,[],[None,[None,None,None,'https://lh3.googleusercontent.com/upload'],[1024,1024]]]
        data=[None,[],[row],None,None,None,None,None]
        self.assertEqual(image_download_url(data,project,source),'https://lh3.googleusercontent.com/upload')
        cropped=[new,project,workflow,'CAI',None,[],[None,[None,None,None,'https://lh3.googleusercontent.com/crop'],[512,512]]]
        client=SimpleNamespace(account_id='conta-a',rpc=AsyncMock(return_value=data),
            request=lambda rpc,params:{'rpc_id':rpc,'params':params},send_submit=AsyncMock(return_value=[cropped]),
            download=AsyncMock(return_value=b'\xff\xd8\xffimage'))
        with tempfile.TemporaryDirectory() as home,patch.dict(os.environ,{'GFLOW_CLI_HOME':home,'FLOW_MCP_OUTPUT':home}),patch('flow_requests._seed',return_value=('seed',new)):
            get_settings.cache_clear()
            try:
                result=await crop_image('conta-a',project,source,[0.25,0.25,0.75,0.75],client=client)
                self.assertEqual(result['status'],'completed')
                self.assertEqual(result['workflow_ids'],[workflow])
                self.assertEqual(client.send_submit.call_args.args[0]['params'],[1,source,None,[0.25,0.25,0.75,0.75],None,None,'seed'])
                client.send_submit.assert_awaited_once()
                for rect in ([],[0,0,0,1],[-1,0,1,1],[0,0,float('nan'),1]):
                    with self.assertRaises(ValueError):
                        await crop_image('conta-a',project,source,rect,client=client)
                client.send_submit.assert_awaited_once()
            finally:get_settings.cache_clear()

    async def test_edit_preserves_source_and_rejects_unrelated_version_without_retry(self):
        from gflow_cli.config import get_settings
        from flow_edit import edit_image
        from flow_http import FlowHTTP
        from flow_video import get_job

        project, source, workflow, new = (str(uuid4()) for _ in range(4))
        old = SimpleNamespace(media_id=source, workflow_id=workflow, project_id=project)
        record = SimpleNamespace(media_id=new, workflow_id=workflow, project_id=project,
                                 image_url="https://lh3.googleusercontent.com/image")
        async def quote(client, job, features):
            self.assertEqual(features, [1, 4])
            job["quoted_credits"] = 0
            return {"model_key":"NARWHAL"}
        async def send(packet):
            self.assertEqual(packet["params"][1][0][2], [[source, None, None, None, 2]])
            self.assertEqual(packet["params"][3][4], workflow)
            self.assertIsNone(packet["params"][1][0][12])
            return []
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ,
                {"GFLOW_CLI_HOME":root,"FLOW_MCP_OUTPUT":root}), patch(
                "flow_edit.image_versions",return_value=[old]), patch(
                "flow_edit.generation_quote",side_effect=quote) as quoting, patch(
                "flow_requests._seed",side_effect=lambda: next(seeds)), patch.object(
                FlowHTTP,"rpc",AsyncMock(return_value=[None,[]])), patch.object(
                FlowHTTP,"prepare",AsyncMock(return_value="captcha")), patch.object(
                FlowHTTP,"request",side_effect=lambda rpc,params: {"rpc_id":rpc,"params":params}), patch.object(
                FlowHTTP,"send_submit",AsyncMock(side_effect=send)) as submit, patch.object(
                FlowHTTP,"download",AsyncMock(return_value=b"\xff\xd8\xffimage")) as download, patch.object(
                FlowHTTP,"close",AsyncMock()), patch(
                "gflow_cli.api.transports.batchexecute.image_records",return_value=[old,record]):
            get_settings.cache_clear()
            try:
                seeds=iter([("seed",new),("seed",str(uuid4()))])
                job=await edit_image("conta-a",project,source,"Edit",0)
                self.assertEqual(job["status"],"completed")
                self.assertEqual(job["previous_media_ids"],[source])
                self.assertEqual(job["request_workflow_ids"],[workflow])
                self.assertEqual(get_job("conta-a",job["job_id"])["media_id"],new)
                submit.assert_awaited_once()
                submit.reset_mock()
                download.reset_mock()
                seeds=iter([("seed",new),("seed",str(uuid4()))])
                record.media_id=str(uuid4())
                job=await edit_image("conta-a",project,source,"Edit",0)
                self.assertEqual(job["status"],"submission_unknown")
                self.assertNotIn("captcha",str(job))
                submit.assert_awaited_once()
                download.assert_not_awaited()
                submit.reset_mock()
                quoting.side_effect=ValueError("Unknown cost")
                job=await edit_image("conta-a",project,source,"Edit",0)
                self.assertEqual(job["status"],"failed_pre_submit")
                submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()


class NativeImageUpscaleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from gflow_cli.config import get_settings
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = patch.dict(os.environ, {"GFLOW_CLI_HOME":self.temp.name, "FLOW_MCP_OUTPUT":self.temp.name})
        env.start()
        self.addCleanup(env.stop)
        get_settings.cache_clear()
        self.addCleanup(get_settings.cache_clear)
        self.project, self.media, self.workflow = (str(uuid4()) for _ in range(3))
        self.image = b"\x89PNG\r\n\x1a\nfixture"
        self.capabilities = {"observed_at":"now", "modes":{"image":{"models":[{
            "model_id":"upsample_2k", "variants":[{"model_key":"GEM_PIX_2_UPSAMPLE_2K",
                "available":True, "credits_per_output":0, "input_feature_codes":[[5]]}]}]}}}
        quoting = patch("flow_capabilities.read_capabilities", AsyncMock(return_value=self.capabilities))
        quoting.start()
        self.addCleanup(quoting.stop)

    def client(self):
        import base64
        from contextlib import asynccontextmanager
        from unittest.mock import MagicMock
        from flow_requests import flow_context

        self.events = []
        page = SimpleNamespace(goto=AsyncMock(), get_by_role=MagicMock(
            return_value=SimpleNamespace(click=AsyncMock())))
        @asynccontextmanager
        async def browser_page():
            self.events.append("page")
            yield page
            self.events.append("closed")
        async def capture(*args):
            self.events.append("capture")
            return {"rpc_id":"SPrCad", "params":[self.media, 1, flow_context(self.project, "test-token")]}
        async def send(*args):
            self.events.append("submit")
            return [[str(uuid4()), self.project, str(uuid4())], base64.b64encode(self.image).decode()]
        row = [self.media, self.project, self.workflow, "CAE", None, [],
               [None, [None, None, None], [1024, 1024]]]
        return SimpleNamespace(account_id="conta-a", browser=SimpleNamespace(page=browser_page),
            rpc=AsyncMock(return_value=[None, [], [row], None, None, None, None, None]),
            capture_submit=AsyncMock(side_effect=capture), send_submit=AsyncMock(side_effect=send))

    async def test_native_upscale_saves_image_and_reuses_completed_output_without_mutation(self):
        from flow_edit import upscale_image_native
        client = self.client()
        output_media = str(uuid4())
        with patch("flow_assets.upload_image", AsyncMock(return_value={"status":"uploaded", "media_id":output_media})) as upload:
            result = await upscale_image_native("conta-a", self.project, self.media, "2K", upload_to_flow=True, client=client)
            again = await upscale_image_native("conta-a", self.project, self.media, upload_to_flow=True, client=client)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.image)
        self.assertEqual(result["credit_cost"], 0)
        self.assertEqual(result["asset_media_id"], output_media)
        self.assertEqual(again["job_id"], result["job_id"])
        self.assertEqual(self.events, ["page", "capture", "closed", "submit"])
        client.send_submit.assert_awaited_once()
        upload.assert_awaited_once_with("conta-a", self.project, result["output_path"], client=client)

    async def test_native_upscale_preserves_local_file_and_does_not_repeat_failed_upload(self):
        from flow_edit import upscale_image_native
        client = self.client()
        with patch("flow_assets.upload_image", AsyncMock(side_effect=RuntimeError("upload unavailable"))) as upload:
            result = await upscale_image_native("conta-a", self.project, self.media, upload_to_flow=True, client=client)
            again = await upscale_image_native("conta-a", self.project, self.media, upload_to_flow=True, client=client)
        self.assertEqual(result["status"], "completed")
        self.assertEqual(again["flow_upload_status"], "failed")
        self.assertEqual(Path(result["output_path"]).read_bytes(), self.image)
        upload.assert_awaited_once()
        client.send_submit.assert_awaited_once()

    async def test_native_upscale_uncertain_submission_is_never_repeated(self):
        from flow_edit import upscale_image_native
        client = self.client()
        client.send_submit.side_effect = RuntimeError("response lost")
        first = await upscale_image_native("conta-a", self.project, self.media, client=client)
        second = await upscale_image_native("conta-a", self.project, self.media, client=client)
        self.assertEqual(first["status"], "submission_unknown")
        self.assertEqual(second["status"], "submission_unknown")
        client.send_submit.assert_awaited_once()
        client.capture_submit.assert_awaited_once()

    async def test_native_upscale_rejects_capture_from_other_source_before_post(self):
        from flow_edit import upscale_image_native
        from flow_requests import flow_context
        client = self.client()
        client.capture_submit.side_effect = None
        client.capture_submit.return_value = {"rpc_id":"SPrCad", "params":[str(uuid4()), 1, flow_context(self.project,"test-token")]}
        result = await upscale_image_native("conta-a", self.project, self.media, client=client)
        self.assertEqual(result["status"], "failed_pre_submit")
        client.send_submit.assert_not_awaited()

    async def test_native_upscale_catalog_blocks_unavailable_or_paid_configuration(self):
        from flow_edit import upscale_image_native
        client = self.client()
        self.capabilities["modes"]["image"]["models"][0]["variants"][0]["credits_per_output"] = 50
        result = await upscale_image_native("conta-a", self.project, self.media, client=client)
        self.assertEqual(result["status"], "failed_pre_submit")
        client.capture_submit.assert_not_awaited()
        client.send_submit.assert_not_awaited()

    async def test_native_upscale_rejects_foreign_or_malformed_response_without_retry(self):
        import base64
        from flow_edit import upscale_image_native
        client = self.client()
        client.send_submit.side_effect = None
        client.send_submit.return_value = [[str(uuid4()), str(uuid4()), str(uuid4())], base64.b64encode(self.image).decode()]
        result = await upscale_image_native("conta-a", self.project, self.media, client=client)
        again = await upscale_image_native("conta-a", self.project, self.media, client=client)
        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(again["files"], [])
        client.send_submit.assert_awaited_once()

    async def test_native_upscale_rejects_missing_asset_or_resolution_before_send(self):
        from flow_edit import upscale_image_native
        client = self.client()
        with self.assertRaises(ValueError):
            await upscale_image_native("conta-a", self.project, self.media, "8k", client=client)
        client.rpc.assert_not_awaited()
        client.rpc.return_value = [None, [], [], None, None, None, None, None]
        result = await upscale_image_native("conta-a", self.project, self.media, client=client)
        self.assertEqual(result["status"], "failed_pre_submit")
        with self.assertRaises(ValueError):
            await upscale_image_native("conta-a", self.project, self.media, upload_to_flow="yes", client=client)
        client.send_submit.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
