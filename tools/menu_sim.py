# -*- coding: utf-8 -*-
"""托盘菜单逻辑验证：直接向托盘窗口投递 WM_APP_TRAY/WM_RBUTTONUP 消息
（绕过鼠标定位，专测 wnd_proc → 队列 → 菜单弹出的应用逻辑），
然后抓菜单应在的区域。需先正常运行 dist/eye-care-u.exe。
产物: tools/menu_sim.png
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

ctypes.windll.user32.SetProcessDPIAware()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_sim.png")
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32

WM_APP_TRAY = 0x8001
WM_RBUTTONUP = 0x0205

hwnd = user32.FindWindowW("EyeCareU_TrayWnd", None)
print("tray hwnd:", hwnd)
if not hwnd:
    sys.exit(1)


class NIID(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("guidItem", ctypes.c_ubyte * 16)]


user32.PostMessageW(wt.HWND(hwnd), wt.UINT(WM_APP_TRAY),
                    wt.WPARAM(0), wt.LPARAM(WM_RBUTTONUP))
time.sleep(0.8)

# 面板锚定在工作区（不含任务栏）右下角：440×296，抓该区域
wa = wt.RECT()
user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(wa), 0)
gw, gh = 470, 330
gx, gy = wa.right - gw - 4, wa.bottom - gh - 4
sdc = user32.GetDC(0)
mdc = gdi32.CreateCompatibleDC(sdc)
bmp = gdi32.CreateCompatibleBitmap(sdc, gw, gh)
gdi32.SelectObject(mdc, bmp)
ok = gdi32.BitBlt(mdc, 0, 0, gw, gh, sdc, gx, gy,
                  0x00CC0020 | 0x40000000)
buf = (ctypes.c_ubyte * (gw * gh * 4))()


class H(ctypes.Structure):
    _fields_ = [("s", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG), ("p", wt.WORD),
                ("b", wt.WORD), ("c", wt.DWORD), ("si", wt.DWORD),
                ("x", wt.LONG), ("y", wt.LONG), ("u", wt.DWORD), ("i", wt.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("h", H), ("colors", wt.DWORD * 3)]


bi = BI()
bi.h.s, bi.h.w, bi.h.h, bi.h.p, bi.h.b = ctypes.sizeof(H), gw, -gh, 1, 32
gdi32.GetDIBits(mdc, bmp, 0, gh, buf, ctypes.byref(bi), 0)
from PIL import Image
img = Image.frombuffer("RGBA", (gw, gh), bytes(buf), "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("menu sim shot ok:", ok, "->", OUT)

# Esc 关闭菜单（若已打开）
user32.keybd_event(0x1B, 0, 0, 0)
user32.keybd_event(0x1B, 0, 2, 0)
