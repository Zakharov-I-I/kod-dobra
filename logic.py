"""Чистая логика без базы и Telegram: серии дней, достижения, разбор времени."""
from __future__ import annotations

import re
from datetime import date

# Сколько пропущенных дней подряд серия «переживает». 1 = один пропуск не обнуляет серию,
# два дня подряд без дел — обнуляет (обоснование: Lally et al., 2010 — один пропуск не мешает привычке).
GRACE_DAYS = 1

ACHIEVEMENTS = [
    # (код, название, описание, условие)
    ("first_step", "Первый шаг", "первое выполненное дело", lambda s: s["total"] >= 1),
    ("streak3", "Три дня подряд", "серия из 3 дней", lambda s: s["current"] >= 3),
    ("streak7", "Неделя добра", "серия из 7 дней", lambda s: s["current"] >= 7),
    ("streak14", "Две недели добра", "серия из 14 дней", lambda s: s["current"] >= 14),
    ("total10", "Десять дел", "10 выполненных дел", lambda s: s["total"] >= 10),
    ("total30", "Тридцать дел", "30 выполненных дел", lambda s: s["total"] >= 30),
    ("all_cats", "Всесторонний помощник", "дела во всех пяти категориях",
     lambda s: s["cats_done"] >= s["cats_total"] > 0),
]


def compute_streaks(done_dates, today: date):
    """Возвращает (текущая серия, лучшая серия) в днях с выполненными делами.

    Один пропущенный день серию не прерывает (GRACE_DAYS), два подряд — прерывают.
    Текущая серия считается живой, если последнее выполненное дело было не более
    чем GRACE_DAYS + 1 день назад.
    """
    days = sorted(set(done_dates))
    if not days:
        return 0, 0
    best = run = 1
    for prev, cur in zip(days, days[1:]):
        if (cur - prev).days <= GRACE_DAYS + 1:
            run += 1
        else:
            run = 1
        best = max(best, run)
    current = run if (today - days[-1]).days <= GRACE_DAYS + 1 else 0
    return current, best


def new_achievements(stats: dict, owned: set) -> list:
    """Коды достижений, которые стали доступны, но ещё не выданы."""
    return [(code, title, desc) for code, title, desc, cond in ACHIEVEMENTS
            if code not in owned and cond(stats)]


_TIME_RE = re.compile(r"^\s*([01]?\d|2[0-3])\s*[:.\-]\s*([0-5]\d)\s*$")


def parse_time(text: str):
    """'9:30', '09.30', '21-05' -> '09:30'; неверный формат -> None."""
    m = _TIME_RE.match(text or "")
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def hm_to_minutes(hm: str) -> int:
    h, m = hm.split(":")
    return int(h) * 60 + int(m)
