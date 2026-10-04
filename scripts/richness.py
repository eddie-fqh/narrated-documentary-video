#!/usr/bin/env python3
"""镜头表丰富度统计：richness.py <ep_dir>（读 shots_src.json 或 shots.json）"""
import sys, json, pathlib, collections
ep = pathlib.Path(sys.argv[1]); p = ep/"shots_src.json" if (ep/"shots_src.json").exists() else ep/"shots.json"
S = json.load(open(p))["shots"]; types = collections.Counter(s["type"] for s in S)
ov = collections.Counter(o["kind"] for s in S for o in s.get("ov", []))
anim = sorted({s["src"] for s in S if s.get("src","").startswith("anim/")})
vids = {s["src"] for s in S if s["type"]=="vid"}
req = {"anim≥2": len(anim)>=2, "vid≥10": len(vids)>=10, "focus≥3": types["focus"]>=3, "split≥2": types["split"]>=2, "grid≥1": types["grid"]>=1,
       "big≥3": ov["big"]>=3, "quote≥1": ov["quote"]>=1, "callout≥4": ov["callout"]>=4, "name≥1": ov["name"]>=1, "chapter≥3": ov["chapter"]>=3}
run = 0; worst = 0
for s in S:
    run = run+1 if s["type"]=="img" else 0; worst = max(worst, run)
print(f"{p.name}: {len(S)} 镜  类型 {dict(types)}  不同视频 {len(vids)}  动画 {anim}")
print("叠加:", dict(ov)); print("最长连续 img:", worst, "(>3 要插别的类型)")
for k, v in req.items(): print(("✅" if v else "❌"), k)
