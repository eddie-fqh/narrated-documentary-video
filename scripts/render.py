#!/usr/bin/env python3
"""合成引擎：shots.json + 逐字时间轴 → 无声画面 picture.mp4（1920x1080 30fps）

镜头切点 = 锚点短语第一个字的发音时刻（逐字对齐，见 align.py），不从字数估算时间。
用法: render.py shots.json out.mp4 [--from 秒 --to 秒]（只渲一段做样片）
"""
import json, sys, subprocess, math, os, pathlib, re, hashlib
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageOps
Image.MAX_IMAGE_PIXELS = None

W, H, FPS = 1920, 1080, 30
HERE = pathlib.Path(os.environ["EP_DIR"]).resolve()   # 当前这一期（一期一个目录）
PROJECT = pathlib.Path(os.environ.get("PROJECT_DIR", HERE.parent.parent)).resolve()   # 项目根：assets/（各期共用素材）、music/
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fonts as _F
# 中间片编码：macOS 用硬件编码（比 x264 medium 快约 4.5×，SSIM 0.995），其它平台用 x264；成片在 finish.py 里统一用 x264 重编
VENC = (["-c:v", "h264_videotoolbox", "-b:v", "20M"] if sys.platform == "darwin" and os.environ.get("RENDER_X264") != "1"
        else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "14"])
def asset(rel):
    import glob
    for base in (HERE, PROJECT/"assets"):
        if (base/rel).exists(): return base/rel
        g = sorted(glob.glob(str(base/rel) + ".*"))
        if g: return pathlib.Path(g[0])
    print(f"⚠️ 素材找不到，用上一镜头代替: {rel}", flush=True)
    return None
ROOT = None
FONT_B, FONT_L, FONT_EN = _F.BOLD, _F.LIGHT, _F.LATIN
INK, RED, GREEN, PAPER = (42, 33, 24), (168, 71, 42), (63, 92, 75), (255, 250, 240)

def font(p, s):
    try: return ImageFont.truetype(p, s)
    except Exception: return ImageFont.truetype(FONT_B, s)

def ease(t): t = min(1, max(0, t)); return 4*t*t*t if t < .5 else 1 - (-2*t+2)**3/2
def smooth(t): t = min(1, max(0, t)); return t*t*(3-2*t)

# ───────────── 时间轴：锚点 → 秒 ─────────────
class Timeline:
    def __init__(self):
        segd = HERE/"audio/segments"
        self.man = json.load(open(segd/"manifest.json"))
        chars = json.load(open(HERE/"work/chars.json"))
        self.bypos = {(c["seg"], c["pos"]): c for c in chars}
        self.text = ""; self.map = []           # 全文每个字符 → (seg,pos)
        for s in self.man["segments"]:
            for i, ch in enumerate(s["text"]):
                self.text += ch; self.map.append((s["index"], i))
        self.cursor = 0
        # 成品 mp3 的实测时长（不用清单里累加的时间）
        self.audio_end = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                str(HERE/"audio/narration.mp3")], capture_output=True, text=True).stdout)
    def at(self, phrase):
        k = self.text.find(phrase, self.cursor)
        if k < 0: raise SystemExit(f"锚点找不到（或顺序错了）：{phrase}")
        self.cursor = k + 1
        for j in range(k, k+len(phrase)):
            c = self.bypos.get(self.map[j])
            if c: return c["t0"]
        raise SystemExit(f"锚点无时间：{phrase}")

# ───────────── 素材 ─────────────
_img_cache = {}
def load_img(path, maxw=3200):
    if path in _img_cache: return _img_cache[path]
    im = ImageOps.exif_transpose(Image.open(path)).convert("RGB")
    if im.width > maxw: im = im.resize((maxw, round(im.height*maxw/im.width)), Image.LANCZOS)
    a = cv2.cvtColor(np.asarray(im), cv2.COLOR_RGB2BGR)
    _img_cache[path] = a; return a

def cover_rect(iw, ih, z=1.0, cx=.5, cy=.5):
    """返回源图上的裁切框 (x,y,w,h)，比例 16:9，z>1 放大。"""
    r = W/H
    if iw/ih > r: h = ih; w = h*r
    else: w = iw; h = w/r
    w /= z; h /= z
    x = (iw - w)*cx; y = (ih - h)*cy
    return x, y, w, h

MOVES = {  # (z0, cx0, cy0) → (z1, cx1, cy1)   舒缓版：幅度约为原来的一半
    "in":    ((1.02, .5, .5), (1.09, .5, .47)),
    "out":   ((1.10, .5, .47), (1.02, .5, .5)),
    "left":  ((1.08, .62, .5), (1.08, .38, .5)),
    "right": ((1.08, .38, .5), (1.08, .62, .5)),
    "up":    ((1.08, .5, .65), (1.08, .5, .35)),
    "down":  ((1.08, .5, .35), (1.08, .5, .65)),
    "none":  ((1.03, .5, .5), (1.03, .5, .5)),
}

def frame_from_rect(src, x, y, w, h):
    s = W / w
    M = np.float32([[s, 0, -x*s], [0, s, -y*s]])
    return cv2.warpAffine(src, M, (W, H), flags=cv2.INTER_LINEAR if s < 1 else cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT)

def gen_img(shot, n):
    src = load_img(str(asset(shot["src"])))
    ih, iw = src.shape[:2]
    mv = shot.get("move", "in")
    (z0, cx0, cy0), (z1, cx1, cy1) = shot["kb"] if "kb" in shot else MOVES[mv]
    for i in range(n):
        t = smooth(i/max(n-1, 1)) if shot.get("ease", True) else i/max(n-1, 1)
        z = z0 + (z1-z0)*t; cx = cx0 + (cx1-cx0)*t; cy = cy0 + (cy1-cy0)*t
        rc = cover_rect(iw, ih, z, cx, cy); shot["_cam"] = ("rect", rc, iw, ih)
        yield frame_from_rect(src, *rc)

def gen_art(shot, n):
    """画作/文献：虚化底 + 居中原作（带投影），缓慢推近。"""
    src = load_img(str(asset(shot["src"])))
    ih, iw = src.shape[:2]
    bg = cv2.GaussianBlur(frame_from_rect(src, *cover_rect(iw, ih, 1.1)), (0, 0), 38)
    bg = (bg*0.42 + np.array([20, 24, 30])*0.58).astype(np.uint8)
    maxh, maxw = H*0.82, W*0.80
    s = min(maxh/ih, maxw/iw)
    fw, fh = int(iw*s), int(ih*s)
    art = cv2.resize(src, (fw, fh), interpolation=cv2.INTER_AREA)
    base = bg.copy()
    x0 = (W-fw)//2 + shot.get("dx", 0); y0 = (H-fh)//2 - 20
    sh = np.zeros((H, W), np.float32); sh[y0+14:y0+fh+14, x0+10:x0+fw+10] = 1
    sh = cv2.GaussianBlur(sh, (0, 0), 22)[..., None]
    base = (base*(1-0.55*sh)).astype(np.uint8)
    base[y0:y0+fh, x0:x0+fw] = art
    for i in range(n):
        z = 1.0 + 0.05*ease(i/max(n-1, 1))
        M = cv2.getRotationMatrix2D((W/2, H/2), 0, z)
        yield cv2.warpAffine(base, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)

def gen_split(shot, n):
    """两图并排对比。"""
    L = load_img(str(asset(shot["src"]))); R = load_img(str(asset(shot["src2"])))
    bg = np.full((H, W, 3), (38, 33, 30), np.uint8)
    out = bg.copy()
    for k, im in enumerate((L, R)):
        ih, iw = im.shape[:2]; s = min((H*0.78)/ih, (W*0.44)/iw)
        fw, fh = int(iw*s), int(ih*s); a = cv2.resize(im, (fw, fh), interpolation=cv2.INTER_AREA)
        cx = W//4 if k == 0 else 3*W//4; x0 = cx - fw//2; y0 = (H-fh)//2 - 30
        out[y0:y0+fh, x0:x0+fw] = a
    for i in range(n):
        z = 1.0 + 0.03*ease(i/max(n-1, 1)); M = cv2.getRotationMatrix2D((W/2, H/2), 0, z)
        yield cv2.warpAffine(out, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(38, 33, 30))

def probe_dur(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p],
                                capture_output=True, text=True).stdout.strip() or 0)

def gen_vid(shot, n):
    p = str(asset(shot["src"])); ss = shot.get("ss", 0.0); d = probe_dur(p) - ss - 0.1
    need = n/FPS
    speed = shot.get("speed", None)
    if speed is None: speed = min(1.0, max(0.45, d/need))          # 不够长就放慢（最多 0.45x）
    vf = [f"setpts=PTS/{speed:.4f}" if abs(speed-1) > 1e-3 else "null",
          f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos",
          f"crop={W}:{H}:(iw-{W})*{shot.get('cx', .5)}:(ih-{H})*{shot.get('cy', .5)}", f"fps={FPS}"]
    if shot.get("zoom"):   # 视频上再叠一点推近
        pass
    cmd = ["ffmpeg", "-v", "error", "-ss", str(ss), "-i", p, "-an", "-vf", ",".join(vf), "-frames:v", str(n),
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-"]
    pr = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    last = None; got = 0
    while got < n:
        buf = pr.stdout.read(W*H*3)
        if len(buf) < W*H*3: break
        last = np.frombuffer(buf, np.uint8).reshape(H, W, 3); got += 1
        yield last
    pr.wait()
    while got < n:                                                 # 源太短：定格
        got += 1; yield last if last is not None else np.zeros((H, W, 3), np.uint8)

GEN = {"img": gen_img, "art": gen_art, "vid": gen_vid, "split": gen_split}
import render_fx as FX
_gen_vid_raw = gen_vid
def gen_vid2(shot, n):
    g = _gen_vid_raw(shot, n)
    if shot["src"].startswith("anim/") and "zoom" not in shot: yield from g; return
    shot.setdefault("zoom", [1.0, 1.04]); yield from FX.vid_zoom(g, shot, n)
GEN["vid"] = gen_vid2
GEN["montage"] = FX.make_montage(GEN, asset)
GEN["grid"] = FX.make_grid(load_img, asset)

# ───────────── 叠层 ─────────────
def rounded_card(w, h, r=16, fill=(255, 250, 240, 235), bar=RED):
    im = Image.new("RGBA", (w+60, h+60), (0, 0, 0, 0))
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0)); ImageDraw.Draw(sh).rounded_rectangle([30, 38, 30+w, 38+h], r, fill=(40, 25, 10, 70))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(14)))
    d = ImageDraw.Draw(im); d.rounded_rectangle([30, 30, 30+w, 30+h], r, fill=fill)
    if bar: d.rectangle([30, 30+6, 36, 30+h-6], fill=bar+(255,))
    return im

def _is_latin(ch): return ord(ch) < 0x2E80          # 中日韩字符及全角标点以下都算拉丁区
def mixed_len(text, fl, fc):
    return sum((fl if _is_latin(ch) else fc).getlength(ch) for ch in text)
def draw_mixed(d, xy, text, fl, fc, fill):
    """拉丁字体没有中文字形（会画成方框）——逐字选字体。"""
    x, y = xy
    for ch in text:
        f = fl if _is_latin(ch) else fc
        d.text((x, y), ch, font=f, fill=fill); x += f.getlength(ch)

def ov_place(o):
    """左上角地点标签：中文名 + 外文名"""
    f1, f2, f2c = font(FONT_B, 34), font(FONT_EN, 22), font(FONT_B, 21)
    t1, t2 = o["text"], o.get("en", "")
    w = int(max(f1.getlength(t1), mixed_len(t2, f2, f2c))) + 70; h = 96 if t2 else 70
    im = rounded_card(w, h, 12, fill=(24, 20, 16, 170), bar=(217, 169, 58))
    d = ImageDraw.Draw(im); d.text((30+30, 30+14), t1, font=f1, fill=(255, 248, 235))
    if t2: draw_mixed(d, (30+31, 30+58), t2, f2, f2c, (217, 199, 160))
    return im, (40, 40)

def ov_name(o):
    """人名卡：左下，中文名 + 原名 + 生卒年"""
    f1, f2, f3 = font(FONT_B, 56), font(FONT_EN, 30), font(FONT_EN, 28)
    f3c = font(FONT_B, 26); yrs = "   " + o.get("years", "")
    w = int(max(f1.getlength(o["zh"]), mixed_len(o["en"], f2, font(FONT_B, 28)) + mixed_len(yrs, f3, f3c))) + 90
    im = rounded_card(w, 150, 16)
    d = ImageDraw.Draw(im)
    d.text((30+40, 30+18), o["zh"], font=f1, fill=INK)
    draw_mixed(d, (30+42, 30+94), o["en"], f2, font(FONT_B, 28), (107, 90, 69))
    draw_mixed(d, (30+48+mixed_len(o["en"], f2, font(FONT_B, 28)), 30+96), yrs, f3, f3c, RED)
    pos = o.get("pos", "bl")
    xy = (70, H-150-60-200) if pos == "bl" else (W-w-130, H-150-60-200)
    return im, xy

def ov_art(o):
    """画作/实物标签：半透明深色卡片 + 标题 + 出处"""
    f1, f2 = font(FONT_B, 36), font(FONT_L, 26)
    w = int(max(f1.getlength(o["title"]), f2.getlength(o["by"]))) + 64; h = 108
    im = rounded_card(w, h, 12, fill=(20, 17, 14, 185), bar=(217, 169, 58))
    d = ImageDraw.Draw(im)
    d.text((30+30, 30+14), o["title"], font=f1, fill=(255, 248, 235))
    d.text((30+30, 30+62), o["by"], font=f2, fill=(226, 208, 172))
    pos = o.get("pos", "br")
    xy = (W-w-60-60, H-h-60-150) if pos == "br" else (60, H-h-60-150)
    return im, xy

def ov_big(o):
    """大数字：居中偏上，带单位与说明"""
    t, sub = o["text"], o.get("sub", "")
    x0 = o.get("x", 120); size = 150
    f1 = font(FONT_B, size)
    while f1.getlength(t) > W - x0 - 100 and size > 44:      # 长句自动缩小到画面放得下
        size -= 6; f1 = font(FONT_B, size)
    f2 = font(FONT_B, 44)
    w = int(max(f1.getlength(t), f2.getlength(sub))) + 80
    im = Image.new("RGBA", (w+80, 300), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    for r in (10, 6):
        d.text((40, 0), t, font=f1, fill=(0, 0, 0, 80), stroke_width=r, stroke_fill=(0, 0, 0, 60))
    d.text((40, 0), t, font=f1, fill=(255, 248, 235), stroke_width=4, stroke_fill=(42, 33, 24))
    if sub: d.text((44, size + 40), sub, font=f2, fill=(255, 235, 200), stroke_width=3, stroke_fill=(42, 33, 24))
    im = im.filter(ImageFilter.SMOOTH_MORE) if False else im
    return im, (o.get("x", 120), o.get("y", 180))

def ov_chapter(o):
    """章节卡：居中半透明白框"""
    f0, f1 = font(FONT_EN, 34), font(FONT_B, 72)
    n, t = o.get("n", ""), o["text"]
    w = int(max(f1.getlength(t), f0.getlength(n))) + 140; h = 210
    im = rounded_card(w, h, 18, fill=(255, 250, 240, 225), bar=None)
    d = ImageDraw.Draw(im)
    d.text((30+(w-f0.getlength(n))/2, 30+26), n, font=f0, fill=RED)
    d.line([(30+w/2-60, 30+80), (30+w/2+60, 30+80)], fill=RED+(255,), width=3)
    d.text((30+(w-f1.getlength(t))/2, 30+100), t, font=f1, fill=INK)
    return im, ((W-w-60)//2, (H-h-60)//2 - 40)

def ov_title(o):
    """片名：大字 + 系列名"""
    f1, f2 = font(FONT_B, 110), font(FONT_B, 44)
    t1, t2 = o["text"], o.get("sub", "")
    w = int(max(f1.getlength(t1), f2.getlength(t2))) + 100
    im = Image.new("RGBA", (w+60, 320), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.text((30+(w-f2.getlength(t2))/2, 20), t2, font=f2, fill=(255, 230, 190), stroke_width=3, stroke_fill=(30, 22, 15))
    d.text((30+(w-f1.getlength(t1))/2, 100), t1, font=f1, fill=(255, 250, 240), stroke_width=6, stroke_fill=(30, 22, 15))
    return im, ((W-w-60)//2, 250)

OVS = {"place": ov_place, "name": ov_name, "art": ov_art, "big": ov_big, "chapter": ov_chapter, "title": ov_title}
OVS.update(FX.make_ov(font, FONT_B, FONT_L))
GEN["focus"] = FX.make_focus(load_img, asset, font, FONT_B)
DYN = FX.make_dyn(font, FONT_B, FONT_L)

def compose(frame, ov_img, xy, alpha, slide=0):
    x, y = xy[0] + int(slide), xy[1]
    oh, ow = ov_img.shape[:2]
    x0, y0 = max(0, x), max(0, y); x1, y1 = min(W, x+ow), min(H, y+oh)
    if x1 <= x0 or y1 <= y0 or alpha <= 0: return frame
    sub = ov_img[y0-y:y1-y, x0-x:x1-x]
    a = sub[..., 3:4].astype(np.float32)/255*alpha
    roi = frame[y0:y1, x0:x1].astype(np.float32)
    frame[y0:y1, x0:x1] = (roi*(1-a) + sub[..., :3].astype(np.float32)*a).astype(np.uint8)
    return frame

def ov_bgra(o):
    im, xy = OVS[o["kind"]](o)
    arr = np.asarray(im.convert("RGBA")).copy()
    arr = arr[..., [2, 1, 0, 3]]                         # RGBA → BGRA
    return arr, xy

# ───────────── 主流程 ─────────────
def main():
    spec = json.load(open(sys.argv[1])); out = sys.argv[2]
    t_from = float(sys.argv[sys.argv.index("--from")+1]) if "--from" in sys.argv else None
    t_to = float(sys.argv[sys.argv.index("--to")+1]) if "--to" in sys.argv else None
    TL = Timeline()
    shots = spec["shots"]
    for s in shots:
        s["t"] = 0.0 if s.get("at") == "__start__" else TL.at(s["at"]) + s.get("lead", -0.12)
    end = TL.audio_end + spec.get("tail", 4.0)
    for i, s in enumerate(shots):
        s["t_end"] = shots[i+1]["t"] if i+1 < len(shots) else end
        assert s["t_end"] > s["t"], f"镜头时长 ≤0：{s.get('at')}"
    # 帧号量化（整帧，防 CFR 漂移）
    for s in shots:
        s["f0"] = round(s["t"]*FPS); s["f1"] = round(s["t_end"]*FPS)
    F0 = round(t_from*FPS) if t_from is not None else 0
    F1 = round(t_to*FPS) if t_to is not None else shots[-1]["f1"]
    json.dump([{k: s[k] for k in ("at", "t", "t_end", "src") if k in s} for s in shots],
              open(HERE/"work/shot_times.json", "w"), ensure_ascii=False, indent=1)
    ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{W}x{H}", "-r", str(FPS),
                           "-i", "-", *VENC, "-pix_fmt", "yuv420p",
                           "-fps_mode", "cfr", out], stdin=subprocess.PIPE)
    prev_last = None
    for idx, s in enumerate(shots):          # 缺素材 → 沿用上一镜头的素材与类型
        if s.get("type") in ("montage", "grid"):
            its = [it if isinstance(it, str) else it["src"] for it in s["items"]]
            miss = [x for x in its if asset(x) is None]
            if len(miss) == len(its):
                assert idx, f"第一个镜头的素材全部缺失：{its}"
                s["type"] = "img"; s["src"] = shots[idx-1]["src"]
            s.setdefault("src", its[0]); continue
        for key in ("src", "src2"):
            if key in s and asset(s[key]) is None:
                prev = shots[idx-1] if idx else None
                if prev and asset(prev["src"]) is not None: s["src"] = prev["src"]; s["type"] = prev.get("type", "img"); s.pop("src2", None); s.pop("kb", None)
                else: raise SystemExit(f"素材找不到，且没有上一镜头可代替：{s[key]}")
        if s.get("type") == "split" and "src2" not in s: s["type"] = "img"; s.pop("kb", None)
    for idx, s in enumerate(shots):
        if s["f1"] <= F0 or s["f0"] >= F1: continue
        n = s["f1"] - s["f0"]
        ovs = []
        s["_has_tl"] = any(o.get("kind") == "tlstrip" for o in s.get("ov", []))   # 顶部有年表条：地名牌下移、focus 标签不进条带
        for o in s.get("ov", []):
            if o.get("kind") == "callout" and "ix" in o:
                def mk(o=o, s=s):
                    cache = {}
                    def f(t):
                        cam = s.get("_cam")
                        if not cam: return None, (0, 0)
                        if cam[0] == "rect":
                            (x, y, w, h), iw, ih = cam[1], cam[2], cam[3]
                            fx = (o["ix"]*iw - x) * W / w; fy = (o["iy"]*ih - y) * W / w
                        else:
                            M, iw, ih = cam[1], cam[2], cam[3]
                            fx, fy = M @ np.array([o["ix"]*iw, o["iy"]*ih, 1.0])
                        key = (int(fx)//2, int(fy)//2)
                        if key not in cache:
                            cache.clear(); cache[key] = ov_bgra(dict(o, x=fx/W, y=fy/H))
                        return cache[key]
                    return f
                ovs.append((mk(), None, o.get("in", 0.25), o.get("dur", None), "dyn")); continue
            if o.get("kind") in DYN:
                ovs.append((DYN[o["kind"]](o), None, o.get("in", 0.25), o.get("dur", None), "dyn")); continue
            img, xy = ov_bgra(o)
            if o.get("kind") == "place" and s.get("_has_tl"): xy = (xy[0], xy[1] + 150)   # 年表条高 132（y 34–166），地名牌挪到它下面
            a0 = o.get("in", 0.25); dur = o.get("dur", None)
            ovs.append((img, xy, a0, dur, o.get("kind")))
        xf = int(max(s.get("xf", 0.7), 0.5 if idx else 0)*FPS) if idx else int(s.get("xf", 0)*FPS)   # 默认 0.7s 叠化
        tr = s.get("tr", "fade") if (s.get("force_tr") or s.get("tr") in ("rack", "light", "luma")) else "fade"
        do_grade = s.get("grade", not s["src"].startswith("anim/"))
        fade_in = int(s.get("fade_in", 0)*FPS)      # 从黑淡入
        fade_out = int(s.get("fade_out", 0)*FPS)    # 淡出到黑
        gen = GEN[s.get("type", "img")](s, n)
        for i, fr in enumerate(gen):
            gi = s["f0"] + i
            if gi >= F1: break
            fr = fr if fr.flags.writeable else fr.copy()
            if do_grade: fr = FX.grade(fr, gi)
            tt = i/FPS
            for img, xy, a0, dur, kind in ovs:
                if kind == "dyn":
                    life = dur if dur else n/FPS
                    out_a = 1 - smooth((tt - (a0 + life - 0.4))/0.4)
                    if tt >= a0 and out_a > 0:
                        im2, xy2 = img(tt - a0)
                        if im2 is not None: fr = compose(fr, im2, xy2, out_a, 0)
                    continue
                life = dur if dur else n/FPS
                a = smooth((tt - a0)/0.35) * (1 - smooth((tt - (a0+life-0.35))/0.35)) if dur else smooth((tt - a0)/0.35) * (1 - smooth((tt - (n/FPS - 0.3))/0.3))
                slide = (1-smooth((tt-a0)/0.45))*(-40 if kind in ("place", "name") else 0)
                if kind == "quote": a = a*1.0
                fr = compose(fr, img, xy, a, slide)
            if xf and prev_last is not None and i < xf:
                fr = FX.transition2(tr, prev_last, fr, i, xf)
            if fade_in and i < fade_in: fr = (fr*smooth(i/fade_in)).astype(np.uint8)
            if fade_out and i >= n-fade_out: fr = (fr*smooth((n-1-i)/fade_out)).astype(np.uint8)
            if gi >= F0: ff.stdin.write(fr.tobytes())
            last = fr
        prev_last = last.astype(np.float32)
        print(f"  [{idx+1}/{len(shots)}] {s['t']:7.2f}–{s['t_end']:7.2f}s {s.get('type','img'):5} {s['src'][-40:]}", flush=True)
    ff.stdin.close(); ff.wait()
    print("✅", out)

if __name__ == "__main__":
    main()
