"""Mantém as sessões vivas: consulta o saldo de cada perfil (sem gerar nada) e registra o status.

Ideias do 9Router adaptadas: execução única por vez, falhas isoladas por conta, pausa com jitter
entre contas do Google e estado persistente. Como o Google não informa quando invalida a sessão,
registra também um fingerprint do cookie de renovação para provar se ele realmente rotaciona.

Uso (cron):  python keepalive.py [--log CAMINHO] [--state CAMINHO]
Sai com 1 se alguma conta não estiver 'ok' (perfil ocupado por outro worker conta como 'busy').
"""
import argparse, asyncio, fcntl, hashlib, json, os, random, time
from datetime import datetime, timezone
from pathlib import Path

MAX_LINES = 1000  # ponytail: log aparado por contagem de linhas; trocar por logrotate se crescer
NEEDS_LOGIN_AFTER = 2  # falhas seguidas antes de declarar needs_login (evita alarme por falha de rede)
PAUSE_S = 30  # base da pausa entre contas, mais jitter de 0 a PAUSE_S


def accounts(root: Path) -> list[str]:
    return sorted(p.name.removeprefix("profile_") for p in root.glob("profile_*") if p.is_dir())


def fingerprint(client) -> str | None:
    """Hash curto do cookie de renovação (nunca o valor): muda quando o Google rotaciona a sessão."""
    try:
        values = sorted(c.value for c in client.client.cookies.jar if c.name == "__Secure-1PSIDTS")
        return hashlib.sha256("|".join(values).encode()).hexdigest()[:10] if values else None
    except Exception:
        return None


async def check(account: str) -> dict:
    from flow_http import FlowHTTP, http_operation

    client, t, fp = FlowHTTP(account, resident=True), time.monotonic(), None
    try:
        r = await asyncio.wait_for(http_operation(client, "credits", {}), 180)
        out = {"status": r.get("status"), "credits": r.get("credits")}
    except Exception as exc:
        busy = "lease" in type(exc).__name__.lower() or "lock" in type(exc).__name__.lower()
        out = {"status": "busy" if busy else "error", "error_type": type(exc).__name__}
    finally:
        fp = fingerprint(client)
        await client.close()
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "account_id": account,
            "seconds": round(time.monotonic() - t, 1), "rotation_fp": fp, **out}


def update_state(state: dict, r: dict) -> dict:
    s = state.setdefault(r["account_id"], {"failures": 0, "last_ok": None, "last_fp": None, "rotations": 0})
    if r["status"] == "ok":
        s["failures"], s["last_ok"] = 0, r["at"]
        if r["rotation_fp"] and s["last_fp"] and r["rotation_fp"] != s["last_fp"]:
            s["rotations"] += 1
        s["last_fp"] = r["rotation_fp"] or s["last_fp"]
    elif r["status"] != "busy":
        s["failures"] += 1
    s["needs_login"] = s["failures"] >= NEEDS_LOGIN_AFTER
    return s


async def main(log: Path, state_path: Path) -> int:
    log.parent.mkdir(parents=True, exist_ok=True)
    lock = open(state_path.with_suffix(".lock"), "w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"status": "skipped", "reason": "outra execução em andamento"}))
        return 0
    root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles"))
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    results = []
    for i, account in enumerate(accounts(root)):
        if i:
            await asyncio.sleep(PAUSE_S + random.uniform(0, PAUSE_S))
        r = await check(account)
        r["needs_login"] = update_state(state, r)["needs_login"]
        results.append(r)
    state_path.write_text(json.dumps(state, indent=1))
    state_path.chmod(0o600)
    lines = (log.read_text(encoding="utf-8").splitlines() if log.exists() else []) + [json.dumps(r) for r in results]
    log.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["status"] in {"ok", "busy"} for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=Path(__file__).parent / "keepalive.log")
    ap.add_argument("--state", type=Path, default=Path(__file__).parent / "keepalive-state.json")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.log, a.state)))
