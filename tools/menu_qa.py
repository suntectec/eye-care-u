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
    # 造一个“有新版”状态：更新条应出现（999.0.0 恒大于 APP_VERSION）；
    # 同时清掉上次运行可能留下的已关闭标记，保证用例可重复
    app.settings["update_latest"] = "999.0.0"
    app.settings["update_dismissed"] = ""

    def fake_save():
        app.save_count += 1
        m.save_settings(app.settings)
    app.save_action = fake_save

    # 不要 stub 掉 GlassPanel._on_focus_out！面板“失焦即收起”正是真实使用路径，
    # 曾经被 stub 后漏测出“第一次按下就把面板 destroy 掉”的严重 bug
    # （canvas.focus_set 触发 Toplevel FocusOut）。现在由 real_check 显式断言。
    panel = m.GlassPanel(app)

    def ensure_panel():
        if app._panel is not None and app._panel.win.winfo_exists():
            return app._panel
        app._panel = m.GlassPanel(app)
        return app._panel

    def grab_shot():
        # QA 留档截图（PrintWindow，内容清晰）→ tools/menu_shot.png。
        # 注意不要写 docs/panel.png——README 用图由 tools/panel_render.py
        # 以 2.5 倍高清渲染生成，直接覆盖会把低分辨率版本写回去。
        p = ensure_panel()
        hwnd = m.native_hwnd(p.win)
        rect = wt.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        img = grab_img(rect, hwnd)
        img.save(os.path.join(ROOT, "tools", "menu_shot.png"))
        print("shot -> tools/menu_shot.png", img.size)

    def click_save():
        # 合成点击 Save 按钮中心：验证命中区 + 保存逻辑
        app.settings["r"] = 123
        p = ensure_panel()
        p.canvas.event_generate("<Button-1>", x=119, y=248)

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
        user32.SetCursorPos(rect.left + 119, rect.top + 248)
        time.sleep(0.05)
        user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
        time.sleep(0.05)
        user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP

    def real_check():
        # 回归断言：真实按下后面板必须还在。若被自己关掉，滑杆就永远拖不动
        # （press 关掉窗口，后续 <B1-Motion> 无处可去），表现为“无法调色”
        alive = app._panel is not None and app._panel.win.winfo_exists()
        print("panel survives click test:", "PASS" if alive else "FAIL")
        print("click-through test:", "PASS" if app.save_count >= 2 else "FAIL",
              "save_count =", app.save_count)

    def check_strip_shown():
        # 更新条：设置里有更大版本号时必须处于“可显示”状态
        print("update strip shown test:",
              "PASS" if app._panel._update_available() else "FAIL")

    def click_dismiss():
        # 合成点击更新条 ✕：验证命中区 + 关闭逻辑。
        # 不点条身——那条路径会真实打开浏览器
        app._panel.canvas.event_generate("<Button-1>", x=410, y=284)

    def check_dismiss():
        p = app._panel
        ok = (app.settings.get("update_dismissed") == "999.0.0"
              and p is not None and not p._update_available())
        print("update strip dismiss test:", "PASS" if ok else "FAIL")

    def finish():
        p = ensure_panel()
        grab_shot()   # 测试结束后再抓一张留档（面板状态可能已被测试改动）
        p.close()
        root.destroy()

    root.after(450, grab_shot)
    root.after(550, check_strip_shown)
    root.after(700, click_save)
    root.after(950, lambda: check_file(123))
    root.after(1200, real_click)
    root.after(1550, real_check)
    root.after(1750, click_dismiss)
    root.after(1900, check_dismiss)
    root.after(2000, lambda: root.after(0, finish))
    root.mainloop()


if __name__ == "__main__":
    main()
