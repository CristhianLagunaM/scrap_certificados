#!/usr/bin/env bash
set -euo pipefail

RUNTIME_DIR="/home/vi/Documentos/certificado/scrap_certificados/.runtime"
URL_FILE="${RUNTIME_DIR}/public_url.txt"

echo "Docker app:"
docker ps --filter name=scrap-certificados-app --format '  {{.Status}}'

echo "LAN route:"
ip -4 addr show | awk '/inet / && $2 !~ /^127\./ && $2 !~ /^172\.(17|18)\./ {print $2}' | head -n 1 | cut -d/ -f1 | sed 's#^#  http://#; s#$#:8001#' || true

if [[ -f "${URL_FILE}" ]] && [[ -s "${URL_FILE}" ]]; then
  echo "Web tunnel:"
  sed 's/^/  /' "${URL_FILE}"
else
  echo "Web tunnel:"
  echo "  URL no disponible aun"
fi

if command -v tailscale >/dev/null 2>&1; then
  echo "VPN route:"
  tailscale status --json 2>/dev/null | python3 - <<'PY'
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    print("  Tailscale no autenticado aun")
    raise SystemExit(0)
self_info = data.get("Self", {}) or {}
dns_name = (self_info.get("DNSName") or "").rstrip(".")
tailscale_ips = self_info.get("TailscaleIPs") or []
if dns_name:
    print(f"  http://{dns_name}")
elif tailscale_ips:
    print(f"  http://{tailscale_ips[0]}")
else:
    print("  Tailscale instalado pero sin ruta disponible")
PY
else
  echo "VPN route:"
  echo "  Tailscale no instalado"
fi
