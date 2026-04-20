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

**Response 201** (создан новый):
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=443&secret=ee...",
  "created": true
}
```

**Response 200** (уже существует):
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=443&secret=ee...",
  "created": false
}
```

---

## DELETE /api/v1/access/{user_id}
Отозвать доступ пользователя.

**Response 204** — успешно отозван.  
**Response 404** — пользователь не найден.

---

## GET /api/v1/access/{user_id}/link
Получить ссылку для конкретного пользователя.

**Response 200:**
```json
{
  "user_id": "123456789",
  "link": "https://t.me/proxy?server=1.2.3.4&port=443&secret=ee..."
}
```

**Response 404** — пользователь не найден.

---

## GET /api/v1/access
Список всех пользователей с доступом.

**Response 200:**
```json
[
  { "user_id": "123456789", "link": "https://t.me/proxy?..." },
  { "user_id": "987654321", "link": "https://t.me/proxy?..." }
]
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
# Выдать доступ
curl -X POST http://VPS:8080/api/v1/access \
  -H "X-Api-Key: your_api_key" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "123456789"}'

# Получить ссылку
curl http://VPS:8080/api/v1/access/123456789/link \
  -H "X-Api-Key: your_api_key"

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
