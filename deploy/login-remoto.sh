#!/bin/bash
# Login remoto na Banana Pi: Chromium normal (sem automação) num display virtual, publicado por noVNC (HTTP, rede local).
# Você abre o link no seu PC, entra no Google, e a sessão nasce no perfil da Banana Pi.
# Uso: login-remoto.sh <conta> [minutos] [email]   (FRESH=1 apaga antes o perfil existente da conta)
set -u
ACC=${1:?uso: login-remoto.sh <conta> [minutos] [email]}; MIN=${2:-20}; EMAIL=${3:-}
source /mnt/ssd/flow-mcp/env.sh
export DISPLAY=:77 PYTHONPATH=$HOME_FLOW/app
IP=$(hostname -I | awk '{print $1}'); PASS=$(openssl rand -hex 4); PORT=6080
PDIR=$HOME_FLOW/home/profile_$ACC
[ "${FRESH:-0}" = 1 ] && rm -rf "$PDIR"
mkdir -p -m 700 "$PDIR"
pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null; rm -f "$HOME_FLOW"/tmp/vncpass; }
trap cleanup EXIT
Xvfb :77 -screen 0 1366x800x24 -nolisten tcp & pids+=($!)
sleep 1
x11vnc -storepasswd "$PASS" "$HOME_FLOW/tmp/vncpass" >/dev/null 2>&1
x11vnc -display :77 -rfbauth "$HOME_FLOW/tmp/vncpass" -localhost -forever -shared -quiet -rfbport 5977 >/dev/null 2>&1 & pids+=($!)
"$HOME_FLOW/vnc-venv/bin/python" -m websockify --web "$HOME_FLOW/novnc" 0.0.0.0:$PORT localhost:5977 >/dev/null 2>&1 & pids+=($!)
echo "LINK: http://$IP:$PORT/vnc.html?autoconnect=1&resize=scale"
echo "SENHA: $PASS"
echo "Valido por $MIN min. Conta (apelido): $ACC"
# O Flow às vezes abre antes de a sessão estar gravada; se a conferência falhar, reabre o navegador no mesmo perfil.
END=$((SECONDS + MIN * 60)); RES="RESULTADO: login nao concluido (prazo ou navegador fechado)"
for attempt in 1 2 3; do
  "$CHROME_BINARY" --user-data-dir="$PDIR" --no-first-run --no-default-browser-check --password-store=basic \
    --remote-debugging-port=9333 --window-position=0,0 --window-size=1300,780 \
    "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fflow.google.com%2F" >/dev/null 2>&1 & CH=$!
  ok=0
  while [ $SECONDS -lt $END ]; do
    sleep 5
    kill -0 "$CH" 2>/dev/null || break
    if curl -s localhost:9333/json 2>/dev/null | grep -Eq '"url": "https://flow\.google\.com/(\?[^"]*|#[^"]*|project/[^"]*)?"'; then ok=1; break; fi
  done
  if [ $ok != 1 ]; then kill "$CH" 2>/dev/null; break; fi
  echo "Login detectado; consolidando o perfil..."
  sleep 20; kill -TERM "$CH" 2>/dev/null; wait "$CH" 2>/dev/null; sleep 3
  echo -n chrome > "$PDIR/.gflow_browser_strategy"; [ -n "$EMAIL" ] && echo -n "$EMAIL" > "$PDIR/.gflow_account"
  RES=$(cd "$HOME_FLOW/app" && uv run --locked python -c '
import asyncio, json, sys
from keepalive import check
print("RESULTADO:", json.dumps(asyncio.run(check(sys.argv[1]))))
' "$ACC" 2>&1 | grep RESULTADO)
  echo "$RES" | grep -q '"status": "ok"' && break
  echo "Sessao ainda nao confirmada (tentativa $attempt); reabrindo o navegador, termine o login na mesma janela."
done
echo "$RES"
echo "ENCERRADO"
