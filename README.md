# TeleGate

Самодостаточный Docker-стек на VPS с четырьмя функциями:

1. **MTProto прокси** — личный Telegram-прокси с рекламой канала и контролем доступа по `user_id`
2. **Telegram API прокси** — домен работает заменой `api.telegram.org` (бот-запросы, вебхуки)
3. **Webhook Bridge** — динамический HTTP-прокси: цель извлекается прямо из URL
4. **HTTP API + Telegram бот** — управление доступами к MTProto прокси

---

## Быстрый старт

```bash
git clone git@github.com:NikolaStar/mtproto-with-ad-proxy.git
cd mtproto-with-ad-proxy
./install.sh
```

Установщик сам запросит все необходимые данные и поднимет стек.

---

## Архитектура

```
                        ┌─────────────────────────────────────────┐
                        │              VPS (Ubuntu 24.04)          │
                        │                                          │
Telegram clients ───────┤──► mtproxy      :2083  (с рекламой)     │
                        │──► mtproxy-noad :2084  (без рекламы)    │
                        │                                          │
                        │       ┌── nginx :443 ──────────────┐    │
Cloudflare (Full SSL) ──┼──────►│                            │    │
Bot API / webhooks ─────┼──────►│  /webhook-proxy/*          │    │
                        │       │    → https://<host>/<path> │    │
                        │       │  /*  → api.telegram.org    │    │
                        │       └────────────────────────────┘    │
                        │                                          │
HTTP API clients ───────┤──► access-bot :8080  (FastAPI)          │
Telegram admin ─────────┤──► access-bot        (aiogram бот)      │
                        │                                          │
                        │       redis  (users / users_noad)       │
                        └─────────────────────────────────────────┘
```

---

## Установщик (`install.sh`)

Интерактивный мастер установки с отслеживанием выполненных шагов.

```bash
./install.sh                      # обычный запуск — пропускает готовые шаги
./install.sh --force              # полная переустановка всего
./install.sh --force-step=env     # перезапустить только один шаг
```

**Доступные шаги для `--force-step`:**

| Шаг | Что делает |
|-----|------------|
| `packages` | apt update + системные зависимости |
| `docker` | Docker Engine + Compose |
| `env` | мастер настройки, запись `.env` |
| `firewall` | правила ufw |
| `launch` | сборка образов и запуск |

**Что делает автоматически:**
- Определяет публичный IP сервера
- Генерирует случайные `API_KEY` и `REDIS_PASSWORD`
- Устанавливает Docker через `get.docker.com`, при ошибке — вручную через apt-репозиторий Docker
- Обнаруживает `docker compose` (v2 плагин) или `docker-compose` (v1 standalone), при отсутствии — устанавливает
- apt-операции с 3 попытками, fallback на DNS 8.8.8.8 и `--fix-missing`
- Читает Cloudflare Origin Certificate построчно и сохраняет в `.env`
- Создаёт `.env` с правами `600`
- Проверяет работоспособность API после запуска

---

## 1. MTProto прокси

Личный MTProto прокси с **Fake-TLS** (трафик выглядит как HTTPS) и опциональной **рекламой канала**.

**Два инстанса** работают параллельно:
- `mtproxy` (порт `PROXY_PORT`, по умолчанию `2083`) — с рекламным тегом `AD_TAG`
- `mtproxy-noad` (порт `PROXY_PORT_NOAD`, по умолчанию `2084`) — без рекламы

**Контроль доступа** работает через уникальные секреты: каждому разрешённому пользователю выдаётся персональная ссылка. При отзыве доступа секрет удаляется, прокси перезапускается — пользователь теряет доступ немедленно.

```
tg://proxy?server=<IP>&port=2083&secret=dd<user_secret>   # с рекламой
tg://proxy?server=<IP>&port=2084&secret=dd<user_secret>   # без рекламы
# или для Fake-TLS (ee):
tg://proxy?server=<IP>&port=2083&secret=ee<user_secret><domain_hex>
```

**Реклама канала (AD_TAG)** — пользователи инстанса с рекламой видят спонсорские посты твоего канала:
1. [@MTProxybot](https://t.me/MTProxybot) → `/newchannel`
2. Добавь бота администратором канала
3. Скопируй hex-тег → вставь в `.env` как `AD_TAG`

---

## 2. Telegram API прокси

Nginx проксирует все запросы к домену напрямую на `api.telegram.org`. Домен работает как полноценная замена — боты могут использовать его вместо стандартного API-адреса.

```bash
# Вместо api.telegram.org — твой домен:
curl -X POST "https://<твой_домен>/bot<TOKEN>/sendMessage" \
  -d '{"chat_id": 123, "text": "hello"}'
```

Вебхук Telegram тоже можно зарегистрировать через этот домен:
```bash
curl "https://api.telegram.org/bot<TOKEN>/setWebhook" \
  -d "url=https://<твой_домен>/bot<TOKEN>/webhook"
```

---

## 3. Webhook Bridge

Nginx принимает HTTPS от Cloudflare и проксирует запросы динамически — цель извлекается прямо из URL, никакой конфигурации под каждый бот не нужно.

**Формат:**
```
https://<твой_домен>/webhook-proxy/<host>/<path>?<query>
                                        ↓
                            https://<host>/<path>?<query>
```

**Пример** — зарегистрировать вебхук Telegram-бота через этот прокси:
```
https://yourdomain.com/webhook-proxy/bot.mysite.ru/bot/handler.php?token=abc
→  https://bot.mysite.ru/bot/handler.php?token=abc
```

**SSL** — Cloudflare Origin Certificate вставляется в `.env`, файлы сертификатов не нужны.

**В Cloudflare:** SSL/TLS → **Full** (не Flexible).

---

## 4. HTTP API

REST API для управления доступами к MTProto прокси. Авторизация: заголовок `X-Api-Key`.

| Метод | Путь | Действие |
|-------|------|----------|
| `POST` | `/api/v1/access` | Выдать доступ `{"user_id": "123"}` или `{"user_id": "123", "no_ad": true}` |
| `PATCH` | `/api/v1/access/{user_id}` | Сменить тир `{"no_ad": true/false}` (новый secret) |
| `DELETE` | `/api/v1/access/{user_id}` | Отозвать доступ (из любого тира) |
| `GET` | `/api/v1/access/{user_id}/link` | Получить ссылку пользователя |
| `GET` | `/api/v1/access` | Список всех пользователей (оба тира) |
| `GET` | `/health` | Healthcheck (без авторизации) |

Поле `no_ad=true` в `POST /api/v1/access` добавляет пользователя на инстанс без рекламы.

**Swagger UI:** `http://<IP>:8080/docs`

Примеры запросов — см. [API.md](./API.md).

---

## 5. Telegram бот (опционально)

Если задан `BOT_TOKEN` — запускается вместе с API в одном контейнере.

**Команды администратора** (пользователи из `ADMIN_IDS`):

| Команда | Действие |
|---------|----------|
| `/allow <name>` | Выдать доступ (инстанс с рекламой), уведомить пользователя |
| `/allownotad <name>` | Выдать доступ без рекламы, уведомить пользователя |
| `/movetoad <name>` | Переместить на инстанс с рекламой (новый secret) |
| `/movenotad <name>` | Переместить на инстанс без рекламы (новый secret) |
| `/revoke <name>` | Отозвать доступ (из любого инстанса), уведомить |
| `/getlink <name>` | Получить ссылку для любого пользователя |
| `/list` | Список всех пользователей с текущими активными подключениями |
| `/reload` | Принудительно пересобрать конфиг прокси |

**Команды пользователя:**

| Команда | Действие |
|---------|----------|
| `/start` | Получить свою ссылку (если есть доступ) |
| `/mylink` | Показать ссылку повторно |
| `/mylink <name>` | Ссылка по кастомному имени (если доступ выдан не по Telegram ID) |

> Узнать свой `user_id`: [@userinfobot](https://t.me/userinfobot)

---

## Конфигурация `.env`

| Переменная | Обязательно | По умолчанию | Описание |
|------------|:-----------:|:------------:|----------|
| `PROXY_HOST` | ✓ | — | Публичный IP или домен VPS |
| `PROXY_PORT` | | `2083` | Порт MTProto прокси (с рекламой) |
| `PROXY_PORT_NOAD` | | `2084` | Порт MTProto прокси без рекламы |
| `PROXY_SECRET_MODE` | | `dd` | Режим ссылки: `dd` (рекомендуется), `ee` (Fake-TLS) |
| `TLS_DOMAIN` | | `www.google.com` | Домен для Fake-TLS маскировки |
| `AD_TAG` | | — | Hex-тег рекламного канала от @MTProxybot |
| `REDIS_PASSWORD` | ✓ | — | Пароль Redis |
| `API_KEY` | ✓ | — | Ключ для HTTP API (`X-Api-Key`) |
| `API_PORT` | | `8080` | Порт HTTP API |
| `CF_ORIGIN_CERT` | ✓ | — | Cloudflare Origin Certificate (PEM) |
| `CF_ORIGIN_KEY` | ✓ | — | Приватный ключ к сертификату |
| `BOT_TOKEN` | | — | Токен Telegram бота (если нужен бот) |
| `ADMIN_IDS` | | — | Telegram user_id администраторов через запятую |

---

## Структура проекта

```
.
├── install.sh               ← мастер установки (запускать первым)
├── docker-compose.yml
├── .env.example
├── API.md                   ← документация HTTP API с примерами curl
│
├── mtproxy/                 ← MTProto прокси (github.com/alexbers/mtprotoproxy)
│   ├── Dockerfile           # используется для обоих инстансов: mtproxy и mtproxy-noad
│   └── entrypoint.sh        # ждёт config.py и запускает прокси
│
├── access-bot/              ← HTTP API + опциональный Telegram бот
│   ├── main.py              # запускает FastAPI и бот параллельно
│   ├── manager.py           # логика: Redis, секреты, конфиг, перезапуск, метрики
│   ├── api.py               # FastAPI роуты
│   ├── bot.py               # aiogram 3 хендлеры
│   └── Dockerfile
│
└── nginx/                   ← Telegram API прокси + Webhook Bridge
    ├── conf.d/
    │   └── webhook-proxy.conf
    ├── entrypoint.sh        # записывает Origin Cert из env в файлы
    └── Dockerfile
```

---

## Обслуживание

```bash
# Статус контейнеров
docker compose ps

# Логи
docker compose logs -f
docker compose logs -f access-bot
docker compose logs -f mtproxy

# Перезапуск
docker compose restart

# Обновление (пересобрать образы)
git pull && docker compose up -d --build

# Перенастроить .env (не трогая остальные шаги)
./install.sh --force-step=env

# Пересобрать и перезапустить без переустановки пакетов
./install.sh --force-step=launch
```
