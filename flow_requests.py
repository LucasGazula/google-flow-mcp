"""Corpos RPC do Flow, conferidos nas capturas e no código do frontend."""

import base64
import hashlib
import secrets
from uuid import uuid4

from flow_assets import media_uuid
from flow_projects import validate_project


def _seed():
    seed = str(uuid4())
    value = list(hashlib.sha256(seed.encode()).hexdigest()[:32])
    value[12], value[16] = "4", format((int(value[16], 16) & 3) | 8, "x")
    value = "".join(value)
    return seed, f"{value[:8]}-{value[8:12]}-{value[12:16]}-{value[16:20]}-{value[20:]}"


def flow_context(project_id, captcha, workflow_id=None):
    validate_project(project_id)
    if not isinstance(captcha, str) or not captcha:
        raise ValueError("Autenticação do pedido não preparada.")
    if workflow_id is not None:
        media_uuid(workflow_id)
    return [None, 22, None, None, workflow_id, project_id, None, None, None, None, [captcha, 1]]


def structured_prompt(prompt, references=(), reference_names=None):
    names = reference_names or {}
    parts = [[None, [[media_uuid(mid), names.get(mid, mid)]]] for mid in references]
    parts.append([("\n\n" if parts else "") + prompt])
    return [parts]


def image_request(project_id, prompt, model_key, aspect, count, captcha, *, references=(),
                  source_media_id=None, workflow_id=None, reference_names=None,
                  character_entity_id=None, character_slot=0):
    aspects = {"1:1":1, "9:16":2, "16:9":3, "3:4":4, "4:3":5}
    context = flow_context(project_id, captcha, workflow_id)
    refs = [[media_uuid(mid), None, None, None, 1] for mid in references]
    if source_media_id is not None:
        refs.insert(0, [media_uuid(source_media_id), None, None, None, 2])
    rows, media_ids, workflows = [], [], []
    for _ in range(count):
        media_seed, mid = _seed()
        workflow_seed, wid = _seed()
        rows.append([None, None, refs or None, secrets.randbelow(2147483647), aspects[aspect], model_key,
                     None, context, structured_prompt(prompt, references, reference_names),
                     None, None, None, None if workflow_id else workflow_seed, media_seed])
        media_ids.append(mid)
        workflows.append(workflow_id or wid)
    batch = [str(uuid4())]
    if character_entity_id is not None:
        if count != 1:
            raise ValueError("O retrato do personagem é uma única imagem.")
        # Pedido capturado em "Novo personagem": liga a imagem ao slot (0 retrato, 1 corpo).
        batch += [None, [media_uuid(character_entity_id), [character_slot]]]
    return {"rpc_id":"ogiZ0b", "params":[None, rows, 1, context, batch],
            "request_media_ids":media_ids, "request_workflow_ids":workflows}


def video_request(project_id, prompt, model_key, aspect, count, captcha, *, start_id=None,
                  end_id=None, references=(), reference_names=None, operation="generate",
                  source_id=None, workflow_id=None, start_frame=None, end_frame=None,
                  create_new_workflow=False, voice=None, characters=()):
    context = flow_context(project_id, captcha)
    if start_id:
        media_uuid(start_id)
    if end_id:
        media_uuid(end_id)
    if end_id and not start_id or references and start_id:
        raise ValueError("Entradas de vídeo incompatíveis.")
    refs = [[None, media_uuid(mid)] for mid in references]
    characters = [[media_uuid(entity_id)] for entity_id in characters]
    if characters and (start_id or operation != "generate"):
        raise ValueError("Personagens exigem geração por ingredientes.")
    rpc = "nprQif" if end_id else "eb1hJf" if start_id else "MZZa6b" if refs or characters else "YhhmEf"
    if operation not in {"generate", "edit", "extend"}:
        raise ValueError("Operação de vídeo inválida.")
    if type(create_new_workflow) is not bool or create_new_workflow and operation != "edit":
        raise ValueError("Novo histórico está disponível apenas na edição de vídeo.")
    if operation != "generate":
        media_uuid(source_id)
        media_uuid(workflow_id)
        if start_id or end_id or count != 1:
            raise ValueError("Entradas de edição/extensão incompatíveis.")
        if operation == "edit" and (type(start_frame) is not int or type(end_frame) is not int
                                    or not 0 <= start_frame < end_frame):
            raise ValueError("Trecho de vídeo inválido.")
        rpc = "jIps6" if operation == "edit" else "fZytfe"
    if voice is not None and (operation != "generate" or not (refs or characters) or start_id
                              or not isinstance(voice, str) or not voice.isalpha()):
        raise ValueError("Voz exige geração com referências de imagem.")
    rows, media_ids, workflows = [], [], []
    for _ in range(count):
        media_seed, mid = _seed()
        workflow_seed, wid = _seed()
        metadata = [None, None, None, None, media_seed, workflow_seed]
        prompt_message = [None, None, structured_prompt(prompt, references, reference_names)]
        ratio = {"9:16":1, "16:9":2}[aspect]
        if operation != "generate":
            if not create_new_workflow:
                metadata = [None, workflow_id, None, None, media_seed]
            source = [None, source_id, start_frame, end_frame]
            if operation == "edit":
                row = [source, prompt_message, model_key, ratio, metadata]
            else:
                row = [source, prompt_message, model_key, ratio, None, metadata]
            if refs:
                row.extend([None] * (8 - len(row)))
                row.append(refs)
        elif end_id:
            row = [prompt_message, model_key, ratio, None, [None, start_id], [None, end_id], metadata]
        elif start_id:
            row = [prompt_message, model_key, ratio, None, [None, start_id], metadata]
        elif refs or characters:
            # Pedidos capturados: voz pronta em minúsculas no campo 7, personagens no 9.
            row = [prompt_message, refs or None, model_key, ratio, None, metadata,
                   None, [[voice.lower()]] if voice else None, None, characters or None]
            while row[-1] is None:
                row.pop()
        else:
            row = [prompt_message, model_key, ratio, None, metadata]
        rows.append(row)
        media_ids.append(mid)
        workflows.append(wid if create_new_workflow else workflow_id or wid)
    return {"rpc_id":rpc, "params":[rows, context, [str(uuid4()), 2]],
            "request_media_ids":media_ids, "request_workflow_ids":workflows}


def upload_request(project_id, body, mime, name, captcha):
    media_seed, mid = _seed()
    workflow_seed, wid = _seed()
    # Os dois campos recebem sementes workflow/mídia, não os IDs derivados.
    return {"rpc_id":"maseQ", "params":[flow_context(project_id, captcha),
            base64.b64encode(body).decode("ascii"), mime, True, None, None, None, None,
            name, None, workflow_seed, media_seed],
            "request_media_ids":[mid], "request_workflow_ids":[wid]}
