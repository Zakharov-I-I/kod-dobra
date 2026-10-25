"""Команды администратора (только для ID из ADMIN_IDS)."""
from __future__ import annotations

import asyncio
from datetime import datetime

from aiogram import Router
from aiogram.filters import BaseFilter, Command, CommandObject
from aiogram.types import BufferedInputFile, Message

import core
import deliver
import texts
from config import Config
from db import DB

router = Router()


class IsAdmin(BaseFilter):
    async def __call__(self, message: Message, cfg: Config) -> bool:
        return message.from_user is not None and message.from_user.id in cfg.admin_ids


router.message.filter(IsAdmin())


@router.message(Command("admin"))
async def cmd_admin(m: Message, db: DB, cfg: Config):
    await m.answer(texts.admin_message(core.admin_report(db, datetime.now(cfg.tz))))


@router.message(Command("export"))
async def cmd_export(m: Message, db: DB):
    data = ("﻿" + core.export_csv(db)).encode("utf-8")  # BOM, чтобы Excel открыл кириллицу
    await m.answer_document(BufferedInputFile(data, filename="dobroden_export.csv"),
                            caption="Выгрузка: одна строка = одно выданное задание (без Telegram-ID).")


@router.message(Command("broadcast"))
async def cmd_broadcast(m: Message, command: CommandObject, db: DB):
    text = (command.args or "").strip()
    if not text:
        await m.answer("Использование: /broadcast текст сообщения")
        return
    sent = 0
    for user in db.broadcast_users():
        if await deliver.safe_send(m.bot, db, user, text):
            sent += 1
        await asyncio.sleep(0.05)
    await m.answer(f"Отправлено: {sent}")


@router.message(Command("addtask"))
async def cmd_addtask(m: Message, command: CommandObject, db: DB):
    """/addtask 2 | 15 | Текст задания   (категория 1–5 | минут 5–30 | текст)"""
    usage = ("Использование: /addtask категория | минут | текст\n"
             "Категории: " + "; ".join(f"{c['id']} — {c['name']}" for c in db.categories()))
    parts = [p.strip() for p in (command.args or "").split("|", 2)]
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit() or len(parts[2]) < 5:
        await m.answer(usage)
        return
    cat, minutes, text = int(parts[0]), int(parts[1]), parts[2]
    if cat not in {c["id"] for c in db.categories()} or not 5 <= minutes <= 30:
        await m.answer(usage)
        return
    ok = db.add_task(cat, text, minutes)
    await m.answer("Задание добавлено ✅" if ok else "Такое задание уже есть.")
