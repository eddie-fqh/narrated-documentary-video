#!/bin/bash
# 全局信号量（先来先得）：glock.sh <name> <slots> <cmd...>
# 排队：在 queue/<name>/ 下放一张带纳秒时间戳的号牌；只有排在最前面 <空槽数> 张号牌的人才能抢槽位（mkdir 原子）。
# 锁目录：$GLOCK_DIR（默认 $TMPDIR/video-glock）。死进程的槽位/号牌按 pid 回收。注意：改这个文件要写新文件再 mv 覆盖，别原地改（正在跑的 bash 会读错位）。
name=$1; slots=$2; shift 2; D="${GLOCK_DIR:-${TMPDIR:-/tmp}/video-glock}"; Q="$D/queue/$name"; mkdir -p "$D" "$Q"
T="$Q/$(date +%s%N 2>/dev/null || python3 -c 'import time;print(time.time_ns())').$$"; echo $$ > "$T"
cleanup(){ rm -f "$T"; [ -n "$L" ] && rm -rf "$L"; }; trap cleanup EXIT
while :; do
  for f in "$Q"/*; do [ -e "$f" ] || continue; p=${f##*.}; kill -0 "$p" 2>/dev/null || rm -f "$f"; done
  free=0
  for i in $(seq 1 $slots); do
    S="$D/$name.$i"; p=$(cat "$S/pid" 2>/dev/null)
    if [ -d "$S" ] && [ -n "$p" ] && ! kill -0 "$p" 2>/dev/null; then rm -rf "$S"; fi
    [ -d "$S" ] || free=$((free+1))
  done
  if [ $free -gt 0 ] && ls "$Q" | sort -n | head -$free | grep -qx "$(basename "$T")"; then
    for i in $(seq 1 $slots); do
      L="$D/$name.$i"
      if mkdir "$L" 2>/dev/null; then echo $$ > "$L/pid"; rm -f "$T"; "$@"; exit $?; fi
    done
    L=""
  fi
  sleep 5
done
