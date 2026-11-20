# -*- coding: utf-8 -*-
"""رگرسیون باگ‌های یافت‌شده در بازبینی خط‌به‌خط (۴٫۱٫۱): هر تست یک باگ واقعی را قفل می‌کند."""
import ast, glob, os, re, sys, tempfile, unittest
from datetime import date, datetime, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import quickadd
from store import Store

class Base(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.s = Store(os.path.join(self.tmp.name, "t.db")); self.t = date.today()
    def tearDown(self): self.s.close(); self.tmp.cleanup()
    def sid(self, i=1): return self.s.study_overview()[i]["id"]

class TestPackaging(unittest.TestCase):
    def read(self, *p):
        with open(os.path.join(ROOT, *p), encoding="utf-8") as f: return f.read()
    def local_modules(self):
        mods = {os.path.splitext(os.path.basename(f))[0] for f in glob.glob(os.path.join(ROOT, "*.py"))}
        used = set()
        for f in glob.glob(os.path.join(ROOT, "*.py")):
            for n in ast.walk(ast.parse(self.read(os.path.basename(f)))):
                if isinstance(n, ast.Import): used |= {a.name.split(".")[0] for a in n.names}
                elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0: used.add(n.module.split(".")[0])
        return mods & used
    def test_ci_stages_every_runtime_module(self):
        # باگ: CI فقط main/store/ui/jalali/meta را در APK می‌گذاشت؛ pages/hero/quickadd/notify نبودند و برنامه هنگام شروع با ImportError می‌مرد
        need = self.local_modules() - {"main"}; self.assertTrue({"pages", "hero", "quickadd", "notify"} <= need)
        for f in (".github/workflows/build.yml", "WORKFLOW_build.yml.txt"):
            try: ci = self.read(*f.split("/"))
            except OSError: continue
            line = next(l for l in ci.splitlines() if "stage/" in l and l.strip().startswith("cp ") and "assets" not in l)
            if "*.py" in line: continue
            for m in need | {"main"}: self.assertIn(m + ".py", line, f"{f}: {m}.py در بستهٔ APK نیست")

class TestStoreFixes(Base):
    def test_past_done_routine_cannot_be_undone_or_locked_forever(self):
        self.s.ensure_day(self.t); r = self.s.one("SELECT * FROM missions WHERE routine_id IS NOT NULL LIMIT 1"); y = (self.t - timedelta(days=1)).isoformat()
        self.s.run("UPDATE missions SET date=?,done=1,completed_at=? WHERE id=?", (y, datetime.now().isoformat(timespec="seconds"), r["id"]))
        self.assertFalse(self.s.toggle_mission(r["id"])); self.assertEqual(self.s.one("SELECT done FROM missions WHERE id=?", (r["id"],))["done"], 1)
        row = self.s.one("SELECT * FROM missions WHERE id=?", (r["id"],)); self.assertFalse(self.s.is_missed(row)); self.assertTrue(self.s.is_locked_routine(row))
    def test_today_routine_still_toggles(self):
        self.s.ensure_day(self.t); r = self.s.one("SELECT id FROM missions WHERE routine_id IS NOT NULL LIMIT 1")
        self.assertTrue(self.s.toggle_mission(r["id"])); self.assertFalse(self.s.toggle_mission(r["id"]))
    def test_deleting_last_study_log_resets_mastery(self):
        sid = self.sid(); t = self.s.save_topic(sid, "1", "x"); lid = self.s.add_study(t, self.t, 30, 80); self.s.delete_study(lid)
        row = self.s.one("SELECT * FROM topics WHERE id=?", (t,)); self.assertEqual((row["mastery"], row["status"], row["next_review"]), (0, 0, None))
        self.assertEqual(next(x for x in self.s.study_overview() if x["id"] == sid)["progress"], 0)
    def test_moving_study_log_to_other_topic_clears_old_topic(self):
        sid = self.sid(); a = self.s.save_topic(sid, "1", "a"); b = self.s.save_topic(sid, "1", "b"); lid = self.s.add_study(a, self.t, 10, 90)
        self.s.update_study(lid, b, self.t, 10, 90); self.assertEqual(self.s.one("SELECT mastery FROM topics WHERE id=?", (a,))["mastery"], 0)
    def test_deleting_study_keeps_quiz_status(self):
        sid = self.sid(); self.s.add_test(sid, "1", "q", "exam", 10, 9, 1, 0, self.t); t = self.s.find_topic(sid, "1", "q")["id"]
        lid = self.s.add_study(t, self.t, 10, 70); st = self.s.one("SELECT status,next_review FROM topics WHERE id=?", (t,)); self.s.delete_study(lid)
        row = self.s.one("SELECT * FROM topics WHERE id=?", (t,)); self.assertEqual((row["mastery"], row["status"], row["next_review"]), (0, st["status"], st["next_review"]))
    def test_studying_a_due_topic_counts_as_review(self):
        sid = self.sid(); t = self.s.save_topic(sid, "2", "y"); self.s.add_study(t, self.t - timedelta(days=5), 10, 50)
        self.assertIn("y", [d["name"] for d in self.s.due_topics()])
        self.s.add_study(t, self.t, 10, 90); self.assertNotIn("y", [d["name"] for d in self.s.due_topics()])
        self.assertGreater(self.s.one("SELECT next_review FROM topics WHERE id=?", (t,))["next_review"], self.t.isoformat())
    def test_note_search_wildcards_are_literal(self):
        self.s.save_note("a", "hello"); self.s.save_note("b", "50% off"); self.s.save_note("c", "snake_case")
        self.assertEqual([r["title"] for r in self.s.search_notes("%")], ["b"]); self.assertEqual([r["title"] for r in self.s.search_notes("_")], ["c"])
        self.assertEqual(len(self.s.search_notes("")), 3); self.assertEqual(len(self.s.search_notes("hel")), 1); self.assertEqual(len(self.s.search_notes("\\")), 0)
    def test_move_tomorrow_never_pulls_future_task_earlier(self):
        m = self.s.save_mission("f", "", 10, 1, self.t + timedelta(days=5)); self.s.move_tomorrow(m)
        self.assertEqual(self.s.one("SELECT date FROM missions WHERE id=?", (m,))["date"], (self.t + timedelta(days=6)).isoformat())
        o = self.s.save_mission("o", "", 10, 1, self.t - timedelta(days=3)); self.s.move_tomorrow(o)
        self.assertEqual(self.s.one("SELECT date FROM missions WHERE id=?", (o,))["date"], (self.t + timedelta(days=1)).isoformat())
        n = self.s.save_mission("n", "", 10, 1, self.t); self.s.move_tomorrow(n); self.assertEqual(self.s.one("SELECT date FROM missions WHERE id=?", (n,))["date"], (self.t + timedelta(days=1)).isoformat())
    def test_editing_done_mission_keeps_ledger_xp(self):
        m = self.s.save_mission("x", "", 30, 1, self.t); self.s.toggle_mission(m); want = self.s.one("SELECT xp FROM xp_ledger WHERE mission_id=?", (m,))["xp"]
        self.s.save_mission("x", "", 120, 2, self.t, mid=m); self.assertEqual(self.s.one("SELECT xp FROM missions WHERE id=?", (m,))["xp"], want)
        u = self.s.save_mission("u", "", 30, 1, self.t); self.s.save_mission("u", "", 120, 2, self.t, mid=u); self.assertGreater(self.s.one("SELECT xp FROM missions WHERE id=?", (u,))["xp"], want)
    def test_zero_total_test_does_not_crash(self):
        t = self.s.save_topic(self.sid(), "1", "z"); self.s.add_log(t, "exam", 0, 0, None, self.t)

class TestQuickAddTimes(unittest.TestCase):
    def tm(self, q): return quickadd.parse(q, date(2026, 11, 20))
    def test_night_and_midnight(self):
        self.assertEqual(self.tm("مطالعه ساعت ۱۲ شب")["time"], "00:00"); self.assertEqual(self.tm("مطالعه ساعت ۹ شب")["time"], "21:00"); self.assertEqual(self.tm("مطالعه ساعت ۲ شب")["time"], "02:00")
    def test_spaced_afternoon(self):
        p = self.tm("حل تمرین ساعت ۴ بعد از ظهر"); self.assertEqual((p["time"], p["title"]), ("16:00", "حل تمرین"))
    def test_existing_behaviour_kept(self):
        self.assertEqual(self.tm("ساعت ۴ عصر مرور")["time"], "16:00"); self.assertEqual(self.tm("فردا ساعت ۱۶:۳۰ حل تمرین ۴۵ دقیقه مهم")["time"], "16:30"); self.assertEqual(self.tm("ساعت ۱۰ صبح")["time"], "10:00")

if __name__ == "__main__": unittest.main()
