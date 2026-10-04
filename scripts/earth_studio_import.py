#!/usr/bin/env python3
"""Google Earth Studio 导出素材入库。

Earth Studio（earth.google.com/studio）不能自动化：用户在 Chrome 里录好机位、导出
帧序列（JPEG/PNG）或 MP4（云渲染）。本脚本把导出物整理成管线可用的 1080p 素材：

  1. 帧率：优先 --fps；其次导出目录里的工程 JSON（.esp 的 settings.frameRate，
     或 3D 跟踪 JSON 的 frameRate）；MP4 用 ffprobe；都没有则 30。
  2. 拼成 1920x1080 h264 → assets/video/ges_<name>.mp4，
     非 16:9 的默认居中裁切（--fit pad 改为加黑边）。
  3. 右下角烧入署名小字（Google Earth + 数据提供方），--no-burn 关闭。
     Earth Studio 渲染时自带的水印才是正式署名；裁切可能切掉它，所以默认补烧一份。
  4. 在 assets/video/credits_ges.json 追加一条记录（键 = 文件名），供片尾字幕使用。

用法：
  python3 earth_studio_import.py <导出目录或.mp4> --name city_orbit \\
      [--providers "Image © 2026 Airbus, Maxar Technologies"] [--fps 30] \\
      [--fit crop|pad] [--corner br|bl|tr|tl] [--no-burn] [--force] [--dry-run]

输出目录：$PROJECT_DIR/assets/video（默认当前目录下的 assets/video）。
署名要求与使用边界见 references/aerial-and-maps.md。
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = os.path.abspath(os.environ.get("PROJECT_DIR", "."))
OUT_DIR = os.path.join(ROOT, "assets", "video")
CREDITS_PATH = os.path.join(OUT_DIR, "credits_ges.json")

W, H = 1920, 1080
DEFAULT_FPS = 30
FRAME_EXT = (".jpg", ".jpeg", ".png")

# 署名文字。Earth Studio 文档要求对 "Google Earth" 与第三方影像提供方署名，
# 并且文字要与渲染图上出现的一致（references/aerial-and-maps.md 有出处）。
ATTRIBUTION_MAIN = "Google Earth"
DOC_URLS = {
    "attribution": "https://earth.google.com/studio/docs/attribution/",
    "faq": "https://www.google.com/earth/studio/faq/",
    "geo_guidelines": "https://about.google/brand-resource-center/products-and-services/geo-guidelines/",
    "earth_terms": "https://www.google.com/help/terms_maps-earth/",
}

FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/System/Library/Fonts/SFNS.ttf",
    "/Library/Fonts/Arial.ttf",
]


def log(*a):
    print("[ges]", *a, file=sys.stderr)


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def slug(name: str) -> str:
    s = re.sub(r"[^A-Za-z0-9_\-一-鿿]+", "_", name.strip()).strip("_")
    return s or "clip"


# ---------- 帧率探测 ----------

def _find_fps_in_json(obj, depth=0):
    """递归找 frameRate / fps 键（.esp: settings.frameRate；3D tracking: frameRate）。"""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k in ("frameRate", "frame_rate", "fps"):
            v = obj.get(k)
            if isinstance(v, (int, float)) and 1 <= v <= 240:
                return float(v)
        for v in obj.values():
            r = _find_fps_in_json(v, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for v in obj[:50]:
            r = _find_fps_in_json(v, depth + 1)
            if r:
                return r
    return None


def detect_project_fps(folder: str):
    """在导出目录（及上一级）里找 .esp / .json 工程文件，返回 (fps, path) 或 (None, None)。"""
    cands = []
    for d in (folder, os.path.dirname(folder.rstrip("/"))):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".esp", ".json")) and not f.startswith("credits"):
                cands.append(os.path.join(d, f))
    for p in cands:
        try:
            with open(p, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            continue
        fps = _find_fps_in_json(data)
        if fps:
            return fps, p
    return None, None


def ffprobe_fps(path: str):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=r_frame_rate,avg_frame_rate", "-of", "json", path],
            capture_output=True, text=True, check=True).stdout
        st = json.loads(out)["streams"][0]
        for k in ("avg_frame_rate", "r_frame_rate"):
            n, _, d = st.get(k, "0/0").partition("/")
            if d and float(d) and float(n):
                return float(n) / float(d)
    except Exception as e:  # noqa: BLE001
        log("ffprobe 失败：", e)
    return None


# ---------- 输入整理 ----------

def collect_frames(folder: str):
    fs = [f for f in os.listdir(folder) if f.lower().endswith(FRAME_EXT) and not f.startswith(".")]
    fs.sort(key=natural_key)
    return [os.path.join(folder, f) for f in fs]


def probe_size(path: str):
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
             "stream=width,height", "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True).stdout.strip()
        w, h = out.split(",")[:2]
        return int(w), int(h)
    except Exception:
        return None


def pick_font():
    for f in FONT_CANDIDATES:
        if os.path.exists(f):
            return f
    return None


def esc_drawtext_path(p: str) -> str:
    # drawtext 的选项值里 ':' 和 '\' 需要转义
    return p.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


# ---------- 滤镜 ----------

def build_vf(fit: str, burn: bool, corner: str, caption_file: str | None, font: str | None):
    # out_range=tv：Earth Studio 的 JPEG 是全范围（yuvj420p），统一转成有限范围再编码
    if fit == "pad":
        vf = [f"scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos:out_range=tv",
              f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2:color=black"]
    else:
        vf = [f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos:out_range=tv",
              f"crop={W}:{H}"]
    vf += ["setsar=1"]
    if burn and caption_file:
        m = 28  # 边距
        x = {"br": f"w-tw-{m}", "tr": f"w-tw-{m}", "bl": str(m), "tl": str(m)}[corner]
        y = {"br": f"h-th-{m}", "bl": f"h-th-{m}", "tr": str(m), "tl": str(m)}[corner]
        opts = [f"textfile={esc_drawtext_path(caption_file)}", "fontsize=22", "fontcolor=white@0.92",
                "box=1", "boxcolor=black@0.45", "boxborderw=10", "line_spacing=4",
                f"x={x}", f"y={y}"]
        if font:
            opts.insert(0, f"fontfile={esc_drawtext_path(font)}")
        vf.append("drawtext=" + ":".join(opts))
    vf.append("format=yuv420p")
    return ",".join(vf)


# ---------- 主流程 ----------

def import_export(src: str, name: str, fps: float | None = None, providers: str = "",
                  fit: str = "crop", corner: str = "br", burn: bool = True,
                  force: bool = False, dry_run: bool = False, bitrate: str = "12M") -> dict:
    src = os.path.abspath(src)
    if not os.path.exists(src):
        raise SystemExit(f"找不到输入：{src}")
    name = slug(name)
    out = os.path.join(OUT_DIR, f"ges_{name}.mp4")
    if os.path.exists(out) and not force and not dry_run:
        raise SystemExit(f"已存在 {out}；加 --force 覆盖")

    is_dir = os.path.isdir(src)
    project_json = None
    frames: list[str] = []
    if is_dir:
        frames = collect_frames(src)
        if not frames:
            raise SystemExit(f"目录里没有 JPEG/PNG 帧：{src}")
        if fps is None:
            fps, project_json = detect_project_fps(src)
            if fps:
                log(f"帧率 {fps:g} 来自工程文件 {project_json}")
        if fps is None:
            fps = DEFAULT_FPS
            log(f"没找到工程 JSON，帧率默认 {fps}")
        n_frames = len(frames)
        size = probe_size(frames[0])
    else:
        if not src.lower().endswith((".mp4", ".mov", ".m4v", ".webm")):
            raise SystemExit("输入要么是帧目录，要么是 MP4/MOV")
        if fps is None:
            fps, project_json = detect_project_fps(os.path.dirname(src))
            if fps:
                log(f"帧率 {fps:g} 来自工程文件 {project_json}")
        if fps is None:
            fps = ffprobe_fps(src) or DEFAULT_FPS
            log(f"帧率 {fps:g}（ffprobe/默认）")
        n_frames = None
        size = probe_size(src)

    if size:
        ar = size[0] / size[1]
        if abs(ar - 16 / 9) > 0.02:
            log(f"源尺寸 {size[0]}x{size[1]}（{ar:.3f}）不是 16:9，按 --fit {fit} 处理；"
                f"{'裁切可能切掉 Earth Studio 自带水印，已补烧署名' if burn else '注意：--no-burn 且裁切，请确认水印仍在画面里'}")

    tmpdir = tempfile.mkdtemp(prefix="ges_")
    caption_file = None
    caption_lines = [ATTRIBUTION_MAIN] + ([providers.strip()] if providers.strip() else [])
    if burn:
        caption_file = os.path.join(tmpdir, "caption.txt")
        with open(caption_file, "w", encoding="utf-8") as fh:
            fh.write("\n".join(caption_lines))

    cmd = ["ffmpeg", "-hide_banner", "-y", "-loglevel", "error", "-stats"]
    list_file = None
    if is_dir:
        list_file = os.path.join(tmpdir, "frames.txt")
        with open(list_file, "w", encoding="utf-8") as fh:
            for p in frames:
                fh.write(f"file '{p.replace(chr(39), chr(39) + chr(92) + chr(39) + chr(39))}'\n")
                fh.write(f"duration {1 / fps:.8f}\n")
            fh.write(f"file '{frames[-1]}'\n")  # concat demuxer 要求最后一帧再列一次
        cmd += ["-f", "concat", "-safe", "0", "-i", list_file]
    else:
        cmd += ["-i", src]

    vf = build_vf(fit, burn, corner, caption_file, pick_font())
    cmd += ["-vf", vf, "-r", f"{fps:g}", "-an",
            *(["-c:v", "h264_videotoolbox", "-b:v", bitrate, "-allow_sw", "1"] if sys.platform == "darwin" else ["-c:v", "libx264", "-preset", "medium", "-crf", "16"]),
            "-profile:v", "high", "-movflags", "+faststart", out]

    if dry_run:
        print(" ".join(shlex.quote(c) for c in cmd))
        _cleanup(tmpdir)
        return {"dry_run": True, "cmd": cmd, "fps": fps, "out": out}

    os.makedirs(OUT_DIR, exist_ok=True)
    try:
        subprocess.run(cmd, check=True)
    finally:
        _cleanup(tmpdir)

    dur = None
    try:
        dur = float(subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out],
            capture_output=True, text=True, check=True).stdout.strip())
    except Exception:
        pass

    rec = {
        "source": "Google Earth Studio",
        "attribution": ATTRIBUTION_MAIN,
        "providers": providers.strip(),
        "credit_line": credit_line(providers),
        "attribution_burned": bool(burn),
        "burn_corner": corner if burn else None,
        "license_note": "非商业/非推广用途；须在画面上同时显示 “Google Earth” 与第三方影像提供方署名，"
                        "不得裁掉或遮挡。教育/纪录类网络视频即使有平台广告分成也无需申请。",
        "fps": fps,
        "frames": n_frames,
        "duration_s": round(dur, 3) if dur else None,
        "fit": fit,
        "input": src,
        "project_json": project_json,
        "created": _dt.datetime.now().isoformat(timespec="seconds"),
        "docs": DOC_URLS,
    }
    write_credit(os.path.basename(out), rec)
    log(f"完成 → {out}  ({dur:.1f}s @ {fps:g}fps)" if dur else f"完成 → {out}")
    log(f"署名记录 → {CREDITS_PATH}")
    return {"out": out, **rec}


def credit_line(providers: str = "") -> str:
    """给片尾字幕用的一行中文署名。"""
    p = providers.strip()
    return f"航拍画面：Google Earth（{p}）" if p else "航拍画面：Google Earth"


def write_credit(key: str, rec: dict):
    os.makedirs(OUT_DIR, exist_ok=True)
    data = {}
    if os.path.exists(CREDITS_PATH):
        try:
            with open(CREDITS_PATH, encoding="utf-8") as fh:
                data = json.load(fh)
        except Exception:
            log("credits_ges.json 解析失败，保留原文件为 .bak")
            os.replace(CREDITS_PATH, CREDITS_PATH + ".bak")
            data = {}
    data[key] = rec
    tmp = CREDITS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    os.replace(tmp, CREDITS_PATH)


def load_credits() -> dict:
    if not os.path.exists(CREDITS_PATH):
        return {}
    with open(CREDITS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def _cleanup(d: str):
    try:
        for f in os.listdir(d):
            os.remove(os.path.join(d, f))
        os.rmdir(d)
    except Exception:
        pass


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help="Earth Studio 导出目录（帧序列）或 MP4")
    ap.add_argument("--name", required=True, help="输出名 → assets/video/ges_<name>.mp4")
    ap.add_argument("--fps", type=float, default=None, help="覆盖帧率（默认读工程 JSON，再默认 30）")
    ap.add_argument("--providers", default="", help='数据提供方文字，照渲染图水印抄，如 "Image © 2026 Airbus, Maxar Technologies"')
    ap.add_argument("--fit", choices=("crop", "pad"), default="crop", help="非 16:9 时裁切(crop)或加黑边(pad)")
    ap.add_argument("--corner", choices=("br", "bl", "tr", "tl"), default="br", help="署名角落")
    ap.add_argument("--no-burn", action="store_true", help="不烧入署名小字")
    ap.add_argument("--bitrate", default="12M")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的输出")
    ap.add_argument("--dry-run", action="store_true", help="只打印 ffmpeg 命令")
    a = ap.parse_args(argv)
    if not a.no_burn and not a.providers:
        log("提示：未给 --providers；只烧 “Google Earth”。若渲染图水印上有第三方提供方，请照抄传入。")
    import_export(a.src, a.name, fps=a.fps, providers=a.providers, fit=a.fit, corner=a.corner,
                  burn=not a.no_burn, force=a.force, dry_run=a.dry_run, bitrate=a.bitrate)


if __name__ == "__main__":
    main()
