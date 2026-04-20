#!/bin/bash
# Запускать ОДИН РАЗ перед первым docker compose up
# Получает Let's Encrypt сертификаты для обоих доменов
#
# Предварительно:
#   1. Оба домена ($TG_API_DOMAIN, $WEBHOOK_PROXY_DOMAIN) уже смотрят на IP этого сервера
#   2. Порт 80 открыт
#   3. Заполнен .env

set -e
source "$(dirname "$0")/../.env"

EMAIL="${CERT_EMAIL:-admin@${WEBHOOK_PROXY_DOMAIN}}"

docker compose run --rm --entrypoint "" nginx \
  certbot certonly \
    --standalone \
    --non-interactive \
    --agree-tos \
    --email "$EMAIL" \
    -d "$TG_API_DOMAIN" \
    -d "$WEBHOOK_PROXY_DOMAIN"

echo "Сертификаты получены. Теперь запускай: docker compose up -d"
