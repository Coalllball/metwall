"""平台适配抽象：壁纸设置 + 屏幕尺寸 + 定时调度 + 用户数据目录。

三平台实现各放一个文件，CLI 通过 platforms 包的工厂获取当前平台的实例。
新增平台 = 实现这两个接口。
"""
import os
import sys
from abc import ABC, abstractmethod


def user_data_dir():
    """平台标准用户数据目录（缓存/日志等写入这里，不污染安装位置）。"""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return base


class WallpaperSetter(ABC):
    """壁纸设置器。"""

    @abstractmethod
    def screen_size(self):
        """返回主屏 (width, height)，供排版使用。"""

    @abstractmethod
    def set(self, path):
        """将图片设为桌面壁纸，返回 bool。"""


class Scheduler(ABC):
    """定时轮换调度器。"""

    @abstractmethod
    def install(self, interval_hours, python, script):
        """创建定时任务：每 interval_hours 小时跑一次 `python script next --style random`。"""

    @abstractmethod
    def remove(self):
        """删除定时任务。"""

    @abstractmethod
    def status(self):
        """返回任务是否存在/启用状态字符串。"""
