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

    link = await _manager.get_link(uid)
    if link:
        await message.answer(
            f"✅ Твоя ссылка на прокси:\n<code>{link}</code>\n\n"
            "Нажми — Telegram предложит подключиться автоматически.",
            parse_mode="HTML",
        )
    else:
        await message.answer("⛔ У тебя нет доступа. Обратись к администратору.")


@dp.message(Command("mylink"))
async def cmd_mylink(message: Message):
    link = await _manager.get_link(str(message.from_user.id))
    if link:
        await message.answer(f"🔗 <code>{link}</code>", parse_mode="HTML")
    else:
        await message.answer("⛔ У тебя нет доступа.")


# ── admin commands ────────────────────────────────────────────────────────────

@dp.message(Command("allow"))
async def cmd_allow(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return

    uid = (command.args or "").strip()
    if not uid.lstrip("-").isdigit():
        await message.answer("Использование: /allow <user_id>")
        return

    created, secret = await _manager.allow(uid)
    link = _manager.build_link(secret)
    status = "✅ Выдан" if created else "ℹ️ Уже был"
    await message.answer(
        f"{status} доступ для <code>{uid}</code>\n\nСсылка:\n<code>{link}</code>",
        parse_mode="HTML",
    )

    if created:
        try:
            await bot.send_message(int(uid), "🎉 Тебе выдали доступ к прокси! Напиши /start")
        except Exception:
            pass


@dp.message(Command("revoke"))
async def cmd_revoke(message: Message, command: CommandObject):
    if not _is_admin(message.from_user.id):
        return

    uid = (command.args or "").strip()
    if not uid.lstrip("-").isdigit():
        await message.answer("Использование: /revoke <user_id>")
        return

    found = await _manager.revoke(uid)
    if found:
        await message.answer(f"🚫 Доступ <code>{uid}</code> отозван.", parse_mode="HTML")
        try:
            await bot.send_message(int(uid), "⛔ Твой доступ к прокси отозван.")
        except Exception:
            pass
    else:
        await message.answer(f"ℹ️ Пользователь {uid} не найден.")


@dp.message(Command("list"))
async def cmd_list(message: Message):
    if not _is_admin(message.from_user.id):
        return

    users = await _manager.list_users()
    if not users:
        await message.answer("Список пуст.")
        return

    lines = [f"👥 <b>Пользователей: {len(users)}</b>\n"] + [f"• <code>{uid}</code>" for uid in users]
    await message.answer("\n".join(lines), parse_mode="HTML")


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
            "<b>Админ:</b>\n"
            "/allow &lt;user_id&gt; — выдать доступ\n"
            "/revoke &lt;user_id&gt; — отозвать\n"
            "/list — список пользователей\n"
            "/reload — пересобрать конфиг\n\n"
            "<b>Пользователь:</b>\n"
            "/start — получить ссылку\n"
            "/mylink — показать ссылку"
        )
    else:
        text = "/start — получить ссылку на прокси\n/mylink — показать свою ссылку"
    await message.answer(text, parse_mode="HTML")
