"""macOS 实现：osascript 设置壁纸 + LaunchAgent 定时任务。

⚠️ 未在真机实测，按 macOS 通用做法实现。
"""

import os
import plistlib
import subprocess

from .base import Scheduler, WallpaperSetter

LABEL = "com.oldspirit.metwallpaper"
AGENT_DIR = os.path.expanduser("~/Library/LaunchAgents")
PLIST = os.path.join(AGENT_DIR, f"{LABEL}.plist")


class MacSetter(WallpaperSetter):
    name = "macos"

    def screen_size(self):
        # system_profiler 解析主显示器分辨率（无第三方依赖）
        r = subprocess.run(["system_profiler", "SPDisplaysDataType"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            m = __import__("re").search(r"Resolution:\s*(\d+) x (\d+)", line)
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1920, 1080  # fallback

    def set(self, path):
        script = f'tell application "System Events" to set picture of every desktop to POSIX file "{path}"'
        r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
        return r.returncode == 0


def open_image(path):
    """用系统默认图片查看器打开（预览用）。"""
    import subprocess
    subprocess.run(["open", path], check=False)


class MacScheduler(Scheduler):
    name = "macos"

    def install(self, interval_hours, python, script):
        os.makedirs(AGENT_DIR, exist_ok=True)
        plist = {
            "Label": LABEL,
            "ProgramArguments": [python, script, "next", "--style", "random"],
            "StartInterval": interval_hours * 3600,
            "RunAtLoad": False,
        }
        with open(PLIST, "wb") as f:
            plistlib.dump(plist, f)
        r = subprocess.run(["launchctl", "load", PLIST], capture_output=True, text=True)
        return r.returncode == 0, r.stderr

    def remove(self):
        r = subprocess.run(["launchctl", "unload", PLIST], capture_output=True, text=True)
        if os.path.exists(PLIST):
            os.remove(PLIST)
        return r.returncode == 0, r.stderr

    def status(self):
        return "已安装" if os.path.exists(PLIST) else "未安装"
