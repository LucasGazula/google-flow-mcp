"""Worker privado por conta: HTTP e Chrome headless residente para o preparo normal."""

import asyncio
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
import json
import os
import re
from pathlib import Path
import sys
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx


class FlowHTTP:
    def __init__(self, account_id, *, resident=False):
        self.account_id = account_id
        self.client = None
        self.templates = {}
        self.as29s_payloads = {}
        self.video_records = {}
        self.pending_upload = None  # ponytail: uma confirmação por conta; enfileirar se houver demanda paralela.
        from flow_browser import FlowBrowser

        self.browser = FlowBrowser(account_id, headless=os.environ.get("FLOW_MCP_HEADLESS", "true").lower() != "false") if resident else None

    @asynccontextmanager
    async def gflow_api_page(self):
        """Borrow gflow-cli's API helpers on the worker's already leased profile."""
        if self.browser is None:
            raise RuntimeError("A operação requer o worker autenticado do Flow.")
        from gflow_cli import auth
        from gflow_cli.api.client import FlowApiClient

        async with self.browser.page() as page:
            api = FlowApiClient(auth.profile_dir(self.account_id), headless=True)
            # ponytail: borrow pinned gflow-cli page hooks; entering another client locks this profile twice.
            api._page, api._context = page, page.context
            yield api, page

    async def close(self):
        try:
            if self.pending_upload is not None:
                pending, self.pending_upload = self.pending_upload, None
                await pending["page_context"].__aexit__(None, None, None)
            if self.client is not None:
                await self.client.aclose()
        finally:
            if self.browser is not None:
                await self.browser.close()

    async def session_from_page(self, page):
        """Transferir cookies somente em memória; não executa requisições."""
        cookies = await page.context.cookies(["https://flow.google.com/"])
        agent = await page.evaluate("navigator.userAgent")
        if self.client is not None:
            await self.client.aclose()
        jar = httpx.Cookies()
        for cookie in cookies:
            jar.set(cookie["name"], cookie["value"], domain=cookie["domain"], path=cookie["path"])
        self.client = httpx.AsyncClient(cookies=jar, headers={"User-Agent": agent},
                                       follow_redirects=False, timeout=120, trust_env=False)

    async def capture_submit(self, page, submit, rpc_ids):
        """Bloquear o envio do navegador e manter a requisição apenas em memória.

        O bloqueio permanece até fechar a página, inclusive para retries do frontend.
        """
        found = asyncio.get_running_loop().create_future()

        async def block(route):
            request = route.request
            parts = urlsplit(request.url)
            if (request.method in {"GET", "HEAD"}
                    or (parts.scheme == "https" and parts.hostname in {"www.google.com", "www.recaptcha.net"}
                        and parts.path.startswith("/recaptcha/"))):
                await route.continue_()
                return
            try:
                if "batchexecute" not in request.url:
                    return
                envelope = json.loads(parse_qs(request.post_data or "").get("f.req", ["[]"])[0])
                calls = [call for batch in envelope for call in batch]
                if any(call[0] in rpc_ids for call in calls) and not found.done():
                    validate_rpc_url(request.url)
                    if len(calls) != 1:
                        raise ValueError("Envio com operações adicionais não autorizado.")
                    found.set_result({"url": request.url, "body": request.post_data,
                        "rpc_id": calls[0][0], "params": json.loads(calls[0][1]),
                        "headers": {key: value for key, value in request.headers.items()
                            if key.lower() not in {"cookie", "host", "content-length", "connection"}}})
            except Exception:
                if not found.done():
                    found.set_exception(ValueError("Envio bloqueado; requisição não reconhecida."))
            finally:
                await route.abort()

        await page.route("**/*", block)
        await submit.click(timeout=5000)
        captured = await asyncio.wait_for(found, 30)
        await self.session_from_page(page)
        return captured

    async def send_submit(self, captured):
        """Um único POST HTTP, sem retries nem recuperação por novo envio."""
        from gflow_cli.api.transports.batchexecute import parse_frames

        validate_rpc_url(captured["url"])
        response = await self.client.post(captured["url"], content=captured["body"],
                                          headers=captured["headers"], timeout=600)
        if response.status_code != 200:
            raise ValueError("Envio HTTP inconclusivo; não reenviar automaticamente.")
        frames = [payload for rpc, payload in parse_frames(response.text) if rpc == captured["rpc_id"]]
        if len(frames) != 1 or frames[0] is None:
            raise ValueError("Resposta do envio HTTP não reconhecida.")
        return frames[0]

    def request(self, rpc_id, params):
        if rpc_id not in {"ogiZ0b", "YhhmEf", "eb1hJf", "nprQif", "MZZa6b", "maseQ", "jIps6", "fZytfe", "sAVZzc"}:
            raise ValueError("Operação de envio HTTP inválida.")
        template = self.templates.get("submission", self.templates.get("Zzl0ze"))
        if template is None:
            raise ValueError("Autenticação do envio não preparada.")
        return encode_rpc(template, rpc_id, params)

    def status_from_submit(self, captured, workflow_id):
        """GetMedia/as29s recebe nome da mídia; reutilizar autenticação do envio.

        O argumento mantém seu nome antigo para compatibilidade dos chamadores.
        """
        from flow_assets import media_uuid

        media_uuid(workflow_id)
        form = parse_qs(captured["body"], keep_blank_values=True)
        call = list(json.loads(form["f.req"][0])[0][0])
        call[:2] = ["as29s", json.dumps([workflow_id])]
        self.templates["as29s"] = {"url": captured["url"], "form": form, "call": call,
            "headers": captured["headers"], "workflow_id": workflow_id}

    async def prepare(self, rpc_id="UpteDb", project_id=None, media_id=None, *, captcha_action=None):
        from flow_browser import account_page
        from flow_projects import validate_project
        from flow_assets import media_uuid
        from gflow_cli.api.transports.batchexecute import parse_frames

        if rpc_id == "as29s":
            if not project_id or not media_id:
                raise ValueError("Identificadores de projeto e mídia necessários para as29s.")
            if media_id in self.as29s_payloads:
                return
        elif rpc_id in self.templates and captcha_action is None:
            return

        if captcha_action not in {None, "IMAGE_GENERATION", "VIDEO_GENERATION", "UPLOAD_IMAGE"}:
            raise ValueError("Ação de autenticação inválida.")

        if project_id:
            validate_project(project_id)
        if media_id:
            media_uuid(media_id)
        target = "https://flow.google.com/"
        if project_id:
            target += f"project/{project_id}"
        if media_id:
            target += f"/edit/{media_id}"
        pages = self.browser.page() if self.browser is not None else account_page(self.account_id)
        async with pages as page:
            found = asyncio.get_running_loop().create_future()

            async def observe(response):
                if "batchexecute" not in response.url:
                    return
                try:
                    text = await response.text()
                    frames = parse_frames(text)
                except Exception:
                    return
                if frames:
                    for rid, payload in frames:
                        if rid == "as29s" and payload is not None:
                            try:
                                from flow_assets import video_record as generation_record
                                rec = generation_record(rid, payload)
                                if rec.media_id and rec.is_done and rec.video_url:
                                    self.as29s_payloads[rec.media_id] = payload
                                    self.video_records[rec.media_id] = rec
                                    if rpc_id == "as29s" and rec.media_id == media_id and not found.done():
                                        found.set_result(True)
                            except Exception:
                                pass
                try:
                    request = response.request
                    form = parse_qs(request.post_data or "", keep_blank_values=True)
                    envelope = json.loads(form.get("f.req", [""])[0])
                    for batch in envelope:
                        for call in batch:
                            rid = call[0]
                            if rid not in {"UpteDb", "Zzl0ze", "Yizz8d", "cPZSdc", "nzlxg", "HTrJv"}:
                                continue
                            self.templates[rid] = {
                                "url": request.url,
                                "form": form,
                                "call": call,
                                "headers": {
                                    key: value for key, value in request.headers.items()
                                    if key.lower() in {"content-type", "x-same-domain", "x-goog-authuser", "origin", "referer"}
                                },
                                "project_id": project_id,
                                "media_id": media_id,
                            }
                            if rid == rpc_id and not found.done():
                                found.set_result(True)
                except Exception:
                    return

            page.on("response", observe)
            try:
                await page.goto(target, wait_until="domcontentloaded", timeout=45000)
                if rpc_id == "nzlxg" and not found.done():
                    await page.get_by_role("button", name=re.compile(r"^Novo projeto$|^New project$")).wait_for(timeout=15000)
                    await page.get_by_role("button", name=re.compile(r"^Detalhes da conta$|^Account details$")).click(timeout=5000)
                await asyncio.wait_for(found, 60)
                captcha = None
                if captcha_action in {"IMAGE_GENERATION", "VIDEO_GENERATION"}:
                    from gflow_cli.api.transports.migrated_composer import MigratedComposer, IMAGE_SUBMIT_RPC, SUBMIT_RPCS

                    # O frontend prepara o reCAPTCHA normal; nenhum pedido dele é enviado.
                    # Chamadas diretas a enterprise.execute são marcadas pelo próprio site.
                    composer = MigratedComposer()
                    pane = await composer._open_pane(page)
                    try:
                        await composer._select(page, pane, axis="mode",
                            lig="image" if captcha_action == "IMAGE_GENERATION" else "videocam")
                    finally:
                        await composer._close_pane(page, strict=False)
                    await page.locator("[contenteditable=true]").fill("Preparação de sessão MCP; envio bloqueado.")
                    submit = await composer._pre_submit_gate(page)
                    captured = await self.capture_submit(page, submit,
                        {IMAGE_SUBMIT_RPC} if captcha_action == "IMAGE_GENERATION" else set(SUBMIT_RPCS))
                    context = captured["params"][3 if captcha_action == "IMAGE_GENERATION" else 1]
                    if context[5] != project_id:
                        raise ValueError("Projeto da autenticação não confirmado.")
                    captcha = context[10][0]
                    form = parse_qs(captured["body"], keep_blank_values=True)
                    call = json.loads(form["f.req"][0])[0][0]
                    self.templates["submission"] = {"url":captured["url"], "form":form,
                                                   "call":call, "headers":captured["headers"]}
                else:
                    if captcha_action is not None:
                        await page.wait_for_function("window.grecaptcha && window.grecaptcha.enterprise", timeout=30000)
                        captcha = await page.evaluate("""async action => {
                            const script = [...document.scripts].find(s => s.src.includes('/recaptcha/enterprise.js'));
                            const key = script && new URL(script.src).searchParams.get('render');
                            if (!key || key === 'explicit') throw new Error('Authentication unavailable');
                            await new Promise(resolve => grecaptcha.enterprise.ready(resolve));
                            return await grecaptcha.enterprise.execute(key, {action});
                        }""", captcha_action)
                    await self.session_from_page(page)
            except asyncio.TimeoutError:
                if rpc_id == "as29s":
                    raise ValueError("Vídeo original ainda não disponível.") from None
                raise
            finally:
                page.remove_listener("response", observe)
        # Página de preparo fechada antes do POST; worker residente mantém só o contexto.
        return captcha

    async def rpc(self, rpc_id, project_id=None, media_id=None, workflow_id=None, params=None):
        from gflow_cli.api.transports.batchexecute import parse_frames

        if rpc_id == "nzlxg" and params is None and rpc_id not in self.templates and "UpteDb" in self.templates:
            params = []  # Saldo usa a sessão já preparada, sem reabrir o menu da conta.
        if params is not None and rpc_id not in {"jHPbke", "o8DA4", "ngNC2", "HTrJv", "yBhWQ", "nzlxg", "QI2zvc", "Uxbujd", "O2COMe", "kVdhHf", "DA4VGb", "mrlkwd", "TunYMc", "csbIsb", "Dcn2Le", "oWTRd", "GoMJte", "GjQLTd", "IxdSwd", "BpMsoe", "tRARke", "GN0Bre", "cz8Z4b", "pGCYOe", "C4BZMd", "Sc7aEb", "rzMKMb", "Kcr7Ub"}:
            raise ValueError("Parâmetros explícitos não autorizados para este RPC.")
        if params is not None:
            await self.prepare("UpteDb")
            template = self.templates["UpteDb"]
        elif rpc_id == "as29s" and rpc_id not in self.templates:
            if media_id and media_id in self.as29s_payloads:
                return self.as29s_payloads[media_id]
            await self.prepare("as29s", project_id, media_id)
            if media_id and media_id in self.as29s_payloads:
                return self.as29s_payloads[media_id]
            raise ValueError("Vídeo original ainda não disponível.")

        elif rpc_id not in self.templates:
            await self.prepare(rpc_id, project_id, media_id)

        if params is None:
            template = self.templates[rpc_id]
        call = list(template["call"])
        call[0] = rpc_id
        params = json.loads(call[1]) if params is None else params
        replacements = {}
        if project_id and template.get("project_id"):
            replacements[template["project_id"]] = project_id
            replacements[f"projects/{template['project_id']}"] = f"projects/{project_id}"
        if media_id and template.get("media_id"):
            replacements[template["media_id"]] = media_id
        if rpc_id == "as29s" and media_id and template.get("workflow_id"):
            replacements[template["workflow_id"]] = media_id
        elif workflow_id and template.get("workflow_id"):
            replacements[template["workflow_id"]] = workflow_id

        def replace(value):
            if isinstance(value, str):
                return replacements.get(value, value)
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            return value

        request = encode_rpc(template, rpc_id, replace(params))
        response = await self.client.post(request["url"], content=request["body"], headers=request["headers"])
        if response.status_code != 200:
            raise ValueError("Consulta HTTP não concluída; sessão pode exigir renovação.")
        payloads = [payload for rid, payload in parse_frames(response.text) if rid == rpc_id]
        if len(payloads) != 1 or payloads[0] is None:
            raise ValueError("Resposta RPC HTTP não reconhecida.")
        return payloads[0]

    async def download(self, url, media_id):
        from gflow_cli.api.transports.ui_automation import _is_allowed_download_host
        from urllib.parse import urljoin

        for _ in range(4):
            parts = urlsplit(url)
            if (not _is_allowed_download_host(url) or parts.username or parts.password
                    or parts.port not in {None, 443}):
                raise ValueError("Host de download não autorizado.")
            response = await self.client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise ValueError("Redirecionamento sem destino.")
                url = urljoin(url, location)
                continue
            if response.status_code != 200:
                raise ValueError("Download HTTP indisponível.")
            return response.content
        raise ValueError("Limite de redirecionamentos excedido.")


def encode_rpc(template, rpc_id, params):
    validate_rpc_url(template["url"])
    parts = urlsplit(template["url"])
    query = parse_qs(parts.query, keep_blank_values=True)
    query["rpcids"] = [rpc_id]
    url = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query, doseq=True), ""))
    call = list(template["call"])
    call[:2] = [rpc_id, json.dumps(params, separators=(",", ":"), ensure_ascii=False)]
    form = {key:list(value) for key,value in template["form"].items()}
    form["f.req"] = [json.dumps([[call]], separators=(",", ":"), ensure_ascii=False)]
    return {"url":url, "body":urlencode(form, doseq=True), "headers":template["headers"],
            "rpc_id":rpc_id, "params":params}


async def api_mutation_once(api, page, method: str, url: str, body: dict,
                            *, content_type: str) -> dict | None:
    """Send one gflow API mutation without retrying an uncertain response."""
    if method not in {"POST", "PATCH"}:
        raise ValueError("Método de mutação inválido.")
    headers = await api._request_headers(
        url=url,
        content_type=content_type,
        is_aisandbox=api._is_aisandbox_url(url),
    )
    try:
        response = await getattr(page.request, method.lower())(
            url, data=json.dumps(body), headers=headers)
        if response.status != 200:
            return None
        text = await response.text()
        return json.loads(text) if text else {}
    except Exception:
        return None


def validate_rpc_url(url):
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "flow.google.com"
            or parts.port not in {None, 443} or parts.username or parts.password
            or not parts.path.endswith("/data/batchexecute")):
        raise ValueError("Endpoint HTTP não autorizado.")


async def http_operation(client, action, payload):
    from flow_projects import parse_projects
    from flow_assets import parse_assets, media_uuid
    from flow_projects import validate_project

    if action == "upscale_video_native":
        from flow_video import upscale_video

        return await upscale_video(client.account_id, **payload, client=client)

    if action in {"generate", "images", "recover"}:
        from flow_video import generate_video, generate_images, recover_job

        return await {"generate":generate_video, "images":generate_images, "recover":recover_job}[action](
            client.account_id, **payload, client=client)
    if action == "edit_image":
        from flow_edit import edit_image

        return await edit_image(client.account_id, **payload, client=client)
    if action == "edit_images":
        from flow_edit import edit_images

        return await edit_images(client.account_id, **payload, client=client)
    if action == "refine_video":
        from flow_video import refine_video

        return await refine_video(client.account_id, **payload, client=client)
    if action == "quote_video":
        from flow_video import generate_video

        # Teto alto: a cotação só informa; o envio real aplica o max_credits do usuário.
        return await generate_video(client.account_id, prompt="cotação", max_credits=10**6,
                                    **payload, client=client, quote_only=True)
    if action in {"edit_video", "extend_video"}:
        from flow_video import generate_video

        return await generate_video(client.account_id, **payload, client=client,
                                    operation="edit" if action == "edit_video" else "extend")
    if action == "crop_image":
        from flow_edit import crop_image

        return await crop_image(client.account_id, **payload, client=client)
    if action == "upscale_image_native":
        from flow_edit import upscale_image_native

        return await upscale_image_native(client.account_id, **payload, client=client)
    if action in {"upload_image", "upload_asset"}:
        from flow_assets import upload_image, upload_asset

        return await (upload_image if action == "upload_image" else upload_asset)(
            client.account_id, **payload, client=client)
    if action == "delete_asset":
        from flow_assets import delete_asset

        return await delete_asset(client.account_id, **payload, client=client)
    if action == "search_assets":
        from flow_assets import search_assets

        return await search_assets(client.account_id, **payload, client=client)
    if action == "confirm_upload":
        from flow_assets import confirm_video_upload

        return await confirm_video_upload(client.account_id, **payload, client=client)
    if action == "save_frame":
        from flow_scene import save_video_frame

        return await save_video_frame(client.account_id, **payload, client=client)
    if action == "export_gif":
        from flow_scene import export_video_gif

        return await export_video_gif(client.account_id, **payload, client=client)
    if action == "build_scene":
        from flow_scene import build_scene

        return await build_scene(client.account_id, **payload, client=client)
    if action == "manage_scene":
        from flow_scene import manage_scene

        return await manage_scene(client.account_id, **payload, client=client)
    if action == "list_scenes":
        from flow_scene import list_scenes

        return await list_scenes(client.account_id, **payload, client=client)
    if action == "export_scene":
        from flow_scene import export_scene

        return await export_scene(client.account_id, **payload, client=client)
    if action == "upscale":
        from flow_scene import upscale_media

        return await upscale_media(client.account_id, **payload, client=client)
    if action == "download_project":
        from flow_projects import download_project

        return await download_project(client.account_id, **payload, client=client)
    if action == "project_summary":
        from flow_projects import project_summary

        return await project_summary(client.account_id, **payload, client=client)
    if action == "list_characters":
        from flow_character import list_characters

        return await list_characters(client.account_id, **payload, client=client)
    if action == "manage_character":
        from flow_character import manage_character

        return await manage_character(client.account_id, **payload, client=client)
    if action == "get_agent_brief":
        from flow_agent import get_agent_brief

        return await get_agent_brief(client.account_id, **payload, client=client)
    if action == "update_agent_brief":
        from flow_agent import update_agent_brief

        return await update_agent_brief(client.account_id, **payload, client=client)
    if action == "agent_request":
        from flow_agent import agent_request
        return await agent_request(client.account_id, **payload, client=client)
    if action == "list_tools":
        from flow_agent import list_tools
        return await list_tools(client.account_id, **payload, client=client)
    if action in {"list_agent_sessions", "create_agent_session", "rename_agent_session",
                  "delete_agent_session"}:
        import flow_agent

        return await getattr(flow_agent, action)(client.account_id, **payload, client=client)

    if action == "capabilities":
        from flow_capabilities import read_capabilities

        return await read_capabilities(client.account_id, payload["project_id"], client=client)
    if action == "user_settings":
        from flow_settings import get_user_settings

        return await get_user_settings(client.account_id, client=client)
    if action == "update_user_settings":
        from flow_settings import update_user_settings

        return await update_user_settings(client.account_id, **payload, client=client)
    if action == "credits":
        from datetime import datetime, timezone
        from flow_credits import parse_http_credits

        result = {"account_id":client.account_id, "status":"unavailable", "credits":None,
                  "generation_enabled":False, "source":"HTTP/nzlxg", "service_tier":None}
        try:
            result.update(credits=parse_http_credits(await client.rpc("nzlxg")), status="ok")
        except Exception:
            pass  # Falha de leitura não significa saldo zero nem sessão expirada.
        result["observed_at"] = datetime.now(timezone.utc).isoformat()
        return result
    if action == "project":
        from flow_projects import project_operation

        return await project_operation(client.account_id, **payload, client=client)
    if action == "delete_project":
        from flow_projects import delete_project

        return await delete_project(client.account_id, **payload, client=client)
    if action == "collection":
        from flow_collections import collection_operation

        return await collection_operation(client.account_id, **payload, client=client)
    if action == "move_assets":
        from flow_collections import move_assets

        return await move_assets(client.account_id, **payload, client=client)
    if action == "projects":
        query = payload.get("query", "")
        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Pesquisa inválida.")
        result = parse_projects(await client.rpc("UpteDb"))
        if query:
            needle = query.casefold()
            result["projects"] = [
                project for project in result["projects"]
                if needle in project["project_id"].casefold() or needle in project["title"].casefold()
            ]
        return {"account_id": client.account_id, "status": "ok", "source": "HTTP/UpteDb",
                **result}
    collection_id = payload.get("collection_id")
    if action == "assets" and collection_id is not None:
        from flow_collections import validate_collection_id

        collection_id = validate_collection_id(collection_id)
    project_id = validate_project(payload["project_id"])
    data = await client.rpc("Zzl0ze", project_id=project_id)
    if action == "collections":
        from flow_collections import parse_collections

        return {"account_id": client.account_id, "project_id": project_id,
                "status": "ok", "source": "HTTP/Zzl0ze",
                "collections": parse_collections(data, project_id), "complete": False}
    if action == "get_asset":
        from flow_edit import asset_details

        return asset_details(data, client.account_id, project_id, payload["media_id"])
    assets = parse_assets(data, project_id)
    if action == "assets":
        query = payload.get("query", "")
        kind = payload.get("kind")
        min_bytes = payload.get("min_bytes")
        max_bytes = payload.get("max_bytes")
        sort_by = payload.get("sort_by")
        sort_order = payload.get("sort_order", "asc")
        limit = payload.get("limit")

        if not isinstance(query, str) or len(query) > 200:
            raise ValueError("Pesquisa inválida.")
        if kind is not None and kind not in {"image", "video"}:
            raise ValueError("Tipo de mídia inválido.")
        if min_bytes is not None and (type(min_bytes) is not int or min_bytes < 0):
            raise ValueError("min_bytes deve ser um inteiro não negativo.")
        if max_bytes is not None and (type(max_bytes) is not int or max_bytes < 0):
            raise ValueError("max_bytes deve ser um inteiro não negativo.")
        if min_bytes is not None and max_bytes is not None and min_bytes > max_bytes:
            raise ValueError("min_bytes não pode ser maior que max_bytes.")
        if sort_by is not None and sort_by not in {"name", "bytes", "revision"}:
            raise ValueError("sort_by deve ser 'name', 'bytes' ou 'revision'.")
        sort_order = str(sort_order).lower().strip()
        if sort_order not in {"asc", "desc"}:
            raise ValueError("sort_order deve ser 'asc' ou 'desc'.")
        if limit is not None and (type(limit) is not int or limit <= 0):
            raise ValueError("limit deve ser um inteiro positivo.")

        if collection_id is not None:
            assets = [asset for asset in assets if asset.get("collection_id") == collection_id]

        if query:
            assets = [asset for asset in assets if query.casefold() in (asset.get("name") or "").casefold()]
        if kind:
            assets = [asset for asset in assets if asset.get("kind") == kind]
        if min_bytes is not None:
            assets = [asset for asset in assets if (asset.get("bytes") or 0) >= min_bytes]
        if max_bytes is not None:
            assets = [asset for asset in assets if (asset.get("bytes") or 0) <= max_bytes]

        if sort_by:
            reverse = (sort_order == "desc")
            if sort_by == "name":
                assets.sort(key=lambda a: (a.get("name") or "").casefold(), reverse=reverse)
            elif sort_by == "bytes":
                assets.sort(key=lambda a: a.get("bytes") or 0, reverse=reverse)
            elif sort_by == "revision":
                assets.sort(key=lambda a: a.get("revision") or 0, reverse=reverse)

        if limit is not None:
            assets = assets[:limit]

        return {"account_id": client.account_id, "project_id": project_id, "status": "ok",
                "source": "HTTP/Zzl0ze", "assets": assets, "complete": False,
                "scope": "Resposta inicial; paginação ainda não validada."}
    if action != "download_asset":
        raise ValueError("Operação HTTP inválida.")
    media_id = media_uuid(payload["media_id"])
    asset = next((item for item in assets if item["media_id"] == media_id), None)
    if asset is None:
        raise ValueError("Mídia ausente da resposta inicial.")
    from flow_video import image_suffix, original_image_url
    from flow_assets import video_record as generation_record
    from gflow_cli.api.transports.migrated_recover import _verify

    if asset["kind"] == "image":
        from flow_assets import image_download_url

        body = await client.download(original_image_url(image_download_url(data,project_id,media_id)), media_id)
        suffix = image_suffix(body)
    else:
        if "as29s" not in client.templates and "Zzl0ze" in client.templates:
            template = client.templates["Zzl0ze"]
            client.status_from_submit({"url":template["url"],"body":urlencode(template["form"],doseq=True),
                                       "headers":template["headers"]}, media_id)
        record = generation_record("as29s", await client.rpc("as29s", project_id=project_id,
            media_id=media_id, workflow_id=asset["workflow_id"]))
        if (record.media_id != media_id or not record.is_done or not record.video_url
                or record.workflow_id != asset["workflow_id"] or record.project_id != project_id):
            raise ValueError("Vídeo original ainda não disponível.")
        body = await client.download(record.video_url, media_id)
        _verify(body, expected=record.size_bytes, media_id=media_id)
        suffix = ".mp4"
    output = Path(os.environ.get("FLOW_MCP_OUTPUT", Path(__file__).parent / "downloads")).resolve()
    output.mkdir(parents=True, exist_ok=True)
    target = output / f"{media_id}{suffix}"
    target.write_bytes(body)
    return {"account_id": client.account_id, "project_id": project_id, "media_id": media_id,
            "status": "downloaded", "source": "HTTP", "path": str(target), "bytes": len(body)}


_workers = {}
_locks = {}


async def close_workers():
    """Encerrar os workers e suas sessões privadas quando o MCP fechar."""
    for account_id, process in list(_workers.items()):
        try:
            if process.stdin is not None:
                process.stdin.close()
            await asyncio.wait_for(process.wait(), 5)
        except (asyncio.TimeoutError, OSError):
            if process.returncode is None:
                process.kill()
                await process.wait()
        finally:
            _workers.pop(account_id, None)
    _locks.clear()


async def run_worker_operation(account_id, action, payload, env, root):
    lock = _locks.setdefault(account_id, asyncio.Lock())
    async with lock:
        process = _workers.get(account_id)
        if process is None or process.returncode is not None:
            process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()), "--worker", account_id,
                env=env, cwd=root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
            _workers[account_id] = process
        try:
            request = json.dumps({"action": action, "payload": payload or {}}).encode() + b"\n"
            process.stdin.write(request)
            await process.stdin.drain()
            batch_ids = payload.get("media_ids") if isinstance(payload, dict) else None
            batch_size = min(10, max(1, len(batch_ids))) if action == "edit_images" and isinstance(batch_ids, list) else 1
            refinements = payload.get("refinements") if isinstance(payload, dict) else None
            refine_size = min(3, max(1, len(refinements))) if isinstance(refinements, list) else 1
            timeout = 1260 * refine_size if action == "refine_video" else 1260 * batch_size if action == "edit_images" else 1260 if action in {"generate", "images", "edit_image", "edit_video", "extend_video", "upscale", "build_scene", "download_project", "export_scene"} or action == "manage_character" and (payload or {}).get("description") else 660 if action in {"connect", "import", "upload_asset", "agent_request"} else 240
            response = await asyncio.wait_for(process.stdout.readline(), timeout)
            return json.loads(response)
        except (asyncio.TimeoutError, ValueError, OSError):
            if process.returncode is None:
                process.kill()
                await process.wait()
            _workers.pop(account_id, None)
            return {"status": "http_worker_error", "message": "Consulta HTTP inconclusiva; não houve reenvio automático."}


async def worker(account_id, input_stream, output_stream):
    from flow_accounts import validate_account

    validate_account(account_id)
    client = FlowHTTP(account_id, resident=True)
    try:
        while True:
            raw = await asyncio.to_thread(input_stream.readline, 1024 * 1024 + 1)
            if not raw:
                break
            try:
                request = json.loads(raw)
                if request["action"] in {"connect", "status", "import"}:
                    from flow_accounts import account_operation

                    await client.close()  # Login/verificação exclusivos no mesmo perfil.
                    client = FlowHTTP(account_id, resident=True)
                    result = await account_operation(request["action"], account_id, session=request.get("payload"))
                else:
                    result = await http_operation(client, request["action"], request.get("payload") or {})
            except Exception as exc:
                result = {"status": "http_error", "error_type": type(exc).__name__,
                          "message": "Falha HTTP; dados da sessão e respostas privadas foram omitidos."}
            output_stream.write(json.dumps(result) + "\n")
            output_stream.flush()
    finally:
        await client.close()


if __name__ == "__main__":
    original_output = sys.stdout
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
        asyncio.run(worker(sys.argv[2], sys.stdin, original_output))
