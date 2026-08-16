"""Web dashboard 后端：FastAPI 单体。

数据层全部复用 met.py / store.py / render.py，本文件只做 HTTP 壳。
启动：wallpaper serve（或 uvicorn server.app:app）
"""
import os
import re
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import library
import met
import notes
import render
import store

app = FastAPI(title="Met Wallpaper Dashboard", version="0.1.0")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
WP_DIR = os.path.join(met.CACHE, "wallpapers")
SEED_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "seed")

# 首次启动：把发布包内的 seed 资源复制进数据目录（首用用户直接有图）
try:
    n = met.init_from_seed(os.path.abspath(SEED_DIR))
    if n:
        print(f"[metwall] 已从 seed 初始化 {n} 个文件")
except Exception:
    pass


# ── API ─────────────────────────────────────────────────────
def _img_ratio(oid):
    """作品图宽高比：库里查，无则从文件懒读并记录。"""
    r = library.ratio(oid)
    if r:
        return r
    try:
        p = met._img_path(met.get_object(oid), small=True)
        if p and os.path.exists(p):
            from PIL import Image as _I
            with _I.open(p) as im:
                r = round(im.width / im.height, 4)
                library.set_ratio(oid, r)
    except Exception:
        pass
    return r or 4 / 3


def _card(info, cached=False, group=None):
    oid = info["objectID"]
    s = met.summarize(info)
    return {
        "id": oid,
        "title": s["title"],
        "artist": s["artist"],
        "date": s["date"],
        "department": s["department"],
        "medium": s["medium"],
        "thumb": f"/media/img/{oid}_small.jpg",
        "image": f"/media/img/{oid}.jpg",
        "cached": cached,
        "ratio": _img_ratio(oid),
        "group": group or {"count": 1, "ids": [oid]},
    }


def _group_by_title(rows, exclude_set):
    """(id, title, artist) 行按 (标题, 作者) 分组：同标题且同作者并一组（堆叠）。

    同标题不同作者（如不同画家的《天使报喜》）是不同作品，不并组。
    组代表 = 第一个（最新入库）。
    """
    groups = {}
    for oid, title, artist in rows:
        if oid in exclude_set:
            continue
        key = (title or f"#{oid}", artist or "")
        groups.setdefault(key, []).append(oid)
    return groups


def _group_members(rep_ids, ids, max_members=20):
    """组卡片：代表 + 组内已有小图的成员（前端 hover 轮播用）。"""
    members = [rep_ids[0]]
    for oid in rep_ids[1:]:
        try:
            p = met._img_path(met.get_object(oid), small=True)
            if p and os.path.exists(p):
                members.append(oid)
                if len(members) >= max_members:
                    break
        except Exception:
            continue
    return {"count": len(ids), "ids": members}


def _list_cards(ids):
    """ID 列表 → 卡片数据（跳过获取失败的）。"""
    out = []
    for oid in ids:
        try:
            info = met.get_object(oid)
            out.append(_card(info, cached=True))
        except Exception:
            continue
    return out


# 会话级"已返回"记录（防单次会话内重复）
from collections import deque
_served = deque(maxlen=400)


def _interleave(groups):
    """多部门轮询交错（用于分隔符池，防尾部同部门扎堆）。"""
    from collections import defaultdict, deque
    g = defaultdict(deque)
    for c in groups:
        g[c.get("department", "")].append(c)
    keys = sorted(g, key=lambda k: -len(g[k]))
    out = []
    while any(g[k] for k in keys):
        for k in keys:
            if g[k]:
                out.append(g[k].popleft())
    return out


def _diversify(cards, max_same=3):
    """打散：最大组均匀切段，其他部门作分隔符插入（对标平台显式多样化）。

    例：12 张 Asian Art + 4 张其他 → A A A E A A A E A A A E A A A E（3 连封顶）。
    分隔符剩余部分先做部门轮询交错，避免尾部同部门扎堆。
    空列表直接返回（防 keys[0] 越界）。
    """
    if not cards:
        return cards
    from collections import defaultdict
    groups = defaultdict(list)
    for c in cards:
        groups[c.get("department", "")].append(c)
    keys = sorted(groups, key=lambda k: -len(groups[k]))
    main = groups[keys[0]]
    others = _interleave([c for k in keys[1:] for c in groups[k]])

    n_seg = (len(main) + max_same - 1) // max_same
    out = []
    seg = max(len(main) / n_seg, 1) if n_seg else 1
    oi = 0
    for s in range(n_seg):
        start = int(s * seg)
        end = int((s + 1) * seg) if s < n_seg - 1 else len(main)
        out.extend(main[start:end])
        if oi < len(others):
            out.append(others[oi])
            oi += 1
    out.extend(others[oi:])
    return out


@app.get("/api/search")
def api_search(q: str, count: int = 24):
    """关键词/艺术家搜索 → 卡片列表。详情并行拉取（串行会慢到前端超时）。"""
    if not q.strip():
        return {"cards": []}
    try:
        ids = met.search(q)[:count * 3]
    except Exception:
        raise HTTPException(503, "Met 搜索暂不可用（限流或网络），请稍后再试")
    from concurrent.futures import ThreadPoolExecutor, as_completed
    cards = []
    ex = ThreadPoolExecutor(max_workers=8)
    try:
        futs = {ex.submit(met.get_object, oid): oid for oid in ids}
        for f in as_completed(futs):
            try:
                info = f.result()
            except Exception:
                continue
            cached = os.path.exists(met._img_path(info, small=True) or "")
            cards.append(_card(info, cached=cached))
            if len(cards) >= count:
                break
    finally:
        # 不等未完成的任务：with 块会 shutdown(wait=True) 等到全部完成（含限流重试）
        ex.shutdown(wait=False)

    # ── 精确性后处理（Met 全文搜索不区分艺术家/标题）──
    ql = q.strip().lower()
    # 1) 搜索词命中艺术家名 → 只保留该艺术家的作品（搜 Monet 只看到莫奈的画）
    artist_hits = [c for c in cards if ql in (c.get("artist") or "").lower()]
    if artist_hits:
        return {"cards": artist_hits[:count]}
    # 2) 否则标题精确/前缀匹配优先（搜作品名时精确结果排最前）
    exact = [c for c in cards if ql == (c.get("title") or "").lower()]
    starts = [c for c in cards
              if ql and (c.get("title") or "").lower().startswith(ql) and c not in exact]
    rest = [c for c in cards if c not in exact and c not in starts]
    return {"cards": (exact + starts + rest)[:count]}


@app.get("/api/candidates")
def api_candidates(count: int = 24, exclude: str = ""):
    """随机候选（按同名系列分组堆叠）：unseen 组优先 → seen 组（LRU）→ 拉新。

    - 同标题作品并成一组，只出一个代表卡片（角标 ×N，hover 轮播预览）
    - seen 按 last_seen 升序：看过的图要等其他图轮过一遍才重现
    - 同部门打散 + 水位触发补货
    """
    import random
    exclude_set = {int(x) for x in exclude.split(",") if x.strip().isdigit()} | set(_served)
    cards = []
    seen_all = set()  # 本批已返回的组员 ID（防批内重复）

    # A) unseen 组：新入库优先，足够则整批全缓存秒开
    for title, ids in _group_by_title(library.unseen_rows(400), exclude_set).items():
        if len(cards) >= count:
            break
        rep = ids[0]
        try:
            info = met.get_object(rep)
            cards.append(_card(info, cached=True, group=_group_members(ids, ids)))
        except Exception:
            continue
        exclude_set.update(ids)   # 组员整组排除（只出代表）
        seen_all.update(ids)

    # B) seen 组：最久未看优先（LRU），补足
    need = count - len(cards)
    if need > 0:
        for title, ids in _group_by_title(library.seen_rows(400), exclude_set).items():
            if len(cards) >= count:
                break
            rep = ids[0]
            try:
                info = met.get_object(rep)
                cards.append(_card(info, cached=True, group=_group_members(ids, ids)))
            except Exception:
                continue
            exclude_set.update(ids)
            seen_all.update(ids)

    # C) 拉新兜底：结果一次性消费——立即入库 + seen，杜绝反复出现
    need = count - len(cards)
    if need > 0:
        try:
            known = library.all_ids()  # 库中已有（含 seen/unseen）不再拉
            infos = met.random_candidates(need + 6)
            for i in infos:
                oid = i["objectID"]
                if oid in exclude_set or oid in known:
                    continue
                cards.append(_card(i, cached=False))
                exclude_set.add(oid)
                seen_all.add(oid)
                try:
                    library.ensure([oid])      # 入库：拉新过滤已覆盖
                    library.mark_seen([oid])   # 立即消费：不进 unseen、不再被拉
                except Exception:
                    pass
                if len(cards) >= count:
                    break
        except Exception as e:
            if not cards:
                raise HTTPException(503, f"候选拉取失败（Met API 可能限流），稍后再试: {e}")

    # 同部门打散
    cards = _diversify(cards)

    # 水位触发：unseen 不足则后台补货（新图持续供给）
    if library.unseen_count() < 60:
        _start_prefetch()

    for c in cards:
        _served.append(c["id"])
        _served.extend(c["group"]["ids"][1:])  # 组员也入会话去重
    return {"cards": cards}


@app.post("/api/seen")
def api_seen(payload: dict):
    """前端渲染后批量标记已看过（body: {"ids": [...]}）。

    同标题组员一并标记——堆叠组的组员不单独出卡。
    """
    ids = payload.get("ids") or []
    library.mark_seen(ids)
    library.mark_seen(library.siblings(ids))
    return {"ok": True}


# ── 拉新入库：用户一进来即触发，新图下批优先展示 ────────────
_prefetch_thread = None


def _start_prefetch(limit=12):
    """后台拉取新图下载入库（幂等：已有线程在跑则跳过）。"""
    global _prefetch_thread
    if _prefetch_thread and _prefetch_thread.is_alive():
        return
    import threading

    def worker():
        try:
            infos = met.random_candidates(limit)
            for info in infos:
                try:
                    met.fetch_image(info, small=True)  # 下载后自动 ensure 入库
                except Exception:
                    continue
        except Exception:
            pass

    _prefetch_thread = threading.Thread(target=worker, daemon=True, name="metwall-prefetch")
    _prefetch_thread.start()


@app.post("/api/prefetch")
def api_prefetch():
    """用户进入页面时调用：后台开始拉新图入库。"""
    _start_prefetch()
    return {"ok": True}


# ── 服务启动：存量缓存入库 + 预热（seed/缓存复用，零网络）───
def _init_library():
    """把已下载的 small 图全部登记入库（老缓存/seed 一次性入池）+ 回填标题/作者。"""
    try:
        ids = met.cached_ids()
        titles, artists = {}, {}
        for oid in ids:
            mp = os.path.join(met.META_DIR, f"{oid}.json")
            if os.path.exists(mp):
                try:
                    import json as _json
                    with open(mp, encoding="utf-8") as f:
                        d = _json.load(f)
                        titles[oid] = d.get("title") or ""
                        artists[oid] = d.get("artistDisplayName") or ""
                except Exception:
                    pass
        library.ensure(ids, titles or None, artists or None)
    except Exception:
        pass


def _backfill_ratios():
    """后台全量回填图片宽高比（存量图懒读只覆盖被请求过的卡片，93% 缺失）。

    小图与大图同比例（Met 同比例缩放），读 small 文件即可。
    """
    import threading

    def worker():
        try:
            for fn in os.listdir(met.IMG_DIR):
                if not fn.endswith("_small.jpg"):
                    continue
                oid = int(fn.split("_")[0])
                if library.ratio(oid):
                    continue
                from PIL import Image as _I
                with _I.open(os.path.join(met.IMG_DIR, fn)) as im:
                    library.set_ratio(oid, round(im.width / im.height, 4))
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True, name="metwall-ratios").start()


_init_library()
_backfill_ratios()


# ── 服务预热：池不够才拉新，够则直接复用（seed 包/历史缓存）──
def _prewarm(min_pool=24):
    """serve 启动时确保本地缓存池达到 min_pool 件。

    优先复用：seed 首充包（app 导入时已初始化进数据目录）和历史浏览缓存，
    全部本地秒开、零网络。仅当池不足时才从 Met 补缺口。
    """
    import threading

    def worker():
        try:
            have = len(met.cached_ids())
            if have >= min_pool:
                return
            infos = met.random_candidates(min_pool - have)
            for info in infos:
                try:
                    met.fetch_image(info, small=True)
                except Exception:
                    continue
        except Exception:
            pass

    t = threading.Thread(target=worker, daemon=True, name="metwall-prewarm")
    t.start()
    return t


_prewarm()


@app.get("/api/work/{object_id}")
def api_work(object_id: int):
    """作品详情（元数据；大图走 /media/img/{id}.jpg 按需下载）。堆叠组附带同组成员。"""
    try:
        info = met.get_object(object_id)
    except Exception:
        raise HTTPException(404, "作品不存在（可能已被 Met 下架）")
    s = met.summarize(info)
    out = {
        **s,
        "id": object_id,
        "image": f"/media/img/{object_id}.jpg",
        "thumb": f"/media/img/{object_id}_small.jpg",
        "favorite": store.is_favorite(object_id),
        "ratio": _img_ratio(object_id),
    }
    try:
        sib = library.siblings([object_id])
        if sib:
            out["group"] = {"count": len(sib) + 1, "ids": [object_id] + sib}
    except Exception:
        pass
    return out


# ── 收藏 / 历史 ─────────────────────────────────────────────
@app.get("/api/favorites")
def api_favorites():
    return {"items": _list_cards(store.list_favorites())}


@app.post("/api/favorites/{object_id}")
def api_favorite_add(object_id: int):
    return {"ok": store.add_favorite(object_id)}


@app.delete("/api/favorites/{object_id}")
def api_favorite_remove(object_id: int):
    return {"ok": store.remove_favorite(object_id)}


@app.get("/api/history")
def api_history(limit: int = 20):
    items = []
    for h in store.list_history(limit):
        try:
            c = _card(met.get_object(h["id"]))
        except Exception:
            continue
        c["style"] = h["style"]
        c["time"] = time.strftime("%m-%d %H:%M", time.localtime(h["time"]))
        items.append(c)
    return {"items": items}


@app.get("/api/styles")
def api_styles():
    return {"styles": list(render.STYLES) + ["random"]}


@app.get("/api/notes/{object_id}")
def api_notes(object_id: int, lang: str = "zh"):
    """作品背景简介（Wikipedia 多语言 / Met 官网兜底）。无简介返回空。"""
    if lang not in ("zh", "en"):
        raise HTTPException(400, "lang 仅支持 zh/en")
    try:
        info = met.get_object(object_id)
    except Exception:
        return {"note": None}
    note = notes.get_notes(object_id, lang=lang, info=info)
    if not note:
        return {"note": None}
    return {"note": {"title": note["title"], "extract": note["extract"],
                     "url": note["url"], "lang": lang}}


# ── 一键换壁纸（本机）───────────────────────────────────────
@app.post("/api/apply/{object_id}")
def api_apply(object_id: int, style: str = "random"):
    """渲染 + 设为壁纸 + 记历史。同步执行，耗时约 5-30 秒（首次下大图）。"""
    from platforms import get_setter

    if style not in list(render.STYLES) + ["random"]:
        raise HTTPException(400, f"未知风格: {style}")
    try:
        info = met.get_object(object_id)
        img_path = met.fetch_image(info)
        if not img_path:
            raise HTTPException(400, "该作品没有可用图片")
        setter = get_setter()
        canvas, used = render.render(info, style, setter.screen_size(), img_path)
        os.makedirs(WP_DIR, exist_ok=True)
        out = os.path.join(WP_DIR, f"{object_id}_{used}.jpg")
        canvas.save(out, "JPEG", quality=95)
        setter.set(out)
        store.add_history(object_id, used)
        return {"ok": True, "style": used, "title": info.get("title", ""),
                "wallpaper": f"/media/wallpapers/{os.path.basename(out)}"}
    except Exception as e:
        raise HTTPException(500, f"应用失败: {e}")


# ── 图片路由（按需下载 + 缓存）──────────────────────────────
def _serve_image(object_id: int, small: bool):
    try:
        info = met.get_object(object_id)
    except Exception:
        raise HTTPException(404, "作品不存在")
    try:
        p = met.fetch_image(info, small=small)
    except Exception:
        p = None
    if not p or not os.path.exists(p):
        raise HTTPException(404, "图片不可用")
    return FileResponse(p, headers={"Cache-Control": "public, max-age=86400"})


@app.get("/media/img/{name}")
def media_img(name: str):
    """按需下载并返回缓存图。name 形如 {id}.jpg 或 {id}_small.jpg。"""
    base = name.rsplit(".", 1)[0]
    small = base.endswith("_small")
    object_id = int(base[: -len("_small")] if small else base)
    return _serve_image(object_id, small)


# ── 静态资源（最后挂载，兜底）──────────────────────────────
from starlette.staticfiles import StaticFiles as _StaticFiles


class NoCacheStaticFiles(_StaticFiles):
    """给静态响应加 no-cache（开发迭代频繁，避免浏览器缓存旧版前端）。
    用子类而非 headers 参数：兼容旧版 starlette。"""

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


app.mount("/media/wallpapers", NoCacheStaticFiles(directory=WP_DIR), name="wallpapers")
app.mount("/", NoCacheStaticFiles(directory=STATIC_DIR, html=True), name="static")
