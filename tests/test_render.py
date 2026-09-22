"""离线渲染测试：不联网，用 seed/ 素材验证全部风格都能出图。

这是跨平台支持的核心回归测试。换掉 Windows 专有字体之前，本文件在
Linux（实测）和 macOS（推断）上 9/9 全红，报 OSError: cannot open resource。
"""
import glob
import json
import os
import sys

import pytest
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import render  # noqa: E402

SEED_META = sorted(glob.glob(os.path.join(ROOT, "seed", "meta", "*.json")))
ALL_STYLES = sorted(render.STYLES)


@pytest.fixture(scope="module")
def sample():
    """seed 里的第一件作品（随仓库分发，零网络）。"""
    assert SEED_META, "seed/meta 为空——没有可用测试素材"
    info = json.load(open(SEED_META[0], encoding="utf-8"))
    img = os.path.join(ROOT, "seed", "img", f"{info['objectID']}_small.jpg")
    assert os.path.exists(img), f"缺少 seed 图片 {img}"
    return info, img


# ── 字体 ────────────────────────────────────────────────────
def test_font_dir_is_bundled():
    """字体必须来自包内，不能依赖系统字体目录（Windows 专有字体不可分发）。"""
    assert os.path.isdir(render.FONT_DIR), f"内置字体目录不存在: {render.FONT_DIR}"
    assert "Windows" not in render.FONT_DIR


@pytest.mark.parametrize("key", sorted(render.FONT_FILES))
def test_bundled_font_loads(key):
    path = os.path.join(render.FONT_DIR, render.FONT_FILES[key])
    assert os.path.exists(path), f"缺少字体文件 {render.FONT_FILES[key]}"
    font = render._font(key, 40)  # 加载失败即抛 OSError
    assert font.getlength("Met Wallpaper") > 0


def test_bundled_fonts_actually_draw():
    """字体能加载还不够——要确认真的能画出字形（空白字形说明字体损坏）。"""
    img = Image.new("RGB", (400, 80), "white")
    d = ImageDraw.Draw(img)
    for key in render.FONT_FILES:
        d.text((10, 20), "Met 1926", font=render._font(key, 32), fill="black")
    assert img.convert("L").getextrema()[0] < 200, "画不出任何字形"


# ── 渲染 ────────────────────────────────────────────────────
@pytest.mark.parametrize("style", ALL_STYLES)
def test_style_renders(style, sample):
    info, img = sample
    canvas, used = render.render(info, style, (1920, 1080), img)
    assert used == style
    assert canvas.size == (1920, 1080)
    lo, hi = canvas.convert("L").getextrema()
    assert hi - lo > 20, f"{style} 输出接近纯色，排版可能没画上去"


@pytest.mark.parametrize("size", [(1280, 720), (3840, 2160), (1080, 1920)])
def test_common_resolutions(size, sample):
    """常见桌面分辨率与竖屏都不能崩（pedestal/column 专为竖幅设计）。"""
    info, img = sample
    for style in ("gallery", "pedestal", "column"):
        canvas, _ = render.render(info, style, size, img)
        assert canvas.size == size


def test_random_style_resolves(sample):
    info, img = sample
    _, used = render.render(info, "random", (1280, 720), img)
    assert used in render.STYLES


def test_unknown_style_raises(sample):
    info, img = sample
    with pytest.raises(KeyError):
        render.render(info, "no-such-style", (1280, 720), img)


# ── 元数据清洗（回归：曾导致 wallpaper next 整条崩溃）────────────
def test_sanitize_info_collapses_whitespace():
    out = render.sanitize_info({"title": "A\nB", "objectID": 5,
                                "medium": "Etching  and\nengraving", "flags": ["x\ny"]})
    assert out["title"] == "A B"
    assert out["medium"] == "Etching and engraving"
    assert out["objectID"] == 5          # 非字符串原样保留
    assert out["flags"] == ["x\ny"]      # 不递归改动容器


def test_multiline_metadata_does_not_crash(sample):
    """Met 的 title/medium 字段确实存在内嵌换行；Pillow 的 textlength() 对多行
    文本抛 ValueError: can't measure length of multiline text，会让渲染整体失败。"""
    _, img = sample
    nasty = {
        "objectID": 726239,
        "title": "Targhe ed altri ornati\ndi varie e capricciose invenzioni",
        "artistDisplayName": "Hans Vredeman\nde Vries",
        "objectDate": "1773\n(circa)",
        "department": "Drawings\tand Prints",
        "medium": "Etching\nand engraving",
    }
    for style in ALL_STYLES:
        canvas, _ = render.render(nasty, style, (1920, 1080), img)
        assert canvas.size == (1920, 1080)
