"""Operações HTTP nativas de coleções do Flow."""

import re
import uuid

from flow_projects import validate_project


def validate_collection_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", value):
        raise ValueError("Coleção inválida.")
    return value


def _collection(payload, collection_id: str, title: str) -> bool:
    return (isinstance(payload, list) and len(payload) >= 3 and payload[0] == collection_id
            and isinstance(payload[2], list) and payload[2]
            and payload[2][0] == title)


def parse_collections(payload, project_id: str) -> list[dict]:
    """Coleções, inclusive vazias, da primeira resposta Zzl0ze do projeto."""
    if not isinstance(payload, list) or len(payload) != 8 or not isinstance(payload[0], list):
        raise ValueError("Resposta de coleções não reconhecida.")
    result, seen = [], set()
    for row in payload[0]:
        if (not isinstance(row, list) or len(row) < 4 or row[3] != project_id
                or not isinstance(row[2], list) or not row[2]
                or not isinstance(row[2][0], str) or not row[2][0].strip()):
            raise ValueError("Registro de coleção não reconhecido.")
        collection_id = validate_collection_id(row[0])
        parent = validate_collection_id(row[1]) if row[1] is not None else None
        if collection_id in seen:
            raise ValueError("Coleção duplicada na resposta do projeto.")
        seen.add(collection_id)
        result.append({"collection_id": collection_id, "parent_collection_id": parent,
                       "title": row[2][0], "project_id": project_id})
    return result


async def _read_collection(client, project_id: str, collection_id: str, title: str) -> bool:
    try:
        rows = parse_collections(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        return any(row["collection_id"] == collection_id and row["title"] == title for row in rows)
    except Exception:
        return False


async def collection_operation(account_id: str, project_id: str, title: str,
                               collection_id: str | None = None,
                               parent_collection_id: str | None = None, *, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ValueError("Informe um título de até 200 caracteres.")
    if collection_id is not None:
        collection_id = validate_collection_id(collection_id)
    if parent_collection_id is not None:
        parent_collection_id = validate_collection_id(parent_collection_id)
    if collection_id is not None and parent_collection_id is not None:
        raise ValueError("Renomeação não aceita parent_collection_id.")

    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")

    try:
        if collection_id is None:
            collection_id = str(uuid.uuid4())
            params = [f"projects/{project_id}",
                      [collection_id, parent_collection_id, ["Untitled collection"], project_id]]
            try:
                created = await client.rpc("Uxbujd", params=params)
            except Exception:
                created = None
            if (not _collection(created, collection_id, "Untitled collection")
                    and not await _read_collection(client, project_id, collection_id, "Untitled collection")):
                return {"account_id": account_id, "project_id": project_id,
                        "collection_id": collection_id, "status": "submission_unknown",
                        "source": "HTTP/Uxbujd", "title": title}
            if title == "Untitled collection":
                return {"account_id": account_id, "project_id": project_id,
                        "collection_id": collection_id,
                        "parent_collection_id": parent_collection_id, "title": title,
                        "status": "ok", "source": "HTTP/Uxbujd"}
            else:
                rpc = "O2COMe"
                params = [[collection_id, parent_collection_id, [title], project_id],
                          [["metadata.display_name"]]]
        else:
            rpc = "O2COMe"
            params = [[collection_id, None, [title], project_id], [["metadata.display_name"]]]

        try:
            updated = await client.rpc(rpc, params=params)
        except Exception:
            updated = None
        if (not _collection(updated, collection_id, title)
                and not await _read_collection(client, project_id, collection_id, title)):
            return {"account_id": account_id, "project_id": project_id,
                    "collection_id": collection_id, "status": "submission_unknown",
                    "source": f"HTTP/{rpc}", "title": title,
                    "message": "A resposta não confirmou o título; nenhum reenvio foi feito."}
        return {"account_id": account_id, "project_id": project_id,
                "collection_id": collection_id, "parent_collection_id": parent_collection_id,
                "title": title, "status": "ok", "source": f"HTTP/{rpc}"}
    finally:
        if owned:
            await client.close()


async def move_assets(account_id: str, project_id: str, asset_ids: list[str],
                      collection_id: str | None, *, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_assets import media_uuid, parse_assets
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    if not isinstance(asset_ids, list) or not asset_ids or len(asset_ids) > 100:
        raise ValueError("Informe de 1 a 100 IDs de ativos.")
    asset_ids = [media_uuid(asset_id) for asset_id in asset_ids]
    if len(set(asset_ids)) != len(asset_ids):
        raise ValueError("A lista contém IDs de ativos repetidos.")
    if collection_id is not None:
        collection_id = validate_collection_id(collection_id)

    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")

    try:
        assets = parse_assets(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        by_id = {asset["media_id"]: asset for asset in assets}
        if any(asset_id not in by_id for asset_id in asset_ids):
            raise ValueError("Todos os ativos precisam pertencer ao projeto informado.")
        workflows = [by_id[asset_id].get("workflow_id") for asset_id in asset_ids]
        if any(not isinstance(workflow, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", workflow)
               for workflow in workflows):
            raise ValueError("A resposta do Flow não contém workflows reconhecíveis para todos os ativos.")

        params = [project_id, [collection_id] if collection_id is not None else None,
                  workflows, [], None, [] if collection_id is None else None, [], []]
        try:
            await client.rpc("kVdhHf", params=params)
        except Exception:
            status = "submission_unknown"
        else:
            status = "submitted"
        unconfirmed = list(asset_ids)
        try:
            observed = await client.rpc("Zzl0ze", project_id=project_id)
            current = {asset["media_id"]: asset for asset in parse_assets(observed, project_id)}
            # Exigir o workflow explícito: metadados ausentes não provam movimento à raiz.
            associations = {}
            for row in observed[1]:
                if (isinstance(row, list) and len(row) >= 5
                        and isinstance(row[0], str) and row[4] == project_id):
                    if row[0] in associations:
                        raise ValueError("Workflow duplicado na leitura do projeto.")
                    associations[row[0]] = row[1]
            unconfirmed = [asset_id for asset_id, workflow in zip(asset_ids, workflows)
                           if asset_id not in current
                           or current[asset_id].get("workflow_id") != workflow
                           or workflow not in associations
                           or associations[workflow] != collection_id]
        except Exception:
            pass
        verified = not unconfirmed
        return {"account_id": account_id, "project_id": project_id,
                "collection_id": collection_id, "asset_ids": asset_ids,
                "status": "ok" if verified else status, "source": "HTTP/kVdhHf",
                "verified": verified, "unconfirmed_asset_ids": unconfirmed,
                "message": ("Associação confirmada por leitura do projeto." if verified else
                            "Associação não confirmada; confira o Flow antes de tentar novamente. Nenhum reenvio foi feito.")}
    finally:
        if owned:
            await client.close()
