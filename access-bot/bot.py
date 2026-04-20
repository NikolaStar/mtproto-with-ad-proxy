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
            f"✅ Твоя ссылка на прокси:\n<code>{link}</code>\n\n"
            "Нажми — Telegram предложит подключиться автоматически.",
            parse_mode="HTML",
        )
        return

    # Попытка найти доступ по Telegram user_id
    link = await _manager.get_link(uid)
    if link:
        await message.answer(
            f"✅ Твоя ссылка на прокси:\n<code>{link}</code>\n\n"
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
            f"🔗 Ссылка для <code>{name}</code>:\n<code>{link}</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer(
            f"⛔ Доступ для <code>{name}</code> не найден.",
            parse_mode="HTML",
        )


# ── admin commands ────────────────────────────────────────────────────────────

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

    created, secret = await _manager.allow(name)
    link = _manager.build_link(secret)
    status = "✅ Выдан" if created else "ℹ️ Уже существует"
    await message.answer(
        f"{status} доступ для <code>{name}</code>\n\nСсылка:\n<code>{link}</code>",
        parse_mode="HTML",
    )

    # Уведомить пользователя в Telegram, если name — числовой ID
    if created and name.lstrip("-").isdigit():
        try:
            await bot.send_message(
                int(name),
                "🎉 Тебе выдали доступ к прокси!\n"
                "Напиши /start чтобы получить ссылку.",
            )
        except Exception:
            pass


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

    lines = [f"👥 <b>Доступов: {len(users)}</b>\n"]
    for name in users:
        lines.append(f"• <code>{name}</code>")
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
            f"🔗 Ссылка для <code>{name}</code>:\n<code>{link}</code>",
            parse_mode="HTML",
        )
    else:
        await message.answer(f"⛔ Доступ для <code>{name}</code> не найден.", parse_mode="HTML")


@dp.message(Command("reload"))
async def cmd_reload(message: Message):
    if not _is_admin(message.from_user.id):
        return
    await _manager._write_config_and_reload()
    await message.answer("🔄 Конфиг обновлён, прокси перезапущен.")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if _is_admin(message.from_user.id):
        text = (
            "<b>Управление доступами:</b>\n"
            "/allow <code>vasya</code> — выдать доступ по имени\n"
            "/allow <code>123456789</code> — выдать по Telegram ID\n"
            "/revoke <code>vasya</code> — отозвать\n"
            "/getlink <code>vasya</code> — получить ссылку по имени\n"
            "/list — список всех доступов\n"
            "/reload — пересобрать конфиг прокси\n\n"
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
