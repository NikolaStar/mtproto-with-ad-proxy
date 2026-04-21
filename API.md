# MTProxy Access API

Base URL: `http://<VPS_IP>:8080`

Auth: заголовок `X-Api-Key: <API_KEY>` обязателен для всех ручек.

---

## POST /api/v1/access
Выдать доступ пользователю.

**Body:**
```json
{ "user_id": "123456789" }
```

Опциональное поле `no_ad` (по умолчанию `false`) — добавить пользователя на инстанс **без спонсорской рекламы** (порт `PROXY_PORT_NOAD`):

```json
{ "user_id": "123456789", "no_ad": true }
```

> Пользователь может находиться только в одном тире. Если он уже добавлен — возвращается его существующая ссылка (`created=false`), тир не меняется. Для смены тира: сначала `/revoke`, затем повторный вызов с нужным `no_ad`.

**Response 201** (создан новый):
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=2083&secret=dd...",
  "created": true,
  "no_ad": false
}
```

**Response 200** (уже существует):
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=2083&secret=dd...",
  "created": false,
  "no_ad": false
}
```

---

## PATCH /api/v1/access/{user_id}
Переместить пользователя на другой инстанс. Генерирует новый secret.

**Body:**
```json
{ "no_ad": true }
```

**Response 200:**
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=2084&secret=dd...",
  "created": true,
  "no_ad": true
}
```
`created=false` — пользователь уже был на запрошенном инстансе.  
**Response 404** — пользователь не найден.

---

## DELETE /api/v1/access/{user_id}
Отозвать доступ пользователя (из любого тира).

**Response 204** — успешно отозван.  
**Response 404** — пользователь не найден.

---

## GET /api/v1/access/{user_id}/link
Получить ссылку для конкретного пользователя.

**Response 200:**
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=2083&secret=dd...",
  "no_ad": false
}
```

**Response 404** — пользователь не найден.

---

## GET /api/v1/access
Список всех пользователей с доступом (оба тира).

**Response 200:**
```json
[
  { "user_id": "123456789", "link": "https://t.me/proxy?...", "no_ad": false },
  { "user_id": "987654321", "link": "https://t.me/proxy?...", "no_ad": true }
]
```

---

## GET /api/v1/access/{user_id}/limit
Получить лимит одновременных подключений пользователя.

**Response 200:**
```json
{
  "user_id": "123456789",
  "limit": 3,
  "is_custom": false,
  "default_limit": 3
}
```
`is_custom=false` — используется глобальный `DEFAULT_CONN_LIMIT`.  
**Response 404** — пользователь не найден.

---

## PUT /api/v1/access/{user_id}/limit
Установить индивидуальный лимит подключений.

**Body:**
```json
{ "limit": 5 }
```
`limit=null` (или не передавать) — сбросить на `DEFAULT_CONN_LIMIT`.

**Response 200:**
```json
{
  "user_id": "123456789",
  "limit": 5,
  "is_custom": true,
  "default_limit": 3
}
```

---

## GET /health
Healthcheck (без авторизации).

```json
{ "status": "ok" }
```

---

## Примеры (curl)

```bash
# Выдать доступ (с рекламой)
curl -X POST http://VPS:8080/api/v1/access \
  -H "X-Api-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123456789"}'

# Выдать доступ без рекламы
curl -X POST http://VPS:8080/api/v1/access \
  -H "X-Api-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123456789", "no_ad": true}'

# Получить ссылку
curl http://VPS:8080/api/v1/access/123456789/link \
  -H "X-Api-Key: your_api_key"

# Переместить на инстанс без рекламы
curl -X PATCH http://VPS:8080/api/v1/access/123456789 \
  -H "X-Api-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"no_ad": true}'

# Переместить обратно на инстанс с рекламой
curl -X PATCH http://VPS:8080/api/v1/access/123456789 \
  -H "X-Api-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"no_ad": false}'

# Отозвать доступ
curl -X DELETE http://VPS:8080/api/v1/access/123456789 \
  -H "X-Api-Key: your_api_key"

# Список всех
curl http://VPS:8080/api/v1/access \
  -H "X-Api-Key: your_api_key"
```

---

## Swagger UI
Доступен по адресу: `http://<VPS_IP>:8080/docs`
