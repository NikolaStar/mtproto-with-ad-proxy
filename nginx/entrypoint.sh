#!/bin/sh
set -e

# Записываем сертификат и ключ из env-переменных в файлы
# (Cloudflare Origin Certificate, вставляется в .env как многострочная переменная)
printf '%s' "$CF_ORIGIN_CERT" > /etc/nginx/certs/origin.pem
printf '%s' "$CF_ORIGIN_KEY"  > /etc/nginx/certs/origin.key

exec nginx -g "daemon off;"
