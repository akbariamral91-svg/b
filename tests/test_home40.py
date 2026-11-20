# -*- coding: utf-8 -*-
"""طراحی ۴٫۰ صفحهٔ امروز: تصویر قهرمان سفارشی‌شدنی، دکمهٔ ＋ دایره‌ای، حذف حالت تمرکز از امروز، و دست‌نخوردگی بقیهٔ صفحه‌ها."""
import os, sys, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_flet as F
F.install()
from PIL import Image
import hero
from test_ui import UI, Ev, ERR
import main as app


def make_png(path, size=(900, 600), color=(200, 60, 90)):
    Image.new("RGB", size, color).save(path); return path

class HomeBase(UI):
    def hero_images(self): return F.find(self.body(), "Image")
    def open_hero_dialog(self):
        cam = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("PHOTO_CAMERA"))[0]; cam.on_click(None); return self.dlg()
    def picker(self): fp = self.page.overlay[0]; fp.pick_files = lambda **kw: None; return fp


class TestHomeLayout(HomeBase):
    def test_sections_present(self):
        s = self.screen()
        for t in ("بخیر", "سطح", "XP تا سطح", "مطالعهٔ هفته", "کارهای امروز", "نمازها", "گزارش عملکرد امروز", "هدف اصلی"): self.assertIn(t, s)
        self.ok()
    def test_default_hero_image_is_the_bundled_asset(self):
        imgs = self.hero_images(); self.assertTrue(imgs); self.assertEqual(imgs[0].src, hero.DEFAULT_SRC)
        self.assertTrue(os.path.getsize(os.path.join(ROOT, "assets", hero.DEFAULT_SRC)) > 20_000)
    def test_no_focus_mode_on_home(self):
        self.add = lambda: (self.fab().on_click(None), setattr(self.field("عنوان"), "value", "حل تمرین"), self.press("ذخیره")); self.add()
        self.assertEqual(F.find(self.body(), "IconButton", lambda c: c._args and "CENTER_FOCUS" in str(c._args[0])), [])
        self.assertNotIn("حالت تمرکز", self.screen())
    def test_focus_feature_still_exists(self):
        self.fab().on_click(None); self.field("عنوان").value = "x"; self.press("ذخیره")
        self.page.data["focus_open"](self.mine()[0]); self.assertIn("حالت تمرکز", F.all_text(self.dlg())); self.press("پایان و ذخیره")
    def test_task_card_shows_time_subject_priority_and_checks_off(self):
        self.fab().on_click(None); self.field("عنوان").value = "حل تمرین"; self.field("درس (اختیاری)").value = "فیزیک"; self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)").value = "16:30"; self.press("ذخیره")
        s = self.screen()
        for t in ("حل تمرین", "فیزیک", "۱۶:۳۰", "متوسط", "۰ از ۱"): self.assertIn(t, s)
        chk = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("RADIO_BUTTON_UNCHECKED") and getattr(c, "tooltip", "") == "انجام شد")[0]
        chk.on_click(None); self.assertIn("۱ از ۱", self.screen()); self.assertTrue(self.db.xp() > 0)
    def test_overdue_card_has_details(self):
        from datetime import date, timedelta
        self.db.save_mission("قدیمی", "", 30, 1, date.today() - timedelta(days=3)); self.go(1); self.go(0)
        s = self.screen(); self.assertIn("کار عقب‌افتاده", s); self.assertIn("قدیمی‌ترین", s)


class TestAddButton(HomeBase):
    def test_circle_on_home_pill_elsewhere_same_position(self):
        fab = self.fab(); self.assertEqual((fab.left, fab.bottom), (20, 92))
        self.assertEqual((fab.width, fab.height, fab.border_radius), (60, 60, 30)); self.assertFalse(F.find(fab, "Text")[0].visible)
        self.go(1); self.assertIsNone(fab.width); self.assertEqual(fab.border_radius, 22); self.assertTrue(F.find(fab, "Text")[0].visible); self.assertEqual((fab.left, fab.bottom), (20, 92))
        self.go(0); self.assertEqual(fab.width, 60)
    def test_still_opens_new_task_form_and_is_not_in_nav(self):
        self.fab().on_click(None); self.assertIn("کار یا ریزه‌کار جدید", F.all_text(self.dlg()))
        nav = [c for c in F.walk(self.body()) if getattr(c, "data", None) and isinstance(c.data, tuple) and c.data[0] == "nav"]
        self.assertEqual(len(nav), 5); self.assertFalse(any(F.find(n, "Container", lambda c: getattr(c, "data", None) == "fab") for n in nav))


class TestOtherScreensUntouched(HomeBase):
    def test_nav_items_unchanged(self):
        self.assertEqual([n[0] for n in app.NAV], ["خانه", "تحصیل", "هفته", "یادداشت‌ها", "پیشرفت"])      # ۴٫۱: ترتیب جدید ناوبری؛ «مرور» با «تحصیل» جایگزین شد
        self.assertEqual([n[1] for n in app.NAV], ["HOME", "SCHOOL", "CALENDAR_MONTH", "STICKY_NOTE_2", "INSIGHTS"])
    def test_topbar_hidden_only_on_home(self):
        top = None
        for c in F.walk(self.body()):
            if type(c).__name__ == "Container" and c._args and type(c._args[0]).__name__ == "Row" and "tab" not in c.__dict__ and getattr(c, "padding", None) is not None and "Get Better" in F.all_text(c) and "تنظیمات" not in F.all_text(c) and top is None and getattr(c, "visible", True) is False: top = c
        self.assertIsNotNone(top); self.go(1); self.assertFalse(top.visible)          # چهار صفحهٔ جدید هدر تصویری خودشان را دارند
        F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("SETTINGS_OUTLINED"))[0].on_click(None); self.assertTrue(top.visible)   # تنظیمات نوار بالا دارد
        self.go(0); self.assertFalse(top.visible)
    def test_other_tabs_have_no_hero(self):
        for i in (1, 2, 3, 4): self.go(i); self.assertEqual([x for x in self.hero_images() if x.src == hero.DEFAULT_SRC], []); self.ok()    # تصویر کوهنورد فقط در خانه


class TestHeroCustomization(HomeBase):
    def pick(self, path):
        d = self.open_hero_dialog(); fp = self.picker(); self.gallery(d); fp.on_result(Ev(files=[Ev(path=path)])); return d, fp
    def gallery(self, d): [c for c in F.walk(d) if type(c).__name__ == "ElevatedButton"][0].on_click(None)
    def test_pick_preview_save_persists_across_restart(self):
        src = make_png(os.path.join(self.tmp.name, "mine.png")); d, fp = self.pick(src)
        self.assertTrue(any(i.src_base64 for i in F.find(d, "Image") if getattr(i, "src_base64", None)))     # پیش‌نمایش
        self.assertIsNone(self.db.pref("hero_file") or None)                                                    # هنوز ذخیره نشده
        sl = F.find(d, "Slider")[0]; sl.on_change(Ev(control=Ev(value=.8))); self.press("ذخیره")
        name = self.db.pref("hero_file"); self.assertTrue(name.startswith("hero_")); self.assertEqual(self.db.pref("hero_pos"), "0.80")
        self.assertTrue(os.path.isfile(os.path.join(self.tmp.name, name)))
        main_img = self.hero_images()[0]; self.assertTrue(main_img.src_base64); self.assertLess(main_img.top, -50)      # موقعیت ۰٫۸ → تصویر بالاتر رفته
        page2 = F.Page(); app.main(page2)                                                                        # «بستن و باز کردن» برنامه
        v = page2.views[-1].controls[0] if page2.views else page2.controls[0]
        self.assertTrue(any(getattr(i, "src_base64", None) for i in F.find(v, "Image")))
    def test_large_photo_is_downscaled(self):
        src = make_png(os.path.join(self.tmp.name, "big.png"), (4000, 3000)); name = hero.import_image(src)
        with Image.open(os.path.join(self.tmp.name, name)) as im: self.assertLessEqual(max(im.size), hero.MAX_SIDE)
    def test_reset_restores_default_and_removes_file(self):
        self.pick(make_png(os.path.join(self.tmp.name, "a.png"))); self.press("ذخیره"); name = self.db.pref("hero_file")
        d = self.open_hero_dialog(); self.press("تصویر پیش‌فرض"); self.press("ذخیره")
        self.assertEqual(self.db.pref("hero_file"), ""); self.assertFalse(os.path.exists(os.path.join(self.tmp.name, name))); self.assertEqual(self.hero_images()[0].src, hero.DEFAULT_SRC)
    def test_cancel_keeps_previous_image(self):
        self.pick(make_png(os.path.join(self.tmp.name, "a.png"))); self.press("انصراف"); self.assertFalse(self.db.pref("hero_file"))
        self.assertEqual(self.hero_images()[0].src, hero.DEFAULT_SRC)
    def test_bad_file_is_graceful(self):
        bad = os.path.join(self.tmp.name, "bad.png"); open(bad, "wb").write(b"not an image")
        self.pick(bad); self.assertTrue(self.page.snacks); self.assertFalse(self.db.pref("hero_file")); self.ok()
        txt_ = os.path.join(self.tmp.name, "x.txt"); open(txt_, "w").write("hi")
        with self.assertRaises(hero.HeroError): hero.import_image(txt_)
    def test_missing_saved_file_falls_back_to_default(self):
        self.pick(make_png(os.path.join(self.tmp.name, "a.png"))); self.press("ذخیره"); os.remove(os.path.join(self.tmp.name, self.db.pref("hero_file")))
        self.go(1); self.go(0); self.assertEqual(self.hero_images()[0].src, hero.DEFAULT_SRC); self.ok()
    def test_picker_cancel_and_failure(self):
        d = self.open_hero_dialog(); fp = self.picker(); self.gallery(d); fp.on_result(Ev(files=None)); fp.on_result(Ev(files=[]))
        def boom(**kw): raise RuntimeError("x")
        fp.pick_files = boom; self.gallery(d); self.assertTrue(self.page.snacks)


if __name__ == "__main__": unittest.main()
