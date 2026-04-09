#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/home/vi/Documentos/certificado/scrap_certificados"
ENV_FILE="${APP_ROOT}/.env.named-tunnel"

cd "${APP_ROOT}"
docker compose --env-file "${ENV_FILE}" -f docker-compose.named-tunnel.yml down || true
