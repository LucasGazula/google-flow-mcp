"""Brief por projeto e sessões do Flow Agent."""

from datetime import datetime, timezone
import json
import re

from flow_errors import error_fields, tolerant_rows
from flow_accounts import validate_account
from flow_projects import validate_project


def parse_agent_brief(payload) -> dict:
    """Brief do Agent na oitava seção de Zzl0ze: [_, [ativo, [[id, título, texto, ativo]]], ...]."""
    if not isinstance(payload, list) or len(payload) < 8:  # Seções novas no fim não invalidam.
        raise ValueError("Resposta do projeto não reconhecida.")
    info = payload[7] if isinstance(payload[7], list) else []
    brief = info[1] if len(info) > 1 and isinstance(info[1], list) else []
    cards = brief[1] if len(brief) > 1 and isinstance(brief[1], list) else []
    instructions = []
    for card in cards:
        if not isinstance(card, list) or not card or not isinstance(card[0], str):
            raise ValueError("Cartão do brief não reconhecido.")
        card = card + [None] * (4 - len(card))
        instructions.append({"id": card[0], "title": card[1] or "", "text": card[2] or "",
                             "enabled": bool(card[3])})
    return {"enabled": bool(brief[0]) if brief else False, "instructions": instructions}


def _cards(values) -> tuple:
    from gflow_cli.api.image import AgentInstruction

    if not isinstance(values, list) or any(not isinstance(card, dict) for card in values):
        raise ValueError("instructions deve ser uma lista de cartões.")

    allowed = {"id", "title", "text", "enabled", "image_media_ids", "character_ids"}
    result = []
    for card in values:
        if set(card) - allowed:
            raise ValueError("Cartão contém campos não reconhecidos.")
        text = card.get("text", "")
        title = card.get("title", "")
        card_id = card.get("id", "")
        enabled = card.get("enabled", True)
        if not all(isinstance(value, str) for value in (text, title, card_id)):
            raise ValueError("ID, título e texto do cartão devem ser texto.")
        if type(enabled) is not bool:
            raise ValueError("enabled do cartão deve ser booleano.")
        refs = {}
        for key in ("image_media_ids", "character_ids"):
            values = card.get(key, [])
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError(f"{key} deve ser uma lista de IDs em texto.")
            refs[key] = tuple(values)
        from flow_assets import media_uuid

        for media_id in refs["image_media_ids"]:
            media_uuid(media_id)
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value)
               for value in (*refs["character_ids"], card_id) if value):
            raise ValueError("ID de personagem ou cartão inválido.")
        result.append(AgentInstruction(text=text, title=title, id=card_id, enabled=enabled,
                                       image_media_ids=refs["image_media_ids"],
                                       character_ids=refs["character_ids"]))
    return tuple(result)


def _parse_agent_sessions(payload) -> list[dict]:
    # Projeto sem sessões pode vir como [] ou [null].
    if not isinstance(payload, list) or (payload and not isinstance(payload[0], (list, type(None)))):
        raise ValueError("Resposta de sessões do Agent não reconhecida.")

    def parse(row):
        if not isinstance(row, list) or not row or not isinstance(row[0], str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,128}", row[0]):
            raise ValueError("Registro de sessão do Agent não reconhecido.")
        metadata = row[1] if len(row) > 1 and isinstance(row[1], list) else []
        return {"session_id": row[0], "title": metadata[0] if metadata and isinstance(metadata[0], str) else None}

    return tolerant_rows(payload[0] if payload else [], parse)


async def _read_agent_sessions(client, project_id: str) -> list[dict]:
    return _parse_agent_sessions(await client.rpc("mrlkwd", params=[project_id]))


async def create_agent_session(account_id: str, project_id: str, *, client=None) -> dict:
    from flow_http import FlowHTTP
    from flow_requests import _seed

    validate_account(account_id)
    project_id = validate_project(project_id)
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        seed, session_id = _seed()
        response_id = None
        try:
            response = await client.rpc("csbIsb", params=[project_id, None, seed])
            if isinstance(response, list) and response and isinstance(response[0], list) and response[0]:
                response_id = response[0][0]
        except Exception:
            pass  # Resultado incerto: reconciliar por leitura, nunca reenviar.
        confirmed = response_id == session_id
        if not confirmed:
            try:
                confirmed = any(item["session_id"] == session_id
                                for item in await _read_agent_sessions(client, project_id))
            except Exception:
                pass
        return {"account_id": account_id, "project_id": project_id,
                "session_id": session_id,
                "status": "created" if confirmed else "submission_unknown",
                "source": "HTTP/csbIsb+mrlkwd" if response_id != session_id else "HTTP/csbIsb",
                **({} if confirmed else {"message": "Criação não confirmada; confira as sessões antes de tentar novamente."})}
    finally:
        if owned:
            await client.close()


async def list_agent_sessions(account_id: str, project_id: str, *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        sessions = await _read_agent_sessions(client, project_id)
        return {"account_id": account_id, "project_id": project_id, "status": "ok",
                "source": "HTTP/mrlkwd", "sessions": sessions, "complete": False,
                "scope": "Resposta inicial; paginação do histórico não validada."}
    finally:
        if owned:
            await client.close()


async def rename_agent_session(account_id: str, project_id: str, session_id: str,
                               title: str, *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("ID de sessão do Agent inválido.")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise ValueError("Informe um título de até 200 caracteres.")
    title = title.strip()
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        before = await _read_agent_sessions(client, project_id)
        session = next((item for item in before if item["session_id"] == session_id), None)
        if session is None:
            return {"account_id": account_id, "project_id": project_id,
                    "session_id": session_id, "status": "not_found_in_first_page",
                    "complete": False}
        if session["title"] == title:
            return {"account_id": account_id, "project_id": project_id,
                    "session_id": session_id, "title": title, "status": "unchanged",
                    "source": "HTTP/mrlkwd"}
        try:
            await client.rpc("TunYMc", params=[session_id, title, project_id])
        except Exception:
            pass  # Envio incerto: a leitura seguinte reconcilia; nunca reenviar.
        try:
            after = await _read_agent_sessions(client, project_id)
        except Exception:
            after = []
        current = next((item for item in after if item["session_id"] == session_id), None)
        confirmed = current is not None and current["title"] == title
        return {"account_id": account_id, "project_id": project_id,
                "session_id": session_id, "title": title,
                "status": "updated" if confirmed else "submission_unknown",
                "source": "HTTP/TunYMc+mrlkwd",
                **({} if confirmed else {"message": "Renomeação não confirmada; confira a sessão antes de tentar novamente."})}
    finally:
        if owned:
            await client.close()


async def delete_agent_session(account_id: str, project_id: str, session_id: str,
                               confirm_delete: bool = False, *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    project_id = validate_project(project_id)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", session_id):
        raise ValueError("ID de sessão do Agent inválido.")
    if confirm_delete is not True:
        return {"account_id": account_id, "project_id": project_id,
                "session_id": session_id, "status": "confirmation_required",
                "message": "A exclusão apaga permanentemente o histórico desta sessão. Confirme com confirm_delete=true."}
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        before = await _read_agent_sessions(client, project_id)
        if not any(item["session_id"] == session_id for item in before):
            return {"account_id": account_id, "project_id": project_id,
                    "session_id": session_id, "status": "not_found_in_first_page",
                    "complete": False}
        response_received = False
        try:
            await client.rpc("Dcn2Le", params=[session_id])
            response_received = True
        except Exception:
            pass  # Resultado incerto: a leitura seguinte reconcilia; nunca reenviar.
        try:
            after = await _read_agent_sessions(client, project_id)
        except Exception:
            after = before
        deleted = response_received and not any(item["session_id"] == session_id for item in after)
        return {"account_id": account_id, "project_id": project_id,
                "session_id": session_id,
                "status": "deleted" if deleted else "submission_unknown",
                "source": "HTTP/Dcn2Le+mrlkwd",
                **({} if deleted else {"message": "Exclusão não confirmada; confira a sessão antes de tentar novamente."})}
    finally:
        if owned:
            await client.close()


async def get_agent_brief(account_id: str, project_id: str, *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        brief = parse_agent_brief(await client.rpc("Zzl0ze", project_id=project_id))
        return {"account_id": account_id, "project_id": project_id, "status": "ok",
                "source": "HTTP/Zzl0ze", "agent_brief": brief}
    finally:
        if owned:
            await client.close()


async def update_agent_brief(account_id: str, project_id: str, *, enabled: bool | None = None,
                             instructions: list[dict] | None = None,
                             confirm_replace_instructions: bool = False, client=None) -> dict:
    """Envia o brief completo uma vez (Kcr7Ub); resultado incerto só é reconciliado por leitura."""
    import asyncio
    from uuid import uuid4

    from flow_http import FlowHTTP

    validate_account(account_id)
    validate_project(project_id)
    if enabled is not None and type(enabled) is not bool:
        raise ValueError("enabled deve ser booleano.")
    if enabled is None and instructions is None:
        raise ValueError("Informe enabled ou instructions para atualizar.")
    if instructions is not None and confirm_replace_instructions is not True:
        return {"account_id": account_id, "project_id": project_id,
                "status": "confirmation_required",
                "message": "A lista inteira de instruções será substituída; confirme explicitamente com confirm_replace_instructions=true."}
    cards = _cards(instructions) if instructions is not None else None
    if cards and any(card.image_media_ids or card.character_ids for card in cards):
        # ponytail: posições de imagens/personagens no cartão nativo ainda não capturadas.
        raise ValueError("Referências de imagem/personagem em cartões ainda não são suportadas.")
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        current = parse_agent_brief(await client.rpc("Zzl0ze", project_id=project_id))
        wanted = {"enabled": current["enabled"] if enabled is None else enabled,
                  "instructions": current["instructions"] if cards is None else [
                      {"id": card.id or str(uuid4()).upper(), "title": card.resolved_title(),
                       "text": card.text, "enabled": card.enabled} for card in cards]}
        # Pedido capturado em "Instruções para o agente" > Concluir (máscara project_brief).
        params = [project_id, [None, [int(wanted["enabled"]),
                  [[c["id"], c["title"], c["text"], int(c["enabled"])] for c in wanted["instructions"]]]],
                  [["project_brief"]]]
        try:
            await client.rpc("Kcr7Ub", params=params)
        except Exception:
            pass  # Resultado decidido só pela leitura posterior; nunca reenviar.
        for attempt in range(4):
            if attempt:
                await asyncio.sleep(2)
            brief = parse_agent_brief(await client.rpc("Zzl0ze", project_id=project_id))
            if brief == wanted:
                return {"account_id": account_id, "project_id": project_id, "status": "updated",
                        "source": "HTTP/Kcr7Ub", "agent_brief": brief}
        return {"account_id": account_id, "project_id": project_id, "status": "submission_unknown",
                "agent_brief": brief, "retry_automatically": False,
                "message": "Alteração não confirmada; confira o brief antes de repetir."}
    finally:
        if owned:
            await client.close()


_TOOL_CATEGORIES = {1:"mine", 2:"templates", 3:"community"}


def _seconds_iso(value):
    if not isinstance(value, list) or not value or type(value[0]) is not int:
        return None
    return datetime.fromtimestamp(value[0], timezone.utc).isoformat()


def parse_tools(payload) -> list[dict]:
    """Applets de ListApplets (tRARke): Minhas ferramentas, Modelos e Comunidade."""
    if not isinstance(payload, list) or not payload or not isinstance(payload[0], list):
        raise ValueError("Resposta de ferramentas não reconhecida.")

    def parse(row):
        if (not isinstance(row, list) or len(row) < 13 or not isinstance(row[2], str)
                or not isinstance(row[11], str) or not row[11].startswith("applets/")
                or row[12] not in _TOOL_CATEGORIES):
            raise ValueError("Ferramenta não reconhecida.")
        return {"tool_id":row[11].removeprefix("applets/"), "title":row[2],
                "description":row[3] if isinstance(row[3], str) else "",
                "category":_TOOL_CATEGORIES[row[12]],
                "creator":row[17] if len(row) > 17 and isinstance(row[17], str) else None,
                "created_at":_seconds_iso(row[7]), "updated_at":_seconds_iso(row[8])}

    return tolerant_rows(payload[0], parse)


async def list_tools(account_id: str, category: str = "all", query: str = "", *, client=None) -> dict:
    from flow_http import FlowHTTP

    validate_account(account_id)
    if category not in {"all", *_TOOL_CATEGORIES.values()}:
        raise ValueError("Categoria inválida: use all, mine, templates ou community.")
    if not isinstance(query, str) or len(query) > 200:
        raise ValueError("Pesquisa de ferramenta inválida.")
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        tools = [tool for tool in parse_tools(await client.rpc("tRARke", params=[]))
                 if category in {"all", tool["category"]}
                 and (query.casefold() in tool["title"].casefold()
                      or query.casefold() in tool["description"].casefold())]
        return {"account_id":account_id, "status":"ok", "source":"HTTP/tRARke",
                "tools":tools, "count":len(tools), "complete":False}
    finally:
        if owned:
            await client.close()


_NO_MEDIA = "Neste turno, apenas responda: não gere, edite, mova nem exclua mídia."
_READ_ONLY_TOOL_PREFIXES = ("list_", "get_", "open_")  # observados: list_project_artifacts, open_chat_panel
_SESSION_ID = re.compile(r"[A-Za-z0-9_-]{1,128}")
_GENERATION_RPCS = ("MZZa6b", "YhhmEf", "jIps6", "ogiZ0b", "eb1hJf", "nprQif", "fZytfe", "sAVZzc", "maseQ")


def _texts(value):
    if isinstance(value, list):
        if (len(value) == 2 and value[0] == "text" and isinstance(value[1], list)
                and len(value[1]) > 2 and isinstance(value[1][2], str)):
            yield value[1][2]
        else:
            for item in value:
                yield from _texts(item)


def parse_agent_stream(body: str) -> dict:
    """Quadros wrb.fr de StreamChat: chamadas de ferramenta, deltas parciais e texto final."""
    tools, finals, deltas, seen_calls = [], [], [], set()
    for line in body.splitlines():
        if not line.startswith("[["):
            continue
        for item in json.loads(line):
            if not (isinstance(item, list) and len(item) > 2 and item[0] == "wrb.fr"
                    and isinstance(item[2], str)):
                continue
            payload = json.loads(item[2])
            content = payload[0] if isinstance(payload, list) and payload else None
            if not isinstance(content, list):
                continue
            partial = len(payload) > 2 and payload[2] is True
            for entry in content[1] if len(content) > 1 and isinstance(content[1], list) else []:
                # entry[3] é a chamada (repetida em parciais); entry[4] é o resultado.
                call = entry[3] if isinstance(entry, list) and len(entry) > 3 else None
                if (isinstance(call, list) and call and isinstance(call[0], str)
                        and entry[0] not in seen_calls):
                    seen_calls.add(entry[0])
                    tools.append(call[0])
            text = "".join(_texts(content[0])) if content else ""
            if text:
                (deltas if partial else finals).append(text)
    answer = finals[-1] if finals else "".join(deltas)
    if "literalString" in answer:
        # Resposta em A2UI: o texto visível está nos literalString do JSON de interface.
        answer = "\n".join(json.loads(f'"{value}"') for value in
                           re.findall(r'"literalString":\s*"((?:[^"\\]|\\.)*)"', answer))
    return {"answer": answer.strip(), "tools": tools}


async def chat_template(client, project_id: str, *, fresh_session: bool) -> dict:
    """Pedido StreamChat digitado na página e retido (abortado): url, corpo com reCAPTCHA novo e cabeçalhos.

    Nada chega ao Agent; RPCs de geração são abortados; a sessão (csbIsb) e as leituras seguem.
    """
    import asyncio
    from urllib.parse import urlsplit

    found = asyncio.get_running_loop().create_future()
    async with client.browser.page() as page:
        async def hold(route):
            request = route.request
            body = (request.post_data_buffer or b"").decode("utf-8", "replace") if request.method == "POST" else ""
            if "batchexecute" in request.url and any(rpc in body for rpc in _GENERATION_RPCS):
                await route.abort()
                return
            if request.method == "POST" and "FlowCreationAgentService/StreamChat" in request.url:
                if not found.done():
                    found.set_result({"url":request.url, "body":body,
                        "headers":{key:value for key, value in request.headers.items()
                                   if key.lower() not in {"cookie", "host", "content-length", "connection"}}})
                await route.abort()
            else:
                await route.fallback()
        await page.route("**/*", hold)
        await page.goto(f"https://flow.google.com/project/{project_id}", wait_until="domcontentloaded", timeout=45000)
        toggle = page.get_by_role("button", name=re.compile("^Agente$|^Agent$"))
        if await toggle.count() and await toggle.first.get_attribute("aria-pressed") != "true":
            raise ValueError("Página não abriu no modo Agente; nada foi digitado.")
        if fresh_session:
            # Painel aberto reabre a última sessão; sem o botão, o envio já cria sessão nova.
            try:
                await page.get_by_role("button", name=re.compile("^Iniciar nova sessão$|^Start new session$")).first.click(timeout=5000)
            except Exception:
                pass
        # Só a caixa visível: no compositor só de Agent há outra editável oculta.
        box = page.locator("[contenteditable=true] >> visible=true").first
        await box.click(timeout=30000)
        await page.keyboard.type("Preparação MCP; envio bloqueado.")
        await page.keyboard.press("Enter")
        captured = await asyncio.wait_for(found, 60)
        await client.session_from_page(page)
    if urlsplit(captured["url"]).hostname != "flow.google.com":
        raise ValueError("Destino do Agent não reconhecido.")
    return captured


def mention(item_id: str, name: str, *, character: bool) -> list:
    """Trecho de mensagem que cita um personagem (entidade) ou uma mídia do projeto, como o @ da interface."""
    return [None, [None, None, [item_id, name]]] if character else [None, [[item_id, name]]]


def chat_form(body: str, project_id: str, parts: list, *, session_id: str | None = None,
              approve: bool = False) -> tuple[str, str]:
    """Troca a mensagem de um StreamChat retido; `approve` vira a resposta "Aprovar" ao pedido de permissão."""
    from urllib.parse import parse_qs, urlencode

    form = parse_qs(body, keep_blank_values=True)
    inner = json.loads(json.loads(form["f.req"][0])[1])
    if (not isinstance(inner, list) or len(inner) < 3 or not isinstance(inner[2], list)
            or inner[2][0] != f"projects/{project_id}" or len(inner[2]) < 6):
        raise ValueError("Pedido do Agent não confirmado; envio bloqueado.")
    # Continuação: o pedido retido usa a sessão aberta no painel; troca-se pela pedida.
    session_id = session_id or inner[0]
    inner[0] = session_id
    media = [part[1][0] for part in parts if part[0] is None and part[1][0] is not None]
    entities = [part[1][2] for part in parts if part[0] is None and part[1][0] is None]
    inner[1] = [[parts]] + ([media or None, None, entities or None] if media or entities else [])
    if approve:
        inner[1] = [[[["Aprovar"]]]]
        inner[2][5] = 2  # resposta de permissão, como o clique em "Aprovar"
        inner[3:] = [None, 1]
    form["f.req"] = [json.dumps([None, json.dumps(inner, separators=(",", ":"), ensure_ascii=False)],
                                separators=(",", ":"), ensure_ascii=False)]
    return urlencode(form, doseq=True), session_id


async def agent_chat(client, project_id: str, parts: list, *, session_id: str | None = None,
                     approve: bool = False) -> dict:
    """Uma mensagem ao Agent por um único POST StreamChat (reCAPTCHA novo a cada mensagem)."""
    captured = await chat_template(client, project_id, fresh_session=session_id is None)
    body, session_id = chat_form(captured["body"], project_id, parts, session_id=session_id, approve=approve)
    response = await client.client.post(captured["url"], content=body, headers=captured["headers"], timeout=600)
    if response.status_code != 200:
        raise ValueError("Resposta do Agent inconclusiva; não reenviar.")
    return {"session_id": session_id, **parse_agent_stream(response.text)}


def agent_cost(answer: str) -> int | None:
    """Créditos do pedido de aprovação do Agent ("... que custa 4 créditos?")."""
    found = re.search(r"(\d+)\s*(?:créditos?|credits?)\b", answer or "", re.I)
    return int(found.group(1)) if found else None


async def agent_generate(client, job: dict, parts: list, *, kind: str, count: int, expected_credits: int,
                         save_job, timeout: int = 600) -> list[dict]:
    """Geração pelo Agent (conta só de Agent): pede, confere o custo informado, aprova e acha a mídia nova.

    Só aprova se o Agent informar exatamente `expected_credits`. Sem pedido de aprovação com custo
    (Agent configurado para não confirmar), o resultado é incerto e não deve ser repetido.
    """
    import asyncio
    from flow_assets import parse_assets

    project_id = job["project_id"]
    listed = lambda payload: parse_assets(payload, project_id)
    before = {a["media_id"] for a in listed(await client.rpc("Zzl0ze", project_id=project_id))}
    job.update(status="submitting", source="Agent/StreamChat")
    save_job(job)  # Com "Confirmar antes de gerar: Nunca", o Agent já gastaria aqui.
    first = await agent_chat(client, project_id, parts)
    job.update(agent_session_id=first["session_id"], agent_answer=first["answer"][:600])
    asked = agent_cost(first["answer"])
    if expected_credits and asked is None:
        raise ValueError("O Agent não pediu aprovação com o custo; ele pode ter gerado sem confirmar. Confira o "
                         "projeto antes de repetir (não reenvie).")
    if expected_credits:
        job["agent_quoted_credits"] = asked
        if asked != expected_credits:
            job["status"] = "preparing"  # Nada aprovado: o pedido fica sem efeito no Agent.
            raise ValueError(f"O Agent cotou {asked} créditos, diferente da cotação ({expected_credits}); "
                             "nada foi aprovado.")
        await agent_chat(client, project_id, [], session_id=first["session_id"], approve=True)
    job["status"] = "accepted"
    save_job(job)
    async with asyncio.timeout(timeout):
        while True:
            new = [a for a in listed(await client.rpc("Zzl0ze", project_id=project_id))
                   if a["media_id"] not in before and a["kind"] == kind]
            if len(new) >= count:
                return new[:count]
            await asyncio.sleep(5)


async def agent_request(account_id: str, project_id: str, message: str, *,
                        allow_media_changes: bool = False, session_id: str | None = None,
                        client=None) -> dict:
    """Envia uma mensagem ao Agent (sessão nova ou existente) por um único POST StreamChat."""
    import asyncio
    from urllib.parse import parse_qs, urlencode, urlsplit
    from uuid import uuid4

    from flow_credits import parse_http_credits
    from flow_http import FlowHTTP
    from flow_video import save_job

    validate_account(account_id)
    project_id = validate_project(project_id)
    if not isinstance(message, str) or not message.strip() or len(message) > 4000:
        raise ValueError("Informe uma mensagem de 1 a 4000 caracteres.")
    if type(allow_media_changes) is not bool:
        raise ValueError("allow_media_changes deve ser booleano.")
    if session_id is not None and (not isinstance(session_id, str) or not _SESSION_ID.fullmatch(session_id)):
        raise ValueError("ID de sessão do Agent inválido.")
    text = message if allow_media_changes else f"{_NO_MEDIA}\n\n{message}"
    owned = client is None
    client = client or FlowHTTP(account_id, resident=True)
    if client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    job = {"job_id":str(uuid4()), "account_id":account_id, "project_id":project_id,
           "kind":"agent_request", "status":"preparing", "source":"HTTP/StreamChat", "files":[]}
    save_job(job)
    try:
        if session_id is not None and not any(item["session_id"] == session_id
                                              for item in await _read_agent_sessions(client, project_id)):
            raise ValueError("Sessão ausente da primeira página deste projeto.")
        before = parse_http_credits(await client.rpc("nzlxg"))
        from flow_settings import get_user_settings, update_user_settings

        # Ativar o modo por clique deixa o Enter na geração; a página precisa abrir já no modo Agente.
        if not (await get_user_settings(account_id, client=client))["settings"]["agent_mode_enabled"]:
            enabled = await update_user_settings(account_id, agent_mode_enabled=True, client=client)
            if enabled.get("status") != "updated":
                raise ValueError("Modo Agente não ativado; nada foi enviado.")
            job["agent_mode_restore"] = True
            save_job(job)
        captured = await chat_template(client, project_id, fresh_session=session_id is None)
        body, session_id = chat_form(captured["body"], project_id, [[text]], session_id=session_id)
        captured["body"] = body
        job.update(status="submitting", session_id=session_id)
        save_job(job)
        response = await client.client.post(captured["url"], content=captured["body"],
                                             headers=captured["headers"], timeout=300)
        if response.status_code != 200:
            raise ValueError("Resposta do Agent inconclusiva; não reenviar.")
        result = parse_agent_stream(response.text)
        try:
            after = parse_http_credits(await client.rpc("nzlxg"))
        except Exception:
            after = None  # A resposta já chegou; saldo ilegível não a invalida.
        unexpected = [tool for tool in result["tools"] if not tool.startswith(_READ_ONLY_TOOL_PREFIXES)]
        job.update(status="completed", tools=result["tools"], credits_before=before, credits_after=after)
        save_job(job)
        return {**job, "answer":result["answer"], "credits_spent":None if after is None else before - after,
                "unexpected_tools":unexpected,
                "warning":("O Agent chamou ferramentas fora da lista somente leitura; confira o projeto."
                           if unexpected and not allow_media_changes else None)}
    except Exception as exc:
        job.update(status="failed_pre_submit" if job["status"] == "preparing" else "submission_unknown",
                   retry_automatically=False, **error_fields(exc))
        save_job(job)
        return job
    finally:
        if job.pop("agent_mode_restore", False):
            from flow_settings import update_user_settings

            try:
                restored = await update_user_settings(account_id, agent_mode_enabled=False, client=client)
                job["agent_mode_restored"] = restored.get("status") == "updated"
            except Exception:
                job["agent_mode_restored"] = False
            save_job(job)
        if owned:
            await client.close()

