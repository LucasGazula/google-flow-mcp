"""MCP stdio: contas, saldo e geração de um vídeo com orçamento explícito."""

import asyncio
from contextlib import asynccontextmanager
import hmac
import json
import os
from pathlib import Path
import sys
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from flow_accounts import validate_account
from flow_session import SessionBridge

root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles")).resolve()
root.mkdir(parents=True, exist_ok=True, mode=0o700)
# Ferramentas locais e workers devem ler o mesmo diretório privado do MCP.
os.environ["GFLOW_CLI_HOME"] = str(root)
from gflow_cli.config import get_settings
get_settings.cache_clear()

bridge: SessionBridge | None = None


@asynccontextmanager
async def lifespan(server):
    try:
        yield {}
    finally:
        if bridge is not None:
            bridge.close()
        from flow_http import close_workers

        await close_workers()


INSTRUCTIONS = """Contas são identificadas pelo e-mail Google (flow_list_accounts).
Antes de qualquer ferramenta que gaste créditos, se houver mais de uma conta e o
usuário não tiver indicado qual usar nesta solicitação, pergunte qual conta usar.
Mostre e-mail, saldo (flow_get_credits) e cotação (flow_quote_video) e aguarde a
confirmação. Nunca escolha a conta por conta própria."""

mcp = MCPServer("google-flow-mcp", instructions=INSTRUCTIONS, lifespan=lifespan)


def resolve_account(account_id: str) -> str:
    """Aceitar e-mail da conta ou apelido do perfil; devolver o apelido."""
    from gflow_cli.profile_store import read_account_file

    if "@" not in account_id:
        return validate_account(account_id)
    matches = [d.name.removeprefix("profile_") for d in root.glob("profile_*")
               if (read_account_file(d) or "").casefold() == account_id.strip().casefold()]
    if len(matches) != 1:
        raise ValueError("E-mail não corresponde a uma conta conectada; consulte flow_list_accounts.")
    return validate_account(matches[0])


async def run_account_operation(action: str, account_id: str = "", session: dict | None = None) -> dict[str, Any]:
    if action != "list":
        try:
            account_id = resolve_account(account_id)
        except ValueError as exc:
            raise ToolError(str(exc)) from None
    result = await _run_account_operation(action, account_id, session)
    if action != "list" and isinstance(result, dict):
        from gflow_cli.profile_store import read_account_file

        result.setdefault("email", read_account_file(root / f"profile_{account_id}"))
    return result


async def _run_account_operation(action: str, account_id: str = "", session: dict | None = None) -> dict[str, Any]:
    root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles")).resolve()
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Evita configuração gflow herdada, HARs e .env de outro projeto.
    env = {k: v for k, v in os.environ.items() if not k.startswith("GFLOW_")}
    env.update(GFLOW_CLI_HOME=str(root), GFLOW_CLI_UPDATE_CHECK="false",
               GFLOW_CLI_INCIDENT_CAPTURE="false", GFLOW_CLI_AUTH_LOGIN_TIMEOUT="600")
    if action not in {"list", "job", "jobs"}:
        from flow_http import run_worker_operation

        return await run_worker_operation(account_id, action, session, env, root)
    process = await asyncio.create_subprocess_exec(
        sys.executable, str(Path(__file__).with_name("flow_accounts.py")), action, account_id,
        env=env, cwd=root, stdin=asyncio.subprocess.PIPE if session is not None else asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(
            process.communicate(json.dumps(session).encode() if session is not None else None),
            timeout=1260 if action in {"generate", "images", "edit_image"} else 210 if action in {"recover", "upload_image", "download_asset", "upscale", "download_project"} else 660 if action in {"connect", "import"} else 90,
        )
        return json.loads(stdout)
    except asyncio.TimeoutError:
        return {"status": "timeout", "generation_enabled": False,
                "message": "Tempo esgotado; consulte a conta antes de tentar novamente."}
    except (ValueError, OSError):
        return {"status": "backend_error", "generation_enabled": False}
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()


@mcp.tool()
def flow_status() -> dict[str, Any]:
    """Diagnóstico local: backend instalado não significa sessão autenticada."""
    return {"backend_status": "accounts_available", "backend": "gflow-cli==0.79.1",
            "generation_enabled": True,
            "message": "Vídeo/imagem com orçamento explícito; suporte observado em docs/IMPLEMENTACAO-FLOW.md."}


@mcp.tool()
async def flow_list_accounts() -> dict[str, Any]:
    """Listar contas conectadas com e-mail e apelido do perfil; sessão salva não prova autenticação."""
    return await run_account_operation("list")


@mcp.tool()
async def flow_connect_account(account_id: str) -> dict[str, Any]:
    """Abrir Chrome dedicado para login humano (até 10 min), sem gastar créditos.

    Chrome deve estar instalado no mesmo sistema do MCP. O apelido nomeia o perfil novo;
    depois a conta pode ser indicada pelo e-mail em account_id.
    """
    return await run_account_operation("connect", account_id)


@mcp.tool()
async def flow_account_status(account_id: str) -> dict[str, Any]:
    """Verificar sessão Flow sem geração; falha de verificação difere de falta de login."""
    return await run_account_operation("status", account_id)


@mcp.tool()
async def flow_get_credits(account_id: str) -> dict[str, Any]:
    """Consultar saldo Flow sem geração. credits=null significa consulta indisponível.

    Usa o RPC do saldo no Flow atual. Chrome prepara a sessão quando necessário;
    consultas seguintes reutilizam o worker HTTP sem ler o saldo da interface.
    Não estima custo nem comprova suporte a geração. Informe o e-mail ou apelido da conta.
    """
    return await run_account_operation("credits", account_id)


@mcp.tool()
async def flow_generate_video(account_id: str, prompt: str, max_credits: int,
                              project_id: str | None = None, model: str = "veo-lite",
                              aspect: str = "16:9", duration_seconds: int = 8,
                              start_image: str | None = None, end_image: str | None = None,
                              reference_images: list[str] | None = None,
                              reference_asset_ids: list[str] | None = None, count: int = 1,
                              resolution: str = "720p",
                              start_image_asset_id: str | None = None,
                              end_image_asset_id: str | None = None,
                              voice: str | None = None,
                              character_ids: list[str] | None = None) -> dict[str, Any]:
    """Gerar e baixar 1–4 vídeos em resolução disponível no catálogo (360p, 720p, 1080p ou 4k).
    Consome créditos.

    Modelos: veo-lite, veo-fast, veo-quality, omni-flash. Proporção 16:9 ou 9:16.
    Modelo, formato, resolução e custo são conferidos no catálogo HTTP; opção ausente impede o envio.
    start_image/end_image são caminhos locais; start_image_asset_id e
    end_image_asset_id reutilizam imagens do projeto como quadros inicial/final;
    reference_images usa arquivos locais; reference_asset_ids reutiliza imagens
    do projeto, sem novo upload.
    Vídeo não é aceito como referência pelo Flow; para transformar um clipe use
    flow_edit_video com create_new_workflow=True.
    voice usa um preset de flow_list_voice_presets; exige omni-flash com
    referências de imagem ou personagens, como na interface (sem ingrediente a
    voz é ignorada). character_ids (1–3, de flow_list_characters) usa personagens
    do projeto como ingredientes; exige omni-flash.
    Combinações inválidas são recusadas.
    Use após autorização de gasto. max_credits é o teto para esta geração;
    custo desconhecido ou acima do teto impede o envio. Aguarda até 20 minutos.
    Tarefa persistida em profiles/jobs. Não reenviar se o resultado for incerto.
    project_id opcional reutiliza projeto; sem ele cria um projeto Flow.
    """
    return await run_account_operation("generate", account_id,
        {"prompt": prompt, "max_credits": max_credits, "project_id": project_id,
         "model": model, "aspect": aspect, "duration_seconds": duration_seconds,
         "start_image": start_image, "end_image": end_image, "reference_images": reference_images,
         "reference_asset_ids": reference_asset_ids, "count": count, "resolution": resolution,
         "start_image_asset_id": start_image_asset_id, "end_image_asset_id": end_image_asset_id,
         "voice": voice, "character_ids": character_ids})


@mcp.tool()
async def flow_upscale_video(account_id: str, project_id: str, media_id: str,
                             target_resolution: str = "720p") -> dict[str, Any]:
    """Aprimorar um vídeo do projeto para 720p ou 1080p pelo Flow, sem créditos.

    Envia uma vez; chame novamente com os mesmos IDs para recuperar e baixar.
    O vídeo original e seu workflow são preservados.
    """
    return await run_account_operation("upscale_video_native", account_id,
                                       {"project_id": project_id, "media_id": media_id,
                                        "target_resolution": target_resolution})


@mcp.tool()
async def flow_edit_video(account_id: str, project_id: str, media_id: str, prompt: str,
                          max_credits: int, aspect: str = "16:9", segment_start: float = 0,
                          segment_end: float | None = None,
                          reference_images: list[str] | None = None,
                          reference_asset_ids: list[str] | None = None,
                          duration_seconds: int = 8, resolution: str = "720p",
                          create_new_workflow: bool = False) -> dict[str, Any]:
    """Editar até 10s de vídeo com Omni Flash por HTTP, preservando versões.

    Trecho em segundos; sem segment_end usa o fim do vídeo. Origem deve pertencer
    à conta/projeto. O prompt pode pedir alterações de objetos ou câmera. Para
    iterar, passe como media_id a saída da chamada anterior; cada chamada cota
    uma edição. Custo confirmado pelo catálogo, sem reenvio automático.
    reference_images usa arquivos locais; reference_asset_ids reutiliza imagens
    deste projeto. Vídeo não é aceito como referência pelo Flow.
    Até dez referências ao todo. Duração/resolução devem existir no catálogo.
    create_new_workflow=True salva a edição em um histórico separado, como ao
    anexar um clipe ao compositor; False mantém o histórico da origem.
    """
    return await run_account_operation("edit_video", account_id, {"project_id":project_id,
        "source_media_id":media_id, "prompt":prompt, "max_credits":max_credits,
        "model":"omni-flash", "aspect":aspect, "segment_start":segment_start,
        "segment_end":segment_end, "reference_images":reference_images,
        "reference_asset_ids":reference_asset_ids, "duration_seconds":duration_seconds,
        "resolution":resolution,
        "create_new_workflow":create_new_workflow})


@mcp.tool()
async def flow_refine_video(account_id: str, project_id: str, media_id: str,
                            refinements: list[str], max_credits: int,
                            aspect: str = "16:9",
                            reference_images: list[str] | None = None,
                            reference_asset_ids: list[str] | None = None,
                            duration_seconds: int = 8,
                            resolution: str = "720p") -> dict[str, Any]:
    """Aplicar de um a três turnos de refinamento a um vídeo já editado.

    Use o media_id retornado por flow_edit_video; cada turno parte da saída
    anterior no mesmo workflow. max_credits cobre a cadeia inteira. A operação
    para no primeiro resultado incerto ou incompleto; cada job fica persistido.
    Referências locais de imagem são enviadas uma vez e reutilizadas por ID
    nos demais turnos.
    Vídeo não é aceito como referência pelo Flow; para transformar um clipe use
    flow_edit_video com create_new_workflow=True.
    """
    return await run_account_operation("refine_video", account_id, {
        "project_id":project_id, "media_id":media_id, "refinements":refinements,
        "max_credits":max_credits, "aspect":aspect, "reference_images":reference_images,
        "reference_asset_ids":reference_asset_ids, "duration_seconds":duration_seconds,
        "resolution":resolution})


@mcp.tool()
async def flow_quote_video(account_id: str, project_id: str, operation: str = "generate",
                           media_id: str | None = None, model: str = "veo-lite",
                           aspect: str = "16:9", duration_seconds: int = 8,
                           resolution: str = "720p", count: int = 1,
                           start_image_asset_id: str | None = None,
                           end_image_asset_id: str | None = None,
                           reference_asset_ids: list[str] | None = None,
                           character_ids: list[str] | None = None) -> dict[str, Any]:
    """Cotar geração, edição ou extensão de vídeo pelo catálogo HTTP, sem enviar nem gastar.

    operation: generate, edit (Omni Flash, exige media_id) ou extend (exige media_id).
    Usa as mesmas validações do envio real e não cria tarefa. quoted_credits é o
    preço do catálogo para a combinação; credits_before é o saldo lido agora.
    """
    if operation not in {"generate", "edit", "extend"}:
        raise ToolError("Operação de cotação inválida.")
    if operation != "generate" and not media_id:
        raise ToolError("Edição/extensão exige media_id.")
    payload = {"project_id":project_id, "model":"omni-flash" if operation == "edit" else model,
               "aspect":aspect, "duration_seconds":duration_seconds, "resolution":resolution,
               "count":count, "start_image_asset_id":start_image_asset_id,
               "end_image_asset_id":end_image_asset_id, "reference_asset_ids":reference_asset_ids,
               "character_ids":character_ids, "operation":operation}
    if operation != "generate":
        payload["source_media_id"] = media_id
    result = await run_account_operation("quote_video", account_id, payload)
    return {key: result.get(key) for key in ("account_id", "project_id", "status", "error_type",
            "operation", "model", "duration_seconds", "resolution", "aspect", "count",
            "quote", "quoted_credits", "credits_before", "email")} | {"operation": operation}


@mcp.tool()
async def flow_extend_video(account_id: str, project_id: str, media_id: str, prompt: str,
                            max_credits: int, model: str = "veo-lite",
                            aspect: str = "16:9", duration_seconds: int = 8) -> dict[str, Any]:
    """Estender um vídeo Veo existente via HTTP e baixar a nova versão.

    Modelo/duração/custo conferidos no catálogo. Recuperação mantém a conta e o
    workflow originais, sem outra geração. Consome créditos até max_credits.
    """
    return await run_account_operation("extend_video", account_id, {"project_id":project_id,
        "source_media_id":media_id, "prompt":prompt, "max_credits":max_credits,
        "model":model, "aspect":aspect, "duration_seconds":duration_seconds})


@mcp.tool()
async def flow_get_asset(account_id: str, project_id: str, media_id: str) -> dict[str, Any]:
    """Ler o ativo e versões de imagem/vídeo da resposta inicial, sem URLs assinadas.

    complete=false: a paginação e o histórico completo ainda não foram validados.
    """
    return await run_account_operation("get_asset", account_id, {"project_id":project_id,"media_id":media_id})


@mcp.tool()
async def flow_crop_image(account_id: str, project_id: str, media_id: str,
                          coordinates: list[float]) -> dict[str, Any]:
    """Recortar imagem via HTTP, preservar versões e baixar o resultado.

    coordinates=[topo, esquerda, base, direita], valores normalizados de 0 a 1.
    Não gera imagem por IA nem altera o original. Resultado incerto não é reenviado.
    """
    return await run_account_operation('crop_image',account_id,
        {'project_id':project_id,'media_id':media_id,'coordinates':coordinates})


@mcp.tool()
async def flow_upscale_image(account_id: str, project_id: str, media_id: str,
                             target_resolution: str = "2k",
                             upload_to_flow: bool = False) -> dict[str, Any]:
    """Aumentar uma imagem gerada pelo Flow para 2K nativos e salvar localmente.

    Catálogo precisa confirmar custo zero; 4K ainda é bloqueado nesta implementação.
    upload_to_flow=True também envia o arquivo final ao projeto. Repetir os mesmos
    IDs reutiliza o arquivo concluído, sem reenviar o upscale ou upload. Um envio
    incerto permanece registrado; falha no upload preserva o arquivo local.
    """
    return await run_account_operation("upscale_image_native", account_id, {
        "project_id": project_id, "media_id": media_id,
        "target_resolution": target_resolution, "upload_to_flow": upload_to_flow,
    })


@mcp.tool()
async def flow_edit_image(account_id: str, project_id: str, media_id: str, prompt: str,
                          max_credits: int, model: str = "nano-banana-2", aspect: str = "1:1",
                          count: int = 1, reference_images: list[str] | None = None,
                          selection: list[list[float]] | None = None,
                          drawings: list[dict[str, Any]] | None = None,
                          reference_asset_ids: list[str] | None = None) -> dict[str, Any]:
    """Editar uma imagem atual e baixar até quatro resultados ligados à origem.

    Modelos: nano-banana-2, nano-banana-2-lite, nano-pro. Lite exige seu ID no catálogo.
    Custo conferido para todo o lote antes do envio. media_id deve identificar a versão atual.
    Retorna tarefa persistida; nunca reenviar quando o resultado for incerto.
    reference_images: caminhos locais; reference_asset_ids: imagens já no projeto.
    selection: polígono de pares [x,y] entre 0 e 1;
    para caixa use quatro cantos. drawings: traços com points, color (#RRGGBB) e width
    em pixels. Seleção/desenho são enviados como imagem anotada, como no editor Flow;
    orientam o modelo e não garantem preservação exata dos pixels fora da região.
    """
    return await run_account_operation("edit_image", account_id, {"project_id":project_id,
        "media_id":media_id,"prompt":prompt,"max_credits":max_credits,"model":model,
        "aspect":aspect,"count":count,"reference_images":reference_images,
        "selection":selection,"drawings":drawings,
        "reference_asset_ids":reference_asset_ids})


@mcp.tool()
async def flow_edit_images(account_id: str, project_id: str, media_ids: list[str], prompt: str,
                           max_credits: int, model: str = "nano-banana-2",
                           aspect: str = "1:1",
                           reference_asset_ids: list[str] | None = None) -> dict[str, Any]:
    """Aplicar o mesmo prompt a 2–10 imagens do projeto e baixar as versões.

    Modelos: nano-banana-2, nano-banana-2-lite, nano-pro. Lite usa o model_id do catálogo.
    Cota o lote inteiro antes do primeiro envio. Cada imagem vira tarefa persistida;
    interrompe se uma submissão ficar incerta. Referências usam imagens do mesmo projeto.
    Use flow_recover_job pelos IDs retornados.
    """
    return await run_account_operation("edit_images", account_id, {"project_id":project_id,
        "media_ids":media_ids,"prompt":prompt,"max_credits":max_credits,
        "model":model,"aspect":aspect,"reference_asset_ids":reference_asset_ids})


@mcp.tool()
async def flow_list_assets(account_id: str, project_id: str, query: str = "",
                           kind: str | None = None,
                           min_bytes: int | None = None,
                           max_bytes: int | None = None,
                           sort_by: str | None = None,
                           sort_order: str = "asc",
                           limit: int | None = None,
                           collection_id: str | None = None) -> dict[str, Any]:
    """Ler mídia da resposta inicial do projeto com filtros e ordenação avançados.

    query filtra nomes. kind filtra por 'image' ou 'video'. collection_id limita
    à associação direta com essa coleção.
    min_bytes e max_bytes filtram por tamanho em bytes.
    sort_by aceita 'name', 'bytes' ou 'revision'. sort_order aceita 'asc' ou 'desc'.
    limit limita a quantidade máxima de itens retornados.
    """
    return await run_account_operation("assets", account_id, {
        "project_id": project_id, "query": query, "kind": kind, "collection_id": collection_id,
        "min_bytes": min_bytes, "max_bytes": max_bytes,
        "sort_by": sort_by, "sort_order": sort_order, "limit": limit
    })


@mcp.tool()
async def flow_search_assets(account_id: str, query: str, kind: str | None = None,
                             limit: int = 100) -> dict[str, Any]:
    """Pesquisar ativos pelo nome ou ID nos projetos retornados pela conta.

    A leitura é somente HTTP. limit aceita 1–500 resultados (padrão 100);
    complete permanece false porque a paginação de ativos não foi validada.
    """
    return await run_account_operation("search_assets", account_id, {
        "query": query, "kind": kind, "limit": limit,
    })


@mcp.tool()
async def flow_upload_image(account_id: str, project_id: str, path: str) -> dict[str, Any]:
    """Enviar arquivo de imagem local ao projeto e confirmar seu ID. Não gera mídia.

    O arquivo permanece no Flow; nome de upload exclusivo evita selecionar outro arquivo.
    """
    return await run_account_operation("upload_image", account_id, {"project_id": project_id, "path": path})


@mcp.tool()
async def flow_upload_asset(account_id: str, project_id: str, path: str) -> dict[str, Any]:
    """Enviar imagem ou vídeo local ao projeto Flow, sem gerar mídia.

    O primeiro vídeo pode exigir confirmação de direitos pelo titular no site.
    """
    return await run_account_operation("upload_asset", account_id, {"project_id": project_id, "path": path})


@mcp.tool()
async def flow_confirm_upload(account_id: str, confirmation_id: str, approve: bool) -> dict[str, Any]:
    """Aceitar ou recusar um aviso de direitos de upload pendente nesta conta.

    approve=true só após o agente obter confirmação explícita do titular para
    o arquivo indicado por flow_upload_asset. O ID expira ao encerrar o worker.
    approve=false fecha o aviso sem enviar o arquivo.
    """
    return await run_account_operation("confirm_upload", account_id,
        {"confirmation_id": confirmation_id, "approve": approve})


@mcp.tool()
async def flow_download_asset(account_id: str, project_id: str, media_id: str) -> dict[str, Any]:
    """Baixar vídeo ou imagem existente, inclusive upload, sem gerar mídia.

    Mídia deve constar da resposta inicial do projeto. Download de imagens enviadas
    por upload usa sua URL original. Paginação ainda não foi validada. URLs ficam em memória.
    """
    return await run_account_operation("download_asset", account_id, {"project_id": project_id, "media_id": media_id})


@mcp.tool()
async def flow_delete_asset(account_id: str, project_id: str, media_id: str,
                            confirm_delete: bool = False) -> dict[str, Any]:
    """Arquivar um ativo e seu histórico; exige pedido e confirmação explícitos."""
    return await run_account_operation("delete_asset", account_id, {
        "project_id": project_id, "media_id": media_id,
        "confirm_delete": confirm_delete,
    })


@mcp.tool()
async def flow_list_projects(account_id: str, query: str = "") -> dict[str, Any]:
    """Listar ou pesquisar projetos da conta no Flow, sem gerar mídia.

    query filtra IDs e títulos sem diferenciar maiúsculas/minúsculas.
    complete=false indica que a resposta remota pode estar incompleta.
    """
    return await run_account_operation("projects", account_id, {"query": query})


@mcp.tool()
async def flow_get_capabilities(account_id: str, project_id: str) -> dict[str, Any]:
    """Consultar modelos, variantes, formatos e preços por plano via HTTP.

    Confirma o projeto na conta; não muda modelo nem gera mídia. Resultado inclui
    horário, estado remoto e escopo. Catálogo não comprova suporte da operação no MCP.
    """
    return await run_account_operation("capabilities", account_id, {"project_id": project_id})


@mcp.tool()
async def flow_get_user_settings(account_id: str) -> dict[str, Any]:
    """Ler preferências do Flow da conta, sem alterar configurações nem gerar mídia."""
    return await run_account_operation("user_settings", account_id, {})


@mcp.tool()
async def flow_update_user_settings(account_id: str,
                                    clear_prompt_on_submit: bool | None = None,
                                    sound_on_hover: bool | None = None,
                                    show_tile_details: bool | None = None,
                                    view_mode: str | None = None,
                                    return_silent_videos: bool | None = None,
                                    agent_mode_enabled: bool | None = None,
                                    confirm_credit_impact: bool = False) -> dict[str, Any]:
    """Atualizar preferências globais da conta com confirmação de leitura.

    return_silent_videos=True pode cobrar créditos quando o Flow retorna vídeos
    sem áudio; nesse caso exige confirm_credit_impact=True.
    """
    return await run_account_operation("update_user_settings", account_id, {
        "clear_prompt_on_submit": clear_prompt_on_submit,
        "sound_on_hover": sound_on_hover,
        "show_tile_details": show_tile_details,
        "view_mode": view_mode,
        "return_silent_videos": return_silent_videos,
        "agent_mode_enabled": agent_mode_enabled,
        "confirm_credit_impact": confirm_credit_impact,
    })


@mcp.tool()
async def flow_create_project(account_id: str, title: str) -> dict[str, Any]:
    """Criar projeto privado com título e confirmar seu ID, sem gerar mídia."""
    return await run_account_operation("project", account_id, {"title": title})


@mcp.tool()
async def flow_rename_project(account_id: str, project_id: str, title: str) -> dict[str, Any]:
    """Renomear projeto existente; título confirmado pela resposta do Flow."""
    return await run_account_operation("project", account_id, {"title": title, "project_id": project_id})


@mcp.tool()
async def flow_delete_project(account_id: str, project_id: str,
                              confirm_delete: bool = False) -> dict[str, Any]:
    """Excluir permanentemente um projeto; exige confirmação explícita do usuário."""
    return await run_account_operation("delete_project", account_id, {
        "project_id": project_id, "confirm_delete": confirm_delete,
    })


@mcp.tool()
async def flow_list_collections(account_id: str, project_id: str) -> dict[str, Any]:
    """Listar coleções do projeto, inclusive vazias, na primeira resposta do Flow."""
    return await run_account_operation("collections", account_id, {"project_id": project_id})


@mcp.tool()
async def flow_create_collection(account_id: str, project_id: str, title: str,
                                 parent_collection_id: str | None = None) -> dict[str, Any]:
    """Criar coleção no projeto ou dentro de outra coleção conhecida.

    A criação usa o título temporário padrão do Flow e renomeia uma vez em
    seguida; resultado incerto não é reenviado automaticamente.
    """
    return await run_account_operation("collection", account_id, {
        "project_id": project_id, "title": title,
        "parent_collection_id": parent_collection_id,
    })


@mcp.tool()
async def flow_rename_collection(account_id: str, project_id: str,
                                 collection_id: str, title: str) -> dict[str, Any]:
    """Renomear coleção existente e confirmar o título na resposta do Flow."""
    return await run_account_operation("collection", account_id, {
        "project_id": project_id, "collection_id": collection_id, "title": title,
    })


@mcp.tool()
async def flow_move_assets(account_id: str, project_id: str, asset_ids: list[str],
                           collection_id: str | None = None) -> dict[str, Any]:
    """Mover ativos para uma coleção; collection_id vazio os move para a raiz.

    Relê o projeto para confirmar a associação, inclusive se o envio retornar
    erro. Resultado inconclusivo nunca provoca reenvio automático.
    """
    return await run_account_operation("move_assets", account_id, {
        "project_id": project_id, "asset_ids": asset_ids,
        "collection_id": collection_id,
    })


@mcp.tool()
async def flow_download_project(account_id: str, project_id: str,
                                output_dir: str | None = None,
                                kind: str | None = None,
                                query: str = "") -> dict[str, Any]:
    """Baixar todos os ativos de um projeto para um diretório local em lote.

    kind filtra por 'image' ou 'video'. query filtra por texto no nome do ativo.
    output_dir opcional especifica o diretório de destino local.
    """
    return await run_account_operation("download_project", account_id, {
        "project_id": project_id, "output_dir": output_dir,
        "kind": kind, "query": query
    })


@mcp.tool()
async def flow_download_collection(account_id: str, project_id: str, collection_id: str,
                                   output_dir: str | None = None,
                                   recursive: bool = False) -> dict[str, Any]:
    """Baixar ativos da coleção; recursive inclui subcoleções conhecidas."""
    return await run_account_operation("download_project", account_id, {
        "project_id": project_id, "collection_id": collection_id,
        "output_dir": output_dir, "recursive": recursive,
    })


@mcp.tool()
async def flow_project_summary(account_id: str, project_id: str) -> dict[str, Any]:
    """Resumo estruturado de um projeto Flow: contagem de ativos, tipos e título.

    Não gera mídia nem consome créditos.
    """
    return await run_account_operation("project_summary", account_id, {
        "project_id": project_id
    })


@mcp.tool()
async def flow_generate_images(account_id: str, prompt: str, max_credits: int,
                               project_id: str | None = None, model: str = "nano-banana-2",
                               aspect: str = "16:9", count: int = 1,
                               reference_images: list[str] | None = None,
                               reference_asset_ids: list[str] | None = None) -> dict[str, Any]:
    """Gerar e baixar 1–4 imagens; custo confirmado antes do envio.

    Modelos: nano-banana-2, nano-banana-2-lite, nano-pro. Lite usa seu ID no catálogo.
    Proporções: 16:9, 9:16, 1:1, 4:3, 3:4.
    Referências: caminhos locais ou IDs de imagens já presentes no project_id.
    Referências por ID não enviam novamente o arquivo.
    max_credits limita o pedido inteiro, inclusive quando o custo observado é zero.
    Não reenviar tarefa com resultado incerto. Aguarda até 20 minutos.
    """
    return await run_account_operation("images", account_id,
        {"prompt": prompt, "max_credits": max_credits, "project_id": project_id,
         "model": model, "aspect": aspect, "count": count, "reference_images": reference_images,
         "reference_asset_ids": reference_asset_ids})


@mcp.tool()
async def flow_list_jobs(account_id: str, limit: int = 100) -> dict[str, Any]:
    """Listar tarefas locais desta conta, inclusive após reiniciar o MCP.

    Ordenadas por observação mais recente. Não consulta tarefas externas ao MCP
    nem reenvia geração. Útil para localizar uma tarefa cujo retorno foi interrompido.
    """
    return await run_account_operation("jobs", account_id, {"limit": limit})


@mcp.tool()
async def flow_get_job(account_id: str, job_id: str) -> dict[str, Any]:
    """Ler último estado SALVO da tarefa; não consulta o Flow nem reenvia geração.

    Após interrupção, use flow_recover_job quando os IDs estiverem disponíveis.
    """
    return await run_account_operation("job", account_id, {"job_id": job_id})


@mcp.tool()
async def flow_recover_job(account_id: str, job_id: str) -> dict[str, Any]:
    """Reconciliar IDs esperados e recuperar arquivos, sem submeter outra geração.

    Se o POST foi incerto, consulta a listagem do projeto e o estado do vídeo
    pelo workflow. Falha ou atraso preserva a tarefa; nunca cria outra cópia.
    """
    return await run_account_operation("recover", account_id, {"job_id": job_id})


@mcp.tool()
async def flow_wait_job(account_id: str, job_id: str, timeout_seconds: int = 60,
                         poll_interval_seconds: int = 5) -> dict[str, Any]:
    """Acompanhar e baixar imagem/vídeo já enviado, sem gerar novamente.

    timeout_seconds=0 faz apenas uma consulta; máximo 600, intervalo de 2–60s.
    O prazo limita novas consultas; uma consulta/download em andamento pode
    excedê-lo. wait_status informa completed, stopped, unavailable ou timeout;
    o status original da tarefa é preservado no timeout. Cancelamento é local.
    """
    from flow_video import get_job

    if (type(timeout_seconds) is not int or not 0 <= timeout_seconds <= 600
            or type(poll_interval_seconds) is not int or not 2 <= poll_interval_seconds <= 60):
        raise ToolError("Use prazo inteiro de 0–600s e intervalo inteiro de 2–60s.")
    try:
        validate_account(account_id)
        job = get_job(account_id, job_id)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from None
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    polls = 0
    while True:
        if job.get("status") in {"completed", "cancelled", "generation_failed", "failed_pre_submit",
                                  "reference_confirmation_required", "reference_upload_unknown"}:
            return {**job, "wait_status": "completed" if job["status"] == "completed" else "stopped",
                    "polls": polls}
        if not (job.get("request_media_ids") or job.get("media_ids") or job.get("media_id")):
            return {**job, "wait_status": "unavailable", "polls": polls}
        if polls and asyncio.get_running_loop().time() >= deadline:
            return {**job, "wait_status": "timeout", "polls": polls}
        result = await run_account_operation("recover", account_id, {"job_id": job_id})
        polls += 1
        if result.get("job_id") != job_id:
            return {**job, "wait_status": "unavailable", "polls": polls,
                    "wait_error_status": result.get("status")}
        job = result
        if job.get("status") in {"completed", "cancelled", "generation_failed", "failed_pre_submit"}:
            continue
        if job.get("recovery_status") == "unavailable":
            return {**job, "wait_status": "unavailable", "polls": polls}
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            return {**job, "wait_status": "timeout", "polls": polls}
        await asyncio.sleep(min(poll_interval_seconds, remaining))
        # Releitura observa cancelamentos locais e resultados de outras consultas.
        job = get_job(account_id, job_id)


@mcp.tool()
def flow_cancel_job(account_id: str, job_id: str) -> dict[str, Any]:
    """Cancelar localmente uma tarefa pendente para evitar recuperação indevida."""
    from flow_scene import cancel_job
    try:
        return cancel_job(account_id, job_id)
    except (ValueError, FileNotFoundError, OSError) as exc:
        raise ToolError(str(exc)) from None


@mcp.tool()
def flow_clean_jobs(account_id: str, status_filter: str | None = None) -> dict[str, Any]:
    """Limpar tarefas locais concluídas ou canceladas para liberar espaço em disco."""
    from flow_scene import clean_jobs
    try:
        return clean_jobs(account_id, status_filter)
    except (ValueError, OSError) as exc:
        raise ToolError(str(exc)) from None


@mcp.tool()
async def flow_save_frame(account_id: str, project_id: str, media_id: str,
                          timestamp_seconds: float = 0.0,
                          upload_to_flow: bool = False) -> dict[str, Any]:
    """Capturar um quadro de um vídeo em alta resolução como imagem local.

    Se upload_to_flow=True, envia o quadro diretamente para o Flow (sem nova geração),
    tornando-o um asset de imagem do projeto para reuso como start_frame ou referência.
    """
    return await run_account_operation("save_frame", account_id, {
        "project_id": project_id, "media_id": media_id,
        "timestamp_seconds": timestamp_seconds, "upload_to_flow": upload_to_flow
    })


@mcp.tool()
async def flow_export_gif(account_id: str, project_id: str, media_id: str,
                          start_time: float = 0.0,
                          duration: float | None = None,
                          fps: int = 15,
                          width: int = 480) -> dict[str, Any]:
    """Exportar clipe de vídeo como GIF animado de alta qualidade.

    Utiliza paleta otimizada para manter fidelidade de cores com tamanho reduzido.
    """
    return await run_account_operation("export_gif", account_id, {
        "project_id": project_id, "media_id": media_id,
        "start_time": start_time, "duration": duration,
        "fps": fps, "width": width
    })


@mcp.tool()
async def flow_build_scene(account_id: str, project_id: str,
                           clips: list[dict[str, Any]],
                           scene_title: str = "Cena sem título") -> dict[str, Any]:
    """Scenebuilder: montar e concatenar múltiplos clipes de vídeo em uma cena contínua.

    Cada clipe deve conter 'media_id' e opcionalmente 'trim_start' e 'trim_end' em segundos.
    Normaliza resolução (1280x720) e framerate (24fps), gerando MP4 sincronizado.
    """
    return await run_account_operation("build_scene", account_id, {
        "project_id": project_id, "clips": clips, "scene_title": scene_title
    })


@mcp.tool()
async def flow_list_scenes(account_id: str, project_id: str, query: str = "") -> dict[str, Any]:
    """Listar cenas, inclusive vazias, da primeira resposta do projeto.

    query filtra por título ou ID. complete=False informa paginação não verificada.
    archived=true marca cenas na lixeira.
    """
    return await run_account_operation("list_scenes", account_id, {"project_id":project_id, "query":query})


@mcp.tool()
async def flow_manage_scene(account_id: str, project_id: str, operation: str,
                            scene_id: str | None = None,
                            workflow_ids: list[str] | None = None,
                            clips: list[dict[str, Any]] | None = None,
                            position: int | None = None,
                            title: str | None = None,
                            confirm: bool = False) -> dict[str, Any]:
    """Criar, ler, incluir/remover clipes, reordenar, aparar, renomear ou arquivar uma cena do Flow.

    create sem workflow_ids cria cena vazia pelo HTTP migrado e confirma por
    leitura. read lê a composição, cortes e ordem pela resposta inicial do projeto,
    com complete=False. add inclui workflow_ids de vídeos do projeto em scene_id,
    na posição informada (padrão: final), por uma única RPC oWTRd confirmada por
    leitura; a cena guarda clones com novos IDs, devolvidos em added_workflow_ids.
    Resultado incerto não é reenviado. remove retira workflow_ids (IDs dos clipes
    na cena); remover todos deixa a cena vazia. rename usa title. archive move a cena
    para a lixeira e exige confirm=true; restore a devolve da lixeira. delete
    exclui definitivamente uma cena já na lixeira e exige confirm=true. Criação com clipes, update e exportação usam o caminho legado,
    ainda não validado nesta conta migrada.
    Para create com clipes, informe workflow_ids de vídeos do projeto. Para read, informe
    scene_id. Para update, informe scene_id e clips na ordem desejada, cada um
    com workflow_id e opcionalmente start_time/end_time em segundos.
    """
    return await run_account_operation("manage_scene", account_id, {
        "project_id": project_id, "operation": operation, "scene_id": scene_id,
        "workflow_ids": workflow_ids, "clips": clips, "position": position,
        "title": title, "confirm": confirm,
    })


@mcp.tool()
async def flow_export_scene(account_id: str, project_id: str,
                            scene_id: str) -> dict[str, Any]:
    """Exportar uma cena persistida como MP4 sem reenviar uma exportação incerta.

    Usa as RPCs nativas GjQLTd/IxdSwd com a ordem e os cortes atuais da cena;
    o MP4 é validado e salvo localmente. Sem gasto de créditos observado.
    """
    return await run_account_operation("export_scene", account_id, {
        "project_id": project_id, "scene_id": scene_id,
    })


@mcp.tool()
async def flow_list_characters(account_id: str, project_id: str) -> dict[str, Any]:
    """Listar personagens e imagens de referência do projeto (HTTP nativo, sem URLs)."""
    return await run_account_operation("list_characters", account_id, {
        "project_id": project_id,
    })


@mcp.tool()
def flow_list_voice_presets() -> dict[str, Any]:
    """Listar presets conhecidos pelo gflow-cli; disponibilidade por conta não é verificada."""
    from flow_character import list_voice_presets

    return list_voice_presets()


@mcp.tool()
async def flow_manage_character(account_id: str, project_id: str, operation: str,
                                entity_id: str | None = None,
                                display_name: str | None = None,
                                image_media_id: str | None = None,
                                voice: str | None = None,
                                personality: str | None = None,
                                slot: str = "portrait",
                                description: str | None = None,
                                max_credits: int | None = None,
                                confirm_delete: bool = False) -> dict[str, Any]:
    """Criar, atualizar (nome, voz, personalidade), definir imagem ou excluir personagem pelo HTTP nativo.

    set_image exige entity_id e image_media_id (imagem do projeto) e usa slot=portrait
    ou body (Retrato/Corpo do editor), ou description + max_credits para gerar a imagem do
    slot com Nano Banana 2 ("Criar retrato/corpo"); se o slot estiver ocupado, a imagem anterior é
    removida antes. remove_image exige entity_id e slot. Ambos confirmam por leitura.

    create exige display_name e image_media_id de uma imagem do projeto (como em
    "Adicionar do projeto") ou description + max_credits para gerar o retrato com
    Nano Banana 2 (geração cotada no catálogo; custo acima do teto impede o envio). update (ou rename) exige entity_id e ao menos um de
    display_name, voice (preset de flow_list_voice_presets) e personality. delete exige
    entity_id e confirm_delete=true após autorização explícita do usuário.
    Envio único confirmado por leitura; resultado incerto não é reenviado.
    """
    return await run_account_operation("manage_character", account_id, {
        "project_id": project_id, "operation": operation, "entity_id": entity_id,
        "display_name": display_name, "image_media_id": image_media_id,
        "voice": voice, "personality": personality, "slot": slot, "description": description,
        "max_credits": max_credits, "confirm_delete": confirm_delete,
    })


@mcp.tool()
async def flow_get_agent_brief(account_id: str, project_id: str) -> dict[str, Any]:
    """Ler o estado e os cartões de instrução do Agent neste projeto (HTTP nativo)."""
    return await run_account_operation("get_agent_brief", account_id, {"project_id": project_id})


@mcp.tool()
async def flow_update_agent_brief(account_id: str, project_id: str,
                                  enabled: bool | None = None,
                                  instructions: list[dict[str, Any]] | None = None,
                                  confirm_replace_instructions: bool = False) -> dict[str, Any]:
    """Atualizar o brief do Agent; substituir cartões exige confirmação explícita.

    Cada cartão aceita id, title, text e enabled (image_media_ids/character_ids
    ainda não são suportados no caminho nativo). Enviar instructions substitui
    a lista inteira; um envio Kcr7Ub confirmado por leitura, sem reenvio.
    """
    return await run_account_operation("update_agent_brief", account_id, {
        "project_id": project_id, "enabled": enabled, "instructions": instructions,
        "confirm_replace_instructions": confirm_replace_instructions,
    })


@mcp.tool()
async def flow_agent_request(account_id: str, project_id: str, message: str,
                             allow_media_changes: bool = False,
                             session_id: str | None = None) -> dict[str, Any]:
    """Perguntar ao Flow Agent e devolver a resposta em texto.

    Sem session_id abre uma sessão nova; com session_id (de uma resposta anterior
    ou de flow_list_agent_sessions) continua a conversa nessa sessão.
    Um único envio StreamChat por HTTP; resultado incerto não é reenviado.
    Por padrão a mensagem é prefixada com a instrução de não gerar, editar, mover
    ou excluir mídia; isso é uma orientação ao Agent, não um bloqueio técnico.
    Retorna session_id, ferramentas chamadas pelo Agent, unexpected_tools e
    credits_spent (saldo antes/depois). Mídia gerada pelo Agent gasta créditos.
    """
    return await run_account_operation("agent_request", account_id, {
        "project_id": project_id, "message": message, "allow_media_changes": allow_media_changes,
        "session_id": session_id})


@mcp.tool()
async def flow_list_tools(account_id: str, category: str = "all", query: str = "") -> dict[str, Any]:
    """Listar ferramentas (applets) do Flow: mine, templates, community ou all.

    Somente leitura via ListApplets; query filtra título e descrição. Executar
    ferramentas ainda não está disponível. complete=False: paginação não verificada.
    """
    return await run_account_operation("list_tools", account_id, {"category": category, "query": query})


@mcp.tool()
async def flow_list_agent_sessions(account_id: str, project_id: str) -> dict[str, Any]:
    """Listar sessões do Agent neste projeto, sem abrir mensagens nem gerar mídia.

    Retorna IDs e títulos da resposta inicial; a paginação ainda não foi validada.
    """
    return await run_account_operation("list_agent_sessions", account_id, {"project_id": project_id})


@mcp.tool()
async def flow_create_agent_session(account_id: str, project_id: str) -> dict[str, Any]:
    """Criar uma sessão do Agent neste projeto, sem enviar mensagens ou gerar mídia."""
    return await run_account_operation("create_agent_session", account_id, {"project_id": project_id})


@mcp.tool()
async def flow_rename_agent_session(account_id: str, project_id: str,
                                    session_id: str, title: str) -> dict[str, Any]:
    """Renomear uma sessão do Agent e confirmar o título por leitura posterior."""
    return await run_account_operation("rename_agent_session", account_id, {
        "project_id": project_id, "session_id": session_id, "title": title,
    })


@mcp.tool()
async def flow_delete_agent_session(account_id: str, project_id: str, session_id: str,
                                    confirm_delete: bool = False) -> dict[str, Any]:
    """Excluir sessão do Agent; apaga permanentemente o histórico após confirmação."""
    return await run_account_operation("delete_agent_session", account_id, {
        "project_id": project_id, "session_id": session_id, "confirm_delete": confirm_delete,
    })


@mcp.tool()
async def flow_upscale(account_id: str, project_id: str, media_id: str,
                       target_resolution: str = "1080p",
                       upload_to_flow: bool = False) -> dict[str, Any]:
    """Aumentar a resolução de imagem ou vídeo (720p, 1080p, 4k) com filtro lanczos e nitidez.

    Compatível com vídeos MP4 e imagens geradas ou importadas. Não consome créditos.
    upload_to_flow=True envia o resultado ao projeto; vídeo pode exigir confirmação
    explícita de direitos via flow_confirm_upload.
    """
    return await run_account_operation("upscale", account_id, {
        "project_id": project_id, "media_id": media_id,
        "target_resolution": target_resolution, "upload_to_flow": upload_to_flow
    })


@mcp.tool()
def flow_begin_account_connection(account_id: str) -> dict[str, Any]:
    """Abrir pareamento no Chrome habitual. O usuário clica na extensão instalada.

    Somente uma captura por vez. Não lê cookies até o clique na extensão.
    """
    global bridge
    try:
        validate_account(account_id)
    except ValueError as exc:
        raise ToolError(str(exc)) from None
    try:
        if bridge is not None:
            bridge.close()
        bridge = SessionBridge(account_id)
        bridge.open_browser()
    except Exception:
        if bridge is not None:
            bridge.close()
            bridge = None
        raise ToolError("Não foi possível abrir o pareamento. Confira Chrome/Chromium local.") from None
    return {"account_id": account_id, "status": "waiting_for_extension", "expires_in_seconds": 300,
            "message": "Na aba aberta, clique na extensão Google Flow MCP e em Conectar sessão. Depois diga: conectei."}


@mcp.tool()
async def flow_complete_account_connection(account_id: str) -> dict[str, Any]:
    """Após o clique humano na extensão, importar e abrir o seletor Google.

    O usuário escolhe a conta e entra no Flow. Autenticação será verificada,
    sem alterar a preferência de aprovação ou gerar mídia.
    """
    global bridge
    if bridge is None or bridge.account_id != account_id:
        raise ToolError("Inicie o pareamento para esta conta primeiro.")
    try:
        payload = bridge.take()
    except ValueError:
        raise ToolError("Sessão não enviada ou pareamento expirado. Clique na extensão ou reinicie.") from None
    bridge = None
    return await run_account_operation("import", account_id, payload)


def http_app(token: str):
    """Streamable HTTP para a rede local; exige `Authorization: Bearer <token>` (o MCP gasta créditos)."""
    app = mcp.streamable_http_app(host="0.0.0.0")
    expected = f"Bearer {token}".encode()

    async def guarded(scope, receive, send):
        if scope["type"] == "http" and not hmac.compare_digest(dict(scope["headers"]).get(b"authorization", b""), expected):
            await send({"type": "http.response.start", "status": 401, "headers": [(b"content-type", b"text/plain")]})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        await app(scope, receive, send)

    return guarded


if __name__ == "__main__":
    if sys.argv[1:] == ["--http"]:
        import uvicorn

        # Sem token o servidor não sobe: nunca expor o MCP na rede sem autenticação.
        uvicorn.run(http_app(os.environ["FLOW_MCP_HTTP_TOKEN"]), host="0.0.0.0",
                    port=int(os.environ.get("FLOW_MCP_HTTP_PORT", "8765")))
    else:
        mcp.run(transport="stdio")
