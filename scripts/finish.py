#!/usr/bin/env python3
"""字幕（ASS，逐字时间）+ 配乐（分段换曲、侧链闪避）+ 烧字幕 + 合成成片。
用法: finish.py picture.mp4 out.mp4 [--to 秒]   （--to 用于样片：只混到这个时间）"""
import json, re, sys, subprocess, pathlib, os
HERE = pathlib.Path(os.environ["EP_DIR"]).resolve()
ROOT = pathlib.Path(os.environ.get("PROJECT_DIR", HERE.parent.parent)).resolve()   # 项目根（music/ 与 assets/sfx/ 在这里）
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import fonts as _F
W, H = 1920, 1080
MP3 = HERE/"audio/narration.mp3"

# ───────── 字幕 ─────────
D = dict(zip("零一二三四五六七八九", "0123456789")); D["两"] = "2"
def cn2int(t):
    """十七→17，四百一十四→414，三万七千→37000，一千→1000"""
    total, sect, num = 0, 0, 0
    for ch in t:
        if ch in D: num = int(D[ch])
        elif ch in "十百千":
            unit = {"十": 10, "百": 100, "千": 1000}[ch]; sect += (num or 1) * unit; num = 0
        elif ch == "万":
            total += (sect + num) * 10000; sect = num = 0
    return total + sect + num
def fmtn(v):
    """十万以上的整万数用「万」显示（一千万 → 1000万，不显示 10000000）；其余照常"""
    return f"{v//10000}万" if v >= 100000 and v % 10000 == 0 else str(v)
UNITS = "年米级个座块吨岁天分钟多万层步名幅件次公里平方位扇"
def disp(s):
    # 并列世纪（十七十八世纪 → 17、18世纪），不然整串当成一个数转成「88世纪」
    s = re.sub(r"([一二]?十[一二三四五六七八九]?)([一二]?十[一二三四五六七八九]?)(?=世纪)", lambda m: f"{cn2int(m.group(1))}、{cn2int(m.group(2))}", s)
    Y = r"([零一二三四五六七八九]{4})"
    yr = lambda t: "".join(D[c] for c in t)
    # 年份区间（一四八五到一四八八年 → 1485到1488年）：两头一起转
    s = re.sub(Y + r"([到至])" + Y + r"(?=年)", lambda m: yr(m.group(1)) + m.group(2) + yr(m.group(3)), s)
    # 年份：四位逐字读的中文数字 + 年 → 阿拉伯数字（一四一八年 → 1418年）
    s = re.sub(Y + r"(?=年)", lambda m: yr(m.group(1)), s)
    # 钟点（九点四十七分 → 9点47分）：时和分一起转，别半中半阿
    s = re.sub(r"([零一二两三四五六七八九十]+)点([零一二三四五六七八九十]+)分(?!之)", lambda m: f"{cn2int(m.group(1))}点{cn2int(m.group(2))}分", s)
    N = r"([零一二两三四五六七八九十百千万]*[十百千万][零一二两三四五六七八九十百千万]*)"
    U = r"(?=[" + UNITS + r"]|世纪)(?!分之)"      # 「世」单独不算单位：人名里的「十世」「十三世」保持中文；「世纪」照转
    def num(t, pre):
        # 裸「百/千/万」（上万件、一百二十多万块里的「万」）不是数字，原样保留——以前会变成 0
        if t in ("百", "千", "万"): return None
        if re.search(r"[一二两三四五六七八九][一二两三四五六七八九][十百千万]", t): return None   # 「五六十吨」「三四百」是约数，保持中文，别算成 60
        if re.search(r"[十百千][一二两三四五六七八九][一二两三四五六七八九]$", t): return None   # 「十七八岁」「二十七八」也是约数，别算成 18
        return fmtn(cn2int(t))
    # 区间（五万到八万名 → 50000到80000名）：两头一起转，不然前一半留中文、后一半变数字
    def rng(m):
        pre = m.string[m.start()-1] if m.start() else ""
        a, b = num(m.group(1), pre), num(m.group(3), "")
        return m.group(0) if a is None or b is None else f"{a}{m.group(2)}{b}"
    s = re.sub(r"(?<![几数])" + N + r"([到至])" + N + U, rng, s)
    # 带十/百/千/万的数目 → 阿拉伯数字（四百六十三级 → 463级；十七年 → 17年）
    def one(m):
        pre = m.string[m.start()-1] if m.start() else ""
        v = num(m.group(1), pre); return m.group(0) if v is None else v
    s = re.sub(r"(?<![几数])" + N + U, one, s)
    return s

def build_ass(path, t_to=None):
    chars = json.load(open(HERE/"work/chars.json"))
    man = json.load(open(HERE/"audio/segments/manifest.json"))
    by = {(c["seg"], c["pos"]): c for c in chars}
    lines = []
    for s in man["segments"]:
        cur = []
        for i, ch in enumerate(s["text"]):
            if ch in "，。\n":
                if cur:
                    if ch == "。": cur[-1] = {**cur[-1], "_end": True}   # 句末：单字答句「有。」并行时要留空格
                    lines.append(cur); cur = []
                continue
            c = by.get((s["index"], i))
            if c: cur.append(c)
            if ch in "？！；" and cur:      # 问号/叹号/分号后也断行（保留标点），别让长句在中点切断词语（「后 / 来看了」）
                lines.append(cur); cur = []
            elif ch == " " and cur: cur.append({**cur[-1], "c": " "})
        if cur: lines.append(cur)
    merged_lines = []                   # 只有一个字的行（如「画，就一直…」里的「画」）并到下一行，别单独闪一下
    for L in lines:
        if merged_lines and len(merged_lines[-1]) == 1:
            P = merged_lines[-1]          # 「有。十二世纪」→「有 12世纪」，别读成「有12世纪」
            merged_lines[-1] = P + ([{**P[-1], "c": " "}] if P[-1].get("_end") else []) + L
        else:
            merged_lines.append(L)
    lines = merged_lines
    cues = []
    for L in lines:
        parts = [L]
        if len(L) > 18:            # 在中点附近切成两条，每条各用自己字的时间；不许切在英文单词中间
            NUM = set("零一二两三四五六七八九十百千万0123456789多")   # 也不许紧跟在数字后面切（二|十公里 → 「二」+「10公里」；二十|三号）
            ok = lambda k: not (L[k-1]["c"].isascii() and L[k-1]["c"].isalpha() and L[k]["c"].isascii() and L[k]["c"].isalpha()) \
                           and not (L[k-1]["c"] in NUM)
            mid = len(L)//2
            # 优先在词边界切（jieba 分词），不把一个词拆到两行；找不到再退回字边界
            try:
                import jieba; jieba.setLogLevel(60)
                if not getattr(jieba, "_ep_words", False):     # 本集人名牌/地名/作品牌里的专名加进词典，长音译名不再被拆
                    try:
                        S = json.load(open(HERE/"shots.json")); S = S if isinstance(S, list) else S.get("shots", [])
                        for sh in S:
                            for o in sh.get("ov", []) or []:
                                for f in ("zh", "text", "label"):
                                    v = o.get(f)
                                    if isinstance(v, str):
                                        for w in re.split(r"[·•，,。、《》「」（）()\s·—/:：]+", v):
                                            if 2 <= len(w) <= 12 and not w.isdigit(): jieba.add_word(w, 10000)
                    except Exception: pass
                    jieba._ep_words = True
                txt = "".join(c["c"] for c in L); bounds, p = set(), 0
                for w in jieba.cut(txt, HMM=False): p += len(w); bounds.add(p)
            except Exception:
                bounds = None
            txt0 = "".join(c["c"] for c in L); inname = set()      # 人名间隔号「·」前后各 3 字内不切（带间隔号的外文人名不被拆开）
            for m in re.finditer(r"·", txt0):
                inname.update(range(max(2, m.start() - 3), m.start() + 4))
            ok0 = ok; ok = lambda k: ok0(k) and k not in inname
            cand = [k for k in range(2, len(L)-1) if ok(k) and (bounds is None or k in bounds)]
            if not cand: cand = [k for k in range(2, len(L)-1) if ok(k)]
            if not cand: cand = [k for k in range(2, len(L)-1) if ok0(k)]      # 整行就是一个长名字时只好切
            k = min(cand, key=lambda k: (abs(k-mid), k))
            parts = [L[:k], L[k:]]
        for P in parts:
            cues.append([P[0]["t0"], P[-1]["t1"], disp("".join(c["c"] for c in P))])
    # 首尾时间整理：略提前出现，停留到下一条前
    for c in cues:                       # 先统一提前开始时间
        c[0] = max(0, c[0] - 0.08)
    merged = []                          # 对齐偶尔给相邻两句同一起点（如「最后，」「最后一片云…」）→ 合并成一条
    for c in cues:
        if merged and c[0] - merged[-1][0] < 0.35:
            merged[-1][1] = max(merged[-1][1], c[1]); merged[-1][2] = merged[-1][2] + " " + c[2]
        else: merged.append(list(c))
    cues = merged
    for j, c in enumerate(cues):         # 再按「已调整的」下一条开始截断结尾 → 绝不重叠
        nxt = cues[j+1][0] if j+1 < len(cues) else c[1] + 1.0
        c[1] = min(max(c[1] + 0.25, c[0] + 0.8), nxt - 0.02)
    bad = [j for j in range(len(cues)-1) if cues[j][1] > cues[j+1][0] or cues[j][1] <= cues[j][0]]
    assert not bad, f"字幕仍有重叠/零长: {bad[:5]}"
    def ts(x):
        h = int(x//3600); m = int(x % 3600//60); s = x % 60
        return f"{h}:{m:02d}:{s:05.2f}"
    hdr = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,{_F.SUB_FONT_NAME},58,&H00FFFFFF,&H00FFFFFF,&H00141414,&H96000000,1,0,0,0,100,100,2,0,1,3.6,1.2,2,120,120,62,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    body = "".join(f"Dialogue: 0,{ts(a)},{ts(b)},Sub,,0,0,0,,{t}\n" for a, b, t in cues if t_to is None or a < t_to)
    # 兜底：ASS 只精确到厘秒，
    # 舍入可能让「前条结束 > 后条开始」—— 按写入文件的厘秒整数再校一遍，重叠就把后条开始推到前条结束。
    def cs(t): h, m, r = t.split(":"); s2, c = r.split("."); return int(h)*360000 + int(m)*6000 + int(s2)*100 + int(c)
    def fmt(c): return f"{c//360000}:{c%360000//6000:02d}:{c%6000//100:02d}.{c%100:02d}"
    out, prev = [], None
    for line in body.splitlines():
        p = line.split(",", 9)
        if prev is not None and cs(p[1]) < prev: p[1] = fmt(prev)
        assert cs(p[2]) > cs(p[1]), f"零长字幕: {line}"
        prev = cs(p[2]); out.append(",".join(p))
    body = "\n".join(out) + "\n"
    pathlib.Path(path).write_text(hdr + body, encoding="utf-8")
    return cues

# ───────── 配乐 ─────────
SECTIONS = [tuple(x) for x in json.load(open(HERE/"music.json"))]   # [[锚点句, 曲名, 倍数], …]，第一段锚点写 "__start__"

def section_times():
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import render as R
    TL = R.Timeline(); out = []
    for a, tr, v in SECTIONS:
        out.append((0.0 if a == "__start__" else TL.at(a) - 0.12, tr, v))
    return out, TL.audio_end

_TG = {}
def track_gain(tr, target=-20.0):
    """曲目响度差近 20 dB（鲁特琴独奏 -32.5 vs 管弦 -12.6）——先各自拉齐到同一积分响度。"""
    if tr not in _TG:
        o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(ROOT/"music"/f"{tr}.mp3"), "-af", "ebur128", "-f", "null", "-"],
                           capture_output=True, text=True).stderr
        I = float(re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1])
        _TG[tr] = 10 ** ((target - I) / 20)
    return _TG[tr]

_TGF = {}
def track_gain_file(p, target=-20.0):
    p = str(p)
    if p not in _TGF:
        o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", p, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
        _TGF[p] = 10 ** ((target - float(re.findall(r"I:\s+(-?[\d.]+) LUFS", o)[-1])) / 20)
    return _TGF[p]

def probe(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                                capture_output=True, text=True).stdout)

def main():
    pic, out = sys.argv[1], sys.argv[2]
    t_to = float(sys.argv[sys.argv.index("--to")+1]) if "--to" in sys.argv else None
    total = probe(pic)
    ass = HERE/"work/subs.ass"; build_ass(ass, t_to)
    secs, aend = section_times()
    inputs = ["-i", str(MP3)]; fl = []; labels = []
    for k, (t0, tr, vol) in enumerate(secs):
        t1 = secs[k+1][0] if k+1 < len(secs) else total
        if t_to is not None and t0 >= t_to: break
        seg = t1 - t0 + 2.0
        vol = vol * track_gain(tr)
        inputs += ["-stream_loop", "-1", "-i", str(ROOT/"music"/f"{tr}.mp3")]
        n = len(labels) + 2
        fl.append(f"[{n}:a]atrim=0:{seg:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=1.5,"
                  f"afade=t=out:st={max(0, seg-2.5):.3f}:d=2.5,volume={vol},adelay={int(t0*1000)}|{int(t0*1000)},"
                  f"aformat=channel_layouts=stereo[m{n}]")
        labels.append(f"[m{n}]")
    # ── 环境声（ambience.json：[[起始锚点, 文件, 素材起点秒, 相对响度dB, 淡入, 淡出, 结束锚点(可选)]]）──
    amb_p = HERE/"ambience.json"
    if amb_p.exists():
        sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import render as R
        TLa = R.Timeline()
        for a, f, off, gdb, fi, fo, *rest in json.load(open(amb_p)):
            t0 = 0.0 if a == "__start__" else TLa.at(a) - 0.1
            t1 = (TLa.at(rest[0]) if rest and rest[0] != "__end__" else total) if rest else total
            TLa.cursor = 0
            seg = max(1.0, t1 - t0); src = ROOT/"assets/sfx"/f
            g = track_gain_file(src) * 10 ** (gdb/20)
            inputs += ["-stream_loop", "-1", "-ss", str(off), "-i", str(src)]
            n = len(labels) + 2
            fl.append(f"[{n}:a]atrim=0:{seg:.3f},asetpts=PTS-STARTPTS,afade=t=in:d={fi},afade=t=out:st={max(0, seg-fo):.3f}:d={fo},"
                      f"volume={g:.4f},adelay={int(t0*1000)}|{int(t0*1000)},aformat=channel_layouts=stereo[m{n}]")
            labels.append(f"[m{n}]")
    fl.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0,acompressor=threshold=0.12:ratio=2.5:attack=200:release=1500:makeup=1,volume=0.32[bgm]")
    fl.append(f"[1:a]aformat=channel_layouts=stereo,apad=whole_dur={total:.3f},asplit=2[vo][key]")
    thr = os.environ.get("DUCK_THR", "0.2"); ratio = os.environ.get("DUCK_RATIO", "1.6")
    fl.append(f"[bgm][key]sidechaincompress=threshold={thr}:ratio={ratio}:attack=60:release=600:makeup=1,asplit=2[duck][stem]")
    fl.append("[vo][duck]amix=inputs=2:normalize=0:duration=longest,loudnorm=I=-16:TP=-1.5:LRA=11[aout]")
    dur = t_to if t_to else total
    subf = str(ass).replace(":", r"\:")
    # 字幕滤镜与 filter_complex 不能同时用 -vf：在 filter_complex 里处理视频
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", pic] + inputs + [
        "-filter_complex", f"[0:v]subtitles={subf}[vout];" + ";".join(fl),
        "-map", "[vout]", "-map", "[aout]",
        "-t", f"{dur:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart", out,
        "-map", "[stem]", "-t", f"{dur:.3f}", str(HERE/"work/bgm_stem.wav")]
    if os.environ.get("AUDIO_ONLY"):
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", pic] + inputs + ["-filter_complex", ";".join(fl),
               "-map", "[stem]", "-t", f"{dur:.3f}", str(HERE/"work/bgm_stem.wav"), "-map", "[aout]", "-t", f"{dur:.3f}", str(HERE/"work/mix_test.wav")]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode: print(r.stderr[-1500:]); sys.exit(1)
    print("✅", out, f"{probe(out):.2f}s")

if __name__ == "__main__":
    main()
