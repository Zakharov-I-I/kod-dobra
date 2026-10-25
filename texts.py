"""Тексты сообщений бота (HTML-разметка Telegram)."""
from __future__ import annotations

import html
import random

import core

PRAISE = [
    "Отлично! Мир стал чуточку добрее 💛",
    "Спасибо, что сделал это — маленькие дела складываются в большие 🌱",
    "Круто! Ты молодец 👏",
    "Так держать! Доброе дело засчитано ✅",
    "Это правда важно, даже если кажется мелочью 🙌",
]

WELCOME = (
    "Привет! Я <b>ДоброДень</b> 🌱\n\n"
    "Каждый день я буду присылать одно простое доброе дело на 5–30 минут: позвонить бабушке, "
    "помочь соседу, убрать мусор во дворе. Ты выполняешь и отмечаешь это здесь. "
    "Я считаю твои дела и дни подряд.\n\n"
    "Это учебный проект студентов МАИ. Хранится только твой Telegram-ID и ответы в боте; "
    "удалить всё можно командой /deleteme.\n\n"
    "Сначала один вопрос: кто ты?"
)
ASK_TIME = "Когда присылать задание? Выбери время (по Москве) или нажми «Другое»."
ASK_CUSTOM_TIME = "Напиши время в формате ЧЧ:ММ, например <code>08:30</code>."
BAD_TIME = "Не получилось разобрать время. Напиши как <code>08:30</code> (от 00:00 до 23:59)."
NOT_STARTED = "Сначала нажми /start, чтобы я тебя знал 🙂"
NO_TASKS = "Пока нет подходящих заданий — включи больше категорий в /settings."
WELCOME_BACK = "С возвращением! Вот твоё задание на сегодня 👇"
DEFAULT_HELP = (
    "<b>Что я умею</b>\n"
    "/today — задание на сегодня\n"
    "/done — отметить задание выполненным\n"
    "/stats — твоя статистика и достижения\n"
    "/settings — время, категории, длительность, пауза\n"
    "/time — быстро сменить время напоминания\n"
    "/privacy — какие данные хранятся\n"
    "/deleteme — удалить все мои данные\n\n"
    "Одно пропущенное дело серию не обнуляет — два дня подряд без дел обнуляют. "
    "Заменить задание можно один раз в день."
)
PRIVACY = (
    "<b>Какие данные хранятся</b>\n"
    "Твой Telegram-ID и ник (если есть), выбранный сегмент, настройки, выданные задания и отметки о выполнении. "
    "Имя, телефон и переписка не сохраняются. Данные используются только в учебном проекте для подсчёта "
    "общей статистики. Удалить всё: /deleteme."
)
SKIPPED = "Ничего страшного — один пропуск серию не прерывает. Завтра будет новое задание 🌿"
EXPIRED = "Это задание уже давно, его нельзя отметить. Ждём тебя с новым ✨"
CONFIRM_DELETE = "Удалить все твои данные из бота безвозвратно?"
DELETED = "Готово, все твои данные удалены. Если захочешь вернуться — нажми /start."
CANCELLED = "Хорошо, ничего не удаляем."
PAUSED_ON = "Рассылка на паузе ⏸ Вернуть: /settings → «Продолжить»."
PAUSED_OFF = "Рассылка снова включена ▶️"


def _e(s) -> str:
    return html.escape(str(s))


def task_message(view, info: dict, intro: str | None = None) -> str:
    head = f"{intro}\n\n" if intro else ""
    status = ""
    if view["status"] == "done":
        status = "\n\n✅ <b>Уже выполнено</b>"
    elif view["status"] == "skipped":
        status = "\n\n⏭ Ты пропустил(а) это задание, но можешь выполнить его позже сегодня."
    streak = f"\n🔥 Серия: <b>{info['current']}</b> дн." if info["current"] else ""
    return (f"{head}🌱 <b>Доброе дело на сегодня</b>\n\n{_e(view['task_text'])}\n\n"
            f"Категория: {_e(view['category'])} · ⏱ ~{view['minutes']} мин{streak}{status}")


def reminder_message(view) -> str:
    return (f"Привет! Задание на сегодня ещё ждёт 🙂\n\n«{_e(view['task_text'])}»\n\n"
            "Если успел(а) — нажми «Выполнено». Не получилось — ничего страшного.")


def done_message(res: dict) -> str:
    parts = [random.choice(PRAISE), f"🔥 Серия: <b>{res['current']}</b> дн. (лучшая: {res['best']})",
             f"Всего добрых дел: <b>{res['total']}</b>"]
    for _, title, desc in res["new"]:
        parts.append(f"🏆 Новое достижение: <b>{_e(title)}</b> — {_e(desc)}")
    parts.append(f"Вместе все участники уже сделали <b>{res['community_total']}</b> добрых дел.")
    return "\n".join(parts)


def stats_message(st: dict) -> str:
    lines = ["📊 <b>Твоя статистика</b>", "",
             f"Добрых дел: <b>{st['total']}</b>",
             f"Серия дней: <b>{st['current']}</b> (лучшая: {st['best']})",
             f"Дней с ботом: {st['days_in_bot']}"]
    if st["by_cat"]:
        lines += ["", "<b>По категориям</b>"] + [f"• {_e(n)}: {c}" for n, c in st["by_cat"]]
    lines += ["", f"<b>Достижения</b> ({len(st['achievements'])}/{st['achievements_total']})"]
    lines += [f"🏆 {_e(t)} — {_e(d)}" for t, d in st["achievements"]] or ["Пока нет — всё впереди!"]
    lines += ["", f"Все участники вместе: {st['community_total']} дел от {st['community_people']} чел."]
    return "\n".join(lines)


def settings_message(user, cat_names: dict) -> str:
    cats = ", ".join(cat_names[c] for c in core.user_cats(user) if c in cat_names) or "—"
    return ("⚙️ <b>Настройки</b>\n\n"
            f"Время задания: <b>{user['notify_time']}</b> (МСК)\n"
            f"Категории: {_e(cats)}\n"
            f"Длительность: до <b>{user['max_minutes']}</b> мин\n"
            f"Рассылка: {'⏸ на паузе' if user['paused'] else '▶️ включена'}")


def admin_message(rep: dict) -> str:
    def pct(x):
        return "нет данных" if x is None else f"{x * 100:.0f}%"
    lines = ["🛠 <b>Сводка проекта</b>", "",
             f"Всего пользователей: {rep['users']} (прошли настройку: {rep['started']}, активны: {rep['active']})",
             f"Выполнено дел: <b>{rep['done_total']}</b> от {rep['people_done']} чел.", "",
             "<b>Показатели гипотезы</b>",
             f"• ≥5 дел из 7 в первую неделю: {pct(rep['share_5of7'])} (по {rep['closed_n']} чел., у кого неделя прошла)",
             f"• ≥10 дел за всё время: {pct(rep['share_10'])}",
             f"• средняя лучшая серия: {'нет данных' if rep['avg_best_streak'] is None else round(rep['avg_best_streak'], 1)} дн."]
    if rep["segments"]:
        lines += ["", "<b>Сегменты</b>"] + [f"• {_e(core.SEGMENTS.get(k, k))}: {v}" for k, v in rep["segments"].items()]
    if rep["by_category"]:
        lines += ["", "<b>Дела по категориям</b>"] + [f"• {_e(n)}: {c}" for n, c in rep["by_category"]]
    lines += ["", "Таблица для отчёта: /export"]
    return "\n".join(lines)
