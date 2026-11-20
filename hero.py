# -*- coding: utf-8 -*-
"""تصویر قهرمان صفحهٔ امروز: پیش‌فرض سینمایی (assets/hero_default.jpg) یا عکس انتخابی کاربر.

عکس انتخابی با Pillow (اگر در برنامه باشد) کوچک و JPEG می‌شود و در پوشهٔ داده‌ی برنامه (کنار دیتابیس) می‌ماند؛ پس با بستن و باز کردن
برنامه، و حتی اگر فایل اصلیِ گالری پاک شود، باقی است. نام فایل و موقعیت برش در تنظیمات داخلی (prefs) ذخیره می‌شود.
اگر فایل گم یا خراب باشد، بی‌صدا به تصویر پیش‌فرض برمی‌گردد. هیچ شبکه‌ای در کار نیست."""
import base64, os, time
from store import data_dir, log_error

DEFAULT_SRC = "hero_default.jpg"               # داخل assets/
PREFIX = "hero_"
EXTS = (".jpg", ".jpeg", ".png", ".webp")
MAX_IN = 40 * 1024 * 1024                      # بزرگ‌تر از این اصلاً خوانده نمی‌شود
MAX_RAW = 5 * 1024 * 1024                      # بدون Pillow نمی‌شود کوچکش کرد؛ فقط تا این اندازه
MAX_SIDE = 1400
_cache = {}

class HeroError(ValueError):
    """پیام فارسی مناسب نمایش به کاربر."""

def current(store):
    """مسیر کامل عکس انتخابی کاربر؛ None اگر ندارد یا فایلش گم شده."""
    name = (store.pref("hero_file") or "").strip()
    if not name or os.path.basename(name) != name: return None
    p = os.path.join(data_dir(), name)
    return p if os.path.isfile(p) else None

def position(store):
    try: return min(1.0, max(0.0, float(store.pref("hero_pos") or .5)))
    except (TypeError, ValueError): return .5

def import_image(src_path):
    """عکس انتخاب‌شده را در پوشهٔ داده کپی (و در صورت امکان کوچک) می‌کند و نام فایل جدید را برمی‌گرداند."""
    if not src_path or not os.path.isfile(src_path): raise HeroError("فایل تصویر پیدا نشد")
    if not src_path.lower().endswith(EXTS): raise HeroError("فقط تصویر JPG، PNG یا WEBP پشتیبانی می‌شود")
    size = os.path.getsize(src_path)
    if size == 0 or size > MAX_IN: raise HeroError("اندازهٔ تصویر مناسب نیست")
    name = f"{PREFIX}{int(time.time() * 1000)}.jpg"; out = os.path.join(data_dir(), name)
    try:
        from PIL import Image, ImageOps
    except ImportError:
        if size > MAX_RAW: raise HeroError("تصویر خیلی بزرگ است؛ تصویر کوچک‌تر از ۵ مگابایت انتخاب کن")
        with open(src_path, "rb") as f, open(out, "wb") as g: g.write(f.read())
        return name
    try:
        with Image.open(src_path) as im:
            im = ImageOps.exif_transpose(im).convert("RGB"); im.thumbnail((MAX_SIDE, MAX_SIDE)); im.save(out, "JPEG", quality=86, optimize=True)
    except Exception as ex:
        log_error("hero import", ex)
        if os.path.exists(out): os.remove(out)
        raise HeroError("این فایل تصویر معتبری نیست")
    return name

def b64(path):
    """محتوای تصویر برای ft.Image(src_base64=...)؛ تا وقتی فایل عوض نشده از حافظه می‌آید."""
    st = os.stat(path); key = (path, st.st_mtime_ns, st.st_size)
    if _cache.get("key") != key:
        with open(path, "rb") as f: _cache.update(key=key, data=base64.b64encode(f.read()).decode("ascii"))
    return _cache["data"]

def prune(keep=None):
    """فایل‌های hero_* قدیمی یا نیمه‌کاره را پاک می‌کند (به‌جز keep)."""
    try:
        for n in os.listdir(data_dir()):
            if n.startswith(PREFIX) and n != keep and n.lower().endswith(EXTS):
                try: os.remove(os.path.join(data_dir(), n))
                except OSError: pass
    except OSError: pass
