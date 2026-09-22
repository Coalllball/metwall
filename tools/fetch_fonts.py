#!/usr/bin/env python3
"""下载内置字体：Gelasio（§ Georgia）+ Cousine（§ Courier New）。

为什么不用 Georgia / Courier New：
  两者是微软授权字体，**不可随包分发**（公开仓库分发属侵权），且 Linux 不自带、
  macOS 把它们放在 /System/Library/Fonts/Supplemental（Pillow 不搜该目录），
  导致非 Windows 平台渲染直接抛 OSError。

为什么 Gelasio / Cousine：
  公制兼容（metric-compatible）——字符宽度、换行点、行距与 Georgia / Courier New
  完全一致，替换后排版零变化。实测文本宽度逐项相同（见 README）。

授权：两者均为 SIL OFL 1.1，可自由分发（授权原文见同目录 *-OFL.txt）。

用法：python tools/fetch_fonts.py    （需已登录 gh CLI 或有公网访问）
"""
import base64
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, os.pardir, "assets", "fonts")
OUT = os.path.normpath(OUT)

# Google Fonts css2 按 UA 决定格式：IE6→EOT、Firefox→WOFF、curl/Android→TTF
UA_TTF = "curl/8.0"

WANTED = [
    # (css2 查询, google/fonts 静态路径 或 None, 目标文件名)
    ("family=Gelasio:wght@400", None, "Gelasio-Regular.ttf"),
    ("family=Gelasio:wght@700", None, "Gelasio-Bold.ttf"),
    ("family=Gelasio:ital@1", None, "Gelasio-Italic.ttf"),
    (None, "ofl/cousine/Cousine-Regular.ttf", "Cousine-Regular.ttf"),
    (None, "ofl/cousine/Cousine-Bold.ttf", "Cousine-Bold.ttf"),
    (None, "ofl/gelasio/OFL.txt", "Gelasio-OFL.txt"),
    (None, "ofl/cousine/OFL.txt", "Cousine-OFL.txt"),
]


def fetch_gh(repo_path, dest):
    """经 gh CLI 取 google/fonts 里的静态文件（走认证 API，国内比 raw 稳）。"""
    r = subprocess.run(["gh", "api", f"repos/google/fonts/contents/{repo_path}", "--jq", ".content"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"gh api 失败 {repo_path}: {r.stderr.strip()[:200]}")
    with open(dest, "wb") as f:
        f.write(base64.b64decode(r.stdout))


def fetch_css(query, dest):
    css = subprocess.run(["curl", "-s", "-A", UA_TTF,
                          f"https://fonts.googleapis.com/css2?{query}"],
                         capture_output=True, text=True).stdout
    m = re.search(r"url\((https://[^)]+)\)", css)
    if not m:
        raise RuntimeError(f"CSS 未取到 url（{query}）: {css.strip()[:200]}")
    subprocess.run(["curl", "-sL", "-o", dest, m.group(1)], check=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    for query, repo_path, name in WANTED:
        dest = os.path.join(OUT, name)
        if query:
            fetch_css(query, dest)
        else:
            fetch_gh(repo_path, dest)
        print(f"  {name:26s} {os.path.getsize(dest):>9,} bytes")

    # 校验：TTF 必须是 00010000，否则说明 UA 协商到了 EOT/WOFF
    print("\n校验：")
    bad = []
    for _, _, name in WANTED:
        if not name.endswith(".ttf"):
            continue
        with open(os.path.join(OUT, name), "rb") as f:
            magic = f.read(4)
        ok = magic == b"\x00\x01\x00\x00"
        print(f"  {name:26s} {'✅ TrueType' if ok else '❌ 非 TTF，魔数=' + magic.hex()}")
        if not ok:
            bad.append(name)

    # 公制兼容性断言：与 Windows 原生 Georgia/Courier New 逐字宽对比
    win_fonts = "C:/Windows/Fonts"
    if os.path.isdir(win_fonts):
        from PIL import ImageFont, Image, ImageDraw
        d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        pairs = [("Gelasio-Regular.ttf", "georgia.ttf"), ("Gelasio-Bold.ttf", "georgiab.ttf"),
                 ("Cousine-Regular.ttf", "cour.ttf"), ("Cousine-Bold.ttf", "courbd.ttf")]
        print("\n公制兼容性（内置 vs 原生，同字号 40）：")
        for ours, native in pairs:
            a = ImageFont.truetype(os.path.join(OUT, ours), 40)
            b = ImageFont.truetype(os.path.join(win_fonts, native), 40)
            wa = [d.textlength(s, font=a) for s in ("Met Wallpaper", "W", "i", "mmm")]
            wb = [d.textlength(s, font=b) for s in ("Met Wallpaper", "W", "i", "mmm")]
            same = all(abs(x - y) < 0.02 for x, y in zip(wa, wb))
            print(f"  {ours:24s} vs {native:16s} {'✅ 完全一致' if same else '❌ 有偏差'}")
            if not same:
                bad.append(ours)

    if bad:
        print(f"\n失败：{bad}")
        return 1
    print("\n全部就绪。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
