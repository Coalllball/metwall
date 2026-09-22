"""打包版入口（PyInstaller 用）。

单文件 exe / .app 双击时的行为要"像个应用"，而不是甩一段 argparse 帮助：

    无参数         → 启动 dashboard 并自动打开浏览器（serve）
    <子命令...>    → 透传给 CLI（next / browse / set / search / ...）

环境变量 METWALL_PORT 可改端口（默认 8000）。
"""
import os
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
for p in (os.path.dirname(HERE), HERE):
    if p not in sys.path:
        sys.path.insert(0, p)


def _open_browser_later(port):
    time.sleep(2.0)
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except Exception:
        pass


def main():
    argv = sys.argv[1:]
    if not argv:
        port = int(os.environ.get("METWALL_PORT", "8000"))
        threading.Thread(target=_open_browser_later, args=(port,), daemon=True).start()
        argv = ["serve", "--port", str(port)]
        print(f"Met Wallpaper 启动中… 浏览器将自动打开 http://127.0.0.1:{port}")
        print("（关闭此窗口即退出；命令行用法：MetWallpaper.exe --help）\n")

    from wallpaper import main as cli_main
    sys.argv = ["wallpaper"] + argv
    try:
        return cli_main()
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
