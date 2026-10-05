"""Saldo do host Flow atual; leitura da interface disponível para conferência."""

import re
from urllib.parse import urlsplit


def parse_http_credits(payload) -> int:
    # nzlxg observado no menu: o primeiro campo contém o saldo exibido.
    if not isinstance(payload, list) or len(payload) != 7 or type(payload[0]) is not int or payload[0] < 0:
        raise ValueError("Resposta de saldo não reconhecida.")
    return payload[0]


def parse_credit_count(text: str) -> int:
    # Aceita agrupamento de milhares observado em pt-BR/en; decimais e sinais falham.
    text = text.replace("\u00a0", " ").replace("\u202f", " ").strip()
    match = re.fullmatch(
        r"(?P<count>[0-9]{1,3}(?P<sep>[., ])[0-9]{3}(?:(?P=sep)[0-9]{3})*|[0-9]+)"
        r"\s+(?:créditos do Google Flow|Google Flow credits|AI credits|credits)",
        text, re.IGNORECASE,
    )
    if match is None:
        raise ValueError("Formato de saldo não reconhecido.")
    return int(re.sub(r"[., ]", "", match["count"]))


async def read_browser_credits(account_id: str) -> int:
    from flow_browser import account_page

    async with account_page(account_id) as page:
        await page.goto("https://flow.google.com", wait_until="domcontentloaded", timeout=25000)
        await page.get_by_role("button", name=re.compile(r"^Novo projeto$|^New project$")).wait_for(timeout=15000)
        if urlsplit(page.url).hostname != "flow.google.com":
            raise ValueError("Conta não chegou ao Flow esperado.")
        # Abrir somente detalhes da conta; não alterar plano nem criar projeto.
        await page.get_by_role("button", name=re.compile(r"^Detalhes da conta$|^Account details$")).click(timeout=5000)
        count = page.locator(".credits-count:visible")
        await count.wait_for(timeout=5000)
        return parse_credit_count(await count.inner_text(timeout=5000))
