"""镜头表生成器的工具函数。每期写一个 build_shots.py（见 templates/episode/build_shots.example.py），
用代码而不是手写 JSON 来排镜头：锚点、动画时长、提示点全部从配音对齐里算，改稿重配后重跑一遍即可。

    import shotlib as L
    L.init(ep_dir)                              # 需要 audio/segments/manifest.json 与 work/chars.json
    L.vid("__start__", "aerial_01", fade_in=0.3)
    L.img("第一句原文", "portrait", ov=[L.name("中文名", "Latin Name", "1475—1564")])
    L.anim("讲到模型的那句", "model", until="下一个镜头的锚点", cues={"c1": "提示点短语", "c2": "end"})
    L.save()                                    # 写 shots_src.json 与 anim/jobs.json
"""
import json, os, pathlib, sys
S, JOBS, EP, TL = [], {}, None, None
def init(ep):
    global EP, TL
    EP = pathlib.Path(ep).resolve(); os.environ["EP_DIR"] = str(EP)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent)); import render as R
    TL = R.Timeline(); S.clear(); JOBS.clear()
def T(phrase, after=None):
    """短语第一个字的发音时刻（秒）。after 给定时从该短语之后找——不依赖调用顺序。
    （render.Timeline.at 是顺序游标：同一短语出现两次时，要靠 after 指明是哪一次。）"""
    TL.cursor = max(TL.text.find(after), 0) if after else 0
    return TL.at(phrase)
def have(key): return any((EP/"img"/f"{key}.{e}").exists() for e in ("jpg", "jpeg", "png", "webp"))
def pick(*keys):
    """按优先级取第一张存在的图；都没有就停——不要让渲染时悄悄用上一镜头顶替。"""
    for k in keys:
        if have(k): return k
    raise SystemExit(f"缺图: {keys}")
def sh(at, type_, src=None, **kw):
    d = {"at": at, "type": type_}
    if src: d["src"] = src
    d.update(kw); S.append(d); return d
def img(at, key, move="in", **kw): return sh(at, "img", f"img/{key}", move=move, **kw)
def kbimg(at, key, a, b, **kw): return sh(at, "img", f"img/{key}", kb=[a, b], **kw)      # a/b = [缩放, cx, cy]，用 kb.py 算
def art(at, key, **kw): return sh(at, "art", f"img/{key}", **kw)
def vid(at, key, **kw): return sh(at, "vid", f"video/{key}.mp4", **kw)
def focus(at, key, rects, **kw): return sh(at, "focus", f"img/{key}", rects=rects, **kw)   # rects = [[x, y, w, h, "标签"], …]（比例）
def split(at, a, b, **kw): return sh(at, "split", f"img/{a}", src2=f"img/{b}", **kw)
def grid(at, keys, **kw): return sh(at, "grid", None, items=[f"img/{k}" for k in keys], **kw)
# ── 叠层
def title(text, sub="", i=0.5): return {"kind": "title", "text": text, "sub": sub, "in": i}
def place(text, en="", i=0.3): return {"kind": "place", "text": text, "en": en, "in": i}
def name(zh, en, years="", pos="bl", i=0.8): return {"kind": "name", "zh": zh, "en": en, "years": years, "pos": pos, "in": i}
def artov(title, by, pos="br", i=0.4): return {"kind": "art", "title": title, "by": by, "pos": pos, "in": i}
def card(label, text, hl="", pos="br", i=0.6): return {"kind": "card", "label": label, "text": text, "hl": hl, "pos": pos, "in": i}
def big(text, sub="", i=0.3): return {"kind": "big", "text": text, "sub": sub, "in": i}
def chapter(n, text, i=0.2): return {"kind": "chapter", "n": n, "text": text, "in": i, "dur": 2.6}
def callout(text, sub, ix, iy, side="r", r=60, i=1.0): return {"kind": "callout", "text": text, "sub": sub, "side": side, "r": r, "ix": ix, "iy": iy, "in": i}
def quote(text, by="", i=0.5): return {"kind": "quote", "text": text, "by": by, "in": i}
def year(text, sub="", i=0.4): return {"kind": "year", "text": text, "sub": sub, "in": i}
def anim(at, scene, until, cues=None, page=None, **kw):
    """专属动画镜头：时长 = 到下一镜头锚点的间隔 + 0.2s。
    必须比镜头略长：短了渲染器会把它放慢来凑时长，放慢靠重复帧，运动中的画面就会一顿一顿。
    cues 里的短语换成相对动画起点的秒数（"end" = 结束前 0.7s），作为 c1…cN 传给页面。"""
    t0 = T(at); dur = round(T(until, at) - t0 + 0.2, 2)
    q = {"scene": scene, "dur": dur}
    for k, v in (cues or {}).items(): q[k] = round(dur - 0.7 if v == "end" else (T(v, at) - t0) if isinstance(v, str) else v, 2)
    if page: q["_page"] = page
    JOBS[f"a_{scene}"] = q
    return sh(at, "vid", f"anim/a_{scene}.mp4", **kw)
def save(tail=4.5):
    json.dump({"tail": tail, "shots": S}, open(EP/"shots_src.json", "w"), ensure_ascii=False, indent=1)
    (EP/"anim").mkdir(exist_ok=True); json.dump(JOBS, open(EP/"anim/jobs.json", "w"), ensure_ascii=False, indent=1)
    print(f"{len(S)} 镜头 → shots_src.json；{len(JOBS)} 段动画 → anim/jobs.json")
