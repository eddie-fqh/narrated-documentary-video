#!/bin/bash
# 渲染一期：render（画面）→ finish（字幕 + 配乐 + 环境声 + 响度）→ 原子替换 final.mp4 → 逐镜截帧样张。
# 同一期同时只允许一个渲染（目录锁）；全机并发用 glock 限制：bash glock.sh render 2 bash render_ep.sh <ep_dir>
# 长渲染要脱离调用方的进程树再跑（见 references/ops.md），否则调用方超时会把 ffmpeg 一起杀掉。
set -e; EP="$(cd "$1" && pwd)"; LIB="$(cd "$(dirname "$0")" && pwd)"; export EP_DIR="$EP"
mkdir -p "$EP/work"; LOCK="$EP/work/.render.lock"
if ! mkdir "$LOCK" 2>/dev/null; then
  p=$(cat "$LOCK/pid" 2>/dev/null)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "已有渲染在跑（pid $p），退出"; exit 3; fi
  echo "发现陈旧锁（pid ${p:-?} 已不在），接管"; echo $$ > "$LOCK/pid"
fi
echo $$ > "$LOCK/pid"; trap 'rm -rf "$LOCK"' EXIT
python3 "$LIB/render.py" "$EP/shots.json" "$EP/work/picture.mp4" > "$EP/work/log_render.txt" 2>&1
python3 "$LIB/finish.py" "$EP/work/picture.mp4" "$EP/work/final_new.mp4"
mv "$EP/work/final_new.mp4" "$EP/final.mp4"; rm -f "$EP/work/picture.mp4" "$EP/work/bgm_stem.wav"
python3 "$LIB/qa_sheet.py" "$EP" | tail -1
echo "[$(date +%T)] 渲染完成 $(basename "$EP") · 素材回退 $(grep -c '素材找不到' "$EP/work/log_render.txt" || true) 处（不为 0 就要补素材重渲）"
