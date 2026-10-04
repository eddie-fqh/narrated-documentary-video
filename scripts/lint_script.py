#!/usr/bin/env python3
"""口播稿检查（写给 TTS 念、写给人听的稿子）：lint_script.py <script.txt> [--series series.json] [--shots shots_src.json]
内置规则：
  · 英文字母 / 阿拉伯数字（TTS 会吞或乱读：外文名写音译，数字写成汉字）
  · 引号、括号、破折号、省略号（念不出来，还会打乱停顿）
  · 说教式结尾、口头语
  · 隐私：行程、住处、具体日期（发在公开频道的稿子里不该有）
series.json（可选，系列级固定格式）: {"opening": "固定开场白", "closing_regex": "固定结尾的正则", "banned": [["正则", "说明"], …], "allow": ["允许出现的英文词", …]}
同时打印节奏指标：字数、句长中位数、设问密度（每百字）；给了 --shots 再报锚点存活率（改稿后有多少镜头锚点还在）。"""
import sys, re, json
BAD = [(r"[A-Za-z]+", "英文"), (r"\d+", "阿拉伯数字"), (r"[“”\"'‘’（）()《》—…]", "引号/括号/破折号"),
       (r"下次当你|停下来，想一想|停下来想一想|告诉我们一个道理", "说教式结尾"), (r"我觉得呢|就是说|哎呀|嗯，|呃", "口头语"),
       (r"行程|我住的|酒店|我们今天去|我们明天", "行程/住处"), (r"周[一二三四五六日天]去|[一二三四五六七八九十]+月[上中下]旬|今年|上个月", "具体时间")]
args = sys.argv[1:]
def opt(name):
    if name in args: k = args.index(name); v = args[k+1]; del args[k:k+2]; return v
series = json.load(open(opt("--series") or "/dev/null")) if "--series" in sys.argv else {}
shots = opt("--shots")
han = lambda s: re.findall(r"[一-鿿]", s)
rc = 0
for f in args:
    t = open(f, encoding="utf-8").read(); issues = []; body = t
    for w in series.get("allow", []): body = body.replace(w, "")
    for p, name in BAD + [tuple(x) for x in series.get("banned", [])]:
        for m in re.finditer(p, body): issues.append(f"{name}: …{body[max(0, m.start()-12):m.end()+12]}…".replace("\n", " "))
    if series.get("opening") and series["opening"] not in t: issues.append("缺固定开场白")
    if series.get("closing_regex") and not re.search(series["closing_regex"] + r"\s*$", t): issues.append("结尾格式不对")
    sents = [s for s in re.split(r"[。！？]", t) if han(s)]; n = len(han(t))
    q = len(re.findall(r"？|吗|呢|为什么|怎么|是不是|对不对|你说|你想|什么意思", t))
    print(f"{f}: {n} 字  {len(sents)} 句  句长中位 {sorted(len(han(s)) for s in sents)[len(sents)//2] if sents else 0}  设问/百字 {100*q/max(n, 1):.2f}  {'OK' if not issues else ''}")
    for i in issues: print("   ", i)
    if shots:
        ats = [s["at"] for s in json.load(open(shots))["shots"] if s["at"] != "__start__"]; dead = [a for a in ats if a not in t]
        print(f"    锚点存活 {len(ats)-len(dead)}/{len(ats)}", ("失效: " + str(dead[:8])) if dead else "")
    rc |= bool(issues)
sys.exit(rc)
