# -*- coding: utf-8 -*-
"""ساخت تصویر پیش‌فرض قهرمان صفحهٔ امروز: assets/hero_default.jpg  (python tools/make_hero.py)

صحنه: مرد جوانی از پشت، روی صخره‌ای در ارتفاع نشسته و به طلوع خورشید پشت قله‌ها نگاه می‌کند.
این یک تصویر ترسیمی/سینمایی است که با Pillow و numpy ساخته می‌شود (عکس واقعی نیست). کاربر در برنامه می‌تواند با
عکس خودش جایگزینش کند؛ اگر عکس واقعی دارید، کافی است همین فایل را با یک JPEG هم‌نام عوض کنید."""
import math, os
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageChops

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
W, H = 1200, 1300
SUN_X = .70                             # خورشید سمت راست، مرد سمت چپ؛ متن‌های راست‌به‌چپ صفحه روی مرد نمی‌افتند
S = 2                                   # فوق‌نمونه‌برداری برای لبه‌های نرم
rng = np.random.default_rng(7)

def lerp(a, b, t): return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
def ramp(stops, t):
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1: return lerp(c0, c1, 0 if t1 == t0 else (t - t0) / (t1 - t0))
    return stops[-1][1]

def sky():
    stops = [(0, (6, 10, 28)), (.28, (22, 30, 76)), (.46, (74, 58, 128)), (.58, (190, 98, 108)), (.66, (255, 156, 84)), (.72, (255, 206, 130)), (1, (255, 224, 160))]
    a = np.zeros((H, W, 3), np.float32)
    for y in range(H): a[y, :] = ramp(stops, y / H)
    return a

def glow(a, cx, cy, r, color, power=1.0):
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / r
    m = np.clip(1 - d, 0, 1) ** 2.2 * power
    a[:] = a * (1 - m[..., None]) + np.array(color, np.float32) * m[..., None]; return a

def ridge(base, amp, rough, seed, n=9, peaks=()):
    """خط قلهٔ کوه: جابه‌جایی نقطهٔ میانی + قله‌های دستی. خروجی: y برای هر x."""
    r = np.random.default_rng(seed); pts = np.zeros(2 ** n + 1); step = 2 ** n; scale = amp
    while step > 1:
        h = step // 2
        for i in range(h, len(pts), step): pts[i] = (pts[i - h] + pts[min(i + h, len(pts) - 1)]) / 2 + r.uniform(-scale, scale)
        scale *= rough; step //= 2
    xs = np.linspace(0, 1, len(pts)); y = base - pts
    for px, ph, pw in peaks: y -= ph * np.exp(-((xs - px) / pw) ** 2)
    return np.interp(np.linspace(0, 1, W), xs, y)

def layer(a, y, color, haze, hz_top, hz_h):
    """یک رشته‌کوه را با مه جوی (روشن‌تر نزدیک افق) روی تصویر می‌کشد."""
    yy = np.arange(H, dtype=np.float32)[:, None]; m = (yy >= y[None, :]).astype(np.float32)
    t = np.clip((yy - hz_top) / hz_h, 0, 1)                                        # شیب مه
    col = np.array(color, np.float32)[None, None, :] * (1 - t[..., None] * haze) + np.array((255, 170, 120), np.float32) * (t[..., None] * haze * .55)
    m3 = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.1)); m = np.asarray(m3, np.float32)[..., None] / 255
    a[:] = a * (1 - m) + col * m; return a

def clouds(img):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay); r = np.random.default_rng(3)
    for k in range(34):
        cx, cy = r.uniform(-.1, 1.1) * W, r.uniform(.22, .52) * H; rw, rh = r.uniform(160, 420), r.uniform(10, 26)
        warm = max(0, min(1, (cy / H - .25) / .27)); col = tuple(int(v) for v in lerp((120, 110, 190), (255, 170, 110), warm)) + (int(r.uniform(40, 95)),)
        d.ellipse([cx - rw, cy - rh, cx + rw, cy + rh], fill=col)
    lay = lay.filter(ImageFilter.GaussianBlur(14)); img.alpha_composite(lay)

def rays(img, sx, sy):
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(lay)
    for ang in np.linspace(-1.35, -.2, 9):
        w = .045; p = [(sx, sy), (sx + math.cos(ang - w) * 1800, sy + math.sin(ang - w) * 1800), (sx + math.cos(ang + w) * 1800, sy + math.sin(ang + w) * 1800)]
        d.polygon(p, fill=(255, 200, 130, 22))
    img.alpha_composite(lay.filter(ImageFilter.GaussianBlur(22)))

def to_img(a): return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB").convert("RGBA")

def sc(pts): return [(x * S, y * S) for x, y in pts]

def mask_poly(polys, blur=0):
    m = Image.new("L", (W * S, H * S), 0); d = ImageDraw.Draw(m)
    for p in polys: d.polygon(sc(p), fill=255)
    return m

def capsule(d, p, q, r):
    d.line([(p[0] * S, p[1] * S), (q[0] * S, q[1] * S)], fill=255, width=int(2 * r * S))
    for c in (p, q): d.ellipse([(c[0] - r) * S, (c[1] - r) * S, (c[0] + r) * S, (c[1] + r) * S], fill=255)

def figure_mask(bx, by, k=1.0):
    """سیلوئت مرد نشسته از پشت (پا جمع‌شده). (bx,by) نقطهٔ نشستن روی صخره؛ k مقیاس."""
    m = Image.new("L", (W * S, H * S), 0); d = ImageDraw.Draw(m)
    P = lambda x, y: (bx + x * k, by + y * k)
    d.ellipse([(bx - 160 * k) * S, (by - 62 * k) * S, (bx + 160 * k) * S, (by + 30 * k) * S], fill=255)                  # لگن و پاهای جمع‌شده
    torso = [P(-104, -30), P(-112, -120), P(-122, -200), P(-100, -258), P(-58, -282), P(58, -282), P(100, -258), P(122, -200), P(112, -120), P(104, -30)]
    d.polygon(sc(torso), fill=255)
    capsule(d, P(-112, -236), P(-140, -140), 27 * k); capsule(d, P(-140, -140), P(-126, -62), 23 * k)                      # بازوها روی زانو
    capsule(d, P(112, -236), P(140, -140), 27 * k); capsule(d, P(140, -140), P(126, -62), 23 * k)
    d.ellipse([(bx - 70 * k) * S, (by - 318 * k) * S, (bx + 70 * k) * S, (by - 236 * k) * S], fill=255)                  # کلاه هودی
    capsule(d, P(2, -300), P(2, -262), 30 * k)                                                                            # گردن
    d.ellipse([(bx - 47 * k) * S, (by - 372 * k) * S, (bx + 51 * k) * S, (by - 272 * k) * S], fill=255)                  # سر
    m = m.resize((W, H), Image.LANCZOS)
    return m.filter(ImageFilter.GaussianBlur(5)).point(lambda v: 255 if v > 128 else int(v * 1.9) if v > 70 else 0).filter(ImageFilter.GaussianBlur(1.2))   # نرم‌کردن گوشه‌ها

def rock_polys():
    top = [(-40, 1010), (120, 1000), (260, 1020), (380, 985), (520, 960), (640, 962), (770, 950), (900, 975), (1040, 960), (1260, 990), (1260, 1340), (-40, 1340)]
    return top

def build():
    a = sky(); a = glow(a, SUN_X * W, .655 * H, 520, (255, 178, 96), .85); a = glow(a, SUN_X * W, .655 * H, 190, (255, 238, 190), .95)
    img = to_img(a); clouds(img)
    a = np.asarray(img.convert("RGB"), np.float32).copy()
    L = [  # (قله‌ها، مبنا، دامنه، زبری، رنگ، مه، شروع مه)
        dict(base=.70 * H, amp=40, rough=.55, seed=11, color=(120, 92, 150), haze=.55, peaks=[(.40, 120, .09), (.94, 70, .07)]),
        dict(base=.745 * H, amp=60, rough=.56, seed=23, color=(84, 66, 128), haze=.5, peaks=[(.10, 150, .10), (.52, 170, .12)]),
        dict(base=.80 * H, amp=70, rough=.58, seed=5, color=(52, 48, 104), haze=.42, peaks=[(.28, 110, .12), (.88, 140, .10)]),
        dict(base=.865 * H, amp=60, rough=.6, seed=41, color=(30, 34, 76), haze=.30, peaks=[(.62, 80, .14), (.02, 120, .10)]),
    ]
    for i, l in enumerate(L):
        y = ridge(l["base"], l["amp"], l["rough"], l["seed"], peaks=l["peaks"]); a = layer(a, y, l["color"], l["haze"], l["base"] - 160, 520)
        mist = np.exp(-((np.arange(H, dtype=np.float32)[:, None] - (l["base"] + 40)) / 70) ** 2) * (.22 if i < 3 else .12)
        a = a * (1 - mist[..., None]) + np.array((255, 190, 150), np.float32) * mist[..., None]
    img = to_img(a)
    # صخره
    rm = mask_poly([rock_polys()]).resize((W, H), Image.LANCZOS)
    rock = Image.new("RGBA", (W, H), (0, 0, 0, 0)); g = np.zeros((H, W, 3), np.float32)
    for y in range(H): g[y, :] = lerp((26, 28, 56), (7, 9, 22), max(0, (y - 950) / 380))
    nz = rng.normal(0, 5, (H, W, 1)).astype(np.float32); g += nz
    rock = Image.fromarray(np.clip(g, 0, 255).astype(np.uint8)).convert("RGBA"); rock.putalpha(rm)
    lit = np.clip(1 - np.abs(np.arange(W, dtype=np.float32) - SUN_X * W) / (W * .7), 0, 1)[None, :, None]                      # نور ملایم طلوع روی سطح صخره
    top_lit = np.clip(1 - (np.arange(H, dtype=np.float32) - 960) / 120, 0, 1)[:, None, None]
    ra = np.asarray(rock, np.float32).copy(); ra[..., :3] += lit * top_lit * np.array((46, 30, 24), np.float32); rock = Image.fromarray(np.clip(ra, 0, 255).astype(np.uint8), "RGBA")
    img.alpha_composite(rock)
    # لبهٔ نورانی بالای صخره
    edge = ImageChops.subtract(rm, rm.transform(rm.size, Image.AFFINE, (1, 0, 0, 0, 1, 7)))
    glowc = Image.new("RGBA", (W, H), (255, 176, 96, 0)); glowc.putalpha(edge.filter(ImageFilter.GaussianBlur(2)).point(lambda v: int(v * .75))); img.alpha_composite(glowc)
    # مرد
    bx, by, k = 330, 968, 1.05
    fm = figure_mask(bx, by, k)
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); sh = fm.filter(ImageFilter.GaussianBlur(26)).point(lambda v: int(v * .45)); shadow.putalpha(sh); img.alpha_composite(shadow)
    body = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gb = np.zeros((H, W, 3), np.float32)
    for y in range(H): gb[y, :] = lerp((38, 44, 78), (12, 15, 34), min(1, max(0, (y - 560) / 440)))
    body = Image.fromarray(np.clip(gb, 0, 255).astype(np.uint8)).convert("RGBA"); body.putalpha(fm); img.alpha_composite(body)
    # نور لبه از طلوع (چپ و بالا)
    sh_x = ImageChops.offset(fm, -7, 4); rim = ImageChops.subtract(fm, sh_x)
    rimc = Image.new("RGBA", (W, H), (255, 190, 120, 0)); rimc.putalpha(rim.filter(ImageFilter.GaussianBlur(1.6)).point(lambda v: min(255, int(v * 2.4)))); img.alpha_composite(rimc)
    soft = Image.new("RGBA", (W, H), (255, 160, 90, 0)); soft.putalpha(rim.filter(ImageFilter.GaussianBlur(9)).point(lambda v: min(255, int(v * 1.2)))); img.alpha_composite(soft)
    # بلوم و درجه‌بندی رنگ
    rgb = img.convert("RGB"); br = rgb.point(lambda v: max(0, v - 190) * 3).filter(ImageFilter.GaussianBlur(40)); rgb = ImageChops.screen(rgb, br.point(lambda v: int(v * .55)))
    arr = np.asarray(rgb, np.float32)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32); v = 1 - .55 * (((xx - W * .5) / (W * .75)) ** 2 + ((yy - H * .5) / (H * .8)) ** 2); arr *= np.clip(v, .35, 1)[..., None]       # وینیت
    lum = arr.mean(axis=2, keepdims=True) / 255; arr += (1 - lum) * np.array((-2, 4, 14), np.float32) * .6                                                                               # سایه‌های نیلی
    arr += rng.normal(0, 3.2, (H, W, 1)).astype(np.float32)                                                                                                                          # دانهٔ فیلم
    # محو شدن پایین به رنگ پس‌زمینهٔ برنامه (#080D20) برای پیوند نرم با کارت‌ها
    t = np.clip((np.arange(H, dtype=np.float32) - H * .80) / (H * .20), 0, 1)[:, None, None] ** 1.5
    arr = arr * (1 - t) + np.array((8, 13, 32), np.float32) * t
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")

if __name__ == "__main__":
    out = os.path.join(ROOT, "assets", "hero_default.jpg"); build().save(out, quality=84, optimize=True, progressive=True)
    print(out, os.path.getsize(out) // 1024, "KB")
