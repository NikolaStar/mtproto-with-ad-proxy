#!/bin/sh
set -e

CONF_DIR="/etc/nginx/conf.d"
TMPL_DIR="/etc/nginx/templates"

# Подставляем переменные окружения во все конфиги
for tmpl in "$TMPL_DIR"/*.conf; do
    name=$(basename "$tmpl")
    envsubst '${TG_API_DOMAIN} ${WEBHOOK_PROXY_DOMAIN}' < "$tmpl" > "$CONF_DIR/$name"
done

# Запускаем nginx + авторенев сертификатов в фоне
(while :; do sleep 12h; certbot renew --nginx --quiet; nginx -s reload; done) &

exec nginx -g "daemon off;"
