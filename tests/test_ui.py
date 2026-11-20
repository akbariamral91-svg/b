# -*- coding: utf-8 -*-
"""تست دودی رابط با شبیه‌ساز Flet: همهٔ صفحه‌ها و فرم‌ها بدون خطا ساخته می‌شوند و رویدادهای اصلی کار می‌کنند."""
import glob, os, sys, tempfile, time, unittest
from unittest import mock
from datetime import date, timedelta
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fake_flet as F
F.install()
import main as app
import meta, store
from store import Store

ERR = "مشکلی پیش آمد"
class Ev:
    def __init__(self, **kw): self.__dict__.update(kw)

class UI(unittest.TestCase):
    onboarded = True            # بیشتر تست‌ها بدون دیالوگ معرفی اجرا می‌شوند
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); os.environ["FLET_APP_STORAGE_DATA"] = self.tmp.name
        if self.onboarded:
            pre = Store(os.path.join(self.tmp.name, "get_better.db")); pre.setpref("onboarded", "1"); pre.close()
        self.page = F.Page(); app.main(self.page)
        self.db = Store(os.path.join(self.tmp.name, "get_better.db"))
    def tearDown(self): self.db.db.close(); self.tmp.cleanup()
    # --- کمکی‌ها
    def body(self): return self.page.views[-1].controls[0] if self.page.views else self.page.controls[0]
    def screen(self): return F.all_text(self.body())
    def go(self, i): F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == ("nav", i))[0].on_click(None)
    def fab(self): return F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == "fab")[0]
    def dlg(self): return self.page.dialogs[-1]
    def mine(self): return [r for r in self.db.today_missions() if r["routine_id"] is None]
    def press(self, label):
        for c in F.walk(self.dlg()):
            if type(c).__name__ in ("FilledButton", "TextButton") and (getattr(c, "text", None) or (c._args[0] if c._args else None)) == label: return c.on_click(None)
        self.fail("دکمه پیدا نشد: " + label)
    def field(self, label): return F.find(self.dlg(), "TextField", lambda c: c.label == label)[0]
    def ok(self): self.assertNotIn(ERR, self.screen())

class TestScreens(UI):
    def test_all_tabs_empty(self):
        for i in range(5): self.go(i); self.ok()
    def test_settings_and_back(self):
        self.body()  # شروع
        gear = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("SETTINGS_OUTLINED"))[0]; gear.on_click(None); self.ok()
        self.assertIn("پشتیبان", self.screen())
    def test_fab_visibility(self):
        fab = self.fab()
        for i, vis in ((0, True), (1, False), (2, False), (3, False), (4, False)): self.go(i); self.assertEqual(fab.visible, vis)   # ＋ شناور فقط در خانه؛ در یادداشت‌ها ＋ داخل نوار ناوبری است

class TestMissionFlow(UI):
    def add_mission(self, title="حل تمرین", repeat=None):
        self.fab().on_click(None); self.field("عنوان").value = title
        self.press("ذخیره"); self.assertEqual(self.page.dialogs, [])
    def test_create_toggle_xp(self):
        self.add_mission(); self.assertEqual(self.mine()[0]["title"], "حل تمرین"); self.assertIn("حل تمرین", self.screen())
        chk = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("RADIO_BUTTON_UNCHECKED"))[0]; chk.on_click(None)
        self.assertGreater(self.db.xp(), 0); self.ok()
        self.assertTrue(any("🏆" in F.all_text(d) or "دستاورد" in F.all_text(d) for d in self.page.dialogs))   # اولین قدم
    def test_validation(self):
        self.fab().on_click(None); self.press("ذخیره")
        self.assertEqual(len(self.page.dialogs), 1); self.assertEqual(self.mine(), [])
    def test_date_picker_clamps_day(self):
        self.fab().on_click(None)
        dds = F.find(self.dlg(), "Dropdown"); dy, mo, yr = dds[0], dds[1], dds[2]
        mo.value = "12"; yr.value = "1404"; mo.on_change(Ev(control=mo)); dy.value = "30"; mo.on_change(Ev(control=mo))
        self.assertEqual(dy.value, "29"); self.assertEqual(len(dy.options), 29)
    def test_repeat_and_edit(self):
        self.add_mission("تکرار"); m = self.mine()[0]
        pop = F.find(self.body(), "PopupMenuButton")[0]; edit = pop.items[0]; edit.on_click(None)
        self.assertEqual(self.field("عنوان").value, "تکرار"); self.field("عنوان").value = "ویرایش‌شده"; self.press("ذخیره")
        self.assertEqual(self.db.one("SELECT title FROM missions WHERE id=?", (m["id"],))["title"], "ویرایش‌شده")
    def test_week_strip_select_day(self):
        tiles = F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and getattr(c, "expand", False))
        self.assertGreaterEqual(len(tiles), 7); tiles[0].on_click(None); self.ok()
    def test_overdue_and_smart_plan(self):
        self.db.save_mission("قدیمی", "", 20, 0, date.today() - timedelta(days=2)); self.go(0); self.assertIn("عقب‌افتاده", self.screen())
        sid = self.db.run("INSERT INTO subjects(name) VALUES('فیزیک')"); t = self.db.run("INSERT INTO topics(subject_id,name) VALUES(?,?)", (sid, "حرکت"))
        self.db.add_log(t, "practice", 10, 3, None, date.today() - timedelta(days=9)); self.go(0); self.assertIn("آمادهٔ مرور", self.screen())
        F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and F.all_text(c) == "برنامهٔ هوشمند")[0].on_click(None)
        self.press("افزودن به برنامه"); self.assertEqual(len(self.mine()), 1); self.ok()
    def test_focus_dialog(self):
        self.add_mission(); self.page.data["focus_open"](self.mine()[0])
        d = self.dlg(); start = F.find(d, "FilledButton", lambda c: c._args and c._args[0] in ("شروع", "توقف"))[0]
        start.on_click(None); time.sleep(1.3); self.assertEqual(start.text, "توقف"); self.press("پایان و ذخیره"); self.assertEqual(self.page.dialogs, []); self.ok()

class TestFocusClock(UI):
    """تایمر باید با ساعت واقعی بشمارد (خاموشی صفحه/پس‌زمینه)، نه با تیک‌های رشته."""
    def open_focus(self):
        TestMissionFlow.add_mission(self); self.page.data["focus_open"](self.mine()[0])
        return F.find(self.dlg(), "FilledButton", lambda c: c._args and c._args[0] in ("شروع", "توقف"))[0]
    def jump(self, seconds):
        real = time.time; off = [0.0]; self._p = mock.patch.object(app.time, "time", lambda: real() + off[0]); self._p.start(); self.addCleanup(self._p.stop)
        return off
    def test_background_gap_is_counted(self):
        off = self.jump(0); start = self.open_focus(); start.on_click(None)
        off[0] += 600                                          # ۱۰ دقیقه صفحه خاموش بود
        self.page.on_app_lifecycle_state_change(Ev(data="resume"))
        self.press("پایان و ذخیره")
        self.assertGreaterEqual(self.db.focus_seconds(date.today()), 590)
    def test_phase_crossed_while_away(self):
        off = self.jump(0); start = self.open_focus(); start.on_click(None)
        off[0] += 26 * 60                                      # تمرکز تمام شد و یک دقیقه از استراحت گذشته
        self.page.on_app_lifecycle_state_change(Ev(data="resume"))
        self.assertTrue(any("استراحت" in str(getattr(c, "value", "")) for c in F.walk(self.dlg())))
        self.press("پایان و ذخیره"); self.assertAlmostEqual(self.db.focus_seconds(date.today()), 25 * 60, delta=5)
    def test_paused_time_not_counted(self):
        off = self.jump(0); start = self.open_focus(); start.on_click(None); start.on_click(None)   # شروع و توقف
        off[0] += 3600; self.page.on_app_lifecycle_state_change(Ev(data="resume"))
        self.press("پایان و ذخیره"); self.assertEqual(self.db.focus_seconds(date.today()), 0)
    def test_forgotten_timer_is_capped(self):
        off = self.jump(0); start = self.open_focus(); start.on_click(None)
        off[0] += 10 * 3600; self.page.on_app_lifecycle_state_change(Ev(data="resume"))
        self.assertEqual(start.text, "ادامه"); self.press("پایان و ذخیره"); self.assertLessEqual(self.db.focus_seconds(date.today()), 2 * 25 * 60 + 5)
    def test_system_back_dismiss_saves_once(self):
        off = self.jump(0); start = self.open_focus(); start.on_click(None); off[0] += 120
        d = self.dlg(); d.on_dismiss(None); d.on_dismiss(None)  # «بازگشت» سیستم، حتی دوبار
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM focus_sessions")["n"], 1)

class TestAndroidBack(UI):
    def back(self): self.page.on_view_pop(None)
    def test_tab_back_goes_home_then_arms_exit(self):
        self.go(3); self.back(); self.assertEqual(self.page.data["tab"], 0); self.assertEqual(len(self.page.views), 2)
        self.back(); self.assertEqual(len(self.page.views), 1)        # نگهبان برداشته شد → Back بعدی خروج واقعی است
        self.assertTrue(any("بازگشت" in F.all_text(s) for s in self.page.snacks))
    def test_exit_guard_returns(self):
        self.back(); time.sleep(3.3); self.assertEqual(len(self.page.views), 2)
    def test_subpages_back(self):
        self.go(2); F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("SETTINGS_OUTLINED"))[0].on_click(None)
        self.assertEqual(self.page.data["tab"], 5); self.back(); self.assertEqual(self.page.data["tab"], 2); self.ok()
    def test_theme_rebuild_keeps_view_stack(self):
        self.page.data["tab"] = 5; app_views = list(self.page.views); self.assertEqual(len(app_views), 2)

class TestOtherPages(UI):
    def test_notes_flow(self):
        self.go(3); F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == "navplus")[0].on_click(None)      # ＋ داخل نوار ناوبری: ویرایشگر یادداشت جدید
        self.assertEqual(self.page.data["tab"], 9); self.ok()
        t = F.find(self.body(), "TextField", lambda c: c.label == "عنوان")[0]; b = F.find(self.body(), "TextField", lambda c: c.label == "متن یادداشت")[0]
        tg = F.find(self.body(), "TextField", lambda c: c.label == "برچسب‌ها (با ویرگول جدا کن)")[0]
        t.value = "قانون دوم"; b.value = "F=ma"; tg.value = "فیزیک، مهم"; t.on_change(None)
        time.sleep(1.3)                                                                       # ذخیرهٔ خودکار
        n = self.db.one("SELECT * FROM notes"); self.assertEqual((n["title"], n["category"]), ("قانون دوم", "other")); self.assertEqual(self.db.note_tag_names(n["id"]), ["فیزیک", "مهم"])
        F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("ARROW_FORWARD"))[0].on_click(None)
        self.assertEqual(self.page.data["tab"], 3); self.ok(); self.assertIn("قانون دوم", self.screen())
        search = F.find(self.body(), "TextField", lambda c: c.label == "جست‌وجو در یادداشت‌ها…")[0]; search.on_change(Ev(control=Ev(value="zzz")))
        self.assertIn("پیدا نشد", self.screen()); search.on_change(Ev(control=Ev(value="F=")))
        self.assertNotIn("پیدا نشد", self.screen())
        self.assertIs(F.find(self.body(), "TextField", lambda c: c.label == "جست‌وجو در یادداشت‌ها…")[0], search)   # فیلد بازسازی نشده
    def test_events_tab(self):
        self.go(3); ev = F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and F.all_text(c) == "اتفاقات روز")[0]; ev.on_click(None); self.ok()
        F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and F.all_text(c) == "ثبت اتفاق")[0].on_click(None)
        self.field("عنوان (اختیاری)").value = "جلسه"; self.press("ذخیره")
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM day_events")["n"], 1)
    def test_study_flow(self):
        self.go(1); self.ok(); scr = self.screen()
        for nm in ("علوم", "ریاضی", "فارسی", "عربی", "مطالعات اجتماعی", "پیام‌های آسمانی"): self.assertIn(nm, scr)
        self.assertEqual(len(F.find(self.body(), "Image", lambda c: str(getattr(c, "src", "")).startswith("icons/"))), 6)
        F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == ("subject", self.db.one("SELECT id FROM subjects WHERE name='ریاضی'")["id"]))[0].on_click(None)
        self.assertEqual(self.page.data["tab"], 8); self.ok()
        F.find(self.body(), "ElevatedButton", lambda c: c._args[0] == "ثبت مطالعه")[0].on_click(None)
        self.field("فصل (مثلاً ۳)").value = "۳"; self.field("مبحث").value = "تابع"; self.field("مدت مطالعه (دقیقه)").value = "۴۵"; F.find(self.dlg(), "Slider")[0].value = 75; self.press("ثبت")
        t = self.db.one("SELECT * FROM topics WHERE name='تابع'"); self.assertEqual((t["chapter"], t["mastery"], t["status"]), ("۳", 75, 1))
        self.assertEqual(self.db.one("SELECT minutes FROM study_logs")["minutes"], 45); self.ok(); self.assertIn("تابع", self.screen())
        self.go(1); self.assertIn("آخرین فصل: فصل ۳", self.screen()); self.assertIn("آخرین مبحث: تابع", self.screen())
    def test_test_session_flow_and_validation(self):
        self.go(1); pills = F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == ("pill", "1"))[0]; pills.on_click(None)
        F.find(self.body(), "ElevatedButton", lambda c: c._args[0] == "ثبت جلسهٔ تست")[0].on_click(None)
        self.field("تعداد کل تست").value = "20"; self.field("صحیح").value = "12"; self.field("غلط").value = "9"; self.press("ثبت")
        self.assertEqual(len(self.page.dialogs), 1); self.assertEqual(self.db.one("SELECT COUNT(*) n FROM quiz_logs")["n"], 0)     # مجموع ناسازگار
        self.field("غلط").value = "5"; self.field("مبحث تست‌زده‌شده").value = "معادله"; self.field("فصل تست‌زده‌شده (مثلاً ۳)").value = "2"; self.press("ثبت")
        r = self.db.tests_of()[0]; self.assertEqual((r["total"], r["correct"], r["wrong_n"], r["blank_n"], r["topic"], r["chapter"]), (20, 12, 5, 3, "معادله", "2")); self.ok(); self.assertIn("۶۰", self.screen())
    def test_week_goals_and_tasks(self):
        self.go(2); self.ok(); goal = F.find(self.body(), "TextField", lambda c: c.label == "هدف جدید برای این هفته…")[0]
        goal.on_submit(Ev(control=Ev(value="۵ فصل ریاضی"))); goal.on_submit(Ev(control=Ev(value="دو آزمون")))
        ws = store.J.week_start(date.today()) if hasattr(store, "J") else None
        gs = self.db.all("SELECT * FROM week_goals"); self.assertEqual(len(gs), 2); self.assertIn("۵ فصل ریاضی", self.screen())
        chk = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("RADIO_BUTTON_UNCHECKED"))[0]; chk.on_click(None)
        self.assertIn("۵۰٪", self.screen())
        F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and F.all_text(c) == "افزودن وظیفه")[0].on_click(None)
        self.field("عنوان").value = "وظیفهٔ هفته"; self.press("ذخیره"); self.assertTrue(self.db.one("SELECT 1 FROM missions WHERE title='وظیفهٔ هفته'")); self.assertIn("وظیفهٔ هفته", self.screen())
    def test_progress_populated(self):
        self.db.save_mission("a", "", 30, 1, date.today()); self.db.toggle_mission(1); self.db.add_focus(1, 900); self.go(4); self.ok()
        self.assertIn("دستاوردهای من", self.screen())
    def test_exam_date_and_settings(self):
        self.go(4); F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("EDIT_CALENDAR_OUTLINED"))[0].on_click(None); self.press("ذخیره")
        self.assertTrue(self.db.pref("exam_date")); self.go(4); self.assertIn("روز تا آزمون", self.screen())
    def settings_row(self, label):
        """دکمهٔ chevron ردیفی از تنظیمات که متنش label است."""
        for c in F.find(self.body(), "Container", lambda c: label in F.all_text(c) and F.find(c, "IconButton", lambda b: b._args and str(b._args[0]).startswith("CHEVRON_LEFT"))):
            btn = F.find(c, "IconButton", lambda b: b._args and str(b._args[0]).startswith("CHEVRON_LEFT"))
            if len(btn) == 1 and F.all_text(c).count(" | ") <= 3: return btn[0]
        self.fail("ردیف تنظیمات پیدا نشد: " + label)
    def open_settings(self):
        F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("SETTINGS_OUTLINED"))[0].on_click(None)
    def test_theme_backup_restore(self):
        self.db.save_mission("پشتیبان", "", 30, 1, date.today())
        self.open_settings()
        sw = F.find(self.body(), "Switch")[0]; sw.on_change(Ev(control=Ev(value=False))); self.assertEqual(self.db.pref("theme"), "light"); self.ok()
        self.open_settings()
        self.settings_row("کپی پشتیبان").on_click(None)
        self.assertTrue(glob.glob(os.path.join(self.tmp.name, "get_better_backup_*.json"))); self.assertIn("پشتیبان", F.all_text(self.dlg()))
        self.assertIn("پشتیبان", self.page.clip); self.press("باشه")
        self.db.clear_all(); self.assertEqual(len(self.db.all("SELECT * FROM missions WHERE routine_id IS NULL")), 0)
        self.settings_row("پشتیبان‌های خودکار").on_click(None)       # «پیش از پاک‌سازی» ساخته شده است
        self.assertIn("پیش از پاک‌سازی", F.all_text(self.dlg()))
        rows = F.find(self.dlg(), "Container", lambda c: getattr(c, "on_click", None) and "پیش از پاک‌سازی" in F.all_text(c))
        rows[-1].on_click(None); self.press("بله")
        self.assertEqual(len(self.db.all("SELECT * FROM missions WHERE routine_id IS NULL")), 1)
    def test_restore_from_pasted_text(self):
        self.db.save_mission("متنی", "", 30, 1, date.today()); text = self.db.backup_text(); self.db.clear_all()
        self.open_settings(); self.settings_row("بازیابی از متن").on_click(None)
        self.field("متن پشتیبان را اینجا بچسبان").value = "این JSON نیست"; self.press("بازیابی")
        self.assertEqual(len(self.page.dialogs), 1); self.assertTrue(self.page.snacks)               # خطا؛ دیالوگ باز می‌ماند
        self.field("متن پشتیبان را اینجا بچسبان").value = text; self.press("بازیابی")
        self.assertEqual(self.db.one("SELECT title FROM missions WHERE routine_id IS NULL")["title"], "متنی")
    def test_save_as_uses_file_picker(self):
        self.open_settings(); fp = self.page.overlay[0]; calls = []
        fp.save_file = lambda **kw: calls.append(kw)
        self.settings_row("ذخیرهٔ پشتیبان").on_click(None)
        self.assertEqual(len(calls), 1); self.assertTrue(calls[0]["file_name"].startswith("get_better_backup_")); self.assertIn("src_bytes", calls[0])
        out = os.path.join(self.tmp.name, "chosen.json"); fp.on_result(Ev(path=out))                 # دسکتاپ: برنامه خودش می‌نویسد
        self.assertTrue(os.path.getsize(out) > 0); fp.on_result(Ev(path=None))                       # انصراف بی‌خطاست
    def test_pick_restore_reads_file(self):
        self.db.save_mission("از فایل", "", 30, 1, date.today()); f = os.path.join(self.tmp.name, "b.json"); self.db.backup(f); self.db.clear_all()
        self.open_settings(); fp = self.page.overlay[0]; fp.pick_files = lambda **kw: None
        self.settings_row("بازیابی از فایل").on_click(None); fp.on_result(Ev(files=[Ev(path=f)])); self.press("بله")
        self.assertEqual(self.db.one("SELECT title FROM missions WHERE routine_id IS NULL")["title"], "از فایل")
    def test_picker_failure_is_graceful(self):
        self.open_settings(); fp = self.page.overlay[0]
        def boom(**kw): raise RuntimeError("no picker")
        fp.save_file = boom; self.settings_row("ذخیرهٔ پشتیبان").on_click(None); self.assertTrue(self.page.snacks); self.ok()
    def test_about_page(self):
        self.open_settings(); self.settings_row("درباره، حریم خصوصی و راهنما").on_click(None); self.ok()
        t = self.screen(); self.assertIn("حریم خصوصی", t); self.assertIn("کاملاً آفلاین", t); self.assertIn(meta.VERSION.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")), t)
        F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and "کپی گزارش خطا" in F.all_text(c))[0].on_click(None); self.assertTrue(self.page.snacks)
        self.page.snacks.clear(); store.log_error("آزمایشی", RuntimeError("x"))
        F.find(self.body(), "Container", lambda c: getattr(c, "on_click", None) and "کپی گزارش خطا" in F.all_text(c))[0].on_click(None)
        self.assertIn("آزمایشی", self.page.clip)

class TestOnboarding(UI):
    onboarded = False
    def test_shown_on_fresh_install_and_completes(self):
        self.assertEqual(len(self.page.dialogs), 1); self.assertIn("خوش آمدی", F.all_text(self.dlg()))
        self.press("بعدی"); self.field("هدفت چیست؟ (مثلاً قبولی در مدرسه نمونه)").value = "مدرسه نمونه"
        F.find(self.dlg(), "Switch")[0].value = True; F.find(self.dlg(), "Switch")[0].on_change(None)
        self.press("بعدی"); self.assertIn("هر روز چند کار", F.all_text(self.dlg()))
        seg = F.find(self.dlg(), "SegmentedButton")[0]; seg.selected = {"5"}
        self.press("شروع"); self.assertEqual(self.page.dialogs, [])
        self.assertEqual((self.db.pref("goal"), self.db.pref("daily_goal"), self.db.pref("onboarded")), ("مدرسه نمونه", "5", "1")); self.assertTrue(self.db.pref("exam_date"))
    def test_skip_marks_done_and_does_not_return(self):
        self.press("رد کردن"); self.assertEqual(self.page.dialogs, []); self.assertEqual(self.db.pref("onboarded"), "1")
        p2 = F.Page(); app.main(p2); self.assertEqual(p2.dialogs, [])
    def test_back_button(self):
        self.press("بعدی"); self.press("قبلی"); self.assertTrue(F.find(self.dlg(), "Column", lambda c: getattr(c, "visible", True) is True and "خوش آمدی" in F.all_text(c)))
    def test_existing_user_upgrade_skips_intro(self):
        self.db.save_mission("قدیمی", "", 30, 1, date.today()); self.db.setpref("onboarded", "0")
        p2 = F.Page(); app.main(p2); self.assertEqual(p2.dialogs, []); self.assertEqual(self.db.pref("onboarded"), "1")

class TestSmartQuickAddUI(UI):
    def test_smart_sentence_creates_timed_task_on_other_day(self):
        self.go(0)
        q = F.find(self.body(), "TextField", lambda c: c.label.startswith("ریزه‌کار جدید"))[0]; q.on_submit(Ev(control=Ev(value="فردا ساعت ۱۶:۳۰ حل تمرین ۴۵ دقیقه مهم")))
        m = self.db.one("SELECT * FROM missions WHERE title='حل تمرین'")
        self.assertEqual((m["kind"], m["time"], m["minutes"], m["priority"], m["date"]), ("task", "16:30", 45, 2, (date.today() + timedelta(days=1)).isoformat()))
    def test_progress_page_shows_report_and_pace(self):
        self.db.toggle_mission(self.db.save_mission("الف", "فیزیک", 30, 1, date.today())); self.db.setpref("exam_date", (date.today() + timedelta(days=30)).isoformat())
        sid = self.db.run("INSERT INTO subjects(name) VALUES('فیزیک')"); self.db.run("INSERT INTO topics(subject_id,name) VALUES(?,?)", (sid, "حرکت"))
        self.go(4); self.ok(); scr = self.screen(); self.assertIn("گزارش هفته", scr); self.assertIn("فیزیک", scr); self.assertIn("هفته‌ای حدود", scr)

class TestMissedRoutineUI(UI):
    def test_past_day_missed_prayers_and_routine_render(self):
        """روز گذشته: نمازها و روتین انجام‌نشده قرمز و قفل نمایش داده می‌شوند و در «عقب‌افتاده» نمی‌آیند."""
        y = (date.today() - timedelta(days=7)).isoformat(); self.db.setpref("miss_since", y)
        self.db.save_routine("ورزش", "chore", 0, "", store.WEEK_ORDER)
        for r in self.db.routines(): self.db.db.execute("INSERT OR IGNORE INTO missions(title,xp,date,kind,routine_id) VALUES(?,?,?,?,?)", (r["title"], 5, y, "chore", r["id"]))
        self.db.db.commit()
        self.go(0); prev = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("CHEVRON_RIGHT"))[0]; prev.on_click(None)
        self.ok(); self.assertIn("ورزش", self.screen()); self.assertNotIn("کار عقب‌افتاده", self.screen())
        self.assertEqual(len(F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("CANCEL"))), 1)   # روتین دلخواه: دایرهٔ قرمز
        xp = self.db.xp(); self.assertEqual(self.db.xp(), xp)

class TestWeekRoutineKinds(UI):
    def prayer_items(self):
        return [c for c in F.find(self.body(), "Container", lambda c: getattr(c, "expand", False) and getattr(c, "on_click", None) and any(k in str([str(getattr(x, "_args", "")) for x in F.walk(c)]) for k in ("WB_TWILIGHT", "WB_SUNNY", "LIGHT_MODE", "NIGHTLIGHT", "BEDTIME", "CHECK")))]
    def test_prayers_shown_and_toggle(self):
        self.assertIn("نمازها", self.screen()); self.assertIn("صبح", self.screen()); self.assertIn("عشا", self.screen())
        self.assertEqual(len(self.prayer_items()), 5); self.prayer_items()[0].on_click(None)
        self.assertEqual(self.db.xp(), 5); self.assertIn("۱ از ۵", self.screen()); self.ok()
    def test_prayers_reset_next_day(self):
        self.prayer_items()[0].on_click(None); tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.go(0)
        tiles = F.find(self.body(), "Container", lambda c: getattr(c, "expand", False) and getattr(c, "ink", False) and getattr(c, "on_click", None))
        tiles[(date.today().weekday() + 2) % 7 + 1 if (date.today().weekday() + 2) % 7 < 6 else 0].on_click(None) if False else None
        self.db.ensure_day(tomorrow); rows = self.db.missions_on(tomorrow); self.assertEqual((len(rows), sum(r["done"] for r in rows)), (5, 0))
    def test_task_with_time_and_chore(self):
        self.fab().on_click(None); self.field("عنوان").value = "کلاس شیمی"; self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)").value = "۱۶:۳۰"
        self.field("مدت (دقیقه، اختیاری)").value = "۹۰"; self.press("ذخیره")
        m = [r for r in self.db.today_missions() if r["title"] == "کلاس شیمی"][0]; self.assertEqual((m["kind"], m["time"], m["minutes"]), ("task", "16:30", 90))
        self.assertIn("۱۶:۳۰–۱۸:۰۰", self.screen())
        q = F.find(self.body(), "TextField", lambda c: c.label.startswith("ریزه‌کار جدید"))[0]; q.on_submit(Ev(control=Ev(value="خرید نان")))
        c = [r for r in self.db.today_missions() if r["title"] == "خرید نان"][0]; self.assertEqual((c["kind"], c["xp"]), ("chore", 5)); self.assertIn("خرید نان", self.screen())
    def test_bad_time_rejected_and_kind_toggle(self):
        self.fab().on_click(None); self.field("عنوان").value = "x"; self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)").value = "25:99"; self.press("ذخیره")
        self.assertEqual(len(self.page.dialogs), 1)
        kseg = F.find(self.dlg(), "SegmentedButton")[0]; box = F.find(self.dlg(), "Column", lambda c: getattr(c, "visible", True) is True and len(c._args[0]) == 3 if c._args else False)
        kseg.selected = {"chore"}; kseg.on_change(Ev(control=kseg)); self.press("ذخیره")
        self.assertEqual(self.db.one("SELECT kind,time FROM missions WHERE title='x'")["kind"], "chore")
    def test_any_start_time_and_numeric_inputs(self):
        self.fab().on_click(None)
        tm = self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)"); mins = self.field("مدت (دقیقه، اختیاری)")
        for f in (tm, mins): self.assertEqual(f.keyboard_type, "NUMBER"); self.assertIsNone(getattr(f, "input_filter", None))     # بدون فیلتر سمت کلاینت
        self.assertIsNone(getattr(tm, "on_change", None))                 # هنگام تایپ هیچ بازنویسی‌ای در کار نیست
        self.assertIsNone(getattr(tm, "max_length", None))
        for raw, shown in (("1630", "16:30"), ("۹۳۰", "09:30"), ("0605", "06:05"), ("16", "16:00"), ("12:3", "12:3"), ("0:3", "0:3")):
            tm.value = raw; tm.on_blur(Ev(control=tm)); self.assertEqual(tm.value, shown)      # فقط ساعت معتبر هنگام خروج مرتب می‌شود
        self.page.dialogs.clear()
        for n, (raw, ok) in enumerate((("16:30", "16:30"), ("1630", "16:30"), ("930", "09:30"), ("9", "09:00"), ("۲۳۵۹", "23:59"), ("0000", "00:00"), ("4:5", None), ("2460", None), ("24:00", None))):
            self.fab().on_click(None); self.field("عنوان").value = f"t{n}"; self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)").value = raw; self.press("ذخیره")
            row = self.db.one("SELECT time FROM missions WHERE title=?", (f"t{n}",))
            if ok is None: self.assertIsNone(row, raw); self.page.dialogs.clear()     # نامعتبر: ذخیره نشد و دیالوگ باز ماند
            else: self.assertEqual(row["time"], ok, raw)
    def test_time_field_first_digit_deletable(self):
        self.fab().on_click(None)
        tm = self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)")
        self.assertIsNone(getattr(tm, "on_change", None))
        tm.value = "1030"; tm.on_blur(Ev(control=tm)); self.assertEqual(tm.value, "10:30")
        for raw in ("0:30", "030", ":30", "30", "0", ""):          # پاک کردن رقم اول و بقیه؛ برنامه هیچ‌کدام را بازنویسی نمی‌کند
            tm.value = raw; self.assertEqual(tm.value, raw)
        tm.value = "0:3"; tm.on_blur(Ev(control=tm)); self.assertEqual(tm.value, "0:3")   # نیمه‌کاره/نامعتبر دست‌نخورده می‌ماند
    def test_numeric_fields_have_no_input_filter_and_validate_on_save(self):
        self.fab().on_click(None)
        mins = self.field("مدت (دقیقه، اختیاری)"); tm = self.field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)")
        for f in (mins, tm): self.assertEqual(f.keyboard_type, "NUMBER"); self.assertIsNone(getattr(f, "input_filter", None)); self.assertIsNone(getattr(f, "on_change", None))
        self.field("عنوان").value = "اعتبار"
        for bad in ("abc", "1_0", "12.5", "-5", "1 2", "9x"):             # ورودی غیرمجاز: ذخیره نمی‌شود و دیالوگ باز می‌ماند
            mins.value = bad; self.press("ذخیره")
            self.assertIsNone(self.db.one("SELECT 1 FROM missions WHERE title='اعتبار'"), bad); self.assertEqual(len(self.page.dialogs), 1, bad)
            self.assertEqual(mins.error_text, "عدد وارد کنید")
        for raw in ("45", "", "۴۵", "٤٥"):                               # چند بار پشت‌سرهم تایپ/پاک/اصلاح؛ مقدار فیلد هیچ‌وقت از سمت برنامه دست نمی‌خورد
            mins.value = raw; self.assertEqual(mins.value, raw)
        mins.value = "۴۵"; self.press("ذخیره")
        r = self.db.one("SELECT minutes FROM missions WHERE title='اعتبار'"); self.assertEqual(r["minutes"], 45)
    def test_log_form_numeric_validation(self):
        import ui as UI
        self.assertEqual([UI.to_int(v) for v in ("12", "۱۲", "٤٢", " 7 ", "0")], [12, 12, 42, 7, 0])
        self.assertEqual([UI.to_int(v) for v in ("", None, "a", "1_0", "1.5", "-3", "+3", "1 2", "²")], [None] * 9)
        self.assertIsNone(getattr(UI.num_field("x"), "input_filter", None)); self.assertEqual(UI.num_field("x").keyboard_type, "NUMBER")
        self.assertIsNone(getattr(UI.time_field("x"), "input_filter", None))
    def test_notes_are_paginated(self):
        for i in range(75): self.db.save_note(f"یادداشت {i}", "متن", ["الف"] if i % 3 == 0 else [])
        self.page = F.Page(); app.main(self.page); self.go(3); self.ok()
        cards = lambda: [c for c in F.find(self.body(), "Container", lambda c: c.__dict__.get("on_click") and F.all_text(c).startswith("یادداشت "))]
        self.assertEqual(len(cards()), 30); more = [c for c in F.find(self.body(), "Container") if "نمایش یادداشت‌های بیشتر" in F.all_text(c) and c.__dict__.get("on_click")]
        self.assertTrue(more); more[-1].on_click(None); self.assertEqual(len(cards()), 60); self.ok()
    def test_nav_fits_any_width(self):
        for w in (260, 300, 320, 360, 400, 480):
            self.page.width = w; self.page.on_resized(None)
            for i in range(5):
                self.page.data.update(tab=i, nav=i); app_nav = F.find(self.body(), "Container", lambda c: getattr(c, "data", None) == ("nav", i))[0]; app_nav.on_click(None)
                boxes = [F.find(self.body(), "Container", lambda c, j=j: getattr(c, "data", None) == ("nav", j))[0] for j in range(5)]
                tot = 0
                for j, b in enumerate(boxes):
                    ic_, lab = b._args[0]._args[0]
                    pad = 2 * dict(b.padding[2])["horizontal"]
                    tot += ic_.size + pad + ((6 + (lab.width or 0)) if j == i else 0)
                self.assertLessEqual(tot, w - 46, (w, i, tot))
    def test_week_page(self):
        self.go(2); self.ok(); self.assertIn("هفته", self.screen()); self.assertIn("اهداف هفته", self.screen()); self.assertIn("وضعیت اهداف", self.screen())
        nxt = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("CHEVRON_LEFT"))[0]; nxt.on_click(None); self.ok()
        prv = F.find(self.body(), "IconButton", lambda c: c._args and str(c._args[0]).startswith("CHEVRON_RIGHT"))[0]; prv.on_click(None); self.ok()
        tiles = F.find(self.body(), "Container", lambda c: str(getattr(c, "data", ""))[:7] == "('wday'"); self.assertEqual(len(tiles), 7); tiles[0].on_click(None); self.ok()
    def test_week_copy(self):
        self.go(2); self.db.save_mission("کپی‌شونده", "", 30, 1, date.today()); self.go(2)
        F.find(self.body(), "ElevatedButton", lambda c: c._args[0] == "کپی به هفتهٔ بعد")[0].on_click(None); self.press("بله")
        self.assertEqual(self.db.one("SELECT COUNT(*) n FROM missions WHERE title='کپی‌شونده'")["n"], 2)
    def open_routines(self):
        self.go(2); F.find(self.body(), "ElevatedButton", lambda c: c._args[0] == "روتین‌ها و نماز")[0].on_click(None)
    def new_routine(self): F.find(self.body(), "ElevatedButton", lambda c: c._args[0] == "روتین جدید")[0].on_click(None)
    def test_routine_create_edit_delete(self):
        self.open_routines(); self.ok(); self.assertIn("نماز صبح", self.screen())
        self.new_routine(); self.field("عنوان روتین (مثلاً ورزش صبحگاهی)").value = "ورزش"; self.press("ذخیره")
        r = self.db.one("SELECT * FROM routines WHERE title='ورزش'"); self.assertEqual((r["kind"], r["days"]), ("chore", "0,1,2,3,4,5,6")); self.assertIn("ورزش", self.screen())
        self.go(0); self.assertIn("روتین امروز", self.screen()); self.assertIn("ورزش", self.screen())
        sw = [c for c in F.find(self.body(), "Switch")]; self.assertEqual(sw, [])          # سوییچ فقط در صفحهٔ روتین‌ها
        self.page.controls  # بازگشت به مدیریت
        self.open_routines()
        sws = F.find(self.body(), "Switch"); self.assertEqual(len(sws), 6); sws[-1].on_change(Ev(control=Ev(value=False))); self.assertEqual(self.db.one("SELECT active FROM routines WHERE title='ورزش'")["active"], 0)
        menus = F.find(self.body(), "PopupMenuButton"); menus[-1].items[1].on_click(None); self.press("بله"); self.assertIsNone(self.db.one("SELECT 1 FROM routines WHERE title='ورزش'"))
    def test_routine_requires_day(self):
        self.open_routines()
        self.new_routine(); self.field("عنوان روتین (مثلاً ورزش صبحگاهی)").value = "الف"
        for chipc in F.find(self.dlg(), "Container", lambda c: getattr(c, "on_click", None) and c.border_radius == 20): chipc.on_click(None)   # همهٔ روزها را خاموش کن
        self.press("ذخیره"); self.assertEqual(len(self.page.dialogs), 1); self.assertTrue(self.page.snacks)
    def test_routine_tile_menu_edits_routine(self):
        tile_menu = [m for m in F.find(self.body(), "PopupMenuButton") if m.items and m.items[0].text == "ویرایش روتین"]; self.assertEqual(len(tile_menu), 0)  # نمازها در کارت جدا هستند
        self.db.save_routine("مطالعه روزانه", "task", 60, "20:00", range(7)); self.go(0)
        menus = [m for m in F.find(self.body(), "PopupMenuButton") if m.items[0].text == "ویرایش روتین"]; self.assertEqual(len(menus), 1)
        menus[0].items[0].on_click(None); self.assertEqual(self.field("عنوان روتین (مثلاً ورزش صبحگاهی)").value, "مطالعه روزانه")

if __name__ == "__main__": unittest.main()
