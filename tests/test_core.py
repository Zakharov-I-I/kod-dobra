import os
import sys
import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core  # noqa: E402
import logic  # noqa: E402
from config import Config  # noqa: E402
from db import DB  # noqa: E402

TZ = ZoneInfo("Europe/Moscow")
CFG = Config(token="x", admin_ids=frozenset({1}), tz=TZ, db_path=":memory:", reminder_time="19:00")


def at(day, hm="09:00"):
    h, m = map(int, hm.split(":"))
    return datetime(2026, 11, 1, h, m, tzinfo=TZ) + timedelta(days=day)


def make_user(db, tg=100, notify="09:00", now=None):
    db.upsert_user(tg, "tester", now or at(0, "08:00"))
    db.update_user(tg, onboarded=1, notify_time=notify, segment="student12")
    return db.get_user(tg)


class Streaks(unittest.TestCase):
    d = staticmethod(lambda *xs: [date(2026, 11, x) for x in xs])

    def test_empty(self):
        self.assertEqual(logic.compute_streaks([], date(2026, 11, 5)), (0, 0))

    def test_simple_run(self):
        self.assertEqual(logic.compute_streaks(self.d(1, 2, 3), date(2026, 11, 3)), (3, 3))

    def test_one_missed_day_keeps_streak(self):
        self.assertEqual(logic.compute_streaks(self.d(1, 2, 4), date(2026, 11, 4)), (3, 3))

    def test_two_missed_days_reset(self):
        self.assertEqual(logic.compute_streaks(self.d(1, 2, 5), date(2026, 11, 5)), (1, 2))

    def test_current_alive_with_one_gap_today(self):
        # последнее дело 2-го, сегодня 4-е: пропущено только 3-е → серия жива
        self.assertEqual(logic.compute_streaks(self.d(1, 2), date(2026, 11, 4))[0], 2)

    def test_current_dies_after_two_missed(self):
        self.assertEqual(logic.compute_streaks(self.d(1, 2), date(2026, 11, 5))[0], 0)
        self.assertEqual(logic.compute_streaks(self.d(1, 2), date(2026, 11, 5))[1], 2)

    def test_duplicates_ignored(self):
        self.assertEqual(logic.compute_streaks(self.d(1, 1, 2), date(2026, 11, 2)), (2, 2))


class Time(unittest.TestCase):
    def test_parse(self):
        for raw, ok in [("9:30", "09:30"), ("09.30", "09:30"), ("21-05", "21:05"), (" 7:00 ", "07:00"),
                        ("24:00", None), ("12:60", None), ("abc", None), ("", None), (None, None)]:
            self.assertEqual(logic.parse_time(raw), ok, raw)


class Bank(unittest.TestCase):
    def test_seed(self):
        db = DB(":memory:")
        self.assertEqual(db.count_tasks(), 50)
        self.assertEqual(len(db.categories()), 5)
        db.seed()  # повторный запуск не дублирует
        self.assertEqual(db.count_tasks(), 50)
        rows = db.conn.execute("SELECT category_id, COUNT(*) FROM tasks GROUP BY category_id").fetchall()
        self.assertTrue(all(r[1] == 10 for r in rows))
        mins = [r[0] for r in db.conn.execute("SELECT duration_min FROM tasks")]
        self.assertTrue(min(mins) >= 5 and max(mins) <= 30)

    def test_add_task(self):
        db = DB(":memory:")
        self.assertTrue(db.add_task(1, "Новое тестовое задание", 10))
        self.assertFalse(db.add_task(1, "Новое тестовое задание", 10))
        self.assertEqual(db.count_tasks(), 51)


class Flow(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.u = make_user(self.db)
        self.addCleanup(self.db.close)

    def test_issue_is_idempotent_per_day(self):
        v1, new1 = core.issue_task(self.db, self.u, at(0))
        v2, new2 = core.issue_task(self.db, self.u, at(0, "15:00"))
        self.assertTrue(new1)
        self.assertFalse(new2)
        self.assertEqual(v1["id"], v2["id"])

    def test_no_repeats_until_bank_exhausted(self):
        seen = set()
        for day in range(50):
            v, _ = core.issue_task(self.db, self.u, at(day))
            self.assertNotIn(v["task_id"], seen)
            seen.add(v["task_id"])
        v, _ = core.issue_task(self.db, self.u, at(50))  # 51-й день — банк пройден, повторы допустимы
        self.assertIsNotNone(v)

    def test_respects_categories_and_duration(self):
        self.db.update_user(100, cats="2", max_minutes=15)
        u = self.db.get_user(100)
        for day in range(10):
            v, _ = core.issue_task(self.db, u, at(day))
            self.assertEqual(v["category_id"], 2)
            self.assertLessEqual(v["minutes"], 15)

    def test_complete_and_stats(self):
        for day in range(3):
            v, _ = core.issue_task(self.db, self.u, at(day))
            res = core.complete_assignment(self.db, self.u, v["id"], at(day, "12:00"))
            self.assertEqual(res["status"], "ok")
        self.assertEqual((res["current"], res["total"]), (3, 3))
        codes = {c for c, _, _ in res["new"]}
        self.assertIn("streak3", codes)
        again = core.complete_assignment(self.db, self.u, v["id"], at(2, "13:00"))
        self.assertEqual(again["status"], "already_done")

    def test_achievements_not_granted_twice(self):
        v, _ = core.issue_task(self.db, self.u, at(0))
        r1 = core.complete_assignment(self.db, self.u, v["id"], at(0, "12:00"))
        self.assertEqual([c for c, _, _ in r1["new"]], ["first_step"])
        v2, _ = core.issue_task(self.db, self.u, at(1))
        r2 = core.complete_assignment(self.db, self.u, v2["id"], at(1, "12:00"))
        self.assertEqual(r2["new"], [])

    def test_can_complete_yesterday_but_not_older(self):
        v0, _ = core.issue_task(self.db, self.u, at(0))
        v1, _ = core.issue_task(self.db, self.u, at(1))
        v2, _ = core.issue_task(self.db, self.u, at(2))
        self.assertEqual(core.complete_assignment(self.db, self.u, v1["id"], at(2, "10:00"))["status"], "ok")
        self.assertEqual(core.complete_assignment(self.db, self.u, v0["id"], at(2, "10:00"))["status"], "expired")

    def test_cannot_touch_foreign_assignment(self):
        other = make_user(self.db, tg=200)
        v, _ = core.issue_task(self.db, other, at(0))
        self.assertEqual(core.complete_assignment(self.db, self.u, v["id"], at(0))["status"], "not_found")
        self.assertEqual(core.swap_assignment(self.db, self.u, v["id"], at(0))["status"], "not_found")
        self.assertEqual(core.skip_assignment(self.db, self.u, v["id"], at(0))["status"], "not_found")

    def test_swap_once_per_day(self):
        v, _ = core.issue_task(self.db, self.u, at(0))
        r = core.swap_assignment(self.db, self.u, v["id"], at(0))
        self.assertEqual(r["status"], "ok")
        self.assertNotEqual(r["view"]["task_id"], v["task_id"])
        self.assertEqual(core.swap_assignment(self.db, self.u, v["id"], at(0))["status"], "limit")

    def test_skip_then_done_allowed(self):
        v, _ = core.issue_task(self.db, self.u, at(0))
        self.assertEqual(core.skip_assignment(self.db, self.u, v["id"], at(0))["status"], "ok")
        self.assertEqual(self.db.assignment_view(v["id"])["status"], "skipped")
        self.assertEqual(core.complete_assignment(self.db, self.u, v["id"], at(0, "20:00"))["status"], "ok")

    def test_done_today_command(self):
        self.assertEqual(core.done_today(self.db, self.u, at(0))["status"], "no_task")
        core.issue_task(self.db, self.u, at(0))
        self.assertEqual(core.done_today(self.db, self.u, at(0, "12:00"))["status"], "ok")

    def test_all_categories_achievement_and_30_days(self):
        # 30 дней подряд: должны появиться streak7, streak14, total10, total30 и all_cats
        got = set()
        for day in range(30):
            v, _ = core.issue_task(self.db, self.u, at(day))
            res = core.complete_assignment(self.db, self.u, v["id"], at(day, "12:00"))
            got |= {c for c, _, _ in res["new"]}
        self.assertTrue({"first_step", "streak3", "streak7", "streak14", "total10", "total30", "all_cats"} <= got)
        st = core.build_stats(self.db, self.u, at(29, "13:00"))
        self.assertEqual((st["total"], st["current"], st["best"]), (30, 30, 30))
        self.assertEqual(st["days_in_bot"], 30)
        self.assertEqual(len(st["achievements"]), 7)

    def test_delete_user_removes_everything(self):
        v, _ = core.issue_task(self.db, self.u, at(0))
        core.complete_assignment(self.db, self.u, v["id"], at(0, "12:00"))
        self.db.delete_user(100)
        self.assertIsNone(self.db.get_user(100))
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM assignments").fetchone()[0], 0)
        self.assertEqual(self.db.conn.execute("SELECT COUNT(*) FROM user_achievements").fetchone()[0], 0)
        self.db.delete_user(100)  # повторное удаление не падает

    def test_update_user_rejects_unknown_field(self):
        with self.assertRaises(ValueError):
            self.db.update_user(100, tg_id=5)


class Scheduler(unittest.TestCase):
    def setUp(self):
        self.db = DB(":memory:")
        self.addCleanup(self.db.close)

    def kinds(self, now):
        return [(k, u["tg_id"]) for k, u, _ in core.due_actions(self.db, CFG, now)]

    def test_daily_sent_at_notify_time_only_once(self):
        make_user(self.db, 100, "09:00")
        self.assertEqual(self.kinds(at(0, "08:59")), [])
        self.assertEqual(self.kinds(at(0, "09:00")), [("daily", 100)])
        u = self.db.get_user(100)
        core.issue_task(self.db, u, at(0, "09:00"))
        self.assertEqual(self.kinds(at(0, "09:01")), [])

    def test_catch_up_after_downtime(self):
        make_user(self.db, 100, "09:00")
        self.assertEqual(self.kinds(at(0, "13:30")), [("daily", 100)])

    def test_reminder_rules(self):
        u = make_user(self.db, 100, "09:00")
        core.issue_task(self.db, u, at(0, "09:00"))
        self.assertEqual(self.kinds(at(0, "18:59")), [])
        self.assertEqual(self.kinds(at(0, "19:00")), [("reminder", 100)])
        a = self.db.get_assignment(u["id"], at(0).date().isoformat())
        self.db.mark_reminded(a["id"])
        self.assertEqual(self.kinds(at(0, "19:30")), [])

    def test_no_reminder_if_done_or_late_evening(self):
        u = make_user(self.db, 100, "09:00")
        v, _ = core.issue_task(self.db, u, at(0, "09:00"))
        self.assertEqual(self.kinds(at(0, "22:30")), [])
        core.complete_assignment(self.db, u, v["id"], at(0, "10:00"))
        self.assertEqual(self.kinds(at(0, "19:30")), [])

    def test_reminder_waits_two_hours_after_late_task(self):
        u = make_user(self.db, 100, "18:30")
        core.issue_task(self.db, u, at(0, "18:30"))
        self.assertEqual(self.kinds(at(0, "19:30")), [])
        self.assertEqual(self.kinds(at(0, "20:30")), [("reminder", 100)])

    def test_paused_inactive_and_unonboarded_skipped(self):
        make_user(self.db, 100)
        make_user(self.db, 101)
        make_user(self.db, 102)
        self.db.update_user(100, paused=1)
        self.db.update_user(101, active=0)
        self.db.update_user(102, onboarded=0)
        self.assertEqual(self.kinds(at(0, "10:00")), [])

    def test_new_day_new_task(self):
        u = make_user(self.db, 100)
        core.issue_task(self.db, u, at(0))
        self.assertEqual(self.kinds(at(1, "09:00")), [("daily", 100)])


class Admin(unittest.TestCase):
    def test_report_and_export(self):
        db = DB(":memory:")
        u = make_user(db, 100, now=at(0, "08:00"))
        make_user(db, 101, now=at(0, "08:00"))
        for day in range(6):  # пользователь 100 выполнил 6 дел в первую неделю
            v, _ = core.issue_task(db, u, at(day))
            core.complete_assignment(db, u, v["id"], at(day, "12:00"))
        rep = core.admin_report(db, at(8, "10:00"))
        self.assertEqual((rep["users"], rep["started"], rep["done_total"]), (2, 2, 6))
        self.assertEqual(rep["closed_n"], 2)
        self.assertAlmostEqual(rep["share_5of7"], 0.5)
        self.assertAlmostEqual(rep["share_10"], 0.0)
        csv_text = core.export_csv(db)
        self.assertEqual(len(csv_text.strip().splitlines()), 7)

    def test_report_empty(self):
        rep = core.admin_report(DB(":memory:"), at(0))
        self.assertIsNone(rep["share_5of7"])
        self.assertEqual(rep["users"], 0)


class TextsSmoke(unittest.TestCase):
    def test_all_messages_render(self):
        import texts
        db = DB(":memory:")
        u = make_user(db)
        v, _ = core.issue_task(db, u, at(0))
        info = core.streak_info(db, u, at(0).date())
        self.assertIn("Доброе дело", texts.task_message(v, info, "Привет"))
        res = core.complete_assignment(db, u, v["id"], at(0, "12:00"))
        self.assertIn("Всего добрых дел", texts.done_message(res))
        self.assertIn("Достижения", texts.stats_message(core.build_stats(db, u, at(0, "13:00"))))
        names = {c["id"]: c["name"] for c in db.categories()}
        self.assertIn("Настройки", texts.settings_message(db.get_user(100), names))
        self.assertIn("Сводка", texts.admin_message(core.admin_report(db, at(0, "13:00"))))
        self.assertIn("ждёт", texts.reminder_message(v))
        self.assertNotIn("<script", texts.task_message({**dict(v), "task_text": "<script>x</script>"}, info))


if __name__ == "__main__":
    unittest.main(verbosity=1)
