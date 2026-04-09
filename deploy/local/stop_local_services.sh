#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/vi/Documentos/certificado/scrap_certificados"
RUNTIME_DIR="${APP_ROOT}/.runtime"
PID_FILE="${RUNTIME_DIR}/cloudflared.pid"

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
  kill "$(cat "${PID_FILE}")" || true
  rm -f "${PID_FILE}"
fi

pkill -f "cloudflared tunnel --url http://127.0.0.1:8001" || true

cd "${APP_ROOT}"
docker compose down
