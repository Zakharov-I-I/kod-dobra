"""Настройки бота из переменных окружения / файла .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class Config:
    token: str
    admin_ids: frozenset
    tz: ZoneInfo
    db_path: str
    reminder_time: str  # "HH:MM" — во сколько напоминать, если задание не отмечено


def load_config() -> Config:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:  # python-dotenv не обязателен: можно задать переменные в системе
        pass
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise SystemExit("Не задан BOT_TOKEN. Скопируйте .env.example в .env и впишите токен от @BotFather.")
    admins = frozenset(int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x)
    return Config(
        token=token,
        admin_ids=admins,
        tz=ZoneInfo(os.getenv("TIMEZONE", "Europe/Moscow")),
        db_path=os.getenv("DB_PATH", "data/dobroden.db"),
        reminder_time=os.getenv("REMINDER_TIME", "19:00"),
    )
