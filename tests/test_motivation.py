# -*- coding: utf-8 -*-
import os, sys, tempfile, unittest
from datetime import date, datetime, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from store import Store, GOAL_BONUS, STREAK_MILESTONES, ACHIEVEMENTS

T = date.today()
def D(n=0): return (T + timedelta(days=n)).isoformat()

class Base(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.s = Store(os.path.join(self.dir.name, "t.db")); self.s.setpref("daily_goal", "2")
    def tearDown(self): self.s.db.close(); self.dir.cleanup()
    def done(self, n=1, day=None):
        ids = []
        for i in range(n):
            m = self.s.save_mission(f"کار{i}", "", 30, 1, day or D(), kind="task"); self.s.toggle_mission(m); ids.append(m)
        return ids
    def activity(self, offset):       # فعالیت در یک روز دلخواه
        self.s.db.execute("INSERT INTO focus_sessions(mission_id,seconds,at) VALUES(NULL,600,?)", (D(offset) + "T10:00:00",)); self.s.db.commit()

class TestGoalBonus(Base):
    def test_not_before_goal(self):
        self.done(1); self.assertEqual(self.s.claim_goal_bonus(), 0)
    def test_once_per_day_and_counts_in_xp(self):
        self.done(2); x0 = self.s.xp()
        self.assertEqual(self.s.claim_goal_bonus(), GOAL_BONUS); self.assertEqual(self.s.xp(), x0 + GOAL_BONUS)
        self.assertEqual(self.s.claim_goal_bonus(), 0); self.assertEqual(self.s.xp(), x0 + GOAL_BONUS)
    def test_undo_redo_gives_no_second_bonus(self):
        ids = self.done(2); self.s.claim_goal_bonus()
        self.s.toggle_mission(ids[0]); self.assertEqual(self.s.claim_goal_bonus(), 0)
        self.s.toggle_mission(ids[0]); self.assertEqual(self.s.claim_goal_bonus(), 0)
    def test_routines_do_not_count(self):
        self.s.setpref("daily_goal", "1"); self.s.ensure_day(D())
        r = self.s.one("SELECT id FROM missions WHERE routine_id IS NOT NULL AND date=?", (D(),)); self.s.toggle_mission(r["id"])
        self.assertEqual(self.s.claim_goal_bonus(), 0)
    def test_goal_days_stat_and_achievement(self):
        for k in range(7):
            self.done(2, D(-k)); self.s.claim_goal_bonus(D(-k))
        self.assertEqual(self.s.stats()["goal_days"], 7)
        self.assertIn("goal_7", [a[0] for a in self.s.check_achievements()])
    def test_penalty_not_counted_as_goal_day(self):
        self.s.db.execute("INSERT INTO xp_ledger(mission_id,xp,at) VALUES(5,-5,?)", (D() + "T01:00:00",)); self.s.db.commit()
        self.assertEqual(self.s.stats()["goal_days"], 0)
    def test_backup_roundtrip_keeps_bonus(self):
        self.done(2); self.s.claim_goal_bonus(); xp = self.s.xp(); txt = self.s.backup_text(); self.s.restore_text(txt, snapshot=False)
        self.assertEqual(self.s.xp(), xp); self.assertEqual(self.s.claim_goal_bonus(), 0)

class TestStreakMilestone(Base):
    def test_fires_once(self):
        for k in range(3): self.activity(-k)
        self.assertEqual(self.s.streak_milestone(), 3); self.assertEqual(self.s.streak_milestone(), 0)
    def test_non_milestone_silent(self):
        for k in range(2): self.activity(-k)
        self.assertEqual(self.s.streak_milestone(), 0)
    def test_rearms_after_break(self):
        for k in range(3): self.activity(-k)
        self.s.streak_milestone()
        self.s.db.execute("DELETE FROM focus_sessions"); self.s.db.commit()
        self.assertEqual(self.s.streak_milestone(), 0)
        for k in range(3): self.activity(-k)
        self.assertEqual(self.s.streak_milestone(), 3)
    def test_next_milestone(self):
        self.assertEqual(self.s.next_milestone(0), 3); self.assertEqual(self.s.next_milestone(7), 14); self.assertIsNone(self.s.next_milestone(100))

class TestCoach(Base):
    def at(self, h): return datetime.combine(T, datetime.min.time()).replace(hour=h)
    def test_new_user(self):
        self.assertEqual(self.s.coach(now=self.at(10))[0], "ROCKET_LAUNCH")
    def test_streak_at_risk_evening(self):
        self.activity(-1); self.activity(-2)
        c = self.s.coach(now=self.at(20)); self.assertEqual(c[1], "red"); self.assertIn("خطر", c[2])
    def test_streak_morning_is_gentle(self):
        self.activity(-1); self.assertEqual(self.s.coach(now=self.at(9))[1], "gold")
    def test_goal_progress_then_reached(self):
        self.s.setpref("daily_goal", "3"); self.done(1)
        self.assertEqual(self.s.coach(now=self.at(12))[0], "TRACK_CHANGES")
        self.done(2); self.assertEqual(self.s.coach(now=self.at(12))[0], "CELEBRATION")
    def test_comeback_after_gap(self):
        self.activity(-5); self.assertEqual(self.s.coach(now=self.at(12))[0], "REPLAY")
    def test_exam_countdown(self):
        for k in range(4): self.activity(-k)                       # استریک ۴ (از نقطهٔ عطف ۷ دور است)؛ هدف نزده‌ایم
        self.s.setpref("exam_date", D(10))
        c = self.s.coach(now=self.at(12)); self.assertEqual(c[0], "EVENT"); self.assertEqual(c[1], "red")
    def test_default_quote_when_nothing_else(self):
        for k in range(4): self.activity(-k)
        c = self.s.coach(now=self.at(12)); self.assertIn(c[0], ("FORMAT_QUOTE", "FLAG"))
    def test_always_returns_four_strings(self):
        for off in (None, 0, 1, 3, 9):
            self.s.db.execute("DELETE FROM focus_sessions")
            if off is not None: self.activity(-off)
            for h in (8, 19):
                c = self.s.coach(now=self.at(h)); self.assertEqual(len(c), 4); self.assertTrue(all(isinstance(x, str) and x for x in c))

class TestAchievementsList(unittest.TestCase):
    def test_ids_unique_and_have_icons(self):
        import ui
        ids = [a[0] for a in ACHIEVEMENTS]; self.assertEqual(len(ids), len(set(ids)))
        for i in ids: self.assertIn(i, ui.ACHIEVEMENT_ICONS)
        self.assertTrue(all(m > 0 for m in STREAK_MILESTONES))

if __name__ == "__main__": unittest.main()
