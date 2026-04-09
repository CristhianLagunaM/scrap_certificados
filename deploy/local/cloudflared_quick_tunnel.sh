#!/usr/bin/env bash
set -euo pipefail

APP_URL="http://127.0.0.1:8001"
RUNTIME_DIR="/home/vi/Documentos/certificado/scrap_certificados/.runtime"
LOG_FILE="${RUNTIME_DIR}/cloudflared.log"
URL_FILE="${RUNTIME_DIR}/public_url.txt"

mkdir -p "${RUNTIME_DIR}"
: > "${LOG_FILE}"
: > "${URL_FILE}"

while true; do
  while IFS= read -r line; do
    printf '%s\n' "${line}" | tee -a "${LOG_FILE}"
    if [[ "${line}" == *"https://"*".trycloudflare.com"* ]]; then
      url="$(printf '%s\n' "${line}" | grep -o 'https://[^ ]*trycloudflare.com' | head -n 1 || true)"
      if [[ -n "${url}" ]]; then
        printf '%s\n' "${url}" > "${URL_FILE}"
      fi
    fi
  done < <(stdbuf -oL cloudflared tunnel --url "${APP_URL}" --loglevel info 2>&1)

  printf '%s\n' "$(date '+%F %T') cloudflared finalizo, reintentando en 5 segundos..." | tee -a "${LOG_FILE}"
  sleep 5
done
