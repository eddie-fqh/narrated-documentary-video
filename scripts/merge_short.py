#!/usr/bin/env python3
"""把过短镜头并入邻居，保证节奏舒缓。用法: merge_short.py <ep_dir> [min_s=3.0]
规则：动画镜头不动；章节卡镜头太短 → 章节卡挪到下一镜头开头，锚点前移；其它短镜头 → 删除，叠层挪到上一镜头（按时间偏移）。"""
import json, sys, os, pathlib
ep = pathlib.Path(sys.argv[1]).resolve(); MIN = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
sys.path.insert(0, str(pathlib.Path(__file__).parent)); os.environ["EP_DIR"] = str(ep)
import render as R
spec = json.load(open(ep/"shots.json")); s = spec["shots"]
json.dump(spec, open(ep/"shots_premerge.json", "w"), ensure_ascii=False, indent=1)
def times():
    TL = R.Timeline(); end = TL.audio_end + spec.get("tail", 4.5)
    for x in s: x["_t"] = 0.0 if x["at"] == "__start__" else TL.at(x["at"])
    for i, x in enumerate(s): x["_d"] = (s[i+1]["_t"] if i+1 < len(s) else end) - x["_t"]
changed = True; n0 = len(s)
while changed:
    changed = False; times()
    for i, x in enumerate(s):
        if i == 0 or x["_d"] >= MIN or str(x.get("src", "")).startswith("anim/"): continue
        ov = x.get("ov", [])
        if any(o["kind"] == "chapter" for o in ov) and i+1 < len(s):
            nx = s[i+1]; nx["at"] = x["at"]; nx["ov"] = [dict(o, **{"in": o.get("in", 0)}) for o in ov] + \
                [dict(o, **{"in": o.get("in", 0) + x["_d"]}) for o in nx.get("ov", [])]
            for k in ("tr", "xf"):
                if k in x: nx[k] = x[k]
        else:
            ID = ("art", "name", "callout")
            has = lambda y: any(o["kind"] in ID for o in y.get("ov", []))
            pv = s[i-1]; off = x["_t"] - pv["_t"]
            nx = s[i+1] if i+1 < len(s) else None
            if has(x) and not has(pv) and not any(o["kind"] in ("chapter", "title") for o in pv.get("ov", [])) and i-1 > 0:
                # 短镜头带身份叠层：让它接管上一镜头的时段，上一镜头的通用叠层并过来
                x["at"] = pv["at"]
                x["ov"] = pv.get("ov", []) + [dict(o, **{"in": o.get("in", 0) + off}) for o in ov]
                for k in ("tr", "xf"):
                    if k in pv: x[k] = pv[k]
                del s[i-1]; changed = True; break
            if has(x) and nx is not None and not has(nx) and not str(nx.get("src", "")).startswith("anim/") \
               and not any(o["kind"] in ("chapter", "title") for o in nx.get("ov", [])):
                # 否则把自己的时段让给下一镜头的图，叠层留给自己的图 → 等价于：下一镜头删掉，本镜头延长
                x["ov"] = ov + [dict(o, **{"in": o.get("in", 0) + x["_d"]}) for o in nx.get("ov", [])]
                del s[i+1]; changed = True; break
            keep = [dict(o, **{"in": o.get("in", 0) + off}) for o in ov if o["kind"] not in ("chapter", "title") + ID]
            pv["ov"] = pv.get("ov", []) + keep
        del s[i]; changed = True; break
for x in s: x.pop("_t", None); x.pop("_d", None)
json.dump(spec, open(ep/"shots.json", "w"), ensure_ascii=False, indent=1)
print(f"{n0} → {len(s)} shots")
