#!/usr/bin/env python3
"""逐镜截帧拼样张：qa_sheet.py <ep_dir> → <ep>/work/qa_sheet_N.png"""
import json, subprocess, os, sys, glob
from PIL import Image
ep = sys.argv[1]; os.chdir(ep)
for f in glob.glob('work/qa/*') + glob.glob('work/qa_sheet_*'): os.remove(f)
st = json.load(open('work/shot_times.json')); os.makedirs('work/qa', exist_ok=True)
for i, x in enumerate(st):
    t = x['t'] + (x['t_end'] - x['t']) * 0.7
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", "final.mp4", "-frames:v", "1", "-vf", "scale=384:-1", f"work/qa/{i:03d}.jpg"])
fs = sorted(os.listdir('work/qa'))
for p in range(0, len(fs), 48):
    c = Image.new('RGB', (384*6, 216*8))
    for i, f in enumerate(fs[p:p+48]): c.paste(Image.open('work/qa/'+f), ((i % 6)*384, (i//6)*216))
    c.save(f'work/qa_sheet_{p//48}.png')
print(len(fs), "shots,", (len(fs)+47)//48, "sheets")
