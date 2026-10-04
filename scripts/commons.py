#!/usr/bin/env python3
"""Wikimedia Commons 搜图：只收 公有领域 / CC0 / CC BY / CC BY-SA，记录作者与许可以便片尾署名。
用法: commons.py "检索词" ...   （检索词用英文、要具体：写到哪件作品的哪个局部）"""
import json, sys, urllib.request, urllib.parse, urllib.error, re, os, time
# Wikimedia 要求 User-Agent 带项目地址或联系方式：用环境变量 COMMONS_UA 设成你自己的
UA = {"User-Agent": os.environ.get("COMMONS_UA", "narrated-documentary-video/1.0 (educational video project; set COMMONS_UA) python-urllib")}
API = "https://commons.wikimedia.org/w/api.php"
OK = re.compile(r"^(public domain|pd|cc0|cc[- ]by(-sa)?[- ][0-9.]+)", re.I)
def get(params):
    u = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    for a in range(6):
        try: return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=40).read())
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(20*(a+1)); continue      # 被限流就退避；连续 429 说明请求太密，别硬顶
            raise
    raise RuntimeError("Commons API 连续 429，稍后再试")
def search(q, n=8, minw=1600):
    r = get({"action": "query", "generator": "search", "gsrsearch": f"filetype:bitmap {q}", "gsrnamespace": 6,
             "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 3000})
    out = []
    for p in (r.get("query", {}).get("pages", {}) or {}).values():
        ii = p["imageinfo"][0]; m = ii.get("extmetadata", {})
        lic = (m.get("LicenseShortName", {}).get("value") or "").strip()
        if not OK.match(lic) or ii["width"] < minw: continue
        artist = re.sub("<[^>]+>", "", m.get("Artist", {}).get("value", "")).strip()
        out.append({"title": p["title"], "w": ii["width"], "h": ii["height"], "license": lic, "artist": artist[:80],
                    "thumb": ii.get("thumburl") or ii["url"], "page": ii["descriptionurl"]})
    return out
def info(titles):
    """File: 标题列表 → {标题: {url(2560 宽缩略), orig, w, h, page, license, artist}}"""
    r = get({"action": "query", "titles": "|".join(titles), "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 2560})
    out = {}
    for p in r["query"]["pages"].values():
        if "imageinfo" not in p: print("  missing", p.get("title")); continue
        ii = p["imageinfo"][0]; m = ii.get("extmetadata", {})
        out[p["title"]] = {"url": ii.get("thumburl") or ii["url"], "orig": ii["url"], "w": ii["width"], "h": ii["height"], "page": ii["descriptionurl"],
                           "license": (m.get("LicenseShortName", {}).get("value") or "").strip(),
                           "artist": re.sub("<[^>]+>", "", m.get("Artist", {}).get("value", "")).strip()[:100]}
    return out
if __name__ == "__main__":
    for q in sys.argv[1:]:
        print("##", q)
        for x in search(q): print(f"  {x['w']}x{x['h']} {x['license']:<14} {x['title'][5:70]}  | {x['artist'][:30]}")
        time.sleep(1)
