"""Mantém as sessões vivas: consulta o saldo de cada perfil (sem gerar nada) e registra o status.

Uso (cron):  python keepalive.py [--log CAMINHO]
Sai com 1 se alguma conta não estiver 'ok'. Perfil em uso por outro worker conta como 'busy'.
"""
import argparse, asyncio, json, os, time
from datetime import datetime, timezone
from pathlib import Path

MAX_LINES = 1000  # ponytail: log aparado por contagem de linhas; trocar por logrotate se crescer


def accounts(root: Path) -> list[str]:
    return sorted(p.name.removeprefix("profile_") for p in root.glob("profile_*") if p.is_dir())


async def check(account: str) -> dict:
    from flow_http import FlowHTTP, http_operation

    client, t = FlowHTTP(account, resident=True), time.monotonic()
    try:
        r = await asyncio.wait_for(http_operation(client, "credits", {}), 180)
        out = {"status": r.get("status"), "credits": r.get("credits")}
    except Exception as exc:
        busy = "lease" in type(exc).__name__.lower() or "lock" in type(exc).__name__.lower()
        out = {"status": "busy" if busy else "error", "error_type": type(exc).__name__}
    finally:
        await client.close()
    return {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "account_id": account,
            "seconds": round(time.monotonic() - t, 1), **out}


async def main(log: Path) -> int:
    root = Path(os.environ.get("FLOW_MCP_HOME", Path(__file__).parent / "profiles"))
    results = [await check(a) for a in accounts(root)]
    log.parent.mkdir(parents=True, exist_ok=True)
    lines = (log.read_text(encoding="utf-8").splitlines() if log.exists() else []) + [json.dumps(r) for r in results]
    log.write_text("\n".join(lines[-MAX_LINES:]) + "\n", encoding="utf-8")
    for r in results:
        print(json.dumps(r))
    return 0 if all(r["status"] in {"ok", "busy"} for r in results) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=Path(__file__).parent / "keepalive.log")
    raise SystemExit(asyncio.run(main(ap.parse_args().log)))
