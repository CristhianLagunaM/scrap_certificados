#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/ubuntu/scrap_certificados"
SERVICE_NAME="scrap-certificados.service"

echo "[1/8] Instalando paquetes del sistema..."
sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  nginx \
  unzip \
  curl \
  git \
  libnss3 \
  libatk1.0-0 \
  libatk-bridge2.0-0 \
  libcups2 \
  libdbus-1-3 \
  libxkbcommon0 \
  libxcomposite1 \
  libxdamage1 \
  libxrandr2 \
  libgbm1 \
  libasound2 \
  libxshmfence1 \
  libxfixes3 \
  libx11-xcb1 \
  libx11-6 \
  libxcb1 \
  libdrm2 \
  libxext6 \
  libxrender1 \
  libpango-1.0-0 \
  libcairo2 \
  libpangocairo-1.0-0 \
  libgtk-3-0

echo "[2/8] Creando entorno virtual..."
cd "${APP_DIR}"
python3 -m venv venv

echo "[3/8] Instalando dependencias Python..."
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

echo "[4/8] Instalando Chromium de Playwright..."
./venv/bin/playwright install chromium

echo "[5/8] Creando carpetas de trabajo..."
mkdir -p uploads salidas

echo "[6/8] Instalando servicio systemd..."
sudo cp deploy/oracle/scrap-certificados.service "/etc/systemd/system/${SERVICE_NAME}"
sudo systemctl daemon-reload
sudo systemctl enable "${SERVICE_NAME}"
sudo systemctl restart "${SERVICE_NAME}"

echo "[7/8] Instalando sitio Nginx..."
sudo cp deploy/oracle/nginx-scrap-certificados.conf /etc/nginx/sites-available/scrap-certificados
sudo ln -sf /etc/nginx/sites-available/scrap-certificados /etc/nginx/sites-enabled/scrap-certificados
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "[8/8] Estado final..."
sudo systemctl status "${SERVICE_NAME}" --no-pager
sudo systemctl status nginx --no-pager

echo
echo "Despliegue base completado."
echo "Si Oracle no abre el sitio, revisa las reglas de ingreso del Security List y el firewall local."
