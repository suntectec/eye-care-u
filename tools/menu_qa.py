# -*- coding: utf-8 -*-
"""托盘控制面板 QA：渲染截图（README 用）+ Save 合成点击 + 真实鼠标穿透测试。
用法: .build-venv/Scripts/python tools/menu_qa.py
产物: docs/panel.png（面板截图，供 README 使用）、tools/menu_shot.png（QA 留档）
"""
import ctypes
import ctypes.wintypes as wt
import os
import queue
import sys
import threading
import time

ctypes.windll.user32.SetProcessDPIAware()   # 物理像素坐标
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def grab_img(rect, hwnd):
    """PrintWindow 渲染窗口自身表面，返回 PIL Image（RGB，窗口原始尺寸）。
    不要用屏幕 DC 的 CAPTUREBLT BitBlt——accent 模糊层会被一起合成进截图，
    内容发糊（实机显示不受影响，纯属采集伪影）。"""
    w, h = rect.right - rect.left, rect.bottom - rect.top
    sdc = user32.GetDC(0)
    mdc = gdi32.CreateCompatibleDC(sdc)
    bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
    gdi32.SelectObject(mdc, bmp)
    user32.PrintWindow(hwnd, mdc, 2)   # PW_RENDERFULLCONTENT

    class H(ctypes.Structure):
        _fields_ = [("s", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG),
                    ("p", wt.WORD), ("b", wt.WORD), ("c", wt.DWORD),
                    ("si", wt.DWORD), ("x", wt.LONG), ("y", wt.LONG),
                    ("u", wt.DWORD), ("i", wt.DWORD)]

    class BI(ctypes.Structure):
        _fields_ = [("h", H), ("colors", wt.DWORD * 3)]

    bi = BI()
    bi.h.s, bi.h.w, bi.h.h, bi.h.p, bi.h.b = ctypes.sizeof(H), w, -h, 1, 32
    buf = (ctypes.c_ubyte * (w * h * 4))()
    gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
    from PIL import Image
    img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
    return img.convert("RGB")


def main():
    import tkinter as tk
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    import eye_care_u as m
    m.tk = tk   # main() 里才注入，这里手动补上

    root = tk.Tk()
    root.withdraw()

    class FakeApp:
        pass

    app = FakeApp()
    app.root = root
    app.on = True                      # 运行中状态
    app.settings = m.load_settings()
    # 截图展示真实使用状态：优先读取 dist/ 里的用户实际配色
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
    app.save_count = 0

    def fake_save():
        app.save_count += 1
        m.save_settings(app.settings)
    app.save_action = fake_save

    # QA 运行在活桌面上，焦点随时会被其他应用抢走；禁用 FocusOut 自动收起，
    # 面板的开/关由测试显式控制
    m.GlassPanel._on_focus_out = lambda self, _e: None

    panel = m.GlassPanel(app)

    def ensure_panel():
        if app._panel is not None and app._panel.win.winfo_exists():
            return app._panel
        app._panel = m.GlassPanel(app)
        return app._panel

    def grab_shot():
        # PrintWindow 渲染窗口自身表面：内容清晰且不受 DWM 过渡动画影响；
        # LANCZOS 2x 放大保证 README 在高 DPI 屏上的展示清晰度。
        # 玻璃背景在窗口表面呈深色（模糊背景由 DWM 实时合成，不入截图）。
        p = ensure_panel()
        hwnd = m.native_hwnd(p.win)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        img = grab_img(rect, hwnd)
        from PIL import Image
        big = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        big.save(os.path.join(ROOT, "docs", "panel.png"))
        img.save(os.path.join(ROOT, "tools", "menu_shot.png"))
        print("screenshot -> docs/panel.png", big.size)

    def click_save():
        # 合成点击 Save 按钮中心：验证命中区 + 保存逻辑
        app.settings["r"] = 123
        p = ensure_panel()
        p.canvas.event_generate("<Button-1>", x=119, y=254)

    def check_file(expect):
        try:
            with open(m.SETTINGS_FILE, "r", encoding="utf-8") as f:
                saved = f.read()
            ok = '"r": %d' % expect in saved
            print("save file test:", "PASS" if ok else "FAIL")
        except Exception as e:
            print("save file test FAIL:", e)

    def real_click():
        # 真实鼠标点击 Save 中心：验证玻璃底（黑色区域）不再鼠标穿透
        p = ensure_panel()
        hwnd = m.native_hwnd(p.win)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        user32.SetCursorPos(rect.left + 119, rect.top + 254)
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP

    def real_check():
        print("click-through test:", "PASS" if app.save_count >= 2 else "FAIL",
              "save_count =", app.save_count)

    def finish():
        p = ensure_panel()
        grab_shot()   # 测试结束后再抓一张留档（面板状态可能已被测试改动）
        p.close()
        root.destroy()

    root.after(450, grab_shot)
    root.after(700, click_save)
    root.after(950, lambda: check_file(123))
    root.after(1200, real_click)
    root.after(1550, real_check)
    root.after(1900, lambda: root.after(0, finish))
    root.mainloop()


if __name__ == "__main__":
    main()
