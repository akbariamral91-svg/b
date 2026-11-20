# -*- coding: utf-8 -*-
"""چهار صفحهٔ بازطراحی‌شدهٔ نسخهٔ ۴٫۱: تحصیل، هفته، یادداشت‌ها و پیشرفت (+ جزئیات درس و ویرایشگر یادداشت).

صفحهٔ خانه (امروز) در main.py است و این ماژول هیچ‌چیز از آن را تغییر نمی‌دهد. main.py یک «ctx» (ابزارهای مشترک: دیتابیس، دیالوگ‌ها،
رندر…) به build() می‌دهد و صفحه‌ها را از خروجی آن برمی‌دارد.
"""
import sqlite3
from datetime import date, datetime, timedelta
import flet as ft
import jalali as J
import ui
from jalali import fa, en
from ui import (P, alpha, ic, txt, ibadge, card, chip, section, empty, btn, field, num_field, dd, pbar, ring, count_up, spacer, M, anim, pill_tabs, pill_btn,
                page_hero, glass_btn, subject_icon, bars, stat_tile, legend_scale, later, EASE)
from store import (DEFAULT_SUBJECTS, NOTE_CATS, ACHIEVEMENTS, level_for_xp, xp_threshold, level_title, chapter_key)
from types import SimpleNamespace

KINDS = {"practice": "تمرین", "exam": "آزمون", "review": "مرور"}
CAT = {"personal": ("شخصی", "PERSON", "violet"), "study": ("درسی", "SCHOOL", "blue"), "work": ("کاری", "WORK", "green"),
       "idea": ("ایده‌ها", "LIGHTBULB", "gold"), "other": ("سایر", "SELL", "muted")}
METRICS = [("xp", "XP"), ("minutes", "مطالعه (دقیقه)"), ("done", "کار انجام‌شده")]


def ch_label(ch):
    ch = (ch or "").strip()
    if not ch: return "—"
    return f"فصل {fa(chapter_key(ch))}" if en(ch).isdigit() else fa(ch)

def mastery_info(m):
    m = int(m or 0)
    return ("تازه شروع", "muted") if m <= 0 else ("ضعیف", "red") if m < 40 else ("متوسط", "gold") if m < 65 else ("خوب", "blue") if m < 90 else ("عالی", "green")

def jshort(iso): return J.fmt(iso, "short")


def build(ctx):
    store, S, page = ctx.store, ctx.S, ctx.page
    render, dialog, confirm, snack = ctx.render, ctx.dialog, ctx.confirm, ctx.snack
    today = date.today
    S.setdefault("study_tab", 0); S.setdefault("subj", None); S.setdefault("subj_tab", 0); S.setdefault("prog_tab", "overall"); S.setdefault("prog_metric", "xp")
    S.setdefault("ncat", None); S.setdefault("wday", None); S.setdefault("note_id", None)

    def settings_btn(): return glass_btn("SETTINGS", "تنظیمات", lambda e: ctx.open_settings())
    def back_btn(fn, tip="بازگشت"): return glass_btn("ARROW_FORWARD", tip, lambda e: fn())

    # ======================================================================== تحصیل
    def open_subject(sid, tab=0): S.update(tab=8, subj=sid, subj_tab=tab); render()
    def close_subject(): S.update(tab=1, subj=None); render()

    def subject_form():
        f = field("نام درس", autofocus=True)
        def save():
            if not f.value.strip(): f.error_text = "الزامی است"; f.update(); return False
            try: store.add_subject(f.value)
            except sqlite3.IntegrityError: snack("این درس از قبل وجود دارد", False); return False
            render()
        dialog("درس جدید", [f], save, icon="MENU_BOOK")

    def chapters_form(st):
        f = num_field("تعداد فصل‌های کتاب", str(st["total_chapters"] or ""), autofocus=True)
        def save():
            v = ui.to_int(f.value) if f.value.strip() else 0
            if v is None or v > 200: f.error_text = "عددی بین ۰ تا ۲۰۰ وارد کن"; f.update(); return False
            store.set_total_chapters(st["id"], v); render()
        dialog("تعداد فصل‌ها", [txt("درصد پیشرفت درس بر پایهٔ همین تعداد فصل حساب می‌شود؛ فصل‌های شروع‌نشده صفر حساب می‌شوند.", 12, color="muted"), f], save, icon="MENU_BOOK")

    def topic_chips(sid, ch, nm):
        """مباحث ثبت‌شدهٔ همین درس برای پر کردن سریع فصل و مبحث."""
        tops = store.subject_topics(sid)[:10]
        def pick(t):
            def go(e): ch.value = t["chapter"] or ""; nm.value = t["name"]; ch.update(); nm.update()
            return go
        return ft.Row([chip((ch_label(t["chapter"]) + " • " if t["chapter"] else "") + t["name"], "blue", on_click=pick(t)) for t in tops], spacing=6, scroll=ft.ScrollMode.AUTO) if tops else ft.Container(height=0)

    def study_form(sid, topic=None, log=None):
        """ثبت مطالعه: فصل، مبحث، مدت، تاریخ، میزان تسلط و یادداشت شخصی."""
        t0 = topic or (store.one("SELECT * FROM topics WHERE id=?", (log["topic_id"],)) if log else None)
        ch = field("فصل (مثلاً ۳)", t0["chapter"] if t0 else "")
        nm = field("مبحث", t0["name"] if t0 else "", autofocus=True)
        mins = num_field("مدت مطالعه (دقیقه)", str(log["minutes"]) if log else "30")
        dfield, get_day, _ = ctx.jdate_field("تاریخ مطالعه", log["date"] if log else today().isoformat())
        m0 = int(log["mastery"]) if log else int((t0["mastery"] if t0 else 0) or 0)
        mlabel = txt("", 13, ft.FontWeight.W_700, "gold")
        slider = ft.Slider(min=0, max=100, divisions=20, value=m0, active_color=P["gold"])
        def paint(update=True):
            lab, col = mastery_info(slider.value); mlabel.value = f"میزان تسلط: {fa(int(slider.value))}٪ • {lab}"
            if update: mlabel.update()
        slider.on_change = lambda e: paint(); paint(False)
        def setm(v):
            def go(e): slider.value = v; slider.update(); paint()
            return go
        quick = ft.Row([chip(f"{n} {fa(v)}٪", c, on_click=setm(v)) for v, n, c in ((25, "ضعیف", "red"), (50, "متوسط", "gold"), (75, "خوب", "blue"), (100, "عالی", "green"))], spacing=6, wrap=True)
        note = field("یادداشت شخصی (اختیاری)", log["note"] if log else "", multiline=True, min_lines=2, max_lines=4)
        def save():
            nm.error_text = mins.error_text = None
            if not nm.value.strip(): nm.error_text = "نام مبحث الزامی است"; nm.update(); return False
            m = ui.to_int(mins.value) if mins.value.strip() else 0
            if m is None or m > 1440: mins.error_text = "مدت را فقط با رقم (حداکثر ۱۴۴۰ دقیقه) وارد کن"; mins.update(); return False
            tid = store.save_topic(sid, ch.value, nm.value)
            if log: store.update_study(log["id"], tid, get_day(), m, int(slider.value), note.value)
            else: store.add_study(tid, get_day(), m, int(slider.value), note.value)
            snack(f"مطالعه ثبت شد • تسلط {fa(int(slider.value))}٪"); render(); ctx.after_action()
        dialog("ویرایش مطالعه" if log else "ثبت مطالعه", [ch, nm, topic_chips(sid, ch, nm), mins, dfield, mlabel, slider, quick, note], save, "ثبت", icon="EDIT_NOTE")

    def topic_form(sid, row=None):
        ch = field("فصل (مثلاً ۳)", row["chapter"] if row else ""); nm = field("نام مبحث", row["name"] if row else "", autofocus=True)
        nt = field("یادداشت شخصی", row["notes"] if row else "", multiline=True, min_lines=2, max_lines=5)
        ms = field("اشتباهات رایج (اختیاری)", row["mistakes"] if row else "", multiline=True, min_lines=1, max_lines=3)
        def save():
            if not nm.value.strip(): nm.error_text = "نام مبحث الزامی است"; nm.update(); return False
            store.save_topic(sid, ch.value, nm.value, nt.value, ms.value, row["id"] if row else None); render()
        dialog("ویرایش مبحث" if row else "مبحث جدید", [ch, nm, nt, ms], save, icon="LIBRARY_BOOKS")

    def history_dialog(sid, t):
        holder = {}
        def edit(lg):
            def go(e): page.close(holder["d"]); study_form(sid, log=lg)
            return go
        def drop(lg):
            def go(e):
                page.close(holder["d"])
                confirm("حذف ثبت مطالعه", "این ثبت مطالعه حذف شود؟", lambda: (store.delete_study(lg["id"]), render()))
            return go
        rows = []
        for lg in store.study_logs_of(t["id"]):
            lab, col = mastery_info(lg["mastery"])
            rows.append(card(ft.Row([ft.Column([txt(jshort(lg["date"]), 13, ft.FontWeight.W_700), txt(f"{ctx.fmt_minutes(lg['minutes'])} • تسلط {fa(lg['mastery'])}٪" if lg["minutes"] else f"تسلط {fa(lg['mastery'])}٪", 11, color="muted"),
                                     *([txt(lg["note"], 11, color="muted", max_lines=2)] if lg["note"] else [])], spacing=2, expand=True),
                                     chip(lab, col), ft.IconButton(ic("EDIT", "outlined"), icon_color=P["muted"], on_click=edit(lg)), ft.IconButton(ic("DELETE", "outlined"), icon_color=P["muted"], on_click=drop(lg))], spacing=4),
                             pad=ft.padding.only(left=4, right=12, top=8, bottom=8), radius=18, shadow=False))
        holder["d"] = dialog("تاریخچهٔ مطالعه — " + t["name"], rows or [txt("هنوز مطالعه‌ای برای این مبحث ثبت نشده.", 12, color="muted")], lambda: True, "بستن", cancel=False, icon="HISTORY")

    # ---- تست
    def test_form(row=None, sid=None):
        subs = store.study_overview()
        if not subs: snack("ابتدا یک درس بساز", False); return
        cur = row["sid"] if row else (sid or subs[0]["id"])
        sdd = dd(str(cur), [(str(s["id"]), s["name"]) for s in subs]) if (sid is None and not row) else None
        kind = ui.seg(row["kind"] if row else "practice", list(KINDS.items()))
        ch = field("فصل تست‌زده‌شده (مثلاً ۳)", row["chapter"] if row else ""); nm = field("مبحث تست‌زده‌شده", row["topic"] if row else "")
        chips_holder = ft.Container(topic_chips(cur, ch, nm))
        if sdd is not None:
            def sub_changed(e): chips_holder.content = topic_chips(int(sdd.value), ch, nm); chips_holder.update()
            sdd.on_change = sub_changed
        tot = num_field("تعداد کل تست", str(row["total"]) if row else "", expand=True); cor = num_field("صحیح", str(row["correct"]) if row else "", expand=True)
        wr = num_field("غلط", str(row["wrong_n"]) if row else "", expand=True); bl = num_field("نزده (خالی = باقی‌مانده)", str(row["blank_n"]) if row else "", expand=True)
        dfield, get_day, _ = ctx.jdate_field("تاریخ آزمون", row["date"] if row else today().isoformat())
        def save():
            for f in (tot, cor, wr, bl): f.error_text = None
            total = ui.to_int(tot.value); correct = ui.to_int(cor.value) if cor.value.strip() else 0; wrong = ui.to_int(wr.value) if wr.value.strip() else 0
            blank = ui.to_int(bl.value) if bl.value.strip() else None
            if total is None or total < 1: tot.error_text = "تعداد کل را با رقم وارد کن"; tot.update(); return False
            if correct is None or wrong is None or (bl.value.strip() and blank is None): snack("صحیح، غلط و نزده را فقط با رقم وارد کن", False); return False
            if blank is None: blank = total - correct - wrong
            if blank < 0 or correct + wrong + blank != total: snack("صحیح + غلط + نزده باید برابر تعداد کل باشد", False); return False
            k = list(kind.selected)[0]; s_id = int(sdd.value) if sdd is not None else cur
            if row: store.update_test(row["id"], s_id, ch.value, nm.value, k, total, correct, wrong, blank, get_day())
            else: store.add_test(s_id, ch.value, nm.value, k, total, correct, wrong, blank, get_day())
            snack(f"ثبت شد • {fa(round(100 * correct / total))}٪ درست"); render(); ctx.after_action()
        dialog("ویرایش جلسهٔ تست" if row else "ثبت جلسهٔ تست", [*([sdd] if sdd is not None else []), kind, ch, nm, chips_holder, ft.Row([tot, cor], spacing=8), ft.Row([wr, bl], spacing=8), dfield], save, "ثبت", icon="FACT_CHECK")

    def del_test(r): confirm("حذف جلسهٔ تست", "این جلسهٔ تست حذف شود؟", lambda: (store.delete_test(r["id"]), render()))

    def test_row(r, with_subject=False):
        pct = r["correct"] / max(1, r["total"]); col = "green" if pct >= .8 else "gold" if pct >= .5 else "red"
        head = (r["subject"] + " • " if with_subject else "") + r["topic"]
        menu = ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=[ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=r: test_form(x)),
                                                                                     ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, x=r: del_test(x))])
        info = ft.Column([txt(head, 13, ft.FontWeight.W_700, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                          txt(f"{ch_label(r['chapter'])} • {KINDS.get(r['kind'], r['kind'])} • {jshort(r['date'])}", 11, color="muted", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                          ft.Row([chip(f"صحیح {fa(r['correct'])}", "green", ic("CHECK")), chip(f"غلط {fa(r['wrong_n'])}", "red", ic("CLOSE")), chip(f"نزده {fa(r['blank_n'])}", "muted", ic("REMOVE"))], spacing=4, wrap=True, run_spacing=4)], spacing=4, expand=True)
        return card(ft.Row([ring(pct, 52, 6, col, key=f"t{r['id']}", center=txt(fa(round(pct * 100)), 12, ft.FontWeight.W_800)), info, ft.Column([txt(f"{fa(r['total'])} تست", 11, color="muted"), menu], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                    pad=ft.padding.only(left=6, right=12, top=10, bottom=10), radius=22, margin=ft.margin.only(bottom=8), shadow=False)

    def test_tiles(sm):
        a = ft.Row([stat_tile(ic("FACT_CHECK", "outlined"), "gold", fa(sm["sessions"]), "جلسهٔ تست"), stat_tile(ic("TRACK_CHANGES", "outlined"), "green", (fa(sm["success"]) + "٪") if sm["success"] is not None else "—", "درصد موفقیت"),
                    stat_tile(ic("TODAY", "outlined"), "blue", fa(sm["today"]), "تست امروز")], spacing=8)
        b = ft.Row([stat_tile(ic("CHECK_CIRCLE", "outlined"), "green", fa(sm["correct"]), "صحیح"), stat_tile(ic("CANCEL", "outlined"), "red", fa(sm["wrong"]), "غلط"),
                    stat_tile(ic("REMOVE_CIRCLE_OUTLINE", "outlined"), "muted", fa(sm["blank"]), "نزده")], spacing=8)
        return ft.Column([a, b], spacing=8)

    def subject_card(st):
        pct = st["progress"] / 100; col = "green" if st["progress"] >= 80 else "gold"
        rg = ring(pct, 58, 6, col, key=f"sr{st['id']}", center=txt(fa(st["progress"]) + "٪", 13, ft.FontWeight.W_800, col))
        meta = ft.Column([ft.Row([ft.Icon(ic("BOOKMARK", "outlined"), size=13, color=P["muted"]), txt("آخرین فصل: " + ch_label(st["last_chapter"]), 11, color="muted")], spacing=4),
                          ft.Row([ft.Icon(ic("EDIT_NOTE", "outlined"), size=13, color=P["muted"]), txt("آخرین مبحث: " + (st["last_topic"] or "—"), 11, color="muted", max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, expand=True)], spacing=4)], spacing=3)
        body = ft.Column([txt(st["name"], 16, ft.FontWeight.W_800), meta, pbar(pct, col, 7, off=214, key=f"sb{st['id']}")], spacing=6, expand=True)
        tests = (f"{fa(st['tests'])} جلسه تست • میانگین {fa(st['avg_success'])}٪") if st["tests"] else "هنوز تستی ثبت نشده"
        foot = ft.Row([txt(tests, 11, color="muted", expand=True), pill_btn("مشاهده جزئیات", ic("CHEVRON_LEFT"), lambda e, i=st["id"]: open_subject(i))], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        return card(ft.Column([ft.Row([subject_icon(st["icon"], 60), body, rg], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER), foot], spacing=10),
                    pad=14, radius=26, margin=ft.margin.only(bottom=10), on_click=lambda e, i=st["id"]: open_subject(i), data=("subject", st["id"]))

    def page_study():
        out = [page_hero("study", "تحصیل", "برنامه و پیگیری دروس", tools=[settings_btn()]),
               pill_tabs([("0", "درس‌ها", "MENU_BOOK"), ("1", "تست‌ها", "FACT_CHECK")], str(S["study_tab"]), lambda k: (S.update(study_tab=int(k)), render()))]
        subs = store.study_overview()
        if S["study_tab"] == 0:
            out.append(section("دروس من", pill_btn("درس جدید", ic("ADD"), lambda e: subject_form()), ic("SCHOOL", "outlined")))
            out += [subject_card(st) for st in subs]
            sm = store.test_summary()
            out.append(card(ft.Row([ibadge(ic("ASSIGNMENT_TURNED_IN", "outlined"), "gold", 44, filled=True, radius=15), ft.Column([txt("تست‌های انجام‌شده", 14, ft.FontWeight.W_800), txt(f"مجموع تست: {fa(sm['total'])} • امروز: {fa(sm['today'])} تست", 12, color="muted")], spacing=2, expand=True),
                                  pill_btn("ثبت تست", ic("ADD"), lambda e: (S.update(study_tab=1), render()))], spacing=12), tint="gold", pad=14, radius=24, shadow=False, margin=ft.margin.only(bottom=4)))
        else:
            sm = store.test_summary()
            out += [test_tiles(sm), btn("ثبت جلسهٔ تست", lambda e: test_form(), ic("ADD"))]
            out.append(section("درس‌ها", None, ic("MENU_BOOK", "outlined")))
            for st in subs:
                out.append(card(ft.Row([subject_icon(st["icon"], 38), ft.Column([txt(st["name"], 14, ft.FontWeight.W_700), txt((f"{fa(st['tests'])} جلسه • میانگین {fa(st['avg_success'])}٪") if st["tests"] else "هنوز تستی ثبت نشده", 11, color="muted")], spacing=1, expand=True),
                                      ft.Icon(ic("CHEVRON_LEFT"), color=P["muted"])], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER), pad=ft.padding.symmetric(horizontal=12, vertical=8), radius=20, shadow=False,
                                margin=ft.margin.only(bottom=6), on_click=lambda e, i=st["id"]: open_subject(i, 1)))
            rows = store.tests_of(None, 15)
            out.append(section("آخرین جلسه‌ها", None, ic("HISTORY")))
            out += [test_row(r, True) for r in rows] or [empty(ic("FACT_CHECK", "outlined"), "هنوز جلسهٔ تستی ثبت نشده")]
        return out + [spacer()]

    # ---- جزئیات درس
    def page_subject():
        sid = S["subj"]; st = next((x for x in store.study_overview() if x["id"] == sid), None)
        if st is None: S.update(tab=1, subj=None); return page_study()
        custom = st["name"] not in dict(DEFAULT_SUBJECTS)
        menu_items = [ft.PopupMenuItem(text="تعداد فصل‌های کتاب", icon=ic("MENU_BOOK", "outlined"), on_click=lambda e: chapters_form(st))]
        if custom: menu_items.append(ft.PopupMenuItem(text="حذف درس", icon=ic("DELETE", "outlined"), on_click=lambda e: confirm("حذف درس", "درس با همهٔ مبحث‌ها، مطالعه‌ها و تست‌هایش حذف شود؟",
                                                                                                                           lambda: (store.run("DELETE FROM subjects WHERE id=?", (sid,)), close_subject()))))
        pct = st["progress"] / 100; col = "green" if st["progress"] >= 80 else "gold"
        top = ft.Row([ft.IconButton(ic("ARROW_FORWARD"), tooltip="بازگشت", on_click=lambda e: close_subject()), txt("جزئیات درس", 18, ft.FontWeight.W_800, expand=True), ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=menu_items)])
        chap = ("از " + fa(st["total_chapters"]) + " فصل") if st["total_chapters"] else "تعداد فصل‌ها تنظیم نشده"
        head = card(ft.Column([ft.Row([subject_icon(st["icon"], 76), ft.Column([txt(st["name"], 22, ft.FontWeight.W_800), txt(f"{fa(st['topics'])} مبحث • {ctx.fmt_minutes(st['minutes']) if st['minutes'] else 'بدون مطالعهٔ ثبت‌شده'}", 12, color="muted"),
                                                                     chip(chap, "gold", ic("MENU_BOOK", "outlined"), on_click=lambda e: chapters_form(st))], spacing=4, expand=True),
                                                ring(pct, 76, 8, col, key="dr", center=txt(fa(st["progress"]) + "٪", 16, ft.FontWeight.W_800, col))], spacing=12, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                               pbar(pct, col, 8, off=68, key="dbar"),
                               ft.Row([txt("آخرین فصل: " + ch_label(st["last_chapter"]), 12, color="muted"), txt("آخرین مبحث: " + (st["last_topic"] or "—"), 12, color="muted", expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, text_align=ft.TextAlign.END)], spacing=8)], spacing=12),
                    grad=True, pad=16, radius=28)
        actions = ft.Row([btn("ثبت مطالعه", lambda e: study_form(sid), ic("EDIT_NOTE")), btn("مبحث جدید", lambda e: topic_form(sid), ic("ADD"), False), btn("ثبت تست", lambda e: test_form(sid=sid), ic("FACT_CHECK"), False)], spacing=8, wrap=True, run_spacing=8)
        out = [top, head, actions, pill_tabs([("0", "مباحث و مطالعه", "LIBRARY_BOOKS"), ("1", "تست‌ها", "FACT_CHECK")], str(S["subj_tab"]), lambda k: (S.update(subj_tab=int(k)), render()))]
        if S["subj_tab"] == 0:
            tops = store.subject_topics(sid)
            if not tops: out.append(empty(ic("LIBRARY_BOOKS", "outlined"), "هنوز مبحثی ثبت نشده.\nبا «ثبت مطالعه» یا «مبحث جدید» شروع کن"))
            groups = {}
            for t in tops: groups.setdefault((t["chapter"] or "").strip(), []).append(t)
            for chv, items in groups.items():
                avg = sum(t["mastery"] or 0 for t in items) / len(items)
                out.append(ft.Row([ft.Row([ibadge(ic("BOOKMARK", "outlined"), "violet", 28, radius=10), txt(ch_label(chv) if chv else "بدون فصل", 14, ft.FontWeight.W_800)], spacing=8), txt(f"میانگین تسلط {fa(round(avg))}٪", 11, color="muted")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN))
                for t in items:
                    lab, mcol = mastery_info(t["mastery"])
                    menu = ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=[
                        ft.PopupMenuItem(text="ثبت مطالعه", icon=ic("EDIT_NOTE"), on_click=lambda e, x=t: study_form(sid, topic=x)),
                        ft.PopupMenuItem(text="تاریخچهٔ مطالعه", icon=ic("HISTORY"), on_click=lambda e, x=t: history_dialog(sid, x)),
                        ft.PopupMenuItem(text="ویرایش مبحث", icon=ic("EDIT", "outlined"), on_click=lambda e, x=t: topic_form(sid, x)),
                        ft.PopupMenuItem(text="حذف مبحث", icon=ic("DELETE", "outlined"), on_click=lambda e, x=t: confirm("حذف مبحث", "مبحث با همهٔ مطالعه‌ها و تست‌هایش حذف شود؟", lambda: (store.delete_topic(x["id"]), render())))])
                    chips_ = [chip(lab + " " + fa(t["mastery"] or 0) + "٪", mcol, ic("TRENDING_UP"))]
                    if t["last_date"]: chips_.append(chip(jshort(t["last_date"]), "muted", ic("EVENT", "outlined")))
                    if t["minutes"]: chips_.append(chip(ctx.fmt_minutes(t["minutes"]), "gold", ic("TIMER", "outlined")))
                    if t["tests"]: chips_.append(chip(f"{fa(t['tests'])} تست", "blue", ic("FACT_CHECK", "outlined")))
                    out.append(card(ft.Column([ft.Row([txt(t["name"], 14, ft.FontWeight.W_700, expand=True), menu], spacing=0), pbar((t["mastery"] or 0) / 100, mcol if mcol != "muted" else "gold", 6, off=60, key=f"tb{t['id']}"),
                                               ft.Row(chips_, spacing=6, wrap=True, run_spacing=4), *([txt(t["notes"], 11, color="muted", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)] if t["notes"] else [])], spacing=6),
                                    pad=ft.padding.only(left=14, right=6, top=6, bottom=12), radius=22, margin=ft.margin.only(bottom=8), shadow=False, on_click=lambda e, x=t: study_form(sid, topic=x)))
            rec = store.recent_study(sid, 8)
            if rec:
                out.append(section("آخرین مطالعه‌ها", None, ic("HISTORY")))
                for lg in rec:
                    lab, mcol = mastery_info(lg["mastery"])
                    def edit(e, x=lg): study_form(sid, log=x)
                    out.append(card(ft.Row([ft.Column([txt(lg["tname"], 13, ft.FontWeight.W_700), txt(f"{ch_label(lg['chapter'])} • {jshort(lg['date'])}" + (f" • {ctx.fmt_minutes(lg['minutes'])}" if lg["minutes"] else ""), 11, color="muted")], spacing=1, expand=True),
                                            chip(f"{fa(lg['mastery'])}٪", mcol), ft.IconButton(ic("DELETE", "outlined"), icon_color=P["muted"], on_click=lambda e, x=lg: confirm("حذف ثبت مطالعه", "این ثبت مطالعه حذف شود؟", lambda: (store.delete_study(x["id"]), render())))], spacing=4,
                                           vertical_alignment=ft.CrossAxisAlignment.CENTER), pad=ft.padding.only(left=14, right=4, top=6, bottom=6), radius=18, margin=ft.margin.only(bottom=6), shadow=False, on_click=edit))
        else:
            out += [test_tiles(store.test_summary(sid)), section("جلسه‌های تست", pill_btn("ثبت تست", ic("ADD"), lambda e: test_form(sid=sid)), ic("FACT_CHECK", "outlined"))]
            out += [test_row(r) for r in store.tests_of(sid)] or [empty(ic("FACT_CHECK", "outlined"), "برای این درس هنوز جلسهٔ تستی ثبت نشده")]
        return out + [spacer()]

    # ======================================================================== هفته
    def week_state():
        ws = J.week_start(date.fromisoformat(S["wk"])); we = ws + timedelta(days=6)
        wd = date.fromisoformat(S["wday"]) if S.get("wday") else today()
        if not (ws <= wd <= we): wd = today() if ws <= today() <= we else ws
        return ws, we, wd

    def goal_form(ws, row=None):
        f = field("هدف این هفته چیست؟", row["title"] if row else "", autofocus=True)
        def save():
            if not f.value.strip(): f.error_text = "الزامی است"; f.update(); return False
            (store.update_goal(row["id"], f.value) if row else store.add_goal(ws, f.value)); render()
        dialog("ویرایش هدف" if row else "هدف هفتگی جدید", [f], save, icon="TRACK_CHANGES")

    def page_week():
        ws, we, wd = week_state(); plan = store.week_plan(ws); cur = ws == J.week_start(today())
        a, b = J.to_jalali(ws), J.to_jalali(we)
        rng = f"{fa(a[2])} {J.MONTHS[a[1] - 1]} – {fa(b[2])} {J.MONTHS[b[1] - 1]}" if a[1] != b[1] else f"{fa(a[2])} – {fa(b[2])} {J.MONTHS[b[1] - 1]}"
        shift = lambda n: (lambda e: (S.update(wk=(ws + timedelta(days=n)).isoformat(), wday=None), render()))
        nav = card(ft.Row([ft.IconButton(ic("CHEVRON_RIGHT"), icon_color=P["gold"], tooltip="هفتهٔ قبل", on_click=shift(-7)),
                           ft.Column([txt(rng, 16, ft.FontWeight.W_800, text_align=ft.TextAlign.CENTER), txt(f"سال {fa(b[0])}" + (" • این هفته" if cur else ""), 11, color="gold" if cur else "muted")], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True),
                           ft.IconButton(ic("CHEVRON_LEFT"), icon_color=P["gold"], tooltip="هفتهٔ بعد", on_click=shift(7))], vertical_alignment=ft.CrossAxisAlignment.CENTER), pad=ft.padding.symmetric(horizontal=6, vertical=4), radius=24, grad=True)
        tiles = []
        for i, d in enumerate(plan):
            day = d["date"]; sel = day == wd; tot, dn = d["total"], d["done"]; dot = P["green"] if tot and dn == tot else (P["gold"] if tot else "transparent")
            tiles.append(ft.Container(ft.Column([txt(J.WEEKDAY_SHORT[day.weekday()], 11, color=P["on_accent"] if sel else "muted"), txt(fa(J.to_jalali(day)[2]), 16, ft.FontWeight.W_800, P["on_accent"] if sel else None),
                                                 ft.Container(width=6, height=6, border_radius=3, bgcolor=P["on_accent"] if (sel and tot) else dot)], spacing=3, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                      padding=ft.padding.symmetric(vertical=9), border_radius=18, expand=True, ink=True, on_click=lambda e, k=day.isoformat(): (S.update(wday=k), render()), data=("wday", day.isoformat()),
                                      bgcolor=P["gold"] if sel else alpha(P["text"], .05), shadow=ft.BoxShadow(blur_radius=16, spread_radius=-2, color=alpha(P["gold"], .45), offset=ft.Offset(0, 5)) if sel else None,
                                      border=ft.border.all(1.4, P["gold"]) if day == today() and not sel else ft.border.all(1, alpha(P["line"], .06))))
        strip = ft.Row(tiles, spacing=6)
        day_d = plan[(wd - ws).days]; dtasks = day_d["tasks"]; left = day_d["total"] - day_d["done"]
        badges = []
        if day_d["prayers"]: badges.append(chip(f"نماز {fa(day_d['prayer_done'])}/{fa(len(day_d['prayers']))}", "green" if day_d["prayer_done"] == len(day_d["prayers"]) else "violet", ic("NIGHTS_STAY")))
        if day_d["routine"]: badges.append(chip(f"روتین {fa(day_d['routine_done'])}/{fa(len(day_d['routine']))}", "blue", ic("EVENT_REPEAT")))
        agenda = card(ft.Column([ft.Row([ft.Row([ibadge(ic("TODAY"), "gold", 34, filled=wd == today(), radius=11), ft.Column([txt("برنامهٔ " + J.WEEKDAYS[wd.weekday()], 15, ft.FontWeight.W_800), txt(J.fmt(wd, "long"), 11, color="muted")], spacing=0)], spacing=10),
                                         pill_btn("افزودن وظیفه", ic("ADD"), lambda e: ctx.mission_form(day=wd.isoformat()), solid=True)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                 ft.Row([chip(f"انجام‌شده {fa(day_d['done'])}", "green", ic("TASK_ALT", "outlined")), chip(f"باقی‌مانده {fa(left)}", "gold" if left else "muted", ic("PENDING_ACTIONS", "outlined")), *badges], spacing=6, wrap=True, run_spacing=4),
                                 *([pbar(day_d["done"] / day_d["total"], "green" if day_d["done"] == day_d["total"] else "gold", 7, off=68, key="dayb")] if day_d["total"] else []),
                                 *([ctx.mission_tile(r, True) for r in dtasks] or [empty(ic("EVENT_AVAILABLE", "outlined"), "برای این روز وظیفه‌ای ثبت نشده")])], spacing=10), pad=16, radius=28)
        # ---- اهداف هفته
        goals = store.week_goals(ws); gs = store.goal_stats(ws); glist = []
        for g in goals:
            ok = bool(g["done"])
            glist.append(ft.Row([ft.IconButton(ic("CHECK_CIRCLE") if ok else ic("RADIO_BUTTON_UNCHECKED", "outlined"), icon_color=P["green"] if ok else P["gold"], icon_size=26, tooltip="تحقق یافت" if not ok else "برگرداندن",
                                               on_click=lambda e, i=g["id"]: (store.toggle_goal(i), render())),
                                 (ft.Text(g["title"], size=14, color=P["muted"], font_family=ui.family(None), style=ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH), expand=True) if ok else txt(g["title"], 14, ft.FontWeight.W_600, expand=True)),
                                 ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=[ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=g: goal_form(ws, x)),
                                                                                                     ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, x=g: confirm("حذف هدف", "این هدف حذف شود؟", lambda: (store.delete_goal(x["id"]), render())))])],
                                spacing=0, vertical_alignment=ft.CrossAxisAlignment.CENTER))
        def quick_goal(e):
            v = (e.control.value or "").strip()
            if v: store.add_goal(ws, v); render()
        goal_in = field("هدف جدید برای این هفته…", prefix_icon=ic("FLAG", "outlined"), on_submit=quick_goal)
        goals_card = card(ft.Column([ft.Row([ft.Row([ibadge(ic("TRACK_CHANGES"), "violet", 34, radius=11), txt("اهداف هفته", 16, ft.FontWeight.W_800)], spacing=10), chip(f"{fa(gs['done'])} از {fa(gs['total'])}", "green" if gs["total"] and gs["done"] == gs["total"] else "violet")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                                     *(glist or [txt("هنوز هدفی برای این هفته نگذاشته‌ای؛ یکی بنویس.", 12, color="muted")]), goal_in], spacing=6), pad=16, radius=26)
        msg = ("برای شروع یک هدف بنویس" if not gs["total"] else "تا اینجا هیچ هدفی تحقق نیافته؛ اولی را بزن" if gs["done"] == 0 else "عالی پیش می‌روی؛ ادامه بده" if gs["pct"] < 100 else "همهٔ اهداف این هفته تحقق یافت!")
        gcol = "green" if gs["pct"] >= 80 else "gold"
        status = card(ft.Row([ring(gs["pct"] / 100, 84, 9, gcol, key="gring", center=txt(fa(gs["pct"]) + "٪", 18, ft.FontWeight.W_800, gcol)),
                              ft.Column([txt("وضعیت اهداف", 15, ft.FontWeight.W_800), txt(f"{fa(gs['done'])} از {fa(gs['total'])} هدف تحقق یافته", 12, color="muted"), txt(msg, 12, ft.FontWeight.W_600, "gold")], spacing=4, expand=True)], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER), pad=16, radius=26)
        # ---- وظایف هفته
        tot = sum(d["total"] for d in plan); dn = sum(d["done"] for d in plan); mins = sum(r["minutes"] for d in plan for r in d["tasks"] if not r["done"])
        tasks_card = card(ft.Column([ft.Row([ibadge(ic("CHECKLIST"), "gold", 34, radius=11), txt("وظایف هفته", 16, ft.FontWeight.W_800)], spacing=10),
                                     pbar((dn / tot) if tot else 0, "green" if tot and dn == tot else "gold", 8, off=68, key="wtasks"),
                                     ft.Row([stat_tile(ic("TASK_ALT", "outlined"), "green", fa(dn), "انجام‌شده"), stat_tile(ic("PENDING_ACTIONS", "outlined"), "gold", fa(tot - dn), "باقی‌مانده"),
                                             stat_tile(ic("TIMER", "outlined"), "blue", ctx.fmt_minutes(mins) if mins else "—", "زمان باقی‌مانده")], spacing=8)], spacing=12), pad=16, radius=26)
        def copy_next():
            n = store.copy_week(ws, ws + timedelta(days=7)); snack(f"{fa(n)} مورد به هفتهٔ بعد کپی شد" if n else "چیزی برای کپی نبود (یا قبلاً کپی شده)", bool(n))
            if n: S.update(wk=(ws + timedelta(days=7)).isoformat(), wday=None)
            render()
        acts = ft.Row([btn("کپی به هفتهٔ بعد", lambda e: confirm("کپی هفته", "کارها و ریزه‌کارهای این هفته (بدون روتین‌ها) به‌صورت انجام‌نشده به هفتهٔ بعد کپی شوند؟", copy_next, False), ic("CONTENT_COPY")),
                       btn("روتین‌ها و نماز", lambda e: (S.update(tab=6, rt_back=S["tab"]), render()), ic("EVENT_REPEAT"), False)], spacing=8, wrap=True)
        from store import QUOTES
        q = QUOTES[today().toordinal() % len(QUOTES)]
        quote = card(ft.Row([ibadge(ic("FORMAT_QUOTE"), "blue", 40, filled=True, radius=14), ft.Column([txt(q[0], 13, ft.FontWeight.W_700), txt(q[1], 11, color="muted")], spacing=2, expand=True)], spacing=12), tint="blue", pad=14, radius=22, shadow=False)
        out = [page_hero("week", "هفته", "برنامه‌ریزی و مدیریت هفته", tools=[settings_btn()]), nav, strip, agenda, goals_card, status, tasks_card, acts, quote]
        return out + [spacer()]

    # ======================================================================== یادداشت‌ها
    def fmt_stamp(iso): return jshort(iso[:10]) + " • " + fa(iso[11:16])

    def open_note(nid=None, cat=None): S.update(tab=8 + 1, note_id=nid, note_cat=cat); render()

    def note_card(r, tags):
        pinned = bool(r["pinned"]); name, icon, col = CAT.get(r["category"] or "other", CAT["other"])
        menu = ft.PopupMenuButton(icon=ic("MORE_VERT"), icon_color=P["muted"], items=[
            ft.PopupMenuItem(text="ویرایش", icon=ic("EDIT", "outlined"), on_click=lambda e, x=r: open_note(x["id"])),
            ft.PopupMenuItem(text="برداشتن سنجاق" if pinned else "سنجاق کردن", icon=ic("PUSH_PIN", "outlined"), on_click=lambda e, x=r: (store.set_note_pinned(x["id"], not x["pinned"]), render())),
            ft.PopupMenuItem(text="حذف", icon=ic("DELETE", "outlined"), on_click=lambda e, x=r: confirm("حذف", "این یادداشت حذف شود؟", lambda: (store.delete_note(x["id"]), render())))])
        edited = r["updated_at"][:16] != r["created_at"][:16]
        head = ft.Row([ibadge(ic(icon, "outlined"), col, 38, radius=13), ft.Column([ft.Row([txt(r["title"] or "(بدون عنوان)", 15, ft.FontWeight.W_700, expand=True, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                                                                                         *([ft.Icon(ic("PUSH_PIN"), size=15, color=P["gold"])] if pinned else [])], spacing=4),
                                                                      txt(r["body"][:140], 12, color="muted", max_lines=2, overflow=ft.TextOverflow.ELLIPSIS)], spacing=2, expand=True), menu], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START)
        foot = ft.Row([chip(name, col), *[chip("#" + x, "blue") for x in tags[:3]], ft.Container(expand=True),
                       ft.Icon(ic("SCHEDULE", "outlined"), size=12, color=P["muted"]), txt(fmt_stamp(r["created_at"]) + (" • ویرایش‌شده" if edited else ""), 10, color="muted")], spacing=6, vertical_alignment=ft.CrossAxisAlignment.CENTER, wrap=False)
        return card(ft.Column([head, foot], spacing=8), pad=ft.padding.only(left=4, right=12, top=10, bottom=10), radius=24, margin=ft.margin.only(bottom=8), tint=col if pinned else None, shadow=False, on_click=lambda e, x=r: open_note(x["id"]), data=("note", r["id"]))

    def event_form():
        t = field("عنوان (اختیاری)"); b = field("توضیحات", multiline=True, min_lines=2); h = ui.time_field("ساعت (HH:MM)", datetime.now().strftime("%H:%M"))
        dfield, get, _ = ctx.jdate_field("تاریخ", today().isoformat())
        def save():
            time_s = ui.norm_time(h.value)
            if not time_s: snack("ساعت نامعتبر است (مثلاً ۰۸:۳۰)", False); return False
            store.run("INSERT INTO day_events(title,body,date,time) VALUES(?,?,?,?)", (t.value, b.value, get(), time_s)); render()
        dialog("اتفاق جدید", [t, b, dfield, h], save, icon="EVENT_NOTE")

    def page_notes():
        counts = store.note_counts(); allc = sum(counts.values()); ev = S["notes_tab"] == 1; cat = S["ncat"]
        if S["tag"] and S["tag"] not in {t["name"] for t in store.all_tags()}: S["tag"] = None      # برچسب دیگر وجود ندارد (یادداشتش حذف یا برچسبش برداشته شد): فیلتر بی‌خروجی نماند
        def pick(c): S.update(ncat=c, notes_tab=0, note_n=30, tag=None if c is None else S["tag"]); render()
        chips_ = [chip(f"همه {fa(allc)}", "gold", ic("APPS"), on_click=lambda e: pick(None), solid=(cat is None and not ev))]
        for k, (nm, icon, col) in CAT.items(): chips_.append(chip(nm + (f" {fa(counts[k])}" if counts[k] else ""), col if col != "muted" else "gold", ic(icon, "outlined"), on_click=lambda e, k=k: pick(k), solid=(cat == k and not ev)))
        chips_.append(chip("اتفاقات روز", "blue", ic("EVENT_NOTE", "outlined"), on_click=lambda e: (S.update(notes_tab=1), render()), solid=ev))
        out = [page_hero("notes", "یادداشت‌ها", "ثبت ایده‌ها و یادداشت‌ها", tools=[settings_btn()])]
        if not ev:
            results = ft.Column(spacing=0)
            def note_cards():
                rows = store.search_notes(S["q"], S["tag"], S["note_n"] + 1, category=S["ncat"]); more = len(rows) > S["note_n"]; rows = rows[:S["note_n"]]
                tagmap = store.tags_for_notes([r["id"] for r in rows]); cs = [note_card(r, tagmap.get(r["id"], [])) for r in rows]
                if more: cs.append(chip("نمایش یادداشت‌های بیشتر", "blue", ic("EXPAND_MORE"), on_click=lambda e: (S.update(note_n=S["note_n"] + 30), render())))
                return cs or [empty(ic("EDIT_NOTE", "outlined"), "یادداشتی پیدا نشد.\nبا دکمهٔ ＋ پایین صفحه یک یادداشت بساز")]
            results.controls = note_cards()
            def search(e): S["q"] = e.control.value; S["note_n"] = 30; results.controls = note_cards(); results.update()
            out.append(field("جست‌وجو در یادداشت‌ها…", S["q"], prefix_icon=ic("SEARCH"), on_change=search))
            out.append(ft.Row(chips_, spacing=6, scroll=ft.ScrollMode.AUTO))
            tags = store.all_tags()
            if tags: out.append(ft.Row([chip("برچسب‌ها:", "muted"), *[chip("#" + t["name"], "blue", on_click=lambda e, n=t["name"]: (S.update(tag=None if S["tag"] == n else n), render()), solid=S["tag"] == t["name"]) for t in tags]], spacing=6, scroll=ft.ScrollMode.AUTO))
            out.append(results)
        else:
            out.append(ft.Row(chips_, spacing=6, scroll=ft.ScrollMode.AUTO))
            out.append(section("اتفاقات روز", pill_btn("ثبت اتفاق", ic("ADD"), lambda e: event_form()), ic("EVENT_NOTE", "outlined")))
            rows = store.all("SELECT * FROM day_events ORDER BY date DESC,time LIMIT ?", (S["ev_n"] + 1,)); more_ev = len(rows) > S["ev_n"]; rows = rows[:S["ev_n"]]
            for r in rows:
                out.append(card(ft.Row([ft.Container(ft.Column([txt(fa(r["time"]), 14, ft.FontWeight.W_800, "gold"), txt(J.fmt(r["date"], "short"), 11, color="muted")], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER), width=62),
                                        ft.Container(width=1, height=36, bgcolor=alpha(P["line"], .12)), ft.Column([txt(r["title"] or "اتفاق", 14, ft.FontWeight.W_600), txt(r["body"], 12, color="muted")], spacing=2, expand=True),
                                        ft.IconButton(ic("DELETE", "outlined"), icon_color=P["muted"], on_click=lambda e, i=r["id"]: (store.run("DELETE FROM day_events WHERE id=?", (i,)), render()))], spacing=8), margin=ft.margin.only(bottom=8)))
            if more_ev: out.append(chip("نمایش اتفاق‌های بیشتر", "blue", ic("EXPAND_MORE"), on_click=lambda e: (S.update(ev_n=S["ev_n"] + 40), render())))
            if not rows: out.append(empty(ic("EVENT_NOTE", "outlined"), "هنوز اتفاقی ثبت نکردی"))
        return out + [spacer()]

    # ---- ویرایشگر یادداشت با ذخیرهٔ خودکار
    NOTE = {"save": None}
    def page_note_editor():
        nid = S.get("note_id"); row = store.note(nid) if nid else None
        if nid and not row: S.update(tab=3, note_id=None); return page_notes()
        st = {"id": nid, "cat": (row["category"] if row else S.get("note_cat")) or "other", "pin": bool(row["pinned"]) if row else False, "gen": 0, "dirty": False}
        status = txt("ذخیرهٔ خودکار فعال است" if not row else "ذخیره‌شده • " + fmt_stamp(row["updated_at"]), 11, color="muted")
        t = field("عنوان", row["title"] if row else ""); b = field("متن یادداشت", row["body"] if row else "", multiline=True, min_lines=9, max_lines=20)
        tg = field("برچسب‌ها (با ویرگول جدا کن)", "، ".join(store.note_tag_names(nid)) if row else "")
        cats = ft.Row([], spacing=6, scroll=ft.ScrollMode.AUTO)
        pin = ft.IconButton(ic("PUSH_PIN") if st["pin"] else ic("PUSH_PIN", "outlined"), icon_color=P["gold"] if st["pin"] else P["muted"], tooltip="سنجاق")
        def set_status(msg):
            status.value = msg
            try: status.update()
            except Exception: pass
        def has_content(): return bool((t.value or "").strip() or (b.value or "").strip())
        def save_now():
            if not has_content(): return False
            tags = [x for x in (tg.value or "").replace("،", ",").split(",")]
            st["id"] = store.save_note((t.value or "").strip(), b.value or "", tags, st["id"], st["cat"]); S["note_id"] = st["id"]
            store.set_note_pinned(st["id"], st["pin"]); st["dirty"] = False; set_status("ذخیره شد • " + fa(datetime.now().strftime("%H:%M:%S"))); return True
        def commit(g):
            if g == st["gen"]:
                try: save_now()
                except Exception as ex: set_status("ذخیره نشد: " + str(ex))
        def changed(e=None):
            st["gen"] += 1; st["dirty"] = True; g = st["gen"]; set_status("در حال ذخیره…"); later(lambda: commit(g), .8)
        for f in (t, b, tg): f.on_change = changed
        def paint_cats(update=True):
            cats.controls = [chip(nm, col if col != "muted" else "gold", ic(icon, "outlined"), on_click=lambda e, k=k: pick_cat(k), solid=st["cat"] == k) for k, (nm, icon, col) in CAT.items()]
            if update: cats.update()
        def pick_cat(k): st["cat"] = k; paint_cats(); changed()
        def toggle_pin(e):
            st["pin"] = not st["pin"]; pin.icon = ic("PUSH_PIN") if st["pin"] else ic("PUSH_PIN", "outlined"); pin.icon_color = P["gold"] if st["pin"] else P["muted"]; pin.update(); changed()
        pin.on_click = toggle_pin; paint_cats(False)
        def leave(e=None): flush(); S.update(tab=3, note_id=None); render()
        def drop(e): confirm("حذف", "این یادداشت حذف شود؟", lambda: (st["id"] and store.delete_note(st["id"]), st.update(gen=st["gen"] + 1), S.update(tab=3, note_id=None), render()))
        def flush():
            st["gen"] += 1                                  # ذخیره‌های معلقِ زمان‌دار باطل می‌شوند
            if has_content():
                if st["dirty"]: save_now()
            elif st["id"]: store.delete_note(st["id"]); st["id"] = None       # یادداشت کاملاً خالی نگه داشته نمی‌شود
        NOTE["save"] = flush
        head = ft.Row([ft.IconButton(ic("ARROW_FORWARD"), tooltip="بازگشت", on_click=leave), txt("ویرایش یادداشت" if row else "یادداشت جدید", 18, ft.FontWeight.W_800, expand=True), pin,
                       ft.IconButton(ic("DELETE", "outlined"), icon_color=P["muted"], tooltip="حذف", on_click=drop)])
        meta = [chip("ثبت: " + fmt_stamp(row["created_at"]), "muted", ic("SCHEDULE", "outlined"))] if row else [chip("تاریخ و ساعت ثبت: " + fmt_stamp(datetime.now().isoformat(timespec="seconds")), "muted", ic("SCHEDULE", "outlined"))]
        return [head, ft.Row([status, ft.Row(meta)], alignment=ft.MainAxisAlignment.SPACE_BETWEEN), txt("دسته‌بندی", 12, color="muted"), cats, t, b, tg, spacer(24)]

    # ======================================================================== پیشرفت
    def total_study_minutes(): return store.one("SELECT COALESCE(SUM(minutes),0) n FROM study_logs")["n"] + store.focus_seconds() // 60

    def level_card(s):
        xp, lvl = s["xp"], s["level"]; lo, hi = xp_threshold(lvl), xp_threshold(lvl + 1); frac = min(1, (xp - lo) / max(1, hi - lo))
        center = ft.Column([ft.Icon(ic("STAR"), size=26, color=P["gold"]), txt(fa(lvl), 22, ft.FontWeight.W_800, "gold"), txt("سطح", 10, color="muted")], spacing=0, horizontal_alignment=ft.CrossAxisAlignment.CENTER, alignment=ft.MainAxisAlignment.CENTER)
        return card(ft.Column([ft.Row([ring(frac, 112, 10, "gold", key="plvl", center=center),
                                       ft.Column([txt(f"سطح {fa(lvl)} • {level_title(lvl)}", 18, ft.FontWeight.W_800, "gold"), ft.Row([ft.Icon(ic("BOLT", "outlined"), size=16, color=P["gold"]), count_up(xp, 20, ft.FontWeight.W_800, None, " XP", key="pxp")], spacing=4),
                                                  txt(f"{fa(hi - xp)} XP تا سطح {fa(lvl + 1)}", 12, color="muted")], spacing=6, expand=True)], spacing=16, vertical_alignment=ft.CrossAxisAlignment.CENTER),
                               pbar(frac, "gold", 8, off=68, key="pxpbar")], spacing=12), grad=True, pad=16, radius=28)

    def stat_card(icon, label, val, col, key=None, sub=None):
        v = count_up(val, 20, ft.FontWeight.W_800, key=key) if isinstance(val, int) else txt(val, 20, ft.FontWeight.W_800)
        return ft.Container(card(ft.Column([ibadge(ic(icon), col, 38, radius=13), v, txt(label, 11, color="muted"), *([txt(sub, 10, color="muted")] if sub else [])], spacing=5), pad=14), col=6)

    def chart_card(kind, titles):
        metric = S["prog_metric"]; ser = store.series(kind); vals = [x[metric] for x in ser]; cur = next((i for i, x in enumerate(ser) if x["current"]), None)
        mets = ft.Row([chip(lab, "gold", on_click=lambda e, k=k: (S.update(prog_metric=k), render()), solid=metric == k) for k, lab in METRICS], spacing=6, wrap=True)
        total = sum(vals); unit = dict(METRICS)[metric]
        return card(ft.Column([ft.Row([ft.Row([ibadge(ic("BAR_CHART"), "gold", 28, radius=9), txt(titles, 14, ft.FontWeight.W_700)], spacing=8), txt(f"مجموع: {fa(total)}", 12, color="gold")], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                               mets, bars(vals, [x["label"] for x in ser], cur, 108, "gold", key=f"c_{kind}_{metric}_"), txt(f"معیار نمودار: {unit}", 10, color="muted")], spacing=10), pad=16, radius=26)

    def report_card():
        rep = store.weekly_report()
        def delta(a, b):
            if not b: return txt("", 10)
            pc = round((a / b - 1) * 100); up = pc >= 0
            return txt(f"{'▲' if up else '▼'} {fa(abs(pc))}٪", 10, ft.FontWeight.W_700, "green" if up else "red")
        def mini(label, val, a, b): return ft.Column([txt(val, 16, ft.FontWeight.W_800), txt(label, 11, color="muted"), delta(a, b)], spacing=2, horizontal_alignment=ft.CrossAxisAlignment.CENTER, expand=True)
        rc, rp = rep["cur"], rep["prev"]
        return card(ft.Column([ft.Row([ibadge(ic("INSIGHTS"), "gold", 28, radius=9), txt("گزارش هفته", 14, ft.FontWeight.W_700)], spacing=8),
                               ft.Row([mini("مطالعه", ctx.fmt_minutes(rc["minutes"]), rc["minutes"], rp["minutes"]), mini("کار انجام‌شده", fa(rc["done"]), rc["done"], rp["done"]), mini("روز فعال", f"{fa(rc['days'])} از ۷", rc["days"], rp["days"])], spacing=4),
                               *[ft.Row([ft.Icon(ic("LIGHTBULB", "outlined"), size=16, color=P["gold"]), txt(x, 12, expand=True)], spacing=8, vertical_alignment=ft.CrossAxisAlignment.START) for x in rep["tips"]],
                               txt("مقایسه با ۷ روز قبل از آن", 10, color="muted")], spacing=10), pad=16, radius=26)

    def heat_card():
        weeks, counts = store.heatmap(5); cols = []
        for wk in weeks:
            cells = []
            for d in wk:
                n = counts.get(d.isoformat(), 0)
                bg = "transparent" if d > today() else alpha(P["text"], .08) if n == 0 else alpha(P["gold"], .35 if n == 1 else .65 if n == 2 else 1)
                cells.append(ft.Container(width=17, height=17, border_radius=5, bgcolor=bg, border=ft.border.all(1.5, P["gold"]) if d == today() else None))
            cols.append(ft.Column(cells, spacing=4))
        return card(ft.Column([ft.Row([ibadge(ic("GRID_VIEW"), "gold", 28, radius=9), txt("نقشهٔ پیوستگی ۵ هفته", 14, ft.FontWeight.W_700)], spacing=8), ft.Row(cols, alignment=ft.MainAxisAlignment.SPACE_EVENLY),
                               legend_scale(), txt("هر خانه یک روز است؛ هرچه پررنگ‌تر، فعالیت بیشتر", 11, color="muted", text_align=ft.TextAlign.CENTER)], spacing=10), pad=16, radius=26)

    def countdown_card(s):
        exam = store.pref("exam_date"); goal_txt = store.pref("goal") or "هدفت را تعیین کن"; msg, sub = "تاریخ آزمون را تعیین کن", goal_txt
        if exam:
            try:
                d = J.days_until(exam); msg = f"{fa(d)} روز تا آزمون" if d > 0 else "آزمون امروز است، موفق باشی!" if d == 0 else "تاریخ آزمون گذشته است"
                left = s["topics"] - s["mastered"]; sub = f"{J.fmt(exam)} • {goal_txt}" + (f" • {fa(left)} مبحث تا تسلط کامل" if left > 0 and d > 0 else "")
                pace = store.exam_pace()
                if pace: sub += f" • برای رسیدن، هفته‌ای حدود {fa(pace['per_week'])} مبحث لازم است"
            except Exception: msg = "تاریخ آزمون ثبت شده است"
        return card(ft.Row([ibadge(ic("EVENT_AVAILABLE"), "gold", 48, filled=True, radius=16), ft.Column([txt(msg, 16, ft.FontWeight.W_800), txt(sub, 12, color="muted")], spacing=2, expand=True),
                            ft.IconButton(ic("EDIT_CALENDAR", "outlined"), icon_color=P["gold"], on_click=lambda e: ctx.set_exam())], spacing=12), grad=True)

    def achievements_block():
        have = store.unlocked(); ach = []
        for aid, t, d, e, _ in ACHIEVEMENTS:
            ok = aid in have; icon, col = ui.ACHIEVEMENT_ICONS.get(aid, ("EMOJI_EVENTS", "gold"))
            badge = ibadge(ic(icon), col, 46, filled=True, radius=16) if ok else ibadge(ic("LOCK", "outlined"), "muted", 46, radius=16)
            ach.append(ft.Container(card(ft.Column([badge, txt(t, 11, ft.FontWeight.W_700, "gold" if ok else "muted", text_align=ft.TextAlign.CENTER)], spacing=6, horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                                         pad=10, bg=None if ok else alpha(P["card"], .45), on_click=lambda e, t=t, d=d: snack(f"{t}: {d}"), shadow=ok), col=4))
        return [section("دستاوردهای من", txt(f"{fa(len(have))} از {fa(len(ACHIEVEMENTS))}", 12, color="muted"), ic("EMOJI_EVENTS")), ft.ResponsiveRow(ach, spacing=8, run_spacing=8)]

    def roadmap_block():
        stages = store.roadmap(); first = next((i for i, x in enumerate(stages) if x[2] < x[3]), len(stages)); tl = []
        for i, (name, rule, have_n, need) in enumerate(stages):
            ok = have_n >= need; act = i == first
            icon, col = ("CHECK_CIRCLE", "green") if ok else ("FLAG_CIRCLE" if act else "LOCK", "gold" if act else "muted")
            tl.append(card(ft.Row([ibadge(ic(icon, "rounded" if ok or act else "outlined"), col, 42, filled=act, radius=14), ft.Column([txt(name, 14, ft.FontWeight.W_700), txt(rule, 12, color="muted"),
                           pbar(min(have_n, need) / need, col, 6, off=146, key=f"road{i}"), txt(f"{fa(min(have_n, need))} از {fa(need)}", 11, color=col)], spacing=6, expand=True)], spacing=12, vertical_alignment=ft.CrossAxisAlignment.START),
                           bg=None if (ok or act) else alpha(P["card"], .5), margin=ft.margin.only(bottom=8), shadow=act, border=ft.border.all(1.2, alpha(P["gold"], .55)) if act else None))
        return [section("نقشهٔ مسیر", None, ic("ROUTE")), *tl]

    def page_progress():
        s = store.stats(); tab = S["prog_tab"]; sm = store.test_summary(); g = store.growth_pct(); wk = store.weekly_report()
        out = [page_hero("progress", "پیشرفت", "مسیر رشد تو", tools=[settings_btn()]),
               pill_tabs([("overall", "کلی", None), ("day", "روزانه", None), ("week", "هفتگی", None), ("month", "ماهانه", None)], tab, lambda k: (S.update(prog_tab=k), render())), level_card(s)]
        if tab == "overall":
            grid = ft.ResponsiveRow([stat_card("LOCAL_FIRE_DEPARTMENT", "رکورد استمرار", f"{fa(s['best_streak'])} روز", "red", sub=f"استمرار فعلی: {fa(s['streak'])} روز"),
                                     stat_card("CHECK_CIRCLE", "وظایف تکمیل‌شده", s["done"], "green", "pdone", sub=f"از {fa(s['missions'])} وظیفه"),
                                     stat_card("TRENDING_UP", "رشد کلی", ("+" if g >= 0 else "−") + fa(abs(g)) + "٪", "gold", sub="XP این هفته در برابر هفتهٔ قبل"),
                                     stat_card("MENU_BOOK", "کل زمان مطالعه", ctx.fmt_minutes(total_study_minutes()), "violet"),
                                     stat_card("WORKSPACE_PREMIUM", "مباحث مسلط", f"{fa(s['mastered'])} از {fa(s['topics'])}", "blue"),
                                     stat_card("FACT_CHECK", "میانگین موفقیت تست", (fa(sm["success"]) + "٪") if sm["success"] is not None else "—", "green", sub=f"{fa(sm['total'])} تست")], spacing=10, run_spacing=10)
            out += [grid, countdown_card(s), chart_card("day", "نمودار پیشرفت (۷ روز اخیر)"), report_card(), *achievements_block(), heat_card(), *roadmap_block()]
        elif tab == "day":
            ser = store.series("day"); t = ser[-1]
            out += [ft.Row([stat_tile(ic("BOLT", "outlined"), "gold", fa(t["xp"]), "XP امروز"), stat_tile(ic("MENU_BOOK", "outlined"), "violet", ctx.fmt_minutes(t["minutes"]) if t["minutes"] else "—", "مطالعهٔ امروز"),
                            stat_tile(ic("TASK_ALT", "outlined"), "green", fa(t["done"]), "کار امروز")], spacing=8), chart_card("day", "نمودار روزانه (۷ روز اخیر)"), heat_card()]
        elif tab == "week":
            out += [chart_card("week", "نمودار هفتگی (۸ هفته اخیر)"), report_card(),
                    ft.Row([stat_tile(ic("BOLT", "outlined"), "gold", fa(wk["cur"]["xp"]), "XP این هفته"), stat_tile(ic("CALENDAR_MONTH", "outlined"), "blue", f"{fa(wk['cur']['days'])} از ۷", "روز فعال"), stat_tile(ic("TASK_ALT", "outlined"), "green", fa(wk["cur"]["done"]), "کار انجام‌شده")], spacing=8)]
        else:
            ser = store.series("month"); t = ser[-1]
            out += [chart_card("month", "نمودار ماهانه (۶ ماه اخیر)"),
                    ft.Row([stat_tile(ic("BOLT", "outlined"), "gold", fa(t["xp"]), f"XP {t['label']}"), stat_tile(ic("MENU_BOOK", "outlined"), "violet", ctx.fmt_minutes(t["minutes"]) if t["minutes"] else "—", "مطالعه"), stat_tile(ic("TASK_ALT", "outlined"), "green", fa(t["done"]), "کار انجام‌شده")], spacing=8)]
        return out + [spacer()]

    return SimpleNamespace(study=page_study, subject=page_subject, week=page_week, notes=page_notes, note_editor=page_note_editor, progress=page_progress,
                           new_note=lambda: open_note(None), flush_note=lambda: NOTE["save"]() if NOTE["save"] else None)
