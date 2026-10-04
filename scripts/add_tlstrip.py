#!/usr/bin/env python3
"""给全集挂顶部时间线条。<ep>/timeline.json: [[年份, 事件说明, 口播里的触发短语], …]
用法: add_tlstrip.py <ep_dir>"""
import json, sys, os, pathlib
ep = pathlib.Path(sys.argv[1]).resolve(); sys.path.insert(0, str(pathlib.Path(__file__).parent)); os.environ["EP_DIR"] = str(ep)
import render as R
spec = json.load(open(ep/"shots.json")); s = spec["shots"]; T = json.load(open(ep/"timeline.json"))
EV = [[y, lab] for y, lab, _ in T]
TL = R.Timeline()
for x in s:
    x["_t"] = 0.0 if x["at"] == "__start__" else TL.at(x["at"]) - 0.12
    x["ov"] = [o for o in x.get("ov", []) if o["kind"] != "tlstrip"]
hits = []
for i, (y, lab, ph) in enumerate(T):
    TL.cursor = 0; hits.append((TL.at(ph), i))
prev = -1
for t, i in sorted(hits):          # 按口播出现顺序挂；进度从上一次显示的年份滑到本次
    y = T[i][0]; j = max(k for k, x in enumerate(s) if x["_t"] <= t); x = s[j]
    src = str(x.get("src", ""))
    if src.startswith("anim/") and not src.startswith("anim/map"):   # 全屏动画自带标题/年表，顶部年表条会压字或重复；地图动画放到底部照挂
        print(y, "→", x["at"], "（全屏动画，跳过）"); prev = i; continue
    x["ov"] = [o for o in x["ov"] if o["kind"] not in ("year", "tlstrip")]
    x["ov"].append({"kind": "tlstrip", "events": EV, "cur": i, "prev": prev, "in": round(max(0.1, t - x["_t"] - 0.3), 2), "dur": 5.5,
                    **({"y": 800} if str(x.get("src", "")).startswith("anim/map") else {})})
    print(y, "→", x["at"]); prev = i
for x in s: x.pop("_t", None)
json.dump(spec, open(ep/"shots.json", "w"), ensure_ascii=False, indent=1)
