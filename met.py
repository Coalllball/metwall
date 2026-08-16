"""Met Museum public API client + local cache."""
import json
import os
import random
import re
import time

import requests

from platforms.base import user_data_dir

BASE = "https://collectionapi.metmuseum.org/public/collection/v1"
UA = {"User-Agent": "wallpaper-app/0.1 (personal desktop wallpaper tool)"}

CACHE = os.path.join(user_data_dir(), "metwall")
META_DIR = os.path.join(CACHE, "meta")   # object detail JSON
IMG_DIR = os.path.join(CACHE, "img")     # downloaded artwork images

# 题材词：随机抽一个做 search，保证画风多样性
TOPICS = [
    "painting", "landscape", "portrait", "still life", "seascape",
    "impressionism", "japanese", "egyptian", "greek", "sculpture",
    "flower", "cityscape", "watercolor", "abstract",
]

MAX_ATTEMPTS = 12  # 随机拉取的重试上限


def _get(path, params=None, timeout=30, retries=1):
    """GET + JSON。429 限流时退避重试。"""
    for attempt in range(retries):
        try:
            r = requests.get(f"{BASE}{path}", params=params, headers=UA, timeout=timeout)
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)
    return {}  # unreachable


def _meta_path(object_id):
    return os.path.join(META_DIR, f"{object_id}.json")


def get_object(object_id, use_cache=True):
    """Fetch object detail, cached to disk. 限流时重试（Met 429 常见）。"""
    p = _meta_path(object_id)
    if use_cache and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    info = _get(f"/objects/{object_id}", retries=2)
    os.makedirs(META_DIR, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(info, f, ensure_ascii=False, indent=1)
    return info


def _img_path(info, small=False):
    url = info.get("primaryImageSmall") if small else (info.get("primaryImage") or info.get("primaryImageSmall"))
    if not url:
        return None
    ext = os.path.splitext(url)[1] or ".jpg"
    name = f"{info['objectID']}_small" if small else f"{info['objectID']}"
    return os.path.join(IMG_DIR, f"{name}{ext}")


def fetch_image(info, small=False):
    """Download artwork image (cached). Returns local path or None.

    small=True 时用 primaryImageSmall（几百 KB，适合快速预览），
    存 {id}_small 文件；正式应用时用 primaryImage（高清大图），存 {id}。
    两者互不覆盖。
    """
    url = (info.get("primaryImageSmall") if small else None) \
        or info.get("primaryImage") or info.get("primaryImageSmall")
    if not url:
        return None
    p = _img_path(info, small=small)
    if p and os.path.exists(p):
        return p
    os.makedirs(IMG_DIR, exist_ok=True)
    # 下载失败重试（Met 图片 CDN 偶发 429/超时）
    for attempt in range(3):
        try:
            r = requests.get(url, headers=UA, timeout=60)
            r.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise
            time.sleep(1 + attempt)
    with open(p, "wb") as f:
        f.write(r.content)
    if small:
        # 小图入库（候选池记录，带标题/作者供堆叠分组）+ 记录宽高比
        try:
            import library
            oid = info["objectID"]
            library.ensure([oid],
                           {oid: info.get("title") or ""},
                           {oid: info.get("artistDisplayName") or ""})
            try:
                from PIL import Image as _I
                with _I.open(p) as im:
                    library.set_ratio(info["objectID"], round(im.width / im.height, 4))
            except Exception:
                pass
        except Exception:
            pass
    return p


def search(q, has_images=True, retries=3, artist=None):
    """Return objectIDs list for a query. 失败重试 3 次（Met 偶发限流）。

    artist: 按艺术家/文化筛选（artistOrCulture）
    """
    params = {"q": q, "hasImages": "true" if has_images else "false"}
    if artist:
        params["artistOrCulture"] = artist
    for attempt in range(retries):
        try:
            data = _get("/search", params)
            return data.get("objectIDs") or []
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(1 + attempt)
    return []


def departments():
    """Met 部门列表。"""
    data = _get("/departments")
    return data.get("departments") or []


def _usable(info):
    """作品可用性：有图、标题存在。isPublicDomain 不强制——只用作壁纸，个人使用没问题。"""
    return bool(info.get("primaryImage") or info.get("primaryImageSmall")) and bool(info.get("title"))


def cached_ids():
    """数据目录里已有小图的作品 ID 列表（本地秒开池，dashboard 优先用）。"""
    ids = []
    try:
        for fn in os.listdir(IMG_DIR):
            if fn.endswith("_small.jpg") or fn.endswith("_small.png"):
                ids.append(int(fn.split("_")[0]))
    except OSError:
        pass
    return ids


def init_from_seed(seed_dir):
    """首次启动初始化：把发布包内的 seed 资源（meta + 小图）复制进数据目录。

    返回复制的文件数。seed 目录结构：meta/*.json + img/*_small.*
    """
    if not os.path.isdir(seed_dir):
        return 0
    copied = 0
    for sub, dst in (("meta", META_DIR), ("img", IMG_DIR)):
        src = os.path.join(seed_dir, sub)
        if not os.path.isdir(src):
            continue
        os.makedirs(dst, exist_ok=True)
        for fn in os.listdir(src):
            sp, dp = os.path.join(src, fn), os.path.join(dst, fn)
            if not os.path.exists(dp):
                try:
                    import shutil
                    shutil.copy2(sp, dp)
                    copied += 1
                except OSError:
                    pass
    return copied


def random_artwork():
    """随机拉一件可用作品。题材随机 + ID 随机 + 重试。"""
    return random_candidates(1)[0]


def random_candidates(n):
    """随机拉 n 件可用作品（去重 + 并行取详情，几秒内返回）。

    策略：3 个随机题材搜索收集 ID 池 → 随机抽取 → 线程池并行取详情。
    个别 ID 404/网络失败会被跳过（Met 有下架作品）。
    同名/同系列作品不再过滤——由堆叠分组（标题+作者）统一展示。
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed

    pool = []
    for _ in range(3):
        topic = random.choice(TOPICS)
        try:
            ids = search(topic)
            if ids:
                pool.extend(ids)
        except requests.RequestException:
            continue
    pool = list(dict.fromkeys(pool))  # 去重保序
    if not pool:
        raise RuntimeError("随机拉取失败：搜索无结果")

    picked, out = set(), []
    with ThreadPoolExecutor(max_workers=8) as ex:
        while len(out) < n and len(picked) < len(pool):
            batch = [i for i in random.sample(pool, min(len(pool), n * 3)) if i not in picked]
            if not batch:
                break
            picked.update(batch)
            futs = {ex.submit(get_object, oid): oid for oid in batch}
            for f in as_completed(futs):
                try:
                    info = f.result()
                except Exception:
                    continue  # 404/网络错误：跳过该 ID
                if _usable(info):
                    out.append(info)
    if not out:
        raise RuntimeError("随机拉取失败：多次尝试未找到可用作品")
    return out[:n]


def summarize(info):
    """控制台展示用的作品信息摘要。"""
    return {
        "id": info.get("objectID"),
        "title": info.get("title"),
        "artist": info.get("artistDisplayName") or "Unknown artist",
        "date": info.get("objectDate") or "n.d.",
        "medium": info.get("medium") or "",
        "dimensions": info.get("dimensions") or "",
        "culture": info.get("culture") or "",
        "department": info.get("department") or "",
        "period": info.get("period") or "",
        "creditLine": info.get("creditLine") or "",
        "accessionNumber": info.get("accessionNumber") or "",
        "description": (info.get("description") or "").strip() or (info.get("objectURL") or ""),
        "image": info.get("primaryImage") or info.get("primaryImageSmall"),
        "url": info.get("objectURL"),
    }
