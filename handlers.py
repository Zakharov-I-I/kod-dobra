"""Обработчики пользовательских команд и кнопок."""
from __future__ import annotations

from datetime import datetime

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import core
import deliver
import keyboards as kb
import logic
import texts
from config import Config
from db import DB

router = Router()


class Flow(StatesGroup):
    custom_time = State()


def now_local(cfg: Config) -> datetime:
    return datetime.now(cfg.tz)


def get_started_user(db: DB, tg_id: int):
    u = db.get_user(tg_id)
    return u if u is not None and u["onboarded"] else None


async def edit_or_answer(c: CallbackQuery, text: str, markup=None) -> None:
    try:
        await c.message.edit_text(text, reply_markup=markup)
    except TelegramBadRequest:  # сообщение слишком старое или текст не изменился
        await c.message.answer(text, reply_markup=markup)


# ---------- старт и первичная настройка ----------
@router.message(CommandStart())
async def cmd_start(m: Message, db: DB, cfg: Config, state: FSMContext):
    await state.clear()
    now = now_local(cfg)
    user = db.upsert_user(m.from_user.id, m.from_user.username, now)
    if user["onboarded"]:
        await deliver.send_task(m.bot, db, user, now, intro=texts.WELCOME_BACK)
        return
    await m.answer(texts.WELCOME, reply_markup=kb.segment_kb())


@router.callback_query(F.data.startswith("seg:"))
async def cb_segment(c: CallbackQuery, db: DB, cfg: Config):
    code = c.data.split(":", 1)[1]
    await c.answer()
    if code not in core.SEGMENTS:
        return
    db.upsert_user(c.from_user.id, c.from_user.username, now_local(cfg))
    db.update_user(c.from_user.id, segment=code)
    await edit_or_answer(c, texts.ASK_TIME, kb.time_kb("obt"))


async def finish_onboarding(bot, db: DB, cfg: Config, tg_id: int, hm: str) -> None:
    db.update_user(tg_id, notify_time=hm, onboarded=1)
    user = db.get_user(tg_id)
    intro = (f"Готово! Буду присылать задание каждый день в <b>{hm}</b> (МСК). "
             "Первое — прямо сейчас 👇")
    await deliver.send_task(bot, db, user, now_local(cfg), intro=intro)


@router.callback_query(F.data.startswith("obt:"))
async def cb_onboarding_time(c: CallbackQuery, db: DB, cfg: Config, state: FSMContext):
    value = c.data.split(":", 1)[1]
    await c.answer()
    if db.get_user(c.from_user.id) is None:
        await c.message.answer(texts.NOT_STARTED)
        return
    if value == "custom":
        await state.set_state(Flow.custom_time)
        await state.update_data(onboarding=True)
        await c.message.answer(texts.ASK_CUSTOM_TIME)
        return
    hm = logic.parse_time(value)
    if hm is None:
        return
    await deliver.drop_keyboard(c.message)
    await finish_onboarding(c.bot, db, cfg, c.from_user.id, hm)


@router.message(Flow.custom_time, F.text)
async def msg_custom_time(m: Message, db: DB, cfg: Config, state: FSMContext):
    hm = logic.parse_time(m.text)
    if hm is None:
        await m.answer(texts.BAD_TIME)
        return
    data = await state.get_data()
    await state.clear()
    if db.get_user(m.from_user.id) is None:
        await m.answer(texts.NOT_STARTED)
        return
    if data.get("onboarding"):
        await finish_onboarding(m.bot, db, cfg, m.from_user.id, hm)
    else:
        db.update_user(m.from_user.id, notify_time=hm)
        await m.answer(f"Хорошо, теперь задание приходит в <b>{hm}</b> (МСК) ⏰")


# ---------- основные команды ----------
@router.message(Command("today"))
async def cmd_today(m: Message, db: DB, cfg: Config):
    user = get_started_user(db, m.from_user.id)
    if user is None:
        await m.answer(texts.NOT_STARTED)
        return
    await deliver.send_task(m.bot, db, user, now_local(cfg))


@router.message(Command("done"))
async def cmd_done(m: Message, db: DB, cfg: Config):
    user = get_started_user(db, m.from_user.id)
    if user is None:
        await m.answer(texts.NOT_STARTED)
        return
    res = core.done_today(db, user, now_local(cfg))
    if res["status"] == "ok":
        await m.answer(texts.done_message(res))
    elif res["status"] == "already_done":
        await m.answer("Это дело уже отмечено ✅ Новое будет завтра.")
    else:
        await m.answer("На сегодня заданий ещё нет — нажми /today.")


@router.message(Command("stats"))
async def cmd_stats(m: Message, db: DB, cfg: Config):
    user = get_started_user(db, m.from_user.id)
    if user is None:
        await m.answer(texts.NOT_STARTED)
        return
    await m.answer(texts.stats_message(core.build_stats(db, user, now_local(cfg))))


@router.message(Command("help"))
async def cmd_help(m: Message):
    await m.answer(texts.DEFAULT_HELP)


@router.message(Command("privacy"))
async def cmd_privacy(m: Message):
    await m.answer(texts.PRIVACY)


@router.message(Command("time"))
async def cmd_time(m: Message, db: DB):
    if get_started_user(db, m.from_user.id) is None:
        await m.answer(texts.NOT_STARTED)
        return
    await m.answer("Во сколько присылать задание?", reply_markup=kb.time_kb("sett"))


# ---------- кнопки задания ----------
@router.callback_query(F.data.startswith("done:"))
async def cb_done(c: CallbackQuery, db: DB, cfg: Config):
    user = get_started_user(db, c.from_user.id)
    await c.answer()
    if user is None:
        return
    res = core.complete_assignment(db, user, int(c.data.split(":")[1]), now_local(cfg))
    if res["status"] == "ok":
        await deliver.drop_keyboard(c.message)
        await c.message.answer(texts.done_message(res))
    elif res["status"] == "already_done":
        await deliver.drop_keyboard(c.message)
        await c.message.answer("Это дело уже отмечено ✅")
    elif res["status"] == "expired":
        await deliver.drop_keyboard(c.message)
        await c.message.answer(texts.EXPIRED)


@router.callback_query(F.data.startswith("swap:"))
async def cb_swap(c: CallbackQuery, db: DB, cfg: Config):
    user = get_started_user(db, c.from_user.id)
    if user is None:
        await c.answer()
        return
    now = now_local(cfg)
    res = core.swap_assignment(db, user, int(c.data.split(":")[1]), now)
    if res["status"] == "ok":
        await c.answer("Заменил ✨")
        v = res["view"]
        info = core.streak_info(db, user, now.date())
        await edit_or_answer(c, texts.task_message(v, info), kb.task_kb(v["id"], v["status"], v["swaps"]))
    elif res["status"] == "limit":
        await c.answer("Заменить можно один раз в день 🙂", show_alert=True)
    else:
        await c.answer("Это задание уже нельзя заменить.", show_alert=True)


@router.callback_query(F.data.startswith("skip:"))
async def cb_skip(c: CallbackQuery, db: DB, cfg: Config):
    user = get_started_user(db, c.from_user.id)
    await c.answer()
    if user is None:
        return
    res = core.skip_assignment(db, user, int(c.data.split(":")[1]), now_local(cfg))
    if res["status"] == "ok":
        await deliver.drop_keyboard(c.message)
        await c.message.answer(texts.SKIPPED)


# ---------- настройки ----------
def _cat_names(db: DB) -> dict:
    return {r["id"]: r["name"] for r in db.categories()}


async def show_settings(c: CallbackQuery, db: DB) -> None:
    user = db.get_user(c.from_user.id)
    await edit_or_answer(c, texts.settings_message(user, _cat_names(db)), kb.settings_kb(bool(user["paused"])))


@router.message(Command("settings"))
async def cmd_settings(m: Message, db: DB):
    user = get_started_user(db, m.from_user.id)
    if user is None:
        await m.answer(texts.NOT_STARTED)
        return
    await m.answer(texts.settings_message(user, _cat_names(db)), reply_markup=kb.settings_kb(bool(user["paused"])))


@router.callback_query(F.data.startswith("set:"))
async def cb_settings(c: CallbackQuery, db: DB):
    user = get_started_user(db, c.from_user.id)
    await c.answer()
    if user is None:
        return
    action = c.data.split(":", 1)[1]
    if action == "time":
        await edit_or_answer(c, "Во сколько присылать задание?", kb.time_kb("sett"))
    elif action == "cats":
        await edit_or_answer(c, "Какие виды помощи включить? Должна остаться хотя бы одна.",
                             kb.cats_kb(db.categories(), set(core.user_cats(user))))
    elif action == "dur":
        await edit_or_answer(c, "Сколько времени максимум готов(а) тратить?", kb.duration_kb(user["max_minutes"]))
    elif action == "pause":
        db.update_user(c.from_user.id, paused=0 if user["paused"] else 1)
        await show_settings(c, db)
    elif action == "back":
        await show_settings(c, db)


@router.callback_query(F.data.startswith("sett:"))
async def cb_settings_time(c: CallbackQuery, db: DB, state: FSMContext):
    user = get_started_user(db, c.from_user.id)
    await c.answer()
    if user is None:
        return
    value = c.data.split(":", 1)[1]
    if value == "custom":
        await state.set_state(Flow.custom_time)
        await state.update_data(onboarding=False)
        await c.message.answer(texts.ASK_CUSTOM_TIME)
        return
    hm = logic.parse_time(value)
    if hm:
        db.update_user(c.from_user.id, notify_time=hm)
        await show_settings(c, db)


@router.callback_query(F.data.startswith("cat:"))
async def cb_category(c: CallbackQuery, db: DB):
    user = get_started_user(db, c.from_user.id)
    if user is None:
        await c.answer()
        return
    cid = int(c.data.split(":")[1])
    enabled = set(core.user_cats(user))
    if cid in enabled:
        if len(enabled) == 1:
            await c.answer("Нужна хотя бы одна категория", show_alert=True)
            return
        enabled.discard(cid)
    else:
        enabled.add(cid)
    db.update_user(c.from_user.id, cats=",".join(str(x) for x in sorted(enabled)))
    await c.answer()
    await edit_or_answer(c, "Какие виды помощи включить? Должна остаться хотя бы одна.",
                         kb.cats_kb(db.categories(), enabled))


@router.callback_query(F.data.startswith("dur:"))
async def cb_duration(c: CallbackQuery, db: DB):
    user = get_started_user(db, c.from_user.id)
    await c.answer()
    if user is None:
        return
    n = int(c.data.split(":")[1])
    if n in core.DURATIONS:
        db.update_user(c.from_user.id, max_minutes=n)
        await show_settings(c, db)


# ---------- удаление данных ----------
@router.message(Command("deleteme"))
async def cmd_deleteme(m: Message, db: DB):
    if db.get_user(m.from_user.id) is None:
        await m.answer("Я ничего о тебе не храню 🙂")
        return
    await m.answer(texts.CONFIRM_DELETE, reply_markup=kb.confirm_delete_kb())


@router.callback_query(F.data.startswith("del:"))
async def cb_delete(c: CallbackQuery, db: DB, state: FSMContext):
    await c.answer()
    if c.data.endswith("yes"):
        db.delete_user(c.from_user.id)
        await state.clear()
        await edit_or_answer(c, texts.DELETED)
    else:
        await edit_or_answer(c, texts.CANCELLED)
