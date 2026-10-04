#!/usr/bin/env python3
"""竖版封面 1080×1440（3:4）。用法: make_cover.py <ep_dir>   读 <ep>/cover.json → <ep>/cover_<name>.png
cover.json: {"name": 文件名后缀, "bg": "img/x.jpg", "series": "顶部系列标签", "title1": 主标题, "title2": 副标题, "latin": 外文名（可空）,
             "hook1": 钩子第一行, "hook2": 钩子第二行（金色）, "place": 地点小字（可空）, "bg_x"/"bg_y": 背景取景 0–1, "bg_scale": 1.06, "align": "center"|"left"}
背景用一张竖幅原图整张铺满；文字集中在 y≈350–1090——很多信息流只显示封面中间的 4:3 横条，上下两端会被裁掉或压上平台角标。
出图后先按 (0,315,1080,1125) 裁一张模拟信息流，确认标题和钩子都在。"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
import numpy as np, pathlib
Image.MAX_IMAGE_PIXELS = None
import sys, json
EP = pathlib.Path(sys.argv[1]).resolve()
C = json.load(open(EP/"cover.json"))
HERE = EP
W, H = 1080, 1440
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import fonts as _F
SONG, PFB, PFL = _F.SERIF, _F.BOLD, _F.LIGHT
f = lambda p, s, i=0: ImageFont.truetype(p, s)

# ── 背景：原生竖幅照片，整张铺满 ──
bg = ImageOps.exif_transpose(Image.open(EP/C["bg"])).convert("RGB")
s = max(W/bg.width, H/bg.height) * C.get("bg_scale", 1.06)
if C.get("fit") == "contain":        # 横图居中 + 上下虚化填充。不推荐：虚化边带在信息流里很难看，优先换一张竖幅原图
    s2 = min(W/bg.width, H/bg.height) * C.get("bg_scale", 1.0)
    fg = bg.resize((round(bg.width*s2), round(bg.height*s2)), Image.LANCZOS)
    blur = bg.resize((round(bg.width*s), round(bg.height*s)), Image.LANCZOS).crop((0, 0, W, H)).filter(ImageFilter.GaussianBlur(40))
    blur = ImageEnhance.Brightness(blur).enhance(0.55)
    blur.paste(fg, (int((W-fg.width)*C.get("fg_x", 0.5)), int((H-fg.height)*C.get("fg_y", 0.5)))); bg = blur; s = 1.0
    C["bg_x"], C["bg_y"] = 0, 0
bg = bg.resize((round(bg.width*s), round(bg.height*s)), Image.LANCZOS)
x0 = int((bg.width - W)*C.get("bg_x", 0.5)); y0 = int((bg.height - H)*C.get("bg_y", 0.3))          # 主体放在画面中下部，给标题留出上半部
bg = bg.crop((x0, y0, x0+W, y0+H))
bg = ImageEnhance.Color(bg).enhance(1.12)
bg = ImageEnhance.Contrast(bg).enhance(1.06)
# 暖色调 + 顶部压暗（给标题留底）+ 底部压暗（给钩子文案）
a = np.asarray(bg).astype(np.float32)
a = a * np.array([1.04, 1.0, 0.92])
yy = np.linspace(0, 1, H)[:, None, None]
LEFT = C.get("align") == "left"
if LEFT:
    xx = np.linspace(0, 1, W)[None, :, None]
    top = np.clip(1 - xx/0.62, 0, 1)**1.3 * 0.78 * np.ones_like(yy); bot = np.zeros_like(top)
else:
    top = np.clip(1 - np.abs(yy-0.36)/0.20, 0, 1)**1.2 * 0.62
    bot = np.clip(1 - np.abs(yy-0.70)/0.13, 0, 1)**1.1 * 0.70
a = a * (1 - top) * (1 - bot) + np.array([22, 16, 12]) * (top + bot*(1-top))
bg = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))

im = bg.convert("RGBA")
d = ImageDraw.Draw(im)
CREAM, GOLD, INK = (255, 247, 232), (224, 184, 104), (30, 22, 16)

def shadow_text(xy, text, font, fill, blur=10, off=(0, 4), alpha=170, anchor="la", spacing=0):
    lay = Image.new("RGBA", im.size, (0, 0, 0, 0)); dd = ImageDraw.Draw(lay)
    dd.text((xy[0]+off[0], xy[1]+off[1]), text, font=font, fill=(0, 0, 0, alpha), anchor=anchor)
    lay = lay.filter(ImageFilter.GaussianBlur(blur)); im.alpha_composite(lay)
    ImageDraw.Draw(im).text(xy, text, font=font, fill=fill, anchor=anchor)

if LEFT:
    X = C.get("text_x", 80)
    ft = f(PFB, 32); tag = C.get("series", ""); tw = ft.getlength(tag)
    pill = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([X - 26, 378 - 32, X + tw + 26, 378 + 32], 32, fill=(24, 18, 12, 175))
    im.alpha_composite(pill); d = ImageDraw.Draw(im); d.text((X, 378), tag, font=ft, fill=GOLD, anchor="lm")
    shadow_text((X - 6, 500), C["title1"], f(SONG, 160, 0), CREAM, blur=16, off=(0, 8), alpha=200, anchor="lm")
    f2 = f(SONG, 88, 0)
    for k, ln in enumerate(C["title2"].split("\n")): shadow_text((X, 640 + k*100), ln, f2, CREAM, blur=14, off=(0, 6), alpha=200, anchor="lm")
    ny = 640 + 100*len(C["title2"].split("\n")) - 20
    for _ in range(2): shadow_text((X + 2, ny), C.get("latin", ""), f(PFL, 20), (240, 222, 188), blur=4, off=(0, 2), alpha=230, anchor="lm")
    fh = f(PFB, 46)
    for k, ln in enumerate(C["hook1"].split("\n")): shadow_text((X, 900 + k*60), ln, fh, CREAM, blur=8, anchor="lm")
    hy = 900 + 60*len(C["hook1"].split("\n"))
    for k, ln in enumerate(C["hook2"].split("\n")): shadow_text((X, hy + k*60), ln, fh, GOLD, blur=8, anchor="lm")
    py = hy + 60*len(C["hook2"].split("\n")) + 6
    shadow_text((X, py), C.get("place", ""), f(PFL, 30), (232, 216, 190), blur=4, anchor="lm")
else:
    # 多行时整块（含顶部标签）一起上移，保持上下居中
    _n = lambda k: len(C[k].split("\n")) - 1
    sh = -((_n("title1"))*160 + _n("title2")*118 + (_n("hook1") + _n("hook2"))*74)//2
    # ── 顶部：系列标签 ──
    ft = f(PFB, 34)
    tag = C.get("series", "")
    tw = ft.getlength(tag)
    pill = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(pill).rounded_rectangle([W//2 - tw/2 - 34, 378 + sh - 34, W//2 + tw/2 + 34, 378 + sh + 34], 34, fill=(24, 18, 12, 175))
    im.alpha_composite(pill.filter(ImageFilter.GaussianBlur(1)))
    d = ImageDraw.Draw(im)
    d.text((W//2, 378 + sh), tag, font=ft, fill=GOLD, anchor="mm")

    # 居中版支持多行（cover.json 里的 \n）：逐行往下排，整块文字再上下居中。
    def fit(path, size, idx, lines, maxw=W - 90):       # 太宽就缩字号，别出画
        while size > 40 and max(f(path, size, idx).getlength(s) for s in lines) > maxw: size -= 4
        return f(path, size, idx)
    t1 = C["title1"].split("\n"); t2 = C["title2"].split("\n")
    h1 = C["hook1"].split("\n"); h2 = C["hook2"].split("\n")
    LT1, LT2, LH = 160, 118, 74
    extra = (len(t1) - 1)*LT1 + (len(t2) - 1)*LT2 + (len(h1) + len(h2) - 2)*LH
    sh = -extra//2                                          # 多出来的高度上下各分一半，保持整块居中
    # ── 主标题 / 副标题 ──
    f1 = fit(SONG, 150, 0, t1)
    for k, ln in enumerate(t1): shadow_text((W//2, 490 + sh + k*LT1), ln, f1, CREAM, blur=16, off=(0, 8), alpha=200, anchor="mm")
    y = 640 + sh + (len(t1) - 1)*LT1
    f2 = fit(SONG, 112, 0, t2)
    for k, ln in enumerate(t2): shadow_text((W//2, y + k*LT2), ln, f2, CREAM, blur=14, off=(0, 6), alpha=200, anchor="mm")
    y += (len(t2) - 1)*LT2
    fe = f(PFL, 21)
    for _ in range(2): shadow_text((W//2, y + 82), C.get("latin", ""), fe, (240, 222, 188), blur=4, off=(0, 2), alpha=230, anchor="mm")

    # ── 底部：钩子 ──
    fh1 = fit(PFB, 52, 0, h1); fh2 = fit(PFB, 52, 0, h2)
    y += 290
    for ln in h1: shadow_text((W//2, y), ln, fh1, CREAM, blur=8, anchor="mm"); y += LH
    for ln in h2: shadow_text((W//2, y), ln, fh2, GOLD, blur=8, anchor="mm"); y += LH

    # 地点
    fs = f(PFL, 30)
    shadow_text((W//2, y - LH + 66), C.get("place", ""), fs, (232, 216, 190), blur=4, anchor="mm")


out = EP/f"cover_{C['name']}.png"
im.convert("RGB").save(out, optimize=True)
print(out, im.size)
