# -*- coding: utf-8 -*-
"""logo 配色重染工具：把 assets/logo.png 的橘猫按新配色重染成彩色版。

只改 RGB 颜色，alpha 与几何逐像素原样保留。用法：
  python recolor_logo.py --variant a --out assets/logo_color_a.png
  python recolor_logo.py --variant b --out assets/logo_color_b.png
"""
import argparse

from PIL import Image

# 方案 A 亮度渐变：暗部深靛蓝 → 紫罗兰 → 品红 → 高光暖金（参考狮子鬃毛配色）
STOPS_A = [
    (0.00, (30, 22, 82)),      # 深靛蓝
    (0.22, (69, 39, 201)),     # 宝石蓝紫
    (0.45, (147, 51, 234)),    # 鲜紫罗兰
    (0.65, (226, 63, 169)),    # 品红粉
    (0.82, (255, 109, 141)),   # 珊瑚粉
    (1.00, (255, 197, 92)),    # 暖金高光
]

# 方案 B 空间渐变：顶部玫粉 → 中部亮紫 → 底部宝蓝（狮子同款流向）
STOPS_B = [
    (0.00, (255, 77, 158)),    # 玫粉
    (0.50, (168, 85, 247)),    # 亮紫
    (1.00, (59, 130, 246)),    # 宝蓝
]


def sample_stops(stops, t):
    """在渐变锚点间线性插值"""
    if t <= stops[0][0]:
        return stops[0][1]
    for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            return tuple(round(c0[k] + (c1[k] - c0[k]) * f) for k in range(3))
    return stops[-1][1]


def contrast(l, strength=0.35):
    """smoothstep 对比：暗更暗、亮更亮，中段平滑过渡"""
    s = l * l * (3 - 2 * l)
    return l * (1 - strength) + s * strength


def recolor(src, mode):
    img = src.convert("RGBA")
    px = img.load()
    w, h = img.size
    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            # Rec.709 亮度 → 对比增强
            l = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0
            l = contrast(l)
            if mode == "a":
                rgb = sample_stops(STOPS_A, l)
            else:
                # 顶部偏粉、底部偏蓝的对角流向（狮子：右上粉→左下蓝）
                t = 0.72 * (y / (h - 1)) + 0.28 * (1.0 - x / (w - 1))
                base = sample_stops(STOPS_B, t)
                k = 0.42 + 0.72 * l           # 原图亮度调制明暗
                rgb = tuple(min(255, round(c * k)) for c in base)
            px[x, y] = rgb + (a,)
    return img


def mockup_sheet(candidates):
    """两个方案并排贴到深海军蓝底上，附小尺寸行，生成对比预览图"""
    BG = (13, 26, 61)   # 参考图的深海军蓝
    sheet = Image.new("RGB", (960, 560), BG)
    for i, (img, label) in enumerate(candidates):
        x0 = 30 + i * 470
        big = img.resize((380, 379))
        sheet.paste(big, (x0, 60), big)
        for j, s in enumerate((64, 48, 32)):
            small = img.resize((s, s))
            sheet.paste(small, (x0 + 20 + j * 80, 470), small)
    sheet.save("assets/logo_color_preview.png")
    print("预览图: assets/logo_color_preview.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", choices=("a", "b"), required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--src", default="assets/logo.png")
    args = ap.parse_args()

    src = Image.open(args.src)
    before = src.convert("RGBA").getchannel("A").histogram()[0]
    out = recolor(src, args.variant)
    after = out.getchannel("A").histogram()[0]
    assert before == after, "alpha 被改动了！"
    out.save(args.out)
    print("%s: %s（透明像素 %d，前后一致）" % (args.variant, args.out, after))


if __name__ == "__main__":
    main()
