#!/usr/bin/env python3
"""按 <ep>/anim/jobs.json（shotlib.anim 写的）渲染全部专属动画，最多 3 路并行。
用法: render_anims.py <ep_dir> <默认页面，如 anim/model3d.html> [--http] [--only scene1,scene2] [--frames]
  --http    页面要加载本地模型/数据时用（以 <ep_dir> 为根起静态服务）
  --frames  只出每段的首/中/尾三张测试帧，不整段渲染（先看再渲）
已存在且比 jobs.json 和页面都新的 mp4 会跳过。"""
import json, sys, os, pathlib, subprocess, urllib.parse
from concurrent.futures import ThreadPoolExecutor
ep = pathlib.Path(sys.argv[1]).resolve(); page0 = sys.argv[2]; HERE = pathlib.Path(__file__).resolve().parent
jobs = json.load(open(ep/"anim/jobs.json")); only = sys.argv[sys.argv.index("--only")+1].split(",") if "--only" in sys.argv else None
def run(item):
    name, q = item; q = dict(q); page = q.pop("_page", page0); out = ep/"anim"/f"{name}.mp4"
    if only and q["scene"] not in only: return f"{name}: 跳过"
    src_m = max((ep/"anim/jobs.json").stat().st_mtime, (ep/page).stat().st_mtime)
    if "--frames" not in sys.argv and out.exists() and out.stat().st_mtime > src_m and not only: return f"{name}: 已是最新"
    cmd = ["bash", str(HERE/"glock.sh"), "anim", "3", sys.executable, str(HERE/"capture.py"),
           page if "--http" in sys.argv else str(ep/page), urllib.parse.urlencode(q), str(out), "30"]
    if "--http" in sys.argv: cmd += ["--http", str(ep)]
    if "--frames" in sys.argv: d = q["dur"]; cmd += ["--frames", f"0.5,{d/2:.1f},{d-0.5:.1f}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return f"{name}: {(r.stdout.strip().splitlines() or [r.stderr[-200:]])[-1]}"
with ThreadPoolExecutor(3) as ex:
    for line in ex.map(run, jobs.items()): print(line, flush=True)
