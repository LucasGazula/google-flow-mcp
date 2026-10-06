"""Preferências de conta do Flow lidas e atualizadas pelos RPCs observados."""

from datetime import datetime, timezone

_FIELDS = {
    "clear_prompt_on_submit": ("should_clear_prompt_box_on_submit", 6),
    "sound_on_hover": ("has_sound_on_tile_hover", 7),
    "show_tile_details": ("is_tile_details_always_visible", 8),
    "view_mode": ("tiles_display_mode", 9),
    "return_silent_videos": ("should_return_silent_videos", 10),
    "agent_mode_enabled": ("is_agent_mode_toggled", 12),
}


def parse_user_settings(payload: list) -> dict:
    if not isinstance(payload, list):
        raise ValueError("Resposta de preferências não reconhecida.")

    settings = {}
    for name, (_, field) in _FIELDS.items():
        value = payload[field - 1] if len(payload) >= field else None
        if name == "view_mode":
            value = "grid" if value is None else value
            # Modo novo do Flow é informado como veio; só a escrita se limita a grid/batch.
            if not isinstance(value, str) or not value or len(value) > 40:
                raise ValueError("Modo de exibição não reconhecido.")
        else:
            value = False if value is None else value
            if type(value) is not bool:
                raise ValueError(f"Preferência {name} não reconhecida.")
        settings[name] = value
    return settings


async def get_user_settings(account_id: str, *, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_http import FlowHTTP

    validate_account(account_id)
    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        settings = parse_user_settings(await client.rpc("Yizz8d"))
        return {"account_id": account_id, "status": "ok", "source": "HTTP/Yizz8d",
                "settings": settings, "observed_at": datetime.now(timezone.utc).isoformat()}
    finally:
        if owned:
            await client.close()


async def update_user_settings(account_id: str, *, clear_prompt_on_submit: bool | None = None,
                               sound_on_hover: bool | None = None,
                               show_tile_details: bool | None = None,
                               view_mode: str | None = None,
                               return_silent_videos: bool | None = None,
                               agent_mode_enabled: bool | None = None,
                               confirm_credit_impact: bool = False, client=None) -> dict:
    from flow_accounts import validate_account
    from flow_http import FlowHTTP

    validate_account(account_id)
    if type(confirm_credit_impact) is not bool:
        raise ValueError("confirm_credit_impact deve ser booleano.")
    requested = {"clear_prompt_on_submit": clear_prompt_on_submit,
                 "sound_on_hover": sound_on_hover,
                 "show_tile_details": show_tile_details,
                 "view_mode": view_mode,
                 "return_silent_videos": return_silent_videos,
                 "agent_mode_enabled": agent_mode_enabled}
    requested = {key: value for key, value in requested.items() if value is not None}
    if not requested:
        raise ValueError("Informe ao menos uma preferência para atualizar.")
    for key, value in requested.items():
        if key == "view_mode":
            if not isinstance(value, str) or value not in {"grid", "batch"}:
                raise ValueError("view_mode deve ser 'grid' ou 'batch'.")
        elif type(value) is not bool:
            raise ValueError(f"{key} deve ser booleano.")
    if requested.get("return_silent_videos") is True and not confirm_credit_impact:
        return {"account_id": account_id, "status": "confirmation_required",
                "message": "Ativar vídeos silenciosos pode cobrar créditos quando o Flow retornar vídeos sem áudio. Repita com confirm_credit_impact=true após autorização explícita."}

    values = [None] * max(_FIELDS[key][1] for key in requested)
    paths = []
    for key, value in requested.items():
        path, field = _FIELDS[key]
        # A interface envia booleanos como 1/0 e a máscara aninhada: [[campo, ...]].
        values[field - 1] = int(value) if type(value) is bool else value
        paths.append(path)

    owned = client is None
    client = client or FlowHTTP(account_id)
    if client.account_id != account_id:
        if owned:
            await client.close()
        raise ValueError("Sessão HTTP pertence a outra conta.")
    try:
        try:
            await client.rpc("DA4VGb", params=[values, [paths]])
        except Exception:
            pass  # Envio incerto: apenas a leitura abaixo pode reconciliar.
        try:
            settings = parse_user_settings(await client.rpc("Yizz8d"))
        except Exception:
            return {"account_id": account_id, "status": "submission_unknown",
                    "message": "Não foi possível confirmar as preferências; leia-as antes de repetir. Nenhum reenvio foi feito."}
        confirmed = all(settings[key] == value for key, value in requested.items())
        return {"account_id": account_id,
                "status": "updated" if confirmed else "submission_unknown",
                "source": "HTTP/DA4VGb+Yizz8d", "settings": settings,
                **({} if confirmed else {"message": "A leitura não confirmou todas as preferências; confira o Flow antes de repetir."})}
    finally:
        if owned:
            await client.close()
