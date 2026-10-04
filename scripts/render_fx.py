"""render v2 扩展：蒙太奇 / 拼贴墙 / 细节聚焦 / 视频推近 / 引文 / 标注 / 调色 / 转场。由 render.py 导入。"""
import numpy as np, cv2, math
import fonts as _F
from PIL import Image, ImageDraw, ImageFilter

W, H, FPS = 1920, 1080, 30
def ease(t): t = min(1, max(0, t)); return 4*t*t*t if t < .5 else 1 - (-2*t+2)**3/2
def smooth(t): t = min(1, max(0, t)); return t*t*(3-2*t)

# ───── 调色：暖色 + 暗角 + 胶片颗粒（查表 + 整数运算，~6ms/帧）─────
_yy, _xx = np.mgrid[0:H, 0:W].astype(np.float32)
_r = np.sqrt(((_xx-W/2)/(W/2))**2 + ((_yy-H/2)/(H/2))**2)
_V = (1 - 0.30*np.clip((_r-0.55)/0.85, 0, 1)**1.6)
VIG3 = cv2.merge([(_V*255).astype(np.uint8)]*3)
_rng = np.random.default_rng(7)
_G = [cv2.resize(_rng.normal(0, 3.2, (H//2, W//2)).astype(np.float32), (W, H)) for _ in range(6)]
GPOS = [cv2.merge([np.clip(g, 0, 255).astype(np.uint8)]*3) for g in _G]
GNEG = [cv2.merge([np.clip(-g, 0, 255).astype(np.uint8)]*3) for g in _G]
_v = np.arange(256, dtype=np.float32)
LUT = cv2.merge([np.clip(255*((np.clip(_v*w, 0, 255))/255)**0.97, 0, 255).astype(np.uint8).reshape(256, 1) for w in (0.965, 1.0, 1.035)]).reshape(256, 1, 3)
def grade(fr, i):
    f = cv2.LUT(fr, LUT)
    f = cv2.multiply(f, VIG3, scale=1/255)
    f = cv2.add(f, GPOS[i % 6]); return cv2.subtract(f, GNEG[i % 6])

# ───── 运镜变化（蒙太奇每张图换一种推拉，避免千篇一律）─────
KB = [((1.03,.5,.5),(1.10,.5,.46)), ((1.10,.47,.5),(1.03,.53,.5)), ((1.08,.4,.5),(1.08,.6,.5)),
      ((1.08,.6,.5),(1.08,.4,.5)), ((1.07,.5,.6),(1.07,.5,.4)), ((1.1,.5,.42),(1.03,.5,.52))]

def make_montage(GEN, asset):
    def gen_montage(shot, n):
        items = [it if isinstance(it, dict) else {"src": it} for it in shot["items"]]
        items = [it for it in items if asset(it["src"]) is not None] or [{"src": shot["src"]}]
        k = len(items); xf = max(12, min(24, n//(k*3)))
        b = [round(n*j/k) for j in range(k+1)]; prev = None; last = None
        for j, it in enumerate(items):
            sub = dict(it); sub.setdefault("kb", KB[(j + shot.get("seed", 0)) % len(KB)])
            typ = sub.get("type", "vid" if sub["src"].startswith(("video/", "anim/")) else "img")
            if typ != "img": sub.pop("kb", None)
            for i, fr in enumerate(GEN[typ](sub, b[j+1]-b[j])):
                if prev is not None and i < xf:
                    a = smooth((i+1)/(xf+1)); fr = (prev*(1-a) + fr*a).astype(np.uint8)
                last = fr; yield fr
            prev = last.astype(np.float32)
    return gen_montage

def _blur_bg(src):
    ih, iw = src.shape[:2]; r = W/H
    if iw/ih > r: h = ih; w = h*r
    else: w = iw; h = w/r
    x, y = (iw-w)/2, (ih-h)/2
    bg = cv2.resize(src[int(y):int(y+h), int(x):int(x+w)], (W, H), interpolation=cv2.INTER_AREA)
    bg = cv2.GaussianBlur(bg, (0, 0), 40)
    return (bg*0.40 + np.array([20, 24, 30])*0.60).astype(np.uint8)

def _card(img, maxw, maxh, border=14, angle=0.0):
    ih, iw = img.shape[:2]; s = min(maxw/iw, maxh/ih)
    a = cv2.resize(img, (max(1, int(iw*s)), max(1, int(ih*s))), interpolation=cv2.INTER_AREA)
    a = cv2.copyMakeBorder(a, border, border, border, border, cv2.BORDER_CONSTANT, value=(240, 246, 250))
    bgra = cv2.cvtColor(a, cv2.COLOR_BGR2BGRA)
    pad = 60; bgra = cv2.copyMakeBorder(bgra, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=(0, 0, 0, 0))
    sh = np.zeros(bgra.shape[:2], np.float32); sh[pad+16:-pad+16, pad+10:-pad+10] = 0.55
    sh = cv2.GaussianBlur(sh, (0, 0), 16)
    out = np.zeros_like(bgra); out[..., 3] = (sh*255).astype(np.uint8)
    al = bgra[..., 3:4]/255.0; out = (out*(1-al) + bgra*al).astype(np.uint8); out[..., 3] = np.maximum(out[..., 3], bgra[..., 3])
    if angle:
        hh, ww = out.shape[:2]; M = cv2.getRotationMatrix2D((ww/2, hh/2), angle, 1.0)
        out = cv2.warpAffine(out, M, (ww, hh), flags=cv2.INTER_LINEAR, borderValue=(0, 0, 0, 0))
    return out

def _paste(fr, card, cx, cy, alpha=1.0, scale=1.0):
    if scale != 1.0: card = cv2.resize(card, None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
    ch, cw = card.shape[:2]; x, y = int(cx-cw/2), int(cy-ch/2)
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x+cw), min(H, y+ch)
    if x1 <= x0 or y1 <= y0: return fr
    sub = card[y0-y:y1-y, x0-x:x1-x]; a = sub[..., 3:4].astype(np.float32)/255*alpha
    fr[y0:y1, x0:x1] = (fr[y0:y1, x0:x1]*(1-a) + sub[..., :3]*a).astype(np.uint8); return fr

LAYOUTS = {2: [(.29, .5, -3), (.71, .5, 3)], 3: [(.2, .47, -5), (.5, .53, 2), (.8, .46, 5)],
           4: [(.27, .3, -4), (.73, .3, 3), (.27, .72, 3), (.73, .72, -3)], 5: [(.18, .32, -5), (.5, .28, 2), (.82, .33, 5), (.33, .74, 3), (.67, .73, -4)]}
def make_grid(load_img, asset):
    def gen_grid(shot, n):
        items = [s for s in shot["items"] if asset(s) is not None][:5] or [shot.get("src")]
        imgs = [load_img(str(asset(s))) for s in items]; k = len(imgs)
        bg = _blur_bg(imgs[0]); lay = LAYOUTS.get(k, [(.5, .5, 0)])
        mw, mh = {1: (W*.7, H*.78), 2: (W*.42, H*.72), 3: (W*.30, H*.62), 4: (W*.40, H*.40), 5: (W*.30, H*.40)}[k]
        cards = [_card(im, mw, mh, angle=lay[j][2]) for j, im in enumerate(imgs)]
        stag = min(1.1*FPS, n*0.6/k)
        for i in range(n):
            fr = bg.copy()
            for j, c in enumerate(cards):
                t = (i - j*stag)/(0.8*FPS)
                if t <= 0: continue
                e = ease(t); _paste(fr, c, lay[j][0]*W, lay[j][1]*H + (1-e)*40, alpha=min(1, t*1.4), scale=0.9+0.1*e)
            z = 1 + 0.02*smooth(i/max(n-1, 1)); M = cv2.getRotationMatrix2D((W/2, H/2), 0, z)
            yield cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    return gen_grid

def make_focus(load_img, asset, font, FONT_B):
    """整幅作品 → 依次推进到几个局部（金色细框 + 标签），最后可回到全图。rects: [[x,y,w,h,"标签"],…]（比例）"""
    def gen_focus(shot, n):
        src = load_img(str(asset(shot["src"]))); ih, iw = src.shape[:2]; bg = _blur_bg(src)
        rects = shot.get("rects", []); back = shot.get("back", False)
        def fitcam(x, y, w, h, fill):      # 让源图区域 (x,y,w,h 像素) 占画面 fill 比例，返回 (cx,cy,scale)
            s = min(W*fill/w, H*fill/h); return x+w/2, y+h/2, s
        full = fitcam(0, 0, iw, ih, 0.86)
        stops = [full] + [fitcam(r[0]*iw, r[1]*ih, r[2]*iw, r[3]*ih, 0.62) for r in rects] + ([full] if back else [])
        m = len(stops)-1 or 1; hold0 = 0.28
        f_lab = font(FONT_B, 40)
        labs = []
        for r in rects:
            t = r[4] if len(r) > 4 else ""
            if not t: labs.append(None); continue
            w = int(f_lab.getlength(t)) + 56; im = Image.new("RGBA", (w, 72), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, w-1, 71], 10, fill=(20, 17, 14, 200)); d.rectangle([0, 8, 5, 63], fill=(217, 169, 58, 255))
            d.text((28, 12), t, font=f_lab, fill=(255, 248, 235)); labs.append(np.asarray(im)[..., [2, 1, 0, 3]].copy())
        for i in range(n):
            u = i/max(n-1, 1)
            if len(stops) == 1: seg, f = 0, 0
            elif u < hold0: seg, f = 0, 0
            else:
                k = (u-hold0)/(1-hold0)*m; seg = min(int(k), m-1); f = k-seg
                f = smooth(min(1, f/0.6))                   # 60% 时间缓慢移动，其余停留
            a, b = stops[seg], stops[min(seg+1, len(stops)-1)]
            cx, cy, s = (a[0]+(b[0]-a[0])*f, a[1]+(b[1]-a[1])*f, math.exp(math.log(a[2])+(math.log(b[2])-math.log(a[2]))*f))
            s *= 1 + 0.01*math.sin(u*math.pi)
            M = np.float32([[s, 0, W/2-cx*s], [0, s, H/2-cy*s]]); shot["_cam"] = ("M", M.astype(np.float64), iw, ih)
            fr = cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_CUBIC if s > 1 else cv2.INTER_AREA, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))
            mask = cv2.warpAffine(np.ones((ih, iw), np.float32), M, (W, H), flags=cv2.INTER_LINEAR, borderValue=0)[..., None]
            fr = (fr*mask + bg*(1-mask)).astype(np.uint8)
            j = seg if f > 0.6 else seg-1                  # 当前聚焦的局部
            if 0 <= j < len(rects) and (u >= hold0):
                r = rects[j]; x0, y0 = M @ np.array([r[0]*iw, r[1]*ih, 1]); x1, y1 = M @ np.array([(r[0]+r[2])*iw, (r[1]+r[3])*ih, 1])
                al = smooth((f-0.6)/0.25) if seg == j+0 and f < 1 and j == seg else 1.0
                if j == seg-1: al = 1 - smooth(f/0.3)
                if al > 0:
                    ov = fr.copy(); cv2.rectangle(ov, (int(x0), int(y0)), (int(x1), int(y1)), (58, 169, 217), 4, cv2.LINE_AA)
                    fr = cv2.addWeighted(ov, al, fr, 1-al, 0)
                    if labs[j] is not None:
                        lb = labs[j]; lx = int(min(max(40, x0), W-lb.shape[1]-40))
                        SAFE = H - 160                         # 字幕区（底边 62 + 字高约 75）之上，标签不进字幕区
                        ly = int(y1 + 18) if y1 + 18 + 72 <= SAFE else int(y0 - 90)
                        ly = min(max(190 if shot.get("_has_tl") else 30, ly), SAFE - 72)   # 有年表条时标签不进顶部条带
                        _paste(fr, lb, lx+lb.shape[1]/2, ly+36, alpha=al)
            yield fr
    return gen_focus

def vid_zoom(gen, shot, n):
    z0, z1 = shot.get("zoom", [1.0, 1.04]); cy = shot.get("zcy", .5)
    for i, fr in enumerate(gen):
        z = z0 + (z1-z0)*smooth(i/max(n-1, 1))
        if abs(z-1) < 1e-3: yield fr; continue
        M = cv2.getRotationMatrix2D((W/2, H*cy), 0, z); yield cv2.warpAffine(fr, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

# ───── 叠层 ─────
def make_ov(font, FONT_B, FONT_L):
    SONG = _F.SERIF
    def ov_quote(o):
        """引文：宋体大字 + 出处，底部渐变压暗，逐行擦出"""
        lines = o["text"].split("\n"); f1 = font(o.get("font", SONG), o.get("size", 64)); f2 = font(FONT_L, 32)
        lh = int(f1.size*1.45); w = int(max(f1.getlength(l) for l in lines)) + 40
        h = lh*len(lines) + (70 if o.get("by") else 10)
        PH = h + 260; yy = np.arange(PH)[:, None]; xx = np.arange(W)[None, :]
        vy = np.clip(1 - np.abs(yy - PH/2)/(PH/2), 0, 1); vx = np.clip(1 - np.abs(xx - W/2)/(W*0.62), 0, 1)
        g = (185*(vy**0.8)*(vx**0.6)).astype(np.uint8)
        base = Image.new("RGBA", (W, PH), (14, 11, 8, 0)); base.putalpha(Image.fromarray(g)); im = base
        d = ImageDraw.Draw(im); x0 = (W-w)//2 + 20; top = 130
        for k, l in enumerate(lines): d.text((x0, top + k*lh), l, font=f1, fill=(255, 246, 228), stroke_width=1, stroke_fill=(30, 22, 15))
        if o.get("by"): d.text((x0 + w - 40 - f2.getlength("—— " + o["by"]), top + len(lines)*lh + 6), "—— " + o["by"], font=f2, fill=(230, 200, 150))
        return im, (0, max(40, (H - PH)//2 - 60))
    def ov_callout(o):
        """指示标注：圆圈 + 折线 + 文字卡。x,y 为画面比例坐标；side=l/r 文字放哪边"""
        x, y = int(o["x"]*W), int(o["y"]*H); side = o.get("side", "r"); f1 = font(FONT_B, 38); f2 = font(FONT_L, 26)
        t, sub = o["text"], o.get("sub", "")
        tw = int(max(f1.getlength(t), f2.getlength(sub) if sub else 0)) + 50; th = 100 if sub else 66
        im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
        r = o.get("r", 46); gold = (217, 169, 58, 255)
        d.ellipse([x-r, y-r, x+r, y+r], outline=gold, width=5); d.ellipse([x-r-10, y-r-10, x+r+10, y+r+10], outline=(217, 169, 58, 90), width=3)
        ex = x + (r+140 if side == "r" else -(r+140)); ey = y - 90 if y > 260 else y + 90
        d.line([(x + (r if side == "r" else -r)*0.7, y - r*0.7*(1 if ey < y else -1)), (ex, ey)], fill=gold, width=4)
        bx = ex if side == "r" else ex - tw; by = ey - th//2
        bx = min(max(20, bx), W-tw-20); by = min(max(20, by), H-th-20)
        d.rounded_rectangle([bx, by, bx+tw, by+th], 10, fill=(20, 17, 14, 210)); d.rectangle([bx, by+8, bx+5, by+th-8], fill=gold)
        d.text((bx+26, by+12), t, font=f1, fill=(255, 248, 235))
        if sub: d.text((bx+27, by+62), sub, font=f2, fill=(226, 208, 172))
        return im, (0, 0)
    def ov_year(o):
        """右上角年份/数字戳：大号数字（中文字自动换中文字体） + 小字说明"""
        fl = font(_F.LATIN, 120); fc = font(FONT_B, 104); f2 = font(FONT_B, 40)
        t, sub = o["text"], o.get("sub", "")
        L = lambda ch: ord(ch) < 0x2E80
        tw = sum((fl if L(ch) else fc).getlength(ch) for ch in t); w = int(max(tw, f2.getlength(sub))) + 40
        im = Image.new("RGBA", (w+40, 220), (0, 0, 0, 0)); d = ImageDraw.Draw(im); x = 20
        for ch in t:
            f = fl if L(ch) else fc; d.text((x, 0 if L(ch) else 14), ch, font=f, fill=(255, 248, 235), stroke_width=3, stroke_fill=(30, 22, 15)); x += f.getlength(ch)
        if sub: d.text((24, 150), sub, font=f2, fill=(255, 226, 170), stroke_width=4, stroke_fill=(30, 22, 15))
        return im, (W - w - 110, 70)
    return {"quote": ov_quote, "callout": ov_callout, "year": ov_year}

def transition(kind, prev, fr, i, m):
    """prev: 上一镜头末帧(float)；i: 本镜头第几帧；m: 转场帧数"""
    if prev is None or i >= m: return fr
    k = smooth((i+1)/(m+1))
    if kind == "flash":
        white = np.full_like(fr, 255, dtype=np.float32)
        return ((white*(1-k) + fr*k) if i >= m//2 else (prev*(1-2*k) + white*2*k)).clip(0, 255).astype(np.uint8)
    if kind == "whip":
        sh = int(W*k); a = np.roll(prev, -sh, axis=1); b = np.roll(fr.astype(np.float32), W-sh, axis=1)
        out = np.where(np.arange(W)[None, :, None] < W-sh, a, b)
        kx = max(1, int(60*math.sin(math.pi*k))); return cv2.blur(out.astype(np.uint8), (kx, 1))
    if kind == "zoom":
        z = 1 + 0.25*(1-k); M = cv2.getRotationMatrix2D((W/2, H/2), 0, z)
        a = cv2.warpAffine(fr, M, (W, H), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
        return (prev*(1-k) + a*k).astype(np.uint8)
    return (prev*(1-k) + fr*k).astype(np.uint8)


# ───── 动态叠层（衬线短句贴片 / 下划线高亮短引文）─────
PAPER = (247, 241, 230, 245); INKC = (42, 33, 24, 255); REDC = (168, 71, 42, 255); GOLDC = (217, 169, 58, 150)
def make_dyn(font, FONT_B, FONT_L):
    SONG = _F.SERIF
    def card(o, big=False):
        lines = o["text"].split("\n"); lab = o.get("label", ""); hl = o.get("hl", "")
        f1 = font(SONG, o.get("size", 84 if big else 54)); f0 = font(FONT_B, 30 if big else 26)
        lh = int(f1.size * 1.42); tw = int(max(f1.getlength(l) for l in lines)); w = max(tw, int(f0.getlength(lab))) + (140 if big else 96)
        h = (80 if lab else 30) + lh*len(lines) + (60 if big else 40)
        pos = o.get("pos", "c" if big else "bl")
        X = (W - w)//2 if pos == "c" else (80 if pos in ("bl", "tl") else W - w - 80)
        Y = (H - h)//2 - 40 if pos == "c" else (H - h - 190 if pos in ("bl", "br") else 90)
        total_chars = sum(len(l) for l in lines); cps = o.get("cps", 16)
        def render(t):
            im = Image.new("RGBA", (w + 60, h + 60), (0, 0, 0, 0))
            a0 = smooth(t/0.45)
            if a0 <= 0: return None, (X, Y)
            sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rectangle([30, 40, 30+w, 40+h], fill=(30, 20, 10, 60))
            im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(16)))
            d = ImageDraw.Draw(im); d.rectangle([30, 30, 30+w, 30+h], fill=PAPER)
            cx = 30 + w/2; y = 30 + (26 if lab else 22)
            if lab:
                la = smooth((t-0.15)/0.3)
                if la > 0: d.text((cx - f0.getlength(lab)/2, y), lab, font=f0, fill=REDC[:3] + (int(255*la),))
                rl = smooth((t-0.3)/0.4) * (min(w*0.5, f0.getlength(lab) + 80))
                if rl > 0: d.line([(cx - rl/2, y + f0.size + 14), (cx + rl/2, y + f0.size + 14)], fill=REDC, width=3)
                y += f0.size + 34
            shown = int(max(0, (t - (0.55 if lab else 0.3))) * cps); k = 0
            for li, l in enumerate(lines):
                x0 = cx - f1.getlength(l)/2; yy = y + li*lh
                if hl and hl in l:
                    j = l.index(hl); hx0 = x0 + f1.getlength(l[:j]); hx1 = hx0 + f1.getlength(hl)
                    done = max(0, (t - (0.55 if lab else 0.3)) - total_chars/cps)
                    e = smooth(done/0.6)
                    if e > 0: d.rectangle([hx0 - 6, yy + lh*0.52, hx0 - 6 + (hx1 - hx0 + 12)*e, yy + lh*0.86], fill=GOLDC)
                xx = x0
                for ch in l:
                    if k < shown:
                        ca = min(1, (shown - k)/3); d.text((xx, yy), ch, font=f1, fill=(INKC if not big else INKC)[:3] + (int(255*ca),))
                    xx += f1.getlength(ch); k += 1
            if a0 < 1: im.putalpha(Image.fromarray((np.asarray(im)[..., 3]*a0).astype(np.uint8)))
            return np.asarray(im)[..., [2, 1, 0, 3]].copy(), (X - 30, Y - 30 + int((1-a0)*24))
        return render
    def chapter(o):
        return card({"text": o["text"], "label": o.get("n", ""), "size": 80, "pos": "c", "cps": 10}, big=True)
    def tlstrip(o):
        """顶部时间线条：全片同一组事件，讲到第 cur 个时出现；进度从上一个平滑走到当前，等距节点、匀速缓动。"""
        ev = o["events"]; cur = o["cur"]; prev = o.get("prev", cur - 1); N = len(ev)
        BW, BH = 1560, 132; X = (W - BW)//2; Y = o.get("y", 34); x0, x1 = 70, BW - 70
        fy = font(_F.LATIN, 26); fyb = font(_F.LATIN, 40); fl = font(FONT_B, 28)
        fyc, fybc = font(FONT_B, 24), font(FONT_B, 36)     # 年份里的中文字（如「前44」的「前」）拉丁字体没有字形，会显示成方框 → 换中文字体
        L = lambda ch: ord(ch) < 0x2E80
        ylen = lambda s, fa, fc: sum((fa if L(ch) else fc).getlength(ch) for ch in s)
        def ytext(d, x, y, s, fa, fc, fill):
            for ch in s:
                f = fa if L(ch) else fc; d.text((x, y + (0 if L(ch) else 3)), ch, font=f, fill=fill); x += f.getlength(ch)
        xs = [x0 + (x1 - x0)*i/(N-1) for i in range(N)]
        def render(t):
            a = smooth(t/0.5)
            if a <= 0: return None, (X, Y)
            k = smooth((t-0.3)/1.2); pos = prev + (cur - prev)*k if prev >= 0 else cur*k
            im = Image.new("RGBA", (BW, BH + 40), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
            d.rounded_rectangle([0, 0, BW-1, BH-1], 18, fill=(20, 16, 12, 150))
            ly = 58; d.line([(x0, ly), (x1, ly)], fill=(205, 189, 159, 140), width=4)
            px = x0 + (x1 - x0)*max(0, pos)/(N-1)
            d.line([(x0, ly), (px, ly)], fill=(217, 169, 58, 255), width=5)
            for i, (yr, lab) in enumerate(ev):
                lit = i <= pos + 1e-6; is_cur = i == cur and k > 0.8
                r = 9 if not is_cur else 13 + 3*math.sin(t*5)
                d.ellipse([xs[i]-r, ly-r, xs[i]+r, ly+r], fill=(217, 169, 58, 255) if lit else (120, 108, 90, 200))
                if is_cur:
                    tw = ylen(str(yr), fyb, fybc); ytext(d, xs[i]-tw/2, ly-58, str(yr), fyb, fybc, (255, 244, 220, 255))
                    lw = fl.getlength(lab); lx = min(max(8, xs[i]-lw/2), BW - lw - 8); d.text((lx, ly+18), lab, font=fl, fill=(240, 214, 160, 255))
                else:
                    tw = ylen(str(yr), fy, fyc); ytext(d, xs[i]-tw/2, ly-44, str(yr), fy, fyc, (230, 220, 200, 220 if lit else 120))
            arr = np.asarray(im).copy(); arr[..., 3] = (arr[..., 3]*a).astype(np.uint8)
            return arr[..., [2, 1, 0, 3]].copy(), (X, Y)
        return render
    return {"card": card, "chapter": chapter, "tlstrip": tlstrip}

def transition2(kind, prev, fr, i, m):
    if prev is None or i >= m: return fr
    k = smooth((i+1)/(m+1))
    if kind == "rack":                      # 焦点转移：旧画面虚化淡出，新画面由虚到实
        s0 = 1 + 14*k; s1 = 1 + 14*(1-k)
        a = cv2.GaussianBlur(prev.astype(np.uint8), (0, 0), s0).astype(np.float32); b = cv2.GaussianBlur(fr, (0, 0), s1).astype(np.float32)
        return (a*(1-k) + b*k).astype(np.uint8)
    if kind == "light":                     # 光晕溶解：中段叠一层暖光
        g = math.sin(math.pi*k)*0.55; mix = prev*(1-k) + fr.astype(np.float32)*k
        warm = np.array([200, 225, 255], np.float32)
        return np.clip(mix*(1-g*0.6) + warm*g*0.6 + mix*g*0.25, 0, 255).astype(np.uint8)
    if kind == "luma":                      # 明暗溶解：新画面从暗部开始浮现
        L = cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY).astype(np.float32)/255
        mask = np.clip((k*1.4 - L)/0.25 + 0.5, 0, 1)[..., None]
        return (prev*(1-mask) + fr.astype(np.float32)*mask).astype(np.uint8)
    return transition(kind, prev, fr, i, m)
