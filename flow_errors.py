"""Erros legíveis e próximos passos para o agente, sem vazar dados do backend.

Repassa o texto só de exceções levantadas pelo código deste MCP (mensagens
escritas aqui) ou pelas validações de entrada do gflow-cli; exceções de rede,
do navegador ou com respostas do Flow viram apenas o tipo e uma dica genérica,
porque podem conter cookies, URLs assinadas ou respostas autenticadas.
"""

import errno
from pathlib import Path
import re
import traceback

_HERE = Path(__file__).resolve().parent
# Validações de entrada do gflow-cli (DTOs e arquivo de imagem): só descrevem o pedido do agente.
_INPUT_VALIDATORS = {("api", "video.py"), ("api", "image.py")}
_INPUT_FUNCTIONS = {"validate_image_file"}

_HINTS = {
    "TimeoutError": "Tempo esgotado esperando o Flow ou o navegador; confira o estado antes de repetir.",
    "ConnectError": "Sem conexão com o Flow; confira a rede antes de repetir.",
    "ReadTimeout": "O Flow não respondeu a tempo; confira o estado antes de repetir.",
    "JSONDecodeError": "Resposta do Flow em formato inesperado; a sessão pode precisar de renovação.",
    "KeyError": "Resposta do Flow em formato inesperado (campo ausente).",
    "IndexError": "Resposta do Flow em formato inesperado (lista menor que a esperada).",
    "TypeError": "Parâmetro ou resposta com tipo inesperado.",
    "ProfileLockedError": ("Perfil da conta em uso por outro processo: keepalive ou login (tente de novo "
                           "em instantes) ou outro cliente MCP com worker desta conta na mesma máquina "
                           "(feche-o ou use o MCP da Pi)."),
}

# O que o agente deve fazer a seguir em cada estado devolvido pelas ferramentas.
NEXT_STEPS = {
    "failed_pre_submit": "Nada foi enviado nem cobrado; corrija o motivo em 'error' e tente de novo.",
    "submission_unknown": "Envio incerto: NÃO repita. Use flow_recover_job (ou flow_wait_job) com o job_id.",
    "generation_unknown": "Envio aceito, resultado ainda não confirmado: NÃO repita. Use flow_wait_job com o job_id.",
    "accepted": ("Envio aceito: NÃO reenvie. Gerações: use flow_wait_job com o job_id; "
                 "flow_upscale_video: chame de novo com os mesmos IDs."),
    "download_failed": "A mídia foi gerada; só o download falhou. Use flow_recover_job com o job_id.",
    "partial_result": "Parte das saídas chegou; use flow_recover_job com o job_id para o restante, sem reenviar.",
    "generation_failed": "O Flow recusou ou falhou a geração; ajuste o prompt/parâmetros antes de nova tentativa.",
    "http_error": "A operação falhou antes de concluir; leia 'error'. Para mutações, confira o estado antes de repetir.",
    "http_worker_error": "O worker da conta foi reiniciado; consulte flow_list_jobs antes de repetir qualquer geração.",
    "account_busy": ("Outra operação desta conta está em andamento (running_action); nada foi enviado. "
                     "Aguarde e tente de novo; flow_list_jobs mostra o andamento."),
    "timeout": "Tempo esgotado; consulte o estado (flow_list_jobs/flow_account_status) antes de repetir.",
    "backend_error": "Falha local do backend; confira Chrome/sessão com flow_account_status.",
    "unavailable": "Leitura indisponível agora; não significa saldo zero nem sessão expirada. Tente flow_account_status.",
    "no_session": "Conta sem sessão autenticada; faça login (flow_connect_account) antes de usar.",
    "needs_login": "Conta sem sessão salva nesta máquina; faça o login da conta.",
    "google_session_only": "Logado no Google, mas sem acesso ao Flow; abra o Flow nessa conta e refaça o login.",
    "profile_marker_missing": "Perfil incompleto; refaça o login da conta.",
    "verification_error": "Verificação inconclusiva (não prova sessão expirada); tente flow_get_credits.",
    "requires_manual_confirmation": "O titular precisa aceitar o aviso de direitos no site do Flow antes de novo upload.",
    "not_found_in_project_listing": "Item ausente da listagem; confira o ID e a conta (flow_list_projects/flow_list_assets).",
    "not_found_in_first_page": "Sessão ausente da primeira página; confira o ID com flow_list_agent_sessions.",
    "submitted": "Enviado, mas não confirmado por leitura: NÃO repita; confira o projeto (flow_list_assets).",
    "output_missing": ("O arquivo local do resultado sumiu e o MCP não refaz o envio sozinho; com asset_media_id, "
                       "use flow_download_asset; senão, confirme com o usuário antes de repetir."),
    # Estados intermediários: tarefa em andamento ou interrompida (processo caiu) nesse estágio.
    "preparing": ("Em preparo ou interrompida antes do envio; nada foi cobrado até aqui. Se não estiver "
                  "em andamento, pode repetir o pedido."),
    "submitting": "Em envio ou interrompida durante o envio: NÃO repita. Use flow_wait_job/flow_recover_job.",
    "processing": "Em processamento ou interrompida: NÃO repita. Use flow_wait_job/flow_recover_job.",
    "downloading": "Gerado; download em andamento ou interrompido. Use flow_recover_job com o job_id.",
    "generating_image": "Gerando imagem (ou interrompida): NÃO repita; confira o projeto depois.",
    "generating_portrait": "Gerando retrato (ou interrompida): NÃO repita; confira o personagem depois.",
    "linking_image": "Vinculando imagem (ou interrompida): NÃO repita; confira com flow_list_characters.",
    "saving": "Resultado recebido; gravação local em andamento ou interrompida. NÃO repita; veja downloads_dir.",
    "confirmation_required": "Peça confirmação explícita ao usuário e repita com o parâmetro de confirmação.",
    "reference_confirmation_required": "Peça ao titular para aprovar os direitos e use flow_confirm_upload.",
}


def error_fields(exc: BaseException, prefix: str = "") -> dict:
    """Campos `error_type` e `error` (texto seguro ou dica genérica) para uma exceção.

    Falhas inesperadas no próprio código (IndexError/KeyError/...) ganham também
    `error_location` (arquivo:linha). `prefix` separa erros secundários
    (ex.: `recovery_`, `submit_`) do erro principal da tarefa.
    """
    fields = {f"{prefix}error_type": type(exc).__name__}
    frames = traceback.extract_tb(exc.__traceback__)
    origin = Path(frames[-1].filename).resolve() if frames else None
    text = str(exc).strip()
    in_gflow = origin is not None and origin.parent.parent.name == "gflow_cli"
    safe = origin is not None and (origin.parent == _HERE or in_gflow and (
        (origin.parent.name, origin.name) in _INPUT_VALIDATORS or frames[-1].name in _INPUT_FUNCTIONS))
    if isinstance(exc, OSError) and exc.errno == errno.ENOSPC:
        safe, text = True, ("Disco cheio na máquina do MCP (veja downloads_dir em flow_status); libere espaço "
                            "e use flow_recover_job para baixar de novo, sem reenviar a geração.")
    elif isinstance(exc, (FileNotFoundError, IsADirectoryError, NotADirectoryError, PermissionError)):
        safe = True  # Caminho local informado pelo próprio agente.
        text = (text or f"Arquivo inválido: {exc.filename}") + (
            " (caminhos são da máquina onde o MCP roda; veja flow_status)")
    if not safe and type(exc).__module__.startswith("playwright") and text:
        # Indica qual elemento da interface do Flow sumiu/mudou; URLs (podem ser assinadas) são removidas.
        safe, text = True, "Navegador: " + re.sub(r"https?://\S+", "<url>", text.splitlines()[0])[:300]
    if origin is not None and origin.parent == _HERE and isinstance(exc, (IndexError, KeyError, TypeError,
                                                                         AttributeError)):
        # Falha inesperada no próprio código (formato novo do Flow ou bug): dica + onde olhar.
        fields[f"{prefix}error"] = f"{_HINTS.get(type(exc).__name__, 'Erro interno do MCP.')} [{text[:200]}]"
        fields[f"{prefix}error_location"] = f"{origin.name}:{frames[-1].lineno}"
    elif safe and text:
        fields[f"{prefix}error"] = text[:500]
    elif type(exc).__name__ in _HINTS:
        fields[f"{prefix}error"] = _HINTS[type(exc).__name__]
    return fields


def tolerant_rows(rows, parse) -> list:
    """Aplicar `parse` a cada linha de uma leitura, ignorando as de formato desconhecido.

    Só para leituras: uma mudança do Flow numa linha não deve esconder as demais.
    Não use em listas que serão reenviadas inteiras numa mutação (ex.: clipes de
    uma cena), onde ignorar uma linha a apagaria.
    """
    result = []
    for row in rows or []:
        try:
            item = parse(row)
        except (ValueError, TypeError, IndexError, KeyError):
            continue
        if item is not None:
            result.append(item)
    return result


def with_next_step(result):
    """Acrescentar `next_step` conforme o status, sem sobrescrever o que já existe."""
    if isinstance(result, dict) and "next_step" not in result:
        step = NEXT_STEPS.get(result.get("status"))
        if step:
            return {**result, "next_step": step}
    return result
