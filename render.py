"""壁纸排版引擎：风格注册表架构。

新增风格 = 写一个函数接收 (img: PIL.Image, info: dict, size: (w,h)) 返回合成图，
再用 @register("风格名") 注册。CLI 用 --style 指定或 random 随机。
"""
import os
import random

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# ── 风格注册表 ──────────────────────────────────────────────
STYLES = {}


def register(name):
    def deco(fn):
        STYLES[name] = fn
        return fn
    return deco


def render(info, style, size, img_path):
    """入口：加载图 → 按风格合成。style='random' 时随机挑一个。"""
    if style == "random":
        style = random.choice(list(STYLES))
    img = Image.open(img_path).convert("RGB")
    fn = STYLES[style]
    return fn(img, sanitize_info(info), size), style


# ── 公共工具 ─────────────────────────────────────────────────
# 内置开源字体：Gelasio ≈ Georgia、Cousine ≈ Courier New（均为 SIL OFL，可自由分发）。
#
# 为什么不用系统字体：Georgia / Courier New 是微软授权字体，**不可随包分发**；
# 且 Linux 不自带、macOS 把它们放在 /System/Library/Fonts/Supplemental —— 而 Pillow
# 只搜 /Library/Fonts、/System/Library/Fonts、~/Library/Fonts，够不着该目录。
# 结果是 Linux 上 9 种风格全部抛 OSError、macOS 同样存疑。
#
# 为什么选这两个：与 Georgia / Courier New **公制兼容**，字符宽度/换行点/行距完全一致，
# 换字体后排版零变化（实测文本宽度逐项相同，见 tools/fetch_fonts.py 的自检）。
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "fonts")

FONT_FILES = {
    "serif": "Gelasio-Regular.ttf",
    "serif_bold": "Gelasio-Bold.ttf",
    "serif_italic": "Gelasio-Italic.ttf",
    "mono": "Cousine-Regular.ttf",
    "mono_bold": "Cousine-Bold.ttf",
}


def _font(name, size):
    return ImageFont.truetype(os.path.join(FONT_DIR, FONT_FILES[name]), size)


def cover(img, size):
    """等比缩放 + 居中裁剪填满目标尺寸。"""
    tw, th = size
    iw, ih = img.size
    scale = max(tw / iw, th / ih)
    nw, nh = int(iw * scale + 0.5), int(ih * scale + 0.5)
    img = img.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - tw) // 2, (nh - th) // 2
    return img.crop((x, y, x + tw, y + th))


def contain(img, box):
    """等比缩放完整放入 box（不裁剪）——竖幅友好风格的核心。

    返回 RGBA 画布（透明边），调用方 paste 到目标背景。
    """
    bw, bh = box
    iw, ih = img.size
    scale = min(bw / iw, bh / ih)
    nw, nh = max(int(iw * scale), 1), max(int(ih * scale), 1)
    art = img.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", (bw, bh), (0, 0, 0, 0))
    canvas.paste(art, ((bw - nw) // 2, (bh - nh) // 2))
    return canvas


def vgradient(size, start_alpha, end_alpha, color=(0, 0, 0)):
    """纵向线性渐变遮罩（自顶向下 start→end alpha）。"""
    w, h = size
    grad = Image.new("L", (1, h))
    for y in range(h):
        a = start_alpha + (end_alpha - start_alpha) * y / max(h - 1, 1)
        grad.putpixel((0, y), int(a))
    grad = grad.resize((w, h))
    layer = Image.new("RGB", size, color)
    layer.putalpha(grad)
    return layer


def wrap_text(draw, text, font, max_width):
    """按像素宽度折行。"""
    lines, cur = [], ""
    for ch in text:
        if draw.textlength(cur + ch, font=font) <= max_width:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def sanitize_info(info):
    """把元数据里的字符串统一压成单行。

    Met 的 title / medium / objectDate 等字段确实存在内嵌换行与多余空白
    （如标题里带 "\\n"），而 Pillow 的 textlength() 对多行文本直接抛
    ValueError: can't measure length of multiline text —— 会让整张壁纸渲染失败。
    在入口处清洗一次，所有风格一并受益。
    """
    return {k: (" ".join(v.split()) if isinstance(v, str) else v) for k, v in info.items()}


def text_with_shadow(draw, xy, text, font, fill, shadow=(0, 0, 0, 160), offset=2):
    x, y = xy
    draw.text((x + offset, y + offset), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)


# ── 画廊风（默认）───────────────────────────────────────────
@register("gallery")
def render_gallery(img, info, size):
    W, H = size
    canvas = cover(img, size)

    # 底部渐变遮罩：提高文字可读性
    grad = vgradient((W, H), start_alpha=0, end_alpha=205)
    canvas.paste(grad, (0, 0), grad)

    draw = ImageDraw.Draw(canvas)
    margin = int(W * 0.05)

    # 信息文本（画廊风：左下角，标题/艺术家/部门/年代+材质）
    title = info.get("title") or "Untitled"
    artist = (info.get("artistDisplayName") or "Unknown artist").upper()
    date = info.get("objectDate") or "n.d."
    medium = info.get("medium") or ""
    department = info.get("department") or ""
    meta_line = " · ".join(x for x in [date, medium] if x)

    # 标题字号：按宽度自适应
    max_w = W - 2 * margin
    title_size = int(H * 0.052)
    while title_size > 24:
        f = _font("serif_bold", title_size)
        if draw.textlength(title, font=f) <= max_w:
            break
        title_size -= 4

    f_title = _font("serif_bold", title_size)
    f_artist = _font("serif", max(int(H * 0.026), 18))
    f_dep = _font("serif_italic", max(int(H * 0.020), 13))
    f_meta = _font("serif", max(int(H * 0.020), 14))
    f_brand = _font("serif", max(int(H * 0.016), 12))

    y = H - margin
    white = (255, 255, 255, 255)

    # 品牌行（右下角）
    brand = "THE METROPOLITAN MUSEUM OF ART  ·  OPEN ACCESS"
    bw = draw.textlength(brand, font=f_brand)
    draw.text((W - margin - bw, margin), brand, font=f_brand, fill=(255, 255, 255, 170))

    # 底部信息块：标题 / 艺术家 / 部门 / 年代·材质
    y -= f_meta.size + 6
    draw.text((margin, y), meta_line, font=f_meta, fill=(255, 255, 255, 200))
    if department:
        y -= f_dep.size + 4
        draw.text((margin, y), department, font=f_dep, fill=(255, 255, 255, 175))
    y -= f_artist.size + 8
    draw.text((margin, y), artist, font=f_artist, fill=(255, 255, 255, 235))
    y -= f_title.size + 6
    text_with_shadow(draw, (margin, y), title, f_title, fill=white)

    # 左侧细装饰线（画廊展签感）
    draw.rectangle([margin, y + f_title.size + 14, margin + int(W * 0.06), y + f_title.size + 16], fill=(255, 255, 255, 220))

    return canvas


# ── 极简风：整幅图为主，底部一行细字 ─────────────────────────
@register("minimal")
def render_minimal(img, info, size):
    W, H = size
    canvas = cover(img, size)

    # 底部 8% 渐变
    gh = int(H * 0.12)
    grad = vgradient((W, gh), start_alpha=0, end_alpha=140)
    canvas.paste(grad, (0, H - gh), grad)

    draw = ImageDraw.Draw(canvas)
    title = info.get("title") or "Untitled"
    artist = info.get("artistDisplayName") or "Unknown artist"
    date = info.get("objectDate") or "n.d."
    department = info.get("department") or ""

    f = _font("serif_italic", max(int(H * 0.022), 16))
    line = f"{title}  —  {artist}  ·  {date}"
    w = draw.textlength(line, font=f)
    x = max((W - w) / 2, 20)
    base_y = H - gh + (gh - f.size) / 2 - 2
    draw.text((x, base_y), line, font=f, fill=(255, 255, 255, 225))

    if department:
        f_dep = _font("serif_italic", max(int(H * 0.015), 11))
        dw = draw.textlength(department, font=f_dep)
        draw.text(((W - dw) / 2, base_y + f.size + 4), department, font=f_dep, fill=(255, 255, 255, 165))
    return canvas


# ── 展览说明牌风：图居中留白 + 右侧信息竖排 ──────────────────
@register("label")
def render_label(img, info, size):
    W, H = size
    # 右 1/3 作信息区，左侧放图
    info_w = int(W * 0.30)
    art_w = W - info_w

    # 图片 cover 到左区
    art = cover(img, (art_w, H))
    canvas = Image.new("RGB", size, (242, 240, 236))  # 米白纸色
    canvas.paste(art, (0, 0))
    draw = ImageDraw.Draw(canvas)

    pad = int(info_w * 0.12)
    x = art_w + pad
    max_w = info_w - 2 * pad

    dark = (40, 40, 40)

    # 标题
    title = info.get("title") or "Untitled"
    f_title = _font("serif_bold", max(int(H * 0.034), 20))
    lines = wrap_text(draw, title, f_title, max_w)
    y = int(H * 0.10)
    for ln in lines[:4]:
        draw.text((x, y), ln, font=f_title, fill=dark)
        y += int(f_title.size * 1.35)

    # 艺术家
    artist = (info.get("artistDisplayName") or "Unknown artist").upper()
    f_artist = _font("serif", max(int(H * 0.020), 14))
    y += int(H * 0.02)
    draw.text((x, y), artist, font=f_artist, fill=(90, 90, 90))
    y += f_artist.size * 2

    # 年代 / 部门 / 材质 / 文化 / 尺寸
    f_meta = _font("serif", max(int(H * 0.018), 13))
    for seg in [info.get("objectDate"), info.get("department"), info.get("medium"),
                info.get("culture"), info.get("dimensions")]:
        if seg:
            for ln in wrap_text(draw, str(seg), f_meta, max_w)[:3]:
                draw.text((x, y), ln, font=f_meta, fill=(120, 120, 120))
                y += int(f_meta.size * 1.4)

    # 顶部细线 + 展签头
    draw.rectangle([x, int(H * 0.07), x + int(info_w * 0.25), int(H * 0.07) + 2], fill=(180, 150, 100))
    f_tag = _font("serif", max(int(H * 0.015), 11))
    draw.text((x, int(H * 0.07) + 8), "THE MET · EXHIBITION LABEL", font=f_tag, fill=(160, 140, 110))

    return canvas


# ── 杂志封面风：上图下色块，大标题居中 ──────────────────────
@register("editorial")
def render_editorial(img, info, size):
    W, H = size
    art_h = int(H * 0.66)
    art = cover(img, (W, art_h))
    canvas = Image.new("RGB", size, (21, 21, 24))
    canvas.paste(art, (0, 0))
    draw = ImageDraw.Draw(canvas)

    # 顶部刊头
    f_head = _font("serif", max(int(H * 0.018), 12))
    head = "THE METROPOLITAN MUSEUM OF ART"
    draw.text(((W - draw.textlength(head, font=f_head)) / 2, int(H * 0.022)),
              head, font=f_head, fill=(255, 255, 255, 200))

    title = info.get("title") or "Untitled"
    artist = (info.get("artistDisplayName") or "Unknown artist").upper()
    date = info.get("objectDate") or "n.d."

    # 大标题（自适应宽度，从底部向上排）
    title_size = int(H * 0.055)
    max_w = W * 0.9
    f_title = _font("serif_bold", title_size)
    while f_title.size > 30 and draw.textlength(title, font=f_title) > max_w:
        title_size -= 3
        f_title = _font("serif_bold", title_size)
    lines = wrap_text(draw, title, f_title, max_w)
    y = H - int(H * 0.055)
    for ln in reversed(lines):
        y -= f_title.size * 1.28
        draw.text(((W - draw.textlength(ln, font=f_title)) / 2, y), ln, font=f_title, fill=(240, 238, 232))

    # 艺术家 · 年代（标题上方）
    f_art = _font("serif", max(int(H * 0.022), 14))
    line = f"{artist}  ·  {date}"
    y -= f_art.size * 2.0
    draw.text(((W - draw.textlength(line, font=f_art)) / 2, y), line, font=f_art, fill=(198, 188, 172))

    # 分隔线
    draw.rectangle([W * 0.08, y - int(H * 0.014), W * 0.92, y - int(H * 0.014) + 1], fill=(110, 100, 85))

    return canvas


# ── 黑白摄影风：去色 + 细线框 + 底部一行 ────────────────────
@register("mono")
def render_mono(img, info, size):
    from PIL import ImageOps
    W, H = size
    canvas = ImageOps.grayscale(cover(img, size)).convert("RGB")
    draw = ImageDraw.Draw(canvas)

    # 细白线框
    m = int(W * 0.014)
    draw.rectangle([m, m, W - m, H - m], outline=(255, 255, 255, 150), width=1)

    # 底部一行斜体
    title = info.get("title") or "Untitled"
    artist = info.get("artistDisplayName") or "Unknown artist"
    date = info.get("objectDate") or "n.d."
    line = f"{title}  —  {artist}  ·  {date}"
    f = _font("serif_italic", max(int(H * 0.020), 14))
    w = draw.textlength(line, font=f)
    text_with_shadow(draw, (max((W - w) / 2, m + 12), H - int(H * 0.045)),
                     line, f, fill=(255, 255, 255, 230), shadow=(0, 0, 0, 140))
    return canvas


# ── 复古海报风：米白底 + 粗边框 + 大号衬线标题 ──────────────
@register("poster")
def render_poster(img, info, size):
    W, H = size
    bg = (240, 234, 224)
    ink = (43, 42, 38)
    canvas = Image.new("RGB", size, bg)
    draw = ImageDraw.Draw(canvas)

    # 标题（图上方，自适应折行）
    title = info.get("title") or "Untitled"
    f_title = _font("serif_bold", max(int(H * 0.045), 26))
    while f_title.size > 22 and draw.textlength(title, font=f_title) > W * 0.88:
        f_title = _font("serif_bold", f_title.size - 3)
    lines = wrap_text(draw, title, f_title, int(W * 0.88))
    y = int(H * 0.028)
    for ln in lines:
        draw.text(((W - draw.textlength(ln, font=f_title)) / 2, y), ln, font=f_title, fill=ink)
        y += int(f_title.size * 1.28)

    # 图片 + 粗边框
    art_w, art_h = int(W * 0.92), int(H * 0.58)
    art = cover(img, (art_w, art_h))
    ax, ay = (W - art_w) // 2, y + int(H * 0.012)
    canvas.paste(art, (ax, ay))
    bw = max(int(W * 0.007), 4)
    draw.rectangle([ax - bw, ay - bw, ax + art_w + bw, ay + art_h + bw], outline=ink, width=bw)

    # 图下方：红棕装饰线 + 艺术家 · 年代
    artist = (info.get("artistDisplayName") or "Unknown artist").upper()
    date = info.get("objectDate") or ""
    f_sub = _font("serif", max(int(H * 0.02), 13))
    sub = " · ".join(x for x in [artist, date] if x)
    draw.rectangle([ax, ay + art_h + int(H * 0.02), ax + art_w, ay + art_h + int(H * 0.02) + 2],
                   fill=(152, 92, 70))
    w = draw.textlength(sub, font=f_sub)
    draw.text(((W - w) / 2, ay + art_h + int(H * 0.032)), sub, font=f_sub, fill=(90, 80, 70))

    # 底部品牌
    f_btm = _font("serif", max(int(H * 0.015), 10))
    brand = "THE METROPOLITAN MUSEUM OF ART  ·  OPEN ACCESS"
    w = draw.textlength(brand, font=f_btm)
    draw.text(((W - w) / 2, H - int(H * 0.032)), brand, font=f_btm, fill=(150, 135, 115))

    return canvas


# ── 档案卡风：图 + 底部档案卡（等宽字体）────────────────────
@register("archive")
def render_archive(img, info, size):
    W, H = size
    art_h = int(H * 0.70)
    art = cover(img, (W, art_h))
    canvas = Image.new("RGB", size, (244, 240, 232))
    canvas.paste(art, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([0, art_h, W, art_h + 2], fill=(120, 110, 95))

    f_tag = _font("mono", max(int(H * 0.02), 13))
    f_val = _font("mono_bold", max(int(H * 0.022), 14))
    pad = int(W * 0.06)
    x = pad
    # 标签列宽按实际渲染宽度动态计算（等宽字体，>8 对齐后所有标签同宽）
    # 坑：固定像素宽在字号随屏幕缩放时会与标签文字重叠
    label_w = int(draw.textlength("ACC. NO.  ", font=f_tag)) + int(f_tag.size * 0.5)
    max_val_w = W - 2 * pad - label_w
    y = art_h + int(H * 0.03)
    line_h = int(f_val.size * 1.75)   # 值行距（留足空隙，防重叠）
    block_gap = int(f_tag.size * 0.6)  # 标签块间距

    rows = [
        ("TITLE", info.get("title") or "Untitled"),
        ("ARTIST", info.get("artistDisplayName") or "Unknown artist"),
        ("DATE", info.get("objectDate") or "n.d."),
        ("DEPT", info.get("department") or ""),
        ("ACC. NO.", info.get("accessionNumber") or ""),
    ]
    for k, v in rows:
        if not v:
            continue
        draw.text((x, y), f"{k:>8}  ", font=f_tag, fill=(152, 92, 70))
        lines = wrap_text(draw, str(v), f_val, max_val_w)[:2]
        if len(wrap_text(draw, str(v), f_val, max_val_w)) > 2:
            lines[-1] = lines[-1][:-1] + "…"
        for i, ln in enumerate(lines):
            draw.text((x + label_w, y + i * line_h), ln, font=f_val, fill=(40, 40, 38))
        y += len(lines) * line_h + block_gap

    f_small = _font("mono", max(int(H * 0.014), 10))
    draw.text((x, H - int(H * 0.028)), "MET COLLECTION  —  OPEN ACCESS", font=f_small, fill=(150, 135, 115))

    return canvas


# ── 基座风：竖图完整居中，上下留白放信息（竖幅友好）─────────
@register("pedestal")
def render_pedestal(img, info, size):
    """基座风：艺术品完整显示（不裁剪），像陈列在深色基座上。

    顶部标题、底部艺术家·年代·部门——对竖幅作品友好（cover 风格会裁掉竖图上下）。
    """
    W, H = size
    canvas = Image.new("RGB", size, (17, 17, 19))
    draw = ImageDraw.Draw(canvas)

    # 竖图 contain 到 60% 高度（不裁剪，完整全貌）
    # 信息区放图正下方（0.7H 内安全区）——底部 0.9H+ 会被 Windows 任务栏遮挡
    art_h = int(H * 0.60)
    art = contain(img, (int(W * 0.92), art_h))
    ax, ay = (W - art.width) // 2, int(H * 0.05)
    canvas.paste(art, (ax, ay), art)
    art_bottom = ay + art.height

    # 顶部标题（小，居中）
    title = info.get("title") or "Untitled"
    f_t = _font("serif_bold", max(int(H * 0.026), 15))
    tsize = f_t.size
    while tsize > 13 and draw.textlength(title, font=f_t) > W * 0.9:
        tsize -= 2
        f_t = _font("serif_bold", tsize)
    tw = draw.textlength(title, font=f_t)
    draw.text(((W - tw) / 2, int(H * 0.028)), title, font=f_t, fill=(240, 238, 232))

    # 装饰细线（图下方）
    line_y = art_bottom + int(H * 0.032)
    draw.rectangle([W * 0.38, line_y, W * 0.62, line_y + 2], fill=(120, 110, 95))

    # 底部信息（图正下方，艺术家 · 年代 · 部门）
    artist = info.get("artistDisplayName") or "Unknown artist"
    date = info.get("objectDate") or ""
    dept = info.get("department") or ""
    line = "  ·  ".join(x for x in [artist, date, dept] if x)
    f_s = _font("serif", max(int(H * 0.021), 14))
    sw = draw.textlength(line, font=f_s)
    while f_s.size > 12 and sw > W * 0.92:
        f_s = _font("serif", f_s.size - 2)
        sw = draw.textlength(line, font=f_s)
    draw.text(((W - sw) / 2, line_y + int(H * 0.016)), line, font=f_s, fill=(205, 197, 182))
    return canvas


# ── 侧栏风：竖图完整靠左，右侧信息栏（宽屏友好）─────────────
@register("column")
def render_column(img, info, size):
    """侧栏风：竖图完整靠左展示，右侧深色信息栏。

    标题大字 + 艺术家/年代/部门/材质竖排——宽屏壁纸展示竖幅作品时
    利用两侧空间，全貌不裁切。
    """
    W, H = size
    canvas = Image.new("RGB", size, (18, 18, 20))
    draw = ImageDraw.Draw(canvas)

    # 竖图 contain 到 94% 高度，靠左
    art_h = int(H * 0.94)
    art = contain(img, (int(W * 0.55), art_h))
    ax, ay = int(W * 0.03), (H - art.height) // 2
    canvas.paste(art, (ax, ay), art)

    # 右侧信息栏
    x = ax + art.width + int(W * 0.045)
    max_w = W - x - int(W * 0.05)
    y = int(H * 0.14)

    # 部门小标签（红棕）
    dept = info.get("department") or ""
    if dept:
        f_tag = _font("serif", max(int(H * 0.018), 12))
        draw.text((x, y), dept.upper(), font=f_tag, fill=(180, 130, 90))
        y += int(f_tag.size * 2.0)

    # 标题大字（换行）
    title = info.get("title") or "Untitled"
    f_title = _font("serif_bold", max(int(H * 0.045), 26))
    tsize = f_title.size
    while tsize > 18:
        if all(draw.textlength(ln, font=f_title) <= max_w for ln in wrap_text(draw, title, f_title, max_w)[:3]):
            break
        tsize -= 2
        f_title = _font("serif_bold", tsize)
    for ln in wrap_text(draw, title, f_title, max_w)[:3]:
        draw.text((x, y), ln, font=f_title, fill=(240, 238, 232))
        y += int(f_title.size * 1.3)
    y += int(H * 0.02)

    # 分隔线
    draw.rectangle([x, y, x + int(max_w * 0.3), y + 2], fill=(120, 110, 95))
    y += int(H * 0.035)

    # 艺术家 / 年代 / 材质 竖排
    f_s = _font("serif", max(int(H * 0.021), 14))
    for label, val in [("ARTIST", info.get("artistDisplayName") or "Unknown artist"),
                       ("DATE", info.get("objectDate") or "n.d."),
                       ("MEDIUM", info.get("medium") or "")]:
        if not val:
            continue
        draw.text((x, y), label, font=_font("serif", max(int(H * 0.015), 11)),
                  fill=(150, 135, 115))
        y += int(f_s.size * 1.15)
        lines = wrap_text(draw, str(val), f_s, max_w)[:2]
        for ln in lines:
            draw.text((x, y), ln, font=f_s, fill=(228, 224, 214))
            y += int(f_s.size * 1.5)
        y += int(H * 0.022)

    # 底部来源 + 品牌
    credit = info.get("creditLine") or ""
    f_c = _font("serif", max(int(H * 0.015), 11))
    yc = H - int(H * 0.09)
    if credit:
        for ln in wrap_text(draw, credit, f_c, max_w)[:2]:
            draw.text((x, yc), ln, font=f_c, fill=(120, 112, 100))
            yc += int(f_c.size * 1.4)
    draw.text((x, H - int(H * 0.04)), "MET  ·  OPEN ACCESS",
              font=_font("serif", max(int(H * 0.013), 10)), fill=(120, 112, 100))

    return canvas
