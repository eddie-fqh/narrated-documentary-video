#!/usr/bin/env python3
"""TTS 不给逐字时间戳 → openai-whisper 逐词时间 + 序列比对，映射回原稿每个字。
（whisper.cpp 快 20 倍，但它的 token 时间在每个转写段开头挤在一起，切镜头会错；对齐仍用 openai-whisper，
 只是它只跑这一步，其余闸门已换 whisper.cpp。）
用法: EP_DIR=<ep> python align.py（需要装了 openai-whisper 的 Python）
输出 <EP>/work/chars.json: [{"c":字,"t0":起,"t1":止,"seg":段号,"pos":位置}]，全局时间 = 各段文件时长累加。"""
import json, difflib, warnings, re, os, sys, subprocess, whisper
warnings.filterwarnings("ignore")
os.chdir(os.environ["EP_DIR"])
segd = "audio/segments"
man = json.load(open(f"{segd}/manifest.json"))
TRUE = {}; cur = 0.0
gaps = json.load(open(f"{segd}/gaps.json")) if os.path.exists(f"{segd}/gaps.json") else {}   # pace.py 插入的段前停顿
for s in man["segments"]:
    cur += float(gaps.get(str(s["index"]), 0.0))
    TRUE[s["index"]] = cur
    cur += float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                 f"{segd}/{s['file']}"], capture_output=True, text=True).stdout)
m = whisper.load_model(os.environ.get("WHISPER_MODEL", "large-v3-turbo"), device=os.environ.get("WHISPER_DEVICE", "cpu"))
PUN = set("，。 \n"); out = []
for s in man["segments"]:
    exp = [(i, c) for i, c in enumerate(s["text"]) if c not in PUN]
    best = None
    for prompt in (None, "以下是普通话的句子。", s["text"][:40]):
        r = m.transcribe(f"{segd}/{s['file']}", language="zh", word_timestamps=True, condition_on_previous_text=False,
                         initial_prompt=prompt)
        heard = []
        for seg in r["segments"]:
            for w in seg.get("words", []):
                t = re.sub(r"[^\w]", "", w["word"]); n = len(t)
                for k, ch in enumerate(t):
                    heard.append((ch, w["start"] + (w["end"]-w["start"])*k/max(n, 1), w["start"] + (w["end"]-w["start"])*(k+1)/max(n, 1)))
        sm = difflib.SequenceMatcher(a=[c for _, c in exp], b=[h[0] for h in heard], autojunk=False)
        rate = sum(n for _, _, n in sm.get_matching_blocks()) / max(len(exp), 1)
        if best is None or rate > best[0]: best = (rate, heard, sm)
        if rate >= 0.93: break
    rate, heard, sm = best
    times = [None] * len(exp)
    for a, b, n in sm.get_matching_blocks():
        for k in range(n): times[a+k] = (heard[b+k][1], heard[b+k][2])
    known = [i for i, t in enumerate(times) if t]
    dur = s["duration"]
    for i in range(len(times)):
        if times[i]: continue
        p = max([k for k in known if k < i], default=None); q = min([k for k in known if k > i], default=None)
        a = times[p][1] if p is not None else 0.0; b = times[q][0] if q is not None else dur
        lo = p if p is not None else -1; hi = q if q is not None else len(times)
        times[i] = (a + (b-a)*(i-lo-0)/(hi-lo), a + (b-a)*(i-lo+1)/(hi-lo))
    for (i, c), (t0, t1) in zip(exp, times):
        out.append({"c": c, "t0": round(TRUE[s["index"]]+t0, 3), "t1": round(TRUE[s["index"]]+t1, 3), "seg": s["index"], "pos": i})
    print(f"段{s['index']:>2} 匹配率 {rate:.0%}", flush=True)
os.makedirs("work", exist_ok=True)
json.dump(out, open("work/chars.json", "w"), ensure_ascii=False)
print("总字数", len(out))
