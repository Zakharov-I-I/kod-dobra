"""Сценарии бота без привязки к Telegram: выдача заданий, отметки, статистика, расписание.

Всё здесь работает только с базой и датами, поэтому проверяется обычными тестами (tests/test_core.py).
"""
from __future__ import annotations

import csv
import io
import random
from datetime import date, datetime, timedelta

import logic
from config import Config
from db import DB

SEGMENTS = {"school": "Школьник 9–11 класса", "student12": "Студент 1–2 курса", "student3p": "Студент 3 курса и старше"}
DURATIONS = (15, 30)  # варианты «не дольше N минут» в настройках
MAX_REMIND_HOUR = 22  # позже этого часа напоминания не отправляем


def user_cats(user) -> list:
    cats = [int(x) for x in (user["cats"] or "").split(",") if x]
    return cats


# ---------- выдача заданий ----------
def choose_task(db: DB, user, exclude=()):
    """Случайное задание из включённых категорий; пока не пройдён весь банк — без повторов."""
    cand = db.candidate_tasks(user_cats(user), user["max_minutes"])
    if not cand:  # настройки слишком узкие — не оставляем человека без задания
        cand = db.candidate_tasks([c["id"] for c in db.categories()], 30)
    used = db.used_task_ids(user["id"])
    fresh = [t for t in cand if t["id"] not in used and t["id"] not in exclude]
    pool = fresh or [t for t in cand if t["id"] not in exclude] or cand
    return random.choice(pool) if pool else None


def issue_task(db: DB, user, now: datetime):
    """Задание на сегодня: существующее или новое. Возвращает (view, создано_ли_сейчас) либо (None, False)."""
    day = now.date().isoformat()
    existing = db.get_assignment(user["id"], day)
    if existing is not None:
        return db.assignment_view(existing["id"]), False
    task = choose_task(db, user)
    if task is None:
        return None, False
    aid = db.create_assignment(user["id"], task["id"], day, now.isoformat(timespec="seconds"))
    return db.assignment_view(aid), True


def swap_assignment(db: DB, user, aid: int, now: datetime):
    a = db.assignment_view(aid)
    if a is None or a["user_id"] != user["id"]:
        return {"status": "not_found"}
    if a["assigned_date"] != now.date().isoformat():
        return {"status": "expired"}
    if a["status"] == "done":
        return {"status": "already_done"}
    if a["swaps"] >= 1:
        return {"status": "limit"}
    task = choose_task(db, user, exclude={a["task_id"]})
    if task is None or task["id"] == a["task_id"]:
        return {"status": "no_tasks"}
    db.swap_task(aid, task["id"])
    if a["status"] == "skipped":
        db.set_status(aid, "sent")
    return {"status": "ok", "view": db.assignment_view(aid)}


def skip_assignment(db: DB, user, aid: int, now: datetime):
    a = db.assignment_view(aid)
    if a is None or a["user_id"] != user["id"]:
        return {"status": "not_found"}
    if a["status"] == "done":
        return {"status": "already_done"}
    db.set_status(aid, "skipped")
    return {"status": "ok"}


# ---------- статистика ----------
def streak_info(db: DB, user, today: date) -> dict:
    dates = [date.fromisoformat(d) for d in db.done_dates(user["id"])]
    current, best = logic.compute_streaks(dates, today)
    return {"current": current, "best": best, "total": len(dates)}


def _stats_for_achievements(db: DB, user, today: date) -> dict:
    s = streak_info(db, user, today)
    done_total = sum(r["n"] for r in db.category_counts(user["id"]))
    return {"total": done_total, "current": s["current"], "best": s["best"],
            "cats_done": len(db.category_counts(user["id"])), "cats_total": len(db.categories())}


def complete_assignment(db: DB, user, aid: int, now: datetime):
    a = db.assignment_view(aid)
    if a is None or a["user_id"] != user["id"]:
        return {"status": "not_found"}
    if a["status"] == "done":
        return {"status": "already_done"}
    yesterday = (now.date() - timedelta(days=1)).isoformat()
    if a["assigned_date"] < yesterday:
        return {"status": "expired"}
    db.set_status(aid, "done", now.isoformat(timespec="seconds"))
    st = _stats_for_achievements(db, user, now.date())
    new = logic.new_achievements(st, db.owned_codes(user["id"]))
    for code, _, _ in new:
        db.grant(user["id"], code, now.isoformat(timespec="seconds"))
    comm_total, _ = db.community()
    return {"status": "ok", "view": db.assignment_view(aid), "current": st["current"], "best": st["best"],
            "total": st["total"], "new": new, "community_total": comm_total}


def done_today(db: DB, user, now: datetime):
    """Для команды /done: отметить сегодняшнее задание."""
    a = db.get_assignment(user["id"], now.date().isoformat())
    if a is None:
        return {"status": "no_task"}
    return complete_assignment(db, user, a["id"], now)


def build_stats(db: DB, user, now: datetime) -> dict:
    today = now.date()
    s = streak_info(db, user, today)
    joined = date.fromisoformat(user["joined_at"][:10])
    comm_total, comm_people = db.community()
    return {**s, "days_in_bot": (today - joined).days + 1,
            "by_cat": [(r["name"], r["n"]) for r in db.category_counts(user["id"])],
            "achievements": [(r["title"], r["description"]) for r in db.user_achievements(user["id"])],
            "achievements_total": len(logic.ACHIEVEMENTS),
            "community_total": comm_total, "community_people": comm_people}


# ---------- расписание ----------
def due_actions(db: DB, cfg: Config, now: datetime) -> list:
    """Что нужно отправить прямо сейчас: [('daily', user, None) | ('reminder', user, assignment)]."""
    actions = []
    today = now.date().isoformat()
    now_min = now.hour * 60 + now.minute
    rem_min = logic.hm_to_minutes(cfg.reminder_time)
    for user in db.schedulable_users():
        a = db.get_assignment(user["id"], today)
        if a is None:
            if now_min >= logic.hm_to_minutes(user["notify_time"]):
                actions.append(("daily", user, None))
        elif a["status"] == "sent" and not a["reminded"] and now.hour < MAX_REMIND_HOUR:
            sent = datetime.fromisoformat(a["sent_at"])
            due = max(rem_min, sent.hour * 60 + sent.minute + 120)  # напоминаем через ≥2 ч после задания
            if now_min >= due:
                actions.append(("reminder", user, a))
    return actions


# ---------- администратор ----------
def admin_report(db: DB, now: datetime) -> dict:
    users = db.all_users()
    today = now.date()
    per = []
    for u in users:
        dates = sorted(date.fromisoformat(d) for d in db.done_dates(u["id"]))
        cur, best = logic.compute_streaks(dates, today)
        joined = date.fromisoformat(u["joined_at"][:10])
        first7 = sum(1 for d in dates if joined <= d <= joined + timedelta(days=6))
        per.append({"u": u, "total": len(dates), "best": best, "first7": first7,
                    "window_closed": (today - joined).days >= 7})
    started = [p for p in per if p["u"]["onboarded"]]
    closed = [p for p in started if p["window_closed"]]
    seg = {}
    for p in started:
        seg[p["u"]["segment"] or "не указан"] = seg.get(p["u"]["segment"] or "не указан", 0) + 1
    comm_total, comm_people = db.community()
    return {
        "users": len(users), "started": len(started), "active": sum(1 for p in started if p["u"]["active"]),
        "done_total": comm_total, "people_done": comm_people,
        "share_5of7": (sum(1 for p in closed if p["first7"] >= 5) / len(closed)) if closed else None,
        "closed_n": len(closed), "share_10": (sum(1 for p in started if p["total"] >= 10) / len(started)) if started else None,
        "avg_best_streak": (sum(p["best"] for p in started) / len(started)) if started else None,
        "segments": seg, "by_category": db.category_totals_done(),
    }


def export_csv(db: DB) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["user", "segment", "date", "category", "minutes", "status", "swaps"])
    for r in db.export_rows():
        w.writerow([r["user_id"], SEGMENTS.get(r["segment"], r["segment"]), r["assigned_date"], r["category"],
                    r["minutes"], r["status"], r["swaps"]])
    return buf.getvalue()
