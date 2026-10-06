"""Catálogo HTTP e conferência do compositor da conta/projeto."""

from datetime import datetime, timezone
from flow_browser import account_page
from flow_projects import validate_project
import re


def _field(row, index, default=None):
    if not isinstance(row, list):
        raise ValueError("Campo do catálogo não reconhecido.")
    return row[index] if len(row) > index and row[index] is not None else default


def _key(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Identificador do catálogo não reconhecido.")
    return value


def _price(entries, tier):
    """Preço por plano: oneof ausente/indisponível não é preço zero."""
    matches = [pair[1] for pair in entries if isinstance(pair, list) and len(pair) == 2 and pair[0] == tier]
    if len(matches) > 1:
        raise ValueError("Preço duplicado no catálogo.")
    if not matches or matches[0] is None or _field(matches[0], 1) is not None:
        return None
    # Campo numérico zero pode ser omitido em um preço protobuf presente.
    value = _field(_field(matches[0], 0, []), 1, 0)
    if type(value) is not int or value < 0:
        raise ValueError("Preço do catálogo não reconhecido.")
    return value


def parse_model_statuses(payload):
    rows = _field(payload, 0)
    if not isinstance(rows, list):
        raise ValueError("Estado dos modelos não reconhecido.")
    states = {}
    for row in rows:
        try:
            key = _key(_field(row, 0))
        except ValueError:
            continue
        status, reasons = _field(row, 1, 0), _field(row, 2, [])
        if (type(status) is not int or status not in {0, 1, 2, 3} or key in states
                or not isinstance(reasons, list) or any(not isinstance(r, list) for r in reasons)):
            # Estado novo/ambíguo: na dúvida o modelo fica bloqueado, nunca liberado.
            states[key] = {"status": status, "blocked": True}
            continue
        # Mesma condição da lista de modelos do frontend (QWa/RZa).
        restricted = (status in {2, 3} or any(_field(r, 0) == 1 for r in reasons)) and any(
            _field(r, 1) in {1, 2} for r in reasons)
        states[key] = {"status": status, "blocked": status == 3 or restricted}
    return states


def parse_capabilities(payload, tier, statuses):
    """HTrJv: campos conferidos no transformador GetModels do próprio Flow."""
    if type(tier) is not int or tier not in {1, 2, 3}:
        raise ValueError("Plano da conta desconhecido; custo não pode ser inferido.")
    catalog = _field(payload, 0)
    result = {}
    for mode, index in (("video", 4), ("image", 5)):
        groups = _field(catalog, index)
        if not isinstance(groups, list):
            raise ValueError("Catálogo de modelos não reconhecido.")
        models = []
        for group in groups:
            # Modelo novo/alterado pelo Flow fica fora da lista sem bloquear os demais.
            try:
                model = _parse_model(group, mode, tier, statuses)
            except (ValueError, TypeError, IndexError):
                continue
            models.append(model)
        result[mode] = {"models":models}
    return result


def _parse_model(group, mode, tier, statuses):
    label, identifier, usages = _field(group, 0), _key(_field(group, 3)), _field(group, 1)
    if not isinstance(label, str) or not label or len(label) > 200 or not isinstance(usages, list):
        raise ValueError("Modelo do catálogo não reconhecido.")
    variants = []
    for row in usages:
        try:
            variants.append(_parse_variant(row, mode, tier, statuses, identifier))
        except (ValueError, TypeError, IndexError):
            continue  # Variante em formato novo: indisponível, sem derrubar o modelo.
    return {"model_id":identifier, "label":label, "variants":variants,
            "disabled":not any(v["available"] for v in variants)}


def _parse_variant(row, mode, tier, statuses, identifier):
    key = _key(_field(row, 0))
    entries = _field(row, 4, [])
    if not isinstance(entries, list):
        raise ValueError("Preços do catálogo não reconhecidos.")
    price = _price(entries, tier)
    state = statuses.get(key, statuses.get(identifier))
    blocked = state is not None and state["blocked"]
    aspect_codes = _field(_field(row, 12 if mode == "video" else 13, []), 0, [])
    aspect_map = {1:"9:16", 2:"16:9"} if mode == "video" else {
        1:"1:1", 2:"9:16", 3:"16:9", 4:"3:4", 5:"4:3"}
    if not isinstance(aspect_codes, list) or any(type(c) is not int for c in aspect_codes):
        raise ValueError("Proporções do catálogo não reconhecidas.")
    # Desde 05/10/2026 o Flow repete códigos e inclui 0 (não especificado); código desconhecido não é oferecido.
    known = [c for c in aspect_codes if c in aspect_map]
    if aspect_codes and not known:
        raise ValueError("Proporções do catálogo não reconhecidas.")
    variant = {"model_key":key, "credits_per_output":price,
        "available":price is not None and not blocked,
        "availability_reason":"remote_restriction" if blocked else "tier_unavailable" if price is None else None,
        "aspects":list(dict.fromkeys(aspect_map[c] for c in (known or list(aspect_map))))}
    if mode == "video":
        duration = _field(row, 16, 8)
        resolutions = _field(_field(row, 23, []), 0, []) or [1]
        resolution_map = {1:"720p", 2:"1080p", 3:"4k", 4:"360p"}
        if (type(duration) is not int or duration <= 0 or not isinstance(resolutions, list)
                or any(type(c) is not int for c in resolutions)):
            raise ValueError("Formato de vídeo do catálogo não reconhecido.")
        # Resolução nova (código desconhecido) não é oferecida.
        resolutions = [c for c in resolutions if c in resolution_map]
        if not resolutions:
            raise ValueError("Resoluções do catálogo não reconhecidas.")
        variant.update(duration_seconds=duration,
                       duration_adjustable=_field(row, 22, False) is True,
                       resolutions=list(dict.fromkeys(resolution_map[c] for c in resolutions)))
    feature_groups = _field(_field(row, 7 if mode == "video" else 8, []), 0, [])
    if not isinstance(feature_groups, list):
        raise ValueError("Entradas do catálogo não reconhecidas.")
    combinations = [_field(g, 0, []) for g in feature_groups]
    if any(not isinstance(c, list) or any(type(v) is not int or v <= 0 for v in c) for c in combinations):
        raise ValueError("Entradas de modelo não reconhecidas.")
    variant["input_feature_codes"] = combinations
    return variant


def quote_configuration(capabilities, model, *, aspect, count, max_credits, features,
                        duration_seconds=None, resolution="720p"):
    """Escolher somente a família pedida e o conjunto exato de entradas."""
    identifiers = {"veo-lite":"veo_3_1_lite", "veo-fast":"veo_3_1_fast",
        "veo-quality":"veo_3_1_quality", "omni-flash":"abra",
        # Em 05/10/2026 o Flow trocou Nano Banana 2 (narwhal_display) por Nano Banana 2.1.
        "nano-banana-2":"beluga_display", "nano-banana-2-lite":"harbor_seal",
        "nano-pro":"nano_banana_pro"}
    if model not in identifiers or type(count) is not int or not 1 <= count <= 4:
        raise ValueError("Modelo ou quantidade inválidos.")
    if type(max_credits) is not int or max_credits < 0:
        raise ValueError("Orçamento inválido.")
    mode = "image" if model in {"nano-banana-2", "nano-banana-2-lite", "nano-pro"} else "video"
    families = [m for m in capabilities["modes"][mode]["models"]
                if m["model_id"] == identifiers[model]]
    if len(families) != 1:
        raise ValueError(f"Modelo {model} ausente do catálogo desta conta (o Flow pode tê-lo renomeado); "
                         "consulte flow_get_capabilities.")
    for variant in families[0]["variants"]:
        if (not variant["available"] or aspect not in variant["aspects"]
                or not any(set(c) == set(features) for c in variant["input_feature_codes"])):
            continue
        if mode == "video" and (resolution not in variant["resolutions"] or
                (not variant["duration_adjustable"] and variant["duration_seconds"] != duration_seconds)):
            continue
        total = variant["credits_per_output"] * count
        if total > max_credits:
            raise ValueError(f"Custo de {total} créditos acima do orçamento autorizado (max_credits={max_credits}); "
                             "nada foi enviado.")
        return {"model_key":variant["model_key"], "credits_per_output":variant["credits_per_output"],
                "quoted_credits":total, "source":"HTTP/HTrJv", "service_tier_code":capabilities["service_tier_code"],
                "observed_at":capabilities["observed_at"]}
    raise ValueError("Configuração solicitada não disponível nesta conta; envio bloqueado. "
                     f"Opções de {model}: {_describe_variants(families[0]['variants'], mode, features)}.")


# Nomes legíveis dos códigos de entrada usados em `features`.
_FEATURE_NAMES = {1: "texto", 4: "referências", 5: "quadro inicial", 6: "referências",
                  7: "quadro final", 14: "extensão", 18: "edição", 19: "edição", 20: "edição"}


def _inputs(combo) -> str:
    return "+".join(dict.fromkeys(_FEATURE_NAMES.get(code, str(code)) for code in combo))


def _describe_variants(variants, mode, features) -> str:
    """Resumo curto do que existe, para o agente ajustar o pedido.

    Com as mesmas entradas pedidas, lista formato/duração/resolução/custo; sem
    nenhuma variante para essas entradas, lista as combinações de entrada aceitas.
    """
    available = [v for v in variants if v["available"]]
    same_inputs = [v for v in available if any(set(c) == set(features) for c in v["input_feature_codes"])]
    if not same_inputs:
        combos = sorted({_inputs(c) for v in available for c in v["input_feature_codes"]})
        return (f"nenhuma variante aceita as entradas pedidas ({_inputs(features)}); entradas aceitas: "
                + (", ".join(combos) or "nenhuma neste plano"))
    options = []
    for variant in same_inputs:
        size = ""
        if mode == "video":
            duration = "duração ajustável" if variant["duration_adjustable"] else f"{variant['duration_seconds']}s"
            size = f"{duration} {'/'.join(variant['resolutions'])} "
        options.append(f"{size}{'/'.join(variant['aspects'])} = {variant['credits_per_output']} créditos")
    text = "; ".join(dict.fromkeys(options))
    return text if len(text) <= 600 else text[:600] + "… (veja flow_get_capabilities)"


async def read_capabilities(account_id: str, project_id: str, *, client=None) -> dict:
    from flow_http import FlowHTTP
    from flow_credits import parse_http_credits

    validate_project(project_id)
    if client is not None and client.account_id != account_id:
        raise ValueError("Sessão HTTP pertence a outra conta.")
    owned = client is None
    client = client or FlowHTTP(account_id)
    try:
        project = await client.rpc("ngNC2", params=[f"tools/PINHOLE/projects/{project_id}"])
        if _field(project, 0) != project_id:
            raise ValueError("Projeto não confirmado nesta conta.")
        credits = await client.rpc("nzlxg")
        balance, tier = parse_http_credits(credits), _field(credits, 3)
        statuses = parse_model_statuses(await client.rpc("yBhWQ", params=[]))
        modes = parse_capabilities(await client.rpc("HTrJv", params=[]), tier, statuses)
        return {"account_id":account_id, "project_id":project_id, "status":"ok", "source":"HTTP/HTrJv",
                "observed_at":datetime.now(timezone.utc).isoformat(), "credits":balance,
                "service_tier_code":tier, "modes":modes,
                "scope":"Catálogo remoto e preços por plano; seleção atual do compositor não lida. "
                        "Disponibilidade não comprova implementação ou validação da operação no MCP."}
    finally:
        if owned:
            await client.close()


async def read_browser_capabilities(account_id: str, project_id: str) -> dict:
    from gflow_cli.api.transports.migrated_composer import MigratedComposer, MENU_ITEM

    validate_project(project_id)
    result = {"account_id": account_id, "project_id": project_id,
              "source": "flow.google.com/UI", "modes": {}}
    async with account_page(account_id) as page:
        composer = MigratedComposer()
        await composer.ensure_editor(page, project_id)
        pane = await composer._open_pane(page)
        initial = await pane.locator("[role=radio][aria-checked=true] mat-icon").all_inner_texts()
        original = "image" if "image" in initial else "videocam"
        try:
            for mode, lig in (("video", "videocam"), ("image", "image")):
                await composer._select(page, pane, axis="mode", lig=lig)
                options = await pane.locator("[role=radio]").evaluate_all(
                    "els => els.map(e=>({label:e.innerText.trim(), selected:e.getAttribute('aria-checked')==='true', disabled:e.getAttribute('aria-disabled')==='true'}))")
                button = pane.locator("button").filter(has=page.locator("mat-icon").filter(has_text="arrow_drop_down")).first
                current = (await button.inner_text()).strip()
                await button.click(timeout=5000)
                items = page.locator(MENU_ITEM)
                await items.first.wait_for(state="visible", timeout=5000)
                models = await items.evaluate_all(
                    "els => els.map(e=>({label:e.innerText.trim(), disabled:e.disabled===true || e.getAttribute('aria-disabled')==='true'}))")
                await page.keyboard.press("Escape")
                result["modes"][mode] = {"selected_model": current, "models": models, "options": options}
        finally:
            try:
                await composer._select(page, pane, axis="mode", lig=original)
            finally:
                await composer._close_pane(page, strict=False)
    result["observed_at"] = datetime.now(timezone.utc).isoformat()
    result["scope"] = "Compositor; opções de duração referem-se ao modelo selecionado, demais recursos não verificados."
    return result
