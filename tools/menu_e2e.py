# -*- coding: utf-8 -*-
"""托盘菜单端到端验证：定位托盘图标 → 模拟右键 → 抓菜单弹出区域。
需先正常运行 dist/eye-care-u.exe（托盘已就绪）。
产物: tools/menu_e2e.png
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys
import time

ctypes.windll.user32.SetProcessDPIAware()

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "menu_e2e.png")
user32 = ctypes.windll.user32
shell32 = ctypes.windll.shell32
gdi32 = ctypes.windll.gdi32

# 1) 找托盘图标窗口（自绘 TrayIcon 的消息窗口）
hwnd = user32.FindWindowW("EyeCareU_TrayWnd", None)
print("tray hwnd:", hwnd)
if not hwnd:
    sys.exit(1)


class NIID(ctypes.Structure):
    _fields_ = [("cbSize", wt.DWORD), ("hWnd", wt.HWND), ("uID", wt.UINT),
                ("guidItem", ctypes.c_ubyte * 16)]


niid = NIID()
niid.cbSize = ctypes.sizeof(niid)
niid.hWnd = wt.HWND(hwnd)
niid.uID = 1
rect = wt.RECT()
hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(niid), ctypes.byref(rect))
print("icon rect:", rect.left, rect.top, rect.right, rect.bottom, "hr:", hr)
if hr != 0:
    sys.exit(1)

# 2) 模拟右键点击图标中心
cx, cy = (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2
user32.SetCursorPos(cx, cy)
user32.mouse_event(0x0008, 0, 0, 0, 0)   # RIGHTDOWN
time.sleep(0.06)
user32.mouse_event(0x0010, 0, 0, 0, 0)   # RIGHTUP
time.sleep(0.7)

# 3) 抓菜单应在的区域（图标上方，含玻璃背景合成效果）
menu_w, menu_h = 320, 250
grab_x, grab_y = rect.right - menu_w + 30, rect.top - menu_h - 6
sdc = user32.GetDC(0)
mdc = gdi32.CreateCompatibleDC(sdc)
bmp = gdi32.CreateCompatibleBitmap(sdc, menu_w, menu_h)
gdi32.SelectObject(mdc, bmp)
ok = gdi32.BitBlt(mdc, 0, 0, menu_w, menu_h, sdc, grab_x, grab_y,
                  0x00CC0020 | 0x40000000)   # SRCCOPY | CAPTUREBLT
buf = (ctypes.c_ubyte * (menu_w * menu_h * 4))()


class H(ctypes.Structure):
    _fields_ = [("s", wt.DWORD), ("w", wt.LONG), ("h", wt.LONG), ("p", wt.WORD),
                ("b", wt.WORD), ("c", wt.DWORD), ("si", wt.DWORD),
                ("x", wt.LONG), ("y", wt.LONG), ("u", wt.DWORD), ("i", wt.DWORD)]


class BI(ctypes.Structure):
    _fields_ = [("h", H), ("colors", wt.DWORD * 3)]


bi = BI()
bi.h.s, bi.h.w, bi.h.h, bi.h.p, bi.h.b = ctypes.sizeof(H), menu_w, -menu_h, 1, 32
gdi32.GetDIBits(mdc, bmp, 0, menu_h, buf, ctypes.byref(bi), 0)
from PIL import Image
img = Image.frombuffer("RGBA", (menu_w, menu_h), bytes(buf), "raw", "BGRA", 0, 1)
img.convert("RGB").save(OUT)
print("menu e2e shot ok:", ok, "->", OUT)

# 4) 按 Esc 关闭菜单（焦点在菜单上时生效；兜底：点空白处）
user32.SetCursorPos(cx, cy - 300)
user32.mouse_event(0x0002, 0, 0, 0, 0)   # LEFTDOWN
user32.mouse_event(0x0004, 0, 0, 0, 0)   # LEFTUP
