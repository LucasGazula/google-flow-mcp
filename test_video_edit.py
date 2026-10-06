"""Edição/extensão: origem, orçamento, revisão e envio único."""
import os
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from flow_assets import video_record
from flow_video import generate_video, get_job, refine_video, save_job


def video_row(project, media, workflow, revision="CAE", status=3, model="veo_3_1_t2v_lite", duration=8):
    details = [None]*14
    details[8], details[9], details[13] = [status], 1, 20
    info = [None]*17
    info[8], info[12], info[16] = "https://flow-content.google/original.mp4", model, 2
    return [media,project,workflow,revision,None,details,None,[info,[None,None,[duration]]]]


class VideoEditTest(unittest.IsolatedAsyncioTestCase):
    def test_video_record_picks_expected_media_among_nested_rows(self):
        from flow_assets import payload_shape

        project, media, workflow, frame, frame_wf = (str(uuid4()) for _ in range(5))
        # Quadro inicial aninhado com o mesmo formato de registro, antes da mídia.
        payload = [[video_row(project, frame, frame_wf, revision=None)], video_row(project, media, workflow, revision=None)]
        record = video_record("as29s", payload, media)
        self.assertEqual((record.media_id, record.workflow_id), (media, workflow))
        with self.assertRaises(ValueError):
            video_record("as29s", payload, str(uuid4()))
        shape = repr(payload_shape(payload))
        self.assertNotIn(media, shape)
        self.assertNotIn("https://", shape)

    async def test_separate_workflow_edit_persists_expected_ids_and_never_retries(self):
        from gflow_cli.config import get_settings
        project, source, workflow, output, new_workflow = (str(uuid4()) for _ in range(5))
        data = [None, [], [video_row(project, source, workflow)], None, None, None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(return_value="captcha"),
            request=lambda rpc, params: {"rpc_id":rpc, "params":params},
            send_submit=AsyncMock(side_effect=TimeoutError("private error")))
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME":home}), \
             patch("flow_video.generation_quote", AsyncMock(return_value={"model_key":"abra_edit"})), \
             patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", new_workflow)]):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Edit", 10, project_id=project,
                    model="omni-flash", operation="edit", source_media_id=source,
                    create_new_workflow=True, client=client)
                self.assertEqual(job["status"], "submission_unknown")
                self.assertEqual(job["source_workflow_id"], workflow)
                self.assertEqual(job["request_workflow_ids"], [new_workflow])
                self.assertEqual(job["request_media_ids"], [output])
                self.assertTrue(get_job("conta-a", job["job_id"])["create_new_workflow"])
                client.send_submit.assert_awaited_once()
                self.assertNotIn("private error", str(job))
            finally:
                get_settings.cache_clear()

    async def test_refinement_chain_reuses_latest_output_and_stops_on_uncertainty(self):
        project, source, reference, output = (str(uuid4()) for _ in range(4))
        calls = []
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())

        async def edit(account_id, prompt, budget, **kwargs):
            calls.append((prompt, budget, kwargs))
            if prompt == "first":
                return {"job_id":"job-1", "status":"completed", "media_id":output,
                        "workflow_id":str(uuid4()), "quoted_credits":10}
            return {"job_id":"job-2", "status":"submission_unknown", "media_id":str(uuid4()),
                    "workflow_id":str(uuid4()), "quoted_credits":10}

        with patch("flow_video.generate_video", side_effect=edit):
            result = await refine_video("conta-a", project, source,
                ["first", "second", "must not send"], 20,
                reference_asset_ids=[reference], client=client)

        self.assertEqual(result["status"], "submission_unknown")
        self.assertEqual(result["media_ids"], [output])
        self.assertEqual(result["quoted_credits"], 20)
        self.assertEqual(result["remaining_budget"], 0)
        self.assertEqual([call[1] for call in calls], [20, 10])
        self.assertEqual(calls[0][2]["source_media_id"], source)
        self.assertEqual(calls[1][2]["source_media_id"], output)
        self.assertEqual(calls[1][2]["reference_asset_ids"], [reference])
        self.assertEqual(result["job_ids"], ["job-1", "job-2"])

    async def test_refinement_uploads_local_references_once_then_reuses_ids(self):
        from pathlib import Path

        project, source, uploaded, output1, output2 = (str(uuid4()) for _ in range(5))
        calls = []
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())

        async def edit(account_id, prompt, budget, **kwargs):
            calls.append(kwargs)
            index = len(calls)
            result = {"job_id":f"job-{index}", "status":"completed",
                      "media_id":output1 if index == 1 else output2,
                      "workflow_id":str(uuid4()), "quoted_credits":5}
            if index == 1:
                result["reference_uploads"] = [{"status":"uploaded", "media_id":uploaded}]
            return result

        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "reference.png"
            path.write_bytes(b"placeholder")
            with patch("gflow_cli.api.client.validate_image_file", new_callable=AsyncMock), \
                 patch("flow_video.generate_video", side_effect=edit):
                result = await refine_video("conta-a", project, source,
                    ["first", "second"], 10, reference_images=[str(path)], client=client)

        self.assertEqual(result["status"], "completed")
        self.assertEqual(result["media_ids"], [output1, output2])
        self.assertEqual(calls[0]["reference_images"], [str(path.resolve())])
        self.assertIsNone(calls[1]["reference_images"])
        self.assertEqual(calls[1]["reference_asset_ids"], [uploaded])

    async def test_refinement_rejects_more_than_three_turns_before_sending(self):
        project, source = str(uuid4()), str(uuid4())
        client = SimpleNamespace(account_id="conta-a", close=AsyncMock())
        with patch("flow_video.generate_video", new_callable=AsyncMock) as generate:
            with self.assertRaises(ValueError):
                await refine_video("conta-a", project, source, ["edit"] * 4, 20, client=client)
        generate.assert_not_awaited()

    async def test_refinement_rights_notice_returns_confirmation_without_spending_budget(self):
        project, source = str(uuid4()), str(uuid4())
        with patch("flow_video.generate_video", AsyncMock(return_value={
                "status":"reference_confirmation_required", "confirmation_id":"local-confirm",
                "reference_upload_status":"confirmation_required", "quoted_credits":10})) as generate:
            result = await refine_video("conta-a", project, source, ["one","must not send"], 20,
                client=SimpleNamespace(account_id="conta-a"))
        self.assertEqual(result["status"], "reference_confirmation_required")
        self.assertEqual(result["remaining_budget"], 20)
        self.assertEqual(result["quoted_credits"], 0)
        self.assertEqual(result["turns"][0]["confirmation_id"], "local-confirm")
        generate.assert_awaited_once()

    async def test_edit_reuses_project_reference_and_checks_variant_before_submission(self):
        from gflow_cli.config import get_settings
        project, source, workflow, reference = (str(uuid4()) for _ in range(4))
        video = video_row(project, source, workflow)
        image = [reference, project, str(uuid4()), "CAE", None, [],
                 [None, [None, None, None, "https://lh3.googleusercontent.com/ref"], [1024, 1024]]]
        data = [None, [], [video, image], None, None, None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(return_value="captcha"),
            request=lambda rpc, params: {"rpc_id":rpc, "params":params},
            send_submit=AsyncMock(side_effect=RuntimeError("uncertain")))
        async def quote(client, job, features):
            self.assertEqual(job["duration_seconds"], 4)
            self.assertEqual(job["resolution"], "360p")
            self.assertEqual(features, [1, 6, 18, 19, 20])
            return {"model_key":"catalog-edit-variant"}
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME":home}), \
             patch("flow_video.generation_quote", side_effect=quote):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Use reference lighting", 20,
                    project_id=project, model="omni-flash", operation="edit", source_media_id=source,
                    duration_seconds=4, resolution="360p", reference_asset_ids=[reference], client=client)
                self.assertEqual(job["status"], "submission_unknown")
                row = client.send_submit.call_args.args[0]["params"][0][0]
                self.assertEqual(row[8], [[None, reference]])
                self.assertEqual(row[2], "catalog-edit-variant")
                self.assertEqual(job["reference_asset_ids"], [reference])
                client.send_submit.reset_mock()
                job = await generate_video("conta-a", "Edit", 20,
                    project_id=project, model="omni-flash", operation="edit", source_media_id=source,
                    reference_asset_ids=[str(uuid4())], client=client)
                self.assertEqual(job["status"], "failed_pre_submit")
                client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_project_images_can_be_used_as_initial_and_final_frames(self):
        from gflow_cli.config import get_settings

        project, start_id, end_id, video_id = (str(uuid4()) for _ in range(4))
        start = [start_id, project, str(uuid4()), "CAE", None, [],
                 [None, [None, None, None, "https://lh3.googleusercontent.com/start"], [1024, 1024]]]
        end = [end_id, project, str(uuid4()), "CAE", None, [],
               [None, [None, None, None, "https://lh3.googleusercontent.com/end"], [1024, 1024]]]
        data = [None, [], [start, end], None, None, None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(return_value="captcha"),
            request=lambda rpc, params: {"rpc_id":rpc, "params":params},
            send_submit=AsyncMock(side_effect=RuntimeError("unknown result")))

        async def quote(client, job, features):
            self.assertEqual(features, [1, 5, 7])
            job["quoted_credits"] = 10
            return {"model_key":"catalog-frame-variant"}

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME":home}), \
             patch("flow_video.generation_quote", side_effect=quote):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Transição entre estes quadros", 10,
                    project_id=project, start_image_asset_id=start_id,
                    end_image_asset_id=end_id, client=client)
                packet = client.send_submit.call_args.args[0]
                row = packet["params"][0][0]
                self.assertEqual(job["status"], "submission_unknown")
                self.assertEqual(packet["rpc_id"], "nprQif")
                self.assertEqual(row[4], [None, start_id])
                self.assertEqual(row[5], [None, end_id])
                client.send_submit.assert_awaited_once()

                client.send_submit.reset_mock()
                client.rpc.return_value = [None, [], [video_row(project, video_id, str(uuid4()))],
                                           None, None, None, None, None]
                job = await generate_video("conta-a", "Invalid frame type", 10,
                    project_id=project, start_image_asset_id=video_id, client=client)
                self.assertEqual(job["status"], "failed_pre_submit")
                client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_uploaded_video_can_reach_edit_submission_but_not_extension(self):
        from gflow_cli.config import get_settings
        project, source, workflow = (str(uuid4()) for _ in range(3))
        row = video_row(project, source, workflow)
        row[7][0] = None
        row[7][1] = [1280, 720, [8]]
        data = [None, [], [row], None, None, None, None, None]
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(return_value="captcha"), request=lambda rpc, params: {"rpc_id": rpc, "params": params},
            send_submit=AsyncMock(side_effect=RuntimeError("unknown result")), close=AsyncMock())

        async def quote(client, job, features):
            job["quoted_credits"] = 40
            return {"model_key": "abra_edit"}

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home}), \
             patch("flow_video.generation_quote", side_effect=quote):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Change the lighting", 40, project_id=project,
                    model="omni-flash", operation="edit", source_media_id=source,
                    segment_start=1, segment_end=5, client=client)
                self.assertEqual(job["status"], "submission_unknown")
                self.assertEqual(job["workflow_id"], workflow)
                self.assertEqual(job["source_fps"], 30)
                self.assertEqual(client.send_submit.call_args.args[0]["params"][0][0][0],
                                 [None, source, 30, 150])
                client.send_submit.assert_awaited_once()
                client.send_submit.reset_mock()
                job = await generate_video("conta-a", "Continue", 40, project_id=project,
                    model="veo-lite", operation="extend", source_media_id=source, client=client)
                self.assertEqual(job["status"], "failed_pre_submit")
                client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    def test_new_video_revision_decodes_without_mutating_remote_response(self):
        for suffix in ("_720p_upsampled", "_upsampled"):
            row = video_row(*(str(uuid4()) for _ in range(3)),revision="CAI")
            row[0] += suffix
            result = video_record("as29s",row)
            self.assertTrue(result.is_done)
            self.assertEqual(result.media_id,row[0])
            self.assertEqual(row[3],"CAI")
        with self.assertRaises(ValueError):
            video_record("as29s",[row,row])
        # Desde 05/10/2026 vídeos novos chegam sem a versão 1.
        fresh = video_row(*(str(uuid4()) for _ in range(3)),revision=None)
        self.assertTrue(video_record("as29s",fresh).is_done)
        self.assertIsNone(fresh[3])

    def test_legacy_video_jobs_migrate_ids_once_and_keep_downloads(self):
        from gflow_cli.config import get_settings
        with tempfile.TemporaryDirectory() as home,patch.dict(os.environ,{'GFLOW_CLI_HOME':home}):
            get_settings.cache_clear()
            try:
                media,workflow=(str(uuid4()) for _ in range(2))
                job={'job_id':str(uuid4()),'account_id':'conta-a','kind':'video',
                     'media_id':workflow,'workflow_id':media,'media_ids':[workflow],
                     'workflow_ids':[media],'files':['existing.mp4']}
                save_job(job)
                read=get_job('conta-a',job['job_id'])
                self.assertEqual(read['media_id'],media)
                self.assertEqual(read['workflow_id'],workflow)
                self.assertEqual(read['legacy_video_ids']['media_id'],workflow)
                self.assertEqual(read['files'],['existing.mp4'])
                self.assertEqual(get_job('conta-a',job['job_id'])['media_id'],media)
            finally:get_settings.cache_clear()

    async def test_mutations_validate_source_quote_twice_submit_once_and_preserve_history(self):
        from gflow_cli.config import get_settings
        project, source, workflow = (str(uuid4()) for _ in range(3))
        row = video_row(project,source,workflow)
        data = [None,[],[row],None,None,None,None,None]
        body = b"1234ftypmp42original!"
        features_seen = []
        async def quote(client,job,features):
            features_seen.append(features)
            job['quoted_credits'] = 20 if job['model']=='omni-flash' else 10
            return {'model_key':'abra_edit' if job['model']=='omni-flash' else 'veo_3_1_extension_lite'}
        submitted=[]
        async def send(packet):
            submitted.append(packet)
            result=video_row(project,output,workflow,revision="CAI")
            result[5][13]=len(body)
            return result
        client=SimpleNamespace(account_id="conta-a",rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(return_value="captcha"),status_from_submit=lambda *args:None,
            download=AsyncMock(return_value=body),close=AsyncMock())
        client.request=lambda rpc,params:{'rpc_id':rpc,'params':params}
        client.send_submit=AsyncMock(side_effect=send)
        with tempfile.TemporaryDirectory() as home,patch.dict(os.environ,{'GFLOW_CLI_HOME':home,'FLOW_MCP_OUTPUT':home}),patch('flow_video.generation_quote',side_effect=quote):
            get_settings.cache_clear()
            try:
                for operation,model,cost,features in (("edit","omni-flash",20,[1,6,18,19,20]),("extend","veo-lite",10,[1,14])):
                    output=str(uuid4())
                    with patch('flow_requests._seed',side_effect=[('media-seed',output),('workflow-seed',str(uuid4()))]):
                        job=await generate_video('conta-a','Mudar iluminação',cost,project_id=project,
                            model=model,operation=operation,source_media_id=source,segment_start=1,segment_end=5,client=client)
                    self.assertEqual(job['status'],'completed')
                    self.assertEqual(job['workflow_ids'],[workflow])
                    self.assertEqual(job['source_media_id'],source)
                    self.assertEqual(features_seen[-2:],[features,features])
                    self.assertEqual(submitted[-1]['params'][0][0][0],[None,source,24,120])
                self.assertEqual(client.send_submit.await_count,2)
                for changes in ({'source_media_id':str(uuid4())},{'aspect':'9:16'},{'segment_end':9}):
                    job=await generate_video('conta-a','Editar',20,project_id=project,model='omni-flash',
                        operation='edit',client=client,**{'source_media_id':source,**changes})
                    self.assertEqual(job['status'],'failed_pre_submit')
                self.assertEqual(client.send_submit.await_count,2)
                client.close.assert_not_awaited()
            finally: get_settings.cache_clear()

    async def test_quote_only_edit_returns_quoted_status_without_submitting_or_saving_job(self):
        from gflow_cli.config import get_settings

        project, source, workflow = (str(uuid4()) for _ in range(3))
        data = [None, [], [video_row(project, source, workflow)], None, None, None, None, None]
        client = SimpleNamespace(
            account_id="conta-a",
            rpc=AsyncMock(return_value=data),
            prepare=AsyncMock(),
            request=AsyncMock(),
            send_submit=AsyncMock(),
        )

        async def quote(client, job, features):
            job["quoted_credits"] = 10
            job["credits_before"] = 100
            return {"model_key": "abra_edit", "quoted_credits": 10}

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home}), \
             patch("flow_video.generation_quote", side_effect=quote):
            get_settings.cache_clear()
            try:
                job = await generate_video(
                    "conta-a", "Ajustar cor e brilho", 20,
                    project_id=project, model="omni-flash", operation="edit",
                    source_media_id=source, quote_only=True, client=client,
                )
                self.assertEqual(job["status"], "quoted")
                self.assertEqual(job["quoted_credits"], 10)
                self.assertEqual(job["credits_before"], 100)
                self.assertTrue(job.get("quote_only"))
                client.prepare.assert_not_awaited()
                client.send_submit.assert_not_awaited()
                jobs_dir = Path(home) / "jobs"
                self.assertFalse(jobs_dir.exists() and any(jobs_dir.iterdir()))
            finally:
                get_settings.cache_clear()

    async def test_quote_only_without_project_id_uses_latest_project_without_creating(self):
        from gflow_cli.config import get_settings

        latest, older = str(uuid4()), str(uuid4())
        client = SimpleNamespace(
            account_id="conta-a",
            rpc=AsyncMock(return_value=[[[latest, ["Recente"]], [older, ["Antigo"]]]]),
            prepare=AsyncMock(),
            send_submit=AsyncMock(),
        )
        seen = []

        async def quote(client, job, features):
            seen.append(job["project_id"])
            job["quoted_credits"] = 10
            return {"model_key": "veo_lite", "quoted_credits": 10}

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home}), \
             patch("flow_video.generation_quote", side_effect=quote):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Gerar vídeo", 10, project_id=None,
                                           model="veo_lite", quote_only=True, client=client)
                self.assertEqual((job["status"], job["project_id"], job["model"]), ("quoted", latest, "veo-lite"))
                self.assertEqual(seen, [latest])
                client.rpc.assert_awaited_once_with("UpteDb")
                client.prepare.assert_not_awaited()
                client.send_submit.assert_not_awaited()
            finally:
                get_settings.cache_clear()

    async def test_completed_generation_records_observed_credit_charge(self):
        from gflow_cli.config import get_settings

        project, source, workflow, output = (str(uuid4()) for _ in range(4))
        row = video_row(project, source, workflow)
        data = [None, [], [row], None, None, None, None, None]
        body = b"1234ftypmp42original!"
        nzlxg_data = [90, None, None, 2, None, None, None]

        async def rpc_handler(rpc_id, **kwargs):
            if rpc_id == "Zzl0ze":
                return data
            if rpc_id == "nzlxg":
                return nzlxg_data
            return None

        async def quote(client, job, features):
            job["quoted_credits"] = 10
            job["credits_before"] = 100
            return {"model_key": "abra_edit", "quoted_credits": 10}

        async def send(packet):
            result = video_row(project, output, workflow, revision="CAI")
            result[5][13] = len(body)
            return result

        client = SimpleNamespace(
            account_id="conta-a",
            rpc=AsyncMock(side_effect=rpc_handler),
            prepare=AsyncMock(return_value="captcha"),
            status_from_submit=lambda *args: None,
            download=AsyncMock(return_value=body),
            close=AsyncMock(),
            request=lambda rpc, params: {"rpc_id": rpc, "params": params},
            send_submit=AsyncMock(side_effect=send),
        )

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home, "FLOW_MCP_OUTPUT": home}), \
             patch("flow_video.generation_quote", side_effect=quote), \
             patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", workflow)]):
            get_settings.cache_clear()
            try:
                job = await generate_video(
                    "conta-a", "Mudar iluminação", 20,
                    project_id=project, model="omni-flash", operation="edit",
                    source_media_id=source, segment_start=1, segment_end=5, client=client,
                )
                self.assertEqual(job["status"], "completed")
                self.assertEqual(job["credits_before"], 100)
                self.assertEqual(job["credits_after"], 90)
                self.assertEqual(job["credits_charged_observed"], 10)
                client.send_submit.assert_awaited_once()
            finally:
                get_settings.cache_clear()

    async def test_polling_tolerates_brief_tracking_lag_after_acceptance(self):
        from gflow_cli.config import get_settings

        project, source, workflow, output = (str(uuid4()) for _ in range(4))
        data = [None, [], [video_row(project, source, workflow)], None, None, None, None, None]
        body = b"1234ftypmp42original!"
        done = video_row(project, output, workflow, revision="CAI")
        done[5][13] = len(body)
        tracking = iter([[], [], done])  # acompanhamento vazio duas vezes, depois pronto

        async def rpc_handler(rpc_id, **kwargs):
            if rpc_id == "as29s":
                return next(tracking)
            return data if rpc_id == "Zzl0ze" else [90, None, None, 2, None, None, None]

        async def quote(client, job, features):
            job.update(quoted_credits=10, credits_before=100)
            return {"model_key": "abra_edit", "quoted_credits": 10}

        accepted = video_row(project, output, workflow, revision="CAI", status=2)  # em andamento
        client = SimpleNamespace(account_id="conta-a", rpc=AsyncMock(side_effect=rpc_handler),
                                 prepare=AsyncMock(return_value="captcha"), status_from_submit=lambda *a: None,
                                 download=AsyncMock(return_value=body), close=AsyncMock(),
                                 request=lambda rpc, params: {"rpc_id": rpc, "params": params},
                                 send_submit=AsyncMock(return_value=accepted))
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home, "FLOW_MCP_OUTPUT": home}), \
             patch("flow_video.generation_quote", side_effect=quote), patch("flow_video.asyncio.sleep", AsyncMock()), \
             patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", workflow)]):
            get_settings.cache_clear()
            try:
                job = await generate_video("conta-a", "Mudar luz", 20, project_id=project, model="omni-flash",
                                           operation="edit", source_media_id=source, segment_start=1,
                                           segment_end=5, client=client)
            finally:
                get_settings.cache_clear()
        self.assertEqual(job["status"], "completed")
        client.send_submit.assert_awaited_once()
        # Mídia que nunca aparece: para após ~6 consultas com orientação clara, sem reenviar.
        tracking = iter([[]] * 10)
        client.send_submit.reset_mock()
        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home, "FLOW_MCP_OUTPUT": home}), \
             patch("flow_video.generation_quote", side_effect=quote), patch("flow_video.asyncio.sleep", AsyncMock()), \
             patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", workflow)]):
            get_settings.cache_clear()
            try:
                lost = await generate_video("conta-a", "Mudar luz", 20, project_id=project, model="omni-flash",
                                            operation="edit", source_media_id=source, segment_start=1,
                                            segment_end=5, client=client)
            finally:
                get_settings.cache_clear()
        self.assertEqual(lost["status"], "generation_unknown")
        self.assertIn("perdido", lost["error"])
        client.send_submit.assert_awaited_once()

    async def test_completed_generation_keeps_completed_status_when_nzlxg_fails(self):
        from gflow_cli.config import get_settings

        project, source, workflow, output = (str(uuid4()) for _ in range(4))
        row = video_row(project, source, workflow)
        data = [None, [], [row], None, None, None, None, None]
        body = b"1234ftypmp42original!"

        async def rpc_handler(rpc_id, **kwargs):
            if rpc_id == "Zzl0ze":
                return data
            if rpc_id == "nzlxg":
                raise RuntimeError("Falha de leitura nzlxg")
            return None

        async def quote(client, job, features):
            job["quoted_credits"] = 10
            job["credits_before"] = 100
            return {"model_key": "abra_edit", "quoted_credits": 10}

        async def send(packet):
            result = video_row(project, output, workflow, revision="CAI")
            result[5][13] = len(body)
            return result

        client = SimpleNamespace(
            account_id="conta-a",
            rpc=AsyncMock(side_effect=rpc_handler),
            prepare=AsyncMock(return_value="captcha"),
            status_from_submit=lambda *args: None,
            download=AsyncMock(return_value=body),
            close=AsyncMock(),
            request=lambda rpc, params: {"rpc_id": rpc, "params": params},
            send_submit=AsyncMock(side_effect=send),
        )

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"GFLOW_CLI_HOME": home, "FLOW_MCP_OUTPUT": home}), \
             patch("flow_video.generation_quote", side_effect=quote), \
             patch("flow_requests._seed", side_effect=[("media-seed", output), ("workflow-seed", workflow)]):
            get_settings.cache_clear()
            try:
                job = await generate_video(
                    "conta-a", "Mudar iluminação", 20,
                    project_id=project, model="omni-flash", operation="edit",
                    source_media_id=source, segment_start=1, segment_end=5, client=client,
                )
                self.assertEqual(job["status"], "completed")
                self.assertEqual(job["credits_before"], 100)
                self.assertIsNone(job["credits_after"])
                self.assertIsNone(job.get("credits_charged_observed"))
                client.send_submit.assert_awaited_once()
            finally:
                get_settings.cache_clear()


if __name__ == '__main__': unittest.main()
