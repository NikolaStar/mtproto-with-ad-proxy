"""Telegram bot handlers (aiogram 3). Manager is injected via set_manager()."""

import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

log = logging.getLogger(__name__)

ADMIN_IDS = set(int(i) for i in os.environ["ADMIN_IDS"].split(","))

bot = Bot(token=os.environ["BOT_TOKEN"])  # only imported when BOT_TOKEN is set
dp = Dispatcher()

_manager = None


def set_manager(manager):
    global _manager
    _manager = manager


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


# ── user commands ─────────────────────────────────────────────────────────────

@dp.message(Command("start"))
async def cmd_start(message: Message):
    uid = str(message.from_user.id)

    # Администраторам доступ выдаётся автоматически при первом /start
    if _is_admin(message.from_user.id):
        _, secret = await _manager.allow(uid)
        link = _manager.build_link(secret)
        await message.answer(
            f"✅ Твоя ссылка на прокси:\n{link}\n\n"
            "Нажми — Telegram предложит подключиться автоматически.",
            parse_mode="HTML",
        )
        return

    # Попытка найти доступ по Telegram user_id
    link = await _manager.get_link(uid)
    if link:
        await message.answer(
            f"✅ Твоя ссылка на прокси:\n{link}\n\n"
            "Нажми — Telegram предложит подключиться автоматически.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            "⛔ Доступ по твоему Telegram ID не найден.\n\n"
            "Если администратор выдал доступ по имени — используй:\n"
            "<code>/mylink &lt;твоё_имя&gt;</code>",
            parse_mode="HTML",
        )


@dp.message(Command("mylink"))
async def cmd_mylink(message: Message, command: CommandObject):
    # /mylink         — ищет по Telegram user_id
    # /mylink <name>  — ищет по кастомному имени
    name = (command.args or "").strip() or str(message.from_user.id)
    link = await _manager.get_link(name)
    if link:
        await message.answer(
            f"🔗 Ссылка для <code>{name}</code>:\n{link}",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⛔ Доступ для <code>{name}</code> не найден.",
            parse_mode="HTML",
        )


# ── admin commands ────────────────────────────────────────────────────────────

async def _do_allow(message: Message, name: str, no_ad: bool):
    created, secret = await _manager.allow(name, no_ad=no_ad)
    # Resolve actual tier in case user already existed in the other one
    info = await _manager.get_secret(name)
    actual_secret, actual_no_ad = info
    link = _manager.build_link(actual_secret, actual_no_ad)
    tier_label = "без рекламы" if actual_no_ad else "с рекламой"
    status_str = "✅ Выдан" if created else "ℹ️ Уже существует"
    await message.answer(
        f"{status_str} доступ ({tier_label}) для <code>{name}</code>\n\nСсылка:\n{link}",
        parse_mode="HTML",
    )
    if created and name.lstrip("-").isdigit():
        try:
            await bot.send_message(
                int(name),
                "🎉 Тебе выдали доступ к прокси!\n"
                "Напиши /start чтобы получить ссылку.",
            )
        except Exception:
            pass


@dp.message(Command("allow"))
async def cmd_allow(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "Использование:\n"
            "/allow <code>vasya</code> — по кастомному имени\n"
            "/allow <code>123456789</code> — по Telegram user_id",
            parse_mode="HTML",
        )
        return

    await _do_allow(message, name, no_ad=False)


@dp.message(Command("allownotad"))
async def cmd_allownotad(message: Message, command: CommandObject):
    """Выдать доступ на инстанс без рекламы."""
    if not _is_admin(message.from_user.id):
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "Использование:\n"
            "/allownotad <code>vasya</code> — выдать доступ без рекламы",
            parse_mode="HTML",
        )
        return

    await _do_allow(message, name, no_ad=True)


async def _do_move(message: Message, name: str, no_ad: bool):
    moved, link = await _manager.move(name, no_ad=no_ad)
    tier_label = "без рекламы" if no_ad else "с рекламой"
    if moved:
        await message.answer(
            f"🔄 <code>{name}</code> перемещён на инстанс {tier_label}\n\nНовая ссылка:\n{link}",
            parse_mode="HTML",
        )
        if name.lstrip("-").isdigit():
            try:
                await bot.send_message(
                    int(name),
                    f"🔄 Твой прокси обновлён. Напиши /start чтобы получить новую ссылку.",
                )
            except Exception:
                pass
    else:
        await message.answer(
            f"ℹ️ <code>{name}</code> уже на инстансе {tier_label} или не найден.",
            parse_mode="HTML",
        )


@dp.message(Command("movetoad"))
async def cmd_movetoad(message: Message, command: CommandObject):
    """Переместить пользователя на инстанс с рекламой."""
    if not _is_admin(message.from_user.id):
        return
    name = (command.args or "").strip()
    if not name:
        await message.answer("Использование: /movetoad <code>vasya</code>", parse_mode="HTML")
        return
    await _do_move(message, name, no_ad=False)


@dp.message(Command("movenotad"))
async def cmd_movenotad(message: Message, command: CommandObject):
    """Переместить пользователя на инстанс без рекламы."""
    if not _is_admin(message.from_user.id):
        return
    name = (command.args or "").strip()
    if not name:
        await message.answer("Использование: /movenotad <code>vasya</code>", parse_mode="HTML")
        return
    await _do_move(message, name, no_ad=True)


@dp.message(Command("revoke"))
async def cmd_revoke(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "Использование: /revoke <code>vasya</code> или /revoke <code>123456789</code>",
            parse_mode="HTML",
        )
        return

    found = await _manager.revoke(name)
    if found:
        await message.answer(f"🚫 Доступ <code>{name}</code> отозван.", parse_mode="HTML")
        if name.lstrip("-").isdigit():
            try:
                await bot.send_message(int(name), "⛔ Твой доступ к прокси отозван.")
            except Exception:
                pass
    else:
        await message.answer(f"ℹ️ <code>{name}</code> не найден.", parse_mode="HTML")


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if not _is_admin(message.from_user.id):
        return

    users = await _manager.list_users()
    if not users:
        await message.answer("Список доступов пуст.")
        return

    conns = {
        False: _manager.fetch_active_conns(False),
        True:  _manager.fetch_active_conns(True),
    }

    lines = [f"👥 <b>Доступов: {len(users)}</b>\n"]
    for name, (secret, no_ad) in users.items():
        curr = conns[no_ad].get(name, 0)
        tier = "б/р" if no_ad else "реклама"
        conn_str = f" — <b>{curr}</b> подкл." if curr > 0 else ""
        lines.append(f"• <code>{name}</code> [{tier}]{conn_str}")
    await message.answer("\n".join(lines), parse_mode="HTML")


@dp.message(Command("getlink"))
async def cmd_getlink(message: Message, command: CommandObject):
    """Получить ссылку для любого имени (только для админов)."""
    if not _is_admin(message.from_user.id):
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer("Использование: /getlink <code>vasya</code>", parse_mode="HTML")
        return

    link = await _manager.get_link(name)
    if link:
        await message.answer(
            f"🔗 Ссылка для <code>{name}</code>:\n{link}",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"⛔ Доступ для <code>{name}</code> не найден.", parse_mode="HTML")


@dp.message(Command("setlimit"))
async def cmd_setlimit(message: Message, command: CommandObject):
    """Установить лимит одновременных подключений для пользователя."""
    if not _is_admin(message.from_user.id):
        return

    args = (command.args or "").split()
    if not args:
        await message.answer(
            "Использование:\n"
            "/setlimit <code>vasya 5</code> — установить лимит 5\n"
            "/setlimit <code>vasya 0</code> — сбросить на дефолт",
            parse_mode="HTML",
        )
        return

    name = args[0]
    limit_arg = args[1] if len(args) > 1 else "0"

    if not limit_arg.isdigit():
        await message.answer("❌ Лимит должен быть числом >= 0 (0 = сбросить на дефолт).")
        return

    limit_val = int(limit_arg)
    if limit_val < 0:
        await message.answer("❌ Лимит должен быть >= 0.")
        return

    info = await _manager.get_secret(name)
    if not info:
        await message.answer(f"⛔ Пользователь <code>{name}</code> не найден.", parse_mode="HTML")
        return

    actual_limit = None if limit_val == 0 else limit_val
    await _manager.set_conn_limit(name, actual_limit)
    effective, is_custom = await _manager.get_conn_limit(name)

    if is_custom:
        await message.answer(
            f"✅ Лимит для <code>{name}</code> установлен: <b>{effective}</b> подключений.",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"🔄 Лимит для <code>{name}</code> сброшен на дефолт: <b>{effective}</b> подключений.",
            parse_mode="HTML",
        )


@dp.message(Command("getlimit"))
async def cmd_getlimit(message: Message, command: CommandObject):
    """Показать текущий лимит подключений для пользователя."""
    if not _is_admin(message.from_user.id):
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer(
            "Использование: /getlimit <code>vasya</code>",
            parse_mode="HTML",
        )
        return

    info = await _manager.get_secret(name)
    if not info:
        await message.answer(f"⛔ Пользователь <code>{name}</code> не найден.", parse_mode="HTML")
        return

    effective, is_custom = await _manager.get_conn_limit(name)
    source = "индивидуальный" if is_custom else f"дефолт (DEFAULT_CONN_LIMIT)"
    await message.answer(
        f"📊 Лимит для <code>{name}</code>: <b>{effective}</b> подключений ({source}).",
        parse_mode="HTML",
    )


@dp.message(Command("reload"))
async def cmd_reload(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await _manager._write_config_and_reload(False)
    await _manager._write_config_and_reload(True)
    await message.answer("🔄 Конфиг обновлён, оба прокси перезапущены.")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if _is_admin(message.from_user.id):
        text = (
            "<b>Управление доступами:</b>\n"
            "/allow <code>vasya</code> — выдать доступ с рекламой\n"
            "/allow <code>123456789</code> — выдать по Telegram ID\n"
            "/allownotad <code>vasya</code> — выдать доступ без рекламы\n"
            "/movetoad <code>vasya</code> — переместить на инстанс с рекламой\n"
            "/movenotad <code>vasya</code> — переместить на инстанс без рекламы\n"
            "/revoke <code>vasya</code> — отозвать\n"
            "/getlink <code>vasya</code> — получить ссылку по имени\n"
            "/list — список всех доступов\n"
            "/reload — пересобрать конфиг прокси\n\n"
            "<b>Лимиты подключений:</b>\n"
            "/setlimit <code>vasya 5</code> — установить лимит 5 подключений\n"
            "/setlimit <code>vasya 0</code> — сбросить на дефолт\n"
            "/getlimit <code>vasya</code> — показать текущий лимит\n\n"
            "<b>Для пользователей:</b>\n"
            "/start — получить ссылку (по Telegram ID)\n"
            "/mylink — ссылка по Telegram ID\n"
            "/mylink <code>vasya</code> — ссылка по имени"
        )
    else:
        text = (
            "/start — получить ссылку на прокси\n"
            "/mylink — показать свою ссылку\n"
            "/mylink <code>имя</code> — ссылка по имени (если выдан доступ не по ID)"
        )
    await message.answer(text, parse_mode="HTML")
