# -*- coding: utf-8 -*-
"""README 面板截图：真实 GlassPanel 按 SCALE 倍高清渲染，玻璃底由仓库壁纸
资产软件合成（高斯模糊 + 25% 压暗），全程无 Win+D、不采集真实桌面。

实机面板只有 440×296 物理像素（100% DPI 屏），直接截屏再放大必然发虚；
这里让文字按 SCALE 倍点阵化、矢量元素整体放大、logo 用当前色高清重染，
PrintWindow 只负责采集 Tk 画布自身的渲染结果，背景与桌面完全解耦。
壁纸资产：assets/wallpaper.png 缺失时自动抓当前桌面壁纸缩存入库（一次性，
提交到仓库），此后渲染结果完全确定；想换氛围直接替换该文件再跑。
用法: python tools/panel_render.py
产物: docs/panel.png（README 用，已带圆角）
"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import tkinter as tk
import tkinter.font as tkfont

ctypes.windll.user32.SetProcessDPIAware()
user32 = ctypes.windll.user32

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

SCALE = 2.5      # 440×296 → 1100×740，README 以 440px 展示正好 2.5x 密度
RADIUS = 28      # 圆角半径（源图像素）
OUT = os.path.join(ROOT, "docs", "panel.png")
WALLPAPER = os.path.join(ROOT, "assets", "wallpaper.png")
BLUR_RADIUS = 14   # 亚克力模糊强度（合成尺寸下的高斯半径）
TINT_ALPHA = 0.65  # 压暗档位：与实机 GLASS_TINT_ALPHA（acrylic GradientColor）一致
NOISE_SIGMA = 18   # acrylic 系统噪点模拟：叠加单色高斯噪点（越淡越接近实机）


def cover_crop(img, w, h):
    """等比放大到铺满 w×h 后居中裁切"""
    from PIL import Image
    scale = max(w / img.width, h / img.height)
    img = img.resize((round(img.width * scale), round(img.height * scale)),
                     Image.LANCZOS)
    x = (img.width - w) // 2
    y = (img.height - h) // 2
    return img.crop((x, y, x + w, y + h))


def load_wallpaper(size):
    """玻璃底用壁纸：优先仓库资产；缺失时抓当前桌面壁纸缩存入库（一次性）"""
    from PIL import Image, ImageDraw
    if os.path.exists(WALLPAPER):
        return Image.open(WALLPAPER).convert("RGB")
    buf = ctypes.create_unicode_buffer(260)
    user32.SystemParametersInfoW(0x0073, 260, buf, 0)   # SPI_GETDESKWALLPAPER
    if buf.value and os.path.exists(buf.value):
        img = Image.open(buf.value).convert("RGB")
    else:   # 纯色/幻灯片壁纸取不到文件路径时，退化为深蓝灰渐变
        img = Image.new("RGB", (1920, 1080))
        d = ImageDraw.Draw(img)
        for y in range(img.height):
            t = y / img.height
            d.line([(0, y), (img.width, y)],
                   fill=(int(38 + 22 * t), int(48 + 26 * t), int(66 + 30 * t)))
    img = cover_crop(img, *size)
    img.save(WALLPAPER, optimize=True)
    print("wallpaper asset ->", WALLPAPER)
    return img


def glass_background(m, size):
    """亚克力玻璃底：壁纸高斯模糊后向 GLASS_TINT 压暗 TINT_ALPHA，再叠
    极淡单色噪点——与实机 accent acrylic（blur×(1-α) + tint×α + 系统噪点）
    的观感对齐"""
    from PIL import Image, ImageChops, ImageFilter
    base = load_wallpaper(size).filter(ImageFilter.GaussianBlur(BLUR_RADIUS))
    tint = Image.new("RGB", base.size, m.GLASS_TINT)
    out = Image.blend(base, tint, TINT_ALPHA)
    noise = Image.effect_noise(base.size, NOISE_SIGMA)
    noise = noise.point(lambda p: 128 + (p - 128) // 6)   # σ≈3 居中 128
    return ImageChops.add(out, noise.convert("RGB"), 1.0, -128)


def hi_res_panel(m):
    """构建真实 GlassPanel 并整体重渲染为 SCALE 倍，返回 (panel, 采集回调, root)"""
    root = tk.Tk()
    root.withdraw()

    class FakeApp:
        pass

    app = FakeApp()
    app.root = root
    app.on = True
    app.settings = m.load_settings()
    # 截图展示真实使用状态：优先读取 dist/ 里的用户实际配色（同 menu_qa）
    dist_settings = os.path.join(ROOT, "dist", "eye_care_u_settings.json")
    if os.path.exists(dist_settings):
        import json
        try:
            with open(dist_settings, "r", encoding="utf-8") as f:
                vals = json.load(f)
            for k in ("r", "g", "b", "strength"):
                if k in vals:
                    app.settings[k] = vals[k]
        except Exception:
            pass
    app.actions = queue.Queue()
    app._panel = None
    app.save_action = lambda: None

    # 渲染窗口不需要 DWM 玻璃：玻璃底已软件合成进画布。开着它 PrintWindow
    # 会把窗口背后的桌面模糊混进半透明区域（壁纸垫底不生效的根因），
    # 关掉后采集的是纯 GDI 表面，与桌面彻底解耦
    m.enable_glass = lambda hwnd: False

    panel = m.GlassPanel(app)
    win, cv = panel.win, panel.canvas
    win.withdraw()   # 先不出窗口：背景铺好后再见人
    sw, sh = round(m.PANEL_W * SCALE), round(m.PANEL_H * SCALE)

    # 1) 矢量元素整体 ×SCALE；线条宽度不在 canvas.scale 之列，手动同步
    cv.scale("all", 0, 0, SCALE, SCALE)
    for item in cv.find_withtag("all"):
        t = cv.type(item)
        if t == "line":
            cv.itemconfigure(item, width=round(float(cv.itemcget(item, "width") or 1) * SCALE))
        elif t == "polygon":
            ow = cv.itemcget(item, "width")
            if ow:   # 按钮描边（纯填充的 round_rect 不带 width）
                cv.itemconfigure(item, width=round(float(ow) * SCALE))

    # 2) 文字按 SCALE 倍点阵化（canvas.scale 只缩放坐标，不缩放字体）
    scaled = {}
    for item in cv.find_withtag("all"):
        if cv.type(item) == "text":
            name = cv.itemcget(item, "font")
            if name not in scaled:
                f = tkfont.Font(root=root, font=name)   # 复制原字体属性
                f.configure(size=int(f.actual("size") * SCALE + 0.5))
                scaled[name] = f
            cv.itemconfigure(item, font=scaled[name])

    # 3) logo 位图不会随 scale 放大，换成 SCALE 倍的当前色染色版
    #    （实机头部 logo 即色块本体，随配色实时染色——见 GlassPanel._tint_logo_img）
    photos = [i for i in cv.find_withtag("all") if cv.type(i) == "image"]
    if photos:
        from PIL import ImageTk
        item = photos[0]
        x0, y0 = cv.coords(item)
        anchor = cv.itemcget(item, "anchor") or "w"
        cv.delete(item)
        px = round(17 * SCALE)
        tinted = panel._tint_logo_img(px)
        if tinted is not None:
            panel._photo = ImageTk.PhotoImage(tinted)
            cv.create_image(x0, y0, anchor=anchor, image=panel._photo)

    # 4) 玻璃底软件合成：删掉画布上的玻璃底矩形（全画布唯一的 rectangle），
    #    垫入模糊压暗的壁纸。此后采集结果与窗口背后的桌面完全无关
    for item in cv.find_withtag("all"):
        if cv.type(item) == "rectangle":
            cv.delete(item)
    from PIL import ImageTk
    panel._wp_photo = ImageTk.PhotoImage(glass_background(m, (sw, sh)))
    wp_item = cv.create_image(0, 0, anchor="nw", image=panel._wp_photo)
    cv.tag_lower(wp_item)

    # 5) 窗口放大并重新锚定工作区右下角（仅摆放位置，采集不依赖桌面）
    wa = m.work_area()
    win.geometry("%dx%d+%d+%d" % (sw, sh, wa.right - sw - 12, wa.bottom - sh - 12))
    cv.configure(width=sw, height=sh)
    win.update_idletasks()
    win.deiconify()   # 背景已铺好，再出窗口

    def grab():
        from menu_qa import grab_img
        hwnd = m.native_hwnd(win)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        return grab_img(rect, hwnd)

    return panel, grab, root


def round_corners(img):
    """四角烤上抗锯齿圆角（超采样保证边缘平滑）"""
    from PIL import Image, ImageDraw
    img = img.convert("RGBA")
    w, h = img.size
    ss = 4
    mask = Image.new("L", (w * ss, h * ss), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, w * ss - 1, h * ss - 1], radius=RADIUS * ss, fill=255)
    img.putalpha(mask.resize((w, h), Image.LANCZOS))
    return img


def main():
    import eye_care_u as m
    m.tk = tk

    panel, grab, root = hi_res_panel(m)

    def finish():
        img = round_corners(grab())
        img.save(OUT, optimize=True)
        print("panel ->", OUT, img.size)
        panel.close()
        root.destroy()

    root.after(400, finish)   # 等画布渲染稳定再采集
    root.mainloop()


if __name__ == "__main__":
    main()
