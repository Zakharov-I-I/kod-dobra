"""Фоновая рассылка: раз в 30 секунд проверяет, кому пора отправить задание или напоминание."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from aiogram import Bot

import core
import deliver
from config import Config
from db import DB

log = logging.getLogger(__name__)
TICK_SECONDS = 30
PAUSE_BETWEEN_MESSAGES = 0.05  # лимит Telegram — около 30 сообщений в секунду


async def tick(bot: Bot, db: DB, cfg: Config) -> int:
    now = datetime.now(cfg.tz)
    actions = core.due_actions(db, cfg, now)
    for kind, user, assignment in actions:
        try:
            if kind == "daily":
                await deliver.send_task(bot, db, user, now)
            else:
                await deliver.send_reminder(bot, db, user, assignment, now)
        except Exception:  # одна ошибка не должна останавливать рассылку остальным
            log.exception("failed to send %s to user %s", kind, user["id"])
        await asyncio.sleep(PAUSE_BETWEEN_MESSAGES)
    return len(actions)


async def run(bot: Bot, db: DB, cfg: Config) -> None:
    log.info("scheduler started (tz=%s)", cfg.tz)
    while True:
        try:
            await tick(bot, db, cfg)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("scheduler tick failed")
        await asyncio.sleep(TICK_SECONDS)
