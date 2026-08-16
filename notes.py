"""作品背景简介：Wikipedia 多语言摘要（首选）+ Met 官网 JSON-LD（兜底）。

网络现实：Wikipedia 域在部分网络直连被墙，需代理（config.json 配置）；
Met 官网偶发 429 限流。两级源都失败时返回 None，前端隐藏简介区，不阻塞浏览。
"""
import json
import os
import re

import requests

from platforms.base import user_data_dir

NOTES_DIR = os.path.join(user_data_dir(), "metwall", "notes")
CONFIG = os.path.join(user_data_dir(), "metwall", "config.json")
# Met 官网对非浏览器 UA 敏感（429），notes 用浏览器 UA
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}


# ── 配置 ────────────────────────────────────────────────────
def load_config():
    try:
        with open(CONFIG, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_config(cfg):
    os.makedirs(os.path.dirname(CONFIG), exist_ok=True)
    with open(CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)


def get_proxy():
    return load_config().get("proxy") or ""


def set_proxy(url):
    cfg = load_config()
    cfg["proxy"] = url
    save_config(cfg)


def _session():
    s = requests.Session()
    s.headers.update(UA)
    proxy = get_proxy()
    if proxy:
        s.proxies = {"http": proxy, "https": proxy}
    return s


# ── Wikipedia（首选）────────────────────────────────────────
def _wiki_search(session, lang, query, limit=3):
    url = f"https://{lang}.wikipedia.org/w/api.php"
    params = {"action": "query", "list": "search", "srsearch": query,
              "srlimit": limit, "format": "json"}
    r = session.get(url, params=params, timeout=15)
    r.raise_for_status()
    return [h["title"] for h in r.json().get("query", {}).get("search", [])]


def _wiki_summary(session, lang, title):
    from urllib.parse import quote
    url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{quote(title.replace(' ', '_'))}"
    r = session.get(url, timeout=15)
    if r.status_code != 200:
        return None
    d = r.json()
    extract = (d.get("extract") or "").strip()
    if not extract:
        return None
    return {
        "title": d.get("title", ""),
        "extract": extract,
        "url": d.get("content_urls", {}).get("desktop", {}).get("page", ""),
    }


def _notes_wikipedia(session, info, lang):
    query = f'"{info.get("title", "")}" {info.get("artistDisplayName", "")}'
    try:
        for title in _wiki_search(session, lang, query):
            note = _wiki_summary(session, lang, title)
            if note:
                return note
    except requests.RequestException:
        pass
    return None


# ── Met 官网正文提取（兜底，限流时不可用）──────────────────
# 页面为 SSR 渲染，介绍文字在 data-testid="read-more-content" 容器内
_MET_RE = re.compile(r'data-testid="read-more-content"><div>(.*?)</div></div>', re.S)


def _clean_html(text):
    from html import unescape
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return unescape(text).strip()


def _notes_met(session, info, lang):
    url = f"https://www.metmuseum.org/{'zh' if lang == 'zh' else 'en'}/art/collection/search/{info['objectID']}"
    try:
        r = session.get(url, timeout=20,
                        headers={"Accept-Language": "zh-CN,zh;q=0.9" if lang == "zh" else "en-US,en;q=0.9"})
        if r.status_code != 200:
            return None
        m = _MET_RE.search(r.text)
        if not m:
            return None
        text = _clean_html(m.group(1))
        if not text:
            return None
        return {"title": info.get("title", ""), "extract": text, "url": url, "source": "met"}
    except requests.RequestException:
        return None


# ── 入口 ────────────────────────────────────────────────────
def get_notes(object_id, lang="zh", info=None):
    """返回 {title, extract, url, source?} 或 None。结果缓存到磁盘。"""
    import met  # 延迟导入避免循环
    os.makedirs(NOTES_DIR, exist_ok=True)
    p = os.path.join(NOTES_DIR, f"{object_id}.json")
    cache = {}
    if os.path.exists(p):
        try:
            cache = json.load(open(p, encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            cache = {}
    if lang in cache:
        return cache[lang] or None

    info = info or met.get_object(object_id)
    note = None
    if get_proxy():  # 有代理才值得试 Wikipedia（直连基本被墙）
        note = _notes_wikipedia(_session(), info, lang)
    if not note:
        note = _notes_met(_session(), info, lang)

    # 只缓存成功结果——失败不缓存，下次请求会重试（源站可能恢复）
    if note:
        cache[lang] = note
        try:
            with open(p, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=1)
        except OSError:
            pass
    return note
