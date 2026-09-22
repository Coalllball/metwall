"""Met Museum 艺术壁纸 CLI（跨平台：Windows / Linux / macOS）。

用法:
  python wallpaper.py next [--style gallery|minimal|label|random] [--no-apply]
  python wallpaper.py set <objectID> [--style ...] [--no-apply]
  python wallpaper.py search <关键词>
  python wallpaper.py schedule --install --every 4     # 每4小时自动换
  python wallpaper.py schedule --remove
  python wallpaper.py schedule --status
"""
import argparse
import os
import re
import sys
import time

import met
import notes
import render
import store
from console import setup_console
from platforms import get_scheduler, get_setter, monitors, open_image

CACHE = met.CACHE
OUT_DIR = os.path.join(CACHE, "wallpapers")

setter = get_setter()


# ── 主流程 ───────────────────────────────────────────────────
def make_wallpaper(info, style):
    """下载图 → 合成 → 存盘（多屏时每屏各渲染一份，主屏应用）。

    返回 (输出路径, 实际风格)。多屏时输出列表 [(屏名, 路径)] 存盘。
    """
    img_path = met.fetch_image(info)
    if not img_path:
        raise RuntimeError("该作品没有可用图片")

    os.makedirs(OUT_DIR, exist_ok=True)
    size = setter.screen_size()

    # 多屏：每屏按各自分辨率渲染（比例正确不拉伸）
    # random 必须先解析成具体风格：否则循环里每调一次 render("random") 就重摇一次，
    # 三块屏会得到三种不同排版。
    if style == "random":
        import random as _r
        style = _r.choice(list(render.STYLES))

    ms = monitors()
    if len(ms) > 1:
        paths = []
        for i, m in enumerate(ms):
            s = (m["w"], m["h"])
            canvas, used_style = render.render(info, style, s, img_path)
            tag = "主" if m["primary"] else f"副{i}"
            out = os.path.join(OUT_DIR, f"{info['objectID']}_{used_style}_{tag}.jpg")
            canvas.save(out, "JPEG", quality=95)
            paths.append((tag, out))
        # 主屏应用（每屏独立设置待 COM 环境支持，见 set_multi）
        primary = next(p for p in paths if p[0] == "主")
        return paths, primary[1], used_style

    canvas, used_style = render.render(info, style, size, img_path)
    out = os.path.join(OUT_DIR, f"{info['objectID']}_{used_style}.jpg")
    canvas.save(out, "JPEG", quality=95)
    return None, out, used_style


def print_info(info):
    s = met.summarize(info)
    print(f"  {s['title']}")
    print(f"  {s['artist']}  ·  {s['date']}")
    if s["medium"]:
        print(f"  材质: {s['medium'][:80]}")
    if s["description"] and s["description"] != s["url"]:
        print(f"  简介: {s['description'][:120]}")
    print(f"  详情: {s['url']}")


def apply_or_report(paths, out, used, no_apply):
    if no_apply:
        if paths:
            for tag, p in paths:
                print(f"  已生成（未应用）[{tag}屏]: {p}  [风格: {used}]")
        else:
            print(f"\n已生成（未应用）: {out}  [风格: {used}]")
    else:
        ok = setter.set(out)
        print(f"\n[风格: {used}] 壁纸已{'应用' if ok else '应用失败'}: {out}")
        if paths and len(paths) > 1:
            print(f"  另生成 {len(paths) - 1} 张副屏版（每屏分辨率独立渲染）")


def cmd_next(args):
    """随机/收藏池拉一件，带防重复（排除最近 N 条历史）。"""
    info = _pick_artwork(args)
    print("随机命中:")
    print_info(info)
    paths, out, used = make_wallpaper(info, args.style)
    apply_or_report(paths, out, used, args.no_apply)


def _pick_artwork(args):
    """按池 + 防重复选择作品：--pool favorites 收藏池；--avoid-recent N 排除最近 N 条。"""
    import random as _r
    excluded = set()
    if getattr(args, "avoid_recent", 0) > 0:
        excluded = {h.get("id") for h in store.list_history(args.avoid_recent)}

    if args.pool == "favorites":
        favs = [f for f in store.list_favorites() if f not in excluded]
        if not favs:
            print("收藏池为空或全在防重复区，回退随机拉取")
            return met.random_artwork()
        return met.get_object(_r.choice(favs))

    # 默认池：随机拉，避开防重复区（最多重试 5 次）
    for _ in range(5):
        info = met.random_artwork()
        if info["objectID"] not in excluded:
            return info
    return info


def cmd_set(args):
    info = met.get_object(args.object_id)
    print_info(info)
    paths, out, used = make_wallpaper(info, args.style)
    apply_or_report(paths, out, used, args.no_apply)


def cmd_search(args):
    ids = met.search(args.query)
    print(f"找到 {len(ids)} 件作品，列出前 10 条:")
    for i, oid in enumerate(ids[:10]):
        info = met.get_object(oid)
        s = met.summarize(info)
        print(f"  [{i}] {oid}  {s['title'][:60]}  —  {s['artist'][:30]}  ({s['date']})")
    print("\n用 `python wallpaper.py set <objectID>` 选择")


def cmd_monitors(args):
    """显示所有显示器信息（多屏适配诊断）。"""
    ms = monitors()
    if not ms:
        print("无法枚举显示器（非 Windows 或 API 失败）")
        return
    print(f"显示器数量: {len(ms)}")
    for m in ms:
        tag = "主屏" if m["primary"] else "副屏"
        print(f"  [{tag}] {m['w']}x{m['h']} @ ({m['x']},{m['y']})  比例 {m['w']/m['h']:.3f}")
    # 每屏独立壁纸可用性
    try:
        from platforms.windows import monitor_paths
        paths = monitor_paths()
        if paths:
            print(f"每屏独立壁纸（IDesktopWallpaper）: 可用（{len(paths)} 屏）")
        else:
            print("每屏独立壁纸（IDesktopWallpaper）: 不可用（COM 注册不完整，当前为各屏填充同一壁纸）")
    except Exception:
        pass


# ── 浏览 / 收藏 / 历史 ──────────────────────────────────────
def cmd_browse(args):
    """交互浏览候选：逐件文本展示，Enter 预览 / 数字应用 / f 收藏 / n 换批 / q 退出。"""
    n = args.count
    while True:
        print(f"\n正在拉取 {n} 件候选...")
        try:
            cands = met.random_candidates(n)
        except RuntimeError as e:
            print(f"拉取失败: {e}")
            return
        # 预下载小图，保证 Enter 预览秒开
        for info in cands:
            try:
                met.fetch_image(info, small=True)
            except Exception:
                pass

        for i, info in enumerate(cands, 1):
            s = met.summarize(info)
            fav = "♥" if store.is_favorite(info["objectID"]) else " "
            print(f"\n── 候选 {i}/{n} {fav} ─────────────────────────")
            print(f"  {s['title']}")
            print(f"  {s['artist']}  ·  {s['date']}")
            meta = " · ".join(x for x in [s["department"], s["medium"]] if x)
            if meta:
                print(f"  {meta}")
            while True:
                ans = input(f"  [1-{n}] 应用  [Enter] 预览  [f] 收藏  [n] 下一件  [q] 退出 > ").strip().lower()
                if ans == "":
                    p = met.fetch_image(info, small=True)
                    if p:
                        open_image(p)
                    else:
                        print("  该作品无预览图")
                elif ans == "f":
                    store.add_favorite(info["objectID"])
                    print(f"  ♥ 已收藏（{s['title'][:40]}）")
                elif ans == "n":
                    break
                elif ans == "q":
                    print("  再见")
                    return
                elif ans.isdigit() and 1 <= int(ans) <= n:
                    target = cands[int(ans) - 1]
                    try:
                        paths, out, used = make_wallpaper(target, args.style)
                    except RuntimeError as e:
                        print(f"  生成失败: {e}")
                        continue
                    setter.set(out)
                    store.add_history(target["objectID"], used)
                    print(f"  ✓ 已应用 [风格:{used}]: {met.summarize(target)['title']}")
                    return
                else:
                    print("  无效输入")
        print("\n本批看完，拉下一批...")


def cmd_favorite(args):
    if args.add:
        ok = store.add_favorite(args.add)
        print("✓ 已收藏" if ok else "已在收藏中")
    elif args.remove:
        ok = store.remove_favorite(args.remove)
        print("✓ 已取消收藏" if ok else "不在收藏中")
    else:
        favs = store.list_favorites()
        if not favs:
            print("收藏为空。browse 里按 f 收藏，或 `wallpaper favorite add <objectID>`")
            return
        for oid in favs:
            try:
                s = met.summarize(met.get_object(oid))
                print(f"  {oid}  {s['title'][:55]}  —  {s['artist'][:25]}  ({s['date']})")
            except Exception:
                print(f"  {oid}  (获取失败)")


def cmd_history(args):
    hist = store.list_history(args.limit)
    if not hist:
        print("暂无历史")
        return
    for h in hist:
        try:
            s = met.summarize(met.get_object(h["id"]))
            t = time.strftime("%m-%d %H:%M", time.localtime(h["time"]))
            print(f"  {t}  [{h['style']:>7}]  {s['title'][:50]}  —  {s['artist'][:22]}")
        except Exception:
            print(f"  {h['id']}  (获取失败)")


# ── Web dashboard ───────────────────────────────────────────
def _lan_ips():
    """本机局域网 IPv4 列表。"""
    import socket
    ips = set()
    try:
        host = socket.gethostname()
        for info in socket.getaddrinfo(host, None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    # ipconfig 兜底
    try:
        out = os.popen("ipconfig").read()
        for m in re.finditer(r"IPv4[^\d]*([\d.]+)", out):
            ip = m.group(1)
            if not ip.startswith(("127.", "169.254.")):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


def cmd_serve(args):
    """启动 web dashboard（浏览器管理面板）。"""
    try:
        import uvicorn
    except ImportError:
        sys.exit("缺少依赖：pip install fastapi uvicorn")
    from server.app import app
    print(f"Met Wallpaper dashboard → http://127.0.0.1:{args.port}")
    if args.host in ("0.0.0.0", ""):
        for ip in _lan_ips():
            print(f"  局域网访问          → http://{ip}:{args.port}")
        print("  提示：Windows 防火墙可能拦截入站，放行命令：")
        print(f'    netsh advfirewall firewall add rule name="MetWallpaper" '
              f'dir=in action=allow protocol=TCP localport={args.port}')
    if not notes.get_proxy():
        print("  作品简介：未配置代理，Wikipedia 不可达（直连被墙）。"
              "`wallpaper config proxy http://127.0.0.1:7897` 启用多语言简介")
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    except KeyboardInterrupt:
        # Ctrl+C 干净退出：uvicorn 默认会刷一大坨 KeyboardInterrupt/
        # CancelledError traceback（服务停止时在途请求被取消），看着像故障
        print("\n服务已停止")
    except Exception as e:
        print(f"\n服务异常退出: {e}")


def cmd_config(args):
    """查看/设置代理（Wikipedia 简介用）。"""
    import notes as _notes
    if args.proxy is not None:
        _notes.set_proxy(args.proxy)
        print(f"代理已设置: {args.proxy}")
    else:
        p = _notes.get_proxy()
        print(f"当前代理: {p or '（未设置，Wikipedia 简介不可用）'}")


# ── 种子包（发布预打包，首用用户秒开）───────────────────────
def cmd_seed(args):
    """预下载一批作品（meta + 小图）到 seed/ 目录，随发布包分发。

    首用用户启动 serve 时自动初始化进数据目录，瀑布流直接有图。
    """
    import json as _json
    import shutil as _shutil

    base = os.path.dirname(os.path.abspath(__file__))
    seed_dir = os.path.join(base, "seed")
    meta_dir, img_dir = os.path.join(seed_dir, "meta"), os.path.join(seed_dir, "img")
    os.makedirs(meta_dir, exist_ok=True)
    os.makedirs(img_dir, exist_ok=True)

    print(f"正在预下载 {args.count} 件作品到 seed/ ...")
    infos = met.random_candidates(args.count)
    n = 0
    for info in infos:
        oid = info["objectID"]
        try:
            p = met.fetch_image(info, small=True)
            if not p:
                continue
            with open(os.path.join(meta_dir, f"{oid}.json"), "w", encoding="utf-8") as f:
                _json.dump(info, f, ensure_ascii=False)
            _shutil.copy2(p, os.path.join(img_dir, os.path.basename(p)))
            n += 1
            print(f"  [{n}/{args.count}] {oid}  {info.get('title', '')[:44]}")
        except Exception as e:
            print(f"  ✗ {oid}: {e}")
    size_mb = sum(os.path.getsize(os.path.join(img_dir, f)) for f in os.listdir(img_dir)) / 1e6 if os.path.isdir(img_dir) else 0
    print(f"\n完成：{n} 件，seed/ 共 {size_mb:.1f} MB（随发布包分发）")


# ── 定时调度 ─────────────────────────────────────────────────
def cmd_schedule(args):
    scheduler = get_scheduler()
    if args.remove:
        ok, msg = scheduler.remove()
        print((f"已卸载定时任务" if ok else f"卸载失败: {msg}") + f"（{scheduler.status()}）")
        return
    if args.install:
        if not args.every:
            sys.exit("--install 需要 --every N（小时）")
        extra = f"--style {args.style} --pool {args.pool} --avoid-recent {args.avoid_recent}"
        ok, msg = scheduler.install(args.every, sys.executable,
                                    os.path.abspath(__file__), extra=extra)
        print((f"已安装定时任务" if ok else f"安装失败: {msg}")
              + f"，每 {args.every} 小时自动换一张"
              + f"（风格 {args.style}，池 {args.pool}，防重复 {args.avoid_recent} 条）"
              + f"（{scheduler.status()}）")
        return
    print(f"定时任务状态: {scheduler.status()}")


def main():
    setup_console()
    ap = argparse.ArgumentParser(description="Met Museum 艺术壁纸（跨平台）")
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("next", help="随机拉一件作品并设为壁纸")
    p.add_argument("--style", default="random",
                   choices=list(render.STYLES) + ["random"],
                   help="排版风格（默认 random）")
    p.add_argument("--pool", default="all", choices=["all", "favorites"],
                   help="作品池：all 随机 / favorites 收藏池（默认 all）")
    p.add_argument("--avoid-recent", type=int, default=0,
                   help="排除最近 N 条已应用历史（防重复，默认 0）")
    p.add_argument("--no-apply", action="store_true", help="只生成不设置壁纸")
    p.set_defaults(fn=cmd_next)

    p = sub.add_parser("set", help="按 objectID 指定作品")
    p.add_argument("object_id", type=int)
    p.add_argument("--style", default="random", choices=list(render.STYLES) + ["random"])
    p.add_argument("--no-apply", action="store_true")
    p.set_defaults(fn=cmd_set)

    p = sub.add_parser("search", help="搜索作品")
    p.add_argument("query")
    p.set_defaults(fn=cmd_search)

    p = sub.add_parser("browse", help="交互浏览候选（预览/应用/收藏）")
    p.add_argument("--count", type=int, default=5, help="每批候选数（默认5）")
    p.add_argument("--style", default="random",
                   choices=list(render.STYLES) + ["random"],
                   help="应用时的排版风格（默认 random）")
    p.set_defaults(fn=cmd_browse)

    p = sub.add_parser("favorite", help="收藏管理")
    p.add_argument("--add", type=int, help="收藏指定 objectID")
    p.add_argument("--remove", type=int, help="取消收藏")
    p.set_defaults(fn=cmd_favorite)

    p = sub.add_parser("history", help="最近应用的壁纸")
    p.add_argument("--limit", type=int, default=10, help="条数（默认10）")
    p.set_defaults(fn=cmd_history)

    p = sub.add_parser("monitors", help="显示所有显示器信息")
    p.set_defaults(fn=cmd_monitors)

    p = sub.add_parser("serve", help="启动 web dashboard")
    p.add_argument("--host", default="127.0.0.1", help="监听地址（0.0.0.0=局域网）")
    p.add_argument("--port", type=int, default=8000, help="端口（默认8000）")
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser("config", help="查看/设置配置（如代理）")
    p.add_argument("proxy", nargs="?", default=None,
                   help="代理地址，如 http://127.0.0.1:7897（不带参数则查看）")
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser("seed", help="预下载种子包（发布打包用，首用用户秒开）")
    p.add_argument("--count", type=int, default=24, help="作品数（默认24）")
    p.set_defaults(fn=cmd_seed)

    p = sub.add_parser("schedule", help="定时自动换壁纸")
    p.add_argument("--install", action="store_true", help="安装定时任务")
    p.add_argument("--every", type=int, default=4, help="间隔小时数（默认4）")
    p.add_argument("--style", default="random", choices=list(render.STYLES) + ["random"],
                   help="轮换风格（默认 random）")
    p.add_argument("--pool", default="all", choices=["all", "favorites"],
                   help="轮换作品池（默认 all）")
    p.add_argument("--avoid-recent", type=int, default=0,
                   help="排除最近 N 条已应用历史（防重复）")
    p.add_argument("--remove", action="store_true", help="卸载定时任务")
    p.add_argument("--status", action="store_true", help="查看任务状态")
    p.set_defaults(fn=cmd_schedule)

    args = ap.parse_args()
    if not getattr(args, "fn", None):
        ap.print_help()
        sys.exit(0)
    args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
