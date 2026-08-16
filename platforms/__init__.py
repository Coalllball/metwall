"""平台检测与适配器工厂。CLI 只依赖这里，不直接碰平台细节。"""

import platform as _platform
import sys

from .base import Scheduler, WallpaperSetter


def detect():
    """返回 (setter, scheduler)。未知平台返回 None。"""
    sys_name = _platform.system()
    if sys_name == "Windows":
        from .windows import WindowsScheduler, WindowsSetter
        return WindowsSetter(), WindowsScheduler()
    if sys_name == "Darwin":
        from .macos import MacScheduler, MacSetter
        return MacSetter(), MacScheduler()
    if sys_name == "Linux":
        from .linux import LinuxScheduler, LinuxSetter
        return LinuxSetter(), LinuxScheduler()
    return None, None


def get_setter() -> WallpaperSetter:
    setter, _ = detect()
    if setter is None:
        sys.exit(f"不支持的平台: {_platform.system()}")
    return setter


def monitors():
    """所有显示器信息（位置/分辨率/主屏）。非 Windows 返回 []。"""
    if _platform.system() == "Windows":
        try:
            from .windows import monitors as _m
            return _m()
        except Exception:
            pass
    return []


def get_scheduler() -> Scheduler:
    _, scheduler = detect()
    if scheduler is None:
        sys.exit(f"不支持的平台: {_platform.system()}")
    return scheduler


def open_image(path):
    """用系统默认图片查看器打开图片（预览用）。"""
    sys_name = _platform.system()
    if sys_name == "Windows":
        from .windows import open_image as _oi
    elif sys_name == "Darwin":
        from .macos import open_image as _oi
    elif sys_name == "Linux":
        from .linux import open_image as _oi
    else:
        sys.exit(f"不支持的平台: {sys_name}")
    _oi(path)
