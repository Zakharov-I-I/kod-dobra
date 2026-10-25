"""Инлайн-клавиатуры."""
from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import core

TIMES = ["07:00", "08:00", "09:00", "12:00", "18:00", "20:00"]


def segment_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for code, name in core.SEGMENTS.items():
        b.button(text=name, callback_data=f"seg:{code}")
    b.adjust(1)
    return b.as_markup()


def time_kb(prefix: str) -> InlineKeyboardMarkup:
    """prefix: 'obt' (первичная настройка) или 'sett' (настройки)."""
    b = InlineKeyboardBuilder()
    for t in TIMES:
        b.button(text=t, callback_data=f"{prefix}:{t}")
    b.button(text="Другое…", callback_data=f"{prefix}:custom")
    b.adjust(3)
    return b.as_markup()


def task_kb(aid: int, status: str, swaps: int) -> InlineKeyboardMarkup | None:
    if status == "done":
        return None
    b = InlineKeyboardBuilder()
    b.button(text="✅ Выполнено", callback_data=f"done:{aid}")
    row = 1
    if swaps < 1:
        b.button(text="🔄 Другое задание", callback_data=f"swap:{aid}")
        row += 1
    if status != "skipped":
        b.button(text="⏭ Пропустить", callback_data=f"skip:{aid}")
        row += 1
    b.adjust(1, row - 1) if row > 1 else b.adjust(1)
    return b.as_markup()


def settings_kb(paused: bool) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="⏰ Время", callback_data="set:time")
    b.button(text="🗂 Категории", callback_data="set:cats")
    b.button(text="⏱ Длительность", callback_data="set:dur")
    b.button(text="▶️ Продолжить" if paused else "⏸ Пауза", callback_data="set:pause")
    b.adjust(2)
    return b.as_markup()


def cats_kb(categories, enabled: set) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in categories:
        mark = "✅" if c["id"] in enabled else "⬜"
        b.button(text=f"{mark} {c['name']}", callback_data=f"cat:{c['id']}")
    b.button(text="« Назад", callback_data="set:back")
    b.adjust(1)
    return b.as_markup()


def duration_kb(current: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for n in core.DURATIONS:
        b.button(text=("✅ " if n == current else "") + f"до {n} мин", callback_data=f"dur:{n}")
    b.button(text="« Назад", callback_data="set:back")
    b.adjust(2, 1)
    return b.as_markup()


def confirm_delete_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Да, удалить", callback_data="del:yes")
    b.button(text="Отмена", callback_data="del:no")
    b.adjust(2)
    return b.as_markup()
