"""Vídeos e imagens por HTTP, com orçamento e tarefas persistidas."""

from datetime import datetime, timezone
import asyncio
import json
import math
import os
from pathlib import Path
import re
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5
from types import SimpleNamespace
from urllib.parse import urlencode, urljoin, urlsplit, urlunsplit

from gflow_cli.api.transports.migrated_composer import MigratedComposer
from flow_browser import account_page
from flow_errors import error_fields
from flow_projects import validate_project


def parse_generation_cost(text: str) -> int:
    matches = re.findall(r"(?:A geração vai usar|Generation will use)\s+([0-9]+)\s+(?:créditos|credits)\b", text, re.I)
    if len(matches) != 1:
        raise ValueError("Custo da geração não identificado.")
    return int(matches[0])


class BudgetedComposer(MigratedComposer):
    """A release fixada oferece o custo no painel após configurar a quantidade."""

    def __init__(self, max_credits: int, uploaded_images=None):
        super().__init__()  # Sem screenshots/DOM de depuração em disco.
        self.max_credits = max_credits
        self.quoted_credits = None
        self.uploaded_images = list(uploaded_images or [])

    async def _upload_via_toolbar(self, page, project_id, image_path):
        # Os uploads HTTP terminam antes de abrir o compositor que vincula os chips.
        for index, uploaded in enumerate(self.uploaded_images):
            if uploaded["path"] == str(image_path) and uploaded["project_id"] == project_id:
                self.uploaded_images.pop(index)
                return uploaded["media_id"], uploaded["name"]
        raise ValueError("Referência sem upload HTTP confirmado; geração bloqueada.")

    async def _select(self, page, pane, *, axis, lig=None, text=None):
        await super()._select(page, pane, axis=axis, lig=lig, text=text)
        if axis == "count":
            self.quoted_credits = parse_generation_cost(await pane.inner_text())
            if self.quoted_credits > self.max_credits:
                raise ValueError("Custo acima do orçamento autorizado.")


def job_path(job_id: str) -> Path:
    from gflow_cli.config import get_settings

    try:
        valid = str(UUID(job_id)) == job_id
    except (ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise ValueError(f"job_id inválido ({str(job_id)[:80]!r}); use um job_id de flow_list_jobs.")
    return get_settings().home / "jobs" / f"{job_id}.json"


VIDEO_MODELS = ("veo-lite", "veo-fast", "veo-quality", "omni-flash")
IMAGE_MODELS = ("nano-banana-2", "nano-banana-2-lite", "nano-pro")
_MODEL_ALIASES = {"nano-banana-pro": "nano-pro", "omni": "omni-flash"}


# Nome do modelo no pedido em texto ao Agent (contas só de Agent).
AGENT_MODEL_NAMES = {"omni-flash": "Omni Flash", "veo-lite": "Veo 3.1 Lite", "veo-fast": "Veo 3.1 Fast",
                     "veo-quality": "Veo 3.1 Quality"}


def normalize_model(model, allowed) -> str:
    """Aceitar variações comuns (omni_flash, Nano Banana Pro) e listar as opções no erro."""
    value = "-".join(model.strip().lower().replace("_", " ").split()) if isinstance(model, str) else model
    value = _MODEL_ALIASES.get(value, value)
    if value not in allowed:
        raise ValueError(f"Modelo inválido ({model!r}); use {', '.join(allowed)}.")
    return value


def downloads_dir() -> Path:
    """Pasta dos arquivos baixados, na máquina do MCP (FLOW_MCP_OUTPUT ou ./downloads)."""
    output = Path(os.environ.get("FLOW_MCP_OUTPUT", Path(__file__).parent / "downloads")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    return output


def save_job(job: dict) -> None:
    if job.get("quote_only"):
        return  # Cotação não cria tarefa.
    target = job_path(job["job_id"])
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    job["observed_at"] = datetime.now(timezone.utc).isoformat()
    temp = target.with_suffix(".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(job, stream, ensure_ascii=False)
    os.replace(temp, target)


def _validate_upscale_capture(params, media_id, workflow_id, project_id, target_resolution):
    try:
        row = params[0][0]
        actual_media, actual_workflow, actual_project = row[0][1], row[4][1], params[1][5]
        actual_resolution = row[2], row[6]
    except (IndexError, KeyError, TypeError):
        raise ValueError("Pedido de aprimoramento não reconhecido; envio bloqueado.") from None
    if (actual_media != media_id or actual_workflow != workflow_id or actual_project != project_id
            or target_resolution == "1080p" and actual_resolution != (2, 2)):
        raise ValueError("Origem, projeto ou resolução do aprimoramento não confirmados; envio bloqueado.")


async def upscale_video(account_id: str, project_id: str, media_id: str,
                        target_resolution: str = "720p", *, client=None) -> dict:
    """Aprimora vídeos para 720p ou 1080p pelos controles nativos observados no Flow."""
    from flow_accounts import validate_account
    from flow_assets import media_uuid, parse_assets
    from flow_http import FlowHTTP, http_operation

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if target_resolution not in {"720p", "1080p"} or media_id.endswith("_upsampled"):
        raise ValueError("Use 720p ou 1080p e informe uma origem compatível.")
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    expected_id = f"{media_id}_720p_upsampled" if target_resolution == "720p" else f"{media_id}_upsampled"
    job_id = str(uuid5(NAMESPACE_URL, f"flow-upscale-{target_resolution}:{account_id}:{project_id}:{media_id}"))
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    try:
        assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        source = next((item for item in assets if item["media_id"] == media_id), None)
        if source is None or source["kind"] != "video":
            raise ValueError("Vídeo de origem ausente da primeira resposta do projeto.")
        job = get_job(account_id, job_id) if job_path(job_id).exists() else None
        result = {"account_id": account_id, "project_id": project_id,
                  "source_media_id": media_id, "media_id": expected_id,
                  "job_id": job_id, "credit_cost": 0}
        if any(item["media_id"] == expected_id for item in assets):
            try:
                downloaded = await http_operation(client, "download_asset",
                                                  {"project_id": project_id, "media_id": expected_id})
                if job:
                    job.update(status="completed", path=downloaded["path"], bytes=downloaded["bytes"])
                    save_job(job)
                return {**result, **downloaded}
            except Exception as exc:
                return {**result, "status": "accepted", **error_fields(exc),
                        "message": "Vídeo aprimorado visto; download ainda indisponível."}
        if job:
            return {**result, "status": job["status"],
                    "message": "Envio anterior registrado; consulte novamente para recuperar, sem reenviar."}
        if client.browser is None:
            raise ValueError("Aprimoramento requer o worker autenticado residente.")
        async with client.browser.page() as page:
            await page.goto(f"https://flow.google.com/project/{project_id}/edit/{source['workflow_id']}",
                            wait_until="domcontentloaded", timeout=45000)
            await page.get_by_role("button", name=re.compile("Baixar mídia|Download media", re.I)).click(timeout=15000)
            submit = page.get_by_role("menuitem", name=re.compile(
                rf"{re.escape(target_resolution)}.*(Aprimorada|Enhanced)", re.I))
            captured = await client.capture_submit(page, submit, {"p0UkFb"})
            _validate_upscale_capture(captured.get("params"), media_id, source["workflow_id"],
                                      project_id, target_resolution)
        job = {**result, "kind": "video_upscale", "status": "submitting",
               "source": "HTTP/p0UkFb", "target_resolution": target_resolution}
        save_job(job)
        try:
            await client.send_submit(captured)
        except Exception as exc:
            job.update(status="submission_unknown", **error_fields(exc))
            save_job(job)
            return {**result, "status": "submission_unknown", **error_fields(exc),
                    "message": "Envio inconclusivo; consulte novamente para reconciliar, sem reenviar."}
        job["status"] = "accepted"
        save_job(job)
        return {**result, "status": "accepted",
                "message": "Envio aceito; consulte novamente para baixar o resultado."}
    finally:
        if owned:
            await client.close()


def get_job(account_id: str, job_id: str) -> dict:
    job = json.loads(job_path(job_id).read_text(encoding="utf-8"))
    if job["account_id"] != account_id:
        raise ValueError("A tarefa pertence a outra conta.")
    if job.get("kind") == "video" and job.get("video_id_schema") is None:
        # Migração das tarefas antigas, preservando caminhos e evidência original.
        job["legacy_video_ids"] = {key:job[key] for key in (
            "media_id", "workflow_id", "media_ids", "workflow_ids",
            "request_media_ids", "request_workflow_ids") if key in job}
        for media_key, workflow_key in (("media_id","workflow_id"),("media_ids","workflow_ids"),
                                        ("request_media_ids","request_workflow_ids")):
            if media_key in job and workflow_key in job:
                job[media_key], job[workflow_key] = job[workflow_key], job[media_key]
        job["video_id_schema"] = "media-workflow-v1"
        save_job(job)
    return job


# Estados em que a tarefa ainda pode ter resultado a reconciliar (nunca reenviar).
PENDING_STATUSES = {"preparing", "submitting", "accepted", "downloading", "submission_unknown",
                    "generation_unknown", "partial_result", "download_failed"}


def list_jobs(account_id: str, limit: int = 100, status: str | None = None) -> dict:
    from flow_accounts import validate_account

    validate_account(account_id)
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("Informe um limite de 1 a 500 tarefas.")
    if status is not None and not isinstance(status, str):
        raise ValueError("status deve ser texto (ex.: pending, completed, submission_unknown).")
    jobs = []
    for path in job_path(str(uuid4())).parent.glob("*.json"):
        try:
            job = get_job(account_id, path.stem)
        except (ValueError, OSError, KeyError):
            continue
        if status == "pending" and job.get("status") not in PENDING_STATUSES or (
                status not in (None, "pending") and job.get("status") != status):
            continue
        jobs.append({key: job.get(key) for key in (
            "job_id", "status", "kind", "model", "project_id", "media_id", "media_ids",
            "quoted_credits", "files", "observed_at", "error")})
    jobs.sort(key=lambda job: job.get("observed_at") or "", reverse=True)
    return {"account_id": account_id, "jobs": jobs[:limit], "total": len(jobs),
            "has_more": len(jobs) > limit, "source": "local_saved_jobs"}


async def prepare_reference_uploads(job, paths, *, client=None):
    from flow_assets import upload_image

    uploaded = []
    for path in paths:
        result = await upload_image(job["account_id"], job["project_id"], str(path), client=client)
        job.setdefault("reference_uploads", []).append({"path": str(path), **result})
        save_job(job)
        if result["status"] != "uploaded":
            reason = result.get("error") or result.get("message")
            raise ValueError(f"Upload da referência {Path(path).name} inconclusivo; geração não enviada"
                             + (f" ({reason})" if reason else "") + ". Confira o projeto antes de reenviar a imagem.")
        uploaded.append({"path": str(path), **result})
    return uploaded


async def record_charge(client, job):
    """Saldo após a conclusão; débito observado, não confirmado pelo Flow."""
    from flow_credits import parse_http_credits

    try:
        # ponytail: leitura única; o débito pode aparecer com atraso no saldo.
        job["credits_after"] = parse_http_credits(await client.rpc("nzlxg"))
        job["credits_charged_observed"] = job["credits_before"] - job["credits_after"]
    except Exception:
        job["credits_after"] = None


async def generation_quote(client, job, features):
    from flow_capabilities import read_capabilities, quote_configuration

    capabilities = await read_capabilities(job["account_id"], job["project_id"], client=client)
    quote = quote_configuration(capabilities, job["model"], aspect=job["aspect"], count=job.get("count", 1),
        max_credits=job["max_credits"], features=features,
        duration_seconds=job.get("duration_seconds"), resolution=job.get("resolution", "720p"))
    job.update(quote=quote, quoted_credits=quote["quoted_credits"], credits_before=capabilities["credits"])
    save_job(job)
    return quote


async def generate_video(account_id: str, prompt: str, max_credits: int,
                         project_id: str | None = None, model: str = "veo-lite",
                         aspect: str = "16:9", duration_seconds: int = 8,
                         start_image: str | None = None, end_image: str | None = None,
                         reference_images: list[str] | None = None, count: int = 1,
                         resolution: str = "720p", *, client=None,
                         operation="generate", source_media_id=None,
                         segment_start=0, segment_end=None, reference_asset_ids=None,
                         start_image_asset_id=None, end_image_asset_id=None,
                         create_new_workflow: bool = False, voice: str | None = None,
                         character_ids: list[str] | None = None, quote_only: bool = False) -> dict:
    from flow_accounts import validate_account
    from flow_projects import project_operation
    from gflow_cli.api.video import GenerateVideoRequest, Mode, Aspect, VideoModel
    from gflow_cli.api.client import validate_image_file
    from flow_http import FlowHTTP
    from gflow_cli.api.transports.batchexecute import _walk_lists
    from flow_assets import MediaAbsent, media_uuid, parse_assets, payload_shape, video_record
    from gflow_cli.api.transports.migrated_recover import _verify
    from flow_requests import video_request
    from flow_http import AgentOnlyComposer, prepare_generation
    from flow_agent import agent_generate, mention

    validate_account(account_id)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Informe um prompt de até 4000 caracteres.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Informe um orçamento inteiro não negativo.")
    if project_id is not None:
        validate_project(project_id)
    model = normalize_model(model, VIDEO_MODELS)
    if aspect not in {"16:9", "9:16"}:
        raise ValueError(f"Proporção de vídeo inválida ({aspect!r}); use 16:9 ou 9:16.")
    if type(duration_seconds) is not int:
        raise ValueError("duration_seconds deve ser um inteiro (ex.: 4, 6, 8 ou 10).")
    if resolution not in {"360p", "720p", "1080p", "4k"}:
        raise ValueError(f"Resolução inválida ({resolution!r}); use 360p, 720p, 1080p ou 4k.")
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("Informe de 1 a 4 saídas.")
    if operation not in {"generate", "edit", "extend"}:
        raise ValueError("Operação de vídeo inválida: use generate, edit ou extend.")
    if type(create_new_workflow) is not bool or create_new_workflow and operation != "edit":
        raise ValueError("Novo histórico está disponível apenas na edição de vídeo.")
    if reference_asset_ids is not None:
        if (type(reference_asset_ids) is not list or len(reference_asset_ids) > 10
                or any(not isinstance(v, str) for v in reference_asset_ids)
                or len(set(reference_asset_ids)) != len(reference_asset_ids)):
            raise ValueError("Informe até dez referências distintas do projeto.")
        for value in reference_asset_ids:
            media_uuid(value)
        validate_project(project_id)
    frame_asset_ids = [value for value in (start_image_asset_id, end_image_asset_id)
                       if value is not None]
    for value in frame_asset_ids:
        media_uuid(value)
    if frame_asset_ids:
        validate_project(project_id)
    if (start_image and start_image_asset_id) or (end_image and end_image_asset_id):
        raise ValueError("Use um caminho local ou ID do projeto para cada quadro, não ambos.")
    if operation != "generate":
        validate_project(project_id)
        media_uuid(source_media_id)
        if count != 1 or start_image or end_image or start_image_asset_id or end_image_asset_id:
            raise ValueError("Edição/extensão aceita um vídeo, sem quadros inicial/final.")
        if operation == "edit" and model != "omni-flash":
            raise ValueError("Edição exige Omni Flash.")
        if operation == "extend" and not model.startswith("veo-"):
            raise ValueError("Extensão exige Veo.")
        if (type(segment_start) not in {int, float} or not 0 <= segment_start < 60
                or segment_end is not None and (type(segment_end) not in {int, float}
                    or not segment_start < segment_end <= 60)):
            raise ValueError("Trecho de vídeo inválido.")
    start = Path(start_image).resolve(strict=True) if start_image else None
    end = Path(end_image).resolve(strict=True) if end_image else None
    refs = tuple(Path(p).resolve(strict=True) for p in (reference_images or []))
    if character_ids is not None:
        if (type(character_ids) is not list or not 1 <= len(character_ids) <= 3
                or len(set(character_ids)) != len(character_ids)):
            raise ValueError("Informe de 1 a 3 personagens distintos do projeto.")
        for value in character_ids:
            media_uuid(value)
        validate_project(project_id)
        if operation != "generate" or model != "omni-flash":
            raise ValueError("Personagens exigem geração Omni Flash.")
    has_refs = bool(refs or reference_asset_ids or character_ids)
    has_start_frame = bool(start or start_image_asset_id)
    has_end_frame = bool(end or end_image_asset_id)
    if has_end_frame and not has_start_frame or has_refs and (has_start_frame or has_end_frame):
        raise ValueError("Use quadros inicial/final ou referências, sem misturar os modos.")
    if voice is not None:
        from gflow_cli.api.character import VOICE_NAMES

        voice = next((name for name in VOICE_NAMES if isinstance(voice, str)
                      and name.casefold() == voice.casefold()), None)
        if voice is None:
            raise ValueError("Voz desconhecida; consulte flow_list_voice_presets.")
        # A interface só envia a voz em geração Omni Flash com ingredientes de imagem.
        if operation != "generate" or model != "omni-flash" or not has_refs:
            raise ValueError("Voz exige geração Omni Flash com referências de imagem ou personagens.")
    mode = Mode.I2V if has_start_frame else Mode.R2V if has_refs else Mode.T2V
    if operation == "generate":
        # This local DTO validates R2V mode/caps; the HTTP builder binds the UUIDs below.
        GenerateVideoRequest(prompt=prompt, mode=mode,
            aspect=Aspect.from_cli(aspect), model=VideoModel.from_cli(model), count=count,
            duration=duration_seconds if model == "omni-flash" or duration_seconds != 8 else None,
            start_image=start, end_image=end,
            start_image_ref_id=start_image_asset_id, end_image_ref_id=end_image_asset_id,
            reference_images=refs,
            ref_names=tuple(reference_asset_ids or ()) + tuple(character_ids or ()))
    if len(refs) + len(reference_asset_ids or []) > 10:
        raise ValueError("Use até dez referências de imagem.")
    for path in (*refs, *(p for p in (start, end) if p is not None)):
        await validate_image_file(path)
    job = {"job_id": str(uuid4()), "account_id": account_id, "kind": "video", "status": "preparing",
           "video_id_schema": "media-workflow-v1",
           "prompt": prompt, "max_credits": max_credits, "model": model, "mode": mode.value,
           "duration_seconds": duration_seconds, "resolution": resolution, "aspect": aspect, "count": count,
           "project_id": project_id, "start_image_asset_id": start_image_asset_id,
           "end_image_asset_id": end_image_asset_id, "voice": voice, "character_ids": character_ids,
           "quoted_credits": None, "files": [], "media_ids": [], "workflow_ids": []}
    if quote_only:
        job["quote_only"] = True
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    save_job(job)
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        if project_id is None and quote_only:
            # O catálogo é lido no contexto de um projeto; cotar não cria projeto.
            from flow_projects import parse_projects
            projects = parse_projects(await client.rpc("UpteDb"))["projects"]
            if not projects:
                raise ValueError("Cotação exige ao menos um projeto na conta.")
            project_id = projects[0]["project_id"]
        if project_id is None:
            created = await project_operation(account_id, "Google Flow MCP", client=client)
            job["project_id"] = created["project_id"]
            job["project_creation_status"] = created["status"]
            if created["status"] != "ok":
                raise ValueError("Criação de projeto inconclusiva; geração não enviada.")
            project_id = created["project_id"]
        job["project_id"] = project_id
        features = [1, 5, 7] if has_end_frame else [1, 5] if has_start_frame else [1, 6] if has_refs else [1]
        existing_refs, agent_characters = [], []
        if character_ids:
            from flow_character import parse_characters

            listed = {c["entity_id"]: c for c in parse_characters(
                await client.rpc("Zzl0ze", project_id=project_id), project_id)}
            agent_characters = [listed[c] for c in character_ids if c in listed]
            known = set(listed)
            if not set(character_ids) <= known:
                raise ValueError("Personagem ausente deste projeto/conta.")
        if reference_asset_ids or frame_asset_ids:
            assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
            for reference_id in reference_asset_ids or ():
                matched = next((a for a in assets if a["media_id"] == reference_id), None)
                if matched and matched["kind"] == "video":
                    raise ValueError("O Flow não aceita vídeo como referência; use flow_edit_video com create_new_workflow=True.")
                if matched is None or matched["kind"] != "image":
                    raise ValueError("Referência de imagem ausente deste projeto/conta.")
                existing_refs.append({"media_id": reference_id, "name": matched.get("name") or reference_id})
            if reference_asset_ids:
                job["reference_asset_ids"] = reference_asset_ids
            for frame_id in frame_asset_ids:
                frame = next((a for a in assets if a["media_id"] == frame_id and a["kind"] == "image"), None)
                if frame is None:
                    raise ValueError("Quadro de imagem ausente deste projeto/conta.")
        workflow_id, first_frame, last_frame = None, None, None
        if operation != "generate":
            payload = await client.rpc("Zzl0ze", project_id=project_id)
            asset = next((a for a in parse_assets(payload, project_id)
                          if a["media_id"] == source_media_id and a["kind"] == "video"), None)
            if asset is None:
                raise ValueError("Vídeo de origem ausente deste projeto/conta.")
            row = next(r for r in payload[2] if r[0] == source_media_id)
            source_info = row[7][0] if isinstance(row[7][0], list) else []
            source_model = source_info[12] if len(source_info) > 12 else None
            source_duration = row[7][1][2][0]
            if type(source_duration) not in {int, float} or source_duration <= 0:
                raise ValueError("Duração do vídeo de origem desconhecida.")
            if operation == "extend" and (not isinstance(source_model, str) or not source_model.startswith("veo_")):
                raise ValueError("Somente vídeos Veo podem ser estendidos.")
            source_aspect = {1:"9:16", 2:"16:9"}.get(source_info[16] if len(source_info) > 16 else None)
            if source_aspect is None and source_model is None:
                width, height = row[7][1][:2]
                if type(width) is not int or type(height) is not int or min(width, height) <= 0:
                    raise ValueError("Dimensões do vídeo enviado desconhecidas.")
                ratio = width / height
                source_aspect = "16:9" if abs(ratio - 16/9) < .02 else "9:16" if abs(ratio - 9/16) < .02 else None
            if source_aspect != aspect:
                raise ValueError("Proporção deve corresponder ao vídeo de origem.")
            if segment_start >= source_duration:
                raise ValueError("Trecho começa após o fim do vídeo.")
            stop = source_duration if segment_end is None else segment_end
            if stop > source_duration or operation == "edit" and stop - segment_start > 10:
                raise ValueError("Trecho fora do vídeo ou maior que dez segundos.")
            # O frontend usa 30 fps para uploads e 24 fps para vídeos gerados.
            if source_model is not None and (not isinstance(source_model, str)
                                             or not source_model.startswith(("veo_", "abra_", "omni_"))):
                raise ValueError("Taxa de quadros da origem ainda não reconhecida.")
            source_fps = 30 if source_model is None else 24
            first_frame, last_frame = math.floor(segment_start * source_fps + .5), math.floor(stop * source_fps + .5)
            if first_frame >= last_frame:
                raise ValueError("Trecho menor que um quadro de vídeo.")
            workflow_id = asset["workflow_id"]
            features = [1, 6, 18, 19, 20] if operation == "edit" else [1, 14]
            if operation == "extend" and has_refs:
                features += [6, 18, 19]
            job.update(kind="video_"+operation, mode=operation, source_media_id=source_media_id,
                       workflow_id=workflow_id, segment_start=segment_start, segment_end=stop,
                       source_fps=source_fps, source_workflow_id=workflow_id,
                       create_new_workflow=create_new_workflow)
        await generation_quote(client, job, features)
        if quote_only:
            job["status"] = "quoted"
            return job
        try:
            agent_only = False
            uploaded = await prepare_reference_uploads(job, (*[p for p in (start, end) if p is not None], *refs), client=client)
            captcha = await prepare_generation(client, project_id, "VIDEO_GENERATION")
        except AgentOnlyComposer:
            agent_only = True
        if agent_only:
            # Conta só de Agent: o Agent gera no servidor; o MCP confere o custo antes de aprovar.
            if operation != "generate" or start or end or refs or start_image_asset_id or end_image_asset_id:
                raise AgentOnlyComposer("Conta só de Agent: o MCP gera nela apenas vídeo novo com personagens e "
                                        "imagens do projeto como referência (sem quadros inicial/final nem "
                                        "arquivos locais). Nada foi enviado.")
            quote = await generation_quote(client, job, features)
            parts = [[f"Gere {count} vídeo{'s' if count > 1 else ''} com o modelo {AGENT_MODEL_NAMES[model]}, "
                      f"{duration_seconds} segundos, {resolution}, proporção {aspect}"]]
            mentions = [mention(c["entity_id"], c["display_name"], character=True) for c in agent_characters] + \
                       [mention(a["media_id"], a["name"] or "imagem", character=False) for a in existing_refs]
            if mentions:
                parts.append([", usando como referência "])
                for k, item in enumerate(mentions):
                    parts += ([[", "]] if k else []) + [item]
            if voice:
                parts.append([f", com a voz {voice}"])
            parts.append([f". Use exatamente este comando, sem reescrever, resumir nem traduzir: \"{prompt}\". "
                          "Peça minha aprovação antes de gerar."])
            found = await agent_generate(client, job, parts, kind="video", count=count,
                                         expected_credits=job["quoted_credits"], save_job=save_job)
            job.update(request_media_ids=[a["media_id"] for a in found],
                       request_workflow_ids=[a["workflow_id"] for a in found])
            template = client.templates["Zzl0ze"]
            captured = {"url": template["url"], "body": urlencode(template["form"], doseq=True),
                        "headers": template["headers"]}
            # Estado inicial "em andamento"; o acompanhamento as29s abaixo lê o estado real.
            records = {a["media_id"]: SimpleNamespace(media_id=a["media_id"], workflow_id=a["workflow_id"],
                                                      is_failed=False, is_done=False, video_url=None)
                       for a in found}
            job.update(media_ids=list(records), workflow_ids=[r.workflow_id for r in records.values()],
                       media_id=found[0]["media_id"], workflow_id=found[0]["workflow_id"])
            save_job(job)
            client.status_from_submit(captured, job["media_id"])
        else:
            quote = await generation_quote(client, job, features)
            start_id = start_image_asset_id or (uploaded[0]["media_id"] if start else None)
            end_upload_index = int(start is not None)
            end_id = end_image_asset_id or (uploaded[end_upload_index]["media_id"] if end else None)
            all_refs = [*existing_refs, *uploaded]
            reference_ids = [u["media_id"] for u in all_refs] if has_refs else []
            packet = video_request(project_id, prompt, quote["model_key"], aspect, count, captcha,
                                   start_id=start_id, end_id=end_id, references=reference_ids,
                                   reference_names={u["media_id"]:u["name"] for u in all_refs},
                                   operation=operation, source_id=source_media_id, workflow_id=workflow_id,
                                   start_frame=first_frame, end_frame=last_frame, voice=voice,
                                   characters=character_ids or (),
                                   create_new_workflow=create_new_workflow)
            rpc = packet["rpc_id"]
            captured = client.request(rpc, packet["params"])
            job.update(request_media_ids=packet["request_media_ids"], request_workflow_ids=packet["request_workflow_ids"])
            job.update(status="submitting", source=f"HTTP/{rpc}")
            save_job(job)  # O navegador não gerou; somente este POST pode cobrar.
            payload = await client.send_submit(captured)
            records = {}
            for row in _walk_lists(payload):
                # Versão (campo 3) vem nula em mídias novas desde 05/10/2026.
                if (len(row) < 6 or not all(isinstance(row[i], str) for i in range(3))
                        or not (row[3] is None or isinstance(row[3], str))):
                    continue
                record = video_record(rpc, row)
                expected = dict(zip(job["request_media_ids"], job["request_workflow_ids"]))
                if (record.project_id != project_id or expected.get(record.media_id) != record.workflow_id
                        or record.media_id in records):
                    raise ValueError("Resposta da geração pertence a outro pedido/projeto.")
                records[record.media_id] = record
            if not records:
                raise ValueError("Identificadores da geração não confirmados.")
            job.update(status="accepted", media_ids=list(records), workflow_ids=[r.workflow_id for r in records.values()],
                       media_id=next(iter(records)), workflow_id=next(iter(records.values())).workflow_id)
            save_job(job)
            client.status_from_submit(captured, job["media_id"])
        misses = {}
        try:
            async with asyncio.timeout(600):
                while True:
                    for media_id, previous in list(records.items()):
                        if previous.is_failed or (previous.is_done and previous.video_url):
                            continue
                        payload = None
                        try:
                            payload = await client.rpc("as29s", project_id=project_id,
                                media_id=media_id, workflow_id=previous.workflow_id)
                            record = video_record("as29s", payload, media_id)
                            if record.workflow_id != previous.workflow_id or record.project_id != project_id:
                                raise ValueError("Resposta de acompanhamento pertence a outra geração.")
                        except MediaAbsent:
                            # O acompanhamento pode atrasar logo após o POST; ~30 s sem a mídia = provável perda.
                            misses[media_id] = misses.get(media_id, 0) + 1
                            if misses[media_id] < 6:
                                continue
                            job["as29s_shape"] = payload_shape(payload)
                            raise ValueError("A mídia aceita não aparece no acompanhamento do Flow após ~30 s; a "
                                             "geração pode ter se perdido no Flow. Use flow_wait_job/flow_recover_job "
                                             "(não reenvie).") from None
                        except ValueError:
                            job["as29s_shape"] = payload_shape(payload)  # Sem IDs, textos ou URLs.
                            raise
                        misses.pop(media_id, None)
                        records[media_id] = record
                    if all(r.is_failed or (r.is_done and r.video_url) for r in records.values()):
                        break
                    await asyncio.sleep(5)
        except TimeoutError:
            raise ValueError("Vídeo ainda em processamento após 10 minutos; a geração continua no Flow. "
                             "Use flow_wait_job com o job_id (sem reenviar).") from None
        job["status"] = "downloading"
        save_job(job)
        output = downloads_dir()
        for record in records.values():
            if not record.is_done:
                continue
            body = await client.download(record.video_url, record.media_id)
            _verify(body, expected=record.size_bytes, media_id=record.media_id)
            path = output / f"{record.media_id}.mp4"
            path.write_bytes(body)
            job["files"].append(str(path))
            save_job(job)
        job["status"] = "completed" if len(job["files"]) == count else "partial_result" if job["files"] else "generation_failed"
        await record_charge(client, job)
    except Exception as exc:
        job.update(error_fields(exc))
        job["failure_stage"] = job["status"]
        job["status"] = {"preparing": "failed_pre_submit", "submitting": "submission_unknown",
                         "accepted": "generation_unknown", "downloading": "download_failed"}.get(job["status"], job["status"])
        # error_fields omite mensagens/URLs do backend; geração incerta não é reenviada.
    finally:
        if owned:
            await client.close()
        save_job(job)
    return job


async def refine_video(account_id: str, project_id: str, media_id: str,
                       refinements: list[str], max_credits: int, aspect: str = "16:9",
                       reference_images: list[str] | None = None,
                       reference_asset_ids: list[str] | None = None,
                       duration_seconds: int = 8, resolution: str = "720p", *,
                       client=None) -> dict:
    from flow_accounts import validate_account
    from flow_assets import media_uuid
    from flow_http import FlowHTTP
    from flow_projects import validate_project
    from gflow_cli.api.client import validate_image_file

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if (type(refinements) is not list or not 1 <= len(refinements) <= 3
            or any(not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000
                   for prompt in refinements)):
        raise ValueError("Informe de um a três prompts de refinamento, com até 4000 caracteres cada.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Informe um orçamento inteiro não negativo para a cadeia toda.")
    if aspect not in {"16:9", "9:16"} or type(duration_seconds) is not int or duration_seconds <= 0:
        raise ValueError("Proporção ou duração inválida.")
    if resolution not in {"360p", "720p", "1080p", "4k"}:
        raise ValueError("Resolução de vídeo inválida.")
    if reference_asset_ids is not None and (type(reference_asset_ids) is not list
            or len(reference_asset_ids) > 10
            or any(not isinstance(value, str) for value in reference_asset_ids)
            or len(set(reference_asset_ids)) != len(reference_asset_ids)):
        raise ValueError("Informe até dez referências distintas do projeto.")
    reference_ids = list(reference_asset_ids or [])
    for reference_id in reference_ids:
        media_uuid(reference_id)
    if reference_images is not None and (type(reference_images) is not list
            or any(not isinstance(value, str) for value in reference_images)):
        raise ValueError("Referências locais devem ser uma lista de caminhos de imagem.")
    paths = [Path(value).resolve(strict=True) for value in (reference_images or [])]
    if any(not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}
           for path in paths):
        raise ValueError("Referências devem ser arquivos de imagem locais.")
    if len(paths) + len(reference_ids) > 10:
        raise ValueError("Use até dez referências de imagem.")
    for path in paths:
        await validate_image_file(path)
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")

    owned = client is None
    client = client or FlowHTTP(account_id)
    source_id = media_id
    remaining, quoted, outputs, turns = max_credits, 0, [], []
    workflow_id = None
    status = "completed"
    try:
        for index, prompt in enumerate(refinements):
            try:
                child = await generate_video(account_id, prompt, remaining,
                    project_id=project_id, model="omni-flash", aspect=aspect,
                    duration_seconds=duration_seconds,
                    reference_images=[str(path) for path in paths] if index == 0 else None,
                    reference_asset_ids=reference_ids, resolution=resolution, client=client,
                    operation="edit", source_media_id=source_id)
            except Exception as exc:
                turns.append({"turn":index + 1, "status":"failed_pre_submit", **error_fields(exc)})
                status = "failed_pre_submit"
                break
            child_status = child.get("status") or "partial_result"
            child_quote = child.get("quoted_credits")
            if child_status not in {"failed_pre_submit", "reference_confirmation_required", "reference_upload_unknown"} and type(child_quote) is int:
                quoted += child_quote
                remaining = max(0, remaining - child_quote)
            turns.append({key:child.get(key) for key in
                ("job_id", "status", "media_id", "quoted_credits", "files", "error_type", "error",
                 "confirmation_id", "reference_upload_status")}
                | {"turn":index + 1})
            if child_status != "completed":
                status = child_status
                break
            try:
                source_id = media_uuid(child.get("media_id"))
            except (TypeError, ValueError):
                status = "partial_result"
                turns[-1]["status"] = status
                break
            outputs.append(source_id)
            workflow_id = child.get("workflow_id") or workflow_id
            if index == 0 and paths:
                uploaded = [item.get("media_id") for item in child.get("reference_uploads", [])
                            if isinstance(item, dict) and item.get("status") == "uploaded"
                            and isinstance(item.get("media_id"), str)]
                if len(uploaded) != len(paths):
                    status = "partial_result"
                    turns[-1]["reference_reconciliation"] = "incomplete"
                    break
                reference_ids = list(dict.fromkeys([*reference_ids,
                    *(media_uuid(value) for value in uploaded)]))
    finally:
        if owned:
            await client.close()
    if status == "completed" and len(outputs) != len(refinements):
        status = "partial_result" if outputs else "failed_pre_submit"
    elif status not in {"completed", "submission_unknown", "generation_unknown", "download_failed"} and outputs:
        status = "partial_result"
    return {"status":status, "source_media_id":media_id,
            "media_id":outputs[-1] if outputs else None, "media_ids":outputs,
            "workflow_id":workflow_id, "turns":turns,
            "job_ids":[item["job_id"] for item in turns if item.get("job_id")],
            "refinements_completed":len(outputs), "requested_refinements":len(refinements),
            "quoted_credits":quoted, "remaining_budget":remaining,
            **({"error": turns[-1]["error"]} if status != "completed" and turns and turns[-1].get("error") else {})}


async def recover_job(account_id: str, job_id: str, *, client=None) -> dict:
    """Confirmar IDs esperados no projeto e recuperar mídia sem reenviar geração."""

    job = get_job(account_id, job_id)
    if job.get("status") == "cancelled":
        return job
    if job.get("status") == "failed_pre_submit" or not (
            job.get("request_media_ids") or job.get("media_ids") or job.get("media_id")):
        # Nada chegou ao Flow (ou a tarefa não guarda IDs): não há o que reconciliar.
        return {**job, "recovery_status": "nothing_to_recover",
                "message": "Tarefa sem envio ou sem IDs de mídia registrados; nada a recuperar."}
    validate_project(job.get("project_id"))
    from flow_assets import media_uuid

    request_ids = job.get("request_media_ids") or []
    request_workflows = job.get("request_workflow_ids") or []
    if (type(request_ids) is not list or type(request_workflows) is not list
            or bool(request_ids) != bool(request_workflows)
            or len(request_ids) != len(request_workflows)):
        raise ValueError("IDs esperados da tarefa não correspondem.")
    pairs = list(zip(job.get("media_ids") or [], job.get("workflow_ids") or []))
    if job.get("media_id") and job.get("workflow_id"):
        pairs.append((job["media_id"], job["workflow_id"]))
    confirmed = {}
    for media_id, workflow_id in pairs:
        media_uuid(media_id)
        media_uuid(workflow_id)
        confirmed[media_id] = workflow_id
    expected = dict(zip(request_ids, request_workflows))
    for media_id, workflow_id in expected.items():
        media_uuid(media_id)
        media_uuid(workflow_id)
    # Estado anterior preservado se o Flow ainda não disponibilizar o arquivo.
    try:
        from urllib.parse import urlencode
        from flow_http import FlowHTTP, http_operation
        from flow_assets import parse_assets, video_record

        if client is not None and client.account_id != account_id:
            raise ValueError("Sessão HTTP pertence a outra conta.")
        owned = client is None
        client = client or FlowHTTP(account_id)
        downloads, pending, failed, direct_ids, unseen = [], [], [], set(), []
        try:
            assets = []
            if expected:
                assets = parse_assets(await client.rpc("Zzl0ze", project_id=job["project_id"]),
                                      job["project_id"])
            assets_by_id = {asset["media_id"]: asset for asset in assets}
            job_kind = str(job.get("kind", ""))
            kind = "video" if job_kind.startswith("video") else "image" if job_kind.startswith("image") else None
            for media_id, workflow_id in expected.items():
                asset = assets_by_id.get(media_id)
                if (kind and asset and asset["workflow_id"] == workflow_id
                        and asset["kind"] == kind):
                    confirmed[media_id] = workflow_id
                    continue
                if kind == "video":
                    templates = getattr(client, "templates", {})
                    if "as29s" not in templates and "Zzl0ze" in templates:
                        template = templates["Zzl0ze"]
                        client.status_from_submit({"url":template["url"],
                            "body":urlencode(template["form"],doseq=True),
                            "headers":template["headers"]}, media_id)
                    try:
                        record = video_record("as29s", await client.rpc("as29s", project_id=job["project_id"],
                                                                          media_id=media_id, workflow_id=workflow_id), media_id)
                    except (ValueError, TypeError, IndexError):
                        unseen.append(media_id)
                        continue
                    if (record.media_id != media_id or record.workflow_id != workflow_id
                            or record.project_id != job["project_id"]):
                        unseen.append(media_id)
                        continue
                    confirmed[media_id] = workflow_id
                    if record.is_failed:
                        failed.append(media_id)
                    elif record.is_done and record.video_url:
                        from gflow_cli.api.transports.migrated_recover import _verify

                        body = await client.download(record.video_url, media_id)
                        _verify(body, expected=record.size_bytes, media_id=media_id)
                        output = downloads_dir()
                        path = output / f"{media_id}.mp4"
                        path.write_bytes(body)
                        downloads.append({"path":str(path),"bytes":len(body)})
                        direct_ids.add(media_id)
                    else:
                        pending.append(media_id)
                else:
                    unseen.append(media_id)  # Imagem fora da listagem do projeto.
            values = [media_id for media_id in expected if media_id in confirmed and media_id not in failed]
            if expected and pending:
                job.update(media_ids=[media_id for media_id in expected if media_id in confirmed],
                           workflow_ids=[confirmed[media_id] for media_id in expected if media_id in confirmed],
                           status="generation_unknown", recovery_status="pending")
                job["files"] = list(dict.fromkeys([*(job.get("files") or []),
                                                     *(d["path"] for d in downloads)]))
                job["bytes"] = sum(Path(path).stat().st_size for path in job["files"] if Path(path).is_file())
                if failed:
                    job["failed_media_ids"] = failed
                save_job(job)
                return job
            if expected and not values and failed:
                job.update(status="generation_failed", recovery_status="generation_failed",
                           failed_media_ids=failed)
                save_job(job)
                return job
            if expected and not values:
                job["recovery_status"] = "not_listed"
                job.pop("recovery_error_type", None)
                job.pop("recovery_error", None)
                save_job(job)
                return job
            if expected and set(values) <= set(unseen):
                # O POST devolveu os IDs, mas o Flow não mostra a mídia nem no projeto nem no acompanhamento.
                job.update(recovery_status="not_found", recovery_message=(
                    "O envio foi aceito, mas a mídia não aparece no projeto nem no acompanhamento do Flow. "
                    "Logo após o envio isso pode ser atraso; se persistir, a geração se perdeu no Flow: "
                    "confira o saldo (flow_get_credits) antes de decidir, com o usuário, gerar de novo."))
                job.pop("recovery_error_type", None)
                job.pop("recovery_error", None)
                save_job(job)
                return job
            if not expected:
                values = list(dict.fromkeys([*confirmed, *(job.get("media_ids") or []),
                                             *([job["media_id"]] if job.get("media_id") else [])]))
                for value in values:
                    media_uuid(value)
            if not values:
                job["recovery_status"] = "not_listed"
                save_job(job)
                return job
            if expected:
                job.update(media_ids=values, workflow_ids=[confirmed[value] for value in values],
                           media_id=values[0], workflow_id=confirmed[values[0]], status="accepted")
                save_job(job)
            for value in values:
                if value in direct_ids:
                    continue
                downloads.append(await http_operation(client,"download_asset",
                    {"project_id":job["project_id"],"media_id":value}))
        finally:
            if owned:
                await client.close()
        files = list(dict.fromkeys([*(job.get("files") or []), *(d["path"] for d in downloads)]))
        sizes = {d["path"]:d.get("bytes", 0) for d in downloads}
        job.update(status="completed" if len(values) == job.get("count",1) and not failed
                           else "partial_result" if files else "generation_failed",
                   files=files, bytes=sum(Path(path).stat().st_size if Path(path).is_file()
                                          else sizes.get(path, 0) for path in files),
                   recovery_status="recovered")
        if expected:
            job.update(media_ids=values, workflow_ids=[confirmed[value] for value in values])
            job.update(media_id=values[0], workflow_id=confirmed.get(values[0]))
        if failed:
            job["failed_media_ids"] = failed
        if job["status"] == "completed" and "error" in job:
            job["previous_error"] = job.pop("error")  # Falha original, já superada pela recuperação.
            job.pop("error_location", None)
        job.pop("recovery_error_type", None)
        job.pop("recovery_error", None)
    except Exception as exc:
        job["recovery_status"] = "unavailable"
        job.pop("recovery_error", None)
        job.update(error_fields(exc, "recovery_"))
    save_job(job)
    return job


async def download_bytes(page, url: str, media_id: str) -> bytes:
    """Validar cada salto, sem repassar credenciais a um host externo."""
    from gflow_cli.api.transports._common import get_signed_media
    from gflow_cli.api.transports.ui_automation import _is_allowed_download_host

    for _ in range(4):
        parts = urlsplit(url)
        if (not _is_allowed_download_host(url) or parts.username or parts.password
                or parts.port not in {None, 443}):
            raise ValueError("Host de download não autorizado.")
        response = await get_signed_media(page, url, media_id=media_id,
            route="media_download", max_redirects=0, remediation="Repita apenas o download.")
        if response.status in {301, 302, 303, 307, 308}:
            location = response.headers.get("location")
            if not location:
                raise ValueError("Redirecionamento sem destino.")
            url = urljoin(url, location)
            continue
        if response.status != 200:
            raise ValueError("Download indisponível.")
        return await response.body()
    raise ValueError("Limite de redirecionamentos excedido.")


async def recover_clip(page, *, project_id: str, media_id: str, out_dir: Path):
    from gflow_cli.api.transports.migrated_recover import _verify, RecoveredClip
    from gflow_cli.api.transports.batchexecute import parse_frames, generation_record

    found = asyncio.get_running_loop().create_future()

    async def observe(response):
        if found.done() or "batchexecute" not in response.url:
            return
        try:
            for rpc, payload in parse_frames(await response.text()):
                # A listagem Zzl0ze contém thumbnail no mesmo campo; as29s é
                # a consulta de status do clipe que fornece o vídeo original.
                if rpc != "as29s":
                    continue
                record = generation_record(rpc, payload)
                if record.media_id == media_id and record.is_done and record.video_url and not found.done():
                    found.set_result(record)
        except Exception:
            pass

    page.on("response", observe)
    try:
        await page.goto(f"https://flow.google.com/project/{project_id}/edit/{media_id}",
                        wait_until="domcontentloaded", timeout=90000)
        record = await asyncio.wait_for(found, 60)
    finally:
        page.remove_listener("response", observe)
    body = await download_bytes(page, record.video_url, media_id)
    _verify(body, expected=record.size_bytes, media_id=media_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{media_id}.mp4"
    path.write_bytes(body)
    return RecoveredClip(media_id=media_id, workflow_id=record.workflow_id, path=path, bytes=len(body))


async def generate_images(account_id: str, prompt: str, max_credits: int,
                          project_id: str | None = None, model: str = "nano-banana-2",
                          aspect: str = "16:9", count: int = 1,
                          reference_images: list[str] | None = None,
                          reference_asset_ids: list[str] | None = None, *,
                          character_entity_id: str | None = None, character_slot: int = 0,
                          client=None) -> dict:
    from flow_accounts import validate_account
    from gflow_cli.api.image import GenerateImageRequest, ImageRef, Model, Aspect
    from flow_projects import project_operation
    from flow_http import FlowHTTP, prepare_generation
    from flow_assets import media_uuid, parse_assets
    from gflow_cli.api.transports.batchexecute import image_records
    from flow_requests import image_request

    validate_account(account_id)
    if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 4000:
        raise ValueError("Informe um prompt de até 4000 caracteres.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Informe um orçamento inteiro não negativo.")
    if project_id is not None:
        validate_project(project_id)
    model = normalize_model(model, IMAGE_MODELS)
    if type(count) is not int:
        raise ValueError("Quantidade inválida.")
    if reference_asset_ids is not None and (type(reference_asset_ids) is not list
            or any(not isinstance(value, str) for value in reference_asset_ids)
            or len(set(reference_asset_ids)) != len(reference_asset_ids)):
        raise ValueError("Informe IDs de referência distintos do projeto.")
    for reference_id in reference_asset_ids or []:
        media_uuid(reference_id)
    if reference_asset_ids and project_id is None:
        raise ValueError("Informe project_id para reutilizar referências do projeto.")
    if character_entity_id is not None and (project_id is None or count != 1):
        raise ValueError("Retrato de personagem exige project_id e uma única imagem.")
    refs = tuple(Path(p).resolve(strict=True) for p in (reference_images or []))
    if any(not p.is_file() or p.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"} for p in refs):
        raise ValueError("Referências devem ser arquivos de imagem locais.")
    GenerateImageRequest(prompt=prompt,
        model=Model.from_cli("nano-banana-2" if model == "nano-banana-2-lite" else model),
        aspect=Aspect.from_cli(aspect), count=count,
        refs=tuple(ImageRef(name=value) for value in (reference_asset_ids or [])), ref_paths=refs)
    job = {"job_id": str(uuid4()), "account_id": account_id, "kind": "image",
           "status": "preparing", "prompt": prompt, "max_credits": max_credits,
           "model": model, "aspect": aspect, "count": count, "project_id": project_id,
           "quoted_credits": None, "media_ids": [], "files": [],
           "reference_asset_ids": reference_asset_ids or []}
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    save_job(job)
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        if project_id is None:
            created = await project_operation(account_id, "Google Flow MCP", client=client)
            job["project_id"] = created["project_id"]
            job["project_creation_status"] = created["status"]
            if created["status"] != "ok":
                raise ValueError("Criação de projeto inconclusiva; geração não enviada.")
            project_id = created["project_id"]
        job["project_id"] = project_id
        existing_refs = []
        if reference_asset_ids:
            assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
            for reference_id in reference_asset_ids:
                asset = next((a for a in assets if a["media_id"] == reference_id
                              and a["kind"] == "image"), None)
                if asset is None:
                    raise ValueError("Imagem de referência ausente deste projeto/conta.")
                existing_refs.append({"media_id": reference_id,
                                      "name": asset.get("name") or reference_id})
        if character_entity_id is not None:
            from flow_character import parse_characters

            if not any(c["entity_id"] == character_entity_id for c in parse_characters(
                    await client.rpc("Zzl0ze", project_id=project_id), project_id)):
                raise ValueError("Personagem ausente deste projeto/conta.")
            job["character_entity_id"] = character_entity_id
        features = [1, 4] if refs or existing_refs else [1]
        await generation_quote(client, job, features)
        uploaded = await prepare_reference_uploads(job, refs, client=client)
        captcha = await prepare_generation(client, project_id, "IMAGE_GENERATION")
        quote = await generation_quote(client, job, features)
        packet = image_request(project_id, prompt, quote["model_key"], aspect, count, captcha,
                               references=[r["media_id"] for r in existing_refs + uploaded],
                               reference_names={r["media_id"]:r["name"]
                                                for r in existing_refs + uploaded},
                               character_entity_id=character_entity_id, character_slot=character_slot)
        captured = client.request(packet["rpc_id"], packet["params"])
        job.update(request_media_ids=packet["request_media_ids"],
                   request_workflow_ids=packet["request_workflow_ids"],
                   status="submitting", source="HTTP/ogiZ0b")
        save_job(job)
        payload = await client.send_submit(captured)
        images = image_records(packet["rpc_id"], payload)
        expected = dict(zip(job["request_media_ids"], job["request_workflow_ids"]))
        if (not images or len({image.media_id for image in images}) != len(images)
                or any(image.project_id != project_id or expected.get(image.media_id) != image.workflow_id
                       for image in images)):
            raise ValueError("Resposta da geração pertence a outro pedido/projeto.")
        job.update(status="downloading", media_ids=[image.media_id for image in images],
                   workflow_ids=[image.workflow_id for image in images])
        save_job(job)
        output = downloads_dir()
        for image in images:
            media_id = str(UUID(image.media_id))
            body = await client.download(original_image_url(image.image_url), media_id)
            path = output / f"{media_id}{image_suffix(body)}"
            path.write_bytes(body)
            job["files"].append(str(path))
            save_job(job)
        job["status"] = "completed" if len(images) == count else "partial_result"
        await record_charge(client, job)
    except Exception as exc:
        job.update(error_fields(exc))
        job["failure_stage"] = job["status"]
        job["status"] = {"preparing": "failed_pre_submit", "submitting": "submission_unknown",
                         "downloading": "download_failed"}.get(job["status"], job["status"])
    finally:
        if owned:
            await client.close()
        save_job(job)
    return job


async def quote_images(account_id: str, model: str = "nano-banana-2", aspect: str = "16:9",
                       count: int = 1, with_references: bool = False, project_id: str | None = None,
                       *, client) -> dict:
    """Cotação de imagens pelo catálogo HTrJv, com as validações do envio real e sem criar tarefa."""
    from flow_capabilities import quote_configuration, read_capabilities
    from flow_projects import parse_projects
    from gflow_cli.api.image import Aspect

    model = normalize_model(model, IMAGE_MODELS)
    Aspect.from_cli(aspect)
    if type(count) is not int or not 1 <= count <= 4:
        raise ValueError("Informe de 1 a 4 imagens.")
    if type(with_references) is not bool:
        raise ValueError("with_references deve ser booleano.")
    if project_id is None:
        # O catálogo é lido no contexto de um projeto; cotar não cria projeto.
        projects = parse_projects(await client.rpc("UpteDb"))["projects"]
        if not projects:
            raise ValueError("Cotação exige ao menos um projeto na conta.")
        project_id = projects[0]["project_id"]
    capabilities = await read_capabilities(account_id, validate_project(project_id), client=client)
    quote = quote_configuration(capabilities, model, aspect=aspect, count=count, max_credits=10**6,
                                features=[1, 4] if with_references else [1])
    return {"account_id": account_id, "project_id": project_id, "status": "quoted", "model": model,
            "aspect": aspect, "count": count, "with_references": with_references, "quote": quote,
            "quoted_credits": quote["quoted_credits"], "credits_before": capabilities["credits"]}


def original_image_url(url: str) -> str:
    """lh3 sem transformação entrega 512px; =s0 preserva as dimensões originais."""
    parts = urlsplit(url)
    if parts.hostname == "lh3.googleusercontent.com":
        path = parts.path.split("=", 1)[0] + "=s0"
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    return url


def image_suffix(body: bytes) -> str:
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if body.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return ".webp"
    raise ValueError("O download não é uma imagem reconhecida.")
