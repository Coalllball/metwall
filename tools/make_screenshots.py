"""生成 README 截图：主图 + 9 种风格总览。

用 Met 公版（CC0）作品全分辨率渲染，输出到 docs/screenshots/。
"""
import json
import os
import subprocess
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import render  # noqa: E402
from platforms.base import user_data_dir  # noqa: E402

OBJECT_ID = 436535  # Van Gogh, Wheat Field with Cypresses（公版）
OUT = "docs/screenshots"
CACHE = os.path.join(user_data_dir(), "metwall", "_shot")
W, H = 1920, 1080

os.makedirs(OUT, exist_ok=True)
os.makedirs(CACHE, exist_ok=True)

meta_path = os.path.join(CACHE, f"{OBJECT_ID}.json")
img_path = os.path.join(CACHE, f"{OBJECT_ID}.jpg")

if not os.path.exists(meta_path):
    print(f"拉取元数据 {OBJECT_ID} ...")
    raw = subprocess.run(["curl", "-s", "--max-time", "60",
                          f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{OBJECT_ID}"],
                         capture_output=True, text=True).stdout
    open(meta_path, "w", encoding="utf-8").write(raw)

info = json.load(open(meta_path, encoding="utf-8"))
url = info["primaryImage"]

if not os.path.exists(img_path):
    print(f"下载原图 ...\n  {url[:100]}")
    subprocess.run(["curl", "-sL", "--max-time", "240", "-o", img_path, url], check=True)

src = Image.open(img_path)
print(f"作品: {info['title']} — {info['artistDisplayName']}")
print(f"原图: {src.size}  {os.path.getsize(img_path) // 1024} KB\n")

tiles = []
for style in sorted(render.STYLES):
    canvas, _ = render.render(info, style, (W, H), img_path)
    path = os.path.join(OUT, f"style-{style}.jpg")
    canvas.save(path, "JPEG", quality=92)
    print(f"  {style:10s} -> {path}  {os.path.getsize(path) // 1024} KB")
    tiles.append((style, canvas))

# 主图：gallery（信息最全，最能代表）
hero = dict(tiles)["gallery"]
hero.save(os.path.join(OUT, "hero.jpg"), "JPEG", quality=92)
print(f"\n主图: {OUT}/hero.jpg")

# 3×3 风格总览
TW, TH, GAP, PAD, LABEL = 620, 349, 12, 16, 26
cols, rows = 3, 3
Mw = PAD * 2 + cols * TW + (cols - 1) * GAP
Mh = PAD * 2 + rows * (TH + LABEL) + (rows - 1) * GAP
sheet = Image.new("RGB", (Mw, Mh), (22, 22, 24))
d = ImageDraw.Draw(sheet)
mono = render._font("mono", 17)

for i, (style, canvas) in enumerate(tiles):
    r, c = divmod(i, cols)
    x = PAD + c * (TW + GAP)
    y = PAD + r * (TH + LABEL + GAP)
    sheet.paste(canvas.resize((TW, TH), Image.LANCZOS), (x, y))
    d.text((x + 2, y + TH + 5), style, font=mono, fill=(190, 190, 200))

sheet_path = os.path.join(OUT, "styles.jpg")
sheet.save(sheet_path, "JPEG", quality=90)
print(f"总览: {sheet_path}  {sheet.size}  {os.path.getsize(sheet_path) // 1024} KB")
