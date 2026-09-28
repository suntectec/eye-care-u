# -*- coding: utf-8 -*-
"""README 面板截图：真实 GlassPanel 按 SCALE 倍高清渲染 → PrintWindow 采集 → 烤圆角。

实机面板只有 440×296 物理像素（100% DPI 屏），直接截屏再放大必然发虚；
这里让文字按 SCALE 倍点阵化、矢量元素整体放大、logo 用高清原图重缩放，
得到真正的高分辨率版本，采集走 menu_qa 的 PrintWindow 路径（玻璃底一并合成）。
亚克力采样的是窗口后面的真实桌面，故截图前先 Win+D 最小化全部窗口、
以桌面壁纸为玻璃背景，采集完成后自动再按一次还原。
用法: python tools/panel_render.py
产物: docs/panel.png（README 用，已带圆角）
"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import time
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


def toggle_desktop():
    """Win+D：显示/还原桌面。截玻璃底前清空背景，采完还原窗口。"""
    user32.keybd_event(0x5B, 0, 0, 0)    # LWIN down
    user32.keybd_event(0x44, 0, 0, 0)    # D down
    user32.keybd_event(0x44, 0, 2, 0)    # D up
    user32.keybd_event(0x5B, 0, 2, 0)    # LWIN up


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

    panel = m.GlassPanel(app)
    win, cv = panel.win, panel.canvas
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

    # 3) logo 位图不会随 scale 放大，换成 SCALE 倍原图
    photos = [i for i in cv.find_withtag("all") if cv.type(i) == "image"]
    if photos:
        from PIL import Image as PImage, ImageTk
        item = photos[0]
        x0, y0 = cv.coords(item)
        anchor = cv.itemcget(item, "anchor") or "w"
        cv.delete(item)
        img = PImage.open(m.resource_path("assets", "logo.png")).convert("RGBA")
        px = round(17 * SCALE)
        panel._photo = ImageTk.PhotoImage(img.resize((px, px), PImage.LANCZOS))
        cv.create_image(x0, y0, anchor=anchor, image=panel._photo)

    # 4) 窗口放大并重新锚定工作区右下角
    wa = m.work_area()
    win.geometry("%dx%d+%d+%d" % (sw, sh, wa.right - sw - 12, wa.bottom - sh - 12))
    cv.configure(width=sw, height=sh)
    win.update_idletasks()

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

    toggle_desktop()          # 最小化全部窗口，桌面作为玻璃背景
    time.sleep(1.0)           # 等最小化动画结束

    panel, grab, root = hi_res_panel(m)

    def finish():
        img = round_corners(grab())
        img.save(OUT, optimize=True)
        print("panel ->", OUT, img.size)
        panel.close()
        root.destroy()
        time.sleep(0.3)
        toggle_desktop()      # 还原窗口

    root.after(400, finish)   # 等玻璃合成稳定再采集
    root.mainloop()


if __name__ == "__main__":
    main()
