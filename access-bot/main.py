"""Entry point: runs FastAPI, optionally Telegram bot if BOT_TOKEN is set."""

import asyncio
import logging
import os

import uvicorn

import api
from manager import ProxyManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

API_PORT = int(os.environ.get("API_PORT", 8080))
REDIS_URL = os.environ["REDIS_URL"]
BOT_TOKEN = os.environ.get("BOT_TOKEN")


async def main():
    manager = ProxyManager(redis_url=REDIS_URL)
    await manager.init()
    await manager._write_config_and_reload(False)
    await manager._write_config_and_reload(True)

    api.set_manager(manager)

    uvicorn_config = uvicorn.Config(
        app=api.app,
        host="0.0.0.0",
        port=API_PORT,
        log_level="info",
        access_log=True,
    )
    server = uvicorn.Server(uvicorn_config)

    tasks = [server.serve()]

    if BOT_TOKEN:
        import bot
        bot.set_manager(manager)
        tasks.append(bot.dp.start_polling(bot.bot, allowed_updates=["message"]))
        log.info("Telegram bot enabled")
    else:
        log.info("BOT_TOKEN not set — Telegram bot disabled")

    log.info("API listening on :%d", API_PORT)
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    asyncio.run(main())
