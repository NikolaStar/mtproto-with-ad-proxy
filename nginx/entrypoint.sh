#!/bin/sh
set -e

# Записываем сертификат и ключ из env-переменных в файлы
# (Cloudflare Origin Certificate, вставляется в .env как многострочная переменная)
# Cert хранится в .env как однострочная \n-escaped строка — раскрываем обратно
printf '%b' "$CF_ORIGIN_CERT" > /etc/nginx/certs/origin.pem
printf '%b' "$CF_ORIGIN_KEY"  > /etc/nginx/certs/origin.key

exec nginx -g "daemon off;"
