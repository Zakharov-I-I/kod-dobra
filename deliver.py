"""Отправка сообщений пользователям (общая для обработчиков и планировщика)."""
from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter

import core
import keyboards
import texts
from db import DB

log = logging.getLogger(__name__)


async def safe_send(bot: Bot, db: DB, user, text: str, **kwargs) -> bool:
    """Отправка с обработкой типичных ошибок. False — сообщение не доставлено."""
    import asyncio
    for _ in range(2):
        try:
            await bot.send_message(user["tg_id"], text, **kwargs)
            return True
        except TelegramForbiddenError:  # пользователь заблокировал бота
            db.update_user(user["tg_id"], active=0)
            log.info("user %s blocked the bot", user["id"])
            return False
        except TelegramRetryAfter as e:
            await asyncio.sleep(e.retry_after + 1)
        except TelegramBadRequest as e:
            log.warning("bad request for user %s: %s", user["id"], e)
            return False
    return False


async def send_task(bot: Bot, db: DB, user, now: datetime, intro: str | None = None) -> bool:
    view, _ = core.issue_task(db, user, now)
    if view is None:
        return await safe_send(bot, db, user, texts.NO_TASKS)
    info = core.streak_info(db, user, now.date())
    return await safe_send(bot, db, user, texts.task_message(view, info, intro),
                           reply_markup=keyboards.task_kb(view["id"], view["status"], view["swaps"]))


async def send_reminder(bot: Bot, db: DB, user, assignment, now: datetime) -> bool:
    view = db.assignment_view(assignment["id"])
    db.mark_reminded(assignment["id"])  # помечаем до отправки, чтобы не слать повторно при сбое
    return await safe_send(bot, db, user, texts.reminder_message(view),
                           reply_markup=keyboards.task_kb(view["id"], view["status"], view["swaps"]))


async def drop_keyboard(message) -> None:
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest:
        pass
