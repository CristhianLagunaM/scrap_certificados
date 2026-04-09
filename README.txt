🚀 Procesador de Certificados – MinInterior

Aplicación web en Flask + Playwright para descargar certificados automáticos del Ministerio del Interior:

Minorías

Indígenas

Permite cargar un archivo Excel, scrapear certificados oficiales y generar archivos PDF y Excel de resumen.

Despliegue recomendado sin túneles: Oracle Cloud Always Free

Archivos preparados para Oracle Ubuntu 22.04:

- `deploy/oracle/bootstrap_oracle_ubuntu.sh`
- `deploy/oracle/scrap-certificados.service`
- `deploy/oracle/nginx-scrap-certificados.conf`

Flujo sugerido:

1. Crear una VM Ubuntu en Oracle Cloud Always Free.
2. Abrir puerto 80 en el Security List o Network Security Group.
3. Clonar este proyecto en `/home/ubuntu/scrap_certificados`.
4. Dar permisos y ejecutar:

   `chmod +x deploy/oracle/bootstrap_oracle_ubuntu.sh`

   `./deploy/oracle/bootstrap_oracle_ubuntu.sh`

5. Probar entrando a la IP pública de la VM.

Logs útiles:

- App: `sudo journalctl -u scrap-certificados.service -f`
- Nginx: `sudo tail -f /var/log/nginx/error.log`

Si actualizas código:

- `git pull`
- `./venv/bin/pip install -r requirements.txt`
- `sudo systemctl restart scrap-certificados.service`

Despliegue local permanente con Docker + túnel

Archivos preparados:

- `docker-compose.yml`
- `deploy/local/scrap-certificados-docker.service`
- `deploy/local/cloudflared-quick.service`
- `deploy/local/cloudflared_quick_tunnel.sh`
- `deploy/local/start_local_services.sh`
- `deploy/local/monitor_local_services.sh`
- `deploy/local/stop_local_services.sh`
- `deploy/local/show_endpoints.sh`
- `deploy/local/tailscale-serve.service`

Objetivo:

- mantener la app disponible mientras el PC esté encendido
- publicar por web mediante Cloudflare Tunnel
- dejar una ruta alternativa por VPN usando Tailscale

Servicios:

- `scrap-certificados-docker.service`: levanta la app con Docker Compose
- `cloudflared-quick.service`: mantiene el quick tunnel y escribe la URL en `.runtime/public_url.txt`
- `tailscale-serve.service`: publica la app solo dentro de la red Tailscale

Sin privilegios root, la automatización puede dejarse con `crontab`:

- `deploy/local/start_local_services.sh`
- `deploy/local/stop_local_services.sh`
- `deploy/local/monitor_local_services.sh`

Named tunnel de Cloudflare con dominio fijo

Nota importante:

- Los quick tunnels de Cloudflare son para pruebas y no soportan SSE.
- Para una URL estable y mejor comportamiento, usa un named tunnel.

Archivos preparados:

- `.env.named-tunnel.example`
- `docker-compose.named-tunnel.yml`
- `deploy/local/start_named_tunnel.sh`
- `deploy/local/stop_named_tunnel.sh`

Flujo:

1. En Cloudflare Zero Trust o Dashboard, crea un Tunnel.
2. Publica un hostname, por ejemplo `app.tudominio.com`, apuntando al origen `http://127.0.0.1:8001`.
3. Copia el token del túnel.
4. Crea el archivo `.env.named-tunnel` basado en `.env.named-tunnel.example`.
5. Ejecuta:

   `./deploy/local/start_named_tunnel.sh`

Para detenerlo:

`./deploy/local/stop_named_tunnel.sh`

Comandos útiles:

- `sudo systemctl status scrap-certificados-docker.service`
- `sudo systemctl status cloudflared-quick.service`
- `journalctl -u cloudflared-quick.service -f`
- `./deploy/local/show_endpoints.sh`
