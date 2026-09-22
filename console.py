"""控制台输出兜底：让中文在任何编码环境下都不会把程序打崩。

背景：Windows 上 Python 只有在**直接连着控制台**时才用 UTF-8 输出（PEP 528）；
一旦输出被管道或重定向（`wallpaper next | tee log.txt`、CI 日志采集、写文件），
就退回系统区域编码——英文 Windows 是 cp1252，print 中文会直接抛
UnicodeEncodeError: 'charmap' codec can't encode characters，整个命令失败。

处理：把 stdout/stderr 切到 UTF-8，并对无法编码的字符降级替换而不是抛异常。
连控制台时 PEP 528 走 WriteConsoleW，该设置不影响显示。
"""
import sys


def setup_console():
    """把 stdout/stderr 设为 UTF-8 + 容错。可重复调用，失败也不影响主流程。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # 非 TextIOWrapper（被替换过）或已关闭——忽略即可
            pass
