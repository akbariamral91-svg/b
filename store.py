# -*- coding: utf-8 -*-
"""لایه داده و منطق Get Better (بدون وابستگی به UI).

ویژگی‌ها: XP و سطح، استریک، مرور فاصله‌دار (لایتنر)، تسلط مبحث، دستاوردها،
تایمر تمرکز، مأموریت‌های تکرارشونده، برنامهٔ هوشمند، آمار هفتگی و پشتیبان‌گیری.
"""
import sqlite3, json, os, glob, re, traceback
from datetime import date, datetime, timedelta
from jalali import fa, en  # noqa: F401  (برای سازگاری: from store import fa)

TABLES = ['routines', 'missions', 'xp_ledger', 'subjects', 'topics', 'study_logs', 'quiz_logs', 'achievements',
          'notes', 'tags', 'note_tags', 'day_events', 'focus_sessions', 'week_goals', 'settings']
BACKUP_VERSION = 3
SCHEMA_VERSION = 6                       # شمارهٔ نسخهٔ ساختار دیتابیس (PRAGMA user_version)
BOX_DAYS = [1, 3, 7, 30, 90]              # جعبه‌های لایتنر: ۱ روز، ۳ روز، ۱ هفته، ۱ ماه، ۳ ماه بعد
REPEATS = {"": "بدون تکرار", "daily": "هر روز", "weekly": "هر هفته"}
DEFAULTS = {"onboarded": "0", "last_auto_backup": "", "theme": "dark", "goal": "", "exam_date": "", "daily_goal": "3", "pomodoro": "25", "break": "5", "notify_on": "1", "notify_hour": "19"}

LEVEL_TITLES = ["نوآموز", "کنجکاو", "کوشا", "پیگیر", "مصمم", "حرفه‌ای", "استاد", "نخبه", "افسانه"]

# نمازهای پنجگانه؛ خودکار به‌عنوان روتین روزانه ساخته می‌شوند (کلید، عنوان، نام کوتاه)
PRAYERS = [("prayer_fajr", "نماز صبح", "صبح"), ("prayer_dhuhr", "نماز ظهر", "ظهر"), ("prayer_asr", "نماز عصر", "عصر"),
           ("prayer_maghrib", "نماز مغرب", "مغرب"), ("prayer_isha", "نماز عشا", "عشا")]
KINDS_TASK = {"task": "کار", "chore": "ریزه‌کار"}      # کار: ساعت/مدت دارد • ریزه‌کار: کار کوچک بدون ساعت معین
CHORE_XP = 5
WEEK_ORDER = [5, 6, 0, 1, 2, 3, 4]                   # شنبه … جمعه (weekday پایتون)
ALL_DAYS = ",".join(map(str, WEEK_ORDER))

def data_dir():
    # روی اندروید پوشه برنامه فقط‌خواندنی است؛ Flet مسیر داده را در این متغیر می‌دهد
    d = os.getenv("FLET_APP_STORAGE_DATA") or os.path.dirname(os.path.abspath(__file__))
    os.makedirs(d, exist_ok=True)
    return d

def log_error(where, exc=None):
    """خطا را در errors.log کنار دیتابیس می‌نویسد (چرخشی، حداکثر حدود ۲۰۰ کیلوبایت). هرگز خطا نمی‌دهد."""
    try:
        p = os.path.join(data_dir(), "errors.log")
        if os.path.exists(p) and os.path.getsize(p) > 200_000: os.replace(p, p + ".1")
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().isoformat(timespec='seconds')}] {where}\n")
            if exc is not None: f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)) + "\n")
    except Exception: pass

def read_error_log(limit=6000):
    try:
        with open(os.path.join(data_dir(), "errors.log"), encoding="utf-8") as f: return f.read()[-limit:]
    except OSError: return ""

def clear_error_log():
    try: os.remove(os.path.join(data_dir(), "errors.log"))
    except OSError: pass

def xp_for_mission(minutes, priority):
    return max(10, min(100, 10 + int(minutes) // 5 + int(priority) * 5))
def xp_for(kind, minutes, priority):
    return CHORE_XP if kind == "chore" else xp_for_mission(minutes or 0, priority)
def xp_threshold(level): return 50 * (level - 1) * level
def level_for_xp(xp):
    level = 1
    while xp >= xp_threshold(level + 1): level += 1
    return level
def level_title(level): return LEVEL_TITLES[min(level - 1, len(LEVEL_TITLES) - 1)]

# --- دستاوردها: (شناسه، عنوان، توضیح، ایموجی، شرط روی stats)
ACHIEVEMENTS = [
    ("first_step", "اولین قدم", "اولین مأموریت را کامل کن", "🌱", lambda s: s["done"] >= 1),
    ("ten_missions", "ده‌تایی", "۱۰ مأموریت کامل کن", "🔟", lambda s: s["done"] >= 10),
    ("fifty_missions", "ماشین مأموریت", "۵۰ مأموریت کامل کن", "⚙️", lambda s: s["done"] >= 50),
    ("streak_3", "سه روز پیاپی", "۳ روز پشت‌سرهم فعالیت کن", "🔥", lambda s: s["best_streak"] >= 3),
    ("streak_7", "هفتهٔ آهنین", "۷ روز پشت‌سرهم فعالیت کن", "⚡", lambda s: s["best_streak"] >= 7),
    ("streak_30", "ماه بی‌وقفه", "۳۰ روز پشت‌سرهم فعالیت کن", "👑", lambda s: s["best_streak"] >= 30),
    ("level_5", "سطح ۵", "به سطح ۵ برس", "🚀", lambda s: s["level"] >= 5),
    ("mastered_1", "مسلط شدی", "یک مبحث را به تسلط برسان", "🎓", lambda s: s["mastered"] >= 1),
    ("exam_1", "اولین آزمون", "یک آزمون ≥۱۰ سؤالی ثبت کن", "📝", lambda s: s["exams"] >= 1),
    ("perfect", "نمرهٔ کامل", "در آزمونی (≥۱۰ سؤال) ۱۰۰٪ بگیر", "💯", lambda s: s["perfect"] >= 1),
    ("focus_5h", "تمرکز عمیق", "۵ ساعت تمرکز ثبت کن", "🎯", lambda s: s["focus_seconds"] >= 5 * 3600),
    ("xp_1000", "هزار امتیازی", "۱۰۰۰ XP جمع کن", "💎", lambda s: s["xp"] >= 1000),
    ("goal_7", "هدف‌زن", "هدف روزانه را در ۷ روز بزن", "🏹", lambda s: s["goal_days"] >= 7),
    ("goal_30", "قهرمان هدف", "هدف روزانه را در ۳۰ روز بزن", "🏆", lambda s: s["goal_days"] >= 30),
]

# --- تحصیل (۴٫۱): شش درس پیش‌فرض با آیکون اختصاصی (assets/icons/<نام>.png)
DEFAULT_SUBJECTS = [("علوم", "science"), ("ریاضی", "math"), ("فارسی", "persian"), ("عربی", "arabic"),
                    ("مطالعات اجتماعی", "geography"), ("پیام‌های آسمانی", "heavenly-messages")]
SUBJECT_ICON = dict(DEFAULT_SUBJECTS)
NOTE_CATS = [("personal", "شخصی"), ("study", "درسی"), ("work", "کاری"), ("idea", "ایده‌ها"), ("other", "سایر")]
MASTERY_LABELS = [(0, "تازه شروع"), (25, "ضعیف"), (50, "متوسط"), (75, "خوب"), (100, "عالی")]

def chapter_key(ch):
    """شمارهٔ فصل از متن («فصل ۷»، «7»، «۷») یا None اگر عددی نباشد."""
    m = re.search(r"\d+", en(str(ch or "")))
    return int(m.group()) if m else None

GOAL_BONUS = 20                                          # پاداش یک‌بار در روز برای رسیدن به هدف روزانه
STREAK_MILESTONES = (3, 7, 14, 30, 60, 100)               # نقاط عطف استریک که جشن می‌گیرند
QUOTES = [
    ("هر روز یک قدمِ کوچک، آخر سال یک جهشِ بزرگ است.", "کوچک شروع کن؛ مهم این است که امروز هم حساب شود."),
    ("لازم نیست عالی باشی؛ فقط لازم است شروع کنی.", "۱۰ دقیقه هم ۱۰ دقیقه است."),
    ("آدم‌های موفق انگیزه را منتظر نمی‌مانند؛ اول کار می‌کنند، بعد انگیزه می‌آید.", "یک کار ساده را همین حالا تیک بزن."),
    ("امروزِ تو، نتیجهٔ روز آزمونِ توست.", "هر مرور، یک سؤالِ کمتر که غافلگیرت کند."),
    ("پیوستگی از شدت مهم‌تر است.", "کم ولی هر روز، از زیاد ولی گاهی بهتر است."),
    ("سخت‌ترین قسمت، نشستن پشت میز است.", "تایمر تمرکز را روشن کن و ۲۵ دقیقه فقط همین."),
    ("تو از دیروزت جلوتری؛ فقط ادامه بده.", "به خودت قول بده فقط یک کار."),
]
def _iso(d): return d if isinstance(d, str) else d.isoformat()


class Store:
    def __init__(self, path=None, bare=False):
        """bare=True: اتصال سبک و جدا برای کارهای پس‌زمینه (پشتیبان‌گیری)؛ هیچ ساخت/مهاجرت/بازسازی‌ای نمی‌کند."""
        self.path = path or os.path.join(data_dir(), "get_better.db")
        self.recovery = None                       # None | "restored" | "fresh" — اگر دیتابیس خراب بود و بازسازی شد
        if bare:
            self.db = sqlite3.connect(self.path, check_same_thread=False, timeout=10); self.db.row_factory = sqlite3.Row; return
        self.db = self._open()
        self.init_db()
        if self.recovery == "fresh": self._recover_from_backup()

    def _open(self):
        """اتصال امن: اگر فایل خراب بود کنارش می‌گذارد (برای بررسی) و دیتابیس تازه می‌سازد.
        check_same_thread=False چون Flet رویدادها را در رشته‌های مختلف اجرا می‌کند."""
        def connect():
            db = sqlite3.connect(self.path, check_same_thread=False, timeout=10)
            db.row_factory = sqlite3.Row
            return db
        try:
            db = connect()
            db.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()        # هدر/ساختار خراب را فوراً می‌گیرد؛ quick_check کامل با هر شروع پویش کل فایل بود و به پشتیبان روزانه رفت
        except sqlite3.DatabaseError as ex:
            try: db.close()
            except Exception: pass
            log_error("دیتابیس خراب بود و کنار گذاشته شد", ex)
            try: os.replace(self.path, f"{self.path}.corrupt-{datetime.now():%Y%m%d-%H%M%S}")
            except OSError:
                try: os.remove(self.path)
                except OSError: pass
            db = connect(); self.recovery = "fresh"
        db.execute("PRAGMA foreign_keys=ON")
        try: db.execute("PRAGMA journal_mode=WAL"); db.execute("PRAGMA synchronous=NORMAL")
        except sqlite3.DatabaseError: pass
        return db

    def _recover_from_backup(self):
        for p, _ in self.list_backups():
            try: self.restore(p, snapshot=False); self.recovery = "restored"; return
            except Exception as ex: log_error(f"بازیابی از {os.path.basename(p)} ناموفق بود", ex)

    def close(self):
        try: self.db.close()
        except Exception: pass

    def schema_version(self): return self.db.execute("PRAGMA user_version").fetchone()[0]

    # ---------- ساخت و مهاجرت دیتابیس ----------
    def init_db(self):
        if self.schema_version() == SCHEMA_VERSION:       # ساختار از قبل کامل است: شروع سریع، بدون ۲۰ دستور CREATE/ALTER/INDEX
            try:
                self.db.execute("SELECT 1 FROM settings LIMIT 1"); self.db.execute("SELECT routine_id FROM missions LIMIT 1"); self.db.execute("SELECT category FROM notes LIMIT 1"); self.db.execute("SELECT 1 FROM study_logs LIMIT 1")
                self.seed_prayers(); return
            except sqlite3.DatabaseError: pass             # چیزی کم بود؛ مسیر کامل ساخت/مهاجرت
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS missions(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT NOT NULL,subject TEXT DEFAULT '',description TEXT DEFAULT '',minutes INTEGER DEFAULT 30,priority INTEGER DEFAULT 1,done INTEGER DEFAULT 0,xp INTEGER DEFAULT 10,date TEXT NOT NULL,note TEXT DEFAULT '',spent_seconds INTEGER DEFAULT 0,completed_at TEXT,icon TEXT);
        CREATE TABLE IF NOT EXISTS xp_ledger(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id INTEGER NOT NULL UNIQUE,xp INTEGER NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS subjects(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS topics(id INTEGER PRIMARY KEY AUTOINCREMENT,subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,chapter TEXT DEFAULT '',name TEXT NOT NULL,notes TEXT DEFAULT '',mistakes TEXT DEFAULT '',status INTEGER DEFAULT 0,next_review TEXT);
        CREATE TABLE IF NOT EXISTS quiz_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,kind TEXT NOT NULL,total INTEGER NOT NULL,correct INTEGER NOT NULL,seconds INTEGER,date TEXT NOT NULL,note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS achievements(id TEXT PRIMARY KEY,unlocked_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notes(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT DEFAULT '',body TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL,pinned INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS tags(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL UNIQUE,color TEXT DEFAULT '#E8B84A');
        CREATE TABLE IF NOT EXISTS note_tags(note_id INTEGER NOT NULL REFERENCES notes(id) ON DELETE CASCADE,tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,PRIMARY KEY(note_id,tag_id));
        CREATE TABLE IF NOT EXISTS day_events(id INTEGER PRIMARY KEY AUTOINCREMENT,title TEXT,body TEXT DEFAULT '',date TEXT NOT NULL,time TEXT DEFAULT '00:00',icon TEXT);
        CREATE TABLE IF NOT EXISTS routines(id INTEGER PRIMARY KEY AUTOINCREMENT,key TEXT DEFAULT '',title TEXT NOT NULL,kind TEXT DEFAULT 'chore',minutes INTEGER DEFAULT 0,time TEXT DEFAULT '',days TEXT DEFAULT '',xp INTEGER DEFAULT 5,active INTEGER DEFAULT 1,sort INTEGER DEFAULT 0,created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS focus_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT,mission_id INTEGER,seconds INTEGER NOT NULL,at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS study_logs(id INTEGER PRIMARY KEY AUTOINCREMENT,topic_id INTEGER NOT NULL REFERENCES topics(id) ON DELETE CASCADE,date TEXT NOT NULL,minutes INTEGER DEFAULT 0,mastery INTEGER DEFAULT 0,note TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS week_goals(id INTEGER PRIMARY KEY AUTOINCREMENT,week TEXT NOT NULL,title TEXT NOT NULL,done INTEGER DEFAULT 0,created TEXT NOT NULL);
        """)
        # ستون‌های نسخهٔ ۲ (روی دیتابیس‌های قدیمی هم امن است)
        self._ensure_column("missions", "repeat", "TEXT DEFAULT ''")
        self._ensure_column("missions", "topic_id", "INTEGER")
        self._ensure_column("missions", "kind", "TEXT DEFAULT 'task'")
        self._ensure_column("missions", "time", "TEXT DEFAULT ''")
        self._ensure_column("missions", "routine_id", "INTEGER")
        self._ensure_column("topics", "box", "INTEGER DEFAULT 0")
        self._ensure_column("topics", "mastery", "INTEGER DEFAULT 0")            # نسخهٔ ۶: میزان تسلط (۰ تا ۱۰۰) از آخرین ثبت مطالعه
        self._ensure_column("subjects", "total_chapters", "INTEGER DEFAULT 0")
        self._ensure_column("quiz_logs", "wrong", "INTEGER")
        self._ensure_column("quiz_logs", "blank", "INTEGER")
        self._ensure_column("notes", "category", "TEXT DEFAULT 'other'")
        self.db.executescript("""
        CREATE INDEX IF NOT EXISTS ix_missions_date ON missions(date);
        CREATE INDEX IF NOT EXISTS ix_logs_topic ON quiz_logs(topic_id,date);
        CREATE INDEX IF NOT EXISTS ix_topics_review ON topics(next_review);
        CREATE INDEX IF NOT EXISTS ix_study_topic ON study_logs(topic_id,date);
        CREATE INDEX IF NOT EXISTS ix_goals_week ON week_goals(week);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_missions_routine_day ON missions(routine_id,date) WHERE routine_id IS NOT NULL;
        """)
        for ddl in ("CREATE INDEX IF NOT EXISTS ix_missions_cdate ON missions(date(completed_at))",   # آمار روزانه بدون پویش کل جدول
                    "CREATE INDEX IF NOT EXISTS ix_xp_date ON xp_ledger(date(at))",
                    "CREATE INDEX IF NOT EXISTS ix_focus_date ON focus_sessions(date(at))",
                    "CREATE INDEX IF NOT EXISTS ix_quiz_date ON quiz_logs(date)"):
            try: self.db.execute(ddl)
            except sqlite3.DatabaseError as ex: log_error("ساخت ایندکس", ex)
        self.db.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.db.commit()
        self.seed_prayers()

    def _columns(self, table):
        return [r["name"] for r in self.db.execute(f"PRAGMA table_info({table})")]
    def _ensure_column(self, table, col, ddl):
        if col not in self._columns(table):
            self.db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")

    # ---------- پایه ----------
    def all(self, sql, args=()): return self.db.execute(sql, args).fetchall()
    def one(self, sql, args=()): return self.db.execute(sql, args).fetchone()
    def run(self, sql, args=()):
        cur = self.db.execute(sql, args); self.db.commit(); return cur.lastrowid
    def pref(self, key, default=None):
        r = self.one("SELECT value FROM settings WHERE key=?", (key,))
        if r: return r["value"]
        return DEFAULTS.get(key, "") if default is None else default
    def pref_int(self, key, default=0):
        try: return int(self.pref(key))
        except (TypeError, ValueError): return default
    def setpref(self, key, value):
        self.run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, str(value)))

    # ---------- XP و مأموریت ----------
    def xp(self): return max(0, self.one("SELECT COALESCE(SUM(xp),0) n FROM xp_ledger")["n"])
    def missions_on(self, day):
        """مأموریت‌های یک روز؛ rkey/rsort از روتین (نماز و...) می‌آید. ساخت روتین‌های روز با ensure_day است."""
        return self.all("""SELECT m.*, r.key rkey, COALESCE(r.sort,0) rsort FROM missions m LEFT JOIN routines r ON r.id=m.routine_id
                           WHERE m.date=? ORDER BY m.done, (m.time=''), m.time, m.priority DESC, m.id""", (_iso(day),))
    def today_missions(self): return self.missions_on(date.today())

    # ---------- روتینِ از دست‌رفته (قرمز، خط‌خورده، امتیاز منفی؛ قابل انتقال نیست) ----------
    @staticmethod
    def is_missed(r, today=None):
        """روتینِ روزِ گذشته که انجام نشده؛ دیگر «عقب‌افتاده» نیست، «از دست رفته» است."""
        return r["routine_id"] is not None and not r["done"] and r["date"] < _iso(today or date.today())
    @staticmethod
    def is_locked_routine(r, today=None):
        """روتینِ روزی که گذشته (انجام‌شده یا نه) قفل است؛ وگرنه با یک لمس اشتباه، روتینِ انجام‌شدهٔ دیروز «از دست رفته» و برای همیشه قفل می‌شد."""
        return r["routine_id"] is not None and r["date"] < _iso(today or date.today())
    def settle_missed_routines(self, today=None):
        """برای هر روتینِ انجام‌نشدهٔ روزهای گذشته یک‌بار امتیاز منفی ثبت می‌کند (فقط از روز نصب این قابلیت به بعد،
        تا تاریخچهٔ قدیمی جریمه نشود). دفتر XP یکتاست، پس تکراری ثبت نمی‌شود. تعداد جریمه‌های تازه را برمی‌گرداند."""
        t = _iso(today or date.today())
        since = self.pref("miss_since", "")
        if not since: self.setpref("miss_since", t); return 0
        n = 0
        for m in self.all("""SELECT id,xp,date FROM missions WHERE routine_id IS NOT NULL AND done=0 AND date>=? AND date<?
                             AND id NOT IN (SELECT mission_id FROM xp_ledger)""", (since, t)):
            self.db.execute("INSERT OR IGNORE INTO xp_ledger(mission_id,xp,at) VALUES(?,?,?)", (m["id"], -abs(m["xp"] or 0), m["date"] + "T23:59:00")); n += 1
        if n: self.db.commit()
        return n
    def overdue(self, today=None):
        return self.all("SELECT * FROM missions WHERE done=0 AND routine_id IS NULL AND date<? ORDER BY date,priority DESC", (_iso(today or date.today()),))

    # ---------- یادآوری‌ها (فقط «چه چیزی و کی»؛ تحویل پیام در notify.py و main.py است) ----------
    def reminders_due(self, now=None):
        """یادآوری‌هایی که همین الان وقتشان است و هنوز نشان داده نشده‌اند؛ شرط‌ها با وضعیت زندهٔ دیتابیس سنجیده می‌شود.
        ۱) کار/روتینی که ساعت دارد: سر ساعت (تا ۳۰ دقیقه دیرتر هم) اگر هنوز انجام نشده.
        ۲) عصر (پیش‌فرض ۱۹): اگر کار مهم (اولویت زیاد) مانده یا بیش از نیمی از کارهای امروز انجام نشده."""
        now = now or datetime.now()
        if self.pref("notify_on") != "1": return []
        today = now.date().isoformat(); out = []
        for m in self.all("SELECT id,title,time FROM missions WHERE date=? AND done=0 AND time!=''", (today,)):
            try: at = datetime.fromisoformat(f"{today}T{m['time']}")
            except ValueError: continue
            if at <= now <= at + timedelta(minutes=30):
                out.append(dict(key=f"t{m['id']}", title="وقتشه ⏰", body=f"الان وقت «{m['title']}» است"))
        hour = min(23, max(0, self.pref_int("notify_hour", 19)))
        at = now.replace(hour=hour, minute=0, second=0, microsecond=0)
        if at <= now <= at + timedelta(hours=2):
            rows = self.all("SELECT title,priority,done FROM missions WHERE date=? AND routine_id IS NULL ORDER BY priority DESC,id", (today,))
            pend = [r for r in rows if not r["done"]]; imp = [r for r in pend if r["priority"] >= 2]
            if pend and (imp or len(pend) * 2 > len(rows)):
                if imp: body = f"حواست باشه هنوز «{imp[0]['title']}» رو انجام ندادی" + (f" (و {fa(len(imp) - 1)} کار مهم دیگر)" if len(imp) > 1 else "")
                else: body = f"{fa(len(pend))} از {fa(len(rows))} کار امروز هنوز مانده؛ مثلاً «{pend[0]['title']}»"
                out.append(dict(key=f"e{today}", title="حواست به کارهای امروز باشه", body=body))
        return [r for r in out if not self.one("SELECT 1 FROM settings WHERE key=?", (f"sent|{today}|{r['key']}",))]
    def mark_reminded(self, key, now=None):
        today = (now or datetime.now()).date().isoformat()
        self.setpref(f"sent|{today}|{key}", "1")
        self.run("DELETE FROM settings WHERE key LIKE 'sent|%' AND substr(key,6,10)<?", (today,))

    # ---------- گزارش هفتگی و سرعت تا آزمون ----------
    def weekly_report(self, end=None):
        """۷ روز منتهی به end در برابر ۷ روز قبل از آن، با حداکثر ۳ نکتهٔ خودکار."""
        import jalali as _J
        end = date.fromisoformat(_iso(end or date.today())); first = end - timedelta(days=6)
        cur, prev = self.week_series(end, 7), self.week_series(end - timedelta(days=7), 7)
        def agg(ws): return dict(minutes=sum(w["minutes"] for w in ws), done=sum(w["done"] for w in ws), xp=sum(w["xp"] for w in ws),
                                 days=sum(1 for w in ws if w["done"] or w["minutes"]))
        c, p = agg(cur), agg(prev)
        best = max(cur, key=lambda w: (w["minutes"], w["done"])) if (c["minutes"] or c["done"]) else None
        sub = self.one("""SELECT subject, SUM(CASE WHEN spent_seconds>0 THEN spent_seconds ELSE minutes*60 END) s FROM missions
                          WHERE done=1 AND subject!='' AND routine_id IS NULL AND date(completed_at) BETWEEN ? AND ? GROUP BY subject ORDER BY s DESC LIMIT 1""",
                       (first.isoformat(), end.isoformat()))
        missed = self.one("SELECT COUNT(*) n FROM missions WHERE routine_id IS NOT NULL AND done=0 AND date BETWEEN ? AND ? AND date<?",
                          (first.isoformat(), end.isoformat(), end.isoformat()))["n"]
        tips = []
        if not c["days"]: tips.append("این هفته هنوز فعالیتی ثبت نشده؛ با یک کار کوچک شروع کن.")
        else:
            if p["minutes"] and c["minutes"] >= p["minutes"] * 1.2: tips.append(f"مطالعه‌ات {fa(round((c['minutes'] / p['minutes'] - 1) * 100))}٪ بیشتر از هفتهٔ قبل بود؛ آفرین.")
            elif p["minutes"] and c["minutes"] <= p["minutes"] * .8: tips.append(f"مطالعه‌ات {fa(round((1 - c['minutes'] / p['minutes']) * 100))}٪ کمتر از هفتهٔ قبل بود؛ یک بلوک تمرکز کوتاه برای امروز بگذار.")
            if best and best["minutes"]: tips.append(f"پرکارترین روزت {_J.WEEKDAYS[date.fromisoformat(best['date']).weekday()]} بود.")
            if sub: tips.append(f"بیشترین وقت را به «{sub['subject']}» دادی.")
        if missed: tips.append(f"{fa(missed)} روتین این هفته از دست رفت؛ برای فردا یکی‌شان را اول صبح بگذار.")
        return dict(cur=c, prev=p, best=best, subject=sub["subject"] if sub else "", missed=missed, tips=tips[:3])

    def exam_pace(self, today=None):
        """برای رسیدن به تسلط همهٔ مباحث تا روز آزمون، هفته‌ای چند مبحث لازم است. بدون آزمون آینده یا مبحث باقی‌مانده: None."""
        exam = self.pref("exam_date")
        if not exam: return None
        try: d = (date.fromisoformat(exam) - (today or date.today())).days
        except ValueError: return None
        tp = self.one("SELECT COUNT(*) n, COALESCE(SUM(status=3),0) m FROM topics"); left = tp["n"] - tp["m"]
        if d <= 0 or tp["n"] == 0 or left <= 0: return None
        return dict(days=d, left=left, per_week=-(-left // max(d // 7, 1)))

    def day_load(self, start, n=7):
        """برای هر روز: (تعداد کل، تعداد انجام‌شده) — برای نوار هفته."""
        start = date.fromisoformat(_iso(start)); out = {}
        rows = self.all("SELECT date,COUNT(*) t,SUM(done) d FROM missions WHERE routine_id IS NULL AND date BETWEEN ? AND ? GROUP BY date",
                        (start.isoformat(), (start + timedelta(days=n - 1)).isoformat()))
        by = {r["date"]: (r["t"], r["d"] or 0) for r in rows}
        for i in range(n):
            k = (start + timedelta(days=i)).isoformat(); out[k] = by.get(k, (0, 0))
        return out

    def save_mission(self, title, subject, minutes, priority, day, mid=None, repeat="", topic_id=None, kind="task", time=""):
        """kind: task (کار؛ ساعت و مدت اختیاری) یا chore (ریزه‌کار؛ بدون ساعت و مدت)."""
        if kind == "chore": minutes, time = 0, ""
        xp = xp_for(kind, minutes, priority); day = _iso(day)
        if mid:
            old = self.one("SELECT done,xp FROM missions WHERE id=?", (mid,))
            if old and old["done"]: xp = old["xp"]          # امتیازِ کارِ انجام‌شده در دفتر XP ثبت شده؛ ویرایش نباید عددِ نمایشی را از آن جدا کند
            self.run("UPDATE missions SET title=?,subject=?,minutes=?,priority=?,xp=?,date=?,repeat=?,kind=?,time=? WHERE id=?",
                     (title, subject, minutes, priority, xp, day, repeat, kind, time, mid)); return mid
        return self.run("INSERT INTO missions(title,subject,minutes,priority,xp,date,repeat,topic_id,kind,time) VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (title, subject, minutes, priority, xp, day, repeat, topic_id, kind, time))

    def toggle_mission(self, mid):
        """True اگر تازه تکمیل شد. دفتر XP یکتاست، پس بازگردانی و تکمیل دوباره امتیاز تکراری نمی‌دهد.
        مأموریت تکرارشونده هنگام تکمیل، نمونهٔ بعدی را می‌سازد (بدون تکرار ساختن)."""
        r = self.one("SELECT * FROM missions WHERE id=?", (mid,))
        if not r: return False
        if self.is_locked_routine(r): return False  # روتینِ روزهای گذشته تاریخچه است: نه از دست‌رفته‌اش تیک می‌خورد، نه انجام‌شده‌اش برگردانده می‌شود
        now = datetime.now().isoformat(timespec='seconds')
        if not r['done']:
            with self.db:
                self.db.execute("UPDATE missions SET done=1,completed_at=? WHERE id=?", (now, mid))
                self.db.execute("INSERT OR IGNORE INTO xp_ledger(mission_id,xp,at) VALUES(?,?,?)", (mid, r['xp'], now))
            if r['repeat']: self._spawn_next(r)
            return True
        self.run("UPDATE missions SET done=0,completed_at=NULL WHERE id=?", (mid,)); return False

    def _spawn_next(self, r):
        step = {"daily": 1, "weekly": 7}.get(r['repeat'])
        if not step: return
        nxt = (date.fromisoformat(r['date']) + timedelta(days=step)).isoformat()
        if not self.one("SELECT 1 FROM missions WHERE title=? AND date=? AND repeat=?", (r['title'], nxt, r['repeat'])):
            self.run("INSERT INTO missions(title,subject,minutes,priority,xp,date,repeat,topic_id,kind,time) VALUES(?,?,?,?,?,?,?,?,?,?)",
                     (r['title'], r['subject'], r['minutes'], r['priority'], r['xp'], nxt, r['repeat'], r['topic_id'], r['kind'], r['time']))

    def move_tomorrow(self, mid):
        """به «فردا» می‌برد؛ کارِ عقب‌افتاده یا امروز → فردای واقعی، و کارِ روزهای آینده → یک روز بعد از همان روز (نه جلو کشیدن به فردا)."""
        r = self.one("SELECT date FROM missions WHERE id=? AND routine_id IS NULL", (mid,))
        if not r: return
        nd = max(date.fromisoformat(r["date"]), date.today()) + timedelta(days=1)
        self.run("UPDATE missions SET date=? WHERE id=?", (nd.isoformat(), mid))
    def move_overdue_to_today(self):
        self.run("UPDATE missions SET date=? WHERE done=0 AND routine_id IS NULL AND date<?", (date.today().isoformat(),) * 2)
    def delete_mission(self, mid): self.run("DELETE FROM missions WHERE id=?", (mid,))

    # ---------- روتین‌ها (کارهای همیشگی؛ هر روز خودکار ساخته و صبح روز بعد ریست می‌شوند) ----------
    def seed_prayers(self):
        """نمازهای پنجگانه یک‌بار به‌صورت روتین روزانه اضافه می‌شوند؛ اگر کاربر حذفشان کرد، دوباره برنمی‌گردند."""
        if self.pref("prayers_seeded") == "1": return
        today = date.today().isoformat()
        for i, (key, name, _) in enumerate(PRAYERS):
            if not self.one("SELECT 1 FROM routines WHERE key=?", (key,)):
                self.db.execute("INSERT INTO routines(key,title,kind,minutes,time,days,xp,active,sort,created) VALUES(?,?,?,?,?,?,?,1,?,?)",
                                (key, name, "chore", 0, "", ALL_DAYS, CHORE_XP, i, today))
        self.db.commit(); self.setpref("prayers_seeded", "1")

    def routines(self):
        return self.all("SELECT * FROM routines ORDER BY sort,id")
    @staticmethod
    def routine_days(r):
        return {int(x) for x in (r["days"] or ALL_DAYS).split(",") if x.strip().isdigit()}
    def save_routine(self, title, kind, minutes, time, days, rid=None):
        days = sorted({int(d) for d in days}) or WEEK_ORDER
        if kind == "chore": minutes, time = 0, ""
        xp, ds = xp_for(kind, minutes, 1), ",".join(map(str, days))
        if rid:
            self.run("UPDATE routines SET title=?,kind=?,minutes=?,time=?,days=?,xp=? WHERE id=?", (title, kind, minutes, time, ds, xp, rid))
        else:
            n = self.one("SELECT COALESCE(MAX(sort),-1)+1 n FROM routines")["n"]
            rid = self.run("INSERT INTO routines(key,title,kind,minutes,time,days,xp,active,sort,created) VALUES('',?,?,?,?,?,?,1,?,?)",
                           (title, kind, minutes, time, ds, xp, n, date.today().isoformat()))
        self._sync_routine(rid); return rid
    def set_routine_active(self, rid, active):
        self.run("UPDATE routines SET active=? WHERE id=?", (1 if active else 0, rid)); self._sync_routine(rid)
    def delete_routine(self, rid):
        """روتین و نمونه‌های انجام‌نشدهٔ امروز و آینده‌اش حذف می‌شوند؛ تاریخچهٔ انجام‌شده‌ها می‌ماند."""
        self.db.execute("DELETE FROM missions WHERE routine_id=? AND done=0 AND date>=?", (rid, date.today().isoformat()))
        self.db.execute("DELETE FROM routines WHERE id=?", (rid,)); self.db.commit()
    def _sync_routine(self, rid):
        """تغییر روتین روی نمونه‌های انجام‌نشدهٔ امروز و آینده اعمال می‌شود."""
        r = self.one("SELECT * FROM routines WHERE id=?", (rid,))
        if not r: return
        days = self.routine_days(r)
        for m in self.all("SELECT id,date FROM missions WHERE routine_id=? AND done=0 AND date>=?", (rid, date.today().isoformat())):
            if not r["active"] or date.fromisoformat(m["date"]).weekday() not in days:
                self.db.execute("DELETE FROM missions WHERE id=?", (m["id"],))
            else:
                self.db.execute("UPDATE missions SET title=?,minutes=?,time=?,kind=?,xp=? WHERE id=?", (r["title"], r["minutes"], r["time"], r["kind"], r["xp"], m["id"]))
        self.db.commit()
    def ensure_day(self, day):
        """نمونهٔ روتین‌های فعالِ آن روز را می‌سازد (فقط از امروز به بعد؛ روز گذشته هرگز دستکاری نمی‌شود)."""
        d = date.fromisoformat(_iso(day))
        if d < date.today(): return
        for r in self.all("SELECT * FROM routines WHERE active=1 AND created<=?", (d.isoformat(),)):
            if d.weekday() not in self.routine_days(r): continue
            self.db.execute("INSERT OR IGNORE INTO missions(title,subject,minutes,priority,xp,date,kind,time,routine_id) VALUES(?,?,?,?,?,?,?,?,?)",
                            (r["title"], "", r["minutes"], 1, r["xp"], d.isoformat(), r["kind"], r["time"], r["id"]))
        self.db.commit()
    def ensure_range(self, start, n=7):
        start = date.fromisoformat(_iso(start))
        for i in range(n): self.ensure_day(start + timedelta(days=i))

    # ---------- برنامهٔ هفتگی ----------
    def week_plan(self, start):
        """۷ روز از start: کارهای عادی، خلاصهٔ روتین و نمازها."""
        start = date.fromisoformat(_iso(start)); self.ensure_range(start, 7); out = []
        for i in range(7):
            d = start + timedelta(days=i); rows = self.missions_on(d)
            tasks = [r for r in rows if r["routine_id"] is None]; rt = [r for r in rows if r["routine_id"] is not None]
            pr = [r for r in rt if (r["rkey"] or "").startswith("prayer")]; other = [r for r in rt if r not in pr]
            out.append(dict(date=d, tasks=tasks, routine=other, prayers=pr,
                            done=sum(1 for r in tasks if r["done"]), total=len(tasks),
                            routine_done=sum(1 for r in other if r["done"]), prayer_done=sum(1 for r in pr if r["done"])))
        return out
    def copy_week(self, src_start, dst_start):
        """کارهای عادی (غیرروتین) یک هفته را به‌صورت انجام‌نشده به هفتهٔ دیگر کپی می‌کند؛ تعداد کپی‌شده را برمی‌گرداند."""
        src, dst = date.fromisoformat(_iso(src_start)), date.fromisoformat(_iso(dst_start)); n = 0
        for r in self.all("SELECT * FROM missions WHERE routine_id IS NULL AND date BETWEEN ? AND ? ORDER BY id", (src.isoformat(), (src + timedelta(days=6)).isoformat())):
            nd = (dst + (date.fromisoformat(r["date"]) - src)).isoformat()
            if self.one("SELECT 1 FROM missions WHERE title=? AND date=? AND kind=?", (r["title"], nd, r["kind"])): continue
            self.run("INSERT INTO missions(title,subject,minutes,priority,xp,date,topic_id,kind,time) VALUES(?,?,?,?,?,?,?,?,?)",
                     (r["title"], r["subject"], r["minutes"], r["priority"], r["xp"], nd, r["topic_id"], r["kind"], r["time"])); n += 1
        return n

    # ---------- تمرکز (پومودورو) ----------
    def add_focus(self, mission_id, seconds):
        seconds = int(seconds)
        if seconds <= 0: return
        with self.db:
            self.db.execute("INSERT INTO focus_sessions(mission_id,seconds,at) VALUES(?,?,?)",
                            (mission_id, seconds, datetime.now().isoformat(timespec='seconds')))
            if mission_id: self.db.execute("UPDATE missions SET spent_seconds=spent_seconds+? WHERE id=?", (seconds, mission_id))
    def focus_seconds(self, day=None):
        if day: return self.one("SELECT COALESCE(SUM(seconds),0) n FROM focus_sessions WHERE date(at)=?", (_iso(day),))["n"]
        return self.one("SELECT COALESCE(SUM(seconds),0) n FROM focus_sessions")["n"]

    # ---------- مرور، تسلط و لایتنر ----------
    def add_log(self, topic_id, kind, total, correct, seconds, day, note='', wrong=None, blank=None):
        day = _iso(day)
        self.run("INSERT INTO quiz_logs(topic_id,kind,total,correct,seconds,date,note,wrong,blank) VALUES(?,?,?,?,?,?,?,?,?)", (topic_id, kind, total, correct, seconds, day, note, wrong, blank))
        t = self.one("SELECT status,box FROM topics WHERE id=?", (topic_id,))
        status, box = t['status'], (t['box'] or 0)
        acc = correct / total if total else 0
        n_logs = self.one("SELECT COUNT(*) n FROM quiz_logs WHERE topic_id=?", (topic_id,))["n"]
        # لایتنر: اولین ثبت همیشه به جعبهٔ اول (۱ روز بعد)؛ بعد از آن بلد بودن (≥۸۰٪) → جعبهٔ بعدی،
        # در غیر این صورت برگشت به جعبهٔ اول
        if n_logs <= 1 or acc < .8: box = 0
        else: box = min(box + 1, len(BOX_DAYS) - 1)
        nxt = (date.fromisoformat(day) + timedelta(days=BOX_DAYS[box])).isoformat()
        logs = self.all("SELECT * FROM quiz_logs WHERE topic_id=? ORDER BY date,id", (topic_id,))
        if status == 0: status = 1
        if acc < .6 and status == 3: status = 2                    # افت عملکرد → نیازمند مرور
        if len(logs) >= 2:
            a, b = logs[-1], logs[-2]
            if a['date'] != b['date'] and a['total'] >= 10 and b['total'] >= 10 and a['correct'] / a['total'] >= .8 and b['correct'] / b['total'] >= .8:
                status = 3
        self.run("UPDATE topics SET status=?,box=?,next_review=? WHERE id=?", (status, box, nxt, topic_id))

    def set_topic_status(self, topic_id, status):
        self.run("UPDATE topics SET status=? WHERE id=?", (status, topic_id))

    def due_topics(self, today=None):
        """مباحثی که زمان مرورشان رسیده؛ ضعیف‌ترها اول."""
        return self.all("""
            SELECT t.*, s.name subject,
                   (SELECT 1.0*SUM(correct)/SUM(total) FROM quiz_logs q WHERE q.topic_id=t.id) acc
            FROM topics t JOIN subjects s ON s.id=t.subject_id
            WHERE t.status>0 AND (t.next_review IS NULL OR t.next_review<=?)
            ORDER BY COALESCE(acc,0), t.next_review""", (_iso(today or date.today()),))

    def subject_summary(self):
        return self.all("""
            SELECT s.id, s.name, COUNT(t.id) topics, COALESCE(SUM(t.status=3),0) mastered,
                   (SELECT 1.0*SUM(q.correct)/SUM(q.total) FROM quiz_logs q JOIN topics tt ON tt.id=q.topic_id WHERE tt.subject_id=s.id) acc
            FROM subjects s LEFT JOIN topics t ON t.subject_id=s.id GROUP BY s.id ORDER BY s.name""")

    def suggest_plan(self, day=None, limit=5):
        """برنامهٔ هوشمند: مرور مباحث موعدگذشته که هنوز برایشان مأموریتی نیست."""
        day = _iso(day or date.today()); out = []
        for t in self.due_topics(day):
            title = f"مرور: {t['name']}"
            if self.one("SELECT 1 FROM missions WHERE date=? AND (topic_id=? OR title=?)", (day, t['id'], title)): continue
            weak = t['acc'] is not None and t['acc'] < .6
            out.append(dict(title=title, subject=t['subject'], minutes=40 if weak else 25, priority=2 if weak else 1, topic_id=t['id']))
            if len(out) >= limit: break
        return out
    def apply_plan(self, items, day=None):
        for it in items:
            self.save_mission(it['title'], it['subject'], it['minutes'], it['priority'], day or date.today(), topic_id=it.get('topic_id'))
        return len(items)

    # ---------- استریک و آمار ----------
    def activity_days(self):
        rows = self.all("""SELECT date(completed_at) d FROM missions WHERE done=1 AND routine_id IS NULL AND completed_at IS NOT NULL
                           UNION SELECT date FROM quiz_logs UNION SELECT date(at) FROM focus_sessions UNION SELECT date FROM study_logs""")
        return sorted({r[0] for r in rows if r[0]})

    def streaks(self, today=None, _days=None):
        """(استریک جاری، بهترین استریک). استریک جاری اگر امروز هنوز فعالیتی نیست، از دیروز حساب می‌شود."""
        today = today or date.today()
        days = {date.fromisoformat(d) for d in (self.activity_days() if _days is None else _days)}
        if not days: return 0, 0
        best = run = 0; prev = None
        for d in sorted(days):
            run = run + 1 if prev and (d - prev).days == 1 else 1
            best = max(best, run); prev = d
        cur, d = 0, today if today in days else today - timedelta(days=1)
        while d in days: cur += 1; d -= timedelta(days=1)
        return cur, best

    def stats(self):
        adays = self.activity_days()
        cur, best = self.streaks(_days=adays); xp = self.xp()
        m = self.one("SELECT COUNT(*) n, COALESCE(SUM(done),0) d FROM missions WHERE routine_id IS NULL")
        tp = self.one("SELECT COUNT(*) n, COALESCE(SUM(status=3),0) m FROM topics")
        q = self.one("""SELECT COALESCE(SUM(kind='exam' AND total>=10),0) exams,
                               COALESCE(SUM(kind='exam' AND total>=10 AND correct=total),0) perfect,
                               COALESCE(SUM(kind='review'),0) reviews,
                               COALESCE(SUM(kind='exam' AND total>=10 AND seconds IS NOT NULL),0) timed FROM quiz_logs""")
        return dict(
            xp=xp, level=level_for_xp(xp), streak=cur, best_streak=best,
            missions=m["n"], done=m["d"], topics=tp["n"], mastered=tp["m"],
            exams=q["exams"], perfect=q["perfect"], reviews=q["reviews"], timed=q["timed"],
            days=len(adays), focus_seconds=self.focus_seconds(),
            goal_days=self.one("SELECT COUNT(*) n FROM xp_ledger WHERE mission_id<0 AND xp>0")["n"])

    def week_series(self, end=None, n=7):
        """آمار n روز منتهی به end: XP، تعداد مأموریت انجام‌شده و دقیقهٔ مطالعه (با چند پرس‌وجوی گروهی، نه ۴ پرس‌وجو برای هر روز)."""
        end = date.fromisoformat(_iso(end or date.today()))
        first, last = (end - timedelta(days=n - 1)).isoformat(), end.isoformat()
        xp = {r[0]: r[1] for r in self.all("SELECT date(at) d, SUM(xp) FROM xp_ledger WHERE date(at) BETWEEN ? AND ? GROUP BY d", (first, last))}
        done, sec = {}, {}
        for r in self.all("""SELECT date(completed_at) d, COUNT(*), SUM(CASE WHEN spent_seconds>0 THEN spent_seconds ELSE minutes*60 END)
                             FROM missions WHERE done=1 AND routine_id IS NULL AND date(completed_at) BETWEEN ? AND ? GROUP BY d""", (first, last)):
            done[r[0]] = r[1]; sec[r[0]] = r[2] or 0
        foc = {r[0]: r[1] for r in self.all("SELECT date(at) d, SUM(seconds) FROM focus_sessions WHERE date(at) BETWEEN ? AND ? GROUP BY d", (first, last))}
        stu = {r[0]: r[1] for r in self.all("SELECT date d, SUM(minutes) FROM study_logs WHERE date BETWEEN ? AND ? GROUP BY d", (first, last))}
        out = []
        for i in range(n - 1, -1, -1):
            d = (end - timedelta(days=i)).isoformat()
            out.append(dict(date=d, xp=xp.get(d, 0), done=done.get(d, 0), minutes=max(sec.get(d, 0), foc.get(d, 0)) // 60 + (stu.get(d, 0) or 0)))
        return out

    def heatmap(self, weeks=5, end=None):
        """شدت فعالیت هر روز برای weeks هفتهٔ منتهی به هفتهٔ شامل end (ستون‌ها شنبه‌تا‌جمعه)."""
        from jalali import week_start
        end = date.fromisoformat(_iso(end or date.today())); start = week_start(end) - timedelta(days=7 * (weeks - 1))
        counts = {}
        for r in self.all("""SELECT d, COUNT(*) n FROM (
                 SELECT date(completed_at) d FROM missions WHERE done=1 AND routine_id IS NULL AND completed_at IS NOT NULL
                 UNION ALL SELECT date FROM quiz_logs UNION ALL SELECT date(at) FROM focus_sessions UNION ALL SELECT date FROM study_logs) WHERE d>=? GROUP BY d""", (start.isoformat(),)):
            counts[r['d']] = r['n']
        return [[(start + timedelta(days=7 * w + i)) for i in range(7)] for w in range(weeks)], counts

    def roadmap(self):
        s = self.stats()
        return [("شروع مسیر", "از همین‌جا شروع می‌شود", 1, 1), ("ساخت عادت مطالعه", "فعالیت در ۵ روز مختلف", s['days'], 5),
                ("تسلط بر مباحث", "۳ مبحث با تسلط تأییدشده", s['mastered'], 3), ("تثبیت و مرور", "۵ مرور ثبت‌شده", s['reviews'], 5),
                ("آزمون‌های ترکیبی", "۳ آزمون با حداقل ۱۰ سؤال", s['exams'], 3), ("آزمون‌های زمان‌دار", "۳ آزمون زمان‌دار", s['timed'], 3),
                ("ارزیابی نهایی آمادگی", "۱۰ آزمون ثبت‌شده", s['exams'], 10)]

    # ---------- انگیزه: پاداش هدف، نقاط عطف استریک، پیام مربی ----------
    def done_on(self, day=None):
        """تعداد کار و ریزه‌کارِ انجام‌شدهٔ آن روز (بدون روتین)؛ همان عددی که حلقهٔ هدف روز نشان می‌دهد."""
        return self.one("SELECT COUNT(*) n FROM missions WHERE done=1 AND routine_id IS NULL AND date=?", (_iso(day or date.today()),))["n"]

    def claim_goal_bonus(self, day=None):
        """اگر هدف روزانه زده شده و پاداشش هنوز گرفته نشده، GOAL_BONUS را ثبت و برمی‌گرداند؛ وگرنه ۰.
        شناسهٔ منفیِ یکتا برای هر روز (−YYYYMMDD) در دفتر XP، تکرار و سوءاستفاده (تیک‌زدن و برداشتن) را ناممکن می‌کند."""
        day = _iso(day or date.today())
        if self.done_on(day) < max(1, self.pref_int("daily_goal", 3)): return 0
        key = -int(day.replace("-", ""))
        cur = self.db.execute("INSERT OR IGNORE INTO xp_ledger(mission_id,xp,at) VALUES(?,?,?)", (key, GOAL_BONUS, datetime.now().isoformat(timespec='seconds')))
        self.db.commit()
        return GOAL_BONUS if cur.rowcount else 0

    def streak_milestone(self, today=None):
        """اگر استریک جاری به یکی از نقاط عطف رسیده و هنوز جشن گرفته نشده، همان عدد را برمی‌گرداند (و ثبت می‌کند)."""
        cur, _ = self.streaks(today)
        last = self.pref_int("streak_cel", 0)
        if cur < last: self.setpref("streak_cel", "0"); last = 0          # استریک شکسته بود؛ دوباره قابل جشن است
        if cur in STREAK_MILESTONES and cur > last:
            self.setpref("streak_cel", str(cur)); return cur
        return 0

    def next_milestone(self, streak):
        return next((m for m in STREAK_MILESTONES if m > streak), None)

    def coach(self, today=None, now=None):
        """یک پیام شخصی برای صفحهٔ امروز: (آیکون، رنگ، عنوان، زیرعنوان). مهم‌ترین وضعیت اول؛ در نهایت جملهٔ روز."""
        today = today or date.today(); now = now or datetime.now()
        adays = set(self.activity_days()); streak, _ = self.streaks(today, adays)
        active_today = today.isoformat() in adays
        goal = max(1, self.pref_int("daily_goal", 3)); done = self.done_on(today); xp = self.xp(); lvl = level_for_xp(xp)
        if not adays:
            return ("ROCKET_LAUNCH", "gold", "اولین قدمت را همین امروز بردار", "حتی یک ریزه‌کارِ کوچک هم حساب است. شروع، سخت‌ترین بخش کار است.")
        if streak and not active_today:
            if now.hour >= 18: return ("LOCAL_FIRE_DEPARTMENT", "red", f"استریک {fa(streak)} روزه‌ات در خطر است!", "فقط یک کار کوچک کافی‌ست تا امروز را نگه داری.")
            return ("LOCAL_FIRE_DEPARTMENT", "gold", f"{fa(streak)} روز پیاپی؛ امروز هم ادامه بده", "اولین کار را زودتر انجام بده تا خیالت راحت شود.")
        if done >= goal:
            return ("CELEBRATION", "green", "هدف امروز را زدی! 🎉", f"هر کار اضافه، XP بیشتر است. +{fa(GOAL_BONUS)} XP پاداش هدف را گرفتی.")
        if done > 0 and goal - done <= 2:
            r = goal - done
            return ("TRACK_CHANGES", "gold", f"فقط {fa(r)} کار تا هدف امروز", f"با رسیدن به هدف، +{fa(GOAL_BONUS)} XP پاداش می‌گیری.")
        to_next = xp_threshold(lvl + 1) - xp
        if to_next <= 40: return ("MILITARY_TECH", "blue", f"{fa(to_next)} XP تا سطح {fa(lvl + 1)}", f"به‌زودی «{level_title(lvl + 1)}» می‌شوی. یک کار دیگر!")
        nm = self.next_milestone(streak)
        if streak and nm and nm - streak <= 2: return ("LOCAL_FIRE_DEPARTMENT", "gold", f"{fa(nm - streak)} روز تا استریک {fa(nm)} روزه", "ادامه بده؛ جشنش را از دست نده.")
        if not streak and adays:
            last = date.fromisoformat(max(adays)); gap = (today - last).days
            if gap >= 2: return ("REPLAY", "violet", "خوش برگشتی!", f"{fa(gap)} روز گذشته؛ مهم نیست. امروز دوباره شروع می‌کنیم.")
        exam = self.pref("exam_date")
        if exam:
            try: dl = (date.fromisoformat(exam) - today).days
            except ValueError: dl = -1
            if 0 <= dl <= 45: return ("EVENT", "red" if dl <= 14 else "gold", f"{fa(dl)} روز تا آزمون", self.pref("goal") and f"یادت باشد برای چه شروع کردی: {self.pref('goal')}" or "هر روز حساب است.")
        g = self.pref("goal")
        q = QUOTES[today.toordinal() % len(QUOTES)]
        if g and today.toordinal() % 2 == 0: return ("FLAG", "gold", "یادت باشد برای چه شروع کردی", g)
        return ("FORMAT_QUOTE", "blue", q[0], q[1])

    # ---------- دستاوردها ----------
    def unlocked(self): return {r['id'] for r in self.all("SELECT id FROM achievements")}
    def check_achievements(self):
        """دستاوردهای تازه‌باز‌شده را ثبت می‌کند و فهرست (id,title,desc,emoji) برمی‌گرداند."""
        s, have, new = self.stats(), self.unlocked(), []
        now = datetime.now().isoformat(timespec='seconds')
        for aid, title, desc, emoji, cond in ACHIEVEMENTS:
            if aid not in have and cond(s):
                self.db.execute("INSERT OR IGNORE INTO achievements(id,unlocked_at) VALUES(?,?)", (aid, now))
                new.append((aid, title, desc, emoji))
        self.db.commit(); return new

    # ---------- یادداشت و برچسب ----------
    def all_tags(self): return self.all("SELECT t.*,(SELECT COUNT(*) FROM note_tags n WHERE n.tag_id=t.id) cnt FROM tags t ORDER BY name")
    def note_tag_names(self, note_id):
        return [r['name'] for r in self.all("SELECT t.name FROM tags t JOIN note_tags n ON n.tag_id=t.id WHERE n.note_id=? ORDER BY t.name", (note_id,))]
    def set_note_tags(self, note_id, names):
        names = list(dict.fromkeys(n.strip() for n in names if n.strip()))
        with self.db:
            self.db.execute("DELETE FROM note_tags WHERE note_id=?", (note_id,))
            for n in names:
                self.db.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (n,))
                tid = self.db.execute("SELECT id FROM tags WHERE name=?", (n,)).fetchone()[0]
                self.db.execute("INSERT OR IGNORE INTO note_tags(note_id,tag_id) VALUES(?,?)", (note_id, tid))
            self.db.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM note_tags)")   # برچسب‌های یتیم
    def save_note(self, title, body, tags=(), nid=None, category=None):
        now = datetime.now().isoformat(timespec="seconds")
        cat = category if category in dict(NOTE_CATS) else None
        if nid:
            self.run("UPDATE notes SET title=?,body=?,updated_at=? WHERE id=?", (title, body, now, nid))
            if cat: self.run("UPDATE notes SET category=? WHERE id=?", (cat, nid))
        else: nid = self.run("INSERT INTO notes(title,body,created_at,updated_at,category) VALUES(?,?,?,?,?)", (title, body, now, now, cat or "other"))
        self.set_note_tags(nid, tags); return nid
    def note(self, nid): return self.one("SELECT * FROM notes WHERE id=?", (nid,))
    def set_note_pinned(self, nid, pinned): self.run("UPDATE notes SET pinned=? WHERE id=?", (1 if pinned else 0, nid))
    def delete_note(self, nid): self.run("DELETE FROM notes WHERE id=?", (nid,))
    def note_counts(self):
        """{دسته: تعداد} برای نوار دسته‌بندی."""
        c = {k: 0 for k, _ in NOTE_CATS}
        for r in self.all("SELECT COALESCE(category,'other') c, COUNT(*) n FROM notes GROUP BY c"): c[r["c"] if r["c"] in c else "other"] += r["n"]
        return c
    def search_notes(self, q="", tag=None, limit=None, category=None):
        like = "%" + q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"          # % و _ در جست‌وجو معنای نوشتاری خودشان را دارند، نه «هرچیزی»
        sql = "SELECT * FROM notes n WHERE (title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')"; args = [like, like]
        if category: sql += " AND COALESCE(category,'other')=?"; args.append(category)
        if tag: sql += " AND EXISTS(SELECT 1 FROM note_tags nt JOIN tags t ON t.id=nt.tag_id WHERE nt.note_id=n.id AND t.name=?)"; args.append(tag)
        sql += " ORDER BY pinned DESC,updated_at DESC"
        if limit: sql += " LIMIT ?"; args.append(int(limit))
        return self.all(sql, args)
    def tags_for_notes(self, ids):
        """نام برچسب‌ها برای چند یادداشت با «یک» کوئری (به‌جای یک کوئری برای هر یادداشت): {note_id: [نام‌ها]}."""
        ids = [int(i) for i in ids]; out = {}
        if not ids: return out
        for r in self.all("SELECT n.note_id, t.name FROM note_tags n JOIN tags t ON t.id=n.tag_id WHERE n.note_id IN (%s) ORDER BY t.name" % ",".join("?" * len(ids)), ids):
            out.setdefault(r["note_id"], []).append(r["name"])
        return out

    # ---------- تحصیل: درس‌ها، مباحث، ثبت مطالعه و جلسه‌های تست (۴٫۱) ----------
    def ensure_default_subjects(self):
        """شش درس پیش‌فرض را (اگر نبودند) می‌سازد؛ idempotent و روی داده‌های قبلی اثر نمی‌گذارد."""
        have = {r["name"] for r in self.all("SELECT name FROM subjects")}
        miss = [n for n, _ in DEFAULT_SUBJECTS if n not in have]
        for n in miss: self.db.execute("INSERT OR IGNORE INTO subjects(name) VALUES(?)", (n,))
        if miss: self.db.commit()
        return len(miss)

    def add_subject(self, name):
        name = (name or "").strip()
        if not name: raise ValueError("نام درس خالی است")
        return self.run("INSERT INTO subjects(name) VALUES(?)", (name,))
    def set_total_chapters(self, sid, n): self.run("UPDATE subjects SET total_chapters=? WHERE id=?", (max(0, min(200, int(n))), sid))

    def subject_stats(self, s):
        """آمار یک درس. درصد پیشرفت = میانگین تسلطِ فصل‌ها بر تعداد فصل‌های کتاب؛ فصل‌های دست‌نخورده صفر حساب می‌شوند."""
        sid = s["id"]
        topics = self.all("SELECT * FROM topics WHERE subject_id=?", (sid,))
        logs = self.all("""SELECT l.*, t.chapter, t.name tname FROM study_logs l JOIN topics t ON t.id=l.topic_id
                           WHERE t.subject_id=? ORDER BY l.date DESC, l.id DESC""", (sid,))
        chapters = {}
        for t in topics:
            k = chapter_key(t["chapter"]); k = k if k is not None else "t:" + (t["chapter"] or "").strip()
            chapters.setdefault(k, []).append(t["mastery"] or 0)
        total = s["total_chapters"] or 0
        progress = (sum(sum(v) / len(v) for v in chapters.values()) / max(total, len(chapters))) if chapters else 0
        studied = {l["topic_id"] for l in logs}
        nums = [chapter_key(t["chapter"]) for t in topics if t["id"] in studied and chapter_key(t["chapter"]) is not None]
        last_chapter = str(max(nums)) if nums else ((logs[0]["chapter"] or "").strip() if logs else "")
        q = self.one("""SELECT COUNT(*) n, COALESCE(SUM(q.correct),0) c, COALESCE(SUM(q.total),0) t FROM quiz_logs q JOIN topics t ON t.id=q.topic_id
                        WHERE t.subject_id=?""", (sid,))
        return dict(id=sid, name=s["name"], icon=SUBJECT_ICON.get(s["name"]), total_chapters=total, topics=len(topics), chapters=len(chapters),
                    progress=int(round(min(100, progress))), last_chapter=last_chapter, last_topic=logs[0]["tname"] if logs else "",
                    last_date=logs[0]["date"] if logs else "", minutes=sum(l["minutes"] or 0 for l in logs), studies=len(logs),
                    tests=q["n"], test_total=q["t"], test_correct=q["c"], avg_success=int(round(100 * q["c"] / q["t"])) if q["t"] else None)

    def study_overview(self):
        self.ensure_default_subjects()
        order = {n: i for i, (n, _) in enumerate(DEFAULT_SUBJECTS)}
        subs = sorted(self.all("SELECT * FROM subjects"), key=lambda s: (order.get(s["name"], 99), s["name"]))
        return [self.subject_stats(s) for s in subs]

    def subject_topics(self, sid):
        rows = self.all("""SELECT t.*, (SELECT COUNT(*) FROM study_logs l WHERE l.topic_id=t.id) studies,
                                    (SELECT COALESCE(SUM(minutes),0) FROM study_logs l WHERE l.topic_id=t.id) minutes,
                                    (SELECT MAX(date) FROM study_logs l WHERE l.topic_id=t.id) last_date,
                                    (SELECT COUNT(*) FROM quiz_logs q WHERE q.topic_id=t.id) tests
                           FROM topics t WHERE t.subject_id=?""", (sid,))
        return sorted(rows, key=lambda r: (chapter_key(r["chapter"]) if chapter_key(r["chapter"]) is not None else 9999, r["chapter"] or "", r["name"]))

    def find_topic(self, sid, chapter, name):
        return self.one("SELECT * FROM topics WHERE subject_id=? AND chapter=? AND name=?", (sid, (chapter or "").strip(), (name or "").strip()))
    def save_topic(self, sid, chapter, name, notes="", mistakes="", tid=None):
        """مبحث را می‌سازد/ویرایش می‌کند. بدون tid و با فصل+نام تکراری، همان مبحث قبلی برگردانده می‌شود (تکراری ساخته نمی‌شود)."""
        chapter, name = (chapter or "").strip(), (name or "").strip()
        if not name: raise ValueError("نام مبحث خالی است")
        if tid:
            self.run("UPDATE topics SET subject_id=?,chapter=?,name=?,notes=?,mistakes=? WHERE id=?", (sid, chapter, name, notes, mistakes, tid)); return tid
        ex = self.find_topic(sid, chapter, name)
        if ex:
            if notes or mistakes: self.run("UPDATE topics SET notes=?,mistakes=? WHERE id=?", (notes or ex["notes"], mistakes or ex["mistakes"], ex["id"]))
            return ex["id"]
        return self.run("INSERT INTO topics(subject_id,chapter,name,notes,mistakes) VALUES(?,?,?,?,?)", (sid, chapter, name, notes, mistakes))
    def delete_topic(self, tid):
        for t in ("study_logs", "quiz_logs"): self.db.execute(f"DELETE FROM {t} WHERE topic_id=?", (tid,))
        self.db.execute("DELETE FROM topics WHERE id=?", (tid,)); self.db.commit()

    # --- ثبت مطالعه
    def add_study(self, topic_id, day, minutes, mastery, note=""):
        lid = self.run("INSERT INTO study_logs(topic_id,date,minutes,mastery,note) VALUES(?,?,?,?,?)",
                       (topic_id, _iso(day), max(0, int(minutes or 0)), max(0, min(100, int(mastery or 0))), note or ""))
        self.recalc_study(topic_id); return lid
    def update_study(self, lid, topic_id, day, minutes, mastery, note=""):
        old = self.one("SELECT topic_id FROM study_logs WHERE id=?", (lid,))
        self.run("UPDATE study_logs SET topic_id=?,date=?,minutes=?,mastery=?,note=? WHERE id=?",
                 (topic_id, _iso(day), max(0, int(minutes or 0)), max(0, min(100, int(mastery or 0))), note or "", lid))
        if old: self.recalc_study(old["topic_id"])
        self.recalc_study(topic_id)
    def delete_study(self, lid):
        old = self.one("SELECT topic_id FROM study_logs WHERE id=?", (lid,))
        self.run("DELETE FROM study_logs WHERE id=?", (lid,))
        if old: self.recalc_study(old["topic_id"])
    def study_logs_of(self, topic_id):
        return self.all("SELECT * FROM study_logs WHERE topic_id=? ORDER BY date DESC, id DESC", (topic_id,))
    def recent_study(self, sid, limit=12):
        return self.all("""SELECT l.*, t.chapter, t.name tname FROM study_logs l JOIN topics t ON t.id=l.topic_id
                           WHERE t.subject_id=? ORDER BY l.date DESC, l.id DESC LIMIT ?""", (sid, limit))
    def recalc_study(self, topic_id):
        """تسلط مبحث = تسلط آخرین ثبت مطالعه. مطالعه‌شدن، مبحث را وارد چرخهٔ مرور می‌کند (وضعیت «در حال یادگیری» و مرور ۱ روز بعد)."""
        t = self.one("SELECT * FROM topics WHERE id=?", (topic_id,))
        if not t: return
        last = self.one("SELECT date,mastery FROM study_logs WHERE topic_id=? ORDER BY date DESC, id DESC LIMIT 1", (topic_id,))
        if not last:                                       # آخرین ثبت مطالعه حذف شد: تسلط و درصد پیشرفت درس نباید روی عدد قدیمی بمانند
            if self.one("SELECT COUNT(*) n FROM quiz_logs WHERE topic_id=?", (topic_id,))["n"]: self.run("UPDATE topics SET mastery=0 WHERE id=?", (topic_id,))
            else: self.run("UPDATE topics SET mastery=0,status=CASE WHEN status=1 THEN 0 ELSE status END,next_review=CASE WHEN status=1 THEN NULL ELSE next_review END WHERE id=?", (topic_id,))
            return
        status = t["status"] or 0; nxt = t["next_review"]; ld = last["date"]
        if status == 0: status = 1
        if not nxt: nxt = (date.fromisoformat(ld) + timedelta(days=BOX_DAYS[0])).isoformat()
        elif nxt <= ld: nxt = (date.fromisoformat(ld) + timedelta(days=BOX_DAYS[min(max(t["box"] or 0, 0), len(BOX_DAYS) - 1)])).isoformat()   # مطالعهٔ دوباره‌ی مبحثِ سررسیدشده یعنی مرور شد؛ تا ابد در فهرست «آمادهٔ مرور» نماند
        self.run("UPDATE topics SET mastery=?,status=?,next_review=? WHERE id=?", (last["mastery"], status, nxt, topic_id))

    # --- جلسه‌های تست
    def add_test(self, sid, chapter, topic, kind, total, correct, wrong, blank, day, note=""):
        tid = self.save_topic(sid, chapter, self._test_topic_name(chapter, topic))
        self.add_log(tid, kind, total, correct, None, day, note, wrong, blank); return tid
    @staticmethod
    def _test_topic_name(chapter, topic):
        topic = (topic or "").strip()
        return topic or (f"کل فصل {(chapter or '').strip()}" if (chapter or "").strip() else "مباحث عمومی")
    def update_test(self, qid, sid, chapter, topic, kind, total, correct, wrong, blank, day, note=""):
        old = self.one("SELECT topic_id FROM quiz_logs WHERE id=?", (qid,))
        if not old: return
        tid = self.save_topic(sid, chapter, self._test_topic_name(chapter, topic))
        self.run("UPDATE quiz_logs SET topic_id=?,kind=?,total=?,correct=?,wrong=?,blank=?,date=?,note=? WHERE id=?",
                 (tid, kind, total, correct, wrong, blank, _iso(day), note or "", qid))
        self._replay(old["topic_id"])
        if tid != old["topic_id"]: self._replay(tid)
    def delete_test(self, qid):
        old = self.one("SELECT topic_id FROM quiz_logs WHERE id=?", (qid,))
        self.run("DELETE FROM quiz_logs WHERE id=?", (qid,))
        if old: self._replay(old["topic_id"])
    def _replay(self, topic_id):
        """وضعیت، جعبهٔ لایتنر و مرور بعدیِ مبحث را از روی همهٔ جلسه‌های تستش دوباره می‌سازد (بعد از ویرایش/حذف جلسه)."""
        if not self.one("SELECT 1 FROM topics WHERE id=?", (topic_id,)): return
        logs = self.all("SELECT * FROM quiz_logs WHERE topic_id=? ORDER BY date,id", (topic_id,))
        studied = self.one("SELECT COUNT(*) n FROM study_logs WHERE topic_id=?", (topic_id,))["n"] > 0
        status, box, prev = (1 if studied else 0), 0, None
        for i, l in enumerate(logs):
            acc = l["correct"] / max(1, l["total"])
            box = 0 if (i == 0 or acc < .8) else min(box + 1, len(BOX_DAYS) - 1)
            if status == 0: status = 1
            if acc < .6 and status == 3: status = 2
            if prev and prev["date"] != l["date"] and prev["total"] >= 10 and l["total"] >= 10 and prev["correct"] / prev["total"] >= .8 and acc >= .8: status = 3
            prev = l
        if logs: nxt = (date.fromisoformat(logs[-1]["date"]) + timedelta(days=BOX_DAYS[box])).isoformat()
        else:
            ls = self.one("SELECT date FROM study_logs WHERE topic_id=? ORDER BY date DESC,id DESC LIMIT 1", (topic_id,))
            nxt = (date.fromisoformat(ls["date"]) + timedelta(days=BOX_DAYS[0])).isoformat() if ls else None
        self.run("UPDATE topics SET status=?,box=?,next_review=? WHERE id=?", (status, box, nxt, topic_id))
    def tests_of(self, sid=None, limit=None):
        sql = """SELECT q.*, COALESCE(q.wrong, q.total-q.correct) wrong_n, COALESCE(q.blank,0) blank_n, t.chapter, t.name topic, s.name subject, s.id sid
                 FROM quiz_logs q JOIN topics t ON t.id=q.topic_id JOIN subjects s ON s.id=t.subject_id"""
        args = []
        if sid: sql += " WHERE s.id=?"; args.append(sid)
        sql += " ORDER BY q.date DESC, q.id DESC"
        if limit: sql += " LIMIT ?"; args.append(int(limit))
        return self.all(sql, args)
    def test_summary(self, sid=None, day=None):
        w = " WHERE t.subject_id=?" if sid else ""; a = (sid,) if sid else ()
        r = self.one(f"""SELECT COUNT(*) n, COALESCE(SUM(q.total),0) total, COALESCE(SUM(q.correct),0) correct,
                         COALESCE(SUM(COALESCE(q.wrong, q.total-q.correct)),0) wrong, COALESCE(SUM(COALESCE(q.blank,0)),0) blank
                         FROM quiz_logs q JOIN topics t ON t.id=q.topic_id{w}""", a)
        d = _iso(day or date.today())
        td = self.one(f"""SELECT COALESCE(SUM(q.total),0) n FROM quiz_logs q JOIN topics t ON t.id=q.topic_id WHERE q.date=?{' AND t.subject_id=?' if sid else ''}""", (d,) + a)["n"]
        return dict(sessions=r["n"], total=r["total"], correct=r["correct"], wrong=r["wrong"], blank=r["blank"], today=td,
                    success=int(round(100 * r["correct"] / r["total"])) if r["total"] else None)

    # ---------- اهداف هفتگی ----------
    def week_goals(self, ws): return self.all("SELECT * FROM week_goals WHERE week=? ORDER BY done, id", (_iso(ws),))
    def add_goal(self, ws, title):
        title = (title or "").strip()
        if not title: raise ValueError("عنوان هدف خالی است")
        return self.run("INSERT INTO week_goals(week,title,done,created) VALUES(?,?,0,?)", (_iso(ws), title[:120], datetime.now().isoformat(timespec="seconds")))
    def update_goal(self, gid, title): self.run("UPDATE week_goals SET title=? WHERE id=?", ((title or "").strip()[:120], gid))
    def toggle_goal(self, gid):
        r = self.one("SELECT done FROM week_goals WHERE id=?", (gid,))
        if r: self.run("UPDATE week_goals SET done=? WHERE id=?", (0 if r["done"] else 1, gid))
    def delete_goal(self, gid): self.run("DELETE FROM week_goals WHERE id=?", (gid,))
    def goal_stats(self, ws):
        g = self.week_goals(ws); done = sum(1 for x in g if x["done"])
        return dict(total=len(g), done=done, pct=int(round(100 * done / len(g))) if g else 0)

    # ---------- آمار پیشرفت (روزانه، هفتگی، ماهانه) ----------
    def series(self, kind, end=None):
        """kind: day (۷ روز اخیر) • week (۸ هفتهٔ شنبه‌تاجمعه) • month (۶ ماه جلالی). هر عضو: label, xp, done, minutes, current."""
        import jalali as _J
        end = date.fromisoformat(_iso(end or date.today())); today = date.today()
        if kind == "day":
            return [dict(label=_J.WEEKDAY_SHORT[date.fromisoformat(w["date"]).weekday()], start=w["date"], current=date.fromisoformat(w["date"]) == today,
                         xp=w["xp"], done=w["done"], minutes=w["minutes"]) for w in self.week_series(end, 7)]
        if kind == "week":
            ws = _J.week_start(end); first = ws - timedelta(days=7 * 7)
            days = {w["date"]: w for w in self.week_series(ws + timedelta(days=6), 56)}; out = []
            for i in range(8):
                s0 = first + timedelta(days=7 * i); chunk = [days.get((s0 + timedelta(days=k)).isoformat()) for k in range(7)]; chunk = [c for c in chunk if c]
                out.append(dict(label=fa(_J.to_jalali(s0)[2]), start=s0.isoformat(), current=(s0 == ws), xp=sum(c["xp"] for c in chunk), done=sum(c["done"] for c in chunk), minutes=sum(c["minutes"] for c in chunk)))
            return out
        jy, jm, _ = _J.to_jalali(end); months = []
        for _i in range(6):
            months.append((jy, jm)); jm -= 1
            if jm == 0: jm, jy = 12, jy - 1
        months.reverse(); lo = _J.from_jalali(months[0][0], months[0][1], 1)
        days = self.week_series(end, max(1, (end - lo).days + 1)); out = []
        for (y, m) in months:
            chunk = [w for w in days if _J.to_jalali(date.fromisoformat(w["date"]))[:2] == (y, m)]
            out.append(dict(label=_J.MONTHS[m - 1], start=_J.from_jalali(y, m, 1).isoformat(), current=((y, m) == _J.to_jalali(today)[:2]),
                            xp=sum(c["xp"] for c in chunk), done=sum(c["done"] for c in chunk), minutes=sum(c["minutes"] for c in chunk)))
        return out
    def growth_pct(self):
        """رشد XP این هفته (۷ روز اخیر) نسبت به ۷ روز قبل از آن، به درصد."""
        w = self.weekly_report(); cur, prev = w["cur"]["xp"], w["prev"]["xp"]
        if prev > 0: return int(round((cur / prev - 1) * 100))
        return 100 if cur > 0 else 0

    # ---------- پشتیبان ----------
    def backup_dict(self):
        return {"app": "Get Better", "version": BACKUP_VERSION, "exported_at": datetime.now().isoformat(timespec='seconds'),
                "data": {t: [dict(r) for r in self.all('SELECT * FROM ' + t)] for t in TABLES}}
    def backup(self, path):
        tmp = path + ".tmp"                      # اول فایل موقت، بعد جایگزینی؛ پشتیبان نیمه‌کاره هرگز باقی نمی‌ماند
        with open(tmp, 'w', encoding='utf-8') as f: json.dump(self.backup_dict(), f, ensure_ascii=False, separators=(',', ':'))   # فشرده: سریع‌تر و کم‌حجم‌تر
        os.replace(tmp, path)
    def backup_text(self): return json.dumps(self.backup_dict(), ensure_ascii=False)
    @staticmethod
    def export_filename(): return f"get_better_backup_{date.today().isoformat()}.json"

    # --- پشتیبان خودکار (پوشهٔ backups کنار دیتابیس)
    def backups_dir(self):
        d = os.path.join(os.path.dirname(os.path.abspath(self.path)), "backups"); os.makedirs(d, exist_ok=True); return d
    def has_data(self):
        return any(self.one(q)["n"] for q in ("SELECT COUNT(*) n FROM missions WHERE routine_id IS NULL", "SELECT COUNT(*) n FROM topics",
                                               "SELECT COUNT(*) n FROM notes", "SELECT COUNT(*) n FROM quiz_logs", "SELECT COUNT(*) n FROM day_events"))
    def auto_backup(self, tag="auto", keep=5):
        d = self.backups_dir(); stamp = datetime.now().strftime("%Y%m%d-%H%M%S"); p = os.path.join(d, f"{tag}-{stamp}.json"); n = 1
        while os.path.exists(p): p = os.path.join(d, f"{tag}-{stamp}-{n}.json"); n += 1
        self.backup(p)
        for old in sorted(glob.glob(os.path.join(d, f"{tag}-*.json")), reverse=True)[keep:]:
            try: os.remove(old)
            except OSError: pass
        return p
    def maybe_daily_backup(self):
        """روزی حداکثر یک پشتیبان خودکار (فقط اگر داده‌ای وجود دارد). True اگر ساخته شد."""
        today = date.today().isoformat()
        if self.pref("last_auto_backup") == today or not self.has_data(): return False
        if self.db.execute("PRAGMA quick_check").fetchone()[0] != "ok":       # بررسی کامل سلامت فقط روزی یک بار و در پس‌زمینه؛ پشتیبانِ خراب جای پشتیبان‌های سالم را نمی‌گیرد
            log_error("quick_check ناموفق بود؛ پشتیبان خودکار امروز ساخته نشد"); return False
        self.auto_backup("auto", 5); self.setpref("last_auto_backup", today); return True
    def list_backups(self):
        """[(مسیر، زمان)] جدیدترین اول؛ فقط فایل‌های JSON پوشهٔ backups."""
        files = glob.glob(os.path.join(self.backups_dir(), "*.json"))
        return sorted(((f, os.path.getmtime(f)) for f in files), key=lambda x: x[1], reverse=True)

    def restore(self, path, snapshot=True):
        with open(path, encoding='utf-8') as f: self.restore_text(f.read(), snapshot)
    def restore_text(self, text, snapshot=True):
        """بازیابی اتمیک: اگر چیزی خراب بود، هیچ تغییری اعمال نمی‌شود. ستون‌های ناشناخته نادیده گرفته می‌شوند.
        پیش از جایگزینی، از وضعیت فعلی یک نسخهٔ «pre-restore» گرفته می‌شود تا اشتباه قابل جبران باشد."""
        try: obj = json.loads(text)
        except ValueError: raise ValueError("فایل پشتیبان معتبر نیست")
        if not isinstance(obj, dict): raise ValueError("فایل پشتیبان معتبر نیست")
        data = obj.get('data', obj)
        if not isinstance(data, dict) or not any(t in data for t in TABLES): raise ValueError("فایل پشتیبان معتبر نیست")
        if isinstance(obj.get("version"), int) and obj["version"] > BACKUP_VERSION: raise ValueError("این پشتیبان از نسخهٔ جدیدتر برنامه است؛ برنامه را به‌روز کن")
        if any(not isinstance(data.get(t, []), list) or any(not isinstance(r, dict) for r in data.get(t, [])) for t in TABLES): raise ValueError("فایل پشتیبان معتبر نیست")
        if snapshot and self.has_data():
            try: self.auto_backup("pre-restore", 3)
            except OSError as ex: log_error("ساخت نسخهٔ پیش از بازیابی ناموفق بود", ex)
        with self.db:
            for t in reversed(TABLES):  # اول جدول‌های وابسته پاک شوند
                if t in data: self.db.execute('DELETE FROM ' + t)
            for t in TABLES:
                cols_ok = set(self._columns(t))
                for row in data.get(t, []):
                    cols = [c for c in row if c in cols_ok]
                    if not cols: continue
                    self.db.execute(f"INSERT INTO {t} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [row[c] for c in cols])
        self.seed_prayers()
    def clear_all(self, keep=("theme", "onboarded")):
        if self.has_data():
            try: self.auto_backup("pre-wipe", 2)
            except OSError as ex: log_error("ساخت نسخهٔ پیش از پاک‌سازی ناموفق بود", ex)
        keep_vals = {k: self.pref(k) for k in keep}
        with self.db:
            for t in reversed(TABLES): self.db.execute('DELETE FROM ' + t)
        for k, v in keep_vals.items(): self.setpref(k, v)
        self.seed_prayers()

    def is_fresh(self):
        """True اگر کاربر هنوز هیچ داده‌ای نساخته (برای نمایش معرفی اولیه)."""
        return not self.has_data() and not (self.pref("goal") or self.pref("exam_date"))
