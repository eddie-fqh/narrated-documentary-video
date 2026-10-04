#!/usr/bin/env python3
"""逐帧确定性渲染 HTML 动画 → mp4。页面约定：加载完设 window.ready=true，暴露 window.renderAt(t)（t 为秒；可返回 Promise）。
不录屏、不依赖实时播放：第 i 帧就是 renderAt(i/fps) 的截图，所以结果可复现、不掉帧。

用法: capture.py <page.html> "scene=a&dur=12" <out.mp4> [fps=30] [--frames t1,t2,…] [--http <根目录>] [--size 1920x1080]
  --frames  只出这几个时刻的测试帧（<out>_t1.0.jpg …），先看一眼再整段渲染
  --http    页面要 fetch 本地文件（glb 模型、GeoJSON）时用：在本机起只读静态服务，<page.html> 写成相对根目录的路径
dur 从 query 里读（默认 10）。动画时长要比它所在的镜头略长（见 references/animation.md）。
无头浏览器 + 软件渲染很吃 CPU：并行别超过 3 路（bash glock.sh anim 3 python3 capture.py …）。"""
import sys, subprocess, pathlib, time, threading, functools, http.server, socketserver
from playwright.sync_api import sync_playwright
def opt(name, default=None):
    return sys.argv[sys.argv.index(name)+1] if name in sys.argv else default
page_path, query, out = sys.argv[1], sys.argv[2], sys.argv[3]
fps = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else 30
test = [float(x) for x in opt("--frames").split(",")] if opt("--frames") else None
Wd, Ht = (int(x) for x in opt("--size", "1920x1080").split("x"))
dur = float(dict(kv.split("=", 1) for kv in query.split("&") if "=" in kv).get("dur", "10"))
srv = None
if opt("--http"):
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a): pass
    srv = socketserver.TCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(pathlib.Path(opt("--http")).resolve())))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/{page_path}?{query}"
else:
    url = pathlib.Path(page_path).resolve().as_uri() + "?" + query
try:
    with sync_playwright() as p:
        b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
        pg = b.new_page(viewport={"width": Wd, "height": Ht})
        pg.on("pageerror", lambda e: print("pageerror:", str(e)[:300], flush=True))
        pg.goto(url); pg.wait_for_function("window.ready===true", timeout=180000)
        if test:
            for t in test:
                pg.evaluate(f"window.renderAt({t})"); pg.screenshot(path=f"{out}_t{t:.1f}.jpg", type="jpeg", quality=88)
            print("test frames ok")
        else:
            n = int(round(dur*fps)); t0 = time.time()
            ff = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "image2pipe", "-framerate", str(fps), "-c:v", "png", "-i", "-",
                                   "-c:v", "libx264", "-preset", "medium", "-crf", "14", "-pix_fmt", "yuv420p", out], stdin=subprocess.PIPE)
            for i in range(n):
                pg.evaluate(f"window.renderAt({i/fps})"); ff.stdin.write(pg.screenshot(type="png"))
            ff.stdin.close(); ff.wait(); print(f"{out}: {n} frames in {time.time()-t0:.0f}s")
        b.close()
finally:
    if srv: srv.shutdown()
