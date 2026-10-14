"""Worker privado por conta: HTTP e Chrome headless residente para o preparo normal."""

import asyncio
from contextlib import asynccontextmanager, redirect_stderr, redirect_stdout
import json
import os
from pathlib import Path
import sys
import uuid
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

# Leituras sem efeito no Flow: podem ser repetidas uma vez após renovar os cookies.
READ_ONLY_RPCS = {"UpteDb", "Zzl0ze", "Yizz8d", "nzlxg", "HTrJv", "as29s", "mrlkwd", "tRARke", "GN0Bre"}
SESSION_LOST = ("A conta não está autenticada no Flow (redirecionada para o login ou para a página "
                "de apresentação); refaça o login da conta antes de continuar.")


class AgentOnlyComposer(ValueError):
    """Conta com compositor só de Agent (atribuído pelo Google): sem envio direto; gerar via Agent."""


async def prepare_generation(client, project_id, captcha_action):
    """Preparo de geração; no compositor só de Agent, liga e desliga o modo Agent e tenta uma vez mais.

    Ligar e desligar `agent_mode_enabled` devolve o compositor clássico (validado em 08/10/2026).
    Se persistir, AgentOnlyComposer segue para o chamador.
    """
    try:
        return await client.prepare("Zzl0ze", project_id=project_id, captcha_action=captcha_action)
    except AgentOnlyComposer as first:
        from flow_settings import update_user_settings

        for enabled in (True, False):
            result = await update_user_settings(client.account_id, agent_mode_enabled=enabled, client=client)
            if result.get("status") != "updated":
                raise AgentOnlyComposer(f"{first} A troca do modo Agent ({enabled}) não foi confirmada: "
                                        f"{result.get('status')} {result.get('message') or ''}".strip()) from None
        try:
            return await client.prepare("Zzl0ze", project_id=project_id, captcha_action=captcha_action)
        except AgentOnlyComposer as second:
            raise AgentOnlyComposer(f"{second} (persistiu após ligar e desligar o modo Agent)") from None


def require_flow_page(page):
    """Erro claro quando o Google redireciona para login em vez de abrir o Flow.

    Deslogado, o Flow manda para flow.google.com/about (observado na Pi em 05/10/2026)
    ou para o login do Google.
    """
    url = getattr(page, "url", None)
    if not isinstance(url, str):
        return
    parts = urlsplit(url)
    if (parts.hostname or "flow.google.com") != "flow.google.com" or parts.path.startswith("/about"):
        raise ValueError(SESSION_LOST)


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

    async def refresh_session(self):
        """Recopiar os cookies do Chrome, que o Google rotaciona; mantém os modelos de RPC."""
        from flow_browser import account_page

        pages = self.browser.page() if self.browser is not None else account_page(self.account_id)
        async with pages as page:
            await page.goto("https://flow.google.com/", wait_until="domcontentloaded", timeout=45000)
            await page.wait_for_timeout(2000)
            require_flow_page(page)
            await self.session_from_page(page)

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
        try:
            captured = await asyncio.wait_for(found, 30)
        except asyncio.TimeoutError:
            require_flow_page(page)
            raise ValueError(f"O site não emitiu o pedido esperado ({', '.join(sorted(rpc_ids))}) em 30 s após "
                             "o clique; a interface do Flow pode ter mudado. Nada foi enviado.") from None
        await self.session_from_page(page)
        return captured

    async def send_submit(self, captured):
        """Um único POST HTTP, sem retries nem recuperação por novo envio."""
        from gflow_cli.api.transports.batchexecute import parse_frames

        validate_rpc_url(captured["url"])
        response = await self.client.post(captured["url"], content=captured["body"],
                                          headers=captured["headers"], timeout=600)
        if response.status_code != 200:
            raise ValueError(f"Envio HTTP inconclusivo (HTTP {response.status_code}); não reenviar automaticamente.")
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
                # Até 60 s pela consulta; a cada 5 s confere se a conta foi mandada para o login.
                for _ in range(12):
                    try:
                        await asyncio.wait_for(asyncio.shield(found), 5)
                        break
                    except asyncio.TimeoutError:
                        require_flow_page(page)
                else:
                    if rpc_id == "as29s":
                        raise asyncio.TimeoutError
                    raise ValueError(f"A página do Flow não fez a consulta {rpc_id} em 60 s (site lento ou "
                                     "interface mudada); nada foi enviado.")
                captcha = None
                if captcha_action in {"IMAGE_GENERATION", "VIDEO_GENERATION"}:
                    from gflow_cli.api.transports.migrated_composer import MigratedComposer, IMAGE_SUBMIT_RPC, SUBMIT_RPCS

                    # O frontend prepara o reCAPTCHA normal; nenhum pedido dele é enviado.
                    # Chamadas diretas a enterprise.execute são marcadas pelo próprio site.
                    from gflow_cli.errors import FlowAgentUiError

                    composer = MigratedComposer()
                    # Espera o compositor e sai do modo Agent (padrão em contas novas), como o gflow-cli faz.
                    try:
                        await composer.ensure_editor(page, project_id)
                    except FlowAgentUiError:
                        # O token do chat do Agent é recusado no envio direto (PUBLIC_ERROR_UNUSUAL_ACTIVITY).
                        raise AgentOnlyComposer("Esta conta usa o compositor só de Agent (atribuído pelo Google); a "
                                                "geração direta não é possível nela. Nada foi enviado.") from None
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
                require_flow_page(page)
                if rpc_id == "as29s":
                    raise ValueError("Vídeo original ainda não disponível.") from None
                raise
            finally:
                page.remove_listener("response", observe)
        # Página de preparo fechada antes do POST; worker residente mantém só o contexto.
        return captcha

    async def rpc(self, rpc_id, project_id=None, media_id=None, workflow_id=None, params=None,
                  *, _refreshed=False):
        from gflow_cli.api.transports.batchexecute import parse_frames

        explicit_params = params

        if rpc_id == "nzlxg" and params is None and rpc_id not in self.templates:
            # Saldo usa a sessão da listagem de projetos: carregar a página basta, sem clicar no
            # menu da conta (o clique falhava após a verificação de login no Linux).
            params = []
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
            if rpc_id in READ_ONLY_RPCS and not _refreshed and self.client is not None:
                # Cookies copiados há horas podem ter sido rotacionados; leitura é segura de repetir.
                await self.refresh_session()
                return await self.rpc(rpc_id, project_id, media_id, workflow_id, explicit_params,
                                      _refreshed=True)
            raise ValueError(f"Flow respondeu HTTP {response.status_code} a {rpc_id}; a sessão pode "
                             "exigir novo login (flow_account_status).")
        payloads = [payload for rid, payload in parse_frames(response.text) if rid == rpc_id]
        if len(payloads) != 1 or payloads[0] is None:
            if rpc_id == "as29s" and media_id:
                from flow_assets import MediaAbsent

                raise MediaAbsent("Mídia esperada ausente do acompanhamento.")
            raise ValueError(f"O Flow não retornou dados para {rpc_id}"
                             + (" (projeto inexistente ou de outra conta?)" if project_id else "")
                             + "; confira os IDs e a conta.")
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
    if action == "quote_images":
        from flow_video import quote_images

        return await quote_images(client.account_id, **payload, client=client)
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
        except Exception as exc:
            from flow_errors import error_fields

            result.update(error_fields(exc))  # Falha de leitura não significa saldo zero nem sessão expirada.
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
                if needle in project["project_id"].casefold() or needle in (project["title"] or "").casefold()
            ]
        return {"account_id": client.account_id, "status": "ok", "source": "HTTP/UpteDb",
                **result}
    collection_id = payload.get("collection_id")
    if action == "assets" and collection_id is not None:
        from flow_collections import validate_collection_id

        collection_id = validate_collection_id(collection_id)
    project_id = validate_project(payload["project_id"])
    if action in {"get_asset", "download_asset"}:
        media_uuid(payload["media_id"])  # ID inválido não precisa consultar o Flow.
    data = await client.rpc("Zzl0ze", project_id=project_id)
    if action == "collections":
        from flow_collections import parse_collections

        return {"account_id": client.account_id, "project_id": project_id,
                "status": "ok", "source": "HTTP/Zzl0ze",
                "collections": parse_collections(data, project_id), "complete": False}
    if action == "get_asset":
        from flow_edit import asset_details

        return asset_details(data, client.account_id, project_id, payload["media_id"])
    skipped = []
    assets = parse_assets(data, project_id, skipped)
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
                "scope": "Resposta inicial; paginação ainda não validada.",
                **({"unrecognized_media": skipped} if skipped else {})}
    if action != "download_asset":
        raise ValueError("Operação HTTP inválida.")
    media_id = media_uuid(payload["media_id"])
    asset = next((item for item in assets if item["media_id"] == media_id), None)
    if asset is None:
        if any(item["media_id"] == media_id for item in skipped):
            raise ValueError("Mídia presente, mas em formato que o MCP ainda não reconhece; o Flow pode ter mudado.")
        raise ValueError("Mídia ausente da resposta inicial do projeto (ainda processando, em outro "
                         "projeto/conta, ou além da primeira página).")
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
    from flow_video import downloads_dir

    output = downloads_dir()
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


# Operações longas (geração + acompanhamento de até 20 min, downloads em lote).
_LONG_ACTIONS = {"generate", "images", "edit_image", "edit_video", "extend_video", "upscale",
                 "build_scene", "download_project", "export_scene"}
_MEDIUM_ACTIONS = {"connect", "import", "upload_asset", "agent_request"}
# Respostas grandes (listagens de projetos/ativos) passam do limite padrão de 64 KiB por linha.
_WORKER_LINE_LIMIT = 64 * 1024 * 1024


def worker_timeout(action, payload) -> int:
    """Prazo em segundos para a resposta do worker a uma ação."""
    payload = payload if isinstance(payload, dict) else {}
    if action == "refine_video" and isinstance(payload.get("refinements"), list):
        return 1260 * min(3, max(1, len(payload["refinements"])))
    if action == "edit_images" and isinstance(payload.get("media_ids"), list):
        return 1260 * min(10, max(1, len(payload["media_ids"])))
    if action in _LONG_ACTIONS or action in {"refine_video", "edit_images"} or (
            action == "manage_character" and payload.get("description")):
        return 1260
    return 660 if action in _MEDIUM_ACTIONS else 240


async def _start_worker(account_id, env, root):
    process = await asyncio.create_subprocess_exec(sys.executable, str(Path(__file__).resolve()), "--worker", account_id,
        env=env, cwd=root, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL, limit=_WORKER_LINE_LIMIT)
    _workers[account_id] = process
    return process


async def _stop_worker(account_id, process):
    if process.returncode is None:
        process.kill()
        await process.wait()
    _workers.pop(account_id, None)


# O worker de cada conta é serial: espera curta pela vez; depois responde "ocupada" em vez de travar.
BUSY_GRACE_SECONDS = 30
_running = {}


async def run_worker_operation(account_id, action, payload, env, root):
    lock = _locks.setdefault(account_id, asyncio.Lock())
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(lock.acquire(), BUSY_GRACE_SECONDS)
    except asyncio.TimeoutError:
        running, started = _running.get(account_id, (None, loop.time()))
        return {"status": "account_busy", "action": action, "running_action": running,
                "running_seconds": round(loop.time() - started),
                "message": f"A conta está ocupada com outra operação ({running}); nada foi enviado."}
    _running[account_id] = (action, loop.time())
    try:
        return await _run_locked(account_id, action, payload, env, root)
    finally:
        _running.pop(account_id, None)
        lock.release()


async def _run_locked(account_id, action, payload, env, root):
    request_id = uuid.uuid4().hex
    request = json.dumps({"id": request_id, "action": action, "payload": payload or {}}).encode() + b"\n"
    process = _workers.get(account_id)
    for attempt in range(2):
        if process is None or process.returncode is not None:
            process = await _start_worker(account_id, env, root)
        try:
            process.stdin.write(request)
            await process.stdin.drain()
            break
        except (OSError, RuntimeError):
            # Worker morto antes de receber o pedido: nada foi enviado ao Flow; reiniciar é seguro.
            await _stop_worker(account_id, process)
            process = None
            if attempt:
                return {"status": "http_worker_error", "action": action,
                        "message": "Não foi possível iniciar o worker da conta; nada foi enviado ao Flow."}
    loop = asyncio.get_running_loop()
    deadline = loop.time() + worker_timeout(action, payload)
    try:
        while True:
            response = await asyncio.wait_for(process.stdout.readline(), max(0, deadline - loop.time()))
            if not response:
                raise EOFError
            result = json.loads(response)
            # Resposta de uma chamada cancelada pelo cliente (recusa/timeout) fica no pipe; descartá-la
            # evita entregá-la a este pedido. A tarefa dela continua persistida (flow_list_jobs).
            if result.pop("request_id", request_id) == request_id:
                return result
    except (asyncio.TimeoutError, EOFError, ValueError, OSError) as exc:
        await _stop_worker(account_id, process)
        reason = ("tempo esgotado" if isinstance(exc, asyncio.TimeoutError)
                  else "worker encerrado durante a operação" if isinstance(exc, EOFError)
                  else "resposta ilegível do worker")
        return {"status": "http_worker_error", "action": action,
                "message": f"Worker da conta sem resposta ({reason}) e reiniciado; não houve reenvio automático."}


# Chrome ocioso é fechado (libera memória e o lease do perfil); o próximo pedido o reabre.
WORKER_IDLE_SECONDS = float(os.environ.get("FLOW_MCP_WORKER_IDLE_SECONDS", "900"))


async def worker(account_id, input_stream, output_stream):
    from flow_accounts import validate_account

    validate_account(account_id)
    client = FlowHTTP(account_id, resident=True)
    try:
        while True:
            read = asyncio.ensure_future(asyncio.to_thread(input_stream.readline, 1024 * 1024 + 1))
            while not (await asyncio.wait({read}, timeout=WORKER_IDLE_SECONDS))[0]:
                browser = getattr(client, "browser", None)
                # Confirmação de upload pendente depende da página aberta: não fechar.
                if getattr(client, "pending_upload", None) is None and getattr(browser, "context", None) is not None:
                    await client.close()
                    client = FlowHTTP(account_id, resident=True)
            raw = read.result()
            if not raw:
                break
            request = None
            try:
                try:
                    request = json.loads(raw)
                except ValueError:
                    raise ValueError("Pedido ao worker ilegível ou maior que 1 MiB.") from None
                if request["action"] in {"connect", "status", "import"}:
                    from flow_accounts import account_operation

                    await client.close()  # Login/verificação exclusivos no mesmo perfil.
                    client = FlowHTTP(account_id, resident=True)
                    result = await account_operation(request["action"], account_id, session=request.get("payload"))
                else:
                    result = await http_operation(client, request["action"], request.get("payload") or {})
            except Exception as exc:
                from flow_errors import error_fields

                # Só mensagens escritas pelo MCP; respostas privadas do Flow são omitidas.
                result = {"status": "http_error", "action": request.get("action") if isinstance(request, dict) else None,
                          **error_fields(exc)}
            if isinstance(request, dict) and "id" in request and isinstance(result, dict):
                result["request_id"] = request["id"]
            # default=str: um valor não serializável (ex.: Path) não pode derrubar o worker.
            output_stream.write(json.dumps(result, default=str) + "\n")
            output_stream.flush()
    finally:
        await client.close()


if __name__ == "__main__":
    # O worker roda do módulo importado: como __main__, suas classes (ex.: AgentOnlyComposer) seriam
    # cópias distintas das que flow_video/flow_edit importam, e os `except` delas não as pegariam.
    import flow_http

    original_output = sys.stdout
    with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
        asyncio.run(flow_http.worker(sys.argv[2], sys.stdin, original_output))
