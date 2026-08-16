"""Windows 实现：SPI 设置壁纸 + schtasks 定时任务。"""

import os
import subprocess

from .base import Scheduler, WallpaperSetter, user_data_dir

SM_CXSCREEN, SM_CYSCREEN = 0, 1
SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

TASK_NAME = "MetWallpaper"


def monitors():
    """枚举所有显示器：位置/分辨率/主屏标志。"""
    import ctypes
    from ctypes import wintypes

    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", RECT),
                    ("rcWork", RECT), ("dwFlags", ctypes.c_ulong)]

    user32 = ctypes.windll.user32
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC,
                        ctypes.POINTER(RECT), wintypes.LPARAM)
    def _cb(hmon, hdc, lprect, lparam):
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(mi)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = lprect.contents
        out.append({
            "x": r.left, "y": r.top,
            "w": r.right - r.left, "h": r.bottom - r.top,
            "primary": bool(mi.dwFlags & 1),
        })
        return True

    user32.EnumDisplayMonitors(0, 0, _cb, 0)
    return out


_dw_holder = None  # 模块级持有 COM 对象，防 GC 提前 Release（vtable 悬垂）
_TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tools", "multiwallpaper.exe")


def _dw():
    """IDesktopWallpaper COM（ctypes 版，留作诊断；实际用 C# 工具）。"""
    global _dw_holder
    import ctypes

    class GUID(ctypes.Structure):
        _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort),
                    ("Data3", ctypes.c_ushort), ("Data4", ctypes.c_ubyte * 8)]

    CLSID = GUID(0xC2CF3110, 0x460E, 0x4FC1,
                 (ctypes.c_ubyte * 8)(0xB9, 0xD0, 0x8A, 0x1C, 0x0C, 0x9C, 0xC4, 0xBD))
    IID = GUID(0xB92B56A9, 0x8B55, 0x4E14,
               (ctypes.c_ubyte * 8)(0x9A, 0x89, 0x01, 0x99, 0xBB, 0xB6, 0xF9, 0x3B))

    ole32 = ctypes.oledll.ole32
    ole32.CoInitializeEx(None, 0x2)
    p = ctypes.POINTER(ctypes.c_void_p)()
    hr = ole32.CoCreateInstance(ctypes.byref(CLSID), None, 4,  # CLSCTX_LOCAL_SERVER
                                ctypes.byref(IID), ctypes.byref(p))
    if hr != 0 or not p:
        return None, None
    _dw_holder = p  # 防 GC
    vtbl = ctypes.cast(p[0], ctypes.POINTER(ctypes.c_void_p))
    return vtbl, ctypes.c_void_p(p[0])


def monitor_paths():
    """每屏的 device path（C# 工具实现——COM 注册完整时可用）。"""
    if not os.path.exists(_TOOL):
        return []
    try:
        r = subprocess.run([_TOOL], capture_output=True, text=True, timeout=15)
        return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


class WindowsSetter(WallpaperSetter):
    name = "windows"

    def screen_size(self):
        import ctypes
        user32 = ctypes.windll.user32
        return user32.GetSystemMetrics(SM_CXSCREEN), user32.GetSystemMetrics(SM_CYSCREEN)

    def set(self, path):
        import ctypes
        user32 = ctypes.windll.user32
        ok = user32.SystemParametersInfoW(SPI_SETDESKWALLPAPER, 0, path,
                                          SPIF_UPDATEINIFILE | SPIF_SENDCHANGE)
        return bool(ok)

    def set_multi(self, wallpapers):
        """每显示器独立壁纸：{device_path: image_path}。

        用 C# 工具（IDesktopWallpaper COM）。工具缺失/COM 损坏（本机
        注册表被清理过）→ 回退 SPI 设主屏，其余屏按各自比例填充显示。
        """
        if not os.path.exists(_TOOL):
            return self.set(next(iter(wallpapers.values())))
        args = [_TOOL] + [f"{dev}={img}" for dev, img in wallpapers.items()]
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=30)
            if r.returncode == 0:
                return True
        except Exception:
            pass
        return self.set(next(iter(wallpapers.values())))


def open_image(path):
    """用系统默认图片查看器打开（预览用）。"""
    import os
    os.startfile(path)


class WindowsScheduler(Scheduler):
    name = "windows"

    def _cmd(self, tr):
        # schtasks 的 /TR 需要引号包裹整条命令，内部路径再各自加引号
        return [
            "schtasks", "/Create", "/F", "/TN", TASK_NAME,
            "/SC", "HOURLY", "/MO", str(self._hours), "/TR", tr,
        ]

    def install(self, interval_hours, python, script, extra=""):
        # 坑：/TR 直接放双引号路径时 taskeng 解析失败（Last Result=1），
        # 必须用 cmd /c 包装；加日志重定向方便排障
        self._hours = interval_hours
        log = os.path.join(user_data_dir(), "metwall", "cache", "schedule.log")
        os.makedirs(os.path.dirname(log), exist_ok=True)
        inner = f'""{python}" "{script}" next {extra} > "{log}" 2>&1"'
        tr = f"cmd /c {inner}"
        r = subprocess.run(self._cmd(tr), capture_output=True, text=True)
        return r.returncode == 0, r.stdout + r.stderr

    def remove(self):
        r = subprocess.run(["schtasks", "/Delete", "/F", "/TN", TASK_NAME],
                           capture_output=True, text=True)
        return r.returncode == 0, r.stdout + r.stderr

    def status(self):
        r = subprocess.run(["schtasks", "/Query", "/TN", TASK_NAME],
                           capture_output=True, text=True)
        return "已安装" if r.returncode == 0 else "未安装"
