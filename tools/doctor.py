#!/usr/bin/env python3
"""平台适配体检：报告当前机器上哪些能力可用、哪些不可用。

CI 在 Windows / macOS / Linux 上各跑一次，把"未实测"变成每次提交都有的实测输出。

用法：
    python tools/doctor.py            # 只读体检
    python tools/doctor.py --apply    # 额外真实尝试设一次壁纸（会改桌面背景）
"""
import argparse
import os
import platform
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from console import setup_console  # noqa: E402


def line(label, value):
    print(f"  {label:<22} {value}")


def main():
    setup_console()
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真实设置壁纸验证适配层")
    args = ap.parse_args()

    print("=" * 60)
    print("Met Wallpaper 平台体检")
    print("=" * 60)

    print("\n[环境]")
    line("系统", f"{platform.system()} {platform.release()}")
    line("架构", platform.machine())
    line("Python", platform.python_version())

    print("\n[依赖]")
    for mod in ("PIL", "requests", "fastapi", "uvicorn"):
        try:
            m = __import__(mod)
            line(mod, getattr(m, "__version__", "已安装"))
        except ImportError:
            line(mod, "❌ 未安装" + ("（serve 需要: pip install -e '.[web]'）" if mod in ("fastapi", "uvicorn") else ""))

    print("\n[内置资源]")
    import render
    line("字体目录", render.FONT_DIR)
    line("目录存在", "✅" if os.path.isdir(render.FONT_DIR) else "❌ 缺失")
    for key, fname in sorted(render.FONT_FILES.items()):
        try:
            render._font(key, 40)
            line(f"字体 {key}", f"✅ {fname}")
        except Exception as e:
            line(f"字体 {key}", f"❌ {fname} — {type(e).__name__}")

    print("\n[渲染]")
    import glob
    import json
    metas = sorted(glob.glob(os.path.join(ROOT, "seed", "meta", "*.json")))
    if not metas:
        line("seed 素材", "❌ 缺失，无法离线验证渲染")
    else:
        info = json.load(open(metas[0], encoding="utf-8"))
        img = os.path.join(ROOT, "seed", "img", f"{info['objectID']}_small.jpg")
        ok, fail = 0, []
        for style in sorted(render.STYLES):
            try:
                render.render(info, style, (1920, 1080), img)
                ok += 1
            except Exception as e:
                fail.append(f"{style}({type(e).__name__})")
        line("风格通过", f"{ok}/{len(render.STYLES)}" + (f"  失败: {fail}" if fail else " ✅"))

    print("\n[平台适配]")
    try:
        from platforms import get_scheduler, get_setter
        setter = get_setter()
        line("壁纸设置器", setter.name)
        try:
            line("屏幕尺寸", f"{setter.screen_size()}")
        except Exception as e:
            line("屏幕尺寸", f"❌ {type(e).__name__}: {e}")
        try:
            sch = get_scheduler()
            line("调度器", f"{sch.name} — {sch.status()}")
        except Exception as e:
            line("调度器", f"❌ {type(e).__name__}: {e}")

        if args.apply:
            import glob as _g
            metas = sorted(_g.glob(os.path.join(ROOT, "seed", "meta", "*.json")))
            if metas:
                import json as _j
                import render as _r
                info = _j.load(open(metas[0], encoding="utf-8"))
                img = os.path.join(ROOT, "seed", "img", f"{info['objectID']}_small.jpg")
                out = os.path.join(os.environ.get("TMPDIR", "/tmp"), "metwall_doctor.jpg")
                canvas, _ = _r.render(info, "gallery", (1920, 1080), img)
                canvas.save(out, "JPEG", quality=85)
                print(f"\n  实测设壁纸 ← {out}")
                try:
                    print(f"  set() 返回: {setter.set(out)}")
                except Exception as e:
                    print(f"  set() 异常: {type(e).__name__}: {e}")
    except Exception as e:
        line("适配层", f"❌ {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
