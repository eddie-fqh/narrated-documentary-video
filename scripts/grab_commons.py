#!/usr/bin/env python3
"""按 selection.json {key: "File:..."} 下载到 <ep>/img/，写 credits.json；慢速+校验，429 退避。
用法: grab_commons.py <ep_dir>"""
import json,os,sys,time,io,urllib.request
from PIL import Image
Image.MAX_IMAGE_PIXELS=None
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import commons as FA
ep=sys.argv[1]; sel=json.load(open(f"{ep}/selection.json")); os.makedirs(f"{ep}/img",exist_ok=True)
cred=json.load(open(f"{ep}/credits.json")) if os.path.exists(f"{ep}/credits.json") else {}
def ok(p):
    try: Image.open(p).verify(); return True
    except Exception: return False
rej={os.path.splitext(f)[0] for f in (os.listdir(f"{ep}/rejected") if os.path.isdir(f"{ep}/rejected") else [])}
todo=[k for k in sel if k not in rej and not (k in cred and os.path.exists(cred[k]["file"]) and ok(cred[k]["file"]))]
titles=list(dict.fromkeys(sel[k] for k in todo)); inf={}
for i in range(0,len(titles),20):
    for a in range(5):
        try: inf.update(FA.info(titles[i:i+20])); break
        except Exception as e: time.sleep(20*(a+1))
    time.sleep(3)
for k in todo:
    x=inf.get(sel[k])
    if not x: print("✗ 无此文件",k,sel[k],flush=True); continue
    p=f"{ep}/img/{k}"+(os.path.splitext(x["url"].split("?")[0])[1].lower() or ".jpg")
    # 缩略图渲染最容易 429；被拒就改拉原图直链（大但不限流那么狠）
    for a,url in enumerate([x["url"], x.get("orig") or x["url"], x.get("orig") or x["url"]]):
        try:
            data=urllib.request.urlopen(urllib.request.Request(url,headers=FA.UA),timeout=180).read()
            im=Image.open(io.BytesIO(data)); im.verify()
            im=Image.open(io.BytesIO(data)).convert("RGB")
            if im.width>2560: im=im.resize((2560, round(im.height*2560/im.width)), Image.LANCZOS)
            p=os.path.splitext(p)[0]+".jpg"; im.save(p, quality=92)
            # [可选] 设了 UPSCALE_MIN_WIDTH（如 2000）且图比它窄 → Real-ESRGAN 放大到 2560 宽，
            # 原图留作 img/<key>.orig.jpg。不设该环境变量则此块完全不执行；放大失败也不影响下载结果。
            if os.environ.get("UPSCALE_MIN_WIDTH"):
                import upscale as UP; UP.maybe_upscale(p, int(os.environ["UPSCALE_MIN_WIDTH"]), 2560)
            cred[k]={**x,"title":sel[k],"file":p}; print("ok",k,im.size,flush=True); break
        except Exception as e:
            wait = 8*(a+1)
            ra = getattr(getattr(e, "headers", None), "get", lambda *_: None)("Retry-After")
            if ra and str(ra).isdigit(): wait = int(ra) + 2
            print("retry",k,str(e)[:60],"等",wait,"s",flush=True); time.sleep(wait)
    time.sleep(2)
    json.dump(cred,open(f"{ep}/credits.json","w"),ensure_ascii=False,indent=1)
print("done",len(cred),"/",len(sel),"缺:",[k for k in sel if k not in cred])
