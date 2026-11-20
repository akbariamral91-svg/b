# -*- coding: utf-8 -*-
"""Get Better — برنامه‌ریز آمادگی آزمون (Flet 0.28.x + SQLite، کاملاً آفلاین)

صفحه‌ها: خانه • تحصیل • هفته • یادداشت‌ها • پیشرفت • تنظیمات • روتین‌ها (تحصیل/هفته/یادداشت‌ها/پیشرفت در pages.py)
ظاهر و انیمیشن‌ها در ui.py (سیستم طراحی) و منطق داده در store.py است.
"""
import os, sys, sqlite3, threading, time, math, traceback
from datetime import date, datetime, timedelta
import flet as ft
import jalali as J
import meta
import ui
import notify
import quickadd
import hero as hero_mod
import pages as pages_mod
from types import SimpleNamespace
from jalali import fa
from ui import (P, alpha, ic, txt, ibadge, card, chip, title, section, empty, btn, field, num_field, time_field, dd, seg, pbar, ring, count_up, divider, spacer,
                glow, M, anim, pulse, pop_in, bounce, later, brand_mark, list_row, group, stat_tile, step_dots, legend_scale, EASE, BACK, ELASTIC, PRAYER_ICONS, ACHIEVEMENT_ICONS)
from store import Store, BACKUP_VERSION, log_error, read_error_log, clear_error_log, level_for_xp, xp_threshold, level_title, data_dir, ACHIEVEMENTS, GOAL_BONUS, REPEATS, PRAYERS, KINDS_TASK, WEEK_ORDER

PRIO = [("کم", "green"), ("متوسط", "gold"), ("زیاد", "red")]
STATUS = [("شروع‌نشده", "muted"), ("در حال یادگیری", "blue"), ("نیازمند مرور", "gold"), ("تسلط تأییدشده", "green")]
KINDS = {"practice": "تمرین", "exam": "آزمون", "review": "مرور"}
NAV = [("خانه", "HOME", 38), ("تحصیل", "SCHOOL", 44), ("هفته", "CALENDAR_MONTH", 38), ("یادداشت‌ها", "STICKY_NOTE_2", 78), ("پیشرفت", "INSIGHTS", 52)]
TOPBAR_TABS = (5, 6, 7)             # فقط تنظیمات/روتین‌ها/درباره نوار بالای کلی دارند؛ خانه و چهار صفحهٔ دیگر هدر تصویری خودشان را دارند
VERSION = meta.VERSION

def install_error_hooks():
    """خطاهای پیش‌بینی‌نشده (حتی در رشته‌های پس‌زمینه) در errors.log ثبت می‌شوند تا برنامه بی‌صدا خراب نشود."""
    def hook(t, v, tb): log_error("unhandled", v)
    def thook(a): log_error(f"thread {getattr(a.thread, 'name', '?')}", a.exc_value)
    sys.excepthook = hook; threading.excepthook = thook

def today(): return date.today()
def fmt_minutes(m):
    m = int(m)
    return f"{fa(m)} دقیقه" if m < 60 else f"{fa(m // 60)} ساعت" + (f" و {fa(m % 60)} دقیقه" if m % 60 else "")


def main(page: ft.Page):
    install_error_hooks()
    store = Store()
    M.page = page                                  # برای ارسال دسته‌ای تغییرات انیمیشن (یک پیام در هر فریم)
    S = {"tab": 0, "nav": 0, "notes_tab": 0, "q": "", "tag": None, "day": today().isoformat(), "wk": today().isoformat(), "pop": None, "subs_open": set(), "note_n": 30, "ev_n": 40}
    page.data = S                                  # برای تست‌ها و اشکال‌زدایی
    LIFE = []                                      # شنونده‌های چرخهٔ عمر (مثلاً تایمر تمرکز)
    def on_life(e):
        st_ = str(getattr(e, "state", None) or getattr(e, "data", "") or "").lower()
        if any(k in st_ for k in ("pause", "hide", "detach")): M.paused = True
        elif any(k in st_ for k in ("resume", "show")): M.paused = False
        for cb in list(LIFE):
            try: cb(str(getattr(e, "state", None) or getattr(e, "data", "") or ""))
            except Exception as ex: log_error("lifecycle", ex)
    try: page.on_app_lifecycle_state_change = on_life
    except Exception as ex: log_error("lifecycle", ex)

    page.title = meta.APP_NAME
    try: page.on_error = lambda e: log_error("page.on_error", Exception(str(getattr(e, "data", e))))
    except Exception: pass
    page.padding = 0
    page.window.width, page.window.height = 400, 820   # فقط برای اجرای دسکتاپ/تست
    ui.setup_fonts(page)
    try: page.rtl = True
    except Exception: pass

    def apply_theme():
        ui.set_mode(store.pref("theme") != "light")
        page.theme_mode = ft.ThemeMode.DARK if ui.is_dark() else ft.ThemeMode.LIGHT
        kw = {"font_family": ui.FONT} if ui.HAS_FONT else {}
        page.theme = ft.Theme(color_scheme_seed=P["gold"], use_material3=True, **kw)
        if not ui.is_dark():                           # حالت روشن: رنگ‌های اجزای Material (سوییچ، کشویی، انتخاب‌گر…) هم‌رنگ پالت برنامه می‌شوند، نه نمونهٔ خودکار قهوه‌ای از seed
            try: page.theme = ft.Theme(color_scheme=ft.ColorScheme(primary=P["gold"], on_primary=P["on_accent"], secondary=P["blue"], surface=P["card"], on_surface=P["text"], outline=P["muted"]), use_material3=True, **kw)
            except Exception as ex: log_error("color_scheme", ex)
        page.dark_theme = page.theme
        page.bgcolor = P["bg"]

    def tidy_overlay():
        """دیالوگ و اسنک‌بارِ بسته‌شده در page.overlay می‌ماند و هر page.update() باید همه را بپیماید؛ هرچه بیشتر از برنامه استفاده شود
        هر کلیک کندتر می‌شد. قدیمی‌های بسته‌شده را برمی‌داریم؛ ۳ تای آخر می‌مانند تا انیمیشن بسته‌شدنِ تازه‌ترین‌ها قطع نشود."""
        try:
            ov = page.overlay
            dead = [c for c in ov if getattr(c, "open", True) is False and type(c).__name__ in ("AlertDialog", "SnackBar", "BottomSheet")]
            for c in dead[:-3]: ov.remove(c)
        except Exception as ex: log_error("overlay", ex)
    def popen(c): tidy_overlay(); page.open(c)
    def dialog_open():
        try: return any(getattr(c, "open", False) is True and type(c).__name__ == "AlertDialog" for c in page.overlay)
        except Exception: return False
    M.hold = dialog_open                           # وقتی دیالوگ باز است، انیمیشن‌های بی‌پایان (نفس‌کشیدن) فریم‌ها را از دیالوگ و کیبورد نمی‌گیرند
    def snack(msg, ok=True): popen(ui.snack_bar(msg, ok))
    def update_width(e=None):
        try: M.page_w = int(page.width or 400)
        except Exception: M.page_w = 400
    try: page.on_resized = update_width
    except Exception: pass

    def dialog(heading, controls, on_save, save_label="ذخیره", cancel=True, icon="EDIT", color="gold"):
        head = ft.Row([ibadge(ic(icon), color, 36, radius=12), txt(heading, 18, ft.FontWeight.W_800, expand=True)], spacing=10)
        dlg = ft.AlertDialog(modal=True, bgcolor=P["card"], shape=ft.RoundedRectangleBorder(radius=28), title=head, inset_padding=ft.padding.symmetric(horizontal=16, vertical=24),
                             content=ft.Container(ft.Column(controls, tight=True, spacing=10, scroll=ft.ScrollMode.AUTO), width=340))
        def save(e):
            if on_save() is not False: page.close(dlg)
        dlg.actions = ([ft.TextButton("انصراف", on_click=lambda e: page.close(dlg), style=ft.ButtonStyle(color=P["muted"]))] if cancel else []) + \
                      [ft.FilledButton(save_label, on_click=save, style=ft.ButtonStyle(bgcolor=P["gold"], color=P["on_accent"], shape=ft.RoundedRectangleBorder(radius=14)))]
        popen(dlg)
        return dlg

    def confirm(heading, msg, on_yes, danger=True):
        col = "red" if danger else "gold"
        dlg = ft.AlertDialog(modal=True, bgcolor=P["card"], shape=ft.RoundedRectangleBorder(radius=28),
                             title=ft.Row([ibadge(ic("DELETE_FOREVER" if danger else "HELP"), col, 36, radius=12), txt(heading, 18, ft.FontWeight.W_800, expand=True)], spacing=10),
                             content=txt(msg, 14, color="muted"))
        def yes(e): page.close(dlg); on_yes()
        dlg.actions = [ft.TextButton("خیر", on_click=lambda e: page.close(dlg), style=ft.ButtonStyle(color=P["muted"])),
                       ft.FilledButton("بله", on_click=yes, style=ft.ButtonStyle(bgcolor=P["red"] if danger else P["gold"], color="#FFFFFF" if danger else P["on_accent"], shape=ft.RoundedRectangleBorder(radius=14)))]
        popen(dlg)

    def jdate_field(label, iso=None):
        """انتخابگر تاریخ جلالی (روز/ماه/سال) بدون دیالوگ تو در تو. خروجی: (کنترل، گرفتن ISO، تنظیم ISO)."""
        d0 = J.as_date(iso) if iso else today(); jy, jm, jd = J.to_jalali(d0)
        cur = J.to_jalali(today())[0]
        years = sorted(set(range(cur - 1, cur + 6)) | {jy})
        yr = dd(str(jy), [(str(y), fa(y)) for y in years], 104)
        mo = dd(str(jm), [(str(i + 1), n) for i, n in enumerate(J.MONTHS)], 132)
        dy = dd(str(jd), [(str(i), fa(i)) for i in range(1, 32)], 80)
        def refresh(e=None):
            ml = J.month_length(int(yr.value), int(mo.value))
            dy.options = [ft.dropdown.Option(str(i), fa(i)) for i in range(1, ml + 1)]
            if int(dy.value) > ml: dy.value = str(ml)
            if e is not None: dy.update()
        yr.on_change = mo.on_change = refresh; refresh()
        def get(): return J.from_jalali(int(yr.value), int(mo.value), int(dy.value)).isoformat()
        def set_(v):
            a, b, c = J.to_jalali(J.as_date(v))
            if str(a) not in [o.key for o in yr.options]: yr.options.append(ft.dropdown.Option(str(a), fa(a)))
            yr.value, mo.value = str(a), str(b); refresh(); dy.value = str(c)
            for x in (yr, mo, dy): x.update()
        quick = ft.Row([chip(n, "gold", on_click=lambda e, k=k: set_((today() + timedelta(days=k)).isoformat()))
                        for n, k in (("امروز", 0), ("فردا", 1), ("پس‌فردا", 2), ("هفتهٔ بعد", 7))], spacing=6, wrap=True)
        return ft.Column([txt(label, 12, color="muted"), ft.Row([dy, mo, yr], spacing=6), quick], spacing=6), get, set_

    # ================= دستاوردها =================
    def celebrate(new, extra=()):
        """جشن یک‌پارچه: سطح تازه، پاداش هدف، نقطهٔ عطف استریک و دستاوردهای جدید در یک دیالوگ.
        extra: فهرست (آیکون، رنگ، عنوان، توضیح)."""
        items = list(extra) + [(*ACHIEVEMENT_ICONS.get(aid, ("EMOJI_EVENTS", "gold")), t, d) for aid, t, d, _e in new]
        if not items: return
        rows = []
        for k, (icon, col, t, d) in enumerate(items):
            badge = pop_in(ft.Container(ibadge(ic(icon), col, 56, filled=True, radius=19)), .05 + .12 * k, .2, live=True)
            rows.append(ft.Row([badge, ft.Column([txt(t, 15, ft.FontWeight.W_800, col), txt(d, 12, color="muted")], spacing=2, expand=True)], spacing=14))
        dialog("آفرین! 🎉" if extra else "دستاورد جدید!", rows, lambda: True, "عالیه", cancel=False, icon="EMOJI_EVENTS")
    def after_action(extra=()):
        try:
            extra = list(extra); n = store.streak_milestone()
            if n: extra.append(("LOCAL_FIRE_DEPARTMENT", "red", f"{fa(n)} روز پیاپی!", "پیوستگی‌ات فوق‌العاده است؛ آتش را روشن نگه دار."))
            celebrate(store.check_achievements(), extra)
        except Exception: traceback.print_exc()

    # ================= مأموریت‌ها =================
    norm_time = ui.norm_time
    def time_label(r):
        if not r["time"]: return ""
        if not r["minutes"]: return fa(r["time"])
        end = (datetime.strptime(r["time"], "%H:%M") + timedelta(minutes=r["minutes"])).strftime("%H:%M")
        return f"{fa(r['time'])}–{fa(end)}"

    def mission_form(row=None, day=None, kind=None):
        """کار: ساعت و مدت اختیاری • ریزه‌کار: کار کوچک بدون ساعت معین."""
        k0 = (row["kind"] if row else kind) or "task"
        kseg = seg(k0, list(KINDS_TASK.items()))
        t = field("عنوان", row["title"] if row else "", autofocus=True)
        sub = field("درس (اختیاری)", row["subject"] if row else "")
        tm = time_field("ساعت شروع (اختیاری، مثل ۱۶:۳۰)", row["time"] if row else "")
        mins = num_field("مدت (دقیقه، اختیاری)", str(row["minutes"]) if row and row["minutes"] else "")
        def setv(c, v): c.value = v; c.update()
        sub_chips = ft.Row([chip(s["name"], "blue", on_click=lambda e, n=s["name"]: setv(sub, n)) for s in store.all("SELECT name FROM subjects ORDER BY name")], spacing=6, scroll=ft.ScrollMode.AUTO)
        min_chips = ft.Row([chip(fa(m), "gold", on_click=lambda e, m=m: setv(mins, str(m))) for m in (15, 30, 45, 60, 90, 120)], spacing=6, scroll=ft.ScrollMode.AUTO)
        task_box = ft.Column([tm, mins, min_chips], spacing=10, visible=k0 == "task")
        def kind_changed(e): task_box.visible = list(e.control.selected)[0] == "task"; task_box.update()
        kseg.on_change = kind_changed
        dfield, get_day, _ = jdate_field("تاریخ", row["date"] if row else (day or S["day"]))
        pr = seg(row["priority"] if row else 1, [(i, n) for i, (n, _) in enumerate(PRIO)])
        def save():
            k = list(kseg.selected)[0]
            if not t.value.strip(): t.error_text = "عنوان الزامی است"; t.update(); return False
            time_s, m = "", 0
            if k == "task":
                tm.error_text = mins.error_text = None
                time_s = norm_time(tm.value)
                if time_s is None: tm.error_text = "ساعت نامعتبر است (۰۰:۰۰ تا ۲۳:۵۹)"; tm.update(); return False
                m = ui.to_int(mins.value) if mins.value.strip() else 0
                if m is None: mins.error_text = "عدد وارد کنید"; mins.update(); return False
                m = min(1440, m)
            store.save_mission(t.value.strip()[:150], sub.value.strip(), m, int(list(pr.selected)[0]), get_day(), row["id"] if row else None,
                               (row["repeat"] if row else "") or "", None, k, time_s)
            render()
        dialog("ویرایش" if row else "کار یا ریزه‌کار جدید", [kseg, t, sub, sub_chips, task_box, dfield, txt("اولویت", 12, color="muted"), pr], save, icon="TASK_ALT")

    def toggle(mid, popped=False):
        lvl0 = level_for_xp(store.xp())
        done_now = store.toggle_mission(mid)
        bonus = store.claim_goal_bonus(today()) if done_now else 0
        if done_now and not popped: S["pop"] = mid           # popped: جهش همان لحظه روی خود کنترل انجام شده؛ در رندر دوباره تکرار نشود
        render()                                    # اول نتیجه روی صفحه؛ پیام تشویق بعد از آن (نه قبل از آن)
        extra = []
        if done_now:
            m = store.one("SELECT xp FROM missions WHERE id=?", (mid,)); snack(f"آفرین! +{fa(m['xp'])} XP" + (f" • +{fa(bonus)} پاداش هدف" if bonus else ""))
            lvl1 = level_for_xp(store.xp())
            if lvl1 > lvl0: extra.append(("MILITARY_TECH", "gold", f"سطح {fa(lvl1)}: {level_title(lvl1)}", "ارتقا پیدا کردی! این نتیجهٔ تلاش‌های روزانه‌ات است."))
            if bonus: extra.append(("TRACK_CHANGES", "green", "هدف امروز زده شد!", f"+{fa(bonus)} XP پاداش هدف روزانه"))
        after_action(extra)

    def focus_dialog(m):
        """تایمر پومودورو: تمرکز/استراحت خودکار؛ زمان تمرکز روی مأموریت و آمار ثبت می‌شود."""
        work, brk = max(1, store.pref_int("pomodoro", 25)), max(1, store.pref_int("break", 5))
        st = dict(phase="work", left=float(work * 60), run=False, stop=False, spent=0.0, rounds=0)
        clock = txt("", 46, ft.FontWeight.W_800, "gold"); phase_t = txt("", 13, color="muted")
        rg = ui.progress_ring(value=0, width=200, height=200, stroke_width=11, color=P["gold"], bgcolor=alpha(P["text"], .10))
        halo = ft.Container(width=232, height=232, border_radius=116, animate=anim(900, ft.AnimationCurve.EASE_IN_OUT),
                            gradient=ft.RadialGradient(center=ft.alignment.center, radius=.5, colors=[alpha(P["gold"], .20), alpha(P["gold"], 0)]))
        main_btn = ft.FilledButton("شروع", icon=ic("PLAY_ARROW"), style=ft.ButtonStyle(bgcolor=P["gold"], color=P["on_accent"], shape=ft.RoundedRectangleBorder(radius=16)))
        def mmss(s): s = max(0, math.ceil(s)); return fa(f"{s // 60:02d}:{s % 60:02d}")
        def paint():
            total = (work if st["phase"] == "work" else brk) * 60
            clock.value = mmss(st["left"]); rg.value = min(1, max(0, 1 - st["left"] / total))
            col = P["gold"] if st["phase"] == "work" else P["green"]
            rg.color = col; clock.color = col
            halo.gradient = ft.RadialGradient(center=ft.alignment.center, radius=.5, colors=[alpha(col, .30 if st["run"] else .12), alpha(col, 0)])
            phase_t.value = ("زمان تمرکز" if st["phase"] == "work" else "استراحت کوتاه") + (f" • دور {fa(st['rounds'] + 1)}" if st["phase"] == "work" else "")
            main_btn.text = "توقف" if st["run"] else ("ادامه" if st["spent"] > 0 or st["rounds"] else "شروع")
            main_btn.icon = ic("PAUSE") if st["run"] else ic("PLAY_ARROW")
            for c in (clock, phase_t, rg, main_btn, halo):
                try: c.update()
                except Exception: pass
        lock = threading.Lock(); st.update(last=time.time(), closed=False)
        def flip():
            """تغییر مرحله (تمرکز ⇄ استراحت) فقط در وضعیت؛ رنگ‌آمیزی جداست."""
            if st["phase"] == "work": st["rounds"] += 1; st["phase"] = "break"; st["left"] = float(brk * 60)
            else: st["phase"] = "work"; st["left"] = float(work * 60)
        def advance():
            """زمان را از روی ساعت واقعی جلو می‌برد، نه از روی تیک‌های رشته؛ پس خاموش‌شدن صفحه یا رفتن به پس‌زمینه شمارش را عقب نمی‌اندازد.
            خروجی: (تعداد مرحله‌های طی‌شده، فاصلهٔ زمانی از آخرین هم‌گام‌سازی به ثانیه)."""
            with lock:
                now = time.time(); dt = max(0.0, now - st["last"]); st["last"] = now     # ساعت به عقب برود → صفر
                if not st["run"] or dt <= 0: return 0, dt
                crossed, budget = 0, dt
                while budget > 0:
                    step = min(budget, st["left"]); st["left"] -= step; budget -= step
                    if st["phase"] == "work": st["spent"] += step
                    if st["left"] <= 1e-6:
                        flip(); crossed += 1
                        if crossed >= 4 and budget > 0:      # بیش از دو چرخهٔ کامل بی‌حضور: تایمر فراموش‌شده را متوقف کن تا زمان مفت ثبت نشود
                            st["run"] = False; break
                return crossed, dt
        def sync(e=None):
            """هم‌گام‌سازی با ساعت + رنگ‌آمیزی؛ از حلقه و از رویداد چرخهٔ عمر برنامه (برگشت از پس‌زمینه) صدا زده می‌شود."""
            if st["stop"]: return
            crossed, dt = advance()
            if crossed and dt > 3: snack("تایمر در غیاب تو ادامه پیدا کرد و مرحله عوض شد")
            paint()
        def switch(e=None):
            advance(); flip(); st["last"] = time.time(); paint()
        def loop():
            while not st["stop"]:
                time.sleep(.5)
                if st["stop"]: break
                try: sync()
                except Exception as ex: log_error("تایمر تمرکز", ex)
        def run_toggle(e): advance(); st["run"] = not st["run"]; st["last"] = time.time(); paint()
        main_btn.on_click = run_toggle
        def close(complete=False, e=None):
            if st["closed"]: return                       # با «بازگشت» سیستم هم بسته می‌شود؛ ذخیره فقط یک بار
            st["closed"] = True; advance(); st["stop"] = True
            if life_cb in LIFE: LIFE.remove(life_cb)
            if st["spent"] >= 20: store.add_focus(m["id"], int(st["spent"]))
            try: page.close(dlg)
            except Exception: pass
            if complete and not store.one("SELECT done FROM missions WHERE id=?", (m["id"],))["done"]: toggle(m["id"])
            else: render(); after_action()
        life_cb = lambda state: sync()
        LIFE.append(life_cb)
        dial = ft.Stack([halo, ft.Container(rg, alignment=ft.alignment.center, width=232, height=232), ft.Container(clock, alignment=ft.alignment.center, width=232, height=232)], width=232, height=232)
        dlg = ft.AlertDialog(modal=True, bgcolor=P["card"], shape=ft.RoundedRectangleBorder(radius=28),
            title=ft.Row([ibadge(ic("CENTER_FOCUS_STRONG"), "gold", 36, radius=12), txt("حالت تمرکز", 18, ft.FontWeight.W_800)], spacing=10),
            content=ft.Container(ft.Column([txt(m["title"], 14, ft.FontWeight.W_600, text_align=ft.TextAlign.CENTER), dial, phase_t,
                ft.Row([main_btn, ft.TextButton("رد کردن", on_click=switch, style=ft.ButtonStyle(color=P["muted"]))], alignment=ft.MainAxisAlignment.CENTER),
                txt("گوشی را کنار بگذار و فقط روی همین کار تمرکز کن؛ تایمر با ساعت واقعی می‌شمارد.", 11, color="muted", text_align=ft.TextAlign.CENTER)],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=12, tight=True), width=300),
            on_dismiss=lambda e: close(),
            actions=[ft.TextButton("پایان و ذخیره", on_click=lambda e: close(), style=ft.ButtonStyle(color=P["muted"])),
                     ft.FilledButton("تکمیل مأموریت", on_click=lambda e: close(True), style=ft.ButtonStyle(bgcolor=P["green"], color=P["on_accent"], shape=ft.RoundedRectangleBorder(radius=14)))])
        popen(dlg); paint()
        threading.Thread(target=loop, daemon=True).start()

    S["focus_open"] = focus_dialog              # حالت تمرکز از صفحهٔ امروز برداشته شد؛ منطقش سر جاست و از این نقطه (تست‌ها / ورودی آیندهٔ دیگر صفحه‌ها) باز می‌شود
    def check_button(r, size):
        if store.is_missed(r):          # روتینِ از دست‌رفته: دایرهٔ قرمز، قفل، بدون انتقال
            return ft.Container(ft.IconButton(ic("CANCEL"), icon_size=size, icon_color=P["red"], disabled=True, tooltip="انجام نشد"))
        if store.is_locked_routine(r):  # روتینِ انجام‌شدهٔ روزهای گذشته: تاریخچه است و برنمی‌گردد
            return ft.Container(ft.IconButton(ic("CHECK_CIRCLE"), icon_size=size, icon_color=P["green"], disabled=True, tooltip="انجام شد"))
        done = bool(r["done"]); pname, pcol = PRIO[max(0, min(2, r["priority"]))]
        cur = [done]
        def hit(e, i=r["id"]):
            was = cur[0]; cur[0] = not was; popped = False       # لمس دوباره‌ی همین کنترل پیش از بازسازی هم با دیتابیس هم‌جهت می‌ماند
            try:                                    # بازخورد فوری: فقط همین یک کنترل با یک پیام کوچک؛ بازسازی کامل صفحه بعد از آن می‌آید
                b.icon = ic("RADIO_BUTTON_UNCHECKED", "outlined") if was else ic("CHECK_CIRCLE")
                b.icon_color = alpha(P[pcol], .95) if was else P["green"]
                if was: holder.update()
                else: bounce(holder, .5); popped = True
            except Exception: pass
            toggle(i, popped)
        b = ft.IconButton(ic("CHECK_CIRCLE") if done else ic("RADIO_BUTTON_UNCHECKED", "outlined"), icon_size=size,
                          icon_color=P["green"] if done else alpha(P[pcol], .95), tooltip="برگرداندن" if done else "انجام شد", on_click=hit)
        holder = ft.Container(b)
        if done and S.get("pop") == r["id"]:
            S["pop"] = None; return pop_in(holder, .02, .35)
        return holder

    def mission_tile(r, compact=False):
        done = bool(r["done"]); pname, pcol = PRIO[max(0, min(2, r["priority"]))]; routine = r["routine_id"] is not None
        missed = store.is_missed(r)
        title_w = ft.Text(r["title"], size=14 if compact else 15, color=alpha(P["red"], .85), font_family=ui.family(None), style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)) if missed else ft.Text(r["title"], size=14 if compact else 15, color=P["muted"], font_family=ui.family(None), style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)) if done else txt(r["title"], 14 if compact else 15, ft.FontWeight.W_600)
        if routine:
            def edit_routine(e, i=r["routine_id"]):
                x = store.one("SELECT * FROM routines WHERE id=?", (i,))
                if x: routine_form(x)
            items = [ft.PopupMenuItem(text="ویرایش روتین", icon=ic("EDIT", "outlined"), on_click=edit_routine),
                     ft.PopupMenuItem(text="مدیریت روتین‌ها", icon=ic("EVENT_REPEAT"), on_click=lambda e: (S.update(tab=6, rt_back=S["tab"]), render()))]
        else:
            items = [ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=r: mission_form(x)),
                     ft.PopupMenuItem(text="انتقال به فردا", icon=ic("EVENT_REPEAT"), on_click=lambda e, i=r["id"]: (store.move_tomorrow(i), render())),
                     ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, i=r["id"]: confirm("حذف", "حذف شود؟ امتیاز قبلی پاک نمی‌شود.", lambda: (store.delete_mission(i), render())))]
        menu = ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=items, tooltip="گزینه‌ها")
        if compact:      # ریزه‌کار و روتین: یک خط ساده
            sub = [txt(r["subject"], 11, color="muted")] if r["subject"] else []
            tl = time_label(r); extra = [chip(tl, "gold", ic("SCHEDULE"))] if tl else []
            return card(ft.Row([check_button(r, 26), ft.Column([title_w, *sub], spacing=0, expand=True), *extra, menu], vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
                        pad=ft.padding.only(left=2, right=2, top=0, bottom=0), margin=ft.margin.only(bottom=6), radius=20, shadow=False, bg=alpha(P["card"], .75) if not ui.is_dark() else None)
        meta = []
        if r["time"]: meta.append(chip(time_label(r), "gold", ic("SCHEDULE")))
        if r["minutes"]: meta.append(chip(fmt_minutes(r["minutes"]), "muted", ic("TIMER", "outlined")))
        meta += [chip(pname, pcol, ic("FLAG")), chip(f"{fa(r['xp'])} XP", "gold", ic("BOLT"))]
        if r["repeat"]: meta.append(chip(REPEATS[r["repeat"]], "blue", ic("REPEAT")))
        if r["spent_seconds"]: meta.append(chip(f"{fa(r['spent_seconds'] // 60)} دقیقه تمرکز", "green", ic("CENTER_FOCUS_STRONG")))
        trail = [ft.IconButton(ic("CENTER_FOCUS_STRONG", "outlined"), icon_color=P["gold"], tooltip="حالت تمرکز", on_click=lambda e, x=r: focus_dialog(x))] if not done else []
        body = ft.Column([title_w, txt(r["subject"], 12, color="muted") if r["subject"] else ft.Container(height=0), ft.Row(meta, spacing=6, wrap=True, run_spacing=4)], spacing=6, expand=True)
        strip = ft.Container(width=4, border_radius=4, bgcolor=P["green"] if done else P[pcol], opacity=.9)
        inner = ft.Row([strip, check_button(r, 30), body, *trail, menu], vertical_alignment=ft.CrossAxisAlignment.START, spacing=0)
        return card(ft.Container(inner, padding=ft.padding.only(right=0, top=0)), pad=ft.padding.only(left=4, right=10, top=10, bottom=12), margin=ft.margin.only(bottom=10),
                    border=ft.border.all(1, alpha(P["green"], .25)) if done else None)

    def smart_plan():
        items = store.suggest_plan(S["day"])
        if not items: snack("فعلاً مبحثی برای مرور سررسید نشده"); return
        rows = [ft.Row([ibadge(ic("AUTO_AWESOME"), "gold", 34, radius=11), ft.Column([txt(i["title"], 13, ft.FontWeight.W_600), txt(f"{i['subject']} • {fmt_minutes(i['minutes'])}", 11, color="muted")], spacing=0, expand=True)], spacing=10) for i in items]
        dialog("برنامهٔ هوشمند", [txt(f"بر اساس مرور فاصله‌دار، این {fa(len(items))} مورد برای {J.fmt(S['day'])} پیشنهاد می‌شود:", 12, color="muted"), *rows],
               lambda: (store.apply_plan(items, S["day"]), render()), "افزودن به برنامه", icon="AUTO_AWESOME")

    # ================= صفحهٔ امروز =================
    def is_prayer(r): return (r["rkey"] or "").startswith("prayer")

    # ---- صفحهٔ امروز (طراحی ۴٫۰): فقط این بخش و کارت نمازها عوض شده‌اند؛ بقیهٔ صفحه‌ها همان‌اند ----
    LIGHT_TXT = "#F5F6FC"                      # روی عکس قهرمان همیشه روشن (مستقل از تم)

    def pray_hit(i, ok, disc, glyph, icon):
        cur = [ok]
        def hit(e=None):
            was = cur[0]; cur[0] = not was; popped = False
            try:                                    # قرص نماز همان لحظه عوض می‌شود (طلایی با انیمیشن ۳۰۰ms خودش، تیک با جهش)
                disc.bgcolor = alpha(P["violet"], .12) if was else P["gold"]
                glyph.name = icon if was else ic("CHECK"); glyph.color = P["violet"] if was else P["on_accent"]
                if was: disc.update()
                else: bounce(disc, .5); popped = True
            except Exception: pass
            toggle(i, popped)
        return hit

    def prayer_card(rows):
        short = {k: n for k, _, n in PRAYERS}; done = sum(1 for r in rows if r["done"]); items = []
        for r in sorted(rows, key=lambda x: x["rsort"]):
            ok = bool(r["done"]); icon = ic(PRAYER_ICONS.get(r["rkey"], "NIGHTS_STAY"), "outlined"); missed = store.is_missed(r)
            if missed:
                items.append(ft.Container(ft.Column([
                    ft.Container(ft.Icon(ic("CLOSE"), size=20, color=P["red"]), width=44, height=44, border_radius=22, alignment=ft.alignment.center,
                                 bgcolor=alpha(P["red"], .10), border=ft.border.all(1.2, alpha(P["red"], .7))),
                    ft.Text(short.get(r["rkey"], r["title"]), size=11, color=P["red"], font_family=ui.family(None), style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH))],
                    spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER), expand=True, padding=ft.padding.symmetric(vertical=6)))
                continue
            glyph = ft.Icon(ic("CHECK") if ok else icon, size=21, color=P["on_accent"] if ok else P["violet"])
            disc = ft.Container(glyph, width=44, height=44, border_radius=22, alignment=ft.alignment.center,
                                bgcolor=P["gold"] if ok else alpha(P["violet"], .12), animate=anim(300), border=None if ok else ft.border.all(1, alpha(P["violet"], .30)),
                                shadow=ft.BoxShadow(blur_radius=14, spread_radius=-2, color=alpha(P["gold"], .5), offset=ft.Offset(0, 4)) if ok else None)
            if ok and S.get("pop") == r["id"]: S["pop"] = None; pop_in(disc, .02, .5)
            items.append(ft.Container(ft.Column([disc,
                txt(short.get(r["rkey"], r["title"]), 11, ft.FontWeight.W_600 if ok else None, "gold" if ok else "muted")], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                expand=True, padding=ft.padding.symmetric(vertical=6), border_radius=16, ink=not store.is_locked_routine(r), on_click=None if store.is_locked_routine(r) else pray_hit(r["id"], ok, disc, glyph, icon)))
        head = ft.Row([ft.Row([ibadge(ic("NIGHTS_STAY", "outlined"), "violet", 30, radius=10), txt("نمازها", 15, ft.FontWeight.W_800)], spacing=8),
                       chip(f"{fa(done)} از {fa(len(rows))}", "gold" if done == len(rows) else "violet")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        return card(ft.Column([head, ft.Row(items, spacing=2)], spacing=8), pad=14, margin=ft.margin.only(bottom=4))

    # ---- تصویر قهرمان: پیش‌فرض یا عکس کاربر، با موقعیت برش
    HERO_EXTRA = 90
    def hero_image(pos, top_h, width=None, name=None):
        """تصویر قهرمان داخل Stack (کمی بلندتر از قاب تا اسلایدر موقعیت بتواند آن را بالا/پایین ببرد). name: فایل پیش‌نمایش‌شده."""
        extra = HERO_EXTRA * top_h / max(1, hero_h()); kw = dict(left=0, right=0, top=-extra * pos, height=top_h + extra, fit=ft.ImageFit.COVER)
        path = os.path.join(data_dir(), name) if name else hero_mod.current(store)
        if path:
            try: return ft.Image(src_base64=hero_mod.b64(path), **kw)
            except Exception as ex: log_error("تصویر قهرمان", ex)          # فایل خراب: بی‌صدا تصویر پیش‌فرض
        return ft.Image(src=hero_mod.DEFAULT_SRC, **kw)

    def hero_h(): return int(max(250, min(340, (M.page_w or 400) * .82)))

    def hero_dialog():
        """تغییر تصویر قهرمان: انتخاب از گالری، پیش‌نمایش با موقعیت برش، بازگردانی پیش‌فرض."""
        hw = max(200, (M.page_w or 400) - 36); pw = 300; ph = int(pw * hero_h() / hw)
        st = {"new": None, "reset": False, "pos": hero_mod.position(store)}
        cur_name = os.path.basename(hero_mod.current(store) or "") or None
        box = ft.Container(height=ph, width=pw, border_radius=18, clip_behavior=ft.ClipBehavior.ANTI_ALIAS, bgcolor=P["bg2"])
        def shown(): return None if st["reset"] else (st["new"] or cur_name)
        def paint(update=True):
            box.content = ft.Stack([hero_image(st["pos"], ph, name=shown())], width=pw, height=ph)
            if update: box.update()
        def on_pos(e): st["pos"] = float(e.control.value); paint()
        slider = ft.Slider(min=0, max=1, value=st["pos"], divisions=20, on_change=on_pos, active_color=P["gold"])
        def got(ev):
            files = getattr(ev, "files", None)
            if not files: return
            try: name = hero_mod.import_image(files[0].path)
            except hero_mod.HeroError as ex: snack(str(ex), False); return
            except Exception as ex: log_error("انتخاب تصویر قهرمان", ex); snack("خواندن تصویر ممکن نشد", False); return
            if st["new"] and st["new"] != cur_name:
                try: os.remove(os.path.join(data_dir(), st["new"]))
                except OSError: pass
            st["new"], st["reset"] = name, False; paint()
        def pick(e):
            fp.on_result = got
            try: fp.pick_files(dialog_title="انتخاب تصویر", file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["jpg", "jpeg", "png", "webp"], allow_multiple=False)
            except Exception as ex: log_error("pick hero", ex); snack("انتخاب تصویر در این دستگاه ممکن نشد", False)
        def reset(e): st["reset"], st["new"], st["pos"] = True, None, .5; slider.value = .5; paint(); slider.update()
        def save():
            if st["reset"]: store.setpref("hero_file", ""); store.setpref("hero_pos", "0.5"); keep = None
            else:
                keep = st["new"] or cur_name
                store.setpref("hero_file", keep or ""); store.setpref("hero_pos", f"{st['pos']:.2f}")
            hero_mod.prune(keep); render()
        paint(False)
        dialog("تصویر صفحهٔ امروز", [box, ft.Row([btn("انتخاب از گالری", pick, ic("PHOTO_LIBRARY", "outlined")), ft.TextButton("تصویر پیش‌فرض", on_click=reset, style=ft.ButtonStyle(color=P["muted"]))], spacing=6, wrap=True),
                                      txt("موقعیت برش (بالا ← پایین)", 12, color="muted"), slider,
                                      txt("متن‌ها روی تیره‌کنندهٔ ملایم می‌آیند؛ پس با هر عکسی خوانا می‌مانند.", 11, color="muted")], save, "ذخیره", icon="IMAGE")

    def glass_btn(icon, tip, on_click):
        return ft.Container(ft.IconButton(ic(icon, "outlined"), icon_color=LIGHT_TXT, icon_size=21, tooltip=tip, on_click=on_click), width=46, height=46, border_radius=23, alignment=ft.alignment.center,
                            bgcolor=alpha("#0A1128", .42), border=ft.border.all(1, alpha("#FFFFFF", .20)))

    def hero_card(greet, streak):
        h = hero_h(); w = max(200, (M.page_w or 400) - 36)
        sc = lambda a_: alpha("#080D20", a_)
        top_scrim = ft.Container(left=0, right=0, top=0, height=int(h * .5), gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=[sc(.72), sc(0)]))
        bot_scrim = ft.Container(left=0, right=0, bottom=0, height=int(h * .62), gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=[sc(0), sc(.30), sc(.78)]))
        brand = ft.Row([brand_mark(38, 13), ft.Column([txt("Get Better", 18, ft.FontWeight.W_800, LIGHT_TXT), txt(meta.TAGLINE, 10, color=alpha(LIGHT_TXT, .78))], spacing=0)], spacing=10, expand=True)
        tools = ft.Row([glass_btn("AUTO_AWESOME", "برنامهٔ هوشمند", lambda e: smart_plan()), glass_btn("SETTINGS", "تنظیمات", lambda e: (S.update(tab=5), render()))], spacing=8)
        badges = [chip(f"{fa(streak)} روز پیاپی", "red", ic("LOCAL_FIRE_DEPARTMENT", "outlined"))] if streak else []
        sel = date.fromisoformat(S["day"]); is_today = sel == today()
        info = ft.Column([txt(f"{greet} بخیر", 30, ft.FontWeight.W_800, LIGHT_TXT), txt(J.fmt(sel if not is_today else today(), "full"), 13, color=alpha(LIGHT_TXT, .85)), ft.Row(badges, spacing=6)], spacing=4)
        change = glass_btn("PHOTO_CAMERA", "تغییر تصویر", lambda e: hero_dialog())
        over = ft.Container(ft.Column([ft.Row([brand, tools], vertical_alignment=ft.CrossAxisAlignment.CENTER), ft.Row([ft.Container(info, expand=True), change], vertical_alignment=ft.CrossAxisAlignment.END)],
                                      alignment=ft.MainAxisAlignment.SPACE_BETWEEN, expand=True), left=14, right=14, top=12, bottom=14, data="hero_content")
        bg = ft.Container(left=0, right=0, top=0, bottom=0, gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=[P["bg2"], P["bg"]]))   # پشتیبان اگر تصویر بالا نیامد
        stack = ft.Stack([bg, hero_image(hero_mod.position(store), h), top_scrim, bot_scrim, over], width=w, height=h)
        return ft.Container(stack, width=w, height=h, border_radius=32, clip_behavior=ft.ClipBehavior.ANTI_ALIAS, border=ft.border.all(1, alpha(P["gold"], .28)),
                            shadow=ft.BoxShadow(blur_radius=30, spread_radius=-8, color=alpha("#000000", .6) if ui.is_dark() else alpha(ui.SHADOW_TINT, .30), offset=ft.Offset(0, 14)), data="hero")

    def level_card(streak):
        xp = store.xp(); lvl = level_for_xp(xp); lo, hi = xp_threshold(lvl), xp_threshold(lvl + 1); frac = min(1, (xp - lo) / max(1, hi - lo))
        rep = store.weekly_report()["cur"]
        lvl_ring = ring(frac, 96, 8, "gold", key="lvl", center=ft.Column([txt(fa(lvl), 28, ft.FontWeight.W_800, "gold"), txt("سطح", 10, color="muted")], spacing=0,
                        horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER))
        head = ft.Row([lvl_ring, ft.Column([ft.Row([ibadge(ic("MILITARY_TECH", "outlined"), "gold", 30, radius=10), txt(level_title(lvl), 20, ft.FontWeight.W_800, "gold")], spacing=8),
                       ft.Row([ft.Icon(ic("BOLT", "outlined"), size=15, color=P["gold"]), count_up(xp, 15, ft.FontWeight.W_800, None, " XP", key="xp")], spacing=3),
                       txt(f"{fa(hi - xp)} XP تا سطح {fa(lvl + 1)}", 11, color="muted")], spacing=4, expand=True)], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        bar = pbar(frac, "gold", 7, off=36 + 32, key="xpbar")
        week = ft.Row([stat_tile(ic("MENU_BOOK", "outlined"), "violet", (fa(f"{rep['minutes'] // 60}:{rep['minutes'] % 60:02d}") if rep["minutes"] >= 60 else f"{fa(rep['minutes'])} د"), "مطالعهٔ هفته"),
                       stat_tile(ic("TASK_ALT", "outlined"), "green", fa(rep["done"]), "کار انجام‌شده"),
                       stat_tile(ic("CALENDAR_MONTH", "outlined"), "blue", f"{fa(rep['days'])} از ۷", "روز فعال")], spacing=8)
        goal_txt = store.pref("goal")
        goal = ft.Container(ft.Row([ft.Icon(ic("FLAG", "outlined"), size=17, color=P["gold"]), txt(goal_txt or "هدف اصلی‌ات را تعیین کن", 13, ft.FontWeight.W_600, None if goal_txt else "muted", expand=True, max_lines=2, overflow=ft.TextOverflow.ELLIPSIS),
                            ft.Icon(ic("EDIT", "outlined"), size=16, color=P["muted"])], spacing=8), padding=ft.padding.symmetric(horizontal=12, vertical=10), border_radius=16, ink=True,
                            bgcolor=alpha(P["gold"], .08), border=ft.border.all(1, alpha(P["gold"], .20)), on_click=lambda e: set_goal())
        return card(ft.Column([head, bar, week, goal], spacing=12), pad=16, grad=True, radius=28)

    def week_card():
        sel = date.fromisoformat(S["day"]); ws = J.week_start(sel); load = store.day_load(ws); tiles = []
        for i in range(7):
            d = ws + timedelta(days=i); k = d.isoformat(); tot, dn = load[k]; is_sel = k == S["day"]
            dot = P["green"] if tot and dn == tot else (P["gold"] if tot else "transparent")
            tiles.append(ft.Container(ft.Column([txt(J.WEEKDAY_SHORT[d.weekday()], 11, color=P["on_accent"] if is_sel else "muted"),
                txt(fa(J.to_jalali(d)[2]), 16, ft.FontWeight.W_800, P["on_accent"] if is_sel else None),
                ft.Container(width=6, height=6, border_radius=3, bgcolor=P["on_accent"] if (is_sel and tot) else dot, animate=anim(250))], spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                padding=ft.padding.symmetric(vertical=9), border_radius=18, expand=True, ink=True, on_click=lambda e, k=k: (S.update(day=k), render()),
                bgcolor=P["gold"] if is_sel else alpha(P["text"], .05), animate=anim(260, EASE), scale=1.04 if is_sel else 1, animate_scale=anim(300, BACK),
                shadow=ft.BoxShadow(blur_radius=16, spread_radius=-2, color=alpha(P["gold"], .45), offset=ft.Offset(0, 5)) if is_sel else None,
                border=ft.border.all(1.4, P["gold"]) if d == today() and not is_sel else ft.border.all(1, alpha(P["line"], .06))))
        jy, jm, _ = J.to_jalali(sel)
        shift = lambda n: (lambda e: (S.update(day=(sel + timedelta(days=n)).isoformat()), render()))
        head = ft.Row([ft.Row([ft.Icon(ic("CALENDAR_TODAY", "outlined"), size=16, color=P["gold"]), txt(f"{J.MONTHS[jm - 1]} {fa(jy)}", 14, ft.FontWeight.W_700)], spacing=6),
            ft.Row([chip("امروز", "gold", ic("TODAY", "outlined"), on_click=lambda e: (S.update(day=today().isoformat()), render())) if S["day"] != today().isoformat() else ft.Container(),
                    ft.IconButton(ic("CHEVRON_RIGHT"), icon_color=P["muted"], on_click=shift(-7)), ft.IconButton(ic("CHEVRON_LEFT"), icon_color=P["muted"], on_click=shift(7))], spacing=0)],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        return card(ft.Column([head, ft.Row(tiles, spacing=6)], spacing=6), pad=ft.padding.only(left=10, right=10, top=6, bottom=12), radius=26)

    def task_card(r):
        """کارت بزرگ کار: عنوان، ساعت، درس (دسته)، اولویت، XP و تیک یک‌لمسی. (حالت تمرکز عمداً اینجا نیست.)"""
        done = bool(r["done"]); pname, pcol = PRIO[max(0, min(2, r["priority"]))]
        title_w = ft.Text(r["title"], size=16, color=P["muted"], font_family=ui.family(None), style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)) if done else txt(r["title"], 16, ft.FontWeight.W_700)
        meta_ = []
        if r["time"]: meta_.append(chip(time_label(r), "gold", ic("SCHEDULE", "outlined")))
        elif r["minutes"]: meta_.append(chip(fmt_minutes(r["minutes"]), "muted", ic("TIMER", "outlined")))
        if r["subject"]: meta_.append(chip(r["subject"], "violet", ic("MENU_BOOK", "outlined")))
        meta_.append(chip(pname, pcol, ic("FLAG", "outlined")))
        if r["repeat"]: meta_.append(chip(REPEATS[r["repeat"]], "blue", ic("REPEAT")))
        meta_.append(chip(f"{fa(r['xp'])} XP", "gold", ic("BOLT", "outlined")))
        if r["time"] and r["minutes"]: meta_.insert(1, chip(fmt_minutes(r["minutes"]), "muted", ic("TIMER", "outlined")))
        menu = ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], tooltip="گزینه‌ها", items=[
            ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=r: mission_form(x)),
            ft.PopupMenuItem(text="انتقال به فردا", icon=ic("EVENT_REPEAT"), on_click=lambda e, i=r["id"]: (store.move_tomorrow(i), render())),
            ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, i=r["id"]: confirm("حذف", "حذف شود؟ امتیاز قبلی پاک نمی‌شود.", lambda: (store.delete_mission(i), render())))])
        strip = ft.Container(width=4, height=44, border_radius=4, bgcolor=P["green"] if done else P[pcol], opacity=.9)
        body = ft.Column([title_w, ft.Row(meta_, spacing=6, wrap=True, run_spacing=6)], spacing=8, expand=True)
        return ft.Container(ft.Row([strip, check_button(r, 32), ft.Container(body, expand=True, on_click=lambda e, x=r: mission_form(x), ink=True, border_radius=12, padding=ft.padding.symmetric(vertical=4)), menu],
                                   vertical_alignment=ft.CrossAxisAlignment.CENTER, spacing=4),
                            padding=ft.padding.only(left=4, right=12, top=12, bottom=12), margin=ft.margin.only(bottom=10), border_radius=22,
                            bgcolor=alpha(P["green"], .06) if done else alpha(P["text"], .045 if ui.is_dark() else .03),
                            border=ft.border.all(1, alpha(P["green"], .28) if done else alpha(P["line"], .08)))

    def report_card(rows):
        done = sum(1 for r in rows if r["done"]); total = len(rows); left_n = total - done; pct = (done / total) if total else 0
        x = store.one("SELECT COALESCE(SUM(xp),0) n FROM xp_ledger WHERE date(at)=?", (S["day"],))["n"]
        msg = ("روز بی‌برنامه‌ای است؛ یک کار کوچک اضافه کن" if not total else "شروع کن؛ اولین قدم از همه سخت‌تر است" if done == 0 else "عالی پیش می‌روی؛ ادامه بده" if pct < .5 else
               "چیزی به پایان نمانده، فشار آخر!" if pct < 1 else "امروز را کامل کردی؛ آفرین!")
        col = "green" if pct >= .8 else "gold"
        rg = ring(pct, 84, 9, col, key="rep", center=txt(fa(round(pct * 100)) + "٪", 17, ft.FontWeight.W_800, col))
        line = lambda c, t, v: ft.Row([ft.Container(width=8, height=8, border_radius=4, bgcolor=P[c]), txt(t, 12, color="muted", expand=True), txt(v, 13, ft.FontWeight.W_800)], spacing=8)
        return card(ft.Column([ft.Row([ft.Row([ibadge(ic("ASSESSMENT", "outlined"), "green", 30, radius=10), txt("گزارش عملکرد امروز", 15, ft.FontWeight.W_800)], spacing=8),
                                        chip("گزارش کامل", "gold", ic("ARTICLE", "outlined"), on_click=lambda e: daily_report())], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                               ft.Row([rg, ft.Column([line("green", "انجام‌شده", fa(done)), line("muted", "باقی‌مانده", fa(left_n)), line("gold", "XP کسب‌شده", "+" + fa(max(0, x)))], spacing=7, expand=True)], spacing=16,
                                      vertical_alignment=ft.CrossAxisAlignment.CENTER),
                               ft.Row([ft.Icon(ic("LIGHTBULB", "outlined"), size=16, color=P["gold"]), txt(msg, 12, ft.FontWeight.W_600, expand=True)], spacing=8)], spacing=12), pad=16, radius=26)

    def page_home():
        store.ensure_day(S["day"]); store.settle_missed_routines()
        streak, _ = store.streaks()
        h = datetime.now().hour; greet = "شب" if h >= 21 or h < 4 else "صبح" if h < 12 else "روز" if h < 17 else "عصر"
        rows = store.missions_on(S["day"])
        ci, cc, ct, cs = store.coach()
        coach = card(ft.Row([ibadge(ic(ci, "outlined"), cc, 42, filled=True), ft.Column([txt(ct, 14, ft.FontWeight.W_700, max_lines=2), txt(cs, 12, color="muted", max_lines=3)], spacing=2, expand=True)], spacing=12),
                     tint=cc, pad=14, radius=22, shadow=False)
        out = [hero_card(greet, streak), level_card(streak), coach, week_card()]

        over = store.overdue()
        if over and S["day"] == today().isoformat():
            oldest = min(r["date"] for r in over)
            out.append(card(ft.Row([ibadge(ic("WARNING_AMBER", "outlined"), "red", 40), ft.Column([txt(f"{fa(len(over))} کار عقب‌افتاده", 14, ft.FontWeight.W_700),
                txt(f"قدیمی‌ترین: {J.fmt(oldest, 'long')} • به امروز منتقلشان کن", 11, color="muted")], spacing=2, expand=True),
                chip("انتقال به امروز", "red", ic("EAST"), on_click=lambda e: (store.move_overdue_to_today(), render()))], spacing=10), tint="red", pad=12, radius=22, shadow=False))
        due = store.due_topics()
        if due:
            names = "، ".join(t["name"] for t in due[:3]) + ("…" if len(due) > 3 else "")
            out.append(card(ft.Row([ibadge(ic("AUTO_AWESOME", "outlined"), "gold", 40), ft.Column([txt(f"{fa(len(due))} مبحث آمادهٔ مرور است", 14, ft.FontWeight.W_700), txt(names, 11, color="muted", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS)], spacing=2, expand=True),
                chip("برنامهٔ هوشمند", "gold", ic("AUTO_AWESOME", "outlined"), on_click=lambda e: smart_plan())], spacing=10), tint="gold", pad=12, radius=22, shadow=False))

        prayers = [r for r in rows if is_prayer(r)]; routine = sorted([r for r in rows if r["routine_id"] is not None and not is_prayer(r)], key=lambda r: (r["done"], r["rsort"]))
        tasks = [r for r in rows if r["routine_id"] is None and (r["kind"] or "task") == "task"]; chores = [r for r in rows if r["routine_id"] is None and (r["kind"] or "task") == "chore"]

        # ----- کارهای امروز: بخش اصلی و بزرگ صفحه
        mine = tasks + chores; mdone = sum(1 for r in mine if r["done"]); total_min = sum(r["minutes"] for r in tasks if not r["done"])
        label = "کارهای امروز" if S["day"] == today().isoformat() else f"کارهای {J.fmt(S['day'], 'long')}"
        frac = (mdone / len(mine)) if mine else 0
        head = ft.Column([ft.Row([ft.Row([ibadge(ic("CHECKLIST", "outlined"), "gold", 34, radius=12), txt(label, 20, ft.FontWeight.W_800)], spacing=10),
                                   chip(f"{fa(mdone)} از {fa(len(mine))}", "green" if mine and mdone == len(mine) else "gold", ic("TASK_ALT", "outlined"))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                          pbar(frac, "green" if mine and mdone == len(mine) else "gold", 8, off=36 + 32, key="tasksbar"),
                          ft.Row([txt(f"{fa(round(frac * 100))}٪ انجام شد", 12, color="muted"), txt(f"{fmt_minutes(total_min)} کار باقی‌مانده" if total_min else "", 12, color="muted")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)], spacing=10)
        body_t = [task_card(r) for r in tasks] or [empty(ic("TASK_ALT", "outlined"), "کاری برای این روز نداری.\nبا دکمه ＋ بساز یا برنامهٔ هوشمند را امتحان کن", btn("برنامهٔ هوشمند", lambda e: smart_plan(), ic("AUTO_AWESOME", "outlined"), False))]
        out.append(card(ft.Column([head, ft.Container(height=2), *body_t], spacing=8), pad=16, radius=28, margin=ft.margin.only(top=4)))

        out.append(section("ریزه‌کارها", txt(f"{fa(sum(1 for r in chores if r['done']))} از {fa(len(chores))}", 12, color="muted") if chores else None, ic("PLAYLIST_ADD_CHECK", "outlined")))
        def quick_chore(e):
            v = (e.control.value or "").strip()
            if not v: return
            q = quickadd.parse(v, today()); day = q["date"] or S["day"]; is_task = bool(q["time"] or q["minutes"])
            store.save_mission(q["title"], "", q["minutes"] or (30 if q["time"] else 0), q["priority"], day, kind="task" if is_task else "chore", time=q["time"])
            render()
            if q["date"] or is_task or q["priority"] > 1:
                bits = ([J.fmt(day, "long")] if day != S["day"] or q["date"] else []) + ([f"ساعت {fa(q['time'])}"] if q["time"] else []) + ([f"{fa(q['minutes'])} دقیقه"] if q["minutes"] else []) + (["مهم"] if q["priority"] > 1 else [])
                snack(f"«{q['title']}» اضافه شد • " + " • ".join(bits))
        out.append(field("ریزه‌کار جدید… مثلاً: فردا ساعت ۱۶ حل تمرین ۴۵ دقیقه مهم", prefix_icon=ic("ADD_TASK", "outlined"), on_submit=quick_chore))
        out += [mission_tile(r, True) for r in chores]

        if prayers: out.append(prayer_card(prayers))
        if routine:
            out.append(section("روتین امروز", chip("مدیریت", "gold", ic("TUNE"), on_click=lambda e: (S.update(tab=6, rt_back=S["tab"]), render())), ic("EVENT_REPEAT", "outlined")))
            out += [mission_tile(r, True) for r in routine]
        out.append(report_card([r for r in rows if r["routine_id"] is None]))
        return out + [spacer()]

    def pulse_wrap(c):
        w = ft.Container(c); pulse(w, 1.035); return w

    def daily_report():
        d = S["day"]; rows = store.missions_on(d); mine = [r for r in rows if r["routine_id"] is None]; c = sum(1 for r in mine if r["done"])
        rt = [r for r in rows if r["routine_id"] is not None]; pr = [r for r in rt if is_prayer(r)]
        x = store.one("SELECT COALESCE(SUM(xp),0) n FROM xp_ledger WHERE date(at)=?", (d,))["n"]; f = store.focus_seconds(d) // 60
        left = [r["title"] for r in mine if not r["done"]]
        def line(icon, col, text): return ft.Row([ibadge(ic(icon), col, 30, radius=10), txt(text, 14)], spacing=10)
        ctl = [line("TASK_ALT", "blue", f"کار و ریزه‌کار انجام‌شده: {fa(c)} از {fa(len(mine))}"), line("BOLT", "gold", f"XP کسب‌شده: {fa(x)}"), line("CENTER_FOCUS_STRONG", "green", f"زمان تمرکز: {fmt_minutes(f)}")]
        if pr: ctl.append(line("NIGHTS_STAY", "violet", f"نمازها: {fa(sum(1 for r in pr if r['done']))} از {fa(len(pr))}"))
        other = [r for r in rt if r not in pr]
        if other: ctl.append(line("EVENT_REPEAT", "blue", f"روتین: {fa(sum(1 for r in other if r['done']))} از {fa(len(other))}"))
        if left: ctl += [txt("باقی‌مانده:", 12, color="muted"), *[txt("• " + t, 12) for t in left[:6]]]
        else: ctl.append(txt("همه‌چیز انجام شد، دمت گرم!" if mine else "برای این روز کاری ثبت نشده بود.", 12, color="muted"))
        dialog("گزارش " + J.fmt(d), ctl, lambda: True, "باشه", cancel=False, icon="ASSESSMENT")

    # ================= روتین‌ها =================
    def days_label(days):
        return "هر روز" if len(days) == 7 else "، ".join(J.WEEKDAYS[d] for d in WEEK_ORDER if d in days)

    def routine_form(row=None):
        """روتین = کاری که همیشه در برنامه هست و هر روز (یا روزهای انتخابی) خودکار اضافه و صفر می‌شود."""
        k0 = row["kind"] if row else "chore"
        kseg = seg(k0, list(KINDS_TASK.items()))
        t = field("عنوان روتین (مثلاً ورزش صبحگاهی)", row["title"] if row else "", autofocus=True)
        tm = time_field("ساعت (اختیاری، مثل ۰۶:۳۰)", row["time"] if row else ""); mins = num_field("مدت (دقیقه، اختیاری)", str(row["minutes"]) if row and row["minutes"] else "")
        task_box = ft.Column([tm, mins], spacing=10, visible=k0 == "task")
        def kind_changed(e): task_box.visible = list(e.control.selected)[0] == "task"; task_box.update()
        kseg.on_change = kind_changed
        sel = set(store.routine_days(row)) if row else set(WEEK_ORDER)
        def day_chip(d):
            lab = txt(J.WEEKDAYS[d], 12, ft.FontWeight.W_600, P["muted"]); c = ft.Container(lab, padding=ft.padding.symmetric(horizontal=12, vertical=7), border_radius=20, animate=anim(220), animate_scale=anim(200, BACK))
            def paint(): on = d in sel; c.bgcolor = P["gold"] if on else alpha(P["muted"], .14); lab.color = P["on_accent"] if on else P["muted"]; c.scale = 1.06 if on else 1
            def tap(e): sel.symmetric_difference_update({d}); paint(); c.update()
            c.on_click = tap; paint(); return c
        def save():
            if not t.value.strip(): t.error_text = "عنوان الزامی است"; t.update(); return False
            if not sel: snack("حداقل یک روز را انتخاب کن", False); return False
            k = list(kseg.selected)[0]; time_s, m = "", 0
            if k == "task":
                tm.error_text = mins.error_text = None
                time_s = norm_time(tm.value)
                if time_s is None: tm.error_text = "ساعت نامعتبر است (۰۰:۰۰ تا ۲۳:۵۹)"; tm.update(); return False
                m = ui.to_int(mins.value) if mins.value.strip() else 0
                if m is None: mins.error_text = "عدد وارد کنید"; mins.update(); return False
            store.save_routine(t.value.strip(), k, m, time_s, sel, row["id"] if row else None); render()
        dialog("ویرایش روتین" if row else "روتین جدید", [kseg, t, task_box, txt("روزهای تکرار", 12, color="muted"), ft.Row([day_chip(d) for d in WEEK_ORDER], spacing=6, run_spacing=6, wrap=True)], save, icon="EVENT_REPEAT")

    def page_routines():
        out = [ft.Row([ft.IconButton(ic("ARROW_FORWARD"), on_click=lambda e: go_back()), title("روتین‌ها", "کارهای همیشگی؛ هر روز خودکار اضافه و از نو شروع می‌شوند")]), btn("روتین جدید", lambda e: routine_form(), ic("ADD")),
               card(ft.Row([ibadge(ic("INFO"), "gold", 34, radius=11), txt("نمازهای پنجگانه به‌صورت پیش‌فرض اینجا هست. هر روز تیک‌ها صفر می‌شوند و تاریخچهٔ روزهای قبل می‌ماند. با دکمهٔ «روتین جدید» روتین دلخواه بساز.", 12, color="muted", expand=True)], spacing=10), tint="gold", pad=12, shadow=False)]
        for r in store.routines():
            days = store.routine_days(r); kind = KINDS_TASK.get(r["kind"], "ریزه‌کار"); is_pr = (r["key"] or "").startswith("prayer")
            sub = f"{kind} • {days_label(days)}" + (f" • {fa(r['time'])}" if r["time"] else "") + (f" • {fmt_minutes(r['minutes'])}" if r["minutes"] else "")
            out.append(card(ft.Row([ibadge(ic(PRAYER_ICONS.get(r["key"], "NIGHTS_STAY") if is_pr else "EVENT_REPEAT"), "gold" if r["active"] else "muted", 40),
                ft.Column([txt(r["title"], 14, ft.FontWeight.W_600, None if r["active"] else "muted"), txt(sub, 11, color="muted")], spacing=2, expand=True),
                ft.Switch(value=bool(r["active"]), active_color=P["gold"], on_change=lambda e, i=r["id"]: (store.set_routine_active(i, e.control.value), render())),
                ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=[
                    ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=r: routine_form(x)),
                    ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, i=r["id"]: confirm("حذف روتین", "روتین از این به بعد حذف شود؟ سابقهٔ روزهای انجام‌شده می‌ماند.", lambda: (store.delete_routine(i), render())))])], spacing=10),
                pad=ft.padding.only(left=14, right=6, top=8, bottom=8), margin=ft.margin.only(bottom=8)))
        if not store.routines(): out.append(empty(ic("EVENT_REPEAT"), "هنوز روتینی نداری. با «روتین جدید» بساز"))
        return out + [spacer()]

    def set_exam():
        dfield, get, _ = jdate_field("تاریخ آزمون", store.pref("exam_date") or (today() + timedelta(days=60)).isoformat()); holder = {}
        def clear(e): store.setpref("exam_date", ""); page.close(holder["d"]); render()
        def save(): store.setpref("exam_date", get()); render()
        holder["d"] = dialog("تاریخ آزمون", [dfield, ft.TextButton("حذف تاریخ آزمون", on_click=clear, style=ft.ButtonStyle(color=P["red"]))], save, icon="EVENT_AVAILABLE")
    def set_goal():
        f = field("هدفت چیست؟ (مثلاً قبولی در مدرسه نمونه)", store.pref("goal"))
        dialog("هدف من", [f], lambda: (store.setpref("goal", f.value.strip()), render()), icon="FLAG")

    # ================= تنظیمات =================
    def page_settings():
        def theme(e): store.setpref("theme", "dark" if e.control.value else "light"); apply_theme(); build_chrome(); render()
        def set_pref(key, label, opts):
            cur = str(store.pref(key)); s = seg(cur, [(o, fa(o)) for o in opts])
            dialog(label, [s], lambda: (store.setpref(key, list(s.selected)[0]), render()), icon="TUNE")
        def do_restore(text):
            try: store.restore_text(text)
            except Exception as ex: log_error("بازیابی", ex); snack(f"بازیابی انجام نشد: {ex}", False); return
            snack("بازیابی انجام شد"); apply_theme(); build_chrome(); render()
        def save_as(e):
            text, name = store.backup_text(), store.export_filename()
            def done(ev):
                path = getattr(ev, "path", None)
                if not path: return                                   # انصراف
                try:
                    if not os.path.exists(path) or os.path.getsize(path) == 0:
                        with open(path, "w", encoding="utf-8") as f: f.write(text)
                    snack("پشتیبان ذخیره شد")
                except OSError as ex: log_error("ذخیرهٔ پشتیبان", ex); snack("ذخیره در این مکان ممکن نشد؛ «کپی پشتیبان» را امتحان کن", False)
            fp.on_result = done
            try:
                try: fp.save_file(dialog_title="ذخیرهٔ پشتیبان", file_name=name, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"], src_bytes=text.encode("utf-8"))
                except TypeError: fp.save_file(dialog_title="ذخیرهٔ پشتیبان", file_name=name, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"])
            except Exception as ex: log_error("save_file", ex); snack("انتخاب مکان در این دستگاه ممکن نشد؛ «کپی پشتیبان» را امتحان کن", False)
        def pick_restore(e):
            def done(ev):
                files = getattr(ev, "files", None)
                if not files: return
                try:
                    with open(files[0].path, encoding="utf-8") as f: text = f.read()
                except Exception as ex: log_error("خواندن فایل پشتیبان", ex); snack("خواندن فایل ممکن نشد؛ از «بازیابی از متن» استفاده کن", False); return
                confirm("بازیابی", "اطلاعات فعلی با این پشتیبان جایگزین می‌شود (از وضعیت فعلی یک نسخهٔ امن گرفته می‌شود). ادامه می‌دهی؟", lambda: do_restore(text))
            fp.on_result = done
            try: fp.pick_files(dialog_title="انتخاب فایل پشتیبان", file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["json"], allow_multiple=False)
            except Exception as ex: log_error("pick_files", ex); snack("انتخاب فایل در این دستگاه ممکن نشد؛ از «بازیابی از متن» استفاده کن", False)
        def auto_list(e):
            items = store.list_backups()[:8]
            if not items: snack("هنوز پشتیبان خودکاری ساخته نشده", False); return
            holder = {}; rows = []
            for pth, mt in items:
                nm = os.path.basename(pth); kind = "پیش از بازیابی" if nm.startswith("pre-restore") else "پیش از پاک‌سازی" if nm.startswith("pre-wipe") else "خودکار روزانه"
                when = datetime.fromtimestamp(mt)
                def pick(ev, pth=pth):
                    page.close(holder["d"])
                    def go():
                        try:
                            with open(pth, encoding="utf-8") as f: text = f.read()
                            do_restore(text)
                        except OSError as ex: log_error("خواندن پشتیبان خودکار", ex); snack("خواندن پشتیبان ممکن نشد", False)
                    confirm("بازیابی", "اطلاعات فعلی با این نسخه جایگزین می‌شود. ادامه می‌دهی؟", go)
                rows.append(card(ft.Row([ibadge(ic("HISTORY"), "blue", 34, radius=11), ft.Column([txt(kind, 13, ft.FontWeight.W_600), txt(f"{J.fmt(when.date())} • {fa(when.strftime('%H:%M'))}", 11, color="muted")], spacing=0, expand=True),
                                         ft.Icon(ic("RESTORE"), size=18, color=P["muted"])], spacing=10), pad=10, radius=18, shadow=False, on_click=pick))
            holder["d"] = dialog("پشتیبان‌های خودکار", [txt("برای بازگردانی روی یک نسخه بزن. هر روز یک نسخه خودکار ساخته می‌شود.", 12, color="muted"), *rows], lambda: True, "بستن", cancel=False, icon="HISTORY")
        def export(e):
            p = os.path.join(data_dir(), store.export_filename())
            try: store.backup(p)
            except Exception as ex: snack(str(ex), False); return
            try: page.set_clipboard(store.backup_text()); extra = "متن پشتیبان در کلیپ‌بورد هم کپی شد؛ می‌توانی در یادداشت‌های گوشی یا پیام‌رسان ذخیره‌اش کنی."
            except Exception: extra = ""
            dialog("پشتیبان ذخیره شد", [ft.Text(p, size=12, selectable=True, color=P["muted"]), txt(extra, 12, color="muted")], lambda: True, "باشه", cancel=False, icon="CLOUD_DONE")
        def restore_text(e):
            f = field("متن پشتیبان را اینجا بچسبان", multiline=True, min_lines=5, max_lines=8)
            def go():
                try: store.restore_text(f.value)
                except Exception as ex: snack(f"متن معتبر نیست: {ex}", False); return False
                snack("بازیابی انجام شد"); apply_theme(); build_chrome(); render()
            dialog("بازیابی از متن", [f], go, "بازیابی", icon="CONTENT_PASTE")
        def wipe(e):
            confirm("تأیید اول", "تمام اطلاعات برای همیشه پاک می‌شود. ادامه؟",
                    lambda: confirm("تأیید نهایی", "این کار قابل بازگشت نیست. مطمئنی؟", lambda: (store.clear_all(), snack("پاک شد؛ نسخهٔ امن در «پشتیبان‌های خودکار» است"), render())))
        def row(icon, t, sub, trailing, col="gold"):
            tap = getattr(trailing, "on_click", None) if isinstance(trailing, ft.IconButton) else None      # ردیف‌های دارای ›: کل ردیف لمس‌پذیر است
            return list_row(icon, t, sub, trailing, col, on_click=tap)
        go_ = lambda f: ft.IconButton(ic("CHEVRON_LEFT"), icon_color=P["muted"], on_click=f)
        exam = store.pref("exam_date")
        logo = ft.Container(ft.Column([brand_mark(52, 18), txt("Get Better", 15, ft.FontWeight.W_800),
                            txt(f"نسخه {fa(VERSION)} • کاملاً آفلاین • هیچ اطلاعاتی از دستگاه خارج نمی‌شود", 11, color="muted", text_align=ft.TextAlign.CENTER)],
                            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6), alignment=ft.alignment.center, padding=20)
        return [ft.Row([ft.IconButton(ic("ARROW_FORWARD"), on_click=lambda e: (S.update(tab=S["nav"]), render())), title("تنظیمات")]),
                section("برنامه‌ریزی", None, ic("EVENT_NOTE")),
                group([
                row("EVENT_REPEAT", "روتین‌ها و نماز", "کارهای همیشگی که هر روز خودکار اضافه می‌شوند", go_(lambda e: (S.update(tab=6, rt_back=S["tab"]), render()))),
                row("FLAG", "هدف من", store.pref("goal") or "هنوز تعیین نشده", go_(lambda e: set_goal())),
                row("EVENT_AVAILABLE", "تاریخ آزمون", J.fmt(exam) if exam else "هنوز تعیین نشده", go_(lambda e: set_exam())),
                row("TASK_ALT", "هدف روزانه", f"{fa(store.pref_int('daily_goal', 3))} مأموریت در روز", go_(lambda e: set_pref("daily_goal", "هدف روزانه (مأموریت)", [1, 2, 3, 4, 5, 6]))),
                row("TIMER", "طول تمرکز", f"{fa(store.pref_int('pomodoro', 25))} دقیقه تمرکز، {fa(store.pref_int('break', 5))} دقیقه استراحت",
                    go_(lambda e: (set_pref("pomodoro", "طول هر دور تمرکز (دقیقه)", [15, 25, 45, 50])))),
                row("COFFEE", "طول استراحت", f"{fa(store.pref_int('break', 5))} دقیقه", go_(lambda e: set_pref("break", "طول استراحت (دقیقه)", [5, 10, 15])))]),
                section("ظاهر", None, ic("PALETTE")),
                group([row("DARK_MODE", "حالت تیره", "انتخاب تو روی همین دستگاه ذخیره می‌شود", ft.Switch(value=ui.is_dark(), active_color=P["gold"], on_change=theme), "violet")]),
                section("یادآوری", None, ic("NOTIFICATIONS")),
                group([
                row("NOTIFICATIONS", "یادآوری‌ها", f"سر ساعتِ کارها و یادآوری عصر؛ تا وقتی برنامه باز یا در پس‌زمینه است" + ("" if notify.AVAILABLE else " (پیام داخل برنامه)"),
                    ft.Switch(value=store.pref("notify_on") == "1", active_color=P["gold"], on_change=lambda e: (store.setpref("notify_on", "1" if e.control.value else "0"), render())), "gold"),
                row("SCHEDULE", "ساعت یادآوری عصر", f"{fa(store.pref_int('notify_hour', 19))}:۰۰ • اگر کار مهم یا بیشتر کارها مانده باشد", go_(lambda e: set_pref("notify_hour", "ساعت یادآوری عصر", [17, 18, 19, 20, 21])))]),
                section("داده‌ها", None, ic("STORAGE")),
                group([
                row("CLOUD_UPLOAD", "ذخیرهٔ پشتیبان", "انتخاب مکان دلخواه (حافظه، فایل‌ها، ابر)", go_(save_as), "blue"),
                row("CLOUD_DOWNLOAD", "بازیابی از فایل", "انتخاب فایل پشتیبان", go_(pick_restore), "blue"),
                row("HISTORY", "پشتیبان‌های خودکار", f"{fa(len(store.list_backups()))} نسخه • روزانه خودکار ساخته می‌شود", go_(auto_list), "blue"),
                row("CONTENT_COPY", "کپی پشتیبان", "فایل داخلی + متن در کلیپ‌بورد", go_(export), "blue"),
                row("CONTENT_PASTE", "بازیابی از متن", "متن کپی‌شدهٔ پشتیبان را بچسبان", go_(restore_text), "blue"),
                row("DELETE_FOREVER", "پاک‌سازی کامل", "با دو تأیید؛ پیش از آن نسخهٔ امن گرفته می‌شود", go_(wipe), "red")]),
                section("برنامه", None, ic("INFO")),
                group([row("PRIVACY_TIP", "درباره، حریم خصوصی و راهنما", f"نسخه {fa(VERSION)}", go_(lambda e: (S.update(tab=7), render())), "green")]),
                logo, spacer(20)]

    # ================= قاب اصلی =================
    body = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=14)
    NAVC, FAB, NAVW = [], {}, {}
    ctx = SimpleNamespace(page=page, store=store, S=S, render=lambda: render(), dialog=dialog, confirm=confirm, snack=snack, jdate_field=jdate_field, mission_form=mission_form,
                          mission_tile=mission_tile, fmt_minutes=fmt_minutes, after_action=after_action, set_exam=lambda: set_exam(), open_settings=lambda: (S.update(tab=5), render()))
    PG = pages_mod.build(ctx)
    pages = [page_home, PG.study, PG.week, PG.notes, PG.progress]        # ترتیب ناوبری: خانه | تحصیل | هفته | یادداشت‌ها | پیشرفت
    SUB = {5: page_settings, 6: page_routines, 7: lambda: page_about(), 8: PG.subject, 9: PG.note_editor}
    SHOWN = {"k": None}

    def goto(i):
        if S["tab"] == 9: PG.flush_note()
        S.update(tab=i, nav=i)
        try: paint_nav(); M.push([n["box"] for n in NAVC])      # تب انتخابی فوراً پررنگ می‌شود؛ ساخت صفحه بعدش
        except Exception as ex: log_error("goto", ex)
        render()

    def nav_metrics(cur, extra=0):
        """اندازهٔ آیتم‌های نوار پایین را از روی عرض واقعی صفحه حساب می‌کند تا در هر عرضی (حتی خیلی باریک) همهٔ آیکون‌ها کامل بمانند."""
        inner = max(240, int(M.page_w or 400)) - 28 - 16 - 2 - 6 - extra          # حاشیه‌ها + لبه‌ها + کمی اطمینان
        isz, pu, ps, lw = 23, 11, 14, NAV[cur][2]
        def need(): return 4 * (isz + 2 * pu) + (isz + 6 + lw + 2 * ps)
        while need() > inner and pu > 5: pu -= 1
        while need() > inner and ps > 9: ps -= 1
        while need() > inner and lw > 30: lw -= 2
        while need() > inner and isz > 19: isz -= 1; lw = min(lw, 36)
        while need() > inner and pu > 3: pu -= 1
        while need() > inner and lw > 0: lw -= 2
        return isz, pu, ps, max(0, lw)

    def paint_nav():
        cur = S["nav"]; plus = S["tab"] == 3                     # دکمهٔ ＋ نوار پایین فقط در یادداشت‌هاست
        isz, pu, ps, lw = nav_metrics(cur, 66 if plus else 0)
        if NAVW.get("row") is not None:
            half = lambda xs: ft.Row(xs, alignment=ft.MainAxisAlignment.SPACE_AROUND, expand=True)
            want = [half([n["box"] for n in NAVC[:2]]), NAVW["plus"], half([n["box"] for n in NAVC[2:]])] if plus else [n["box"] for n in NAVC]
            if plus != NAVW.get("plus_on"): NAVW["row"].controls = want; NAVW["plus_on"] = plus
            NAVW["box"].visible = S["tab"] != 9
        for i, n in enumerate(NAVC):
            sel = i == cur
            n["box"].bgcolor = P["gold"] if sel else "#00000000"
            n["box"].padding = ft.padding.symmetric(horizontal=ps if sel else pu, vertical=10)
            n["icon"].name = ic(NAV[i][1]) if sel else ic(NAV[i][1], "outlined")
            n["icon"].color = P["on_accent"] if sel else P["muted"]
            n["icon"].size = isz
            n["lab"].width = lw if sel else 0
            n["lab"].opacity = 1 if sel and lw >= 28 else 0
            n["box"].scale = 1.0 if sel else .96

    LASTW = {"w": None}
    def on_resize(e=None):
        update_width()
        if LASTW["w"] == M.page_w: return        # باز/بسته شدن کیبورد فقط ارتفاع را عوض می‌کند؛ page.update() وسط تایپ نباید زده شود
        LASTW["w"] = M.page_w
        try: paint_nav(); page.update()
        except Exception as ex: log_error("resize", ex)
    try: page.on_resized = on_resize
    except Exception: pass

    def reveal(ctrls):
        """ورود نرم بخش‌ها: همه با «یک» پیام و انیمیشن کوتاه (به‌جای یک پیام جدا برای هر بخش) تا تعویض تب روان بماند."""
        for c in ctrls:
            c.opacity = 0; c.offset = ft.Offset(0, .05); c.animate_opacity = anim(260, EASE); c.animate_offset = anim(300, EASE)
        def show():
            for c in ctrls: c.opacity = 1; c.offset = ft.Offset(0, 0)
            M.push(ctrls)
        M.jobs = [(0, show)] + M.jobs     # اول ورود بخش‌ها، بعد پر شدن نوار و حلقه‌ها
        M.base = .02

    RS = {"mx": threading.Lock(), "busy": False, "again": False}
    def render():
        """رندرهای هم‌زمان ادغام می‌شوند: لمس‌های پیاپی (مثلاً چند بار «هفتهٔ بعد» یا چند تیک پشت‌سرهم) در رشته‌های جدا اجرا می‌شوند و
        هرکدام کل صفحه را از نو می‌ساخت. حالا اگر رندری در جریان است، درخواست‌های بعدی فقط یک رندر دیگر (با آخرین وضعیت) پشت سرش می‌گذارند."""
        with RS["mx"]:
            if RS["busy"]: RS["again"] = True; return
            RS["busy"] = True
        try:
            while True:
                _render()
                with RS["mx"]:
                    if RS["again"]: RS["again"] = False; continue
                    RS["busy"] = False; break
        except BaseException:
            with RS["mx"]: RS["busy"] = False; RS["again"] = False
            raise

    def _render():
        M.reset(); update_width()
        try: body.controls = SUB[S["tab"]]() if S["tab"] in SUB else pages[S["tab"]]()
        except Exception as ex:
            traceback.print_exc(); body.controls = [empty(ic("ERROR"), f"مشکلی پیش آمد: {ex}")]
        key = (S["tab"], S["notes_tab"], S["day"] if S["tab"] == 0 else S["wk"] if S["tab"] == 2 else "", S["study_tab"], S["subj"], S["subj_tab"], S["prog_tab"], S["ncat"], S["note_id"] if S["tab"] == 9 else 0)
        fresh = SHOWN["k"] != key
        M.animate = fresh
        if fresh:
            SHOWN["k"] = key; M.prev.clear(); reveal(body.controls[:10])
        paint_nav()
        if FAB:
            shape_fab()
            vis = S["tab"] == 0                       # ＋ شناور فقط در خانه (همان جای قبلی)
            FAB["c"].visible = vis
            if vis and fresh:
                FAB["c"].scale = .6
                def pop(): FAB["c"].scale = 1; FAB["c"].update()
                M.after(pop, .08)
        page.update(); M.flush()

    def on_fab(e): mission_form()

    # ---- دکمهٔ بازگشت اندروید: پشتهٔ دو view (نگهبان + اصلی) تا Back به on_view_pop برسد؛ با یک view، اندروید مستقیم خارج می‌شود
    VIEWS = {"guard": None, "main": None, "exit_armed": False}
    def mount(root):
        try:
            if VIEWS["main"] is None:
                VIEWS["guard"] = ft.View(route="/guard", controls=[], padding=0, spacing=0)
                VIEWS["main"] = ft.View(route="/", controls=[root], padding=0, spacing=0, bgcolor=P["bg"])
                page.views.clear(); page.views.append(VIEWS["guard"]); page.views.append(VIEWS["main"])
            else:
                VIEWS["main"].controls = [root]; VIEWS["main"].bgcolor = P["bg"]
            return
        except Exception as ex:
            VIEWS["main"] = None; log_error("پشتهٔ view", ex)
        page.controls.clear(); page.add(root)         # جایگزین: همان رفتار قبلی (Back مستقیم خارج می‌شود)

    def set_guard(on):
        """نگهبان را برمی‌دارد/برمی‌گرداند. بدون نگهبان، Back بعدی طبق رفتار پیش‌فرض اندروید از برنامه خارج می‌شود."""
        try:
            has = VIEWS["guard"] in page.views
            if on and not has: page.views.insert(0, VIEWS["guard"]); page.update()
            elif not on and has: page.views.remove(VIEWS["guard"]); page.update()
        except Exception as ex: log_error("نگهبان Back", ex)

    def go_back():
        """منطق Back: زیرصفحه → صفحهٔ پیشین • تب دیگر → امروز • امروز → دوبار Back برای خروج. خروجی: آیا برنامه خودش مصرف کرد."""
        t = S["tab"]
        if t == 7: S["tab"] = 5
        elif t == 5: S["tab"] = S["nav"]
        elif t == 6: S.update(tab=S.pop("rt_back", None) if S.get("rt_back") in (0, 2, 5) else 2)
        elif t == 8: S.update(tab=1, subj=None)
        elif t == 9: PG.flush_note(); S.update(tab=3, note_id=None)
        elif t != 0: S.update(tab=0, nav=0)
        else: return False
        render(); return True

    def on_view_pop(e=None):
        if go_back(): VIEWS["exit_armed"] = False; return
        # در صفحهٔ امروز: بار اول فقط هشدار؛ نگهبان برداشته می‌شود تا Back دوم (طی ۳ ثانیه) خروج واقعی باشد
        snack("برای خروج، یک بار دیگر «بازگشت» را بزن"); set_guard(False); VIEWS["exit_armed"] = True
        def rearm():
            if VIEWS["exit_armed"]: VIEWS["exit_armed"] = False; set_guard(True)
        threading.Timer(3.0, rearm).start()
    try: page.on_view_pop = on_view_pop
    except Exception as ex: log_error("on_view_pop", ex)

    def shape_fab():
        """دکمهٔ ＋ در صفحهٔ امروز یک دایرهٔ کامل است (همان جای قبلی)؛ در بقیهٔ صفحه‌ها همان قرص «افزودن» قبلی می‌ماند."""
        c = FAB.get("c")
        if c is None: return
        circ = S["tab"] == 0
        c.width = c.height = 60 if circ else None
        c.padding = 0 if circ else ft.padding.symmetric(horizontal=18, vertical=14)
        c.border_radius = 30 if circ else 22
        c.alignment = ft.alignment.center if circ else None
        FAB["lab"].visible = not circ; FAB["icon"].size = 30 if circ else 24
        if FAB.get("top") is not None: FAB["top"].visible = S["tab"] in TOPBAR_TABS

    def build_chrome():
        NAVC.clear()
        dark = ui.is_dark()
        # پس‌زمینهٔ شفقی: گرادیان + دو هالهٔ نور
        aurora = ft.Container(left=0, right=0, top=0, bottom=0, gradient=ft.LinearGradient(begin=ft.alignment.top_center, end=ft.alignment.bottom_center, colors=[P["bg"], P["bg2"]]))
        halo1 = glow(380, "gold", .07 if dark else .12, right=-140, top=-120)
        halo2 = glow(420, "violet", .10 if dark else .10, left=-190, bottom=40)
        logo = brand_mark(36, 12); pulse(logo, 1.06)
        top = ft.Row([ft.Row([logo, ft.Column([txt("Get Better", 18, ft.FontWeight.W_800), txt("بهتر شو، هر روز", 10, color="muted")], spacing=0)], spacing=10, expand=True),
                      ft.Container(ft.IconButton(ic("SETTINGS", "outlined"), icon_color=P["muted"], tooltip="تنظیمات", on_click=lambda e: (S.update(tab=5), render())), border_radius=16,
                                   bgcolor=alpha(P["card"], .8), border=ft.border.all(1, alpha(P["line"], .08)))], alignment=ft.MainAxisAlignment.SPACE_BETWEEN)
        topbar = ft.Container(top, padding=ft.padding.only(top=6)); FAB["top"] = topbar        # در صفحهٔ امروز نوار بالا داخل کارت قهرمان است و این‌جا پنهان می‌شود
        topbar.visible = S["tab"] in TOPBAR_TABS
        content = ft.Container(ft.Column([topbar, body], spacing=4, expand=True), padding=ft.padding.symmetric(horizontal=18), left=0, right=0, top=0, bottom=0)

        # نوار پایین شناور: فقط تب فعال برچسب دارد؛ عرض و رنگ با انیمیشن عوض می‌شوند
        items = []
        for i, (label, icon, w) in enumerate(NAV):
            icn = ft.Icon(ic(icon, "outlined"), size=23, color=P["muted"])
            lab = ft.Container(txt(label, 12, ft.FontWeight.W_800, P["on_accent"], no_wrap=True), width=0, opacity=0, animate=anim(320, EASE), animate_opacity=anim(260), clip_behavior=ft.ClipBehavior.ANTI_ALIAS)
            box = ft.Container(ft.Row([icn, lab], spacing=6, tight=True, alignment=ft.MainAxisAlignment.CENTER), border_radius=22, animate=anim(320, EASE), animate_scale=anim(300, BACK),
                               ink=True, on_click=lambda e, i=i: goto(i), data=("nav", i), tooltip=NAV[i][0], padding=ft.padding.symmetric(horizontal=11, vertical=10))
            NAVC.append({"box": box, "icon": icn, "lab": lab}); items.append(box)
        nav_row = ft.Row(items, alignment=ft.MainAxisAlignment.SPACE_AROUND)
        plus = ft.Container(ft.Icon(ic("ADD"), size=30, color=P["on_accent"]), width=54, height=54, border_radius=27, alignment=ft.alignment.center, ink=True, on_click=lambda e: PG.new_note(), data="navplus", tooltip="یادداشت جدید",
                            gradient=ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=[P["gold"], P["amber"]]),
                            shadow=ft.BoxShadow(blur_radius=22, spread_radius=-2, color=alpha(P["gold"], .55 if dark else .38), offset=ft.Offset(0, 6)))
        NAVW.update(row=nav_row, plus=plus, plus_on=False)
        nav = ft.Container(nav_row, left=14, right=14, bottom=12, height=66, padding=ft.padding.symmetric(horizontal=8, vertical=8), border_radius=30,
                           bgcolor=alpha(P["card"], .94), border=ft.border.all(1, alpha(P["line"], .10)),
                           shadow=ft.BoxShadow(blur_radius=30, spread_radius=-6, color=alpha("#000000", .55) if dark else alpha(ui.SHADOW_TINT, .24), offset=ft.Offset(0, 12)))

        NAVW["box"] = nav
        fab_lab = txt("افزودن", 14, ft.FontWeight.W_800, P["on_accent"]); fab_icon = ft.Icon(ic("ADD"), size=24, color=P["on_accent"]); FAB["lab"], FAB["icon"] = fab_lab, fab_icon
        fab = ft.Container(ft.Row([fab_icon, fab_lab], spacing=6, tight=True, alignment=ft.MainAxisAlignment.CENTER),
                           padding=ft.padding.symmetric(horizontal=18, vertical=14), border_radius=22, left=20, bottom=92, ink=True, on_click=on_fab, data="fab",
                           gradient=ft.LinearGradient(begin=ft.alignment.top_left, end=ft.alignment.bottom_right, colors=[P["gold"], P["amber"]]),
                           shadow=ft.BoxShadow(blur_radius=24, spread_radius=-2, color=alpha(P["gold"], .55 if dark else .38), offset=ft.Offset(0, 8)), animate_scale=anim(380, BACK), scale=1)
        FAB["c"] = fab; shape_fab()
        page.bgcolor = P["bg"]
        mount(ft.Stack([aurora, halo1, halo2, ft.SafeArea(ft.Stack([content, nav, fab], expand=True), expand=True)], expand=True))
        paint_nav()

    fp = ft.FilePicker()
    try: page.overlay.append(fp)
    except Exception as ex: log_error("FilePicker", ex)

    # ================= معرفی اولیه =================
    def onboarding():
        """سه گام: خوش‌آمدگویی • هدف و تاریخ آزمون • هدف روزانه. هر لحظه می‌شود رد کرد."""
        st = {"i": 0}
        goal = field("هدفت چیست؟ (مثلاً قبولی در مدرسه نمونه)", store.pref("goal"))
        has_exam = bool(store.pref("exam_date"))
        use_exam = ft.Switch(label="تاریخ آزمون دارم", value=has_exam, active_color=P["gold"])
        dfield, get_exam, _ = jdate_field("تاریخ آزمون", store.pref("exam_date") or (today() + timedelta(days=90)).isoformat())
        dfield.visible = has_exam
        def exam_toggle(e): dfield.visible = bool(use_exam.value); dfield.update()
        use_exam.on_change = exam_toggle
        dgoal = seg(store.pref_int("daily_goal", 3), [(n, fa(n)) for n in (1, 2, 3, 4, 5)])
        def bullet(icon, col, t): return ft.Row([ibadge(ic(icon), col, 34, radius=11), txt(t, 13, expand=True)], spacing=10)
        s1 = ft.Column([ft.Row([brand_mark(72, 24)], alignment=ft.MainAxisAlignment.CENTER),
                        txt("به Get Better خوش آمدی", 20, ft.FontWeight.W_800, text_align=ft.TextAlign.CENTER),
                        txt("همراه روزانهٔ تو برای آمادگی آزمون", 12, color="muted", text_align=ft.TextAlign.CENTER),
                        bullet("CHECKLIST", "gold", "کارها، ریزه‌کارها و برنامهٔ هفتگی جلالی"),
                        bullet("AUTO_STORIES", "blue", "مرور فاصله‌دار تا چیزی از یادت نرود"),
                        bullet("LOCAL_FIRE_DEPARTMENT", "red", "امتیاز، سطح و استریک برای انگیزه"),
                        bullet("LOCK", "green", "همه‌چیز آفلاین و فقط روی گوشی خودت می‌ماند")], spacing=12, tight=True)
        s2 = ft.Column([txt("هدف و آزمونت را بگو تا شمارش معکوس و مسیر پیشرفتت ساخته شود. بعداً در تنظیمات قابل تغییر است.", 12, color="muted"), goal, use_exam, dfield], spacing=12, tight=True, visible=False)
        s3 = ft.Column([txt("هر روز چند کار را هدف می‌گیری؟", 14, ft.FontWeight.W_700), dgoal,
                        txt("پیشنهاد: با عدد کوچک شروع کن و هر هفته کمی بالاتر ببر؛ پیوستگی از شدت مهم‌تر است.", 12, color="muted")], spacing=12, tight=True, visible=False)
        steps = [s1, s2, s3]; holder = {}
        dots, set_dots = step_dots(len(steps))
        nxt = ft.FilledButton("بعدی", style=ft.ButtonStyle(bgcolor=P["gold"], color=P["on_accent"], shape=ft.RoundedRectangleBorder(radius=14)))
        back = ft.TextButton("قبلی", visible=False, style=ft.ButtonStyle(color=P["muted"]))
        skip = ft.TextButton("رد کردن", style=ft.ButtonStyle(color=P["muted"]))
        def paint():
            for i, c in enumerate(steps): c.visible = i == st["i"]
            set_dots(st["i"])
            back.visible = st["i"] > 0; nxt.text = "شروع" if st["i"] == len(steps) - 1 else "بعدی"
            try: holder["d"].update()
            except Exception: pass
        def finish(save):
            if save:
                store.setpref("goal", goal.value.strip()[:120]); store.setpref("exam_date", get_exam() if use_exam.value else "")
                store.setpref("daily_goal", list(dgoal.selected)[0])
            store.setpref("onboarded", "1"); page.close(holder["d"]); render()
        def go_next(e):
            if st["i"] >= len(steps) - 1: finish(True)
            else: st["i"] += 1; paint()
        def go_back(e): st["i"] = max(0, st["i"] - 1); paint()
        nxt.on_click, back.on_click, skip.on_click = go_next, go_back, lambda e: finish(False)
        holder["d"] = ft.AlertDialog(modal=True, bgcolor=P["card"], shape=ft.RoundedRectangleBorder(radius=28), inset_padding=ft.padding.symmetric(horizontal=16, vertical=24),
                                     content=ft.Container(ft.Column([dots, *steps], tight=True, spacing=16, scroll=ft.ScrollMode.AUTO), width=340), actions=[skip, back, nxt])
        popen(holder["d"])

    # ================= درباره، حریم خصوصی و راهنما =================
    def page_about():
        def point(icon, col, t, sub=None):
            return card(ft.Row([ibadge(ic(icon), col, 38, radius=13), ft.Column([txt(t, 13, ft.FontWeight.W_700)] + ([txt(sub, 11, color="muted")] if sub else []), spacing=2, expand=True)], spacing=12),
                        pad=12, radius=20, shadow=False, margin=ft.margin.only(bottom=6))
        def copy_log(e):
            log = read_error_log()
            if not log: snack("گزارش خطایی ثبت نشده؛ همه‌چیز سالم است"); return
            try: page.set_clipboard(log); snack("گزارش خطا کپی شد؛ برای پشتیبانی بفرست")
            except Exception: snack("کپی انجام نشد", False)
        def clear_log(e): clear_error_log(); snack("گزارش خطا پاک شد"); render()
        logo = card(ft.Column([brand_mark(72, 24), txt(meta.APP_NAME, 20, ft.FontWeight.W_800),
                               txt(meta.TAGLINE, 12, color="muted"),
                               chip(f"نسخه {fa(VERSION)} • ساخت {fa(meta.BUILD_NUMBER)}", "gold", ic("VERIFIED"))], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=6),
                    grad=True, pad=20, radius=28)
        out = [ft.Row([ft.IconButton(ic("ARROW_FORWARD"), tooltip="بازگشت", on_click=lambda e: (S.update(tab=5), render())), title("درباره و حریم خصوصی")]), logo,
               section("حریم خصوصی", None, ic("PRIVACY_TIP")),
               point("PHONELINK_LOCK", "green", "همه‌چیز فقط روی گوشی تو", "کارها، یادداشت‌ها و آمار در حافظهٔ همین دستگاه ذخیره می‌شوند."),
               point("PERSON_OFF", "blue", "بدون حساب کاربری", "ثبت‌نام، ورود یا شمارهٔ تلفن لازم نیست."),
               point("WIFI_OFF", "violet", "کاملاً آفلاین", "برنامه هیچ داده‌ای نمی‌فرستد و هیچ ردیاب، تبلیغ یا تحلیل‌گری ندارد."),
               point("BACKUP", "gold", "پشتیبان دست خودت است", "پشتیبان را خودت می‌سازی و خودت نگه می‌داری. با حذف برنامه، داده‌ها هم پاک می‌شوند؛ پیش از آن پشتیبان بگیر."),
               section("راهنمای سریع", None, ic("LIGHTBULB")),
               point("BOLT", "gold", "امتیاز و سطح", "هر کار انجام‌شده XP می‌دهد؛ کارهای طولانی‌تر و مهم‌تر امتیاز بیشتری دارند."),
               point("AUTO_STORIES", "blue", "مرور فاصله‌دار", "اگر مرور را ≥۸۰٪ درست بزنی یک جعبه جلو می‌روی؛ وگرنه فردا دوباره مرور می‌شود."),
               point("CENTER_FOCUS_STRONG", "green", "حالت تمرکز", "تایمر با ساعت واقعی می‌شمارد؛ خاموش‌شدن صفحه یا رفتن به برنامهٔ دیگر مشکلی ایجاد نمی‌کند. فقط اگر سیستم خود برنامه را ببندد، دور نیمه‌کاره ذخیره نمی‌شود."),
               section("اطلاعات فنی", None, ic("INFO")),
               card(ft.Column([txt(f"ساختار دیتابیس: نسخهٔ {fa(store.schema_version())}", 12, color="muted"), txt(f"نسخهٔ پشتیبان: {fa(BACKUP_VERSION)}", 12, color="muted"),
                               ft.Row([chip("کپی گزارش خطا", "blue", ic("BUG_REPORT"), on_click=copy_log), chip("پاک کردن گزارش", "muted", ic("DELETE", "outlined"), on_click=clear_log)], spacing=8, wrap=True)], spacing=8), pad=14, radius=20, shadow=False),
               section("سپاس‌ها", None, ic("FAVORITE")),
               txt("ساخته‌شده با Flet (Apache-2.0)، فونت وزیرمتن (OFL) و آیکون‌های Material (Apache-2.0).", 11, color="muted")]
        if meta.SUPPORT_EMAIL: out.append(point("MAIL", "gold", "پشتیبانی", meta.SUPPORT_EMAIL))
        out.append(btn("مرور دوبارهٔ معرفی برنامه", lambda e: onboarding(), ic("PLAY_CIRCLE"), False))
        return out + [spacer()]

    try: hero_mod.prune(os.path.basename(hero_mod.current(store) or "") or None)     # فایل‌های قدیمی/نیمه‌کارهٔ تصویر قهرمان
    except Exception as ex: log_error("hero prune", ex)
    apply_theme(); build_chrome(); render()
    def bg_backup():                                # پشتیبان روزانه کاملاً در پس‌زمینه و با اتصال جدا؛ نه شروع برنامه معطل می‌ماند نه انیمیشن‌های اول
        time.sleep(5); helper = None
        try: helper = Store(store.path, bare=True); helper.maybe_daily_backup()
        except Exception as ex: log_error("پشتیبان خودکار", ex)
        finally:
            if helper is not None: helper.close()
    threading.Thread(target=bg_backup, daemon=True).start()
    notifier = notify.Notifier(page, log_error)
    def remind_loop():                              # هر ۲۰ ثانیه، تا وقتی برنامه زنده است؛ شرط‌ها با دیتابیس زنده سنجیده می‌شوند
        helper = None
        try:
            helper = Store(store.path, bare=True)
            while True:
                time.sleep(20)
                for r in helper.reminders_due():
                    helper.mark_reminded(r["key"])
                    try: notifier.send(r["title"], r["body"]); snack(r["body"])
                    except Exception as ex: log_error("یادآوری", ex)
        except Exception as ex: log_error("حلقهٔ یادآوری", ex)
        finally:
            if helper is not None: helper.close()
    threading.Thread(target=remind_loop, daemon=True).start()
    if store.recovery: snack("دیتابیس آسیب‌دیده بود و از آخرین پشتیبان بازیابی شد" if store.recovery == "restored" else "دیتابیس آسیب‌دیده بود؛ برنامه از نو شروع شد (فایل قبلی نگه داشته شد)", store.recovery == "restored")
    if store.pref("onboarded") != "1":
        if store.is_fresh(): onboarding()
        else: store.setpref("onboarded", "1")        # کاربر قدیمی که از نسخهٔ قبل ارتقا داده است

if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")
