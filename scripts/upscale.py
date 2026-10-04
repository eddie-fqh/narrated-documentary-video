#!/usr/bin/env python3
"""Real-ESRGAN 放大：把 1000–1600 px 的老版画/老照片拉到 2560 宽，渲染推镜时不糊。

后端是官方预编译的 realesrgan-ncnn-vulkan（xinntao/Real-ESRGAN v0.2.5.0, 20220424-macos，
Apple Silicon 走 Metal/MoltenVK），二进制在 ~/bin/realesrgan-ncnn-vulkan，模型在 ~/bin/models/。
可用 REALESRGAN_BIN / REALESRGAN_MODELS 环境变量改路径。

用法:
  upscale.py <in> <out> [--scale 4] [--target-width 2560] [--anime]
  from upscale import upscale; upscale(src, dst, scale=None, model="realesrgan-x4plus")

逻辑:
  1. 先按 EXIF 方向把图转正（ncnn 不认 EXIF），存成临时 PNG 喂给二进制。
  2. 选倍率：最小的 s∈{2,3,4} 使 w*s ≥ target，不超过 4×。
     注意 x4plus / x4plus-anime 是固定 4× 网络，二进制的 -s 2/3 只是把 4× 结果再用
     便宜滤波缩回去——GPU 耗时一样、画质更差，所以这两个模型永远跑原生 4×，缩放交给
     下一步的 Lanczos 一次完成。只有 realesr-animevideov3 是真的 2/3/4× 多尺度模型。
  3. 结果比 target 宽就用 Lanczos 缩到正好 target 宽；原图 4× 后仍不够宽就保持 w*s，不再插值硬拉。
  4. 输出 JPEG q=92，RGB，EXIF 已应用故不再写入。

模型选择:
  realesrgan-x4plus        照片、油画翻拍、彩色地图——默认
  realesrgan-x4plus-anime  --anime；线刻版画线条更干净，但会抹掉纸纹和细交叉线，更"画"而不"印"
"""
import os, sys, time, shutil, subprocess, tempfile, argparse
from PIL import Image, ImageOps
Image.MAX_IMAGE_PIXELS = None

BIN = os.environ.get("REALESRGAN_BIN", os.path.expanduser("~/bin/realesrgan-ncnn-vulkan"))
MODELS = os.environ.get("REALESRGAN_MODELS", os.path.join(os.path.dirname(BIN), "models"))
MODEL_NAMES = ("realesrgan-x4plus", "realesrgan-x4plus-anime", "realesr-animevideov3")
TARGET = 2560

def available():
    return os.access(BIN, os.X_OK) and os.path.isfile(os.path.join(MODELS, "realesrgan-x4plus.param"))

def pick_scale(width, target=TARGET):
    """最小的 2/3/4 使 width*s ≥ target；都不够就 4。"""
    for s in (2, 3, 4):
        if width * s >= target: return s
    return 4

def upscale(src, dst, scale=None, model="realesrgan-x4plus", face=False, target_width=TARGET, quality=92, verbose=False):
    """放大 src 写到 dst（JPEG）。返回 dict(scale, model, src_size, out_size, sec, skipped)。
    scale=None 自动选；face 在 ncnn 后端不可用（无 GFPGAN），传 True 只会警告。"""
    if model not in MODEL_NAMES: raise ValueError(f"model 必须是 {MODEL_NAMES}")
    if face: print("upscale: ncnn 后端没有 GFPGAN，face=True 忽略", file=sys.stderr)
    if not available(): raise RuntimeError(f"找不到 realesrgan-ncnn-vulkan 或模型: {BIN} / {MODELS}")
    t0 = time.time()
    im = Image.open(src); im = ImageOps.exif_transpose(im)   # 1. 转正
    w, h = im.size; src_size = (w, h)
    if w >= target_width:                                   # 已经够宽：不放大，只统一到 target
        if w > target_width: im = im.resize((target_width, round(h * target_width / w)), Image.LANCZOS)
        im.convert("RGB").save(dst, "JPEG", quality=quality)
        return {"scale": 1, "model": None, "src_size": src_size, "out_size": im.size, "sec": time.time() - t0, "skipped": True}
    s = scale or pick_scale(w, target_width)
    if s not in (2, 3, 4): raise ValueError("scale 只能是 2/3/4")
    native = s if model == "realesr-animevideov3" else 4    # 2. x4plus 系列永远原生 4×
    tmpd = tempfile.mkdtemp(prefix="upscale_")
    try:
        tin = os.path.join(tmpd, "in.png"); tout = os.path.join(tmpd, "out.png")
        im.convert("RGB").save(tin, "PNG", compress_level=1)
        cmd = [BIN, "-i", tin, "-o", tout, "-n", model, "-s", str(native), "-m", MODELS]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0 or not os.path.exists(tout):
            raise RuntimeError(f"realesrgan 失败 rc={r.returncode}: {r.stderr[-400:]}")
        if verbose: print(r.stderr.strip().splitlines()[0], file=sys.stderr)
        out = Image.open(tout).convert("RGB")
        want = min(target_width, w * s)                      # 3. 缩到 target；4× 仍不够就 w*s
        if out.width != want: out = out.resize((want, round(out.height * want / out.width)), Image.LANCZOS)
        out.save(dst, "JPEG", quality=quality)               # 4. q=92
        return {"scale": s, "model": model, "src_size": src_size, "out_size": out.size, "sec": time.time() - t0, "skipped": False}
    finally:
        shutil.rmtree(tmpd, ignore_errors=True)

def maybe_upscale(path, min_width, target_width=TARGET):
    """给下载步骤用的钩子：path 比 min_width 窄就放大到 target_width，原图留作 <stem>.orig.jpg。
    任何失败都不动 path（打印警告），保证下载流程本身不变。返回 True 表示放大了。"""
    try:
        with Image.open(path) as im: w = ImageOps.exif_transpose(im).width
        if w >= min_width: return False
        stem, _ = os.path.splitext(path); orig = stem + ".orig.jpg"
        if not os.path.exists(orig): shutil.copy2(path, orig)
        tmp = stem + ".upscaling.jpg"
        r = upscale(orig, tmp, target_width=target_width)
        os.replace(tmp, path)
        print(f"  upscale {os.path.basename(path)} {r['src_size']}→{r['out_size']} ×{r['scale']} {r['sec']:.1f}s", flush=True)
        return True
    except Exception as e:
        print(f"  upscale 跳过 {path}: {str(e)[:120]}", file=sys.stderr, flush=True); return False

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("src"); ap.add_argument("dst")
    ap.add_argument("--scale", type=int, choices=(2, 3, 4), default=None, help="不给则自动选")
    ap.add_argument("--target-width", type=int, default=TARGET)
    ap.add_argument("--model", choices=MODEL_NAMES, default="realesrgan-x4plus")
    ap.add_argument("--anime", action="store_true", help="用 realesrgan-x4plus-anime（线刻版画）")
    ap.add_argument("--face", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    a = ap.parse_args()
    r = upscale(a.src, a.dst, scale=a.scale, model="realesrgan-x4plus-anime" if a.anime else a.model,
                face=a.face, target_width=a.target_width, verbose=a.verbose)
    print(f"{a.src}: {r['src_size']} → {r['out_size']}  scale×{r['scale']} model={r['model']}  {r['sec']:.1f}s" + ("  (已够宽，未放大)" if r["skipped"] else ""))
