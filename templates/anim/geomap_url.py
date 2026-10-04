#!/usr/bin/env python3
"""把 geomap.html 的参数（含本地 GeoJSON 路线文件）拼成 capture.py 用的 query 字符串。
file:// 页面不能 fetch 本地文件，所以路线要内联进 route=。

用法:
  python3 geomap_url.py dur=8 c0=105,35 z0=3.4 c1=116.3972,39.9163 z1=15.6 p1=62 b1=-25 \
      --route path.geojson --pts "故宫:116.3972:39.9163:@6.4"
  → 打印 "dur=8&c0=...&route=116.39,39.91;..."，直接作为 capture.py 的第二个参数。
"""
import json, sys, urllib.parse

def route_param(path, every=1):
    j = json.load(open(path))
    f = j["features"][0] if j.get("type") == "FeatureCollection" else j
    g = f["geometry"] if f.get("type") == "Feature" else f
    coords = [c for part in g["coordinates"] for c in part] if g["type"] == "MultiLineString" else g["coordinates"]
    coords = coords[::every] if every > 1 else coords
    return ";".join(f"{x:.5f},{y:.5f}" for x, y, *_ in coords)

def main(argv):
    kv, i = [], 0
    while i < len(argv):
        a = argv[i]
        if a == "--route": kv.append(("route", route_param(argv[i+1]))); i += 2
        elif a == "--every": i += 2          # 处理在下面
        elif a == "--pts": kv.append(("pts", argv[i+1])); i += 2
        elif "=" in a: kv.append(tuple(a.split("=", 1))); i += 1
        else: sys.exit(f"bad arg {a}")
    if "--every" in argv:
        n = int(argv[argv.index("--every")+1]); kv = [(k, route_param(argv[argv.index("--route")+1], n) if k == "route" else v) for k, v in kv]
    print(urllib.parse.urlencode(kv, safe=",;:@|#"))

if __name__ == "__main__":
    main(sys.argv[1:])
