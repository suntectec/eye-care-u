# -*- coding: utf-8 -*-
"""从 PE 文件提取嵌入图标（RT_GROUP_ICON -> 重组 .ico），存到指定路径。
用法: python extract_exe_icon.py <exe> <out.ico>
"""
import ctypes
import ctypes.wintypes as wt
import struct
import sys

EXE, OUT = sys.argv[1], sys.argv[2]
RT_ICON = 3
RT_GROUP_ICON = 14

k = ctypes.windll.kernel32
k.LoadLibraryExW.argtypes = [wt.LPCWSTR, wt.HANDLE, wt.DWORD]
k.LoadLibraryExW.restype = wt.HMODULE
k.EnumResourceNamesW.argtypes = [wt.HMODULE, wt.LPCWSTR, ctypes.c_void_p, wt.LPARAM]
k.FindResourceW.argtypes = [wt.HMODULE, wt.LPCWSTR, wt.LPCWSTR]
k.FindResourceW.restype = wt.HRSRC
k.SizeofResource.argtypes = [wt.HMODULE, wt.HRSRC]
k.SizeofResource.restype = wt.DWORD
k.LoadResource.argtypes = [wt.HMODULE, wt.HRSRC]
k.LoadResource.restype = wt.HGLOBAL
k.LockResource.argtypes = [wt.HGLOBAL]
k.LockResource.restype = wt.LPVOID

hsrc = k.LoadLibraryExW(EXE, None, 0x00000020 | 0x00000002)
assert hsrc, "LoadLibraryEx failed"

enum = k.EnumResourceNamesW
proto = ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HMODULE, wt.LPARAM,
                           wt.LPARAM, wt.LPARAM)
groups = []


@proto
def cb_group(h, _t, name, _l):
    groups.append(name)   # name 是整数 ID（MAKEINTRESOURCE），不做字符串转换
    return True


enum(hsrc, wt.LPCWSTR(RT_GROUP_ICON), cb_group, 0)
print("group icons:", groups)
assert groups, "no RT_GROUP_ICON resource (exe has no embedded icon)"

gname = wt.LPCWSTR(groups[0])
hres = k.FindResourceW(hsrc, gname, wt.LPCWSTR(RT_GROUP_ICON))
size = k.SizeofResource(hsrc, hres)
hglb = k.LoadResource(hsrc, hres)
data = ctypes.string_at(k.LockResource(hglb), size)

# GRPICONDIR 头为 (idReserved, idType, idCount)——count 在第 3 个字段
_res, _typ, count = struct.unpack_from("<HHH", data, 0)
entries = []
off = 6
for _ in range(count):
    b, w, h, nc, r1, r2, size_img, idi = struct.unpack_from("<BBBBHHIH", data, off)
    entries.append((w, h, size_img, idi))
    off += 14
print("entries:", [(w or 256, h or 256, idi) for w, h, _s, idi in entries])

icons = {}
for _w, _h, _s, idi in entries:
    hr = k.FindResourceW(hsrc, wt.LPCWSTR(idi), wt.LPCWSTR(RT_ICON))
    sz = k.SizeofResource(hsrc, hr)
    hg = k.LoadResource(hsrc, hr)
    icons[idi] = ctypes.string_at(k.LockResource(hg), sz)

# 重建 ico: ICONDIR + ICONDIR entries(16B) + 图像数据
n = len(entries)
out = struct.pack("<HHH", 0, 1, n)
images = b""
offset = 6 + 16 * n
for w, h, sz, idi in entries:
    out += struct.pack("<BBBBHHII", w, h, 0, 0, 1, 32, sz, offset)
    images += icons[idi]
    offset += sz
open(OUT, "wb").write(out + images)
print("saved:", OUT, "icons:", n)
