#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/vi/Documentos/certificado/scrap_certificados"
RUNTIME_DIR="${APP_ROOT}/.runtime"
PID_FILE="${RUNTIME_DIR}/cloudflared.pid"

cd "${APP_ROOT}"

if ! docker ps --filter name=scrap-certificados-app --filter status=running --format '{{.Names}}' | grep -q '^scrap-certificados-app$'; then
  ./deploy/local/start_local_services.sh
  exit 0
fi

if [[ -f "${PID_FILE}" ]] && kill -0 "$(cat "${PID_FILE}")" 2>/dev/null; then
  exit 0
fi

rm -f "${PID_FILE}"
./deploy/local/start_local_services.sh
