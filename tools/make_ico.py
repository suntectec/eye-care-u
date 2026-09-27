# -*- coding: utf-8 -*-
"""从 assets/logo.png（唯一来源）重新生成多尺寸 assets/logo.ico。

托盘图标与设置窗口水印直接读 logo.png（打包时 --add-data 带入 exe），
exe 文件图标用 logo.ico。因此换 logo 只需替换 logo.png 再跑 build.bat：
本脚本在打包前自动重生成 ico，两处图标永远同图同色。
"""
import os

from PIL import Image

SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(BASE, "assets", "logo.png")
dst = os.path.join(BASE, "assets", "logo.ico")

img = Image.open(src).convert("RGBA")
img.save(dst, format="ICO", sizes=SIZES)
print("logo.ico regenerated from logo.png:", [s[0] for s in SIZES])
