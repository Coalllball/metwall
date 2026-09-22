#!/usr/bin/env bash
# 编译 multiwallpaper.exe —— 每显示器独立壁纸（IDesktopWallpaper COM）。
#
# 为什么需要单独编译：*.exe 不进版本库（构建产物），但缺了它 Windows 上
# "每屏独立壁纸"会静默降级成"各屏同一张"。发布流程会把它一起打包。
#
# 用法：bash platforms/tools/build.sh
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# csc 是原生程序，不认 MSYS 的 /c/... 路径 → 转成 C:/... 形式
here_win="$(cygpath -m "$here" 2>/dev/null || echo "$here")"
src="$here_win/multiwallpaper.cs"
out="$here_win/multiwallpaper.exe"

# .NET Framework 自带的 C# 编译器（Windows 无需额外 SDK）
csc=""
for cand in "C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe" \
            "C:/Windows/Microsoft.NET/Framework/v4.0.30319/csc.exe"; do
  [ -f "$cand" ] && csc="$cand" && break
done

if [ -z "$csc" ]; then
  # 退路：dotnet SDK
  if command -v dotnet >/dev/null 2>&1; then
    echo "未找到 csc.exe，改用 dotnet ..."
    cd "$here"
    dotnet new console -o _build --force >/dev/null
    cp "$src" _build/Program.cs
    dotnet publish _build -c Release -o _out >/dev/null
    cp "_out/$(basename "$(ls _out/*.dll | head -1)" .dll).exe" "$out" 2>/dev/null || true
    rm -rf _build _out
    [ -f "$out" ] && { echo "已生成: $out"; exit 0; }
  fi
  echo "错误：找不到 C# 编译器（需要 .NET Framework 或 dotnet SDK）" >&2
  exit 1
fi

# 用 '-' 前缀而非 '/'：MSYS 会把 /nologo 之类的参数当路径处理；
# 且 cd 进目录后只用相对文件名，避免原生编译器收到被 MSYS 改写的路径
cd "$here"
"$csc" -nologo -target:exe -out:multiwallpaper.exe multiwallpaper.cs
echo "已生成: $out"
