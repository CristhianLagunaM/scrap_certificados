#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/vi/Documentos/certificado/scrap_certificados"
ENV_FILE="${APP_ROOT}/.env.named-tunnel"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Falta ${ENV_FILE}. Copia .env.named-tunnel.example y pega el token del tunnel."
  exit 1
fi

cd "${APP_ROOT}"
docker compose --env-file "${ENV_FILE}" -f docker-compose.named-tunnel.yml up -d
docker compose --env-file "${ENV_FILE}" -f docker-compose.named-tunnel.yml ps
