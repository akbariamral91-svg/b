# -*- coding: utf-8 -*-
"""نسخهٔ ۴٫۱: منطق تحصیل (درس، مبحث، مطالعه، تست)، اهداف هفتگی، دستهٔ یادداشت و نمودارها + دارایی‌های تصویری."""
import os, sys, tempfile, unittest
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); sys.path.insert(0, ROOT)
import store as sm
from store import Store

class T(unittest.TestCase):
    def setUp(self): self.tmp = tempfile.TemporaryDirectory(); self.s = Store(os.path.join(self.tmp.name, "t.db")); self.sid = {r["name"]: r["id"] for r in (self.s.study_overview(), )[0] and [dict(id=x["id"], name=x["name"]) for x in self.s.study_overview()]}
    def tearDown(self): self.s.close(); self.tmp.cleanup()
    def st(self, name="ریاضی"): return next(x for x in self.s.study_overview() if x["name"] == name)

class TestStudy(T):
    def test_six_default_subjects_in_order_and_idempotent(self):
        names = [x["name"] for x in self.s.study_overview()]; self.assertEqual(names, [n for n, _ in sm.DEFAULT_SUBJECTS]); self.assertEqual(len(self.s.study_overview()), 6)
    def test_progress_uses_chapter_count(self):
        m = self.sid["ریاضی"]; self.s.set_total_chapters(m, 10)
        t = self.s.save_topic(m, "3", "تابع"); self.s.add_study(t, date.today(), 30, 100)
        r = self.st(); self.assertEqual((r["progress"], r["last_chapter"], r["last_topic"], r["minutes"]), (10, "3", "تابع", 30))
        t2 = self.s.save_topic(m, "۴", "معادله"); self.s.add_study(t2, date.today(), 20, 50); self.assertEqual(self.st()["progress"], 15)
    def test_study_enters_review_cycle_and_edit_delete(self):
        m = self.sid["علوم"]; t = self.s.save_topic(m, "1", "سلول"); lid = self.s.add_study(t, date.today(), 15, 40)
        row = self.s.one("SELECT * FROM topics WHERE id=?", (t,)); self.assertEqual((row["mastery"], row["status"]), (40, 1)); self.assertTrue(row["next_review"])
        self.s.update_study(lid, t, date.today(), 25, 80, "ن"); self.assertEqual(self.s.one("SELECT mastery FROM topics WHERE id=?", (t,))["mastery"], 80)
        self.s.delete_study(lid); self.assertEqual(self.s.study_logs_of(t), [])
        self.assertIn(date.today().isoformat(), self.s.activity_days() or [date.today().isoformat()])
    def test_topic_no_duplicates_and_delete_cascades(self):
        m = self.sid["فارسی"]; a = self.s.save_topic(m, "2", "دستور"); b = self.s.save_topic(m, "2", "دستور"); self.assertEqual(a, b)
        self.s.add_study(a, date.today(), 10, 50); self.s.add_test(m, "2", "دستور", "practice", 10, 5, 3, 2, date.today())
        self.s.delete_topic(a); self.assertEqual((self.s.one("SELECT COUNT(*) n FROM study_logs")["n"], self.s.one("SELECT COUNT(*) n FROM quiz_logs")["n"]), (0, 0))
    def test_tests_counts_edit_delete_and_replay(self):
        m = self.sid["عربی"]; d0 = date.today() - timedelta(days=3)
        self.s.add_test(m, "1", "ضمایر", "exam", 10, 9, 1, 0, d0); self.s.add_test(m, "1", "ضمایر", "exam", 10, 9, 1, 0, d0 + timedelta(days=1))
        t = self.s.find_topic(m, "1", "ضمایر"); self.assertEqual(self.s.one("SELECT status FROM topics WHERE id=?", (t["id"],))["status"], 3)
        rows = self.s.tests_of(m); self.assertEqual((len(rows), rows[0]["wrong_n"], rows[0]["blank_n"]), (2, 1, 0))
        self.s.update_test(rows[0]["id"], m, "1", "ضمایر", "exam", 10, 3, 5, 2, d0 + timedelta(days=1))
        self.assertNotEqual(self.s.one("SELECT status FROM topics WHERE id=?", (t["id"],))["status"], 3)       # ویرایش، مسلط‌بودن را بازمحاسبه می‌کند
        sm_ = self.s.test_summary(m); self.assertEqual((sm_["sessions"], sm_["total"], sm_["correct"], sm_["wrong"], sm_["blank"], sm_["success"]), (2, 20, 12, 6, 2, 60))
        self.s.delete_test(rows[0]["id"]); self.assertEqual(self.s.test_summary(m)["sessions"], 1)
    def test_blank_topic_gets_default_name_and_legacy_rows(self):
        m = self.sid["ریاضی"]; self.s.add_test(m, "5", "", "practice", 4, 2, 1, 1, date.today()); self.assertEqual(self.s.tests_of(m)[0]["topic"], "کل فصل 5")
        t = self.s.save_topic(m, "", "قدیمی"); self.s.run("INSERT INTO quiz_logs(topic_id,kind,total,correct,date) VALUES(?,?,?,?,?)", (t, "exam", 10, 7, date.today().isoformat()))
        r = [x for x in self.s.tests_of(m) if x["topic"] == "قدیمی"][0]; self.assertEqual((r["wrong_n"], r["blank_n"]), (3, 0))
    def test_backup_roundtrip_includes_new_tables(self):
        m = self.sid["علوم"]; t = self.s.save_topic(m, "1", "x"); self.s.add_study(t, date.today(), 5, 20); self.s.add_goal(date.today(), "هدف"); self.s.save_note("a", "b", [], None, "work")
        text = self.s.backup_text(); self.s.clear_all(); self.s.restore_text(text)
        self.assertEqual((len(self.s.study_logs_of(t)), len(self.s.week_goals(date.today())), self.s.search_notes(category="work")[0]["title"]), (1, 1, "a"))

class TestGoalsNotesSeries(T):
    def test_goals(self):
        ws = date.today(); a = self.s.add_goal(ws, "الف"); self.s.add_goal(ws, "ب"); self.s.toggle_goal(a)
        self.assertEqual(self.s.goal_stats(ws), dict(total=2, done=1, pct=50)); self.s.update_goal(a, "ج"); self.s.delete_goal(a); self.assertEqual(self.s.goal_stats(ws)["total"], 1)
        with self.assertRaises(ValueError): self.s.add_goal(ws, "  ")
    def test_note_categories_pin_counts(self):
        a = self.s.save_note("t1", "b", [], None, "study"); self.s.save_note("t2", "b"); self.s.save_note("t3", "b", [], None, "zzz")   # دستهٔ نامعتبر → سایر
        self.assertEqual(self.s.note_counts(), {"personal": 0, "study": 1, "work": 0, "idea": 0, "other": 2})
        self.s.set_note_pinned(a, True); self.assertEqual(self.s.search_notes()[0]["id"], a); self.assertEqual(len(self.s.search_notes(category="study")), 1)
        self.s.save_note("t1", "bb", [], a, "idea"); self.assertEqual(self.s.note(a)["category"], "idea")
    def test_series_shapes_and_study_minutes(self):
        t = self.s.save_topic(self.sid["علوم"], "1", "x"); self.s.add_study(t, date.today(), 40, 50)
        for kind, n in (("day", 7), ("week", 8), ("month", 6)):
            ser = self.s.series(kind); self.assertEqual(len(ser), n, kind); self.assertEqual(sum(1 for x in ser if x["current"]), 1, kind); self.assertEqual(sum(x["minutes"] for x in ser), 40, kind)
        self.assertEqual(self.s.growth_pct(), 0)

class TestAssets(unittest.TestCase):
    def test_icons_and_headers_present_and_transparent(self):
        from PIL import Image
        for _, n in sm.DEFAULT_SUBJECTS:
            with Image.open(os.path.join(ROOT, "assets", "icons", n + ".png")) as im: self.assertEqual(im.mode, "RGBA"); self.assertEqual(im.getpixel((2, 2))[3], 0)     # گوشه شفاف است (پس‌زمینهٔ شطرنجی حذف شده)
        for n in ("study", "notes", "week", "progress"): self.assertGreater(os.path.getsize(os.path.join(ROOT, "assets", "headers", n + ".jpg")), 20000)

if __name__ == "__main__": unittest.main()
