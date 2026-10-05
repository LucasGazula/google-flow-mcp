#!/bin/bash
# Login remoto na Banana Pi: Chromium normal (sem automação) num display virtual, publicado por noVNC/HTTPS.
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
cleanup() { kill "${pids[@]}" 2>/dev/null; rm -f "$HOME_FLOW"/tmp/{vncpass,novnc.key,novnc.crt}; }
trap cleanup EXIT
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$HOME_FLOW/tmp/novnc.key" -out "$HOME_FLOW/tmp/novnc.crt" -days 1 -subj "/CN=$IP" 2>/dev/null
Xvfb :77 -screen 0 1366x800x24 -nolisten tcp & pids+=($!)
sleep 1
x11vnc -storepasswd "$PASS" "$HOME_FLOW/tmp/vncpass" >/dev/null 2>&1
x11vnc -display :77 -rfbauth "$HOME_FLOW/tmp/vncpass" -localhost -forever -shared -quiet -rfbport 5977 >/dev/null 2>&1 & pids+=($!)
"$HOME_FLOW/vnc-venv/bin/python" -m websockify --web "$HOME_FLOW/novnc" --cert "$HOME_FLOW/tmp/novnc.crt" --key "$HOME_FLOW/tmp/novnc.key" 0.0.0.0:$PORT localhost:5977 >/dev/null 2>&1 & pids+=($!)
"$CHROME_BINARY" --user-data-dir="$PDIR" --no-first-run --no-default-browser-check --password-store=basic \
  --remote-debugging-port=9333 --window-position=0,0 --window-size=1300,780 \
  "https://accounts.google.com/ServiceLogin?continue=https%3A%2F%2Fflow.google.com%2F" >/dev/null 2>&1 & CH=$!
echo "LINK: https://$IP:$PORT/vnc.html?autoconnect=1&resize=scale"
echo "SENHA: $PASS"
echo "Valido por $MIN min. Conta (apelido): $ACC"
ok=0
for _ in $(seq 1 $((MIN * 12))); do
  sleep 5
  kill -0 "$CH" 2>/dev/null || break
  if curl -s localhost:9333/json 2>/dev/null | grep -Eq '"url": "https://flow\.google\.com/(\?[^"]*|#[^"]*|project/[^"]*)?"'; then ok=1; break; fi
done
if [ $ok = 1 ]; then
  echo "Login detectado; consolidando o perfil..."
  sleep 20; kill -TERM "$CH" 2>/dev/null; wait "$CH" 2>/dev/null; sleep 3
  echo -n chrome > "$PDIR/.gflow_browser_strategy"; [ -n "$EMAIL" ] && echo -n "$EMAIL" > "$PDIR/.gflow_account"
  cd "$HOME_FLOW/app" && uv run --locked python -c '
import asyncio, json, sys
from keepalive import check
print("RESULTADO:", json.dumps(asyncio.run(check(sys.argv[1]))))
' "$ACC" 2>&1 | grep RESULTADO
else
  kill "$CH" 2>/dev/null; echo "RESULTADO: login nao concluido (prazo ou navegador fechado)"
fi
echo "ENCERRADO"
