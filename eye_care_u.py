# -*- coding: utf-8 -*-
"""
Eye Care U（eye-care-u）—— Windows 系统托盘版护眼工具

原理：改写显卡驱动层 Gamma Ramp 给显示器物理输出染色（无遮罩窗口、零输入干扰，
      与 f.lux / Windows 夜间模式同层），任何分辨率/宽高比/多显示器全覆盖。

形态：后台驻留，任务栏右下角（系统托盘）显示图标。
      左键/右键托盘图标：弹出玻璃控制面板（Red/Green/Blue/Strength 滑杆 + Save/Exit）
      拖动滑杆即时染色，所见即所得；Save 保存设置；点面板外部或 Esc 关闭
      托盘悬停提示：Eye Care U
      退出唯一入口：面板 Exit 按钮（退出前恢复原色彩）

界面：托盘面板为亚克力半透明玻璃风格（方案 B 玄青极简），
      老系统不支持时自动回退纯色深底，功能不受影响。

构建：build.bat 一键打包（自动从 assets/logo.png 生成多尺寸 ico 再打包）；
      手动：先 python tools/make_ico.py 生成 assets/logo.ico（不入库），再
            PyInstaller --onefile --noconsole --name eye-care-u --icon assets/logo.ico
            --add-data "assets/logo.png;assets" eye_care_u.py
"""

import ctypes
import json
import math
import os
import queue
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes

APP_NAME = "Eye Care U"
APP_VERSION = "1.5.0"    # 发版时必须与 tag 同步更新（release.yml 有校验步骤）
PID_FILE = os.path.join(tempfile.gettempdir(), "eye_care_u.pid")
STOP_FILE = os.path.join(tempfile.gettempdir(), "eye_care_u.stop")

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "eye_care_u_error.log")
SETTINGS_FILE = os.path.join(BASE_DIR, "eye_care_u_settings.json")

# 暖琥珀 #FFD2A5（红通道零损失，压蓝为主，f.lux/夜间模式同源的温和色温）
DEFAULTS = {"r": 255, "g": 210, "b": 165, "strength": 0.5,
            # 新版本感知：上次检查时间戳 / 已知最新版号 / 用户已关闭提醒的版号
            "update_check_at": 0.0, "update_latest": "", "update_dismissed": ""}
REAPPLY_SECONDS = 5      # 周期重刷 Gamma，防被游戏/其他软件重置；0 = 关闭

RELEASES_PAGE = "https://github.com/suntectec/eye-care-u/releases/latest"
RELEASES_API = "https://api.github.com/repos/suntectec/eye-care-u/releases/latest"
UPDATE_CHECK_DELAY = 30        # 启动后延迟首次检查，避开启动关键路径
UPDATE_CHECK_INTERVAL = 3600   # 节流：最多每小时匿名请求一次

# ---- 配色（方案 B 玄青极简 · 半透明玻璃）----
# 玻璃原理：DWM 玻璃配方下 GDI 的纯黑像素渲染为透明（"黑色即玻璃"），
# 且窗口命中测试与像素内容无关（整窗可点）——不能用 -transparentcolor
# 色键（键色像素对鼠标同样穿透，导致面板点击穿模）。内容里避免绘制
# 纯 #000000。
GLASS_BG = "#000000"           # 画布底：渲染为 acrylic 玻璃，鼠标不穿透
PANEL_FALLBACK = "#131418"     # 玻璃不可用时的纯色回退
GLASS_TINT = "#262B33"         # acrylic 压暗色（DWM 侧 blur×(1-α) + 此色×α + 系统噪点）
GLASS_TINT_ALPHA = 0xA6        # 压暗强度 ≈65%：明显降透，亮色窗口垫底也不刺眼；
                               # 0=纯模糊（过透，已废弃试验），历史网点版见 963efef
TEXT_HI = "#F2F3F7"            # 主文字
TEXT_MD = "#A3A9B6"            # 次级文字（标签）
TRACK_C = "#31343D"            # 滑轨底
FILL_C = "#CDD1DA"             # 滑轨已填充段
KNOB_C = "#F2F4F8"             # 旋钮
SEC_BD = "#4A4E58"             # 按钮描边
SEC_BD_HOVER = "#71767F"       # 按钮描边（悬停）
RED = "#E5484D"                # Exit
UPDATE_C = "#FFD2A5"           # 更新条文字/圆点（与默认配色同源）
STRIP_BG = "#2A2520"           # 更新条底色
STRIP_BD = "#4A4034"           # 更新条描边
STRIP_BD_HOVER = "#6B5C49"     # 更新条描边（悬停）
DIVIDER_MID = (142, 150, 164)  # 分隔线中段（渐隐线最亮处）
DIVIDER_EDGE = (36, 41, 50)    # 分隔线两端（融进玻璃底）
PANEL_W, PANEL_H = 440, 296    # 托盘面板尺寸

user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001


def resource_path(*parts):
    """打包资源路径：exe 内取 _MEIPASS，源码模式取脚本目录"""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, *parts)


def ensure_single_instance():
    """命名互斥锁，防止重复运行多个实例抢 Gamma"""
    kernel32.CreateMutexW(None, True, "eye_care_u_single_instance_mutex")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


# ---------------- 显示设备与 Gamma 引擎 ----------------

class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class DISPLAY_DEVICE(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * 32),
        ("DeviceString", wintypes.WCHAR * 128),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * 128),
        ("DeviceKey", wintypes.WCHAR * 128),
    ]


class GAMMA_RAMP(ctypes.Structure):
    _fields_ = [
        ("Red", wintypes.WORD * 256),
        ("Green", wintypes.WORD * 256),
        ("Blue", wintypes.WORD * 256),
    ]


gdi32.CreateDCW.restype = wintypes.HDC
gdi32.CreateDCW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR]
gdi32.DeleteDC.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.GetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
gdi32.SetDeviceGammaRamp.argtypes = [wintypes.HDC, ctypes.c_void_p]
user32.EnumDisplayDevicesW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD,
    ctypes.POINTER(DISPLAY_DEVICE), wintypes.DWORD,
]


def desktop_devices():
    """枚举所有已连接到桌面的显示设备（与分辨率/宽高比无关，天然全屏）"""
    names = []
    i = 0
    while True:
        disp = DISPLAY_DEVICE()
        disp.cb = ctypes.sizeof(DISPLAY_DEVICE)
        if not user32.EnumDisplayDevicesW(None, i, ctypes.byref(disp), 0):
            break
        if disp.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP:
            names.append(disp.DeviceName)
        i += 1
    return names


def build_tinted_ramp(r, g, b, strength):
    s = max(0.0, min(1.0, strength))
    ramp = GAMMA_RAMP()
    for i in range(256):
        base = i * 65535 // 255
        ramp.Red[i] = min(65535, int(base * ((1.0 - s) + s * r / 255.0)))
        ramp.Green[i] = min(65535, int(base * ((1.0 - s) + s * g / 255.0)))
        ramp.Blue[i] = min(65535, int(base * ((1.0 - s) + s * b / 255.0)))
    return ramp


ORIGINAL = {}
FAILED = []


def apply_tint(ramp, save_original=True):
    ok = 0
    for name in desktop_devices():
        if name in FAILED:
            continue
        hdc = gdi32.CreateDCW(None, name, None, None)
        if not hdc:
            continue
        try:
            if save_original and name not in ORIGINAL:
                orig = GAMMA_RAMP()
                if not gdi32.GetDeviceGammaRamp(hdc, ctypes.byref(orig)):
                    FAILED.append(name)
                    continue
                ORIGINAL[name] = orig
            if gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(ramp)):
                ok += 1
        finally:
            gdi32.DeleteDC(hdc)
    return ok


def restore():
    for name, orig in ORIGINAL.items():
        hdc = gdi32.CreateDCW(None, name, None, None)
        if hdc:
            try:
                gdi32.SetDeviceGammaRamp(hdc, ctypes.byref(orig))
            finally:
                gdi32.DeleteDC(hdc)
    ORIGINAL.clear()


def load_settings():
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {k: type(v)(data.get(k, v)) for k, v in DEFAULTS.items()}
    except Exception:
        return dict(DEFAULTS)


def save_settings(s):
    try:
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def log_error(msg):
    print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%Y-%m-%d %H:%M:%S ") + msg + "\n")
    except OSError:
        pass


def version_gt(a, b):
    """版本号比较 a > b；解析失败一律 False（宁可漏提示，不误报）"""
    def parse(v):
        out = []
        for part in str(v).strip().lstrip("vV").split("."):
            digits = ""
            for ch in part:
                if ch.isdigit():
                    digits += ch
                else:
                    break
            if not digits:
                return None
            out.append(int(digits))
        while len(out) < 3:
            out.append(0)
        return tuple(out[:3])
    pa, pb = parse(a), parse(b)
    return pa is not None and pb is not None and pa > pb


def fetch_latest_version(timeout=5):
    """匿名查询 GitHub 最新 Release 版本号；任何失败返回 None（静默，绝不打扰）"""
    try:
        req = urllib.request.Request(
            RELEASES_API, headers={"User-Agent": "%s/%s" % (APP_NAME, APP_VERSION)})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            tag = str(json.load(resp).get("tag_name", "")).strip().lstrip("vV")
        return tag or None
    except Exception:
        return None


# ---------------- 玻璃背景（blur-behind，参考 token-monitor windowsBackdrop.js） ----------------

class ACCENT_POLICY(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_uint),
        ("AccentFlags", ctypes.c_uint),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_uint),
        ("Blend", ctypes.c_uint),
    ]


class WCA_DATA(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.c_void_p),
        ("SizeOfData", ctypes.c_size_t),
    ]


class DWM_BLURBEHIND(ctypes.Structure):
    _fields_ = [
        ("dwFlags", wintypes.DWORD),
        ("fEnable", wintypes.BOOL),
        ("hRgnBlur", wintypes.HANDLE),
        ("fTransitionOnMaximized", wintypes.BOOL),
    ]


class MARGINS(ctypes.Structure):
    _fields_ = [
        ("cxLeftWidth", ctypes.c_int),
        ("cxRightWidth", ctypes.c_int),
        ("cyTopHeight", ctypes.c_int),
        ("cyBottomHeight", ctypes.c_int),
    ]


def native_hwnd(widget):
    """Tk 控件对应的根级 Win32 窗口句柄"""
    widget.update_idletasks()
    hwnd = user32.GetAncestor(widget.winfo_id(), 2)   # GA_ROOT
    return hwnd or widget.winfo_id()


def enable_glass(hwnd):
    """玻璃背景完整配方（Win10/11 通用）：
    1) DwmEnableBlurBehindWindow：空区域 (0,0,-1,-1) 启用 blur-behind
    2) DwmExtendFrameIntoClientArea：margins 全 -1，玻璃延伸到整个客户区
    3) ACCENT_ENABLE_ACRYLICBLURBEHIND：GradientColor 用 GLASS_TINT 配
       GLASS_TINT_ALPHA——压暗在 DWM 侧完成，面板=模糊+固定暗色+系统噪点
       （真 acrylic 质感，无内容侧网点），透度由 alpha 一处调节
    画布保持纯黑即玻璃；绝不用 -transparentcolor 色键（键色像素对鼠标
    穿透，导致面板点击穿模）。
    返回 True 表示系统支持；False 时调用方应回退纯色底。"""
    region = gdi32.CreateRectRgn(0, 0, -1, -1)
    if not region:
        return False
    try:
        bb = DWM_BLURBEHIND(0x1 | 0x2 | 0x4, True, region, True)
        if dwmapi.DwmEnableBlurBehindWindow(wintypes.HWND(hwnd),
                                            ctypes.byref(bb)) != 0:
            return False
        mg = MARGINS(-1, -1, -1, -1)
        if dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd),
                                               ctypes.byref(mg)) != 0:
            return False
        tint_abgr = (GLASS_TINT_ALPHA << 24) | int.from_bytes(
            bytes.fromhex(GLASS_TINT[1:]), "little")   # AABBGGRR
        acc = ACCENT_POLICY(4, 0, tint_abgr, 0, 0)     # 4 = ACCENT_ENABLE_ACRYLICBLURBEHIND
        data = WCA_DATA(19, ctypes.cast(ctypes.byref(acc), ctypes.c_void_p),
                        ctypes.sizeof(acc))
        user32.SetWindowCompositionAttribute.argtypes = [wintypes.HWND, ctypes.c_void_p]
        return bool(user32.SetWindowCompositionAttribute(wintypes.HWND(hwnd),
                                                         ctypes.byref(data)))
    finally:
        gdi32.DeleteObject(region)


def work_area():
    """工作区（不含任务栏）。exe 进程内与 Tk 坐标同属虚拟化空间，可直接混用"""
    rc = wintypes.RECT()
    user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rc), 0)  # SPI_GETWORKAREA
    return rc


# ---------------- 自绘托盘图标（ctypes，呼出玻璃控制面板） ----------------

WM_APP_TRAY = 0x8000 + 1
WM_LBUTTONUP = 0x0202
WM_RBUTTONUP = 0x0205
WM_DESTROY = 0x0002
WM_CLOSE = 0x0010
NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("hWnd", wintypes.HWND),
        ("uID", wintypes.UINT),
        ("uFlags", wintypes.UINT),
        ("uCallbackMessage", wintypes.UINT),
        ("hIcon", wintypes.HICON),
        ("szTip", wintypes.WCHAR * 128),
        ("dwState", wintypes.DWORD),
        ("dwStateMask", wintypes.DWORD),
        ("szInfo", wintypes.WCHAR * 256),
        ("uVersion", wintypes.UINT),
        ("szInfoTitle", wintypes.WCHAR * 64),
        ("dwInfoFlags", wintypes.DWORD),
        ("guidItem", ctypes.c_ubyte * 16),
    ]


WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                             wintypes.WPARAM, wintypes.LPARAM)


class WNDCLASSW(ctypes.Structure):
    """ctypes.wintypes 未提供 WNDCLASSW，自定义"""
    _fields_ = [
        ("style", wintypes.UINT),
        ("lpfnWndProc", WNDPROC),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HICON),
        ("hCursor", wintypes.HANDLE),
        ("hbrBackground", wintypes.HBRUSH),
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
    ]


class TrayIcon:
    """托盘图标：左键/右键都呼出玻璃控制面板，悬停提示 Eye Care U"""

    def __init__(self, actions):
        self.actions = actions
        self.hwnd = None
        self.hicon = None
        self.nid = None
        self._wndproc_ref = None

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def notify(self, title, msg):
        """托盘气泡（Win10+ 转为系统通知）：一次性新版提醒。
        NIIF_RESPECT_QUIET_TIME 遵守系统免打扰；失败静默不重试。"""
        if not self.nid:
            return
        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(nid)
        nid.hWnd = self.nid.hWnd
        nid.uID = self.nid.uID
        nid.uFlags = 0x10                          # NIF_INFO
        nid.szInfo = msg
        nid.szInfoTitle = title
        nid.dwInfoFlags = 0x1 | 0x80               # NIIF_INFO | NIIF_RESPECT_QUIET_TIME
        ctypes.windll.shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(nid))

    def _make_ico(self):
        """从打包的 logo.png 生成托盘用 ico（16/32px），路径同时供窗口图标使用"""
        try:
            from PIL import Image
            img = Image.open(resource_path("assets", "logo.png")).convert("RGBA")
            path = os.path.join(tempfile.gettempdir(), "eye_care_u_tray.ico")
            img.save(path, format="ICO",
                     sizes=[(16, 16), (32, 32), (48, 48)])
            return path
        except Exception:
            return None

    def _run(self):
        user32.DefWindowProcW.restype = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT,
                                          wintypes.WPARAM, wintypes.LPARAM]

        def wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_APP_TRAY:
                ev = lparam & 0xFFFF
                if ev in (WM_LBUTTONUP, WM_RBUTTONUP):
                    self.actions.put("panel")
                return 0
            if msg == WM_DESTROY:
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)

        self._wndproc_ref = WNDPROC(wnd_proc)   # 防 GC 回收

        hinst = kernel32.GetModuleHandleW(None)
        wc = WNDCLASSW()
        wc.lpfnWndProc = self._wndproc_ref
        wc.hInstance = hinst
        wc.lpszClassName = "EyeCareU_TrayWnd"
        if not user32.RegisterClassW(ctypes.byref(wc)):
            return

        self.hwnd = user32.CreateWindowExW(
            0, "EyeCareU_TrayWnd", "EyeCareU_Tray", 0,
            0, 0, 0, 0, None, None, hinst, None)
        if not self.hwnd:
            return

        ico_path = self._make_ico()
        if ico_path:
            user32.LoadImageW.restype = wintypes.HICON
            self.hicon = user32.LoadImageW(None, ico_path, 1, 16, 16, 0x10)  # LR_LOADFROMFILE
        if not self.hicon:
            user32.LoadIconW.restype = wintypes.HICON
            self.hicon = user32.LoadIconW(None, wintypes.LPCWSTR(32512))     # IDI_APPLICATION

        nid = NOTIFYICONDATAW()
        nid.cbSize = ctypes.sizeof(nid)
        nid.hWnd = self.hwnd
        nid.uID = 1
        nid.uFlags = 0x1 | 0x2 | 0x4          # MESSAGE | ICON | TIP
        nid.uCallbackMessage = WM_APP_TRAY
        nid.hIcon = self.hicon
        nid.szTip = APP_NAME
        self.nid = nid
        shell32 = ctypes.windll.shell32
        shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(nid))

        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

        self._hide()

    def _hide(self):
        if self.nid is not None:
            shell32 = ctypes.windll.shell32
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self.nid))
            self.nid = None

    def remove(self):
        self._hide()
        if self.hwnd:
            user32.PostMessageW(self.hwnd, WM_CLOSE, 0, 0)


# ---------------- 托盘玻璃控制面板（状态 + 滑杆 + Save/Exit） ----------------

def round_rect(cv, x1, y1, x2, y2, r, **kw):
    """canvas 圆角矩形（smooth 多边形近似）"""
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2,
           x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return cv.create_polygon(pts, smooth=True, **kw)


class GlassPanel:
    """托盘控制面板：应用名/状态 + 遮罩色与强度滑杆 + 开关/退出。
    点外部或 Esc 关闭；拖动滑杆即时染色。"""

    def __init__(self, app):
        import tkinter.font as tkfont
        self.app = app
        w, h = PANEL_W, PANEL_H

        # 锚点：固定桌面右下角（工作区不含任务栏），与 Tk 坐标同空间
        wa = work_area()
        x = wa.right - w - 12
        y = wa.bottom - h - 12

        self.win = tk.Toplevel(app.root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        try:
            self.win.attributes("-toolwindow", True)   # 不在任务栏出现 Tk 图标
        except Exception:
            pass
        self.win.configure(bg=GLASS_BG)
        self.win.geometry("%dx%d+%d+%d" % (w, h, int(x), int(y)))

        self.canvas = tk.Canvas(self.win, width=w, height=h, bd=0,
                                highlightthickness=0, bg=GLASS_BG)
        self.canvas.pack()
        self.win.update_idletasks()

        hwnd = native_hwnd(self.win)
        self.glass_ok = enable_glass(hwnd)
        if not self.glass_ok:
            self.win.configure(bg=PANEL_FALLBACK)
            self.canvas.configure(bg=PANEL_FALLBACK)

        # 头部猫 logo（17px）：即"色块"本体——按当前配色做双色调染色，
        # 随滑杆实时变化（方案 A：一图两用）。缓存灰度+alpha 两级：
        # 全分辨率供 panel_render 放大，17px 供 draw 每次廉价重着色
        self._logo_hi = None
        self._logo_17 = None
        self._photo = None
        try:
            from PIL import Image as PImage
            img = PImage.open(resource_path("assets", "logo.png")).convert("RGBA")
            lum, alpha = img.convert("L"), img.split()[3]
            self._logo_hi = (lum, alpha)
            self._logo_17 = (lum.resize((17, 17), PImage.LANCZOS),
                             alpha.resize((17, 17), PImage.LANCZOS))
        except Exception:
            pass

        self.f_title = tkfont.Font(family="Microsoft YaHei UI", size=11, weight="bold")
        self.f_body = tkfont.Font(family="Microsoft YaHei UI", size=9)
        self.f_small = tkfont.Font(family="Microsoft YaHei UI", size=8)
        self.f_mono = tkfont.Font(family="Consolas", size=10, weight="bold")
        self.f_mono_s = tkfont.Font(family="Consolas", size=9)

        self.x0, self.x1 = 24, w - 24
        self.rows = [
            ("r", "Red", 0, 255, 84),
            ("g", "Green", 0, 255, 122),
            ("b", "Blue", 0, 255, 160),
            ("strength", "Strength", 0.0, 1.0, 198),
        ]
        self.tx0, self.tx1 = self.x0 + 72, self.x1 - 54
        self.btn_w = (self.x1 - self.x0 - 12) // 2
        self.btn_y0, self.btn_h = 228, 40
        self.strip_y0, self.strip_h = 277, 14    # 底部更新条（发现新版时出现）
        self.dragging = None
        self.hover_btn = None
        self.hover_zone = None
        self.saved_until = 0.0

        self.draw()
        self.win.deiconify()
        self.win.lift()
        self.win.focus_force()
        # 注意：不要用 grab_set_global——全局抓取下 Tk 走底层鼠标钩子，
        # 事件坐标按物理像素送达（×DPI 缩放），与虚拟化的绘制坐标错位，
        # 按钮命中区会相互"穿模"。改为 FocusOut + Esc 收起。
        self._opened_at = time.monotonic()

        self.canvas.bind("<Motion>", self._on_motion)
        self.canvas.bind("<Button-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.win.bind("<Escape>", lambda _e: self.close())
        self.win.bind("<FocusOut>", self._on_focus_out)

    # ---- 着色 ----
    def _tint_logo_img(self, size=17):
        """当前色双色调猫 logo（PIL Image）：亮部=当前色提亮 25%，暗部=当前色×0.3。
        PIL 缺失或异常时返回 None（头部退化为纯文字）"""
        if self._logo_hi is None:
            return None
        try:
            from PIL import Image, ImageOps
            if size == 17:
                lum, alpha = self._logo_17
            else:
                lum, alpha = self._logo_hi
                lum = lum.resize((size, size), Image.LANCZOS)
                alpha = alpha.resize((size, size), Image.LANCZOS)
            s = self.app.settings
            c = (int(s["r"]), int(s["g"]), int(s["b"]))
            hi = tuple(min(255, int(v + (255 - v) * 0.25)) for v in c)
            lo = tuple(int(v * 0.3) for v in c)
            img = ImageOps.colorize(lum, black=lo, white=hi).convert("RGBA")
            img.putalpha(alpha)
            return img
        except Exception:
            return None

    def _tint_photo(self):
        try:
            from PIL import ImageTk
            img = self._tint_logo_img(17)
            return ImageTk.PhotoImage(img) if img is not None else None
        except Exception:
            return None

    # ---- 绘制 ----
    def draw(self):
        cv = self.canvas
        cv.delete("all")
        s = self.app.settings

        # 玻璃底压暗在 DWM 侧完成（enable_glass 的 acrylic GradientColor），
        # 画布保持纯黑=玻璃。不画内容侧网点：点阵在渲染放大后显形，
        # 实机与 panel_render 难一致（f795a41 同因弃用 stipple 分隔线）

        # 头部：猫 logo（染当前色，即色块本体）+ 应用名 + 右侧 HEX 读数
        self._photo = self._tint_photo()
        if self._photo:
            cv.create_image(self.x0, 22, anchor="w", image=self._photo)
        # 版本号紧跟标题：用 bbox 取实际渲染边界（measure 不含 DPI 放大量，
        # 125% 缩放下会贴到标题上）
        t = cv.create_text(self.x0 + 26, 22, anchor="w", text=APP_NAME,
                           fill=TEXT_HI, font=self.f_title)
        tb = cv.bbox(t)
        cv.create_text((tb[2] if tb else self.x0 + 26 + 100) + 12, 22,
                       anchor="w", text="v" + APP_VERSION,
                       fill=TEXT_MD, font=self.f_small)
        tint = "#%02X%02X%02X" % (int(s["r"]), int(s["g"]), int(s["b"]))
        cv.create_text(self.x1, 22, anchor="e", text=tint,
                       fill=TEXT_HI, font=self.f_mono)

        # 分隔线：中间亮、两端渐隐进玻璃底。用纯色分段渐变而不用 stipple——
        # stipple 点阵不随 panel_render 的缩放变细，实机与渲染会不一致
        n_seg = 56
        step = (self.x1 - self.x0) / n_seg
        for i in range(n_seg):
            t = abs((i + 0.5) / n_seg * 2 - 1)   # 0=中段 1=两端
            col = "#%02X%02X%02X" % tuple(
                int(a + (b - a) * t) for a, b in zip(DIVIDER_MID, DIVIDER_EDGE))
            xa = self.x0 + i * step
            cv.create_line(xa, 54, xa + step, 54, fill=col, width=1)

        # 滑杆
        for key, label, lo, hi, yc in self.rows:
            cv.create_text(self.x0, yc, anchor="w", text=label,
                           fill=TEXT_MD, font=self.f_body)
            v = s[key]
            frac = (v - lo) / (hi - lo)
            kx = self.tx0 + frac * (self.tx1 - self.tx0)
            cv.create_line(self.tx0, yc, self.tx1, yc, fill=TRACK_C,
                           width=4, capstyle="round")
            if kx > self.tx0 + 2:
                cv.create_line(self.tx0, yc, kx, yc, fill=FILL_C,
                               width=4, capstyle="round")
            txt = "%d%%" % round(v * 100) if key == "strength" else "%d" % round(v)
            cv.create_text(self.x1, yc, anchor="e", text=txt,
                           fill=TEXT_HI, font=self.f_mono_s)
            cv.create_oval(kx - 7, yc - 7, kx + 7, yc + 7, fill=KNOB_C,
                           outline="")

        # 按钮：Save / Exit（同款描边风格，仅字体颜色区分）
        b_y1 = self.btn_y0 + self.btn_h
        bd_s = SEC_BD_HOVER if self.hover_btn == "save" else SEC_BD
        round_rect(cv, self.x0, self.btn_y0, self.x0 + self.btn_w, b_y1, 12,
                   fill="", outline=bd_s, width=1)
        save_txt = "Saved" if time.monotonic() < self.saved_until else "Save"
        cv.create_text(self.x0 + self.btn_w // 2, (self.btn_y0 + b_y1) // 2,
                       text=save_txt, fill=TEXT_HI, font=self.f_title)
        bd_q = SEC_BD_HOVER if self.hover_btn == "quit" else SEC_BD
        round_rect(cv, self.x0 + self.btn_w + 12, self.btn_y0, self.x1, b_y1, 12,
                   fill="", outline=bd_q, width=1)
        cv.create_text((self.x0 + self.btn_w + 12 + self.x1) // 2,
                       (self.btn_y0 + b_y1) // 2, text="Exit",
                       fill=RED, font=self.f_title)

        # 底部更新条：后台发现新版且未被用户关闭时出现，点击开下载页
        if self._update_available():
            sy0, sy1 = self.strip_y0, self.strip_y0 + self.strip_h
            bd = STRIP_BD_HOVER if self.hover_zone == "update" else STRIP_BD
            round_rect(cv, self.x0, sy0, self.x1, sy1, 7,
                       fill=STRIP_BG, outline=bd, width=1)
            mid = (sy0 + sy1) // 2
            cv.create_oval(self.x0 + 7, mid - 3, self.x0 + 13, mid + 3,
                           fill=UPDATE_C, outline="")
            cv.create_text(self.x0 + 22, mid, anchor="w",
                           text="新版本 v%s 可用 · 点击前往下载"
                                % self.app.settings["update_latest"],
                           fill=UPDATE_C, font=self.f_small)
            cv.create_text(self.x1 - 9, mid, anchor="e", text="✕",
                           fill=TEXT_MD, font=self.f_small)

    # ---- 交互 ----
    def _update_available(self):
        s = self.app.settings
        latest = s.get("update_latest", "")
        return (bool(latest) and latest != s.get("update_dismissed", "")
                and version_gt(latest, APP_VERSION))

    def _strip_at(self, x, y):
        return (self.x0 <= x <= self.x1
                and self.strip_y0 - 4 <= y <= self.strip_y0 + self.strip_h + 2)

    def _btn_at(self, x, y):
        """按钮命中区：覆盖整个按钮区块（含描边外扩），以两钮中点分界，互不重叠"""
        top, bottom = self.btn_y0 - 6, self.btn_y0 + self.btn_h + 6
        if top <= y <= bottom:
            mid = self.x0 + self.btn_w + 6          # 两钮间隙中点
            if self.x0 - 6 <= x < mid:
                return "save"
            if mid <= x <= self.x1 + 6:
                return "quit"
        return None

    def _row_at(self, x, y):
        for key, _label, lo, hi, yc in self.rows:
            if abs(y - yc) <= 11 and self.tx0 - 10 <= x <= self.tx1 + 10:
                return key, lo, hi, yc
        return None

    def _set_value(self, key, lo, hi, x):
        frac = max(0.0, min(1.0, (x - self.tx0) / (self.tx1 - self.tx0)))
        v = lo + frac * (hi - lo)
        if key != "strength":
            v = int(round(v))
        self.app.on_scale_key(key, v)

    def _on_press(self, e):
        try:
            self._on_press_inner(e)
        except Exception:
            # 窗口化 exe 里 Tk 回调异常默认静默，落盘便于排查
            import traceback
            log_error(traceback.format_exc())

    def _on_press_inner(self, e):
        # 点面板任意处都把焦点从 HEX 输入框移走（失焦回退无效输入）
        self.canvas.focus_set()
        # 更新条在按钮下方，命中带与按钮外扩带的少量重叠按“越低越靠条”处理
        if self._update_available() and self._strip_at(e.x, e.y):
            if e.x >= self.x1 - 22:      # ✕：只关闭当前版本的提醒
                self.app.settings["update_dismissed"] = \
                    self.app.settings["update_latest"]
                save_settings(self.app.settings)
                self.draw()
            else:
                webbrowser.open(RELEASES_PAGE)
            return
        btn = self._btn_at(e.x, e.y)
        if btn == "save":
            self.app.save_action()
            return
        if btn == "quit":
            self.close()
            self.app.actions.put("quit")
            return
        row = self._row_at(e.x, e.y)
        if row:
            self.dragging = row
            self._set_value(row[0], row[1], row[2], e.x)

    def _on_drag(self, e):
        if self.dragging:
            self._set_value(self.dragging[0], self.dragging[1], self.dragging[2], e.x)

    def _on_motion(self, e):
        zone = "update" if (self._update_available()
                            and self._strip_at(e.x, e.y)) else None
        btn = None if zone else self._btn_at(e.x, e.y)
        row = self._row_at(e.x, e.y)
        cursor = "hand2" if (zone or btn or row) else ""
        if self.canvas["cursor"] != cursor:
            self.canvas.configure(cursor=cursor)
        if btn != self.hover_btn or zone != self.hover_zone:
            self.hover_btn, self.hover_zone = btn, zone
            self.draw()
        elif self.dragging:
            self.draw()

    def _on_focus_out(self, _e):
        # 打开瞬间 focus 变化会误触发，延迟 0.3s 后才允许自动收起
        if time.monotonic() - self._opened_at <= 0.3:
            return
        # 焦点被面板自己的子控件抢走（按下时 canvas.focus_set、点击激活窗口）
        # 也会送 FocusOut 给 Toplevel，这不是“点了面板外”：按收起语义
        # 只应该由“点到别的应用”触发，故用指针位置判定。
        # 否则第一次按下就把面板 destroy 掉，滑杆拖不动、按钮点不到。
        w = self.win
        try:
            px, py = w.winfo_pointerx(), w.winfo_pointery()
            x, y = w.winfo_rootx(), w.winfo_rooty()
            if (x <= px <= x + w.winfo_width()
                    and y <= py <= y + w.winfo_height()):
                return
        except Exception:
            pass
        self.close()

    def close(self, *_e):
        try:
            self.win.destroy()
        except Exception:
            pass
        self.app._panel_closed_at = time.monotonic()
        if self.app._panel is self:
            self.app._panel = None


# ---------------- 应用主体 ----------------

class App:
    def __init__(self, root):
        self.root = root
        self.settings = load_settings()
        self.on = False
        self._panel = None
        self.actions = queue.Queue()

        root.withdraw()  # 无主窗口，仅托盘

        with open(PID_FILE, "w", encoding="ascii") as f:
            f.write(str(os.getpid()))
        if os.path.exists(STOP_FILE):
            os.remove(STOP_FILE)

        self.tray = TrayIcon(self.actions)
        self.tray.start()
        self._update_kick = threading.Event()   # 打开面板时唤醒检查线程立即评估
        threading.Thread(target=self.update_checker, daemon=True).start()
        if REAPPLY_SECONDS > 0:
            threading.Thread(target=self.reapplier, daemon=True).start()

        self.root.after(100, self.poll)
        self.root.after(500, self.start_overlay)  # 启动即自动开染
        self._panel_closed_at = 0.0

        # 窗口图标统一用猫 logo（避免任何地方露出 Tk 默认羽毛图标）
        try:
            ico = self.tray._make_ico()
            if ico:
                root.iconbitmap(default=ico)
        except Exception:
            pass

    # ----- 遮罩 -----
    def current_ramp(self):
        s = self.settings
        return build_tinted_ramp(s["r"], s["g"], s["b"], s["strength"])

    def start_overlay(self):
        if self.on:
            return
        if apply_tint(self.current_ramp()) == 0:
            log_error("没有显示器支持 Gamma Ramp（HDR/10bit 模式下不可用）。")
            return
        self.on = True

    def _refresh_panel(self):
        if self._panel is not None and self._panel.win.winfo_exists():
            self._panel.draw()

    # ----- 动作轮询（线程安全） -----
    def poll(self):
        while True:
            try:
                cmd = self.actions.get_nowait()
            except queue.Empty:
                break
            try:
                self.handle(cmd)
            except Exception:
                # 窗口化 exe 里 Tk 回调异常默认静默，落盘便于排查
                import traceback
                log_error(traceback.format_exc())
        if os.path.exists(STOP_FILE):
            self.quit_app()
            return
        self.root.after(100, self.poll)

    def handle(self, cmd):
        if cmd == "panel":
            self.toggle_panel()
        elif cmd == "save":
            self.save_action()
        elif cmd == "quit":
            self.quit_app()
        elif isinstance(cmd, tuple) and cmd[0] == "update_found":
            self.on_update_found(cmd[1])

    # ----- 新版本感知（后台静默：断网 / GitHub 不可达时不打扰） -----
    def update_checker(self):
        time.sleep(UPDATE_CHECK_DELAY)
        while True:
            try:
                if (time.time() - float(self.settings.get("update_check_at", 0) or 0)
                        >= UPDATE_CHECK_INTERVAL):
                    latest = fetch_latest_version()
                    if latest:
                        self.actions.put(("update_found", latest))
            except Exception:
                pass
            # 常规 10 分钟一醒；打开面板会立刻唤醒（节流仍生效，不会多打请求）
            self._update_kick.wait(600)
            self._update_kick.clear()

    def on_update_found(self, latest):
        """查到最新 Release：落盘已知版本；首次发现新版才弹一次托盘气泡"""
        changed = latest != self.settings.get("update_latest", "")
        self.settings["update_check_at"] = time.time()
        self.settings["update_latest"] = latest
        save_settings(self.settings)
        if changed and version_gt(latest, APP_VERSION):
            self.tray.notify("Eye Care U v%s 可用" % latest,
                             "当前 v%s。点击托盘图标打开面板前往下载；"
                             "用新 exe 覆盖原位置可保留配色设置。" % APP_VERSION)
            self._refresh_panel()

    # ----- 托盘面板 -----
    def toggle_panel(self):
        if self._panel is not None:
            self._panel.close()
            return
        if time.monotonic() - self._panel_closed_at < 0.4:
            return   # 刚因焦点转移收起（如点击任务栏），不要立刻又弹回
        panel = None
        try:
            panel = GlassPanel(self)
            self._panel = panel
            self._update_kick.set()   # 面板已开：检查线程立即评估（节流仍生效）
        except Exception:
            # 构造半途失败时销毁半初始化窗口，避免泄漏一块空玻璃
            import traceback
            log_error(traceback.format_exc())
            try:
                if panel is not None:
                    panel.win.destroy()
            except Exception:
                pass
            self._panel = None

    def save_action(self):
        """Save：把当前滑杆值落盘（染色已实时生效），按钮短暂显示 Saved"""
        save_settings(self.settings)
        self._panel.saved_until = time.monotonic() + 0.9
        self._refresh_panel()
        self.root.after(900, self._refresh_panel)

    def apply_rgb(self, r, g, b):
        """整体应用一组 RGB（HEX 输入用）：更新滑杆并实时染色"""
        self.settings["r"], self.settings["g"], self.settings["b"] = r, g, b
        if not self.on:
            self.start_overlay()
        else:
            apply_tint(self.current_ramp(), save_original=False)
        self._refresh_panel()

    def on_scale_key(self, key, value):
        self.settings[key] = value
        self._refresh_panel()
        if not self.on:
            self.start_overlay()   # 拖动即自动开染，所见即所得
        else:
            apply_tint(self.current_ramp(), save_original=False)

    # ----- 退出 -----
    def quit_app(self):
        # 保存走面板上的 Save（显式保存）；退出恢复原色并清理后硬退出
        if self.on:
            restore()
        try:
            self.tray.remove()
        except Exception:
            pass
        for path in (PID_FILE, STOP_FILE):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
        os._exit(0)

    def reapplier(self):
        while True:
            time.sleep(REAPPLY_SECONDS)
            if self.on:
                apply_tint(self.current_ramp(), save_original=False)


# ---------------- 入口 ----------------

def headless_test():
    s = load_settings()
    ramp = build_tinted_ramp(s["r"], s["g"], s["b"], s["strength"])
    applied = apply_tint(ramp)
    if applied == 0:
        print("错误：没有显示器支持 Gamma Ramp。", file=sys.stderr)
        sys.exit(1)
    print("已染色 %d 台显示器，3 秒后自动恢复..." % applied)
    time.sleep(3)
    restore()
    print("已恢复。测试通过。")


def main():
    global tk
    import tkinter as tk

    if "--test" in sys.argv:
        headless_test()
        return

    if not ensure_single_instance():
        print("Eye Care U 已在运行。")
        return

    root = tk.Tk()
    app = App(root)
    if "--ui-test" in sys.argv:
        root.after(300, app.toggle_panel)
        root.after(2600, app.start_overlay)   # 延迟开染，留出无染色干扰的抓图窗口
        root.after(4000, app.quit_app)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        log_error(traceback.format_exc())
        raise
