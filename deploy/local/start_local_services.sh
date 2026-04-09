#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/vi/Documentos/certificado/scrap_certificados"
RUNTIME_DIR="${APP_ROOT}/.runtime"
PID_FILE="${RUNTIME_DIR}/cloudflared.pid"
LOG_FILE="${RUNTIME_DIR}/autostart.log"

mkdir -p "${RUNTIME_DIR}"

cd "${APP_ROOT}"
docker compose up -d --build >> "${LOG_FILE}" 2>&1

if [[ -f "${PID_FILE}" ]]; then
  if kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
    exit 0
  fi
  rm -f "${PID_FILE}"
fi

setsid /bin/bash -lc "${APP_ROOT}/deploy/local/cloudflared_quick_tunnel.sh >> '${LOG_FILE}' 2>&1" >/dev/null 2>&1 &
echo $! > "${PID_FILE}"
