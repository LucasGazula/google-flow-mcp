"""Gestão de personagens e referências visuais no projeto Flow."""

from flow_accounts import validate_account
from flow_projects import validate_project


def list_voice_presets() -> dict:
    from gflow_cli.api.character import VOICES

    return {"status": "catalog_only", "source": "gflow-cli==0.79.1",
            "verified_for_account": False,
            "voices": [{"name": voice.name, "description": voice.description} for voice in VOICES]}


def parse_characters(payload, project_id):
    """Personagens da sexta seção de Zzl0ze: [projeto, id, _, [1, nome, refs], capa, dimensões, ...]."""
    from flow_assets import media_uuid

    if not isinstance(payload, list) or len(payload) != 8:
        raise ValueError("Resposta de personagens não reconhecida.")
    characters = []
    for row in payload[5] or []:
        if (not isinstance(row, list) or len(row) < 5 or row[0] != project_id
                or not isinstance(row[3], list) or len(row[3]) < 2 or not isinstance(row[3][1], str)):
            raise ValueError("Personagem não reconhecido.")
        # character_info: [imagens [[id], ...], vozes [[_, preset]], personalidade].
        info = row[3][2] if len(row[3]) > 2 and isinstance(row[3][2], list) else []
        info = info + [None] * (3 - len(info))
        voices = info[1] if isinstance(info[1], list) else []
        # Posicional: [retrato, corpo]; slot vazio vem como [].
        slots = [media_uuid(ref[0]) if ref else None for ref in info[0] or []]
        slots += [None] * (2 - len(slots))
        characters.append({"entity_id":media_uuid(row[1]), "project_id":project_id,
                           "display_name":row[3][1],
                           "reference_media_ids":[slot for slot in slots if slot],
                           "portrait_media_id":slots[0], "body_media_id":slots[1],
                           "voice":voices[0][1] if voices and isinstance(voices[0], list) and len(voices[0]) > 1 else None,
                           "personality":info[2] if isinstance(info[2], str) else None,
                           "thumbnail_media_id":media_uuid(row[4]) if row[4] else None})
    return characters


def _validate_name(value: str | None) -> None:
    if value is not None and (not isinstance(value, str) or not value.strip() or len(value) > 100):
        raise ValueError("O nome do personagem deve ter de 1 a 100 caracteres.")


async def list_characters(account_id: str, project_id: str, *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        characters = parse_characters(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        return {"account_id": account_id, "project_id": project_id, "status": "ok",
                "source": "HTTP/Zzl0ze", "characters": characters, "complete": False}
    finally:
        if owned:
            await client.close()


async def _read_until(client, project_id, done):
    """Repete apenas leituras: a listagem do projeto pode atrasar alguns segundos."""
    import asyncio

    for attempt in range(6):
        if attempt:
            await asyncio.sleep(2)
        characters = parse_characters(await client.rpc("Zzl0ze", project_id=project_id), project_id)
        found = done(characters)
        if found:
            return found
    return None


async def manage_character(account_id: str, project_id: str, operation: str,
                           *, entity_id: str | None = None,
                           display_name: str | None = None,
                           image_media_id: str | None = None,
                           voice: str | None = None,
                           personality: str | None = None,
                           slot: str = "portrait",
                           description: str | None = None,
                           max_credits: int | None = None,
                           confirm_delete: bool = False,
                           client=None) -> dict:
    """Create from a project image, update name/voice/personality, set a portrait/body image, or delete a character."""
    from uuid import uuid4

    from flow_assets import media_uuid, parse_assets
    from flow_http import FlowHTTP
    from flow_requests import _seed
    from flow_video import save_job

    validate_account(account_id)
    validate_project(project_id)
    if operation == "rename":
        operation = "update"
    if operation not in {"create", "update", "delete", "set_image", "remove_image"}:
        raise ValueError("Operação de personagem inválida: use create, update, set_image, remove_image ou delete.")
    if slot not in {"portrait", "body"}:
        raise ValueError("slot deve ser portrait ou body.")
    _validate_name(display_name)
    if voice is not None:
        from gflow_cli.api.character import VOICE_NAMES

        voice = next((name.lower() for name in VOICE_NAMES if isinstance(voice, str)
                      and name.casefold() == voice.casefold()), None)
        if voice is None:
            raise ValueError("Voz desconhecida; consulte flow_list_voice_presets.")
    if personality is not None and (not isinstance(personality, str) or len(personality) > 2000):
        raise ValueError("A personalidade deve ter até 2.000 caracteres.")
    if operation == "create":
        if display_name is None:
            raise ValueError("Criação exige display_name.")
        if (image_media_id is None) == (description is None):
            raise ValueError("Informe image_media_id ou description (não ambos).")
        if image_media_id is not None:
            media_uuid(image_media_id)
        elif (not isinstance(description, str) or not description.strip() or len(description) > 4000
              or type(max_credits) is not int or max_credits < 0):
            raise ValueError("description exige texto de até 4000 caracteres e max_credits inteiro.")
    elif description is not None and operation != "set_image":
        raise ValueError("description só é usada na criação e em set_image.")
    else:
        media_uuid(entity_id)
        if operation == "set_image":
            if (image_media_id is None) == (description is None):
                raise ValueError("Informe image_media_id ou description (não ambos).")
            if image_media_id is not None:
                media_uuid(image_media_id)
            elif (not isinstance(description, str) or not description.strip() or len(description) > 4000
                  or type(max_credits) is not int or max_credits < 0):
                raise ValueError("description exige texto de até 4000 caracteres e max_credits inteiro.")
        elif image_media_id is not None:
            raise ValueError("image_media_id só é usado em create e set_image.")
    if operation == "update" and display_name is None and voice is None and personality is None:
        raise ValueError("Informe display_name, voice ou personality.")
    if operation != "update" and (voice is not None or personality is not None):
        raise ValueError("voice e personality são alterados com operation=update.")
    if operation == "delete" and confirm_delete is not True:
        return {"account_id": account_id, "project_id": project_id, "entity_id": entity_id,
                "status": "confirmation_required",
                "message": "Para excluir, repita somente após autorização explícita do usuário e defina confirm_delete=true."}

    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    job = {"job_id":str(uuid4()), "account_id":account_id, "project_id":project_id,
           "kind":f"character_{operation}", "status":"preparing", "entity_id":entity_id, "files":[]}
    save_job(job)
    try:
        payload = await client.rpc("Zzl0ze", project_id=project_id)
        before = parse_characters(payload, project_id)
        if operation != "create" and not any(c["entity_id"] == entity_id for c in before):
            raise ValueError("Personagem ausente deste projeto.")
        if image_media_id is not None and not any(
                a["media_id"] == image_media_id and a["kind"] == "image" for a in parse_assets(payload, project_id)):
            raise ValueError("Imagem ausente deste projeto.")
        if operation == "remove_image" and not next(
                c for c in before if c["entity_id"] == entity_id)["body_media_id" if slot == "body" else "portrait_media_id"]:
            raise ValueError("O slot do personagem já está vazio.")
        job["status"] = "submitting"
        save_job(job)
        if operation == "update":
            # Pedidos capturados no editor do personagem; campos combinados numa máscara.
            masks = [path for path, value in (("entity_info.display_name", display_name),
                     ("entity_info.character_info.audio_references", voice),
                     ("entity_info.character_info.personality_notes", personality)) if value is not None]
            entity_info = [1, display_name]
            if voice is not None or personality is not None:
                character_info = [None, [[None, voice]] if voice else None, personality]
                while character_info[-1] is None:
                    character_info.pop()
                entity_info.append(character_info)
            rpc, params = "rzMKMb", [[project_id, entity_id, None, entity_info], [masks]]
            done = lambda chars: next((c for c in chars if c["entity_id"] == entity_id
                                       and (display_name is None or c["display_name"] == display_name)
                                       and (voice is None or c["voice"] == voice)
                                       and (personality is None or c["personality"] == personality)), None)
        elif operation in {"set_image", "remove_image"}:
            index, key = (1, "body_media_id") if slot == "body" else (0, "portrait_media_id")
            current = next(c for c in before if c["entity_id"] == entity_id)
            if current[key]:
                # Slot ocupado rejeita nova imagem: limpa antes (pedido capturado em "Excluir imagem").
                images = [[c] if c else [] for c in (current["portrait_media_id"], current["body_media_id"])]
                images[index] = []
                try:
                    await client.rpc("rzMKMb", params=[[project_id, entity_id, None, [1, None, [images]]],
                                                       [["entity_info.character_info.image_references"]]])
                except Exception:
                    pass
                if not await _read_until(client, project_id, lambda chars: next(
                        (c for c in chars if c["entity_id"] == entity_id and not c[key]), None)):
                    raise ValueError("Remoção da imagem não confirmada por leitura.")
            if operation == "remove_image" or description is not None:
                rpc = None
                done = lambda chars: next((c for c in chars if c["entity_id"] == entity_id), None)
            else:
                # Pedido capturado em "Adicionar do projeto": [entidade, [0 retrato | 1 corpo]].
                workflow_seed, _ = _seed()
                media_seed, _ = _seed()
                rpc = "Sc7aEb"
                params = [image_media_id, None, None, project_id, None, None, None,
                          [None, None, [entity_id, [index]]], None, workflow_seed, media_seed]
                done = lambda chars: next((c for c in chars if c["entity_id"] == entity_id and c[key]), None)
        elif operation == "delete":
            rpc, params = "cz8Z4b", [None, None, project_id, [entity_id]]
            done = lambda chars: all(c["entity_id"] != entity_id for c in chars)
        else:
            # Pedidos capturados em "Novo personagem" > "Adicionar do projeto".
            rpc, params = "C4BZMd", [[project_id, None, None, [1, display_name, []]]]
            known = {c["entity_id"] for c in before}
            done = lambda chars: next((c for c in chars if c["entity_id"] not in known
                                       and c["display_name"] == display_name), None)
        try:
            if rpc:
                await client.rpc(rpc, params=params)
        except Exception:
            pass  # Resultado decidido só pela leitura posterior; nunca reenviar.
        if operation == "set_image" and description is not None:
            # "Criar retrato/corpo": imagem gerada (Nano Banana 2) já ligada ao slot.
            from flow_video import generate_images

            job.update(status="generating_image")
            save_job(job)
            generated = await generate_images(account_id, description, max_credits, project_id,
                                              model="nano-banana-2", aspect="3:4" if slot == "body" else "16:9",
                                              count=1, character_entity_id=entity_id,
                                              character_slot=index, client=client)
            job["generated_job_id"] = generated.get("job_id")
            if generated.get("status") != "completed":
                raise ValueError("Imagem do personagem não concluída; veja generated_job_id.")
        found = await _read_until(client, project_id, done)
        if not found:
            raise ValueError("Alteração do personagem não confirmada por leitura.")
        if operation == "create" and description is not None:
            # "Novo personagem" por descrição: retrato gerado (Nano Banana 2) já ligado ao personagem.
            from flow_video import generate_images

            entity_id = found["entity_id"]
            job.update(entity_id=entity_id, status="generating_portrait")
            save_job(job)
            portrait = await generate_images(account_id, description, max_credits, project_id,
                                             model="nano-banana-2", aspect="16:9", count=1,
                                             character_entity_id=entity_id, client=client)
            job["portrait_job_id"] = portrait.get("job_id")
            if portrait.get("status") != "completed":
                raise ValueError("Retrato do personagem não concluído; veja portrait_job_id.")
        elif operation == "create":
            # ponytail: só a imagem de criação; trocar retrato/corpo não reproduziu por HTTP.
            entity_id = found["entity_id"]
            job.update(entity_id=entity_id, status="linking_image")
            save_job(job)
            workflow_seed, _ = _seed()
            media_seed, _ = _seed()
            try:
                await client.rpc("Sc7aEb", params=[image_media_id, None, None, project_id, None, None, None,
                                                   [None, None, [entity_id, [0]]], None,
                                                   workflow_seed, media_seed])
            except Exception:
                pass
        if operation == "create":
            found = await _read_until(client, project_id, lambda chars: next(
                (c for c in chars if c["entity_id"] == entity_id and c["reference_media_ids"]), None))
            if not found:
                raise ValueError("Imagem do personagem não confirmada por leitura.")
        job["status"] = "completed"
        save_job(job)
        result = {**job, "status":{"create":"created", "update":"updated", "set_image":"image_set", "remove_image":"image_removed",
                                  "delete":"deleted"}[operation]}
        if isinstance(found, dict):
            result["character"] = found
        return result
    except Exception as exc:
        job.update(status="failed_pre_submit" if job["status"] == "preparing" else "submission_unknown",
                   error_type=type(exc).__name__, retry_automatically=False)
        if job["status"] == "failed_pre_submit" and isinstance(exc, ValueError):
            job["message"] = str(exc)
        save_job(job)
        return job
    finally:
        if owned:
            await client.close()
