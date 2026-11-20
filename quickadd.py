# -*- coding: utf-8 -*-
"""ورود سریع هوشمند: از یک جملهٔ فارسی تاریخ، ساعت، مدت و اولویت را می‌فهمد.
مثال: «فردا ساعت ۱۶:۳۰ حل تمرین فیزیک ۴۵ دقیقه مهم».  تابع خالص است و به دیتابیس یا رابط وابسته نیست."""
import re
from datetime import date, timedelta

_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_WD = {"شنبه": 5, "یکشنبه": 6, "دوشنبه": 0, "سهشنبه": 1, "چهارشنبه": 2, "پنجشنبه": 3, "جمعه": 4}
_REL = {"امروز": 0, "فردا": 1, "پسفردا": 2}
_NAMES = {0: "امروز", 1: "فردا", 2: "پس‌فردا"}
_PM = ("عصر", "شب", "بعدازظهر")

def _norm(s): return re.sub(r"بعد\s*از\s*ظهر", "بعدازظهر", s.translate(_DIG).replace("\u200c", "").replace("ي", "ی").replace("ك", "ک"))      # «بعد از ظهر» هم یک واژه است
def _cut(s, m): return s[:m.start()] + " " + s[m.end():]

def parse(text, today=None):
    """-> dict(title, date, time, minutes, priority, notes). date/time/minutes خالی یعنی در جمله نبوده؛ priority پیش‌فرض ۱."""
    today = today or date.today(); s = " " + _norm(text) + " "; out = dict(title="", date="", time="", minutes=0, priority=1, notes=[])
    # اولویت
    m = re.search(r"(?<!\w)(مهم|فوری|ضروری)(?!\w)|!", s)
    if m: out["priority"] = 2; s = _cut(s, m); out["notes"].append("مهم")
    # تاریخ نسبی و نام روز هفته
    m = re.search(r"(?<!\w)(\d{1,3})\s*روز\s*(?:دیگه|دیگر|بعد)(?!\w)", s)
    if m and 0 < int(m.group(1)) <= 365:
        out["date"] = (today + timedelta(days=int(m.group(1)))).isoformat(); out["notes"].append(f"{m.group(1)} روز دیگر"); s = _cut(s, m)
    else:
        for w, k in sorted(_REL.items(), key=lambda x: -len(x[0])):
            m = re.search(rf"(?<!\w){w}(?!\w)", s)
            if m: out["date"] = (today + timedelta(days=k)).isoformat(); out["notes"].append(_NAMES[k]); s = _cut(s, m); break
        else:
            for w, wd in sorted(_WD.items(), key=lambda x: -len(x[0])):
                m = re.search(rf"(?<!\w){w}(?!\w)", s)
                if m:
                    gap = (wd - today.weekday()) % 7 or 7                       # نزدیک‌ترین روز آینده (نه امروز)
                    out["date"] = (today + timedelta(days=gap)).isoformat(); out["notes"].append(w); s = _cut(s, m); break
    # مدت
    m = re.search(r"(?<!\w)نیم\s*ساعت(?!\w)", s)
    if m: out["minutes"] = 30; s = _cut(s, m)
    else:
        m = re.search(r"(?<!\w)(\d{1,3}(?:[.,]\d)?)\s*(دقیقه|ساعت)(?!\s*\d)(?!\w)", s)
        if m:
            n = float(m.group(1).replace(",", ".")); mins = int(round(n * (60 if m.group(2) == "ساعت" else 1)))
            if 0 < mins <= 12 * 60: out["minutes"] = mins; s = _cut(s, m)
    # ساعت شروع (۱۶:۳۰ یا «ساعت ۴ عصر»)
    period = re.search(r"(?<!\w)(صبح|ظهر|بعدازظهر|عصر|شب)(?!\w)", s); h = mi = None; m = re.search(r"(?:(?<!\w)ساعت\s*)?(?<!\d)(\d{1,2}):(\d{2})(?!\d)", s)
    if m: h, mi = int(m.group(1)), int(m.group(2))
    else:
        m = re.search(r"(?<!\w)ساعت\s*(\d{1,2})(?!\d)", s)
        if m: h, mi = int(m.group(1)), 0
    if m and h is not None and h < 24 and mi < 60:
        pw = period.group(1) if period else ""
        if pw == "شب":                                                          # ۱۲ شب = ۰۰:۰۰، ۱ تا ۵ شب = بامداد، ۶ تا ۱۱ شب = ۱۸ تا ۲۳
            if h == 12: h = 0
            elif 6 <= h < 12: h += 12
        elif pw and h < 12 and (pw in _PM or (pw == "ظهر" and h <= 5)): h += 12
        out["time"] = f"{h:02d}:{mi:02d}"; s = _cut(s, m)
        if period: s = s.replace(period.group(0), " ", 1)
    t = re.sub(r"\s+", " ", s).strip(" \t،,:-؛")
    out["title"] = t or re.sub(r"\s+", " ", _norm(text)).strip()
    return out
