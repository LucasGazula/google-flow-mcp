"""Ativos do host atual; respostas assinadas permanecem somente em memória."""

import asyncio
import base64
from pathlib import Path
from uuid import UUID

from flow_projects import validate_project


def _base_media_id(value: str) -> str:
    while True:
        base = value
        for suffix in ("_720p_upsampled", "_upsampled"):
            value = value.removesuffix(suffix)
        if value == base:
            return value


def media_uuid(value: str) -> str:
    message = (f"ID inválido ({str(value)[:80]!r}); esperado um UUID do Flow "
               "(media_id de flow_list_assets, entity_id de flow_list_characters etc.).")
    if not isinstance(value, str):
        raise ValueError(message)
    media_id = _base_media_id(value)
    try:
        valid = str(UUID(media_id)) == media_id
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(message)
    return value


def media_revision(value: str | None) -> int:
    """Campo protobuf em base64: CAE=1, CAI=2, CAM=3, ...

    Desde 05/10/2026 o Flow omite a versão 1 (valor padrão) em mídias novas.
    """
    if value is None:
        return 1
    if not isinstance(value,str) or len(value)>16:
        raise ValueError("Versão de mídia inválida.")
    try:
        raw=base64.b64decode(value+"="*(-len(value)%4),validate=True)
    except ValueError:
        raise ValueError("Versão de mídia inválida.") from None
    if not 2 <= len(raw) <= 11 or raw[0] != 8 or raw[-1] & 128:
        raise ValueError("Versão de mídia inválida.")
    if any(byte < 128 for byte in raw[1:-1]):
        raise ValueError("Versão de mídia inválida.")
    revision=sum((byte & 127) << (7*i) for i,byte in enumerate(raw[1:]))
    if revision <= 0 or revision >= 2**64:
        raise ValueError("Versão de mídia inválida.")
    return revision


class MediaAbsent(ValueError):
    """A resposta não traz a mídia pedida (atraso do Flow ou geração perdida)."""


def video_record(rpc, payload, media_id=None):
    """O decoder fixado aceita só CAE; edições/extensões têm novas revisões.

    Com media_id, considera só a linha dessa mídia: respostas podem aninhar
    registros de quadros/referências com o mesmo formato.
    """
    from gflow_cli.api.transports.batchexecute import generation_record, _walk_lists

    rows = [r for r in _walk_lists(payload) if len(r) >= 6
            and all(isinstance(r[i], str) for i in range(3)) and (r[3] is None or isinstance(r[3], str))]
    if media_id is not None:
        rows = [r for r in rows if _base_media_id(r[0]) == _base_media_id(media_id)]
        if not rows:
            raise MediaAbsent("Mídia esperada ausente da resposta.")
    if not rows:
        return generation_record(rpc, payload)
    if len(rows) != 1:
        raise ValueError("Registro de vídeo não identificado de forma única.")
    row = list(rows[0])
    media_revision(row[3])
    for i in range(3):
        media_uuid(row[i])
    media_id = row[0]
    row[0] = _base_media_id(row[0])
    row[3] = "CAE"
    from dataclasses import replace

    record = generation_record(rpc, row)
    # O frontend define nome da mídia no campo 1 e workflow no campo 3.
    # O decoder da release fixada inverte esses dois nomes para vídeos.
    return replace(record, media_id=media_id, workflow_id=row[2])


def payload_shape(value, depth=0):
    """Estrutura sem conteúdo (só tipos/tamanhos) para diagnosticar respostas novas."""
    if isinstance(value, list):
        return [payload_shape(v, depth + 1) for v in value[:12]] if depth < 8 else "list"
    if isinstance(value, str):
        try:
            media_uuid(value)
            return "uuid"
        except ValueError:
            return "url" if value.startswith("https://") else f"str{len(value)}"
    return value if value is None or isinstance(value, (bool, int, float)) else type(value).__name__


def image_download_url(payload, project_id, media_id):
    """URL original de imagem gerada, recortada ou upload, sem depender de prompt/semente."""
    from gflow_cli.api.transports.batchexecute import _walk_lists

    media_uuid(media_id)
    rows = [row for row in _walk_lists(payload) if len(row) >= 7
            and row[0] == media_id and row[1] == project_id and isinstance(row[6], list)]
    if len(rows) != 1:
        raise ValueError("Imagem não identificada de forma única neste projeto.")
    info = rows[0][6]
    url = None
    if isinstance(info, list):
        for field, index in [(info[0] if len(info) > 0 else None, 13),
                             (info[1] if len(info) > 1 else None, 3)]:
            if isinstance(field, list) and len(field) > index and isinstance(field[index], str) and field[index].startswith("https://"):
                url = field[index]
                break
    if not url:
        for item in _walk_lists(rows[0]):
            for val in item:
                if isinstance(val, str) and (val.startswith("https://lh3.googleusercontent.com/") or val.startswith("https://lh3.")):
                    url = val
                    break
            if url:
                break
    if not isinstance(url, str) or not url.startswith("https://"):
        raise ValueError("URL original da imagem indisponível.")
    return url



def parse_assets(payload, project_id: str, skipped: list | None = None) -> list[dict]:
    """Mídias do projeto na resposta Zzl0ze.

    Uma linha em formato desconhecido é ignorada (e descrita em `skipped`, se
    informado) em vez de derrubar a listagem inteira: mudanças do Flow numa mídia
    não devem impedir o uso das demais. O envelope inválido continua sendo erro.
    """
    if not isinstance(payload, list) or len(payload) < 8:  # Seções novas no fim não invalidam.
        raise ValueError("Resposta de mídia não reconhecida.")
    # Projeto vazio: o Flow omite as listas (null) desde 05/10/2026.
    payload = [*payload[:1], payload[1] or [], payload[2] or [], *payload[3:]]
    if not isinstance(payload[1], list) or not isinstance(payload[2], list):
        raise ValueError("Resposta de mídia não reconhecida.")
    names, collections, archived = {}, {}, set()
    for workflow in payload[1]:
        if isinstance(workflow, list) and len(workflow) >= 5 and workflow[4] == project_id:
            meta = workflow[3]
            if isinstance(meta, list) and meta and isinstance(meta[0], str):
                names[workflow[0]] = meta[0]
                if len(meta) > 2 and meta[2] is True:
                    archived.add(workflow[0])  # na lixeira
                # The Flow workflow resource uses field 2 for collection_id.
                collections[workflow[0]] = workflow[1] if isinstance(workflow[1], str) and workflow[1] else None
    # Cópias de imagem dos personagens (seção 5) não têm versão e não aparecem entre as mídias.
    character_refs = {row[4] for row in payload[5] or [] if isinstance(row, list) and len(row) > 4}
    # character_info = [imagens [[id], ...], vozes, personalidade].
    character_refs |= {ref[0] for row in payload[5] or [] if isinstance(row, list) and len(row) > 3
                       and isinstance(row[3], list) and len(row[3]) > 2 and isinstance(row[3][2], list)
                       and row[3][2] and isinstance(row[3][2][0], list)
                       for ref in row[3][2][0] if isinstance(ref, list) and ref}
    assets = []
    for row in payload[2]:
        try:
            asset = _parse_asset_row(row, project_id, payload, character_refs)
        except (ValueError, TypeError, IndexError) as exc:
            if skipped is not None:
                skipped.append({"media_id": row[0] if isinstance(row, list) and row and isinstance(row[0], str) else None,
                                "reason": str(exc) if isinstance(exc, ValueError) else type(exc).__name__})
            continue
        if asset is None:
            continue
        workflow_id, media_id = asset["workflow_id"], asset["media_id"]
        asset.update(project_id=project_id,
                     name=names.get(workflow_id, names.get(media_id)),
                     collection_id=collections.get(workflow_id), archived=workflow_id in archived)
        assets.append(asset)
    return assets


def _parse_asset_row(row, project_id, payload, character_refs):
    if not isinstance(row, list) or len(row) < 7 or row[1] != project_id:
        raise ValueError("Registro de mídia não reconhecido.")
    if row[0] in character_refs:
        return None  # cópias internas de personagem (retrato/corpo/miniatura)
    revision = media_revision(row[3])
    info = row[6]
    dimensionless_upscale = (
        isinstance(info, list) and len(info) == 1
        and isinstance(info[0], list) and len(info[0]) == 17
        and type(info[0][14]) is int and info[0][14] == 1
        and info[0][16] == [None, 1]
        and isinstance(info[0][13], str) and info[0][13].startswith("https://")
    )
    if isinstance(info, list) and (len(info) >= 3 or dimensionless_upscale):
        dims = None if dimensionless_upscale else info[2]
        if not dimensionless_upscale and (not isinstance(dims, list) or len(dims) != 2 or any(type(v) is not int or v <= 0 for v in dims)):
            raise ValueError("Dimensões de imagem não reconhecidas.")
        media_id, workflow_id = media_uuid(row[0]), media_uuid(row[2])
        asset = {"media_id": media_id, "workflow_id": workflow_id,
                 "kind": "image", "dimensions": dims}
    elif row[6] is None and len(row) >= 8 and isinstance(row[7], list):
        record = video_record("Zzl0ze", row)
        media_id, workflow_id = media_uuid(record.media_id), media_uuid(record.workflow_id)
        asset = {"media_id": media_id, "workflow_id": workflow_id,
                 "kind": "video", "status": record.status, "bytes": record.size_bytes}
    else:
        raise ValueError("Tipo de mídia não reconhecido.")
    asset["revision"] = revision
    return asset


async def project_media(page, project_id: str):
    from gflow_cli.api.transports.batchexecute import parse_frames

    found = asyncio.get_running_loop().create_future()

    async def observe(response):
        if found.done() or "batchexecute" not in response.url:
            return
        try:
            frames = parse_frames(await response.text())
        except Exception:
            return
        for rpc, payload in frames:
            if rpc == "Zzl0ze" and not found.done():
                found.set_result(payload)

    page.on("response", observe)
    try:
        await page.goto(f"https://flow.google.com/project/{project_id}",
                        wait_until="domcontentloaded", timeout=45000)
        return await asyncio.wait_for(found, 30)
    finally:
        page.remove_listener("response", observe)


async def list_assets(account_id: str, project_id: str, query: str = "", kind: str | None = None,
                      min_bytes: int | None = None, max_bytes: int | None = None,
                      sort_by: str | None = None, sort_order: str = "asc",
                      limit: int | None = None) -> dict:
    from flow_http import FlowHTTP, http_operation

    validate_project(project_id)
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Pesquisa inválida.")
    if kind is not None and kind not in {"image", "video"}:
        raise ValueError("Tipo de mídia inválido.")
    client = FlowHTTP(account_id)
    try:
        return await http_operation(client, "assets", {
            "project_id": project_id, "query": query, "kind": kind,
            "min_bytes": min_bytes, "max_bytes": max_bytes,
            "sort_by": sort_by, "sort_order": sort_order, "limit": limit
        })
    finally:
        await client.close()


async def search_assets(account_id: str, query: str, kind: str | None = None,
                        limit: int = 100, *, client=None) -> dict:
    from datetime import datetime, timezone
    from flow_accounts import validate_account
    from flow_http import FlowHTTP
    from flow_projects import parse_projects

    validate_account(account_id)
    if not isinstance(query, str) or not query.strip() or len(query) > 200:
        raise ValueError("Informe uma pesquisa de até 200 caracteres.")
    if kind is not None and kind not in {"image", "video"}:
        raise ValueError("Tipo de mídia inválido.")
    if type(limit) is not int or not 1 <= limit <= 500:
        raise ValueError("limit deve estar entre 1 e 500.")
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")

    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        projects = parse_projects(await client.rpc("UpteDb"))
        results, failures = [], []
        assets_scanned = 0
        projects_scanned = 0
        needle = query.strip().casefold()
        truncated = False
        project_limit = 100
        selected_projects = projects["projects"][:project_limit]
        for project in selected_projects:
            projects_scanned += 1
            try:
                assets = parse_assets(
                    await client.rpc("Zzl0ze", project_id=project["project_id"]),
                    project["project_id"],
                )
            except Exception as exc:
                from flow_errors import error_fields

                failures.append({"project_id": project["project_id"], **error_fields(exc)})
                continue
            assets_scanned += len(assets)
            for asset in assets:
                if kind and asset["kind"] != kind:
                    continue
                if needle not in (asset.get("name") or "").casefold() and needle not in asset["media_id"].casefold():
                    continue
                results.append({**asset, "project_title": project["title"]})
                if len(results) > limit:
                    truncated = True
                    break
            if truncated:
                break

        results = results[:limit]
        project_limit_hit = len(projects["projects"]) > len(selected_projects)
        return {
            "account_id": account_id, "status": "ok", "query": query,
            "kind": kind, "results": results, "result_count": len(results),
            "assets_scanned": assets_scanned, "projects_scanned": projects_scanned,
            "projects_returned": len(projects["projects"]), "projects_complete": projects["complete"],
            "failed_projects": failures, "truncated": truncated or project_limit_hit,
            "complete": False,
            "source": "HTTP/UpteDb+Zzl0ze",
            "scope": "Respostas iniciais dos projetos; paginação de mídia não validada.",
            "observed_at": datetime.now(timezone.utc).isoformat(),
        }
    finally:
        if owned:
            await client.close()


async def delete_asset(account_id: str, project_id: str, media_id: str,
                       *, confirm_delete: bool = False, client=None) -> dict:
    """Move one project media workflow to the trash (native pGCYOe) after explicit confirmation."""
    from flow_accounts import validate_account
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    media_uuid(media_id)
    if confirm_delete is not True:
        return {"account_id": account_id, "project_id": project_id,
                "media_id": media_id, "status": "confirmation_required",
                "message": "Para arquivar, repita somente após autorização explícita do usuário e defina confirm_delete=true."}
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        asset = next((item for item in assets if item["media_id"] == media_id), None)
        if asset is None:
            return {"account_id": account_id, "project_id": project_id,
                    "media_id": media_id, "status": "not_found_in_project_listing"}
        workflow_id = media_uuid(asset["workflow_id"])
        submit_error = {}
        try:  # Pedido capturado em "Mover para a lixeira" na interface; nunca reenviar.
            await client.rpc("pGCYOe", params=[[[workflow_id, None, None, [None, None, 1], project_id]],
                                               [["metadata.archived"]]])
        except Exception as exc:
            from flow_errors import error_fields

            submit_error = error_fields(exc, "submit_")
        import asyncio

        for attempt in range(6):
            if attempt:
                await asyncio.sleep(2)
            remaining = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
            if any(item["media_id"] == media_id and item["archived"] for item in remaining):
                break
        else:
            return {"account_id": account_id, "project_id": project_id, "media_id": media_id,
                    "workflow_id": workflow_id, "status": "submission_unknown", **submit_error,
                    "message": "Arquivamento não confirmado por leitura; confira o projeto antes de repetir."}
        return {"account_id": account_id, "project_id": project_id, "media_id": media_id,
                "workflow_id": workflow_id, "kind": asset["kind"], "status": "archived"}
    finally:
        if owned:
            await client.close()


async def upload_image(account_id: str, project_id: str, path: str, *, client=None) -> dict:
    from gflow_cli.api.client import validate_image_file
    from gflow_cli.api.transports.migrated_composer import _unique_display_name
    from flow_accounts import validate_account
    from flow_requests import upload_request
    from flow_http import FlowHTTP
    from gflow_cli.api.transports.batchexecute import _walk_lists
    import mimetypes

    validate_account(account_id)
    validate_project(project_id)
    source = Path(path).resolve(strict=True)
    await validate_image_file(source)
    name = _unique_display_name(source)
    body = await asyncio.to_thread(source.read_bytes)
    mime = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        captcha = await client.prepare("Zzl0ze", project_id=project_id, captcha_action="UPLOAD_IMAGE")
        packet = upload_request(project_id, body, mime, name, captcha)
        captured = client.request(packet["rpc_id"], packet["params"])
        try:
            reply = await client.send_submit(captured)
            # maseQ contém o registro em um envelope; não tratar o envelope como mídia.
            rows = [row for row in _walk_lists(reply) if len(row) >= 4 and row[1] == project_id
                    and isinstance(row[0], str) and row[0] != project_id]
            if len(rows) != 1:
                raise ValueError("Resposta de upload não reconhecida.")
            media_id = media_uuid(rows[0][0])
            workflow_id = media_uuid(rows[0][2])
            media_revision(rows[0][3])
            if media_id != packet["request_media_ids"][0] or workflow_id != packet["request_workflow_ids"][0]:
                raise ValueError("Upload pertence a outro pedido.")
        except Exception as exc:
            from flow_errors import error_fields

            return {"account_id": account_id, "project_id": project_id, "name": name,
                    "status": "submission_unknown", "source": "HTTP/maseQ", **error_fields(exc),
                    "request_media_ids": packet["request_media_ids"],
                    "request_workflow_ids": packet["request_workflow_ids"],
                    "message": "Upload inconclusivo; confira o projeto antes de tentar novamente."}
        return {"account_id": account_id, "project_id": project_id, "media_id": media_id,
                "name": name, "status": "uploaded", "kind": "image", "source": "HTTP/maseQ"}
    finally:
        if owned:
            await client.close()


async def upload_asset(account_id: str, project_id: str, path: str, *, client=None) -> dict:
    """Upload de imagem por maseQ; vídeo pela interface normal de upload do Flow."""
    from flow_accounts import validate_account
    from flow_browser import FlowBrowser
    from flow_http import FlowHTTP
    from gflow_cli.api.transports.migrated_composer import TOOLBAR_ADD, UPLOAD_MENU_ITEM
    import secrets

    validate_account(account_id)
    validate_project(project_id)
    source = Path(path).resolve(strict=True)
    if source.suffix.lower() not in {".mp4", ".mov", ".avi", ".wmv"}:
        return await upload_image(account_id, project_id, path, client=client)
    if not source.is_file() or not 0 < source.stat().st_size <= 1_000_000_000:
        raise ValueError("Vídeo vazio ou acima de 1 GB.")
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.pending_upload is not None:
        raise ValueError("Há uma confirmação de upload pendente nesta conta.")
    browser = client.browser or FlowBrowser(account_id)
    page_context = browser.page()
    keep_page = False
    try:
        before = {asset["media_id"] for asset in parse_assets(
            await client.rpc("Zzl0ze", project_id=project_id), project_id)}
        page = await page_context.__aenter__()
        try:
            await page.goto(f"https://flow.google.com/project/{project_id}", wait_until="domcontentloaded", timeout=45000)
            await page.locator(TOOLBAR_ADD).first.click(timeout=10000)
            async with page.expect_file_chooser(timeout=10000) as chooser_info:
                await page.locator(UPLOAD_MENU_ITEM).first.click(timeout=5000)
            chooser = await chooser_info.value
            await chooser.set_files(str(source))  # Uma entrega ao site; nunca repetir automaticamente.
            try:
                for _ in range(120):
                    dialogs = await page.locator("[role=dialog]").all_inner_texts()
                    if dialogs:
                        rights = any("direitos de uso" in text.casefold() or "rights to use" in text.casefold()
                                     for text in dialogs)
                        if rights and client.browser is browser:
                            confirmation_id = secrets.token_urlsafe(24)
                            client.pending_upload = {"confirmation_id": confirmation_id,
                                "page_context": page_context, "page": page, "project_id": project_id,
                                "name": source.name, "before": before}
                            keep_page = True
                            return {"account_id": account_id, "project_id": project_id, "kind": "video",
                                    "name": source.name, "status": "confirmation_required",
                                    "confirmation_id": confirmation_id,
                                    "message": "Peça ao titular autorização explícita para confirmar os direitos deste vídeo; depois chame flow_confirm_upload."}
                        return {"account_id": account_id, "project_id": project_id, "kind": "video",
                                "status": "requires_manual_confirmation" if rights else "submission_unknown",
                                "message": "Confirme os direitos do vídeo pessoalmente no Flow antes de novo upload."
                                           if rights else "Diálogo do Flow interrompeu o upload; confira o projeto."}
                    result = await _uploaded_video(client, project_id, source.name, before)
                    if result is not None:
                        return {"account_id": account_id, "project_id": project_id, **result}
                    await asyncio.sleep(3)
                observed = {}
            except Exception as exc:
                from flow_errors import error_fields

                observed = error_fields(exc)  # Após escolher o arquivo, qualquer falha de observação é incerta.
        finally:
            if not keep_page:
                await page_context.__aexit__(None, None, None)
        return {"account_id": account_id, "project_id": project_id, "kind": "video", **observed,
                "status": "submission_unknown", "message": "Upload inconclusivo; confira o projeto antes de tentar novamente."}
    finally:
        if browser is not client.browser:
            await browser.close()
        if owned:
            await client.close()


async def _uploaded_video(client, project_id, name, before):
    try:
        assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
    except ValueError:
        return None  # Processamento remoto pode deixar a listagem incompleta.
    matches = [asset for asset in assets if asset["media_id"] not in before
               and asset["kind"] == "video" and asset.get("name") in {name, Path(name).stem}]
    if len(matches) == 1:
        return {"media_id": matches[0]["media_id"], "name": name,
                "kind": "video", "status": "uploaded", "source": "Flow/UI"}
    if len(matches) > 1:
        return {"kind": "video", "status": "submission_unknown",
                "message": "Upload não identificado de forma única; confira o projeto."}
    return None


async def confirm_video_upload(account_id: str, confirmation_id: str, approve: bool, *, client) -> dict:
    """Consumir uma pendência de direitos sem reapresentar o arquivo ao navegador."""
    import re
    import secrets
    from flow_accounts import validate_account

    validate_account(account_id)
    if client.account_id != account_id or type(approve) is not bool or not isinstance(confirmation_id, str):
        raise ValueError("Confirmação de upload inválida.")
    pending = client.pending_upload
    if pending is None or not secrets.compare_digest(pending["confirmation_id"], confirmation_id):
        raise ValueError("Confirmação de upload ausente ou expirada.")
    client.pending_upload = None
    project_id, page = pending["project_id"], pending["page"]
    try:
        if not approve:
            return {"account_id": account_id, "project_id": project_id, "kind": "video",
                    "status": "cancelled", "message": "Aviso recusado; vídeo não enviado."}
        dialogs = await page.locator("[role=dialog]").all_inner_texts()
        if not any("direitos de uso" in text.casefold() or "rights to use" in text.casefold()
                   for text in dialogs):
            raise ValueError("Aviso de direitos não está mais aberto.")
        await page.get_by_role("button", name=re.compile(r"^(Concordo|I agree|Agree)$", re.I)).click(timeout=5000)
        for _ in range(120):
            result = await _uploaded_video(client, project_id, pending["name"], pending["before"])
            if result is not None:
                return {"account_id": account_id, "project_id": project_id, **result}
            await asyncio.sleep(3)
    except Exception:
        pass  # Depois do clique, não há reenvio automático.
    finally:
        await pending["page_context"].__aexit__(None, None, None)
    return {"account_id": account_id, "project_id": project_id, "kind": "video",
            "status": "submission_unknown", "message": "Confirmação inconclusiva; confira o projeto antes de tentar novamente."}


async def download_asset(account_id: str, project_id: str, media_id: str) -> dict:
    from flow_http import FlowHTTP, http_operation

    validate_project(project_id)
    media_uuid(media_id)
    client = FlowHTTP(account_id)
    try:
        return await http_operation(client, "download_asset", {"project_id":project_id, "media_id":media_id})
    finally:
        await client.close()
