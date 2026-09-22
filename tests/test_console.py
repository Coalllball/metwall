"""回归：非 UTF-8 输出编码下不能崩。

Windows 上 Python 只有直接连控制台时才用 UTF-8（PEP 528）；输出一旦被管道或重定向
（`wallpaper next | tee log.txt`、CI 日志采集），就退回系统区域编码——英文 Windows 是
cp1252，print 中文直接抛 UnicodeEncodeError: 'charmap' codec can't encode characters，
整个命令失败。CI 的 windows-latest 上就是这样挂的。

这里把输出编码强制成 cp1252 来复现该环境，断言各入口仍能跑通。
"""
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.parametrize("name,args", [
    ("wallpaper", ["wallpaper.py", "--help"]),
    ("doctor", ["tools/doctor.py"]),
    ("preview", ["tools/preview.py"]),
])
def test_tools_survive_non_utf8_stdout(name, args, tmp_path):
    if name == "preview":
        args = args + ["--out", str(tmp_path)]

    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    r = subprocess.run([sys.executable] + args, cwd=ROOT, env=env,
                       capture_output=True, encoding="utf-8", errors="replace", timeout=600)

    assert r.returncode == 0, (
        f"{name} 在 cp1252 输出编码下失败（退出码 {r.returncode}）：\n{r.stderr[-2000:]}")
    assert "UnicodeEncodeError" not in (r.stdout + r.stderr)


def test_preview_actually_writes_images(tmp_path):
    """同一路径顺带验证出图：写不出文件的话上面那条也可能因为静默失败而"通过"。"""
    import glob
    r = subprocess.run([sys.executable, "tools/preview.py", "--out", str(tmp_path)],
                       cwd=ROOT, capture_output=True, encoding="utf-8",
                       errors="replace", timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    files = glob.glob(os.path.join(str(tmp_path), "*.jpg"))
    assert len(files) >= 9, f"只出了 {len(files)} 张图"
    assert all(os.path.getsize(f) > 10_000 for f in files), "有图片体积异常，可能是空图"
