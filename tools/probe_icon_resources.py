# -*- coding: utf-8 -*-
"""校验 exe 内嵌图标资源完整性：RT_ICON 各帧 + RT_GROUP_ICON 声明表。
用法: python probe_icon_resources.py <exe>
退出码 0=完整（group 引用的每帧都存在且大小一致），1=异常。
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

EXE = sys.argv[1]
RT_ICON, RT_GROUP_ICON = 3, 14

k = ctypes.windll.kernel32
k.LoadLibraryExW.restype = wt.HMODULE
k.LoadLibraryExW.argtypes = [wt.LPCWSTR, wt.HANDLE, wt.DWORD]
k.FindResourceW.argtypes = [wt.HMODULE, wt.LPCWSTR, wt.LPCWSTR]
k.FindResourceW.restype = wt.HRSRC
k.SizeofResource.argtypes = [wt.HMODULE, wt.HRSRC]
k.SizeofResource.restype = wt.DWORD
k.LoadResource.argtypes = [wt.HMODULE, wt.HRSRC]
k.LoadResource.restype = wt.HGLOBAL
k.LockResource.argtypes = [wt.HGLOBAL]
k.LockResource.restype = wt.LPVOID
k.EnumResourceNamesW.argtypes = [wt.HMODULE, wt.LPCWSTR, ctypes.c_void_p, wt.LPARAM]

h = k.LoadLibraryExW(EXE, None, 0x2)
assert h, "LoadLibraryEx failed"


def res_data(rtype, name):
    hr = k.FindResourceW(h, wt.LPCWSTR(name), wt.LPCWSTR(rtype))
    if not hr:
        return None
    size = k.SizeofResource(h, hr)
    hg = k.LoadResource(h, hr)
    return ctypes.string_at(k.LockResource(hg), size)


names_proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HMODULE, wt.LPARAM,
                                 wt.LPARAM, wt.LPARAM)
icons = []


@names_proto
def ncb(_h, _t, name, _l):
    icons.append(name)
    return True


k.EnumResourceNamesW(h, wt.LPCWSTR(RT_ICON), ncb, 0)
print("RT_ICON ids:", sorted(icons))
for n in sorted(icons):
    d = res_data(RT_ICON, n)
    fmt = "PNG" if d[:4] == b"\x89PNG" else "BMP"
    print("  RT_ICON %-2s: %6d bytes  %s" % (n, len(d), fmt))

grp = res_data(RT_GROUP_ICON, 1)
# GRPICONDIR 头为 (idReserved, idType, idCount)——count 在第 3 个字段
_reserved, _type, cnt = struct.unpack_from("<HHH", grp, 0)
print("RT_GROUP_ICON 1: %d bytes, %d entries" % (len(grp), cnt))
off = 6
ok = cnt > 0
for _i in range(cnt):
    w, h2, _nc, _r, planes, bpp, sz, idi = struct.unpack_from("<BBBBHHIH", grp, off)
    off += 14
    print("  entry: %dx%d planes=%d bpp=%d bytes=%d -> RT_ICON %d"
          % (w or 256, h2 or 256, planes, bpp, sz, idi))
    d = res_data(RT_ICON, idi)
    if d is None or len(d) != sz:
        ok = False
        print("    !! 引用的 RT_ICON %d 缺失或大小不符" % idi)
print("check:", "OK" if ok else "FAILED")
sys.exit(0 if ok else 1)
