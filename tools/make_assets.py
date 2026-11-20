# -*- coding: utf-8 -*-
"""ساخت آیکون، اسپلش و گرافیک‌های فروشگاه با Pillow (قابل اجرای دوباره):  python tools/make_assets.py
خروجی: assets/icon.png, assets/splash.png, assets/splash_dark.png, assets/favicon.png, store/icon_512.png, store/feature_graphic.png

نشان برنامه: حلقهٔ پیشرفت طلایی (حدود ۷۵٪ پر) با تیک بزرگِ رو‌به‌بالا در مرکز و یک جرقهٔ کوچک روی سر حلقه
= «هر روز کمی بهتر». محتوا داخل ناحیهٔ امن آیکون تطبیقی اندروید (۶۶٪ مرکز) می‌ماند."""
import math, os
from PIL import Image, ImageDraw, ImageFilter, ImageFont, features

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD_A, GOLD_B = (255, 214, 102), (255, 150, 64)
BG_TOP, BG_BOTTOM, INDIGO = (16, 26, 64), (5, 9, 24), (66, 88, 214)
SS = 3                                                    # فوق‌نمونه‌برداری برای لبه‌های نرم

def lerp(a, b, t): return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))

def gradient(size, c1, c2, diagonal=False):
    w, h = size; img = Image.new("RGB", size); px = img.load()
    for y in range(h):
        for x in range(w):
            t = ((x / max(1, w - 1)) + (y / max(1, h - 1))) / 2 if diagonal else y / max(1, h - 1)
            px[x, y] = lerp(c1, c2, t)
    return img

def background(size):
    bg = gradient(size, BG_TOP, BG_BOTTOM).convert("RGBA"); w, h = size
    light = Image.new("RGBA", size, INDIGO + (0,)); a = Image.new("L", size, 0)
    ImageDraw.Draw(a).ellipse([w * .30, -h * .45, w * 1.40, h * .60], fill=120)
    light.putalpha(a.filter(ImageFilter.GaussianBlur(w * .13))); bg.alpha_composite(light)
    return bg

def mark_mask(size, cx, cy, R, sweep=270, stroke_ratio=.20, ss=SS):
    """ماسک نشان: حلقه + تیک + جرقه، همه با سر گرد. R شعاع بیرونی حلقه است."""
    W, H = size[0] * ss, size[1] * ss; ring = Image.new("L", (W, H), 0); d = ImageDraw.Draw(ring)
    cx, cy, R = cx * ss, cy * ss, R * ss; sw = R * stroke_ratio; rm = R - sw / 2          # rm: شعاع میانی خط
    start = 135                                                                           # از پایین‌چپ، ساعت‌گرد، تا بالا‌راست
    d.arc([cx - R, cy - R, cx + R, cy + R], start, start + sweep, fill=255, width=int(sw))
    for ang in (start, start + sweep):                                                    # سر گرد
        x, y = cx + rm * math.cos(math.radians(ang)), cy + rm * math.sin(math.radians(ang)); d.ellipse([x - sw / 2, y - sw / 2, x + sw / 2, y + sw / 2], fill=255)
    chk = Image.new("L", (W, H), 0); c = ImageDraw.Draw(chk); u = R / 300; w = int(sw * 1.02)
    p1, p2, p3 = (cx - 112 * u, cy + 6 * u), (cx - 28 * u, cy + 92 * u), (cx + 138 * u, cy - 96 * u)
    c.line([p1, p2, p3], fill=255, width=w, joint="curve")
    for p in (p1, p3): c.ellipse([p[0] - w / 2, p[1] - w / 2, p[0] + w / 2, p[1] + w / 2], fill=255)
    m = Image.new("L", (W, H), 0); m.paste(255, mask=ring); m.paste(255, mask=chk)
    return m.resize(size, Image.LANCZOS)

def spark_mask(size, cx, cy, r, ss=SS, p=.58):
    W, H = size[0] * ss, size[1] * ss; m = Image.new("L", (W, H), 0); d = ImageDraw.Draw(m); pts = []
    for i in range(720):
        t = 2 * math.pi * i / 720; c, s = math.cos(t), math.sin(t)
        pts.append((cx * ss + r * ss * math.copysign(abs(c) ** (2 / p), c), cy * ss + r * ss * math.copysign(abs(s) ** (2 / p), s)))
    d.polygon(pts, fill=255); return m.resize(size, Image.LANCZOS)

def draw_mark(base, cx, cy, R, glow=True, track=True, color=None):
    size = base.size; mask = mark_mask(size, cx, cy, R)
    if track:                                                                              # ردّ کم‌رنگ بخش ناپر شدهٔ حلقه
        tr = Image.new("L", (size[0] * SS, size[1] * SS), 0); sw = R * SS * .20
        ImageDraw.Draw(tr).arc([(cx - R) * SS, (cy - R) * SS, (cx + R) * SS, (cy + R) * SS], 45, 135, fill=255, width=int(sw))
        tr = tr.resize(size, Image.LANCZOS).point(lambda v: int(v * .16)); lay = Image.new("RGBA", size, (255, 255, 255, 0)); lay.putalpha(tr); base.alpha_composite(lay)
    if glow:
        halo = Image.new("RGBA", size, GOLD_A + (0,)); halo.putalpha(mask.filter(ImageFilter.GaussianBlur(R * .10)).point(lambda v: int(v * .45))); base.alpha_composite(halo)
    fill = (Image.new("RGB", size, color) if color else gradient(size, GOLD_A, GOLD_B, True)).convert("RGBA"); fill.putalpha(mask); base.alpha_composite(fill)
    sx, sy = cx + (R - R * .10) * math.cos(math.radians(45)) + R * .20, cy - R * .78                 # جرقه کنار سر حلقه
    sm = spark_mask(size, sx, sy, R * .17)
    if glow:
        h2 = Image.new("RGBA", size, GOLD_A + (0,)); h2.putalpha(sm.filter(ImageFilter.GaussianBlur(R * .06)).point(lambda v: int(v * .6))); base.alpha_composite(h2)
    sp = (Image.new("RGB", size, color) if color else gradient(size, (255, 240, 190), GOLD_A)).convert("RGBA"); sp.putalpha(sm); base.alpha_composite(sp)

def icon(n=1024):
    img = background((n, n)); draw_mark(img, n * .5, n * .52, n * .295)
    return img.convert("RGB")

def splash(n=512):
    img = Image.new("RGBA", (n, n), (0, 0, 0, 0)); draw_mark(img, n * .5, n * .52, n * .30, glow=False, track=False); return img

def _font(name, size):
    p = os.path.join(ROOT, "assets", "fonts", name)
    kw = {"layout_engine": ImageFont.Layout.RAQM} if features.check("raqm") else {}
    return ImageFont.truetype(p, size, **kw)

def feature_graphic():
    W, H = 1024, 500; img = background((W, H)); draw_mark(img, 790, 258, 168)
    d = ImageDraw.Draw(img)
    try:
        big, mid, small = _font("Vazirmatn-Bold.ttf", 92), _font("Vazirmatn-Bold.ttf", 44), _font("Vazirmatn-Regular.ttf", 28)
        d.text((72, 120), "Get Better", font=big, fill=(238, 241, 251))
        d.text((76, 250), "برنامه‌ریز آمادگی آزمون", font=mid, fill=GOLD_A, direction="rtl", language="fa")
        d.text((76, 320), "مرور هوشمند • تمرکز • پیشرفت", font=small, fill=(168, 180, 222), direction="rtl", language="fa")
    except OSError: pass
    return img.convert("RGB")

if __name__ == "__main__":
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True); os.makedirs(os.path.join(ROOT, "store"), exist_ok=True)
    ic = icon(1024); ic.save(os.path.join(ROOT, "assets", "icon.png"), optimize=True)
    ic.resize((512, 512), Image.LANCZOS).save(os.path.join(ROOT, "store", "icon_512.png"), optimize=True)
    ic.resize((64, 64), Image.LANCZOS).save(os.path.join(ROOT, "assets", "favicon.png"), optimize=True)
    sp = splash(); sp.save(os.path.join(ROOT, "assets", "splash.png"), optimize=True); sp.save(os.path.join(ROOT, "assets", "splash_dark.png"), optimize=True)
    feature_graphic().save(os.path.join(ROOT, "store", "feature_graphic.png"), optimize=True)
    print("assets ready")
