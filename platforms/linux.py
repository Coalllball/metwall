"""Linux 实现：按桌面环境尝试 gsettings / plasma-apply / feh，调度用 crontab。

⚠️ 未在真机实测，按各 DE 通用做法实现。
"""

import os
import re
import subprocess

from .base import Scheduler, WallpaperSetter

CRON_LINE = "met-wallpaper"


class LinuxSetter(WallpaperSetter):
    name = "linux"

    def screen_size(self):
        # 从 xrandr 解析主屏分辨率（标 * 的行）
        r = subprocess.run(["xrandr", "--current"], capture_output=True, text=True)
        for line in r.stdout.splitlines():
            m = re.search(r"\b(\d{3,5})x(\d{3,5})\b.*\*", line)
            if m:
                return int(m.group(1)), int(m.group(2))
        return 1920, 1080  # fallback

    def set(self, path):
        uri = f"file://{path}"
        attempts = [
            # GNOME
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri", uri],
            ["gsettings", "set", "org.gnome.desktop.background", "picture-uri-dark", uri],
            # KDE
            ["plasma-apply-wallpaperimage", path],
            # 通用 fallback（无 DE / i3 等）
            ["feh", "--bg-fill", path],
        ]
        for cmd in attempts:
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
                if r.returncode == 0:
                    return True
            except (FileNotFoundError, subprocess.TimeoutExpired):
                continue
        return False


def open_image(path):
    """用系统默认图片查看器打开（预览用）。"""
    import subprocess
    subprocess.run(["xdg-open", path], check=False)


class LinuxScheduler(Scheduler):
    name = "linux"

    def _crontab(self):
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        return r.stdout.splitlines() if r.returncode == 0 else []

    def install(self, interval_hours, python, script):
        lines = [ln for ln in self._crontab() if CRON_LINE not in ln]
        lines.append(f"0 */{interval_hours} * * * cd {os.path.dirname(script)} && "
                     f'"{python}" "{script}" next --style random  # {CRON_LINE}')
        r = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True,
                           capture_output=True)
        return r.returncode == 0, r.stderr

    def remove(self):
        lines = [ln for ln in self._crontab() if CRON_LINE not in ln]
        r = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True,
                           capture_output=True)
        return r.returncode == 0, r.stderr

    def status(self):
        return "已安装" if any(CRON_LINE in ln for ln in self._crontab()) else "未安装"
