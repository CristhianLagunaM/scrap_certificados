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
