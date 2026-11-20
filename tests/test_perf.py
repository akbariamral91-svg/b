# -*- coding: utf-8 -*-
"""روانی لمس: بازخورد فوری، ادغام رندرهای هم‌زمان، پاک‌سازی overlay و مهار انیمیشن‌های بی‌پایان."""
import os, sys, threading, time, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_flet as F
F.install()
import ui
from test_ui import UI


class FakePage:
    def __init__(self): self.calls = []
    def update(self, *c): self.calls.append(c)

class Box:
    def __init__(self): self.value = 0
    def update(self): pass


class TestInstantFeedback(UI):
    def add(self, title="تمرین"):
        self.fab().on_click(None); self.field("عنوان").value = title; self.press("ذخیره")

    def check(self, kind):
        return F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith(kind))[0]

    def test_check_flips_before_render_and_db_follows(self):
        self.add(); chk = self.check("RADIO_BUTTON_UNCHECKED"); chk.on_click(None)
        self.assertTrue(str(chk.icon).startswith("CHECK_CIRCLE"))             # همان کنترل قدیمی فوراً تیک خورد
        self.assertEqual(self.mine()[0]["done"], 1); self.ok()
        self.assertIsNone(self.page.data.get("pop"))                           # جهش روی خود کنترل بود؛ رندر دوباره تکرارش نمی‌کند

    def test_uncheck_flips_back(self):
        self.add(); self.check("RADIO_BUTTON_UNCHECKED").on_click(None)
        done = self.check("CHECK_CIRCLE"); done.on_click(None)
        self.assertTrue(str(done.icon).startswith("RADIO_BUTTON_UNCHECKED")); self.assertEqual(self.mine()[0]["done"], 0)

    def test_double_tap_on_stale_control_stays_consistent(self):
        self.add(); chk = self.check("RADIO_BUTTON_UNCHECKED")
        chk.on_click(None); chk.on_click(None)                                  # دو لمس روی همان کنترلِ قدیمی (پیش از بازسازی)
        self.assertEqual(self.mine()[0]["done"], 0)                            # دیتابیس دو بار برگشت
        self.assertTrue(str(chk.icon).startswith("RADIO_BUTTON_UNCHECKED"))   # و بازخورد فوری هم‌جهت است

    def test_toggle_snack_comes_after_render(self):
        self.add(); order = []
        orig_update = self.page.update
        self.page.update = lambda *a: (order.append("update"), orig_update(*a))[1]
        orig_open = self.page.open
        self.page.open = lambda c: (order.append(type(c).__name__), orig_open(c))[1]
        self.check("RADIO_BUTTON_UNCHECKED").on_click(None)
        self.assertIn("SnackBar", order)
        self.assertLess(order.index("update"), order.index("SnackBar"))        # نتیجه روی صفحه، بعد پیام

    def test_prayer_toggle_still_works_with_instant_flip(self):
        items = F.find(self.body(), "Container", lambda c: getattr(c, "ink", False) and getattr(c, "expand", False) and "صبح" in F.all_text(c))
        items[0].on_click(None); self.ok()
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM missions WHERE done=1 AND routine_id IS NOT NULL")["n"], 1)

    def test_nav_highlights_before_page_is_built(self):
        seen = []
        orig = self.page.update
        def spy(*c):
            if c: seen.append(len(c))
            return orig(*c)
        self.page.update = spy
        self.go(2); self.assertTrue(seen and seen[0] >= 5)                      # همهٔ ۵ آیتم نوار پایین با یک پیام فوری
        self.ok()


class TestRenderCoalescing(UI):
    def test_concurrent_taps_do_not_queue_full_rebuilds(self):
        full = []; orig = self.page.update
        def slow(*c):
            if not c: full.append(1); time.sleep(.04)
            return orig(*c)
        self.page.update = slow
        ts = [threading.Thread(target=lambda i=i: self.go(i % 2)) for i in range(10)]
        for t in ts: t.start()
        for t in ts: t.join()
        self.assertGreaterEqual(len(full), 1); self.assertLess(len(full), 10)
        text = self.screen(); self.ok()
        self.assertTrue(("برنامه و پیگیری دروس" in text) if self.page.data["tab"] == 1 else ("بخیر" in text))   # صفحهٔ نهایی با آخرین وضعیت ساخته شده

    def test_sequential_renders_still_run_every_time(self):
        n = []; orig = self.page.update
        self.page.update = lambda *c: (n.append(1) if not c else None, orig(*c))[1]
        for _ in range(3): self.go(0)
        self.assertEqual(len(n), 3)


class TestOverlayTidy(UI):
    def test_old_closed_dialogs_are_dropped_but_filepicker_stays(self):
        AD = F._cls("AlertDialog"); dead = [AD(open=False) for _ in range(6)]; live = AD(open=True)
        keep_before = [c for c in self.page.overlay]
        self.page.overlay.extend(dead + [live])
        self.go(4); self.fab().on_click(None)                                   # بدون درس: اسنک‌بار باز می‌شود → پاک‌سازی
        closed = [c for c in self.page.overlay if type(c).__name__ == "AlertDialog" and c.open is False]
        self.assertLessEqual(len(closed), 3); self.assertIn(live, self.page.overlay)
        for c in keep_before: self.assertIn(c, self.page.overlay)               # FilePicker و بقیه دست‌نخورده
        self.assertEqual(closed, dead[-len(closed):])                           # فقط قدیمی‌ترین‌ها رفتند


class TestMotionHold(unittest.TestCase):
    def test_ambient_waits_while_held_and_resumes(self):
        m = ui.Motion(); m.page = FakePage(); b = Box(); held = {"on": True}
        m.hold = lambda: held["on"]; m.ambient(lambda tick: b)
        m.flush(); time.sleep(.3); self.assertEqual(m.page.calls, [])
        held["on"] = False; time.sleep(.8); self.assertTrue(m.page.calls)
        m.reset(); m.flush()

    def test_ambient_starts_after_entrance_tweens(self):
        m = ui.Motion(); m.page = FakePage(); b = Box(); ticks = []
        m.ambient(lambda tick: ticks.append(tick)); m.tween(lambda v: setattr(b, "value", v), 0, 5, .2, ctrl=b)
        m.flush(); time.sleep(.5); self.assertEqual(ticks, [])                  # هنوز ورود/پر شدن در جریان است
        time.sleep(1.3); self.assertTrue(ticks); self.assertEqual(b.value, 5)
        m.reset(); m.flush()

    def test_hold_errors_never_break_motion(self):
        m = ui.Motion(); m.page = FakePage(); b = Box()
        def boom(): raise RuntimeError("x")
        m.hold = boom; m.ambient(lambda tick: b); m.flush(); time.sleep(.3)
        self.assertTrue(m.page.calls)
        m.reset(); m.flush()


if __name__ == "__main__": unittest.main()
