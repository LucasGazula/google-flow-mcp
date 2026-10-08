"""Edição e histórico de imagens no editor atual do Flow."""

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from flow_errors import error_fields
from flow_assets import media_uuid, parse_assets
from flow_projects import validate_project
from flow_video import (IMAGE_MODELS, downloads_dir, generation_quote, image_suffix, normalize_model,
                        original_image_url, save_job)


def image_versions(payload, media_id, project_id):
    from gflow_cli.api.transports.batchexecute import image_records
    from gflow_cli.errors import WireFormatError
    from types import SimpleNamespace

    asset = next((a for a in parse_assets(payload, validate_project(project_id))
                  if a["media_id"] == media_uuid(media_id)), None)
    if asset is None or asset["kind"] != "image":
        raise ValueError("Imagem ausente da resposta do projeto.")
    try:
        records = image_records("Zzl0ze", payload)
    except WireFormatError:
        records = []
    if not any(r.media_id == media_id for r in records):
        # Uploads/recortes não têm metadados de geração; a pilha vem do workflow.
        return [SimpleNamespace(**a) for a in parse_assets(payload, project_id)
                if a["workflow_id"] == asset["workflow_id"] and a["kind"] == "image"]
    return [r for r in records if r.workflow_id == asset["workflow_id"]]


def asset_details(payload, account_id, project_id, media_id):
    from gflow_cli.errors import WireFormatError
    validate_project(project_id)
    media_uuid(media_id)
    asset = next((a for a in parse_assets(payload, project_id) if a["media_id"] == media_id), None)
    if asset is None:
        raise ValueError("Mídia ausente da resposta inicial.")
    versions = []
    if asset["kind"] == "image":
        try:
            versions = [{"media_id":r.media_id, "workflow_id":r.workflow_id,
                         "dimensions":list(r.dimensions) if r.dimensions is not None else None,
                         "prompt":getattr(r, "prompt", None)}
                        for r in image_versions(payload, media_id, project_id)]
        except (ValueError, WireFormatError):
            pass  # Uploads não possuem os detalhes de geração do decoder.
    elif asset["kind"] == "video":
        versions = [a for a in parse_assets(payload,project_id)
                    if a["kind"] == "video" and a["workflow_id"] == asset["workflow_id"]]
    return {"account_id":account_id, "project_id":project_id, "status":"ok", "asset":asset,
            "versions":versions, "complete":False, "source":"HTTP/Zzl0ze",
            "observed_at":datetime.now(timezone.utc).isoformat()}


async def get_asset(account_id, project_id, media_id):
    from flow_http import FlowHTTP, http_operation

    client = FlowHTTP(account_id)
    try:
        return await http_operation(client, "get_asset", {"project_id":project_id,"media_id":media_id})
    finally:
        await client.close()


def _new_image_edit_records(rpc, payload, *, project_id, workflow_id, previous_ids, workflows):
    from gflow_cli.api.transports.batchexecute import image_records

    records = image_records(rpc, [payload, workflows])
    return [r for r in records if r.project_id == project_id and r.workflow_id == workflow_id
            and r.media_id not in previous_ids]


def image_edit_record(rpc, payload, *, project_id, workflow_id, previous_ids, workflows):
    """Relacionar a nova versão à pilha de origem, mesmo com prompt traduzido."""
    new = _new_image_edit_records(rpc, payload, project_id=project_id,
        workflow_id=workflow_id, previous_ids=previous_ids, workflows=workflows)
    if len(new) != 1:
        raise ValueError("Nova versão da imagem não confirmada.")
    return new[0]


def image_edit_records(rpc, payload, *, project_id, workflow_id, previous_ids, workflows,
                       expected_ids):
    if not expected_ids or len(set(expected_ids)) != len(expected_ids):
        raise ValueError("IDs de resultado da edição inválidos.")
    new = _new_image_edit_records(rpc, payload, project_id=project_id,
        workflow_id=workflow_id, previous_ids=previous_ids, workflows=workflows)
    by_id = {r.media_id:r for r in new}
    if (not new or len(by_id) != len(new)
            or any(media_id not in expected_ids for media_id in by_id)):
        raise ValueError("Novas versões da imagem não confirmadas.")
    return [by_id[media_id] for media_id in expected_ids if media_id in by_id]


async def edit_image(account_id: str, project_id: str, media_id: str, prompt: str,
                     max_credits: int, model: str = "nano-banana-2", aspect: str = "1:1",
                     count: int = 1, *, reference_images=None, selection=None,
                     drawings=None, reference_asset_ids=None, client=None) -> dict:
    from flow_accounts import validate_account
    from gflow_cli.api.image import Model, Aspect
    from flow_requests import image_request
    from flow_http import FlowHTTP, prepare_generation
    from flow_annotations import validate_annotations, upload_annotated_image
    from flow_assets import image_download_url
    from flow_video import prepare_reference_uploads
    from gflow_cli.api.client import validate_image_file

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>4000:
        raise ValueError("Informe um prompt de até 4000 caracteres.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Informe um orçamento inteiro não negativo.")
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("A quantidade deve estar entre 1 e 4.")
    model = normalize_model(model, IMAGE_MODELS)
    Model.from_cli("nano-banana-2" if model == "nano-banana-2-lite" else model)
    Aspect.from_cli(aspect)
    validate_annotations(selection, drawings)
    if reference_images is not None and (type(reference_images) is not list
            or len(reference_images) > 10 or any(not isinstance(p, str) for p in reference_images)):
        raise ValueError("Informe até dez caminhos de imagem de referência.")
    if reference_asset_ids is not None and (type(reference_asset_ids) is not list
            or len(reference_asset_ids) > 10
            or any(not isinstance(value, str) for value in reference_asset_ids)
            or len(set(reference_asset_ids)) != len(reference_asset_ids)):
        raise ValueError("Informe até dez IDs de referência distintos do projeto.")
    for reference_id in reference_asset_ids or []:
        media_uuid(reference_id)
    if len(reference_images or []) + len(reference_asset_ids or []) > 10:
        raise ValueError("Use até dez referências de imagem.")
    refs = [Path(p).resolve(strict=True) for p in (reference_images or [])]
    for path in refs:
        await validate_image_file(path)
    job = {"job_id":str(uuid4()), "account_id":account_id, "kind":"image_edit", "status":"preparing",
           "project_id":project_id, "source_media_id":media_id, "prompt":prompt, "model":model,
           "aspect":aspect, "count":count, "max_credits":max_credits, "quoted_credits":None,
           "files":[], "media_ids":[]}
    if selection is not None or drawings is not None:
        job.update(selection=selection, drawings=drawings)
    save_job(job)
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        payload = await client.rpc("Zzl0ze", project_id=project_id)
        versions = image_versions(payload, media_id, project_id)
        if not versions:
            raise ValueError("Detalhes de geração da imagem ausentes.")
        project_references = []
        if reference_asset_ids:
            assets = {a["media_id"]: a for a in parse_assets(payload, project_id)}
            for reference_id in reference_asset_ids:
                asset = assets.get(reference_id)
                if asset is None or asset["kind"] != "image":
                    raise ValueError("Imagem de referência ausente deste projeto/conta.")
                project_references.append({"media_id": reference_id,
                                           "name": asset.get("name") or reference_id})
            job["reference_asset_ids"] = reference_asset_ids
        previous_ids = {r.media_id for r in versions}
        workflow_id = versions[0].workflow_id
        job.update(workflow_id=workflow_id, previous_media_ids=sorted(previous_ids))
        await generation_quote(client, job, [1, 4])
        base_id = media_id
        if selection is not None or drawings is not None:
            body = await client.download(original_image_url(
                image_download_url(payload, project_id, media_id)), media_id)
            annotated = await upload_annotated_image(client, project_id, body, selection, drawings)
            job["annotation_upload"] = annotated
            save_job(job)
            if annotated.get("status") != "uploaded":
                raise ValueError("Upload da anotação inconclusivo; edição não enviada.")
            base_id = annotated["media_id"]
        uploaded = await prepare_reference_uploads(job, refs, client=client)
        captcha = await prepare_generation(client, project_id, "IMAGE_GENERATION")
        quote = await generation_quote(client, job, [1, 4])
        packet = image_request(project_id, prompt, quote["model_key"], aspect, count, captcha,
                               source_media_id=base_id, workflow_id=workflow_id,
                               references=[r["media_id"] for r in project_references + uploaded],
                               reference_names={r["media_id"]:r["name"]
                                                for r in project_references + uploaded})
        captured = client.request(packet["rpc_id"], packet["params"])
        job.update(request_media_ids=packet["request_media_ids"],
                   request_workflow_ids=packet["request_workflow_ids"],
                   status="submitting", source="HTTP/ogiZ0b")
        save_job(job)
        result = await client.send_submit(captured)
        records = image_edit_records(packet["rpc_id"], result, project_id=project_id,
            workflow_id=workflow_id, previous_ids=previous_ids, workflows=payload[1],
            expected_ids=packet["request_media_ids"])
        job.update(status="downloading", media_id=records[0].media_id,
                   workflow_id=workflow_id, media_ids=[r.media_id for r in records],
                   workflow_ids=[r.workflow_id for r in records], rpc=packet["rpc_id"])
        save_job(job)
        output = downloads_dir()
        for record in records:
            body = await client.download(original_image_url(record.image_url), record.media_id)
            path = output/(record.media_id+image_suffix(body))
            path.write_bytes(body)
            job["files"].append(str(path))
            job["bytes"] = job.get("bytes", 0) + len(body)
            save_job(job)
        job["status"] = "completed" if len(records) == count else "partial_result"
    except Exception as exc:
        job.update(error_fields(exc))
        job.update(failure_stage=job["status"],
            status={"preparing":"failed_pre_submit","submitting":"submission_unknown",
                    "downloading":"download_failed"}.get(job["status"],job["status"]))
    finally:
        if owned:
            await client.close()
        save_job(job)
    return job


async def edit_images(account_id: str, project_id: str, media_ids: list[str], prompt: str,
                      max_credits: int, model: str = "nano-banana-2", aspect: str = "1:1",
                      *, reference_asset_ids=None, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_capabilities import read_capabilities, quote_configuration
    from flow_http import FlowHTTP
    from gflow_cli.api.image import Model, Aspect

    validate_account(account_id)
    validate_project(project_id)
    if (type(media_ids) is not list or not 2 <= len(media_ids) <= 10
            or any(not isinstance(value, str) for value in media_ids)
            or len(set(media_ids)) != len(media_ids)):
        raise ValueError("Informe de 2 a 10 mídias distintas.")
    for media_id in media_ids:
        media_uuid(media_id)
    if reference_asset_ids is not None and (type(reference_asset_ids) is not list
            or len(reference_asset_ids) > 10
            or any(not isinstance(value, str) for value in reference_asset_ids)
            or len(set(reference_asset_ids)) != len(reference_asset_ids)):
        raise ValueError("Informe até dez IDs de referência distintos do projeto.")
    for reference_id in reference_asset_ids or []:
        media_uuid(reference_id)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Informe um prompt de até 4000 caracteres.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Informe um orçamento inteiro não negativo.")
    model = normalize_model(model, IMAGE_MODELS)
    Model.from_cli("nano-banana-2" if model == "nano-banana-2-lite" else model)
    Aspect.from_cli(aspect)
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")

    job = {"job_id":str(uuid4()), "account_id":account_id, "kind":"image_edit_batch",
           "status":"preparing", "project_id":project_id, "source_media_ids":media_ids,
           "prompt":prompt, "model":model, "aspect":aspect, "count":len(media_ids),
           "max_credits":max_credits, "quoted_credits":None, "reserved_credits":0,
           "media_ids":[], "workflow_ids":[], "request_media_ids":[],
           "request_workflow_ids":[], "files":[], "subjobs":[],
           "reference_asset_ids":reference_asset_ids or []}
    save_job(job)
    owned = client is None
    client = client or FlowHTTP(account_id)
    remaining = max_credits
    try:
        payload = await client.rpc("Zzl0ze", project_id=project_id)
        if reference_asset_ids:
            assets = {a["media_id"]:a for a in parse_assets(payload, project_id)}
            if any((assets.get(value) or {}).get("kind") != "image"
                   for value in reference_asset_ids):
                raise ValueError("Imagem de referência ausente deste projeto/conta.")
        workflows = []
        for media_id in media_ids:
            versions = image_versions(payload, media_id, project_id)
            if not versions:
                raise ValueError("Detalhes de geração de uma imagem ausentes.")
            workflows.append(versions[0].workflow_id)
        capabilities = await read_capabilities(account_id, project_id, client=client)
        quote = quote_configuration(capabilities, model, aspect=aspect, count=1,
            max_credits=max_credits, features=[1, 4])
        quote["quoted_credits"] *= len(media_ids)
        if quote["quoted_credits"] > max_credits:
            raise ValueError("Custo total do lote acima do orçamento autorizado.")
        job.update(source_workflow_ids=workflows, quote=quote,
                   quoted_credits=quote["quoted_credits"], status="submitting")
        save_job(job)

        # ponytail: serialize edits per account; parallelize only after Flow limits are measured.
        for media_id in media_ids:
            job["current_source_media_id"] = media_id
            save_job(job)
            child = await edit_image(account_id, project_id, media_id, prompt, remaining,
                model=model, aspect=aspect, reference_asset_ids=reference_asset_ids,
                client=client)
            summary = {key:child.get(key) for key in (
                "job_id", "status", "media_id", "media_ids", "request_media_ids",
                "files", "quoted_credits", "error_type", "error")}
            summary["source_media_id"] = media_id
            job["subjobs"].append(summary)
            job["request_media_ids"].extend(child.get("request_media_ids", []))
            job["request_workflow_ids"].extend(child.get("request_workflow_ids", []))
            for value in child.get("media_ids", []):
                if value not in job["media_ids"]:
                    job["media_ids"].append(value)
            job["workflow_ids"].extend(child.get("workflow_ids", []))
            job["files"].extend(child.get("files", []))
            job["bytes"] = job.get("bytes", 0) + child.get("bytes", 0)
            if child.get("media_ids") and not job.get("media_id"):
                job["media_id"] = child["media_ids"][0]
            child_quote = child.get("quoted_credits")
            if child.get("status") != "failed_pre_submit" and type(child_quote) is int:
                job["reserved_credits"] += child_quote
                remaining = max(0, remaining - child_quote)
            job["remaining_budget"] = remaining
            job["current_subjob_id"] = child["job_id"]
            save_job(job)
            if child.get("status") != "completed":
                status = child.get("status") or "partial_result"
                # Imagens anteriores do lote já foram enviadas: o lote não é "nada enviado".
                if status == "failed_pre_submit" and len(job["subjobs"]) > 1:
                    status = "partial_result"
                job.update(status=status, failure_stage=child.get("status"),
                           **({"error": child["error"]} if child.get("error") else {}))
                break
        else:
            job["status"] = "completed"
    except Exception as exc:
        job.update(error_fields(exc))
        job.update(failure_stage=job["status"],
                   status="failed_pre_submit" if job["status"] in {"preparing", "submitting"}
                   and not job["subjobs"] else "partial_result")
    finally:
        if owned:
            await client.close()
        job["remaining_budget"] = remaining
        save_job(job)
    return job


async def crop_image(account_id, project_id, media_id, coordinates, *, client):
    """TransformImage mantém o workflow e retorna a nova versão sem geração."""
    from flow_accounts import validate_account
    from flow_assets import image_download_url
    from flow_requests import _seed
    from gflow_cli.api.transports.batchexecute import _walk_lists

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if (not isinstance(coordinates,list) or len(coordinates)!=4
            or any(type(v) not in {int,float} or not 0 <= v <= 1 for v in coordinates)
            or not coordinates[0] < coordinates[2] or not coordinates[1] < coordinates[3]):
        raise ValueError("Informe [topo, esquerda, base, direita] entre 0 e 1, com área positiva.")
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    data = await client.rpc("Zzl0ze",project_id=project_id)
    source = next((a for a in parse_assets(data,project_id)
                   if a['media_id']==media_id and a['kind']=='image'),None)
    if source is None:
        raise ValueError("Imagem de origem ausente deste projeto.")
    seed, new_id = _seed()
    job = {'job_id':str(uuid4()),'account_id':account_id,'project_id':project_id,
           'kind':'image_crop','source_media_id':media_id,'coordinates':coordinates,
           'status':'preparing','quoted_credits':0,'files':[],'media_ids':[],
           'request_media_ids':[new_id],'request_workflow_ids':[source['workflow_id']]}
    save_job(job)
    try:
        packet = client.request('sAVZzc',[1,media_id,None,coordinates,None,None,seed])
        job['status']='submitting';save_job(job)
        result = await client.send_submit(packet)
        rows = [r for r in _walk_lists(result) if len(r)>=7 and r[0]==new_id
                and r[1]==project_id and r[2]==source['workflow_id']]
        if len(rows)!=1:
            raise ValueError("Nova versão recortada não confirmada.")
        job.update(status='downloading',media_ids=[new_id],workflow_ids=[source['workflow_id']])
        save_job(job)
        readback = await client.rpc("Zzl0ze",project_id=project_id)
        output_asset = next((asset for asset in parse_assets(readback,project_id)
            if asset['media_id']==new_id and asset['workflow_id']==source['workflow_id']
            and asset['kind']=='image'),None)
        download_payload = readback if output_asset else rows[0]
        body = await client.download(original_image_url(image_download_url(
            download_payload,project_id,new_id)),new_id)
        output=downloads_dir()
        target=output/(new_id+image_suffix(body));target.write_bytes(body)
        job.update(status='completed',files=[str(target)],bytes=len(body))
    except Exception as exc:
        job.update(error_fields(exc))
        job.update(failure_stage=job['status'],
            status={'preparing':'failed_pre_submit','submitting':'submission_unknown',
                    'downloading':'download_failed'}.get(job['status'],job['status']))
    save_job(job)
    return job


def _validate_image_upscale_capture(params, media_id, project_id):
    """SPrCad 2K: origem, resolução e contexto conferidos antes do único POST."""
    if (not isinstance(params, list) or len(params) != 3 or params[0] != media_id
            or type(params[1]) is not int or params[1] != 1
            or not isinstance(params[2], list) or len(params[2]) != 11
            or params[2][5] != project_id or params[2][4] is not None
            or not isinstance(params[2][10], list) or len(params[2][10]) != 2
            or not isinstance(params[2][10][0], str) or not params[2][10][0]
            or params[2][10][1] != 1):
        raise ValueError("Origem, projeto ou resolução do upscale não confirmados; envio bloqueado.")


def _image_upscale_quote(capabilities, target_resolution):
    family = [m for m in capabilities["modes"]["image"]["models"]
              if m["model_id"] == "upsample_" + target_resolution]
    feature = 5 if target_resolution == "2k" else 6
    variants = [v for m in family for v in m["variants"]
                if v["available"] and [feature] in v["input_feature_codes"]]
    if len(family) != 1 or len(variants) != 1 or variants[0]["credits_per_output"] != 0:
        raise ValueError("Upscale indisponível ou sem custo zero confirmado no catálogo desta conta.")
    if target_resolution != "2k":
        raise ValueError("O pedido nativo 4K ainda não foi confirmado; envio bloqueado.")
    return {"model_key":variants[0]["model_key"], "quoted_credits":0,
            "source":"HTTP/HTrJv", "observed_at":capabilities["observed_at"]}


async def upscale_image_native(account_id, project_id, media_id,
                               target_resolution="2k", upload_to_flow=False, *, client):
    """Upscale nativo 2K pela RPC migrada; nunca repetir envio incerto."""
    import base64
    import re
    from uuid import NAMESPACE_URL, uuid5
    from flow_accounts import validate_account
    from flow_capabilities import read_capabilities
    from flow_video import get_job, job_path
    from gflow_cli.api.client import MAX_UPSAMPLE_B64_LEN, _is_png_or_jpeg

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    if type(upload_to_flow) is not bool:
        raise ValueError("upload_to_flow deve ser booleano.")
    if not isinstance(target_resolution, str) or target_resolution.strip().lower() not in {"2k", "4k"}:
        raise ValueError("Resolução deve ser '2k' ou '4k'.")
    target_resolution = target_resolution.strip().lower()
    job_id = str(uuid5(NAMESPACE_URL, f"flow-image-upscale-{target_resolution}:{account_id}:{project_id}:{media_id}"))
    job = get_job(account_id, job_id) if job_path(job_id).exists() else None
    if job and job["status"] != "failed_pre_submit":
        if job["status"] != "completed":
            return {**job, "retry_automatically":False}
        target = Path(job["output_path"])
        if not target.is_file() or target.stat().st_size != job.get("bytes"):
            return {**job, "status":"output_missing", "retry_automatically":False}
    else:
        job = {"job_id":job_id, "account_id":account_id, "project_id":project_id,
               "source_media_id":media_id, "target_resolution":target_resolution,
               "kind":"image_upscale_native", "status":"preparing", "files":[],
               "quoted_credits":0, "credit_cost":0, "source":"HTTP/SPrCad"}
        save_job(job)
        try:
            job["preparation_stage"] = "source_lookup"
            payload = await client.rpc("Zzl0ze", project_id=project_id)
            source = next((asset for asset in parse_assets(payload, project_id)
                           if asset["media_id"] == media_id and asset["kind"] == "image"), None)
            if source is None:
                raise ValueError("Imagem de origem ausente deste projeto.")
            job["preparation_stage"] = "catalog"
            job["quote"] = _image_upscale_quote(await read_capabilities(account_id, project_id, client=client), target_resolution)
            job["preparation_stage"] = "capture"
            async with client.browser.page() as page:
                await page.goto(f"https://flow.google.com/project/{project_id}/edit/{source['workflow_id']}",
                                wait_until="domcontentloaded", timeout=45000)
                await page.get_by_role("button", name=re.compile("Baixar mídia|Download media", re.I)).click(timeout=20000)
                submit = page.get_by_role("menuitem", name=re.compile(r"^2K.*(?:Aprimorada|Enhanced)", re.I))
                captured = await client.capture_submit(page, submit, {"SPrCad"})
                job["preparation_stage"] = "capture_validation"
                if captured.get("rpc_id") != "SPrCad":
                    raise ValueError("RPC de upscale não reconhecida; envio bloqueado.")
                _validate_image_upscale_capture(captured.get("params"), media_id, project_id)
            job["preparation_stage"] = "catalog_recheck"
            job["quote"] = _image_upscale_quote(await read_capabilities(account_id, project_id, client=client), target_resolution)
            job["status"] = "submitting"
            save_job(job)
            result = await client.send_submit(captured)
            if (not isinstance(result, list) or len(result) != 2
                    or not isinstance(result[0], list) or len(result[0]) < 3
                    or result[0][1] != project_id or not isinstance(result[1], str)
                    or not 0 < len(result[1]) <= MAX_UPSAMPLE_B64_LEN):
                raise ValueError("Resposta do upscale não reconhecida.")
            job["response_media_id"] = media_uuid(result[0][0])
            job["response_workflow_id"] = media_uuid(result[0][2])
            image = base64.b64decode(result[1], validate=True)
            del result
            if not _is_png_or_jpeg(image):
                raise ValueError("Resposta do upscale não contém PNG/JPEG.")
            job["status"] = "saving"
            save_job(job)
            output = downloads_dir()
            target = output / f"upscale_{media_id}_{target_resolution}{image_suffix(image)}"
            target.write_bytes(image)
            job.update(status="completed", output_path=str(target), files=[str(target)], bytes=len(image))
        except Exception as exc:
            job.update(status={"preparing":"failed_pre_submit", "submitting":"submission_unknown",
                               "saving":"output_save_failed"}.get(job["status"], job["status"]),
                       retry_automatically=False, **error_fields(exc))
            save_job(job)
            return job
        save_job(job)
    if upload_to_flow and not job.get("flow_upload_status"):
        from flow_assets import upload_image

        job["flow_upload_status"] = "submitting"
        save_job(job)
        try:
            uploaded = await upload_image(account_id, project_id, job["output_path"], client=client)
        except Exception as exc:
            job.update(flow_upload_status="failed", **error_fields(exc, "flow_upload_"))
        else:
            job["flow_upload_status"] = uploaded.get("status") or "submission_unknown"
            if uploaded.get("media_id"):
                job["asset_media_id"] = uploaded["media_id"]
        save_job(job)
    return job
