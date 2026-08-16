"""本地数据存储：收藏 + 历史（JSON，数据目录下）。

纯数据层，不依赖 CLI/渲染——未来的 web dashboard 后端直接 import 复用。
"""
import json
import os
import time

from platforms.base import user_data_dir

DATA_DIR = os.path.join(user_data_dir(), "metwall")
FAVORITES = os.path.join(DATA_DIR, "favorites.json")
HISTORY = os.path.join(DATA_DIR, "history.json")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save(path, data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)


# ── 收藏 ────────────────────────────────────────────────────
def list_favorites():
    return _load(FAVORITES, [])


def is_favorite(object_id):
    return object_id in list_favorites()


def add_favorite(object_id):
    favs = list_favorites()
    if object_id not in favs:
        favs.append(object_id)
        _save(FAVORITES, favs)
        return True
    return False


def remove_favorite(object_id):
    favs = list_favorites()
    if object_id in favs:
        favs.remove(object_id)
        _save(FAVORITES, favs)
        return True
    return False


# ── 历史（最近应用过的作品）─────────────────────────────────
def add_history(object_id, style):
    hist = list_history(limit=1000)
    hist = [h for h in hist if h["id"] != object_id]  # 去重，保留最新
    hist.insert(0, {"id": object_id, "style": style, "time": int(time.time())})
    _save(HISTORY, hist[:200])


def list_history(limit=10):
    return _load(HISTORY, [])[:limit]
