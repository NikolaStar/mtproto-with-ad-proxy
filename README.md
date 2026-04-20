# MTProto Proxy + Webhook Bridge

Самодостаточный Docker-стек на VPS с тремя функциями:

1. **MTProto прокси** — личный Telegram прокси с рекламой канала и контролем доступа по `user_id`
2. **Webhook Bridge** — двусторонний HTTP прокси-посредник между Telegram и твоими ботами
3. **HTTP API + Telegram бот** — управление доступами к MTProto прокси

---

## Архитектура

```
                        ┌─────────────────────────────────────────┐
                        │              VPS (Ubuntu 24.04)          │
                        │                                          │
Telegram clients ───────┤─► mtproxy :2083   (MTProto proxy)       │
                        │                                          │
                        │       ┌── nginx :443 ──────────────┐    │
Cloudflare ─────────────┼──────►│                            │    │
 (Full SSL)             │       │  /webhook-proxy/*          │    │
                        │       │    ↓ проксирует в          │    │
Telegram webhooks ──────┼──────►│  https://<host>/<path>     │    │
                        │       │                            │    │
Твои боты ──────────────┼──────►│  (обратно — тоже сюда)     │    │
                        │       └────────────────────────────┘    │
                        │                                          │
Your app ───────────────┤─► access-bot :8080  (HTTP API)          │
Telegram admin ─────────┤─► access-bot        (Telegram бот)      │
                        │                                          │
                        │       redis  (хранит user→secret)        │
                        └─────────────────────────────────────────┘
```

---

## 1. MTProto прокси

Личный MTProto прокси с поддержкой **Fake-TLS** (трафик выглядит как HTTPS) и **рекламы канала**.

### Контроль доступа

Каждый разрешённый пользователь получает **уникальный secret**. Ссылка на прокси персональная — при отзыве доступа secret удаляется из конфига и прокси перезапускается. Пользователь теряет доступ немедленно.

```
tg://proxy?server=VPS_IP&port=2083&secret=ee<domain_hex><user_secret>
```

### Реклама канала (AD_TAG)

Пользователи прокси видят спонсорские посты твоего Telegram-канала. Получить тег:

1. Открой [@MTProxybot](https://t.me/MTProxybot) → `/newchannel`
2. Добавь бота администратором своего канала
3. Скопируй hex-тег → вставь в `.env` как `AD_TAG`

---

## 2. Webhook Bridge (двусторонний прокси)

Nginx принимает HTTPS от Cloudflare и проксирует запросы в обе стороны.

### Из Telegram → к твоему боту

Telegram шлёт вебхук на твой домен, nginx читает цель **прямо из URL** и форвардит:

```
POST https://yourdomain.com/webhook-proxy/bot.mysite.ru/bot/handler.php?token=abc
                                    ↓
POST https://bot.mysite.ru/bot/handler.php?token=abc
```

Формат: `/webhook-proxy/<host>/<path>?<query>` → `https://<host>/<path>?<query>`

Никакой конфигурации для каждого бота не нужно — цель извлекается динамически.

### SSL

Cloudflare Origin Certificate вставляется прямо в `.env` — никаких файлов сертификатов, никакого certbot.

---

## 3. HTTP API (управление доступами)

REST API для управления доступами к MTProto прокси. Используй из своего бота или приложения.

Аутентификация: заголовок `X-Api-Key: <API_KEY>`

| Метод | Путь | Действие |
|-------|------|----------|
| `POST` | `/api/v1/access` | Выдать доступ `{"user_id": "123"}` |
| `DELETE` | `/api/v1/access/{user_id}` | Отозвать доступ |
| `GET` | `/api/v1/access/{user_id}/link` | Получить ссылку пользователя |
| `GET` | `/api/v1/access` | Список всех пользователей |
| `GET` | `/health` | Healthcheck |

Swagger UI: `http://VPS_IP:8080/docs`

---

## 4. Telegram бот (опционально)

Если задан `BOT_TOKEN` — рядом с API стартует Telegram бот для ручного управления.

**Команды администратора** (задаются через `ADMIN_IDS`):

| Команда | Действие |
|---------|----------|
| `/allow <user_id>` | Выдать доступ, уведомить пользователя |
| `/revoke <user_id>` | Отозвать доступ, уведомить пользователя |
| `/list` | Список всех пользователей с доступом |
| `/reload` | Принудительно пересобрать конфиг прокси |

**Команды пользователя:**

| Команда | Действие |
|---------|----------|
| `/start` | Получить свою ссылку (если есть доступ) |
| `/mylink` | Показать персональную ссылку повторно |

> Узнать свой `user_id`: написать [@userinfobot](https://t.me/userinfobot)

---

## Деплой

### Требования
- VPS с Ubuntu 24.04
- Docker + Compose (`curl -fsSL https://get.docker.com | sh`)
- Домен в Cloudflare (для webhook bridge)

### 1. Клонировать

```bash
git clone git@github.com:NikolaStar/mtproto-with-ad-proxy.git /opt/mtproto
cd /opt/mtproto
```

### 2. Настроить `.env`

```bash
cp .env.example .env
nano .env
```

Обязательные поля:

```env
PROXY_HOST=1.2.3.4          # IP твоего VPS
API_KEY=supersecret          # ключ для HTTP API
REDIS_PASSWORD=supersecret2  # пароль Redis

# Cloudflare Origin Certificate (SSL/TLS → Origin Server → Create Certificate)
CF_ORIGIN_CERT="-----BEGIN CERTIFICATE-----
MIIEpDCC...
-----END CERTIFICATE-----"

CF_ORIGIN_KEY="-----BEGIN PRIVATE KEY-----
MIIEvgIB...
-----END PRIVATE KEY-----"
```

Опциональные (для Telegram бота):

```env
BOT_TOKEN=1234567890:AAxxx
ADMIN_IDS=123456789,987654321
```

### 3. Открыть порты

```bash
ufw allow 443/tcp    # nginx (webhook bridge)
ufw allow 2083/tcp   # MTProto proxy
ufw allow 8080/tcp   # HTTP API (закрой если не нужен внешний доступ)
```

### 4. Запустить

```bash
docker compose up -d
```

### 5. Cloudflare

- DNS → A-запись домена → IP VPS, проксирование включено (оранжевое облако)
- SSL/TLS → **Full**

---

## Конфигурация `.env`

| Переменная | Обязательно | Описание |
|------------|:-----------:|----------|
| `PROXY_HOST` | ✓ | IP VPS для генерации ссылок на прокси |
| `PROXY_PORT` | | Порт MTProto (по умолчанию `2083`) |
| `API_KEY` | ✓ | Ключ для HTTP API |
| `REDIS_PASSWORD` | ✓ | Пароль Redis |
| `CF_ORIGIN_CERT` | ✓ | Cloudflare Origin Certificate (PEM) |
| `CF_ORIGIN_KEY` | ✓ | Приватный ключ к сертификату |
| `AD_TAG` | | Hex-тег рекламного канала от @MTProxybot |
| `TLS_DOMAIN` | | Домен для Fake-TLS маскировки (по умолчанию `www.google.com`) |
| `BOT_TOKEN` | | Токен Telegram бота (если нужен бот) |
| `ADMIN_IDS` | | Telegram user_id администраторов через запятую |
| `API_PORT` | | Порт HTTP API (по умолчанию `8080`) |

---

## Структура проекта

```
.
├── docker-compose.yml
├── .env.example
├── mtproxy/                 # MTProto proxy (python mtprotoproxy)
│   ├── Dockerfile
│   └── entrypoint.sh        # ждёт config.py и запускает прокси
├── access-bot/              # HTTP API + опциональный Telegram бот
│   ├── main.py              # запускает FastAPI и бот параллельно
│   ├── manager.py           # логика: Redis, генерация секретов, конфиг
│   ├── api.py               # FastAPI роуты
│   ├── bot.py               # aiogram 3 хендлеры
│   └── Dockerfile
└── nginx/                   # Webhook bridge
    ├── conf.d/
    │   └── webhook-proxy.conf
    ├── entrypoint.sh        # записывает Origin Cert из env в файлы
    └── Dockerfile
```
