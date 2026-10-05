"""Ponte temporária para sessão Google: somente loopback, pareada, sem logs."""

import argparse
import asyncio
from contextlib import redirect_stderr, redirect_stdout
import hmac
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
import os
from pathlib import Path
import re
import secrets
import subprocess
import threading
import time

from flow_accounts import validate_account

MAX_BODY = 1024 * 1024
DOMAINS = {"google.com", "www.google.com", "accounts.google.com", "labs.google", "flow.google.com"}
TTL = 300


def normalize_cookies(payload: object) -> list[dict]:
    """Valida todos os campos antes de escrever/importar uma sessão."""
    if not isinstance(payload, dict) or not isinstance(payload.get("cookies"), list):
        raise ValueError("Formato de sessão inválido.")
    cookies = payload["cookies"]
    if not 1 <= len(cookies) <= 1000:
        raise ValueError("Quantidade de cookies inválida.")
    normalized = []
    seen = set()
    for c in cookies:
        if not isinstance(c, dict):
            raise ValueError("Cookie inválido.")
        domain, name, value, path = (c.get(k) for k in ("domain", "name", "value", "path"))
        if (not isinstance(domain, str) or domain.lstrip(".") not in DOMAINS or
                domain not in DOMAINS | {"." + d for d in DOMAINS} or
                not isinstance(name, str) or not 1 <= len(name) <= 256 or
                not isinstance(value, str) or len(value) > 16384 or
                not isinstance(path, str) or not path.startswith("/") or len(path) > 2048 or
                any(ch in name + value + path for ch in "\r\n\x00") or "partitionKey" in c):
            raise ValueError("Cookie fora do escopo permitido.")
        for key in ("secure", "httpOnly", "hostOnly"):
            if key in c and not isinstance(c[key], bool):
                raise ValueError("Atributo de cookie inválido.")
        same_site = c.get("sameSite", "unspecified")
        mapping = {"strict": "Strict", "lax": "Lax", "no_restriction": "None", "unspecified": "Lax"}
        if same_site not in mapping or (same_site == "no_restriction" and not c.get("secure", False)):
            raise ValueError("SameSite inválido.")
        expires = c.get("expirationDate", -1)
        if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
            raise ValueError("Expiração inválida.")
        if expires != -1 and expires <= time.time():
            continue
        key = (domain, path, name)
        if key in seen:
            raise ValueError("Cookie duplicado.")
        seen.add(key)
        normalized.append({"name": name, "value": value, "domain": domain, "path": path,
                           "secure": c.get("secure", False), "httpOnly": c.get("httpOnly", False),
                           "sameSite": mapping[same_site], "expires": expires})
    if not normalized:
        raise ValueError("Sessão vazia ou expirada.")
    return normalized


class SessionBridge:
    def __init__(self, account_id: str, ttl: float = TTL):
        self.account_id = validate_account(account_id)
        self.token = secrets.token_hex(32)
        self.deadline = time.monotonic() + ttl
        self.payload = None
        self.used = False
        self.closed = False
        self.received = threading.Event()
        self.lock = threading.Lock()
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(3)

            def log_message(self, *args):
                pass  # URLs e cabeçalhos de pareamento não entram em logs.

            def allowed(self):
                origin = self.headers.get("Origin")
                return (self.headers.get("Host") == f"127.0.0.1:{bridge.port}" and
                        (origin is None or re.fullmatch(r"chrome-extension://[a-p]{32}", origin)))

            def respond(self, code, body=b"", content_type="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", content_type)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
                self.send_header("Referrer-Policy", "no-referrer")
                origin = self.headers.get("Origin")
                if self.allowed() and origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                    self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Flow-Pairing")
                    self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if not self.allowed() or self.path != "/pair":
                    return self.respond(403)
                # A chave está apenas no fragmento da URL, nunca no HTML ou HTTP.
                body = ("<!doctype html><html lang='pt-BR'><meta charset='utf-8'>"
                        "<title>Conectar Google Flow MCP</title><h1>Conectar Google Flow MCP</h1>"
                        f"<p>Perfil de destino: {bridge.account_id}</p>"
                        "<p>Mantenha esta aba aberta. Clique na extensão Google Flow MCP e "
                        "depois em Conectar sessão.</p><p>A conexão expira em cinco minutos. "
                        "Nenhum vídeo será gerado.</p></html>").encode()
                self.respond(200, body, "text/html; charset=utf-8")

            def do_OPTIONS(self):
                self.respond(204 if self.allowed() else 403)

            def do_POST(self):
                if not self.allowed() or self.path != "/session":
                    return self.respond(403)
                with bridge.lock:
                    if (bridge.closed or time.monotonic() >= bridge.deadline or bridge.used or
                            not re.fullmatch(r"[a-f0-9]{64}", self.headers.get("X-Flow-Pairing", "")) or
                            not hmac.compare_digest(self.headers.get("X-Flow-Pairing", ""), bridge.token)):
                        return self.respond(403)
                    try:
                        length = int(self.headers.get("Content-Length", "0"))
                        if (not 0 < length <= MAX_BODY or self.headers.get_content_type() != "application/json" or
                                self.headers.get("Transfer-Encoding") or len(self.headers.get_all("Content-Length", [])) != 1):
                            return self.respond(400)
                        raw = self.rfile.read(length)
                        if len(raw) != length:
                            return self.respond(400)
                        payload = json.loads(raw)
                        normalize_cookies(payload)
                        # Somente o formato documentado é mantido em memória.
                        bridge.payload = {"cookies": [{k: v for k, v in c.items() if k in {
                            "name", "value", "domain", "path", "secure", "httpOnly", "hostOnly",
                            "sameSite", "expirationDate"}} for c in payload["cookies"]]}
                        bridge.used = True
                        bridge.received.set()
                        self.respond(200, b'{"ok":true}')
                    except (ValueError, TypeError, OSError):
                        self.respond(400, b'{"error":"invalid_session"}')

        # ponytail: uma captura por ponte; criar outra ponte para conectar outra conta.
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.timer = threading.Timer(ttl, self.close)
        self.timer.daemon = True
        self.timer.start()

    def open_browser(self):
        from gflow_cli.browser_manager import resolved_chrome_binary
        chrome = resolved_chrome_binary()
        if not chrome:
            raise RuntimeError("Chrome/Chromium não encontrado.")
        # Sem --user-data-dir: abre a aba no Chrome normal já conectado.
        subprocess.Popen([chrome, f"http://127.0.0.1:{self.port}/pair#{self.token}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def take(self):
        with self.lock:
            if self.payload is None or time.monotonic() >= self.deadline:
                raise ValueError("Sessão não enviada ou pareamento expirado.")
            payload, self.payload = self.payload, None
            self.token = ""  # A chave nunca pode ser reutilizada.
        self.close()
        return payload

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.closed = True
            self.payload = None
            self.token = ""
        self.timer.cancel()
        self.server.shutdown()
        self.server.server_close()


def main():
    parser = argparse.ArgumentParser(description="Capturar/importar sessão sem mostrar cookies.")
    parser.add_argument("action", choices=["connect", "export", "import"])
    parser.add_argument("account_id")
    parser.add_argument("--file", type=Path, help="Arquivo local para importação no destino.")
    args = parser.parse_args()
    validate_account(args.account_id)
    try:
        if args.action == "import":
            if args.file is None or args.file.stat().st_size > MAX_BODY:
                raise ValueError("Arquivo necessário ou grande demais.")
            payload = json.loads(args.file.read_text(encoding="utf-8"))
            normalize_cookies(payload)
        else:
            bridge = SessionBridge(args.account_id)
            try:
                bridge.open_browser()
                print("Na aba aberta, clique na extensão e em Conectar sessão. Aguardando por 5 minutos.", flush=True)
                if not bridge.received.wait(TTL):
                    raise ValueError("Pareamento expirado.")
                payload = bridge.take()
            finally:
                bridge.close()
        if args.action == "export":
            directory = Path(__file__).parent / "exports"
            directory.mkdir(mode=0o700, exist_ok=True)
            with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
                from gflow_cli.winsec import restrict_dir_to_current_user
                hardened = restrict_dir_to_current_user(directory)
                if os.name == "nt" and not hardened:
                    raise RuntimeError("Não foi possível proteger o diretório de exportação.")
            if os.name != "nt":
                directory.chmod(0o700)
            target = directory / f"session-{args.account_id}-{secrets.token_hex(4)}.json"
            fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(payload, file)
            print(f"Arquivo privado criado em {target}. Transfira por SSH/SCP; contém cookies em texto claro.")
        else:
            from flow_mcp import run_account_operation
            print(json.dumps(asyncio.run(run_account_operation("import", args.account_id, payload))))
    except Exception:
        print("Não foi possível concluir. Confira pareamento, arquivo, Chrome/Chromium e sessão local.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
