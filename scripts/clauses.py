#!/usr/bin/env python3
"""把口播稿按标点切成短句，列出每句开始时间与时长（用于排镜头）。用法: clauses.py <ep_dir>"""
import json, sys, re, pathlib
ep = pathlib.Path(sys.argv[1]); c = json.load(open(ep/"work/chars.json"))
segd = ep/"audio/segments"; man = json.load(open(segd/"manifest.json"))
text = ""; mp = []
for s in man["segments"]:
    for i, ch in enumerate(s["text"]): text += ch; mp.append((s["index"], i))
by = {(x["seg"], x["pos"]): x for x in c}
def t_at(k):
    for j in range(k, min(k+8, len(mp))):
        if mp[j] in by: return by[mp[j]]["t0"]
    return None
parts = [(m.start(), m.group()) for m in re.finditer(r"[^，。！？、；：\n]+[，。！？、；：]?", text)]
rows = []
for k, (st, p) in enumerate(parts):
    t = t_at(st); rows.append((t, p.strip()))
for i, (t, p) in enumerate(rows):
    nt = rows[i+1][0] if i+1 < len(rows) else None
    d = (nt - t) if (t is not None and nt is not None) else 0
    print(f"{t:7.2f} {d:5.2f}  {p}")
