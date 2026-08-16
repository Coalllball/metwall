"""本地图片库：SQLite 表，记录作品是否被用户看过（seen）与上次曝光时间。

职责：
- 库 = 候选池的权威记录（有 small 图的作品）
- unseen 优先 → 新拉入的图排最前（ORDER BY added DESC）
- seen 按"最久未看优先"（LRU 循环）：看过一张图，要等其他所有图
  轮过一遍才重现——曝光抑制对标 Pinterest/小红书的信息流做法
- seen/last_seen 由前端渲染后批量上报
"""
import os
import sqlite3
import time

from platforms.base import user_data_dir

DB = os.path.join(user_data_dir(), "metwall", "library.db")


def _conn():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS works (
        id INTEGER PRIMARY KEY,
        title TEXT DEFAULT '',
        artist TEXT DEFAULT '',
        seen INTEGER DEFAULT 0,
        added INTEGER DEFAULT 0,
        last_seen INTEGER DEFAULT 0,
        ratio REAL DEFAULT 0
    )""")
    # 迁移：旧表缺列
    cols = [r[1] for r in conn.execute("PRAGMA table_info(works)")]
    if "last_seen" not in cols:
        conn.execute("ALTER TABLE works ADD COLUMN last_seen INTEGER DEFAULT 0")
    if "ratio" not in cols:
        conn.execute("ALTER TABLE works ADD COLUMN ratio REAL DEFAULT 0")
    if "title" not in cols:
        conn.execute("ALTER TABLE works ADD COLUMN title TEXT DEFAULT ''")
    if "artist" not in cols:
        conn.execute("ALTER TABLE works ADD COLUMN artist TEXT DEFAULT ''")
    conn.commit()
    return conn


def ensure(ids, titles=None, artists=None):
    """入库（幂等）：记录有 small 图的作品。新图 added=now（排最前）。

    titles: {id: title}、artists: {id: artist}——堆叠分组键 (title, artist) 用。
    """
    if not ids:
        return
    now = int(time.time())
    conn = _conn()
    try:
        conn.executemany(
            "INSERT OR IGNORE INTO works (id, title, artist, seen, added) VALUES (?, ?, ?, 0, ?)",
            [(i, (titles or {}).get(i, ""), (artists or {}).get(i, ""), now) for i in ids])
        if titles:
            conn.executemany(
                "UPDATE works SET title = ? WHERE id = ? AND title = ''",
                [(t, i) for i, t in titles.items()])
        if artists:
            conn.executemany(
                "UPDATE works SET artist = ? WHERE id = ? AND artist = ''",
                [(a, i) for i, a in artists.items()])
        conn.commit()
    finally:
        conn.close()


def mark_seen(ids):
    """标记已看过并记录曝光时间（前端渲染后上报）。"""
    if not ids:
        return
    now = int(time.time())
    conn = _conn()
    try:
        conn.executemany(
            "UPDATE works SET seen = 1, last_seen = ? WHERE id = ?",
            [(now, i) for i in ids])
        conn.commit()
    finally:
        conn.close()


def unseen_rows(limit=400):
    """未看过的图（id, title, artist），新入库优先。堆叠分组键 (title, artist)。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, title, artist FROM works WHERE seen = 0 ORDER BY added DESC LIMIT ?",
            (limit,)).fetchall()
        return rows
    finally:
        conn.close()


def unseen_ids(limit=200):
    """未看过的图 ID（新入库优先）。"""
    return [r[0] for r in unseen_rows(limit)]


def seen_rows(limit=400):
    """已看过的图（id, title, artist）：最久未看优先（LRU 循环）。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id, title, artist FROM works WHERE seen = 1 ORDER BY last_seen ASC LIMIT ?",
            (limit,)).fetchall()
        return rows
    finally:
        conn.close()


def seen_ids(limit=200):
    """已看过的图 ID（LRU）。"""
    return [r[0] for r in seen_rows(limit)]


def unseen_count():
    """未看过图的数量（新图供给水位）。"""
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM works WHERE seen = 0").fetchone()[0]
    finally:
        conn.close()


def seen_ids(limit=200):
    """已看过的图：最久未看优先（LRU 循环，重现间隔 = 池子大小）。"""
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT id FROM works WHERE seen = 1 ORDER BY last_seen ASC LIMIT ?",
            (limit,)).fetchall()
        return [r[0] for r in rows]
    finally:
        conn.close()


def ratio(oid):
    """查询作品图片宽高比（0 表示未知）。"""
    conn = _conn()
    try:
        r = conn.execute("SELECT ratio FROM works WHERE id = ?", (oid,)).fetchone()
        return r[0] if r and r[0] else 0
    finally:
        conn.close()


def set_ratio(oid, value):
    """记录作品图片宽高比（占位撑高用，防瀑布流跳动）。"""
    conn = _conn()
    try:
        conn.execute("UPDATE works SET ratio = ? WHERE id = ?", (value, oid))
        conn.commit()
    finally:
        conn.close()


def siblings(ids):
    """同 (标题, 作者) 组的其他成员 ID——堆叠组的组员不单独出卡，随代表一并标记。"""
    if not ids:
        return []
    conn = _conn()
    try:
        marks = ",".join("?" * len(ids))
        rows = conn.execute(
            f"SELECT title, artist FROM works WHERE id IN ({marks}) AND title != ''",
            ids).fetchall()
        keys = [(r[0], r[1]) for r in rows]
        if not keys:
            return []
        # 按 (title, artist) 匹配同组
        out = []
        for t, a in keys:
            if a:
                rows = conn.execute(
                    "SELECT id FROM works WHERE title = ? AND artist = ? AND id NOT IN (" + marks + ")",
                    [t, a] + ids).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id FROM works WHERE title = ? AND id NOT IN (" + marks + ")",
                    [t] + ids).fetchall()
            out.extend(r[0] for r in rows)
        return list(dict.fromkeys(out))
    finally:
        conn.close()


def all_ids():
    """库中全部作品 ID（拉新过滤用：已出现过的绝不再拉）。"""
    conn = _conn()
    try:
        return {r[0] for r in conn.execute("SELECT id FROM works")}
    finally:
        conn.close()


def count():
    conn = _conn()
    try:
        return conn.execute("SELECT COUNT(*) FROM works").fetchone()[0]
    finally:
        conn.close()
