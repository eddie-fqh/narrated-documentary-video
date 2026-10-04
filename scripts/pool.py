#!/usr/bin/env python3
"""候选图池：批量检索 → 缩略图 → 带编号样张 → 人工挑选 → 写 selection.json 并下载原图。
  pool.py search <ep> "q1" "q2" ...     每个检索词取前 N(=10) 张合规大图，缩略图存 <ep>/pool/
  pool.py sheet  <ep> [from_id]          生成样张 <ep>/pool/sheet_XXX.png（每张 30 格，带编号+检索词）
  pool.py pick   <ep> 12:key 40:key ...  把候选编号映射成 img key，写入 selection.json 并调 grab_commons 下载
  pool.py sheetimg <ep>                  现有 img/ 全部图片的样张（核对错图用）"""
import json, sys, os, time, io, hashlib, urllib.request, subprocess
from PIL import Image, ImageDraw, ImageFont
Image.MAX_IMAGE_PIXELS = None
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from commons import get, OK, UA
import re
import fonts as _F
F = ImageFont.truetype(_F.BOLD, 20)
def search(q, n=10, minw=900):
    for a in range(5):
        try:
            r = get({"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
                     "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 480})
            break
        except Exception as e:
            if "429" in str(e): time.sleep(15*(a+1)); continue
            return []
    else: return []
    out = []
    pages = sorted((r.get("query", {}).get("pages", {}) or {}).values(), key=lambda p: p.get("index", 0))
    for p in pages:
        ii = p["imageinfo"][0]; m = ii.get("extmetadata", {})
        lic = (m.get("LicenseShortName", {}).get("value") or "").strip()
        if not OK.match(lic) or ii["width"] < minw: continue
        out.append({"title": p["title"], "w": ii["width"], "h": ii["height"], "thumb": ii.get("thumburl") or ii["url"]})
    return out
def cmd_search(ep, qs):
    d = f"{ep}/pool"; os.makedirs(d, exist_ok=True); pj = f"{d}/pool.json"
    pool = json.load(open(pj)) if os.path.exists(pj) else []
    have = {x["title"] for x in pool}
    try: have |= set(json.load(open(f"{ep}/selection.json")).values())
    except Exception: pass
    for q in qs:
        res = search(q); added = 0
        for x in res:
            if x["title"] in have: continue
            fn = f"{d}/{hashlib.md5(x['title'].encode()).hexdigest()[:10]}.jpg"
            for a in range(3):
                try:
                    data = urllib.request.urlopen(urllib.request.Request(x["thumb"], headers=UA), timeout=40).read()
                    Image.open(io.BytesIO(data)).convert("RGB").save(fn, quality=85); break
                except Exception as e: time.sleep(5*(a+1))
            else: continue
            pool.append({"id": len(pool), "title": x["title"], "q": q, "w": x["w"], "h": x["h"], "thumb": fn}); have.add(x["title"]); added += 1
        print(f"{q}: +{added}", flush=True); json.dump(pool, open(pj, "w"), ensure_ascii=False, indent=1); time.sleep(1)
def sheet(items, out, label):
    cols, cw, ch = 6, 320, 250; rows = (len(items)+cols-1)//cols
    S = Image.new("RGB", (cols*cw, rows*ch), (30, 30, 30)); d = ImageDraw.Draw(S)
    for i, it in enumerate(items):
        try: im = Image.open(it["thumb"]).convert("RGB"); im.thumbnail((cw-8, ch-50))
        except Exception: continue
        x, y = (i % cols)*cw, (i//cols)*ch; S.paste(im, (x+4+(cw-8-im.width)//2, y+4))
        d.rectangle([x, y+ch-44, x+cw, y+ch], fill=(0, 0, 0)); d.text((x+6, y+ch-42), label(it)[:30], font=F, fill=(255, 220, 120))
        d.text((x+6, y+ch-22), it.get("sub", "")[:34], font=F, fill=(200, 200, 200))
    S.save(out); print(out)
def cmd_sheet(ep, start=0):
    pool = json.load(open(f"{ep}/pool/pool.json"))
    for k in range(start, len(pool), 30):
        items = [{**x, "sub": x["title"][5:40]} for x in pool[k:k+30]]
        sheet(items, f"{ep}/pool/sheet_{k:03d}.png", lambda it: f"#{it['id']} {it['q'][:22]}")
def cmd_sheetimg(ep):
    fs = sorted(f for f in os.listdir(f"{ep}/img") if f.lower().endswith((".jpg", ".png", ".jpeg")))
    os.makedirs(f"{ep}/pool", exist_ok=True)
    for k in range(0, len(fs), 30):
        items = [{"thumb": f"{ep}/img/{f}", "k": os.path.splitext(f)[0], "sub": ""} for f in fs[k:k+30]]
        sheet(items, f"{ep}/pool/img_{k:03d}.png", lambda it: it["k"])
def cmd_pick(ep, pairs):
    pool = {x["id"]: x for x in json.load(open(f"{ep}/pool/pool.json"))}
    sp = f"{ep}/selection.json"; sel = json.load(open(sp)) if os.path.exists(sp) else {}
    for pr in pairs:
        i, k = pr.split(":", 1); sel[k] = pool[int(i)]["title"]
        cp = f"{ep}/credits.json"
        if os.path.exists(cp):   # 替换同名 key：删旧记录与旧文件，强制重下
            c = json.load(open(cp))
            if k in c:
                try: os.remove(c[k]["file"])
                except Exception: pass
                del c[k]; json.dump(c, open(cp, "w"), ensure_ascii=False, indent=1)
    json.dump(sel, open(sp, "w"), ensure_ascii=False, indent=1)
    subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "grab_commons.py"), ep])
if __name__ == "__main__":
    c, ep = sys.argv[1], sys.argv[2].rstrip("/")
    {"search": lambda: cmd_search(ep, sys.argv[3:]), "sheet": lambda: cmd_sheet(ep, int(sys.argv[3]) if len(sys.argv) > 3 else 0),
     "pick": lambda: cmd_pick(ep, sys.argv[3:]), "sheetimg": lambda: cmd_sheetimg(ep)}[c]()
