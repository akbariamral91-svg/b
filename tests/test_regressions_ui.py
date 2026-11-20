# -*- coding: utf-8 -*-
"""رگرسیون رابط (۴٫۱٫۱): فیلتر برچسبِ گیرکرده، کارت گزارش امروز، و قفل‌بودن روتینِ روزهای گذشته."""
import os, sys, tempfile, unittest
from datetime import date, datetime, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_flet as F
F.install()
import main as app
from store import Store

class UI(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); os.environ["FLET_APP_STORAGE_DATA"] = self.tmp.name
        pre = Store(os.path.join(self.tmp.name, "get_better.db")); pre.setpref("onboarded", "1"); self.seed(pre); pre.close()
        self.page = F.Page(); app.main(self.page); self.db = Store(os.path.join(self.tmp.name, "get_better.db"))
    def tearDown(self): self.db.db.close(); self.tmp.cleanup()
    def seed(self, s): pass
    def body(self): return self.page.views[-1].controls[0] if self.page.views else self.page.controls[0]
    def screen(self): return F.all_text(self.body())
    def go(self, i): F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == ("nav", i))[0].on_click(None)

class TestStuckTagFilter(UI):
    def seed(self, s): s.save_note("یادداشت یک", "متن", [])
    def test_stale_tag_filter_does_not_hide_all_notes(self):
        self.page.data["tag"] = "برچسب-حذف‌شده"; self.go(3)
        self.assertIn("یادداشت یک", self.screen()); self.assertIsNone(self.page.data["tag"])

class TestHomeReport(UI):
    def test_empty_day_report_says_no_plan_even_with_prayers(self):
        self.go(0); self.assertIn("روز بی‌برنامه‌ای است", self.screen())

class TestPastRoutineLocked(UI):
    def seed(self, s):
        s.ensure_day(date.today()); y = (date.today() - timedelta(days=1)).isoformat()
        s.run("UPDATE missions SET date=?,done=1,completed_at=? WHERE routine_id IS NOT NULL", (y, datetime.now().isoformat(timespec="seconds")))
    def test_done_prayers_of_a_past_day_are_not_tappable(self):
        self.page.data["day"] = (date.today() - timedelta(days=1)).isoformat(); self.go(0)
        discs = F.find(self.body(), "Container", lambda c: getattr(c, "width", None) == 44 and getattr(c, "height", None) == 44)
        self.assertTrue(discs)
        tiles = F.find(self.body(), "Container", lambda c: getattr(c, "expand", False) and getattr(c, "border_radius", None) == 16 and F.all_text(c) in ("صبح", "ظهر", "عصر", "مغرب", "عشا"))
        self.assertEqual(len(tiles), 5); self.assertTrue(all(getattr(t, "on_click", None) is None for t in tiles))

if __name__ == "__main__": unittest.main()
