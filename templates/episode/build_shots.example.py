#!/usr/bin/env python3
"""镜头表生成器示例：放到 <ep>/work/build_shots.py，配音对齐（align.py）完成后运行。
写出 <ep>/shots_src.json 和 <ep>/anim/jobs.json。所有锚点都是口播稿里原样出现的文字。
用法: SKILL_SCRIPTS=<skill>/scripts python3 work/build_shots.py"""
import os, sys, pathlib
EP = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, os.environ.get("SKILL_SCRIPTS", str(EP.parent.parent/"scripts")))
import shotlib as L
L.init(EP)

# ── 钩子：开场 5 秒内抛出问题，并预告全片最好看的那段画面
L.vid("__start__", "clip", fade_in=0.6, ov=[L.title("屋顶为什么盖两层", "系列名 · 第 1 期", i=0.4)])

# ── 第一章：章节卡 + 柔和转场；关键数字说出口的那一刻弹大数字卡
L.img("先说它有多大", "wide", move="in", tr="rack", xf=1.0, ov=[L.chapter("PART I", "它有多大"), L.place("示例建筑", "EXAMPLE HALL", i=3.0)])
L.anim("内径三十五米六", "cut", until="好，再说里面", cues={"c1": "你想", "c2": "十几层楼"})

# ── 第二章：问句处画面停住，答案落下时切镜
L.focus("好，再说里面", "detail", [[0.10, 0.20, 0.30, 0.35, "外层"], [0.55, 0.40, 0.30, 0.35, "内层"]], tr="rack", xf=1.0, ov=[L.chapter("PART II", "两层之间")])
L.split("我原来以为", "old", "portrait", ov=[L.card("对比", "外面一层挡雨\n里面一层承重", hl="承重", pos="br", i=3.2)])

# ── 收束：落回对象本身，淡出
L.kbimg("最后，站在它底下", "tall", [1.02, .5, .75], [1.10, .5, .30], tr="light", xf=1.0, fade_out=2.0, ov=[L.quote("光从顶上漏下来\n一整天都在慢慢地走", i=3.0)])
L.save(tail=3.0)
