#!/usr/bin/env python3
"""离线渲染预览：用 seed/ 素材把每种风格各出一张图。

用途：README 截图、CI 归档出图证据、本地改风格后快速看效果（不联网）。

用法：
    python tools/preview.py                          # 全部风格 → preview/
    python tools/preview.py --size 2560x1600          # 竖屏
    python tools/preview.py --style pedestal --size 1080x1920
    python tools/preview.py --apply                   # 渲染后尝试设为壁纸（平台实测）
"""
import argparse
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import render  # noqa: E402
from console import setup_console  # noqa: E402


def main():
    setup_console()
    ap = argparse.ArgumentParser(description="从 seed 素材离线渲染风格预览")
    ap.add_argument("--out", default="preview", help="输出目录（默认 preview/）")
    ap.add_argument("--size", default="1920x1080", help="分辨率 WxH（默认 1920x1080）")
    ap.add_argument("--style", action="append", help="只渲染指定风格，可重复")
    ap.add_argument("--object-id", type=int, help="指定 seed 中的作品 objectID")
    ap.add_argument("--quality", type=int, default=88, help="JPEG 质量（默认 88）")
    ap.add_argument("--apply", action="store_true", help="渲染后尝试设为壁纸（实测平台适配）")
    args = ap.parse_args()

    w, h = (int(x) for x in args.size.lower().split("x"))
    metas = sorted(glob.glob(os.path.join(ROOT, "seed", "meta", "*.json")))
    if not metas:
        sys.exit("seed/meta 为空——无法离线预览")
    if args.object_id:
        metas = [m for m in metas if json.load(open(m, encoding="utf-8"))["objectID"] == args.object_id]
        if not metas:
            sys.exit(f"seed 中没有 objectID={args.object_id}")

    info = json.load(open(metas[0], encoding="utf-8"))
    img = os.path.join(ROOT, "seed", "img", f"{info['objectID']}_small.jpg")
    styles = args.style or sorted(render.STYLES)

    out_dir = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(out_dir, exist_ok=True)

    print(f"作品: {info['objectID']}  {info.get('title')}")
    print(f"尺寸: {w}x{h}   输出: {out_dir}\n")

    ok, fail = [], []
    for style in styles:
        try:
            canvas, used = render.render(info, style, (w, h), img)
            path = os.path.join(out_dir, f"{style}.jpg")
            canvas.save(path, "JPEG", quality=args.quality)
            print(f"  ✅ {style:10s} {os.path.getsize(path) // 1024:>5} KB  {path}")
            ok.append((style, path))
        except Exception as e:
            print(f"  ❌ {style:10s} {type(e).__name__}: {e}")
            fail.append(style)

    print(f"\n{len(ok)}/{len(styles)} 成功" + (f"，失败: {fail}" if fail else ""))

    if args.apply and ok:
        from platforms import get_setter
        setter = get_setter()
        style, path = ok[0]
        print(f"\n实测平台适配 [{setter.name}]：设为壁纸 → {path}")
        try:
            print(f"  屏幕尺寸: {setter.screen_size()}")
        except Exception as e:
            print(f"  屏幕尺寸读取失败: {type(e).__name__}: {e}")
        try:
            result = setter.set(path)
            print(f"  set() 返回: {result}")
        except Exception as e:
            print(f"  set() 异常: {type(e).__name__}: {e}")

    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())
