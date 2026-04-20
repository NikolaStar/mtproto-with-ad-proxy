# MTProto Proxy + Webhook Bridge

Самодостаточный Docker-стек на VPS с тремя функциями:

1. **MTProto прокси** — личный Telegram-прокси с рекламой канала и контролем доступа по `user_id`
2. **Webhook Bridge** — двусторонний HTTP прокси-посредник между Telegram и твоими ботами
3. **HTTP API + Telegram бот** — управление доступами к MTProto прокси

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
Telegram clients ───────┤──► mtproxy :2083   (MTProto proxy)       │
                        │                                          │
                        │       ┌── nginx :443 ──────────────┐    │
Cloudflare (Full SSL) ──┼──────►│                            │    │
                        │       │  /webhook-proxy/*          │    │
Telegram webhooks ──────┼──────►│    ↓ читает цель из URL    │    │
                        │       │  https://<host>/<path>     │    │
                        │       └────────────────────────────┘    │
                        │                                          │
HTTP API clients ───────┤──► access-bot :8080  (FastAPI)          │
Telegram admin ─────────┤──► access-bot        (aiogram бот)      │
                        │                                          │
                        │       redis  (хранит user_id → secret)  │
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

Личный MTProto прокси с **Fake-TLS** (трафик выглядит как HTTPS) и **рекламой канала**.

**Контроль доступа** работает через уникальные секреты: каждому разрешённому пользователю выдаётся персональная ссылка. При отзыве доступа секрет удаляется, прокси перезапускается — пользователь теряет доступ немедленно.

```
tg://proxy?server=<IP>&port=2083&secret=ee<domain_hex><user_secret>
```

**Реклама канала (AD_TAG)** — пользователи прокси видят спонсорские посты твоего канала:
1. [@MTProxybot](https://t.me/MTProxybot) → `/newchannel`
2. Добавь бота администратором канала
3. Скопируй hex-тег → вставь в `.env` как `AD_TAG`

---

## 2. Webhook Bridge

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

## 3. HTTP API

REST API для управления доступами к MTProto прокси. Авторизация: заголовок `X-Api-Key`.

| Метод | Путь | Действие |
|-------|------|----------|
| `POST` | `/api/v1/access` | Выдать доступ `{"user_id": "123"}` → вернуть ссылку |
| `DELETE` | `/api/v1/access/{user_id}` | Отозвать доступ |
| `GET` | `/api/v1/access/{user_id}/link` | Получить ссылку пользователя |
| `GET` | `/api/v1/access` | Список всех пользователей |
| `GET` | `/health` | Healthcheck (без авторизации) |

**Swagger UI:** `http://<IP>:8080/docs`

Примеры запросов — см. [API.md](./API.md).

---

## 4. Telegram бот (опционально)

Если задан `BOT_TOKEN` — запускается вместе с API в одном контейнере.

**Команды администратора** (пользователи из `ADMIN_IDS`):

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
| `/mylink` | Показать ссылку повторно |

> Узнать свой `user_id`: [@userinfobot](https://t.me/userinfobot)

---

## Конфигурация `.env`

| Переменная | Обязательно | По умолчанию | Описание |
|------------|:-----------:|:------------:|----------|
| `PROXY_HOST` | ✓ | — | Публичный IP или домен VPS |
| `PROXY_PORT` | | `2083` | Порт MTProto прокси |
| `REDIS_PASSWORD` | ✓ | — | Пароль Redis |
| `API_KEY` | ✓ | — | Ключ для HTTP API (`X-Api-Key`) |
| `API_PORT` | | `8080` | Порт HTTP API |
| `CF_ORIGIN_CERT` | ✓ | — | Cloudflare Origin Certificate (PEM, `\n`-escaped) |
| `CF_ORIGIN_KEY` | ✓ | — | Приватный ключ к сертификату |
| `TLS_DOMAIN` | | `www.google.com` | Домен для Fake-TLS маскировки |
| `AD_TAG` | | — | Hex-тег рекламного канала от @MTProxybot |
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
├── mtproxy/                 ← MTProto прокси (python mtprotoproxy)
│   ├── Dockerfile
│   └── entrypoint.sh        # ждёт config.py и запускает прокси
│
├── access-bot/              ← HTTP API + опциональный Telegram бот
│   ├── main.py              # запускает FastAPI и бот параллельно
│   ├── manager.py           # логика: Redis, секреты, конфиг, перезапуск
│   ├── api.py               # FastAPI роуты
│   ├── bot.py               # aiogram 3 хендлеры
│   └── Dockerfile
│
└── nginx/                   ← Webhook bridge
    ├── conf.d/
    │   └── webhook-proxy.conf
    ├── entrypoint.sh        # записывает Origin Cert из env в файлы
    └── Dockerfile
```

---

## Обслуживание

```bash
# Статус контейнеров
sudo docker compose ps

# Логи
sudo docker compose logs -f
sudo docker compose logs -f access-bot
sudo docker compose logs -f mtproxy

# Перезапуск
sudo docker compose restart

# Обновление (пересобрать образы)
git pull && sudo docker compose up -d --build

# Перенастроить .env (не трогая остальные шаги)
./install.sh --force-step=env

# Пересобрать и перезапустить без переустановки пакетов
./install.sh --force-step=launch
```
