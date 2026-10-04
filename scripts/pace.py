#!/usr/bin/env python3
"""给配音加呼吸：按段落在段与段之间插入真实停顿，重拼成品 mp3。
默认段间 0.6s；章节开头（以 PACE_CHAPTER_PREFIXES 里任一前缀起头的段）前 1.2s。停顿用低电平噪声（不是数字零，避免拼接咔嗒感）。
写 <segments>/gaps.json = {index: gap_before_sec}，align.py 据此修正各段的真实起点。
只能在「刚拼好、还没插过停顿」的成品上跑一次（tts_segments.py 每次重拼都会删掉 gaps.json）。
用法: EP_DIR=... pace.py   环境变量 PACE_GAP(默认0.6) PACE_CHAPTER_GAP(默认1.2) PACE_CHAPTER_PREFIXES(逗号分隔)"""
import os, json, subprocess, tempfile, pathlib
EP = pathlib.Path(os.environ["EP_DIR"]); segd = EP/"audio/segments"
MP3 = EP/"audio/narration.mp3"
GAP = float(os.environ.get("PACE_GAP", "0.6")); CGAP = float(os.environ.get("PACE_CHAPTER_GAP", "1.2"))
man = json.load(open(segd/"manifest.json")); segs = man["segments"]
PREFIXES = tuple(x for x in os.environ.get("PACE_CHAPTER_PREFIXES", "好，|先说|再说|最后，|第一，|第二，|第三，|第四，").split("|") if x)
def is_chapter(t): return t.lstrip().startswith(PREFIXES)
if (segd/"gaps.json").exists(): raise SystemExit("gaps.json 已存在：这份成品已经插过停顿。先用 tts_segments.py 重拼再跑 pace。")
gaps = {}
for k, s in enumerate(segs):
    gaps[str(s["index"])] = 0.0 if k == 0 else (CGAP if is_chapter(s["text"]) else GAP)
json.dump(gaps, open(segd/"gaps.json","w"))
with tempfile.TemporaryDirectory() as d:
    # 不从原始分段重拼（会丢母带/响度处理），而是把成品 mp3 按各段累计时长切开，在切点插入停顿
    src = f"{d}/src.wav"; subprocess.run(["ffmpeg","-v","error","-y","-i",str(MP3),"-ar","44100","-ac","1",src],check=True)
    def dur(f): return float(subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f],capture_output=True,text=True).stdout)
    def noise(sec, out):
        subprocess.run(["ffmpeg","-v","error","-y","-f","lavfi","-i",f"anoisesrc=color=pink:amplitude=0.0006:d={sec}:r=44100","-ac","1","-af","afade=t=in:d=0.03,afade=t=out:st={:.3f}:d=0.03".format(max(0,sec-0.03)),out],check=True)
    parts = []; cur = 0.0; total = dur(src)
    for k, s in enumerate(segs):
        L = dur(str(segd/s["file"])); g = gaps[str(s["index"])]
        if g > 0: n = f"{d}/g{k}.wav"; noise(g, n); parts.append(n)
        w = f"{d}/s{k}.wav"; end = total if k == len(segs)-1 else min(total, cur+L)
        subprocess.run(["ffmpeg","-v","error","-y","-ss",f"{cur:.4f}","-to",f"{end:.4f}","-i",src,"-c:a","pcm_s16le",w],check=True); parts.append(w); cur = end
    lst = f"{d}/list.txt"; open(lst,"w").write("".join(f"file '{p}'\n" for p in parts))
    tmp = str(MP3)+".pace.mp3"
    subprocess.run(["ffmpeg","-v","error","-y","-f","concat","-safe","0","-i",lst,"-c:a","libmp3lame","-b:a","192k",tmp],check=True)
    os.replace(tmp, MP3)
tot = sum(gaps.values()); print(f"pace: {len(segs)} 段，插入停顿共 {tot:.1f}s（段间 {GAP}s，章节前 {CGAP}s）")
