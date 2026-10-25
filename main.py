"""Точка входа: python main.py"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import admin
import handlers
import scheduler
from config import load_config
from db import DB

COMMANDS = [
    BotCommand(command="today", description="Задание на сегодня"),
    BotCommand(command="done", description="Отметить выполненным"),
    BotCommand(command="stats", description="Моя статистика"),
    BotCommand(command="settings", description="Настройки"),
    BotCommand(command="time", description="Сменить время"),
    BotCommand(command="help", description="Помощь"),
    BotCommand(command="privacy", description="Какие данные хранятся"),
    BotCommand(command="deleteme", description="Удалить мои данные"),
]


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config()
    db = DB(cfg.db_path)
    bot = Bot(cfg.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage(), db=db, cfg=cfg)
    dp.include_router(admin.router)     # админские команды раньше обычных
    dp.include_router(handlers.router)

    me = await bot.get_me()
    logging.info("Бот запущен: @%s, заданий в банке: %s, админов: %s", me.username, db.count_tasks(), len(cfg.admin_ids))
    await bot.set_my_commands(COMMANDS)
    await bot.delete_webhook(drop_pending_updates=False)

    task = asyncio.create_task(scheduler.run(bot, db, cfg))
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        task.cancel()
        await bot.session.close()
        db.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
