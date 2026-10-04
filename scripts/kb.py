#!/usr/bin/env python3
"""把「原图上想放在画面中心的点」换成 kb 参数。
kb 的 [z, cx, cy] 里 cx/cy 不是中心坐标，而是裁切框在剩余余量里的位置（0=贴左/上，1=贴右/下，0.5=居中）。
用法: kb.py <图片> <u> <v> <z>      u,v = 目标点在原图上的归一化坐标（0–1）；z = 缩放（≥1）
输出: [z, cx, cy]（已夹在 0–1）；也可 import: from kb import kb_for"""
import sys
from PIL import Image
Image.MAX_IMAGE_PIXELS = None
W, H = 1920, 1080
def kb_for(path, u, v, z):
    iw, ih = Image.open(path).size
    r = W/H
    if iw/ih > r: h = ih; w = h*r
    else: w = iw; h = w/r
    w /= z; h /= z
    cx = 0.5 if iw - w < 1 else (u*iw - w/2)/(iw - w)
    cy = 0.5 if ih - h < 1 else (v*ih - h/2)/(ih - h)
    return [round(z, 3), round(min(1, max(0, cx)), 3), round(min(1, max(0, cy)), 3)]
if __name__ == "__main__":
    p, u, v, z = sys.argv[1], *map(float, sys.argv[2:5]); print(kb_for(p, u, v, z))
