#!/usr/bin/env bash
set -euo pipefail

APP_SERVICE="scrap-certificados.service"
APP_URL="http://127.0.0.1:8000"
TUNNEL_LOG="/tmp/cloudflared.log"

echo "[1/4] Reiniciando ${APP_SERVICE}..."
if systemctl is-active --quiet "${APP_SERVICE}"; then
  systemctl stop "${APP_SERVICE}" || true
  sleep 2
fi

if systemctl is-active --quiet "${APP_SERVICE}"; then
  systemctl kill "${APP_SERVICE}" || true
  sleep 2
fi

systemctl start "${APP_SERVICE}"

echo "[2/4] Cerrando tuneles cloudflared previos..."
pkill -f "cloudflared tunnel --url ${APP_URL}" 2>/dev/null || true

echo "[3/4] Levantando tunel nuevo..."
: > "${TUNNEL_LOG}"
setsid /bin/bash -lc "cloudflared tunnel --url ${APP_URL} --loglevel debug > ${TUNNEL_LOG} 2>&1" >/dev/null 2>&1 &

echo "[4/4] Esperando URL publica..."
for _ in $(seq 1 20); do
  if rg -q 'https://.*trycloudflare.com' "${TUNNEL_LOG}"; then
    break
  fi
  sleep 1
done

URL="$(rg -o 'https://[^ ]+trycloudflare.com' "${TUNNEL_LOG}" | head -n 1 || true)"

echo "APP_SERVICE=${APP_SERVICE}"
echo "TUNNEL_LOG=${TUNNEL_LOG}"
if [[ -n "${URL}" ]]; then
  echo "PUBLIC_URL=${URL}"
else
  echo "PUBLIC_URL=NO_DISPONIBLE_AUN"
fi
