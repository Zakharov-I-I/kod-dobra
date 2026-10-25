"""Работа с базой SQLite (стандартная библиотека, без внешних зависимостей)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

from logic import ACHIEVEMENTS
from tasks_data import BANK

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tg_id INTEGER NOT NULL UNIQUE,
    username TEXT,
    segment TEXT,
    notify_time TEXT NOT NULL DEFAULT '09:00',
    cats TEXT NOT NULL DEFAULT '1,2,3,4,5',
    max_minutes INTEGER NOT NULL DEFAULT 30,
    paused INTEGER NOT NULL DEFAULT 0,
    active INTEGER NOT NULL DEFAULT 1,
    onboarded INTEGER NOT NULL DEFAULT 0,
    joined_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS categories (id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE);
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id INTEGER NOT NULL REFERENCES categories(id),
    text TEXT NOT NULL UNIQUE,
    duration_min INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    task_id INTEGER NOT NULL REFERENCES tasks(id),
    assigned_date TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'sent',   -- sent / done / skipped
    sent_at TEXT NOT NULL,
    done_at TEXT,
    swaps INTEGER NOT NULL DEFAULT 0,
    reminded INTEGER NOT NULL DEFAULT 0,
    UNIQUE (user_id, assigned_date)
);
CREATE TABLE IF NOT EXISTS achievements (code TEXT PRIMARY KEY, title TEXT NOT NULL, description TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS user_achievements (
    user_id INTEGER NOT NULL REFERENCES users(id),
    code TEXT NOT NULL REFERENCES achievements(code),
    earned_at TEXT NOT NULL,
    PRIMARY KEY (user_id, code)
);
"""

USER_FIELDS = {"username", "segment", "notify_time", "cats", "max_minutes", "paused", "active", "onboarded"}


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.seed()

    def close(self):
        self.conn.close()

    # ---------- начальные данные ----------
    def seed(self):
        """Заполняет категории, задания и достижения. Безопасно вызывать повторно:
        новые задания из tasks_data.py добавятся, существующие не дублируются."""
        with self.conn:
            for i, (cat, items) in enumerate(BANK, start=1):
                self.conn.execute("INSERT OR IGNORE INTO categories (id, name) VALUES (?, ?)", (i, cat))
                for text, minutes in items:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO tasks (category_id, text, duration_min) VALUES (?, ?, ?)",
                        (i, text, minutes))
            for code, title, desc, _ in ACHIEVEMENTS:
                self.conn.execute("INSERT OR REPLACE INTO achievements VALUES (?, ?, ?)", (code, title, desc))

    # ---------- пользователи ----------
    def upsert_user(self, tg_id: int, username, now) -> sqlite3.Row:
        with self.conn:
            row = self.get_user(tg_id)
            if row is None:
                self.conn.execute("INSERT INTO users (tg_id, username, joined_at) VALUES (?, ?, ?)",
                                  (tg_id, username, now.isoformat(timespec="seconds")))
            else:
                self.conn.execute("UPDATE users SET username = ?, active = 1 WHERE tg_id = ?", (username, tg_id))
        return self.get_user(tg_id)

    def get_user(self, tg_id: int):
        return self.conn.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,)).fetchone()

    def get_user_by_id(self, uid: int):
        return self.conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()

    def update_user(self, tg_id: int, /, **fields):
        bad = set(fields) - USER_FIELDS
        if bad:
            raise ValueError(f"Нельзя менять поля: {bad}")
        if not fields:
            return
        sets = ", ".join(f"{k} = ?" for k in fields)
        with self.conn:
            self.conn.execute(f"UPDATE users SET {sets} WHERE tg_id = ?", (*fields.values(), tg_id))

    def delete_user(self, tg_id: int):
        row = self.get_user(tg_id)
        if row is None:
            return
        with self.conn:
            self.conn.execute("DELETE FROM user_achievements WHERE user_id = ?", (row["id"],))
            self.conn.execute("DELETE FROM assignments WHERE user_id = ?", (row["id"],))
            self.conn.execute("DELETE FROM users WHERE id = ?", (row["id"],))

    def schedulable_users(self):
        return self.conn.execute(
            "SELECT * FROM users WHERE active = 1 AND onboarded = 1 AND paused = 0").fetchall()

    def broadcast_users(self):
        return self.conn.execute("SELECT * FROM users WHERE active = 1").fetchall()

    def all_users(self):
        return self.conn.execute("SELECT * FROM users ORDER BY id").fetchall()

    # ---------- задания ----------
    def candidate_tasks(self, cat_ids, max_minutes: int):
        if not cat_ids:
            return []
        marks = ",".join("?" * len(cat_ids))
        return self.conn.execute(
            f"SELECT * FROM tasks WHERE is_active = 1 AND category_id IN ({marks}) AND duration_min <= ?",
            (*cat_ids, max_minutes)).fetchall()

    def used_task_ids(self, user_id: int) -> set:
        return {r[0] for r in self.conn.execute("SELECT task_id FROM assignments WHERE user_id = ?", (user_id,))}

    def categories(self):
        return self.conn.execute("SELECT * FROM categories ORDER BY id").fetchall()

    def add_task(self, category_id: int, text: str, minutes: int) -> bool:
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO tasks (category_id, text, duration_min) VALUES (?, ?, ?)",
                (category_id, text, minutes))
        return cur.rowcount > 0

    def count_tasks(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM tasks WHERE is_active = 1").fetchone()[0]

    # ---------- выдача и отметки ----------
    def get_assignment(self, user_id: int, day: str):
        return self.conn.execute("SELECT * FROM assignments WHERE user_id = ? AND assigned_date = ?",
                                 (user_id, day)).fetchone()

    def create_assignment(self, user_id: int, task_id: int, day: str, sent_at: str) -> int:
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO assignments (user_id, task_id, assigned_date, sent_at) VALUES (?, ?, ?, ?)",
                (user_id, task_id, day, sent_at))
        return cur.lastrowid

    def assignment_view(self, aid: int):
        return self.conn.execute(
            """SELECT a.*, t.text AS task_text, t.duration_min AS minutes, c.name AS category, t.category_id
               FROM assignments a JOIN tasks t ON t.id = a.task_id JOIN categories c ON c.id = t.category_id
               WHERE a.id = ?""", (aid,)).fetchone()

    def set_status(self, aid: int, status: str, done_at=None):
        with self.conn:
            self.conn.execute("UPDATE assignments SET status = ?, done_at = ? WHERE id = ?", (status, done_at, aid))

    def swap_task(self, aid: int, new_task_id: int):
        with self.conn:
            self.conn.execute("UPDATE assignments SET task_id = ?, swaps = swaps + 1 WHERE id = ?",
                              (new_task_id, aid))

    def mark_reminded(self, aid: int):
        with self.conn:
            self.conn.execute("UPDATE assignments SET reminded = 1 WHERE id = ?", (aid,))

    # ---------- статистика ----------
    def done_dates(self, user_id: int) -> list:
        return [r[0] for r in self.conn.execute(
            "SELECT DISTINCT assigned_date FROM assignments WHERE user_id = ? AND status = 'done'", (user_id,))]

    def category_counts(self, user_id: int):
        return self.conn.execute(
            """SELECT c.id, c.name, COUNT(*) AS n FROM assignments a
               JOIN tasks t ON t.id = a.task_id JOIN categories c ON c.id = t.category_id
               WHERE a.user_id = ? AND a.status = 'done' GROUP BY c.id ORDER BY c.id""", (user_id,)).fetchall()

    def user_achievements(self, user_id: int):
        return self.conn.execute(
            """SELECT a.code, a.title, a.description FROM user_achievements ua
               JOIN achievements a ON a.code = ua.code WHERE ua.user_id = ? ORDER BY ua.earned_at""",
            (user_id,)).fetchall()

    def owned_codes(self, user_id: int) -> set:
        return {r[0] for r in self.conn.execute("SELECT code FROM user_achievements WHERE user_id = ?", (user_id,))}

    def grant(self, user_id: int, code: str, when: str):
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO user_achievements VALUES (?, ?, ?)", (user_id, code, when))

    def community(self):
        total = self.conn.execute("SELECT COUNT(*) FROM assignments WHERE status = 'done'").fetchone()[0]
        people = self.conn.execute("SELECT COUNT(DISTINCT user_id) FROM assignments WHERE status = 'done'").fetchone()[0]
        return total, people

    def export_rows(self):
        return self.conn.execute(
            """SELECT a.user_id, COALESCE(u.segment, '') AS segment, a.assigned_date, c.name AS category,
                      t.duration_min AS minutes, a.status, a.swaps
               FROM assignments a JOIN users u ON u.id = a.user_id JOIN tasks t ON t.id = a.task_id
               JOIN categories c ON c.id = t.category_id ORDER BY a.assigned_date, a.user_id""").fetchall()

    def category_totals_done(self):
        return self.conn.execute(
            """SELECT c.name, COUNT(*) FROM assignments a JOIN tasks t ON t.id = a.task_id
               JOIN categories c ON c.id = t.category_id WHERE a.status = 'done' GROUP BY c.id ORDER BY c.id"""
        ).fetchall()
