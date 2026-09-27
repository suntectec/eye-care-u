# -*- coding: utf-8 -*-
"""一键全屏查看：启动程序 → 左键消息开设置窗 → 右键消息开托盘菜单 → 全屏抓图。
产物: tools/fullview.png（整屏，含设置窗口 + 托盘菜单的真实合成效果）
"""
import ctypes
import ctypes.wintypes as wt
import os
import subprocess
import sys
import time

ctypes.windll.user32.SetProcessDPIAware()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "tools", "fullview.png")
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32

WM_APP_TRAY = 0x8001
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205

hwnd = user32.FindWindowW("EyeCareU_TrayWnd", None)
if not hwnd:
    subprocess.Popen([os.path.join(ROOT, "dist", "eye-care-u.exe")])
    for _ in range(40):
        hwnd = user32.FindWindowW("EyeCareU_TrayWnd", None)
        if hwnd:
            break
        time.sleep(0.15)
print("tray hwnd:", hwnd)
if not hwnd:
    sys.exit(1)
time.sleep(1.0)

# 右键 → 托盘控制面板（左键同为 toggle，这里只发一次避免开了又关）
user32.PostMessageW(wt.HWND(hwnd), wt.UINT(WM_APP_TRAY),
                    wt.WPARAM(0), wt.LPARAM(WM_RBUTTONUP))
time.sleep(1.0)

w = user32.GetSystemMetrics(0)
h = user32.GetSystemMetrics(1)
sdc = user32.GetDC(0)
mdc = gdi32.CreateCompatibleDC(sdc)
bmp = gdi32.CreateCompatibleBitmap(sdc, w, h)
gdi32.SelectObject(mdc, bmp)
ok = gdi32.BitBlt(mdc, 0, 0, w, h, sdc, 0, 0, 0x00CC0020 | 0x40000000)


class H(ctypes.Structure):
    _fields_ = [("s", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG), ("p", wt.WORD),
                ("b", wt.WORD), ("c", wt.DWORD), ("si", wt.DWORD),
                ("x", wt.LONG), ("y", wt.LONG), ("u", wt.DWORD), ("i", wt.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("h", H), ("colors", wt.DWORD * 3)]


bi = BI()
bi.h.s, bi.h.w, bi.h.h, bi.h.p, bi.h.b = ctypes.sizeof(H), w, -h, 1, 32
buf = (ctypes.c_ubyte * (w * h * 4))()
gdi32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bi), 0)
from PIL import Image
img = Image.frombuffer("RGBA", (w, h), bytes(buf), "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("fullview ok:", ok, img.size, "->", OUT)
