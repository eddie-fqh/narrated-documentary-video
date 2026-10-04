#!/usr/bin/env python3
"""口播稿 → 分段配音 → 响度拉齐 → 拼成成品，并写分段清单（下游的镜头、字幕、配乐时间全部从这份清单和对齐结果来）。
与配音服务无关：用环境变量 TTS_CMD 给出命令模板，脚本对每一段调用一次。
  TTS_CMD='my-tts --voice my-voice --speed 0.95 --in {text_file} --out {out}'
    {text_file} 这一段的文字（UTF-8 文本文件）   {out} 输出音频路径（扩展名由 TTS_OUT_EXT 定，默认 wav）
密钥放在环境变量或权限 600 的 env 文件里由 TTS_CMD 自己读，不要写进命令行和日志。

用法:
  EP_DIR=<ep> tts_segments.py              全部生成（文字没变且文件还在的段直接复用）
  EP_DIR=<ep> tts_segments.py --only 3,4   只重做（重掷）这几段，然后重拼成品
  EP_DIR=<ep> tts_segments.py --splice     不生成，只按现有分段重拼成品
环境变量: SEG_MAX_CHARS(180) SEG_MIN_TAIL(80) SEG_LUFS(-17) TTS_STRIP_CHARS(·•‧) TTS_OUT_EXT(wav) TTS_CONCURRENCY(4) FORCE_TTS=1
<ep>/tts_subs.json = {"原字": "送给 TTS 的字"}：只改送去合成的文字（多音字、总读错的专名），稿子 / 字幕 / 锚点保留原字。
产出: <ep>/audio/segments/seg_NNN.flac + manifest.json，<ep>/audio/narration.mp3；并删掉 gaps.json（停顿要重新插，见 pace.py）。"""
import os, re, sys, json, pathlib, subprocess, tempfile, shlex
from concurrent.futures import ThreadPoolExecutor
EP = pathlib.Path(os.environ["EP_DIR"]).resolve(); SEGD = EP/"audio/segments"; MP3 = EP/"audio/narration.mp3"
MAXC = int(os.environ.get("SEG_MAX_CHARS", "180")); MIN_TAIL = int(os.environ.get("SEG_MIN_TAIL", "80"))
LUFS = float(os.environ.get("SEG_LUFS", "-17")); STRIP = os.environ.get("TTS_STRIP_CHARS", "·•‧"); EXT = os.environ.get("TTS_OUT_EXT", "wav")

def split_text(text, maxc=MAXC):
    """按句号/问号/叹号切句，贪心装进 ≤maxc 字的段；段落（空行）处优先断开。
    末段太短（<MIN_TAIL 字）并回上一段：孤立的短结尾语气容易飘，音色检查也容易不过。"""
    segs, cur = [], ""
    for para in [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]:
        if cur and len(cur) >= maxc*0.5: segs.append(cur); cur = ""
        for sent in re.findall(r"[^。？！\n]+[。？！]?|\n", para):
            if sent == "\n": continue
            if cur and len(cur) + len(sent) > maxc: segs.append(cur); cur = ""
            cur += sent
        if cur: cur += "\n"
    if cur.strip(): segs.append(cur)
    segs = [s.strip() for s in segs if s.strip()]
    if len(segs) > 1 and len(segs[-1]) < MIN_TAIL: segs[-2:] = [segs[-2] + "\n" + segs[-1]]
    return segs

def probe(p):
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True).stdout or 0)

def synth(i, text):
    subs_p = EP/"tts_subs.json"; subs = json.load(open(subs_p)) if subs_p.exists() else {}
    for a, b in subs.items(): text = text.replace(a, b)
    text = text.translate(str.maketrans("", "", STRIP))
    with tempfile.TemporaryDirectory() as d:
        tf = f"{d}/seg.txt"; raw = f"{d}/seg.{EXT}"; open(tf, "w", encoding="utf-8").write(text)
        cmd = os.environ["TTS_CMD"].format(text_file=shlex.quote(tf), out=shlex.quote(raw))
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        if r.returncode or not os.path.exists(raw) or probe(raw) < 0.2:
            raise SystemExit(f"段{i} 合成失败（rc={r.returncode}）：{(r.stderr or r.stdout)[-300:]}")
        # 响度：量积分响度后做线性增益（不用单遍 loudnorm——短片段上它会抽吸），再加限幅
        o = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", raw, "-af", "ebur128", "-f", "null", "-"], capture_output=True, text=True).stderr
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", o); gain = LUFS - float(m[-1]) if m and float(m[-1]) > -60 else 0.0
        out = SEGD/f"seg_{i:03d}.flac"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", raw, "-ar", "44100", "-ac", "1", "-af", f"volume={gain:.2f}dB,alimiter=limit=0.89", str(out)], check=True)
    return out

def splice(texts):
    segs, cur = [], 0.0
    for i, t in enumerate(texts):
        f = SEGD/f"seg_{i:03d}.flac"
        if not f.exists(): raise SystemExit(f"缺分段文件 {f}")
        d = probe(f); segs.append({"index": i, "file": f.name, "text": t, "start": round(cur, 3), "duration": round(d, 3)}); cur += d
    json.dump({"segments": segs}, open(SEGD/"manifest.json", "w"), ensure_ascii=False, indent=1)
    lst = SEGD/"concat.txt"; lst.write_text("".join(f"file '{SEGD/s['file']}'\n" for s in segs))
    tmp = str(MP3) + ".tmp.mp3"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c:a", "libmp3lame", "-b:a", "192k", tmp], check=True)
    os.replace(tmp, MP3); lst.unlink()
    (SEGD/"gaps.json").unlink(missing_ok=True)       # 成品是无停顿的新拼接：pace → align 要重跑
    print(f"{len(segs)} 段，{probe(MP3):.1f}s → {MP3}（接着跑 pace.py、align.py）")

def main():
    SEGD.mkdir(parents=True, exist_ok=True)
    texts = split_text((EP/"script.txt").read_text(encoding="utf-8"))
    man_p = SEGD/"manifest.json"; old = [s["text"] for s in json.load(open(man_p))["segments"]] if man_p.exists() else []
    if "--splice" in sys.argv:
        if old != texts: raise SystemExit("稿子的分段和现有清单不一致，不能只重拼；去掉 --splice 重新生成变了的段")
        return splice(texts)
    only = [int(x) for x in sys.argv[sys.argv.index("--only")+1].split(",")] if "--only" in sys.argv else None
    if only is not None:
        if len(old) != len(texts): raise SystemExit("段数变了（改稿影响了分段边界）：去掉 --only 重新生成")
        todo = only
    else:
        force = os.environ.get("FORCE_TTS") == "1"
        todo = [i for i, t in enumerate(texts) if force or i >= len(old) or old[i] != t or not (SEGD/f"seg_{i:03d}.flac").exists()]
        for f in SEGD.glob("seg_*.flac"):                # 段数变少时清掉多余的旧段（只删本脚本自己生成的、编号超出范围的文件）
            if int(f.stem[4:]) >= len(texts): f.unlink()
    if "TTS_CMD" not in os.environ and todo: raise SystemExit("没有设 TTS_CMD（见本文件开头的说明）")
    print(f"共 {len(texts)} 段，生成 {todo or '无（全部复用）'}", flush=True)
    with ThreadPoolExecutor(int(os.environ.get("TTS_CONCURRENCY", "4"))) as ex:
        for i, f in zip(todo, ex.map(lambda i: synth(i, texts[i]), todo)):
            n = len(re.findall(r"[\u4e00-\u9fff]", texts[i])); d = probe(f); print(f"  段{i:>2} {d:6.1f}s  {n/d:.1f} 字/秒", flush=True)
    splice(texts)

if __name__ == "__main__":
    main()
