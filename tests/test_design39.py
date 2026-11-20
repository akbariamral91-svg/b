# -*- coding: utf-8 -*-
"""نسخهٔ ۳٫۹: کامپوننت‌های تازهٔ سیستم طراحی و صفحه‌هایی که از آن‌ها استفاده می‌کنند."""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_flet as F
F.install()
import ui
from test_ui import UI, ERR


class TestComponents(unittest.TestCase):
    def test_group_puts_dividers_between_rows_only(self):
        rows = [ui.list_row("FLAG", f"ردیف {i}", "توضیح") for i in range(4)]
        g = ui.group(rows)
        col = F.find(g, "Column")[0]
        self.assertEqual(len(col.__dict__["_args"][0]), 4 + 3)             # ۴ ردیف + ۳ خط جداکننده
    def test_group_single_row_has_no_divider(self):
        g = ui.group([ui.list_row("FLAG", "تنها")]); self.assertEqual(len(F.find(g, "Column")[0]._args[0]), 1)
    def test_list_row_clickable_only_with_handler(self):
        self.assertFalse(ui.list_row("FLAG", "a").ink)
        self.assertTrue(ui.list_row("FLAG", "a", on_click=lambda e: None).ink)
    def test_step_dots_marks_current(self):
        row, set_ = ui.step_dots(3); dots = row._args[0]
        self.assertEqual([d.width for d in dots], [24, 8, 8])
        set_(2); self.assertEqual([d.width for d in dots], [8, 8, 24])
    def test_stat_tile_and_legend_build(self):
        self.assertIn("۳", F.all_text(ui.stat_tile("BOLT", "gold", "۳", "کار")))
        self.assertIn("بیشتر", F.all_text(ui.legend_scale()))
    def test_brand_mark(self): self.assertIsNotNone(ui.brand_mark(40))


class TestScreens39(UI):
    def test_stats_strip_removed_from_home(self):                    # جایش را کارت سطح و گزارش روز گرفته‌اند
        self.assertNotIn("ساعت برنامه‌ریزی‌شده", self.screen())
    def test_settings_groups_render_and_rows_are_tappable(self):
        gear = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("SETTINGS_OUTLINED"))[0]; gear.on_click(None); self.ok()
        rows = F.find(self.body(), "Container", lambda c: getattr(c, "ink", False) and getattr(c, "on_click", None) and "روتین‌ها و نماز" in F.all_text(c))
        self.assertTrue(rows); rows[0].on_click(None); self.ok(); self.assertIn("روتین", self.screen())
    def test_progress_has_heatmap_legend(self):
        self.go(4); self.assertIn("کمتر", self.screen()); self.ok()


class TestOnboardingDots(UI):
    onboarded = False
    def test_dots_follow_steps(self):
        d = self.dlg(); dots = [c for c in F.walk(d) if type(c).__name__ == "Container" and getattr(c, "width", None) in (8, 24) and getattr(c, "height", None) == 8]
        self.assertEqual([c.width for c in dots], [24, 8, 8])
        self.press("بعدی"); self.assertEqual([c.width for c in dots], [8, 24, 8])
        self.press("قبلی"); self.assertEqual([c.width for c in dots], [24, 8, 8])


if __name__ == "__main__": unittest.main()
