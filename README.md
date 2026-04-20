# MTProto Proxy + Access Bot

MTProto proxy с рекламой канала и контролем доступа по Telegram user_id.

## Как это работает

```
Пользователь → Bot /start → бот проверяет user_id → выдаёт персональную ссылку
                                                        ↓
                                                unique secret в mtprotoproxy config
                                                        ↓
Admin /revoke → удаляет secret → proxy перезапускается → пользователь теряет доступ
```

**Реклама:** через `AD_TAG` — пользователи прокси видят спонсорские посты твоего канала.

---

## Быстрый деплой на VPS

### 1. Установи Docker + Compose

```bash
curl -fsSL https://get.docker.com | sh
```

### 2. Склонируй репо

```bash
git clone <repo> /opt/mtproxy
cd /opt/mtproxy
```

### 3. Создай `.env`

```bash
cp .env.example .env
nano .env
```

Заполни:
- `BOT_TOKEN` — токен от [@BotFather](https://t.me/BotFather)
- `ADMIN_IDS` — свои Telegram user_id (узнать у [@userinfobot](https://t.me/userinfobot))
- `PROXY_HOST` — IP твоего VPS
- `AD_TAG` — тег рекламного канала (см. ниже)

### 4. Получи AD_TAG (реклама канала)

1. Открой [@MTProxybot](https://t.me/MTProxybot) в Telegram
2. Отправь `/newchannel`
3. Укажи свой канал (бот должен быть администратором канала)
4. Скопируй hex-тег → вставь в `.env` как `AD_TAG`

Если не нужна реклама — оставь `AD_TAG=` пустым.

### 5. Запусти

```bash
docker compose up -d
```

### 6. Открой порт на файрволе

```bash
# ufw
ufw allow 443/tcp

# iptables
iptables -A INPUT -p tcp --dport 443 -j ACCEPT
```

---

## Управление доступом

Все команды через Telegram бота:

| Команда | Описание |
|---------|----------|
| `/allow 123456789` | Выдать доступ пользователю |
| `/revoke 123456789` | Отозвать доступ |
| `/list` | Список всех разрешённых |
| `/reload` | Принудительно пересобрать конфиг |

Пользователь отправляет боту `/start` → получает свою персональную ссылку.

---

## Как получить user_id нового пользователя

Попроси пользователя написать [@userinfobot](https://t.me/userinfobot) — он ответит их ID.
Или попроси написать твоему боту, затем проверь логи:

```bash
docker logs access-bot --tail 50
```

---

## Структура проекта

```
.
├── docker-compose.yml
├── .env.example
├── mtproxy/
│   ├── Dockerfile          # python mtprotoproxy
│   └── entrypoint.sh       # ждёт config.py и запускает прокси
└── access-bot/
    ├── Dockerfile
    ├── bot.py              # aiogram 3 бот
    └── requirements.txt
```

---

## Обслуживание

```bash
# Логи прокси
docker logs mtproxy -f

# Логи бота
docker logs access-bot -f

# Перезапуск
docker compose restart

# Обновление
git pull && docker compose up -d --build
```

---

## Ограничения

- Контроль доступа работает через уникальные секреты (не на уровне протокола)
- При смене IP прокси нужно обновить `PROXY_HOST` в `.env` и разослать новые ссылки
- Один порт (443) — рекомендуется для обхода блокировок
