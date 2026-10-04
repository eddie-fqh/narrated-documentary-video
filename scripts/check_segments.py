#!/usr/bin/env python3
"""配音分段的「内容」验收（whisper.cpp 转写）。声学指标都正常的段也可能念错——这三项专抓那一类：
  · 口头语：带口语提示转写，出现原文没有的 呃/嗯/啊 → 不合格
  · 截断：字/秒 > 7 = 后半段没念出来
  · 数字：<ep>/numbers.json [["四百一十四","414"],…] 里的数字必须在转写里找得到；数字发音 < 0.55s 视为吞音
用法:
  EP_DIR=<ep> check_segments.py [段号 …]            只检查（不给段号 = 全部）；有不合格则退出码 1
  EP_DIR=<ep> check_segments.py --reroll 3 [段号 …] 不合格的段调 tts_segments.py --only 重掷，最多 3 轮
环境变量: WHISPER_CPP_MODEL（ggml 模型路径，默认 ~/models/ggml-large-v3-turbo-q5_0.bin）  WHISPER_CPP_BIN（默认 whisper-cli）
注意：数字闸门会误报（「2米02 / 2.02米」「4成 / 40%」这类多种写法）。同一个数字连掷 3 次都不过，
先看转写到底是什么——多半该改稿子的读法或补 numbers.json，而不是继续掷；白掷只会把音高越掷越偏。"""
import os, re, sys, json, pathlib, subprocess, tempfile, shutil
EP = pathlib.Path(os.environ["EP_DIR"]).resolve(); SEGD = EP/"audio/segments"
GGML = os.environ.get("WHISPER_CPP_MODEL", str(pathlib.Path.home()/"models/ggml-large-v3-turbo-q5_0.bin")); BIN = os.environ.get("WHISPER_CPP_BIN", "whisper-cli")
FILLERS = set("呃嗯额啊哦唔")
NUMS = json.load(open(EP/"numbers.json")) if (EP/"numbers.json").exists() else []
D = dict(zip("零一二三四五六七八九", "0123456789")); NUMCH = "零一二两三四五六七八九十百千万"

def probe(f):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", f], capture_output=True, text=True).stdout or 0)

def whisper_cpp(path, prompt="以下是普通话的句子。"):
    """返回 (text, tokens[{text, offsets:{from,to}}])"""
    d = tempfile.mkdtemp(prefix="wcpp_"); wav = f"{d}/a.wav"
    try:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ar", "16000", "-ac", "1", wav], check=True)
        subprocess.run([BIN, "-m", GGML, "-l", "zh", "-f", wav, "-ojf", "-of", f"{d}/o", "--prompt", prompt, "-nt"], capture_output=True, check=True)
        j = json.loads(open(f"{d}/o.json", "rb").read().decode("utf-8", "replace"))   # 偶尔把一个汉字拆在两个 token 里，输出非法 UTF-8
    finally:
        shutil.rmtree(d, ignore_errors=True)
    segs = j["transcription"]; toks = [t for s in segs for t in s.get("tokens", []) if not t["text"].startswith("[_")]
    return "".join(s["text"] for s in segs), toks

def cuts(f, maxlen=24.0):
    """在停顿处切片，每片 ≤ maxlen 秒（whisper 对 >30s 的片段会整句跳读）。返回 [(start, end)]"""
    dur = probe(f)
    if dur <= maxlen: return [(0.0, dur)]
    err = subprocess.run(["ffmpeg", "-v", "info", "-i", f, "-af", "silencedetect=n=-35dB:d=0.2", "-f", "null", "-"], capture_output=True, text=True).stderr
    sil, st = [], None
    for line in err.splitlines():
        m = re.search(r"silence_start: ([\d.]+)", line)
        if m: st = float(m.group(1))
        m = re.search(r"silence_end: ([\d.]+)", line)
        if m and st is not None: sil.append((st + float(m.group(1)))/2); st = None
    out, a = [], 0.0
    while dur - a > maxlen:
        cand = [c for c in sil if a + 6 < c <= a + maxlen]; b = cand[-1] if cand else a + maxlen
        out.append((a, b)); a = b
    out.append((a, dur)); return out

def wchunks(f, prompt=None):
    """分片转写，返回 (全文, tokens[绝对时间 ms])"""
    texts, toks = [], []
    for a, b in cuts(f):
        d = tempfile.mkdtemp(prefix="wch_"); piece = f"{d}/p.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", f, "-ar", "16000", "-ac", "1", piece], check=True)
        tx, tk = whisper_cpp(piece, prompt) if prompt else whisper_cpp(piece)
        for t in tk: t["offsets"] = {"from": t["offsets"]["from"] + a*1000, "to": t["offsets"]["to"] + a*1000}
        texts.append(tx); toks += tk; shutil.rmtree(d, ignore_errors=True)
    return "".join(texts), toks

def cn(t):   # 「八十」→80，「四十八」→48，「一百八十九」→189，逐字读的「一三四九」→1349
    if all(c in D for c in t): return "".join(D[c] for c in t)
    tot, sect, num = 0, 0, 0
    for ch in t:
        if ch in D: num = int(D[ch])
        elif ch in "十百千": sect += (num or 1)*{"十": 10, "百": 100, "千": 1000}[ch]; num = 0
        elif ch == "万": tot += (sect + num)*10000; sect = num = 0
    return str(tot + sect + num)

def check(s):
    f = str(SEGD/s["file"]); probs = []
    _, toks = wchunks(f, prompt="呃，嗯，那个，就是说，啊，我们今天呢，呃，来聊一聊。")
    fill = [(round(t["offsets"]["from"]/1000, 2), t["text"].strip()) for t in toks
            if t["text"].strip() and set(t["text"].strip()) <= FILLERS and not any(c in s["text"] for c in t["text"].strip())]
    if fill: probs.append(f"口头语 {fill}")
    dur = probe(f); n = len(re.findall(r"[\u4e00-\u9fff]", s["text"]))
    if dur and n/dur > 7.0: probs.append(f"疑似截断：{n} 字只有 {dur:.1f}s（{n/dur:.1f} 字/秒）")
    if any(zh in s["text"] for zh, _ in NUMS):
        _, t2 = wchunks(f)
        w2 = [{"word": t["text"], "start": t["offsets"]["from"]/1000, "end": t["offsets"]["to"]/1000} for t in t2]
        ni = [k for k, w in enumerate(w2) if any(ch.isdigit() for ch in w["word"])]
        if ni:                                            # 每个数字串单独量时长
            groups, cur = [], [ni[0]]
            for k in ni[1:]:
                if k == cur[-1] + 1: cur.append(k)
                else: groups.append(cur); cur = [k]
            groups.append(cur)
            for g in groups:
                a = w2[g[0]]["start"]; j = g[-1] + 1; b = w2[j]["start"] if j < len(w2) else w2[g[-1]]["end"]
                txt = "".join(w2[k]["word"] for k in g)
                if not any(key in txt for _, key in NUMS): continue        # 只查目标数字
                if b - a <= 0.05: continue                                 # whisper.cpp 的 token 时间偶尔挤在一起，不计
                if b - a < 0.55: probs.append(f"数字 {txt} 只有 {b-a:.2f}s（疑似吞音）")
        heard = "".join(w["word"] for w in w2).replace(" ", "")
        norm = re.sub(r"[零一二三四五六七八九十百千][零一二三四五六七八九十百千万]*", lambda m: cn(m.group(0)), heard)   # 单独的「万」不当数字
        norm = re.sub(r"(\d+)万", lambda m: str(int(m.group(1))*10000), norm)
        for zh, dg in NUMS:                               # 转写可能是「八十」也可能是「80」，统一成数字再比
            alone = re.search("(?<![" + NUMCH + "])" + re.escape(zh) + "(?![" + NUMCH + "])", s["text"])   # 「八十」不能是「一百八十九」的一部分
            dgn = re.sub(r"(\d+)万", lambda m: str(int(m.group(1))*10000), dg)
            digs = re.findall(r"\d+(?:\.\d+)?", dgn)      # 单位和连接词写法多变，只核对数字本身
            if alone and dg not in norm and dgn not in norm and zh not in heard and not (digs and all(d in norm for d in digs)):
                probs.append(f"原文有 {zh}，转写里没有 {dg}（读错/吞音）")
    return probs

def run(idx):
    man = json.load(open(SEGD/"manifest.json"))["segments"]; bad = []
    for s in man:
        if idx and s["index"] not in idx: continue
        pr = check(s); print(f"段{s['index']:>2} {'✅' if not pr else '❌ ' + str(pr)}", flush=True)
        if pr: bad.append(s["index"])
    return bad

if __name__ == "__main__":
    args = sys.argv[1:]; rounds = 0
    if "--reroll" in args: k = args.index("--reroll"); rounds = int(args[k+1]); del args[k:k+2]
    idx = [int(x) for x in args]
    bad = run(idx)
    for r in range(rounds):
        if not bad: break
        print(f"── 第 {r+1} 轮重掷 {bad} ──", flush=True)
        subprocess.run([sys.executable, str(pathlib.Path(__file__).with_name("tts_segments.py")), "--only", ",".join(map(str, bad))], check=True)
        bad = run(bad)
    print("不合格:", bad or "无"); sys.exit(1 if bad else 0)
