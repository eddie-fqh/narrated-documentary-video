#!/bin/bash
# 成片自动扫描：scan_video.sh <final.mp4> [静止阈值秒=2.5]
# 报：连续静止的画面（刻意的定格可以保留，但要知道它在哪）、黑场、整体响度与真峰值、时长。
f="$1"; d="${2:-2.5}"
echo "── 时长 $(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")s"
echo "── 静止 ≥${d}s"; ffmpeg -hide_banner -nostats -i "$f" -vf "freezedetect=n=0.003:d=$d" -map 0:v -f null - 2>&1 | grep -E "freeze_(start|duration)" | sed -E 's/.*lavfi\.freezedetect\.//' | paste - - | sed 's/^/   /' || true
echo "── 黑场 ≥0.5s"; ffmpeg -hide_banner -nostats -i "$f" -vf "blackdetect=d=0.5:pix_th=0.08" -an -f null - 2>&1 | grep -o "black_start:[0-9.]* black_end:[0-9.]* black_duration:[0-9.]*" | sed 's/^/   /' || true
echo "── 响度"; ffmpeg -hide_banner -nostats -i "$f" -af ebur128=peak=true -vn -f null - 2>&1 | grep -E "^ +(I|LRA|Peak):" | tr -s ' ' | sed 's/^/  /'
