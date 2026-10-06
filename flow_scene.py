"""Operações de edição de cena, extração de quadros e exportação de mídia."""

import asyncio
from datetime import datetime, timezone
import math
import os
from pathlib import Path
import platform
import re
import shutil
from uuid import uuid4

from flow_accounts import validate_account
from flow_errors import error_fields, tolerant_rows
from flow_assets import media_uuid
from flow_projects import validate_project
from flow_video import downloads_dir, get_job, save_job


_SCENE_ID = re.compile(r"^[A-Za-z0-9-]{1,128}$")
# ponytail: ARM (Banana Pi) só extrai quadros; GIF/montagem/upscale local ficam no Windows.
LIGHT_HOST = platform.machine().lower() in ("aarch64", "arm64", "armv7l")
HEAVY_FFMPEG_TOOLS = ["flow_export_gif", "flow_build_scene", "flow_upscale"]


def _heavy_ffmpeg_allowed():
    if LIGHT_HOST:
        raise RuntimeError("Processamento de vídeo pesado desativado nesta máquina (ARM) para não "
                           "sobrecarregá-la. Use flow_export_scene ou flow_upscale_video/"
                           "flow_upscale_image (nativos do Flow), ou o MCP do Windows.")


def _scene_id(value: str) -> str:
    if not isinstance(value, str) or not _SCENE_ID.fullmatch(value):
        raise ValueError(f"scene_id inválido ({str(value)[:80]!r}); use um scene_id de flow_list_scenes.")
    return value


def _native_scene(row, project_id):
    if (not isinstance(row, list) or len(row) < 8 or type(row[5]) is not int
            or row[5] != 2 or not isinstance(row[1], str) or not row[1].strip()
            or not isinstance(row[7], list)):
        raise ValueError("Registro de cena não reconhecido.")
    # row[7] é scene_metadata; [True] marca a cena movida para a lixeira.
    return {"scene_id":_scene_id(row[0]), "project_id":project_id, "title":row[1],
            "archived":row[7][:1] == [True]}


def parse_scenes(payload, project_id):
    validate_project(project_id)
    if not isinstance(payload, list) or len(payload) < 8:  # Seções novas no fim não invalidam.
        raise ValueError("Resposta de cenas não reconhecida.")
    rows = payload[4]
    if rows is None:
        return []
    if not isinstance(rows, list):
        raise ValueError("Resposta de cenas não reconhecida.")
    scenes = tolerant_rows(rows, lambda row: _native_scene(row, project_id))
    if len({scene["scene_id"] for scene in scenes}) != len(scenes):
        raise ValueError("Cena duplicada na resposta do projeto.")
    return scenes


def _scene_seconds(value):
    if isinstance(value, list) and len(value) == 2 and value[0] is None:
        value = [0, value[1]]
    if (not isinstance(value, list) or len(value) > 2
            or any(type(part) is not int or part < 0 for part in value)
            or len(value) == 2 and value[1] >= 1_000_000_000):
        raise ValueError("Duração da cena não reconhecida.")
    return (value[0] if value else 0) + (value[1] / 1_000_000_000 if len(value) == 2 else 0)


def parse_native_scene(payload, project_id, scene_id):
    from gflow_cli.api.scene import Scene, SceneWorkflow, SceneWorkflowMetadata
    from flow_assets import parse_assets

    _scene_id(scene_id)
    if not any(scene["scene_id"] == scene_id for scene in parse_scenes(payload, project_id)):
        raise ValueError("Cena ausente da resposta inicial deste projeto.")
    rows = [] if payload[6] is None else payload[6]
    if not isinstance(rows, list):
        raise ValueError("Composição da cena não reconhecida.")
    assets = {(asset["media_id"], asset["workflow_id"]):asset for asset in parse_assets(payload, project_id)}
    clips = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 3:
            raise ValueError("Clipe de cena não reconhecido.")
        if row[1] != scene_id:
            continue
        workflow, _, metadata = row
        if (not isinstance(workflow, list) or len(workflow) < 5 or workflow[4] != project_id
                or not isinstance(workflow[3], list) or len(workflow[3]) < 5
                or not isinstance(metadata, list) or len(metadata) < 4):
            raise ValueError("Clipe de cena não reconhecido.")
        workflow_id, media_id = media_uuid(workflow[0]), media_uuid(workflow[3][4])
        asset = assets.get((media_id, workflow_id))
        if asset is None or asset["kind"] != "video":
            raise ValueError("Vídeo da cena não confirmado neste projeto.")
        position = 0 if metadata[0] is None else metadata[0]
        total, start, end = (_scene_seconds(value) for value in metadata[1:4])
        if type(position) is not int or position < 0 or not 0 <= start < end <= total:
            raise ValueError("Ordem ou corte da cena não reconhecido.")
        clips.append(SceneWorkflow(workflow_id, SceneWorkflowMetadata(position, start, end, total), media_id))
    if (len({clip.workflow_id for clip in clips}) != len(clips)
            or len({clip.metadata.position for clip in clips}) != len(clips)):
        raise ValueError("Clipe ou posição duplicados na cena.")
    return Scene(scene_id, project_id, tuple(sorted(clips, key=lambda clip:clip.metadata.position)))


async def list_scenes(account_id, project_id, query="", *, client=None):
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Pesquisa de cena inválida.")
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        scenes = parse_scenes(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        scenes = [scene for scene in scenes if query.casefold() in scene["title"].casefold()
                  or query == scene["scene_id"]]
        return {"account_id":account_id, "project_id":project_id, "status":"ok",
                "scenes":scenes, "count":len(scenes), "complete":False,
                "source":"HTTP/Zzl0ze", "observed_at":datetime.now(timezone.utc).isoformat()}
    finally:
        if owned:
            await client.close()


def _duration_wire(seconds):
    whole, nanos = divmod(round(seconds * 1_000_000_000), 1_000_000_000)
    return [] if not whole and not nanos else [whole] if not nanos else [whole or None, nanos]


def _scene_job_failed(job, exc):
    before = job["status"] == "preparing"
    job.update(status="failed_pre_submit" if before else "submission_unknown",
               retry_automatically=False, **error_fields(exc))
    save_job(job)
    return job


async def _create_empty_scene(client, project_id):
    job = {"job_id":str(uuid4()), "account_id":client.account_id, "project_id":project_id,
           "kind":"scene_create", "status":"preparing", "source":"HTTP/rqZuUc", "files":[]}
    save_job(job)
    try:
        # Conferir o projeto antes da única mutação; rqZuUc cria a cena vazia.
        parse_scenes(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        async with client.browser.page() as page:
            await page.goto(f"https://flow.google.com/project/{project_id}",
                            wait_until="domcontentloaded", timeout=45000)
            await page.get_by_role("button", name=re.compile("^Menu para adicionar arquivos$|^Add files menu$", re.I)).click(timeout=15000)
            captured = await client.capture_submit(page,
                page.get_by_role("menuitem", name=re.compile("Nova cena|New scene", re.I)), {"rqZuUc"})
            if (captured.get("rpc_id") != "rqZuUc"
                    or captured.get("params") != [f"projects/{project_id}", None, None, None, 2]):
                raise ValueError("Pedido de criação da cena não confirmado; envio bloqueado.")
        job["status"] = "submitting"
        save_job(job)
        payload = await client.send_submit(captured)
        if not isinstance(payload, list) or len(payload) != 1:
            raise ValueError("Resposta de criação da cena não reconhecida.")
        scene = _native_scene(payload[0], project_id)
        job.update(scene_id=scene["scene_id"], title=scene["title"])
        save_job(job)
        scenes = parse_scenes(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        if scene not in scenes:
            raise ValueError("Criação da cena não confirmada por leitura.")
        job["status"] = "completed"
        save_job(job)
        return {**job, "status":"created", "clips":[], "complete":False}
    except Exception as exc:
        return _scene_job_failed(job, exc)


async def _add_scene_clips(client, project_id, scene_id, workflow_ids, position):
    from flow_assets import parse_assets

    job = {"job_id":str(uuid4()), "account_id":client.account_id, "project_id":project_id,
           "scene_id":scene_id, "kind":"scene_update", "status":"preparing",
           "source":"HTTP/oWTRd", "workflow_ids":workflow_ids, "files":[]}
    save_job(job)
    try:
        payload = await client.rpc("Zzl0ze", project_id=project_id)
        current = parse_native_scene(payload, project_id, scene_id)
        videos = {asset["workflow_id"] for asset in parse_assets(payload, project_id) if asset["kind"] == "video"}
        if any(workflow_id not in videos for workflow_id in workflow_ids):
            raise ValueError("Clipe não é vídeo confirmado neste projeto.")
        position = len(current.workflows) if position is None else position
        if position > len(current.workflows):
            raise ValueError("Posição fora da cena.")
        job.update(status="submitting", position=position)
        save_job(job)
        # Pedido capturado na interface: [projeto, cena, workflow_ids, posição].
        try:
            await client.rpc("oWTRd", params=[project_id, scene_id, workflow_ids, position])
        except Exception as exc:
            # Resultado decidido só pela leitura posterior; nunca reenviar. O erro fica como evidência.
            job.update(error_fields(exc, "submit_"))
        # A listagem pode atrasar alguns segundos; somente leituras se repetem.
        for attempt in range(6):
            if attempt:
                await asyncio.sleep(2)
            confirmed = parse_native_scene(await client.rpc("Zzl0ze", project_id=project_id), project_id, scene_id)
            # A cena guarda clones com novos workflow_ids; confirmar pela contagem e posição.
            previous = {clip.workflow_id for clip in current.workflows}
            added = [clip for clip in confirmed.workflows if clip.workflow_id not in previous]
            if ({clip.workflow_id for clip in confirmed.workflows} >= previous
                    and len(added) == len(workflow_ids)):
                break
        else:
            raise ValueError("Inclusão não confirmada por leitura.")
        if [clip.metadata.position for clip in added] != list(range(position, position + len(added))):
            raise ValueError("Posição da inclusão não confirmada por leitura.")
        job.update(status="completed", added_workflow_ids=[clip.workflow_id for clip in added])
        save_job(job)
        return {**job, "status":"updated", "complete":False, **_scene_data(confirmed)}
    except Exception as exc:
        return _scene_job_failed(job, exc)


async def _update_scene_clips(client, project_id, scene_id, clips, remove_ids=None):
    from gflow_cli.api.scene import SceneWorkflow, SceneWorkflowMetadata

    job = {"job_id":str(uuid4()), "account_id":client.account_id, "project_id":project_id,
           "scene_id":scene_id, "kind":"scene_update", "status":"preparing",
           "source":"HTTP/GoMJte", "files":[]}
    save_job(job)
    try:
        current = parse_native_scene(await client.rpc("Zzl0ze", project_id=project_id), project_id, scene_id)
        by_id = {clip.workflow_id: clip for clip in current.workflows}
        if remove_ids is not None:
            # A interface remove clipes reenviando a lista restante, com cortes preservados.
            if not set(remove_ids) <= set(by_id):
                raise ValueError("Clipe a remover não está na cena.")
            clips = [{"workflow_id":clip.workflow_id} for clip in current.workflows
                     if clip.workflow_id not in remove_ids]
            job["removed_workflow_ids"] = remove_ids
        ids = [clip.get("workflow_id") for clip in clips if isinstance(clip, dict)]
        if len(ids) != len(clips) or any(not isinstance(value, str) for value in ids):
            raise ValueError("Cada clipe precisa de um workflow_id válido.")
        for workflow_id in ids:
            media_uuid(workflow_id)
        if len(set(ids)) != len(ids) or set(ids) != set(by_id) - set(remove_ids or []):
            raise ValueError("A atualização deve listar cada clipe atual da cena uma vez.")
        updated = []
        for position, clip in enumerate(clips):
            previous = by_id[clip["workflow_id"]]
            total = previous.metadata.total_duration
            start = clip.get("start_time", previous.metadata.start_time)
            end = clip.get("end_time", previous.metadata.end_time)
            if (type(start) not in {int, float} or not math.isfinite(start) or start < 0
                    or type(end) not in {int, float} or not math.isfinite(end) or end < 0):
                raise ValueError("Cortes devem ser segundos não negativos e finitos.")
            end = end if end > 0 else total
            if total <= 0 or start >= end or end > total:
                raise ValueError("Corte fora da duração do clipe.")
            updated.append(SceneWorkflow(previous.workflow_id,
                SceneWorkflowMetadata(position, start, end, total), previous.media_id))
        # Pedido capturado na interface: a lista completa substitui ordem e cortes.
        params = [project_id, scene_id, [[[clip.workflow_id, None, None, [None, None, None, None, clip.media_id]],
                  scene_id, [clip.metadata.position or None, _duration_wire(clip.metadata.total_duration),
                             _duration_wire(clip.metadata.start_time), _duration_wire(clip.metadata.end_time)]]
                  for clip in updated]]
        if not updated:
            params.pop()  # Cena esvaziada: a interface envia só [projeto, cena].
        job["status"] = "submitting"
        save_job(job)
        try:
            await client.rpc("GoMJte", params=params)
        except Exception as exc:
            # Resultado decidido só pela leitura posterior; nunca reenviar. O erro fica como evidência.
            job.update(error_fields(exc, "submit_"))
        wanted = {clip.workflow_id: clip.metadata for clip in updated}
        for attempt in range(6):
            if attempt:
                await asyncio.sleep(2)
            confirmed = parse_native_scene(await client.rpc("Zzl0ze", project_id=project_id), project_id, scene_id)
            actual = {clip.workflow_id: clip.metadata for clip in confirmed.workflows}
            if set(actual) == set(wanted) and all(
                    actual[key].position == meta.position
                    and math.isclose(actual[key].start_time, meta.start_time, abs_tol=1e-6)
                    and math.isclose(actual[key].end_time, meta.end_time, abs_tol=1e-6)
                    for key, meta in wanted.items()):
                break
        else:
            raise ValueError("Ordem/cortes não confirmados por leitura.")
        job["status"] = "completed"
        save_job(job)
        return {**job, "status":"updated", "complete":False, **_scene_data(confirmed)}
    except Exception as exc:
        return _scene_job_failed(job, exc)


async def _update_scene_record(client, project_id, scene_id, params, kind, confirmed,
                               rpc_id="BpMsoe", ready=lambda scene: True):
    """Envia a mutação uma vez e decide o resultado somente pela leitura de Zzl0ze."""
    job = {"job_id":str(uuid4()), "account_id":client.account_id, "project_id":project_id,
           "scene_id":scene_id, "kind":kind, "status":"preparing", "source":f"HTTP/{rpc_id}", "files":[]}
    save_job(job)
    try:
        scenes = parse_scenes(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        current = next((scene for scene in scenes if scene["scene_id"] == scene_id), None)
        if current is None:
            raise ValueError("Cena ausente da resposta inicial deste projeto.")
        if not ready(current):
            raise ValueError("Estado da cena incompatível: exclusão definitiva só a partir da lixeira.")
        job["status"] = "submitting"
        save_job(job)
        try:
            await client.rpc(rpc_id, params=params)
        except Exception as exc:
            # Resultado decidido só pela leitura posterior; nunca reenviar. O erro fica como evidência.
            job.update(error_fields(exc, "submit_"))
        for attempt in range(6):
            if attempt:
                await asyncio.sleep(2)
            scenes = parse_scenes(await client.rpc("Zzl0ze", project_id=project_id), project_id)
            if confirmed(next((scene for scene in scenes if scene["scene_id"] == scene_id), None)):
                break
        else:
            raise ValueError("Alteração da cena não confirmada por leitura.")
        job["status"] = "completed"
        save_job(job)
        return {**job, "status":"deleted" if kind == "scene_delete" else "updated"}
    except Exception as exc:
        return _scene_job_failed(job, exc)


def _scene_data(scene) -> dict:
    return {
        "scene_id": scene.scene_id,
        "project_id": scene.project_id,
        "clips": [{
            "workflow_id": clip.workflow_id,
            "media_id": clip.media_id,
            "position": clip.metadata.position,
            "start_time": clip.metadata.start_time,
            "end_time": clip.metadata.end_time,
            "total_duration": clip.metadata.total_duration,
        } for clip in scene.workflows],
    }


async def manage_scene(account_id: str, project_id: str, operation: str,
                       *, scene_id: str | None = None, workflow_ids: list[str] | None = None,
                       clips: list[dict] | None = None, position: int | None = None,
                       title: str | None = None, confirm: bool = False,
                       client=None) -> dict:
    """Create, read, add/remove clips, reorder/trim, rename or archive a Flow scene."""
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    if operation not in {"create", "read", "add", "remove", "update", "rename", "archive", "restore", "delete"}:
        raise ValueError("Operação de cena inválida: use create, read, add, remove, update, rename, "
                         "archive, restore ou delete.")
    if operation == "rename" and (not isinstance(title, str) or not title.strip() or len(title) > 200):
        raise ValueError("Informe um título de 1 a 200 caracteres.")
    if operation in {"archive", "delete"} and confirm is not True:
        raise ValueError("Mover para a lixeira ou excluir definitivamente exige confirm=true.")
    if operation in {"create", "add", "remove"} and (workflow_ids or operation != "create"):
        if (not isinstance(workflow_ids, list) or not 1 <= len(workflow_ids) <= 50
                or len(set(workflow_ids)) != len(workflow_ids)):
            raise ValueError("Informe workflow_ids: de 1 a 50 IDs distintos (workflow_id de flow_list_assets "
                             "para add/create; IDs dos clipes da cena, de operation=read, para remove).")
        for workflow_id in workflow_ids:
            media_uuid(workflow_id)
    elif operation == "create" and workflow_ids not in (None, []):
        raise ValueError("Informe até 50 IDs de clipe de vídeo.")
    if operation != "create":
        _scene_id(scene_id)
    if operation == "add" and position is not None and (type(position) is not int or position < 0):
        raise ValueError("Posição de cena inválida.")
    if operation == "update" and (not isinstance(clips, list) or not 1 <= len(clips) <= 50):
        raise ValueError("Informe a ordem de 1 a 50 clipes da cena.")

    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    try:
        if operation == "read":
            payload = await client.rpc("Zzl0ze", project_id=project_id)
            return {"account_id":account_id, "status":"ok", "source":"HTTP/Zzl0ze",
                    "complete":False, **_scene_data(parse_native_scene(payload, project_id, scene_id))}
        if operation == "update":
            return await _update_scene_clips(client, project_id, scene_id, clips)
        if operation == "remove":
            return await _update_scene_clips(client, project_id, scene_id, None, workflow_ids)
        if operation == "rename":
            title = title.strip()
            return {**await _update_scene_record(client, project_id, scene_id,
                [project_id, scene_id, [None, title], [["display_name"]]], "scene_rename",
                lambda scene: scene is not None and scene["title"] == title), "title":title}
        if operation == "archive":
            # Pedido capturado em "Mover para a lixeira"; a listagem passa a marcar archived.
            return await _update_scene_record(client, project_id, scene_id,
                [project_id, scene_id, [scene_id, None, None, None, None, None, None, [1]],
                 [["scene_metadata.is_archived", "parent_collection_id"]]], "scene_archive",
                lambda scene: scene is None or scene["archived"])
        if operation == "restore":
            # Pedido capturado em "Restaurar" na lixeira do projeto.
            return await _update_scene_record(client, project_id, scene_id,
                [project_id, scene_id, [scene_id, None, None, None, None, None, None, []],
                 [["scene_metadata.is_archived", "parent_collection_id"]]], "scene_restore",
                lambda scene: scene is not None and not scene["archived"])
        if operation == "delete":
            # "Excluir permanentemente" na lixeira usa BatchDeleteAssets com o ID da cena.
            return await _update_scene_record(client, project_id, scene_id,
                [None, None, project_id, None, [scene_id]], "scene_delete",
                lambda scene: scene is None, rpc_id="cz8Z4b", ready=lambda scene: scene["archived"])
        if operation == "add":
            return await _add_scene_clips(client, project_id, scene_id, workflow_ids, position)
        created = await _create_empty_scene(client, project_id)
        if not workflow_ids or created["status"] != "created":
            return created
        added = await _add_scene_clips(client, project_id, created["scene_id"], workflow_ids, None)
        return {**added, "status":"created" if added["status"] == "updated" else added["status"],
                "create_job_id":created["job_id"], "title":created["title"]}
    finally:
        if owned:
            await client.close()


async def export_scene(account_id: str, project_id: str, scene_id: str,
                       *, client=None) -> dict:
    """Render a saved Flow scene as one MP4 without resubmitting an uncertain export."""
    import base64
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    _scene_id(scene_id)
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    job = {"job_id":str(uuid4()), "account_id":account_id, "project_id":project_id,
           "scene_id":scene_id, "kind":"scene_export", "status":"preparing",
           "source":"HTTP/GjQLTd", "files":[]}
    save_job(job)
    try:
        scene = parse_native_scene(await client.rpc("Zzl0ze", project_id=project_id), project_id, scene_id)
        if not 1 <= len(scene.workflows) <= 50:
            raise ValueError("A cena deve conter entre 1 e 50 clipes.")
        # Pedido capturado na interface: mídia de cada clipe com início/fim, na ordem da cena.
        params = [[[clip.media_id, None, _duration_wire(clip.metadata.start_time),
                    _duration_wire(clip.metadata.end_time)] for clip in scene.workflows]]
        job["status"] = "submitting"
        save_job(job)
        response = await client.rpc("GjQLTd", params=params)
        operation = response[1][0][0]
        if not isinstance(operation, str) or not operation:
            raise ValueError("Operação de exportação não reconhecida.")
        job["status"] = "processing"
        save_job(job)
        # IxdSwd: 2 = em andamento; ao concluir, o MP4 chega em base64 no quinto campo.
        for attempt in range(60):
            if attempt:
                await asyncio.sleep(3)
            state = await client.rpc("IxdSwd", params=[[[operation]]])
            if not isinstance(state, list) or not state or state[0] != 2:
                break
        encoded = state[4] if isinstance(state, list) and len(state) > 4 else None
        if not isinstance(encoded, str) or not encoded:
            if isinstance(state, list) and state and state[0] == 2:
                raise ValueError("Exportação ainda em processamento após 3 minutos. Nas validações a "
                                 "exportação não gastou créditos; uma nova chamada mais tarde inicia outra exportação.")
            raise ValueError("Exportação sem arquivo confirmado.")
        video = base64.b64decode(encoded, validate=True)
        if video[4:8] != b"ftyp":
            raise ValueError("Exportação não retornou MP4.")
        output = downloads_dir()
        target = output / f"scene_{scene_id}_{job['job_id'][:8]}.mp4"
        await asyncio.to_thread(target.write_bytes, video)
        job.update(status="completed", files=[str(target)])
        save_job(job)
        return {**job, "status":"exported", "path":str(target), "bytes":len(video),
                "clips":len(scene.workflows)}
    except Exception as exc:
        return _scene_job_failed(job, exc)
    finally:
        if owned:
            await client.close()


async def _ensure_local_asset(client, account_id: str, project_id: str, media_id: str) -> tuple[Path, str]:
    """Garante que o arquivo de mídia (vídeo ou imagem) esteja disponível localmente."""
    from flow_http import http_operation

    output = downloads_dir()
    for ext in [".mp4", ".png", ".jpg", ".jpeg", ".webp"]:
        candidate = output / f"{media_id}{ext}"
        if candidate.is_file() and candidate.stat().st_size > 0:
            kind = "video" if ext == ".mp4" else "image"
            return candidate, kind

    # Se não existe localmente, baixa via cliente HTTP
    download = await http_operation(client, "download_asset", {"project_id": project_id, "media_id": media_id})
    target = Path(download["path"]).resolve()
    if not target.is_file() or target.stat().st_size == 0:
        raise ValueError("Ativo de origem não pôde ser baixado.")
    kind = "video" if target.suffix.lower() == ".mp4" else "image"
    return target, kind


async def _ensure_local_video(client, account_id: str, project_id: str, media_id: str) -> Path:
    """Garante que o arquivo de vídeo MP4 esteja disponível localmente para processamento."""
    target, kind = await _ensure_local_asset(client, account_id, project_id, media_id)
    if kind != "video":
        raise ValueError("Vídeo de origem não pôde ser baixado.")
    return target


async def save_video_frame(account_id: str, project_id: str, media_id: str,
                           timestamp_seconds: float = 0.0,
                           upload_to_flow: bool = False,
                           *, client=None) -> dict:
    """Extrai um quadro de um vídeo em alta resolução e opcionalmente envia como asset de imagem."""
    from flow_http import FlowHTTP
    from flow_assets import upload_image

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)

    if not isinstance(timestamp_seconds, (int, float)) or timestamp_seconds < 0:
        raise ValueError("Timestamp deve ser um número não negativo.")

    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg não está instalado na máquina do MCP (ex.: sudo apt install ffmpeg).")

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        video_path = await _ensure_local_video(client, account_id, project_id, media_id)

        output_dir = downloads_dir()
        frame_id = str(uuid4())
        frame_path = output_dir / f"frame_{media_id}_{frame_id[:8]}.png"

        # ffmpeg: -ss antes de -i para busca rápida, extraindo 1 quadro com máxima qualidade
        cmd = [
            *(["nice", "-n", "19"] if shutil.which("nice") else []),
            ffmpeg_bin, "-threads", "1",
            "-ss", f"{timestamp_seconds:.3f}",
            "-i", str(video_path),
            "-frames:v", "1",
            "-q:v", "2",
            "-y",
            str(frame_path)
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not frame_path.is_file() or frame_path.stat().st_size == 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Falha ao extrair quadro com ffmpeg: {err_msg[:300]}")

        result = {
            "account_id": account_id,
            "project_id": project_id,
            "source_media_id": media_id,
            "timestamp_seconds": timestamp_seconds,
            "frame_path": str(frame_path),
            "bytes": frame_path.stat().st_size,
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

        if upload_to_flow:
            upload_res = await upload_image(account_id, project_id, str(frame_path), client=client)
            result["flow_upload"] = upload_res
            result["asset_media_id"] = upload_res.get("media_id")

        return result
    finally:
        if owned:
            await client.close()


async def export_video_gif(account_id: str, project_id: str, media_id: str,
                           start_time: float = 0.0,
                           duration: float | None = None,
                           fps: int = 15,
                           width: int = 480,
                           *, client=None) -> dict:
    """Converte um vídeo (ou trecho) em GIF animado de alta qualidade usando paleta otimizada."""
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)

    if not isinstance(start_time, (int, float)) or start_time < 0:
        raise ValueError("start_time deve ser um número não negativo.")
    if duration is not None and (not isinstance(duration, (int, float)) or duration <= 0):
        raise ValueError("duration deve ser um número positivo.")
    if not isinstance(fps, int) or not 1 <= fps <= 30:
        raise ValueError("fps deve ser um inteiro entre 1 e 30.")
    if not isinstance(width, int) or not 120 <= width <= 1920:
        raise ValueError("width deve ser um inteiro entre 120 e 1920.")

    _heavy_ffmpeg_allowed()
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg não está instalado na máquina do MCP (ex.: sudo apt install ffmpeg).")

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        video_path = await _ensure_local_video(client, account_id, project_id, media_id)

        output_dir = downloads_dir()
        gif_id = str(uuid4())
        gif_path = output_dir / f"{media_id}_{gif_id[:8]}.gif"

        filter_graph = f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd = [ffmpeg_bin, "-ss", f"{start_time:.3f}"]
        if duration is not None:
            cmd.extend(["-t", f"{duration:.3f}"])
        cmd.extend(["-i", str(video_path), "-vf", filter_graph, "-y", str(gif_path)])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not gif_path.is_file() or gif_path.stat().st_size == 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Falha ao gerar GIF com ffmpeg: {err_msg[:300]}")

        return {
            "account_id": account_id,
            "project_id": project_id,
            "source_media_id": media_id,
            "gif_path": str(gif_path),
            "bytes": gif_path.stat().st_size,
            "fps": fps,
            "width": width,
            "start_time": start_time,
            "duration": duration,
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if owned:
            await client.close()


async def _has_audio_stream(video_path: Path) -> bool:
    """Verifica se o vídeo contém faixa de áudio."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return True
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-select_streams", "a",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        str(video_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return "audio" in stdout.decode("utf-8", errors="ignore").lower()
    except Exception:
        return True


async def _get_video_duration(video_path: Path) -> float:
    """Obtém a duração do vídeo em segundos via ffprobe."""
    ffprobe_bin = shutil.which("ffprobe")
    if not ffprobe_bin:
        return 8.0
    cmd = [
        ffprobe_bin,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        str(video_path),
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return float(stdout.decode("utf-8", errors="ignore").strip())
    except Exception:
        return 8.0


async def build_scene(account_id: str, project_id: str, clips: list[dict],
                      scene_title: str = "Cena sem título",
                      *, client=None) -> dict:
    """Scenebuilder: sequencia, corta e concatena múltiplos clipes de vídeo em uma cena MP4 contínua."""
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)

    if not isinstance(clips, list) or len(clips) < 1 or len(clips) > 50:
        raise ValueError("Informe entre 1 e 50 clipes para a cena.")
    if not isinstance(scene_title, str) or not scene_title.strip() or len(scene_title) > 200:
        raise ValueError("Título da cena inválido.")

    for i, clip in enumerate(clips):
        if not isinstance(clip, dict) or "media_id" not in clip:
            raise ValueError(f"Clipe {i} deve ser um dicionário contendo 'media_id'.")
        media_uuid(clip["media_id"])
        trim_start = clip.get("trim_start")
        trim_end = clip.get("trim_end")
        if trim_start is not None and (not isinstance(trim_start, (int, float)) or trim_start < 0):
            raise ValueError(f"trim_start do clipe {i} deve ser não negativo.")
        if trim_end is not None and (not isinstance(trim_end, (int, float)) or trim_end <= (trim_start or 0)):
            raise ValueError(f"trim_end do clipe {i} deve ser maior que trim_start.")

    _heavy_ffmpeg_allowed()
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg não está instalado na máquina do MCP (ex.: sudo apt install ffmpeg).")

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        output_dir = downloads_dir()
        scene_id = str(uuid4())
        scene_path = output_dir / f"scene_{scene_id[:8]}.mp4"

        # Baixar todos os clipes locais
        local_files = []
        for clip in clips:
            path = await _ensure_local_video(client, account_id, project_id, clip["media_id"])
            local_files.append((path, clip.get("trim_start"), clip.get("trim_end")))

        # Montagem dos inputs e filtros do ffmpeg
        cmd = [ffmpeg_bin]
        filter_inputs = []
        filter_parts = []

        for idx, (path, t_start, t_end) in enumerate(local_files):
            clip_duration = None
            if t_start is not None:
                cmd.extend(["-ss", f"{t_start:.3f}"])
            if t_end is not None:
                clip_duration = t_end - (t_start or 0)
                cmd.extend(["-t", f"{clip_duration:.3f}"])
            cmd.extend(["-i", str(path)])
            # Padronizar resolução para 1280x720 e framerate para 24fps para concatenação sem falha
            filter_parts.append(f"[{idx}:v]scale=1280:720:force_original_aspect_ratio=decrease,pad=1280:720:(ow-iw)/2:(oh-ih)/2,fps=24,setsar=1[v{idx}];")
            # Tratar áudio: se o clipe não tiver áudio, gerar faixa de silêncio para manter sincronia
            has_audio = await _has_audio_stream(path)
            if has_audio:
                filter_parts.append(f"[{idx}:a]aformat=sample_rates=44100:channel_layouts=stereo[a{idx}];")
            else:
                dur = clip_duration if clip_duration is not None else await _get_video_duration(path)
                filter_parts.append(f"aevalsrc=0:d={dur:.3f},aformat=sample_rates=44100:channel_layouts=stereo[a{idx}];")
            filter_inputs.append(f"[v{idx}][a{idx}]")

        n = len(local_files)
        filter_str = "".join(filter_parts) + "".join(filter_inputs) + f"concat=n={n}:v=1:a=1[outv][outa]"

        cmd.extend([
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "192k",
            "-y",
            str(scene_path)
        ])

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not scene_path.is_file() or scene_path.stat().st_size == 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Falha ao renderizar cena com ffmpeg: {err_msg[:300]}")

        return {
            "account_id": account_id,
            "project_id": project_id,
            "scene_id": scene_id,
            "title": scene_title,
            "clip_count": len(clips),
            "scene_path": str(scene_path),
            "bytes": scene_path.stat().st_size,
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if owned:
            await client.close()


def cancel_job(account_id: str, job_id: str) -> dict:
    """Cancela uma tarefa local pendente para evitar tentativas de recuperação ou polling."""
    from gflow_cli.config import get_settings

    validate_account(account_id)
    root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles")).resolve()
    if "GFLOW_CLI_HOME" not in os.environ:
        os.environ["GFLOW_CLI_HOME"] = str(root)
        get_settings.cache_clear()
    try:
        job = get_job(account_id, job_id)
    except FileNotFoundError:
        raise ValueError(f"Tarefa {job_id} não encontrada.") from None
    if job.get("status") in {"completed", "cancelled"}:
        return {"account_id": account_id, "job_id": job_id, "status": job.get("status"), "message": "Tarefa já finalizada."}
    job["status"] = "cancelled"
    job["cancelled_at"] = datetime.now(timezone.utc).isoformat()
    save_job(job)
    return {"account_id": account_id, "job_id": job_id, "status": "cancelled"}


async def upscale_media(account_id: str, project_id: str, media_id: str,
                        target_resolution: str = "1080p",
                        upload_to_flow: bool = False,
                        *, client=None) -> dict:
    """Aumenta a resolução de um vídeo ou imagem com filtro lanczos e nitidez unsharp."""
    from flow_http import FlowHTTP
    from flow_assets import upload_image

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)

    res_lower = str(target_resolution).lower().strip()
    resolution_dimensions = {
        "720p": 1280,
        "1080p": 1920,
        "4k": 3840,
    }
    if res_lower not in resolution_dimensions:
        raise ValueError("Resolução de destino inválida. Use '720p', '1080p' ou '4k'.")

    max_dim = resolution_dimensions[res_lower]

    _heavy_ffmpeg_allowed()
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        raise RuntimeError("ffmpeg não está instalado na máquina do MCP (ex.: sudo apt install ffmpeg).")

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        source_path, kind = await _ensure_local_asset(client, account_id, project_id, media_id)

        output_dir = downloads_dir()
        upscale_id = str(uuid4())

        scale_filter = f"scale='if(gte(a,1),{max_dim},-2)':'if(gte(a,1),-2,{max_dim})':flags=lanczos,unsharp=5:5:0.8:3:3:0.4"

        if kind == "video":
            out_path = output_dir / f"upscale_{media_id}_{res_lower}_{upscale_id[:8]}.mp4"
            cmd = [
                ffmpeg_bin,
                "-i", str(source_path),
                "-vf", scale_filter,
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-c:a", "copy",
                "-y",
                str(out_path)
            ]
        else:
            ext = source_path.suffix.lower() if source_path.suffix else ".png"
            out_path = output_dir / f"upscale_{media_id}_{res_lower}_{upscale_id[:8]}{ext}"
            cmd = [
                ffmpeg_bin,
                "-i", str(source_path),
                "-vf", scale_filter,
                "-y",
                str(out_path)
            ]

        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0 or not out_path.is_file() or out_path.stat().st_size == 0:
            err_msg = stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(f"Falha no upscale com ffmpeg: {err_msg[:300]}")

        result = {
            "account_id": account_id,
            "project_id": project_id,
            "source_media_id": media_id,
            "target_resolution": res_lower,
            "kind": kind,
            "output_path": str(out_path),
            "bytes": out_path.stat().st_size,
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }

        if upload_to_flow:
            if kind == "image":
                upload_res = await upload_image(account_id, project_id, str(out_path), client=client)
                result["flow_upload"] = upload_res
                result["asset_media_id"] = upload_res.get("media_id")
            else:
                from flow_assets import upload_asset

                upload_res = await upload_asset(account_id, project_id, str(out_path), client=client)
                result["flow_upload"] = upload_res
                result["flow_upload_status"] = upload_res.get("status")
                if upload_res.get("media_id"):
                    result["asset_media_id"] = upload_res["media_id"]

        return result
    finally:
        if owned:
            await client.close()


def clean_jobs(account_id: str, status_filter: str | None = None) -> dict:
    """Limpa tarefas locais finalizadas ou canceladas para liberar espaço em disco."""
    from flow_video import job_path
    from gflow_cli.config import get_settings

    validate_account(account_id)
    root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles")).resolve()
    if "GFLOW_CLI_HOME" not in os.environ:
        os.environ["GFLOW_CLI_HOME"] = str(root)
        get_settings.cache_clear()

    jobs_dir = job_path(str(uuid4())).parent
    if not jobs_dir.is_dir():
        return {"account_id": account_id, "cleaned_count": 0, "remaining_count": 0, "status": "ok"}

    status_mapping = {
        "completed": {"completed"},
        "cancelled": {"cancelled"},
        "failed": {"failed_pre_submit", "generation_failed", "failed"},
        "uncertain": {"submission_unknown", "uncertain"},
        "failed_pre_submit": {"failed_pre_submit"},
        "generation_failed": {"generation_failed"},
        "submission_unknown": {"submission_unknown"},
        "partial_result": {"partial_result"},
    }
    if status_filter is not None:
        sf = str(status_filter).lower().strip()
        if sf not in status_mapping:
            raise ValueError(f"Filtro de status inválido. Opções: {sorted(status_mapping.keys())}")
        targets = status_mapping[sf]
    else:
        targets = {"completed", "cancelled"}

    cleaned = 0
    remaining = 0
    for path in jobs_dir.glob("*.json"):
        try:
            job = get_job(account_id, path.stem)
        except Exception:
            continue
        if job.get("status") in targets:
            path.unlink(missing_ok=True)
            cleaned += 1
        else:
            remaining += 1

    return {
        "account_id": account_id,
        "cleaned_count": cleaned,
        "remaining_count": remaining,
        "target_statuses": sorted(targets),
        "status": "ok"
    }
