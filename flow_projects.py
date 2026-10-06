"""Projetos no host atual, com confirmação HTTP da resposta do próprio Flow."""

from datetime import datetime, timezone
import asyncio
import re
from flow_browser import account_page
from flow_errors import error_fields


def validate_project(project_id: str) -> str:
    # IDs legados do Flow podem terminar em _backfill; o identificador é opaco.
    if not isinstance(project_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", project_id):
        raise ValueError(f"Projeto inválido ({str(project_id)[:80]!r}); use um project_id de flow_list_projects.")
    return project_id


def parse_projects(payload) -> dict:
    """UpteDb: lista de pares ID/metadados; somente ID e título saem.

    Conta sem projetos pode vir com a lista nula; linhas em formato desconhecido
    são ignoradas para não esconder os demais projetos.
    """
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], (list, type(None))):
        raise ValueError("Resposta de projetos não reconhecida.")
    projects = []
    for row in payload[0] or []:
        try:
            project_id = validate_project(row[0])
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        meta = row[1] if len(row) > 1 and isinstance(row[1], list) else []
        projects.append({"project_id": project_id,
                         "title": meta[0] if meta and isinstance(meta[0], str) else None})
    # Campo adicional pode representar paginação: nunca anunciar lista completa.
    return {"projects": projects, "complete": len(payload) == 1}


async def list_projects(account_id: str) -> dict:
    from gflow_cli.api.transports.batchexecute import parse_frames

    async with account_page(account_id) as page:
        found = asyncio.get_running_loop().create_future()

        async def observe(response):
            if found.done() or "batchexecute" not in response.url:
                return
            try:
                frames = parse_frames(await response.text())
            except Exception:
                return  # Respostas abortadas de outras consultas não são listagens.
            for rpc, payload in frames:
                if rpc == "UpteDb" and not found.done():
                    try:
                        found.set_result(parse_projects(payload))
                    except ValueError:
                        found.set_exception(ValueError("Consulta de projetos inconclusiva."))

        page.on("response", observe)
        try:
            await page.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=45000)
            result = await asyncio.wait_for(found, 30)
        finally:
            page.remove_listener("response", observe)
    return {"account_id": account_id, "status": "ok", "source": "flow.google.com/UpteDb",
            "observed_at": datetime.now(timezone.utc).isoformat(), **result}


async def project_operation(account_id: str, title: str, project_id: str | None = None, *, client=None) -> dict:
    from flow_http import FlowHTTP
    from flow_assets import media_uuid
    from flow_accounts import validate_account

    validate_account(account_id)
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("Informe um título de até 200 caracteres.")
    if project_id is not None:
        validate_project(project_id)
    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)
    try:
        # A página de preparo fecha antes dos RPCs; contexto residente pode continuar ativo.
        await client.prepare("UpteDb")
        if project_id is None:
            rpc, params = "jHPbke", ["projects/*", [None, [title]], [None, 22]]
        else:
            data = await client.rpc("ngNC2", params=[f"tools/PINHOLE/projects/{project_id}"])
            if (not isinstance(data, list) or len(data) < 2 or data[0] != project_id
                    or not isinstance(data[1], list) or not data[1] or not isinstance(data[1][0], str)):
                raise ValueError("Metadados do projeto não reconhecidos; renomeação não enviada.")
            cover = data[1][1] if len(data[1]) > 1 else None
            if cover is not None:
                media_uuid(cover)
            rpc, params = "o8DA4", [f"projects/{project_id}", [title, cover], [["project_title"]], [None, 22]]
        try:
            reply = await client.rpc(rpc, params=params)
            if rpc == "jHPbke":
                if not isinstance(reply, list) or len(reply) < 2 or not isinstance(reply[1], list):
                    raise ValueError("Resposta de criação não reconhecida.")
                project_id = validate_project(reply[0])
                echoed = reply[1][0] if reply[1] else None
            else:
                echoed = reply[0] if isinstance(reply, list) and reply else None
            if echoed != title:
                raise ValueError("Título não confirmado pelo Flow.")
        except Exception:
            return {"account_id": account_id, "project_id": project_id, "status": "submission_unknown",
                    "source": f"HTTP/{rpc}", "requested_title": title,
                    "message": "Alteração inconclusiva; consulte os projetos antes de tentar novamente."}
        return {"account_id": account_id, "project_id": project_id, "title": title,
                "status": "ok", "source": f"HTTP/{rpc}"}
    finally:
        if owned:
            await client.close()


async def delete_project(account_id: str, project_id: str, *, confirm_delete: bool = False, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    if confirm_delete is not True:
        return {"account_id": account_id, "project_id": project_id,
                "status": "confirmation_required",
                "message": "Para excluir, repita somente após autorização explícita do usuário e defina confirm_delete=true."}
    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        before = parse_projects(await client.rpc("UpteDb"))
        project = next((item for item in before["projects"] if item["project_id"] == project_id), None)
        if project is None:
            return {"account_id": account_id, "project_id": project_id,
                    "status": "not_found_in_project_listing", "complete": before["complete"]}
        submit_error = {}
        try:
            await client.rpc("QI2zvc", params=[f"projects/{project_id}"])
        except Exception as exc:
            submit_error = error_fields(exc, "submit_")  # Reconcile by reading; never resend an uncertain deletion.
        try:
            after = parse_projects(await client.rpc("UpteDb"))
        except Exception:
            after = {"projects": [], "complete": False}
        if after["complete"] and not any(item["project_id"] == project_id for item in after["projects"]):
            return {"account_id": account_id, "project_id": project_id, "title": project["title"],
                    "status": "deleted", "source": "HTTP/QI2zvc+UpteDb"}
        return {"account_id": account_id, "project_id": project_id, "title": project["title"],
                "status": "submission_unknown", **submit_error,
                "message": "Exclusão inconclusiva; confira os projetos antes de repetir. Nenhum reenvio automático foi feito."}
    finally:
        if owned:
            await client.close()


async def download_project(account_id: str, project_id: str, output_dir: str | None = None,
                           kind: str | None = None, query: str = "",
                           collection_id: str | None = None, recursive: bool = False, *, client=None) -> dict:
    """Baixa todos os ativos de um projeto para um diretório local com suporte a filtros."""
    from pathlib import Path
    import shutil
    from flow_http import FlowHTTP, http_operation
    from flow_accounts import validate_account
    from flow_collections import validate_collection_id

    validate_account(account_id)
    validate_project(project_id)
    if kind is not None and kind not in {"image", "video"}:
        raise ValueError("Tipo de mídia inválido. Use 'image' ou 'video'.")
    if collection_id is not None:
        collection_id = validate_collection_id(collection_id)
    if type(recursive) is not bool or (recursive and collection_id is None):
        raise ValueError("recursive exige uma coleção.")
    if output_dir is not None and (not isinstance(output_dir, str) or not output_dir.strip()):
        raise ValueError("Diretório de saída inválido.")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Pesquisa inválida.")

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        selected_collections = {collection_id} if collection_id else set()
        if recursive:
            listing = await http_operation(client, "collections", {"project_id": project_id})
            rows = listing["collections"]
            if not any(row["collection_id"] == collection_id for row in rows):
                raise ValueError("Coleção não encontrada na primeira resposta do projeto.")
            while True:
                children = {row["collection_id"] for row in rows
                            if row["parent_collection_id"] in selected_collections}
                expanded = selected_collections | children
                if expanded == selected_collections:
                    break
                selected_collections = expanded
        assets_res = await http_operation(client, "assets", {
            "project_id": project_id, "kind": kind, "query": query,
            "collection_id": None if recursive else collection_id,
        })
        assets = assets_res.get("assets", [])
        if recursive:
            assets = [asset for asset in assets
                      if asset.get("collection_id") in selected_collections]

        if output_dir:
            target_dir = Path(output_dir).resolve()
        else:
            from flow_video import downloads_dir

            base_output = downloads_dir()
            target_dir = base_output / (f"collection_{collection_id}" if collection_id else f"project_{project_id}")
        target_dir.mkdir(parents=True, exist_ok=True)

        downloaded = []
        failed = []

        for item in assets:
            mid = item["media_id"]
            try:
                dl = await http_operation(client, "download_asset", {"project_id": project_id, "media_id": mid})
                src_path = Path(dl["path"])
                dest_path = target_dir / src_path.name
                if src_path != dest_path:
                    shutil.copy2(src_path, dest_path)
                downloaded.append({
                    "media_id": mid,
                    "kind": item.get("kind"),
                    "name": item.get("name"),
                    "path": str(dest_path),
                    "bytes": dl.get("bytes", dest_path.stat().st_size)
                })
            except Exception as exc:
                failed.append({
                    "media_id": mid,
                    "name": item.get("name"),
                    **error_fields(exc)
                })

        return {
            "account_id": account_id,
            "project_id": project_id,
            "collection_id": collection_id,
            "recursive": recursive,
            "collection_ids": sorted(selected_collections) if collection_id else [],
            "complete": False if recursive else assets_res.get("complete", False),
            "output_dir": str(target_dir),
            "total_assets": len(assets),
            "downloaded_count": len(downloaded),
            "failed_count": len(failed),
            "total_bytes": sum(a["bytes"] for a in downloaded),
            "assets": downloaded,
            "failed": failed,
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        if owned:
            await client.close()


async def project_summary(account_id: str, project_id: str, *, client=None) -> dict:
    """Gera resumo estruturado de um projeto e seus ativos."""
    from flow_http import FlowHTTP, http_operation
    from flow_accounts import validate_account

    validate_account(account_id)
    validate_project(project_id)

    owned = client is None
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    client = client or FlowHTTP(account_id)

    try:
        projects_res = await http_operation(client, "projects", {})
        title = next((p["title"] for p in projects_res.get("projects", []) if p["project_id"] == project_id), None)

        assets_res = await http_operation(client, "assets", {"project_id": project_id})
        assets = assets_res.get("assets", [])

        images = [a for a in assets if a.get("kind") == "image"]
        videos = [a for a in assets if a.get("kind") == "video"]
        total_bytes = sum((a.get("bytes") or 0) for a in videos)

        return {
            "account_id": account_id,
            "project_id": project_id,
            "title": title or "Projeto sem título",
            "total_assets": len(assets),
            "image_count": len(images),
            "video_count": len(videos),
            "total_video_bytes": total_bytes,
            "asset_names": [a.get("name") for a in assets if a.get("name")],
            "status": "ok",
            "observed_at": datetime.now(timezone.utc).isoformat()
        }
    finally:
        if owned:
            await client.close()
