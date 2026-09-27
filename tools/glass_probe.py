# -*- coding: utf-8 -*-
"""玻璃策略矩阵实测：亮色背景上并排 6 种半透明方案，一眼看出哪种真的有亚克力。
产物: tools/glass_matrix.png
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

ctypes.windll.user32.SetProcessDPIAware()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

import tkinter as tk

import eye_care_u as m

m.tk = tk

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

MAGIC = m.GLASS_MAGIC
CHROMA = m.GLASS_MAGIC


def accent(hwnd, state, argb, flags=0, dwm_steps=False):
    """可调参的 accent 调用；dwm_steps=True 时先走 Dwm 两步（完整配方）"""
    if dwm_steps:
        region = gdi32.CreateRectRgn(0, 0, -1, -1)
        if not region:
            return False
        bb = m.DWM_BLURBEHIND(0x1 | 0x2 | 0x4, True, region, True)
        if dwmapi(hwnd, bb) != 0:
            return False
        mg = m.MARGINS(-1, -1, -1, -1)
        if ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(
                wt.HWND(hwnd), ctypes.byref(mg)) != 0:
            return False
    acc = m.ACCENT_POLICY(state, flags, argb, 0, 0)
    data = m.WCA_DATA(19, ctypes.cast(ctypes.byref(acc), ctypes.c_void_p),
                      ctypes.sizeof(acc))
    user32.SetWindowCompositionAttribute.argtypes = [wt.HWND, ctypes.c_void_p]
    return bool(user32.SetWindowCompositionAttribute(wt.HWND(hwnd),
                                                     ctypes.byref(data)))


def dwmapi(hwnd, bb):
    return ctypes.windll.dwmapi.DwmEnableBlurBehindWindow(
        wt.HWND(hwnd), ctypes.byref(bb))


STRATS = [
    ("1 accent a=.59", dict(state=4, argb=0x96181413)),
    ("2 accent a=.23", dict(state=4, argb=0x3A181413)),
    ("3 full   a=.59", dict(state=4, argb=0x96181413, dwm_steps=True)),
    ("4 bluronly   ", dict(state=3, argb=0x00000000)),
    ("5 blur+extend", dict(state=3, argb=0x00000000, dwm_steps=True)),
    ("6 solid      ", None),
]


def main():
    root = tk.Tk()
    root.withdraw()

    # 亮色底板：彩色条纹 + 大字，亚克力模糊效果一目了然
    base = tk.Toplevel(root)
    base.geometry("1240x400+80+120")
    base.configure(bg="#E8E2D0")
    base.attributes("-topmost", True)
    cv = tk.Canvas(base, width=1240, height=400, bd=0, highlightthickness=0,
                   bg="#E8E2D0")
    cv.pack()
    colors = ["#D94F4F", "#E8A33D", "#3D9BE8", "#3DC974", "#8A5FE8", "#E83D9E"]
    for i, c in enumerate(colors):
        cv.create_rectangle(60 + i * 190, 40, 60 + i * 190 + 150, 340,
                            fill=c, outline="")
    for y in range(60, 340, 28):
        cv.create_text(620, y, text="BACKDROP 模糊测试 0123 ABC",
                       fill="#20242C", font=("Consolas", 15, "bold"))
    base.update_idletasks()

    wins = []
    for i, (label, cfg) in enumerate(STRATS):
        win = tk.Toplevel(root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.geometry("190x240+%d+%d" % (100 + i * 196, 150))
        win.configure(bg=MAGIC)
        c2 = tk.Canvas(win, width=190, height=240, bd=0,
                       highlightthickness=0, bg=MAGIC)
        c2.pack()
        c2.create_rectangle(25, 60, 165, 140, fill="#FFFFFF", outline="")
        c2.create_text(95, 100, text="WHITE", fill="#D94F4F",
                       font=("Consolas", 12, "bold"))
        c2.create_text(95, 26, text=label.strip(), fill="#F2F3F7",
                       font=("Microsoft YaHei UI", 9, "bold"))
        win.update_idletasks()
        hwnd = m.native_hwnd(win)
        if cfg is None:
            c2.configure(bg="#131418")
            win.configure(bg="#131418")
            res = "solid"
        else:
            res = accent(hwnd, **cfg)
            win.attributes("-transparentcolor", CHROMA)
        wins.append((label, res))
        print(label.strip(), "->", res)

    def finish():
        rect = wt.RECT(80, 120, 80 + 1240, 120 + 400)
        w, h = rect.right - rect.left, rect.bottom - rect.top
        sdc = user32.GetDC(0)
        mdc = gdi32.CreateCompatibleDC(sdc)
        bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
        gdi32.SelectObject(mdc, bmp)
        gdi32.BitBlt(mdc, 0, 0, w, h, sdc, rect.left, rect.top,
                     0x00CC0020 | 0x40000000)   # CAPTUREBLT 含分层窗口
        bi = m.WCA_DATA  # noqa
        from PIL import Image

        class H(ctypes.Structure):
            _fields_ = [("s", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG),
                        ("p", wt.WORD), ("b", wt.WORD), ("c", wt.DWORD),
                        ("si", wt.DWORD), ("x", wt.LONG), ("y", wt.LONG),
                        ("u", wt.DWORD), ("i", wt.DWORD)]

        class BI(ctypes.Structure):
            _fields_ = [("h", H), ("colors", wt.DWORD * 3)]

        bi2 = BI()
        bi2.h.s, bi2.h.w, bi2.h.h, bi2.h.p, bi2.h.b = ctypes.sizeof(H), w, -h, 1, 32
        buf = (ctypes.c_ubyte * (w * h * 4))()
        gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi2), 0)
        img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
        img.convert("RGB").save(os.path.join(ROOT, "tools", "glass_matrix.png"))
        print("saved tools/glass_matrix.png")
        for w2 in wins:
            pass
        base.destroy()
        root.destroy()

    root.after(1200, finish)
    root.mainloop()


if __name__ == "__main__":
    main()
