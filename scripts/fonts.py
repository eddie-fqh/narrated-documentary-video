"""字体：按平台挑第一个存在的；都可以用环境变量覆盖（FONT_BOLD / FONT_LIGHT / FONT_LATIN / FONT_SERIF / SUB_FONT）。
拉丁字体通常没有中文字形（会画成方框），引擎里凡是中西混排都逐字选字体。"""
import os, sys
def _first(env, cands):
    v = os.environ.get(env)
    if v: return v
    return next((c for c in cands if os.path.exists(c)), cands[0])
BOLD = _first("FONT_BOLD", ["/System/Library/Fonts/STHeiti Medium.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
                            "/usr/share/fonts/noto-cjk/NotoSansCJK-Bold.ttc", "C:/Windows/Fonts/msyhbd.ttc"])
LIGHT = _first("FONT_LIGHT", ["/System/Library/Fonts/STHeiti Light.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                              "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc", "C:/Windows/Fonts/msyh.ttc"])
LATIN = _first("FONT_LATIN", ["/System/Library/Fonts/Avenir Next.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "C:/Windows/Fonts/segoeui.ttf"])
SERIF = _first("FONT_SERIF", ["/System/Library/Fonts/Supplemental/Songti.ttc", "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                              "/usr/share/fonts/noto-cjk/NotoSerifCJK-Regular.ttc", "C:/Windows/Fonts/simsun.ttc"])
SUB_FONT_NAME = os.environ.get("SUB_FONT", "Heiti SC" if sys.platform == "darwin" else "Noto Sans CJK SC")   # 字幕（libass 按字体名找）
