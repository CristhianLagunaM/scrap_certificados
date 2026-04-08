FROM python:3.10-bullseye

ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Dependencias necesarias para Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget curl unzip git \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdbus-1-3 libdbus-glib-1-2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libasound2 libxshmfence1 libxfixes3 libx11-xcb1 \
    libx11-6 libxcb1 libdrm2 libxext6 libxrender1 \
    libpango-1.0-0 libcairo2 libpangocairo-1.0-0 \
    libgtk-3-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias Python
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Instalar Playwright y Chromium
RUN pip install playwright && playwright install chromium

# Copiar código de la aplicación
COPY . .

EXPOSE 8000

# Gunicorn aumentado de timeout porque Playwright tarda
CMD ["gunicorn", "wsgi:app", "--bind", "0.0.0.0:8000", "--timeout", "600"]
