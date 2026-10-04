#!/usr/bin/env python3
"""列出 shots_src.json 里短于阈值的镜头。用法: short_shots.py <ep> [min=3.0]"""
import json,sys,os,pathlib
ep=pathlib.Path(sys.argv[1]).resolve(); M=float(sys.argv[2]) if len(sys.argv)>2 else 3.0
os.environ["EP_DIR"]=str(ep); sys.path.insert(0,str(pathlib.Path(__file__).parent)); import render as R
TL=R.Timeline(); sh=json.load(open(ep/"shots_src.json"))["shots"]
t=[0 if x['at']=='__start__' else TL.at(x['at']) for x in sh]
for i,x in enumerate(sh):
    d=(t[i+1] if i+1<len(t) else 999)-t[i]
    if d<M: print(f"{t[i]:7.1f} {d:4.1f}  {x['at']}  {x.get('src',x.get('items'))}")
