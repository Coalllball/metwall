[**中文**](README.md) | [English](README.en.md)

# Met Wallpaper — 大都会艺术博物馆壁纸

从 Met Museum 公开 API 随机拉取高清艺术品，自动排版合成壁纸（含作品背景信息），并设置为桌面壁纸。

![九种排版风格](docs/screenshots/styles.jpg)

## 安装

**不需要 Python 环境** —— 从 [Releases](../../releases) 下载现成安装包：

| 平台 | 文件 | 首次运行 |
|---|---|---|
| Windows 10/11 | `MetWallpaper.exe` | 双击 → 浏览器自动打开管理面板 |
| macOS | `MetWallpaper-*-macos.dmg` | 打开 DMG，把 app 拖进 Applications。未签名版本首次打开需右键 → 打开，或执行 `xattr -dr com.apple.quarantine "/Applications/Met Wallpaper.app"` |

**从源码安装**（Python 3.9+）：

```
pip install -e ".[web]"     # [web] 装上 dashboard 需要的 FastAPI + uvicorn
```

依赖：Pillow + requests（`serve` 另需 FastAPI/uvicorn）。CI 在 Windows / macOS / Linux 三平台验证。

## 用法

```
wallpaper next [--style gallery|minimal|label|...|random] [--pool all|favorites]
               [--avoid-recent N] [--no-apply]
wallpaper browse [--count 5] [--style ...]     # 交互浏览：Enter预览/数字应用/f收藏
wallpaper set <objectID> [--style ...]         # 指定作品
wallpaper search <关键词>                       # 搜索后 set
wallpaper favorite [--add ID] [--remove ID]    # 收藏管理
wallpaper history [--limit 10]                 # 最近应用的壁纸
wallpaper monitors                             # 列出所有显示器 + 多屏诊断
wallpaper schedule --install --every 4         # 每4小时自动换
wallpaper schedule --remove | --status
wallpaper serve [--host 127.0.0.1] [--port 8000]  # 启动 web dashboard
wallpaper config [代理地址]                     # 查看/设置/清除配置（如代理）
```

- `--no-apply`：只生成不设置壁纸（预览用）
- `--pool favorites`：从收藏池里取，而非随机拉取
- `--avoid-recent N`：跳过最近 N 条历史里的作品（防重复）
- 数据目录（缓存/日志/成品/收藏/历史）：`%LOCALAPPDATA%\metwall`（Win）/ `~/.local/share/metwall`（Linux）/ `~/Library/Application Support/metwall`（macOS）
- 定时任务日志：`<数据目录>/cache/schedule.log`

## Web dashboard

`wallpaper serve` 启动浏览器管理面板（FastAPI 单体，默认 http://127.0.0.1:8000）：

![管理面板](docs/screenshots/dashboard.jpg)

- **瀑布流**网格（CSS columns，图片自然比例错落；滚动提前 1200px 触发加载、换一批去重）
- **搜索 / 艺术家浏览**：顶栏关键词搜索（回车）；搜索词命中艺术家名时只返回该艺术家的作品；详情页点艺术家名可看其全部作品
- **图片库（SQLite）驱动候选**（对标 Pinterest/小红书信息流）：
  - unseen 优先（新入库排最前）；seen 按**最久未看优先**（LRU 循环——看过一张图，要等其他图轮过一遍才重现）
  - **同部门打散**：最大组均匀切段 + 其他部门作分隔符（实测同部门最大连续 3 封顶）
  - **水位补货**：unseen 池 < 60 时后台自动拉新入库，新图持续供给
  - 前端渲染后批量上报 seen（last_seen 时间戳）
- **服务预热**：serve 启动时确保缓存池达 24 件（seed 包/历史缓存直接复用，零网络，仅不足时补缺口）
- 卡片悬停 ♥ 收藏，详情抽屉：大图懒加载 + 完整元数据 + 官网链接
- **一键换壁纸**：详情里选风格 → 设为壁纸 → 本机立即应用并记历史
- 左侧面板：收藏管理（含取消）、历史回看（时间 + 风格）
- **作品简介**：详情抽屉内中文/English 切换（Wikipedia 多语言摘要优先，Met 官网正文兜底；失败自动隐藏，不阻塞浏览）
- API：`/api/search`、`/api/candidates`、`/api/seen`、`/api/prefetch`、`/api/work/{id}`、`/api/favorites`、`/api/history`、`/api/styles`、`/api/notes/{id}?lang=zh|en`、`/api/apply/{id}?style=...`、`/media/img/{id}[_small].jpg`（按需下载+缓存）
- 图片路由按需下载，缩略图（`_small`）与高清大图分文件缓存，互不覆盖
- Met API 偶发限流：搜索自动重试 3 次，候选接口返回 503 带提示

### 种子包（随仓库/安装包分发，首用秒开）

```
wallpaper seed --count 24    # 预下载作品（meta + 小图）到 seed/ 目录
```

- seed/ 随仓库与发布包一起分发；首用用户启动 serve 时自动初始化进数据目录，瀑布流直接有图
- 已下载作品自动进入本地缓存池，candidates 优先返回（无需额外逻辑）

### 局域网共享

```
wallpaper serve --host 0.0.0.0
```

启动时自动打印局域网地址；Windows 防火墙可能拦截入站，按提示执行放行命令。

### 作品简介的代理配置

Wikipedia 域直连常被墙（Met 官网正文兜底则无需代理）。开了 Clash 等代理后：

```
wallpaper config http://127.0.0.1:7897   # 设置代理（启用 Wikipedia 简介）
wallpaper config                          # 查看
wallpaper config ""                       # 清除
```

## 风格一览

![主图](docs/screenshots/hero.jpg)

| 风格 | 形态 |
|---|---|
| `gallery` | 全幅铺底 + 左下角信息卡（标题/艺术家/部门/年代·材质）+ 品牌角标 |
| `minimal` | 整幅图为主，底部斜体细字 + 部门 |
| `label` | 展览说明牌：左图右字，米白纸色，竖排信息 |
| `editorial` | 杂志封面：上图下深色面板，大标题居中 + 刊头 |
| `mono` | 黑白摄影：去色 + 细线框 + 底部一行 |
| `poster` | 复古海报：米白底 + 粗边框 + 大号衬线标题 |
| `archive` | 档案卡：等宽字体标签/值对齐，馆藏编号 |
| `pedestal` | 基座：作品完整不裁剪、居中置于深色基座，上标题下信息（竖幅友好） |
| `column` | 侧栏：作品完整靠左，右侧深色信息栏（宽屏友好） |

新增风格 = 在 `render.py` 用 `@register("名字")` 注册一个函数：

```python
@register("my-style")
def render_my_style(img, info, size):
    """img: PIL.Image — info: Met 元数据 dict — size: (w, h)，返回 PIL.Image。"""
```

离线预览全部风格（用仓库自带 seed 素材，不联网、不动你的壁纸）：

```
python tools/preview.py --size 2560x1440            # 输出到 preview/
python tools/preview.py --style pedestal --size 1080x1920
```

## 平台支持状态

| 平台 | 出图 | 设为壁纸 | 定时轮换 |
|---|---|---|---|
| Windows 10/11 | ✅ 已实测 | ✅ 已实测（SPI；每屏独立用 `IDesktopWallpaper`） | ✅ 已实测（schtasks） |
| macOS | ✅ CI 实测 | ⚠️ **尚未在真机确认**（osascript） | ⚠️ 未确认（LaunchAgent） |
| Linux | ✅ CI 实测 | ⚠️ 未确认（gsettings / plasma-apply / feh） | ⚠️ 未确认（crontab） |

出图在三平台每次提交都由 CI 验证。macOS/Linux 的**设壁纸**已实现但未经证实——不生效时跑
`python tools/doctor.py --apply`，它会打印卡在哪一步。新增平台 = 在 `platforms/` 实现
`WallpaperSetter` 和 `Scheduler` 两个接口。

## 字体

渲染器自带字体，不用系统字体。原因：Georgia 与 Courier New 是**微软授权字体，不可随包分发**；Linux 完全
没有这两个字体；macOS 把它们放在 `/System/Library/Fonts/Supplemental`——而 Pillow 不搜索该目录。三条路
都走不通，非 Windows 平台上合成会直接抛 `OSError: cannot open resource`。

| 内置 | 替代 | 授权 |
|---|---|---|
| [Gelasio](https://fonts.google.com/specimen/Gelasio) | Georgia | SIL OFL 1.1 |
| [Cousine](https://fonts.google.com/specimen/Cousine) | Courier New | SIL OFL 1.1 |

两者都与原字体**公制兼容**——字符宽度、换行点、行高完全一致，因此排版零变化。跑
`python tools/fetch_fonts.py` 可重新下载并打印逐串宽度对比，任何一项有偏差它会直接报错退出。

## 开发

```
pip install -e ".[web,dev]"
pytest tests/ -v                # 离线：用 seed 素材渲染全部风格，不联网
python tools/doctor.py          # 环境 + 平台能力体检
python tools/doctor.py --apply  # 并真实尝试设置一次壁纸
python tools/preview.py         # 全部风格出图到 preview/
bash platforms/tools/build.sh   # 编译 multiwallpaper.exe（每屏独立壁纸，Windows）
```

CI 每次提交在 Windows / macOS / Linux 上跑渲染测试；另有一个 job 在真实 macOS runner 上尝试换壁纸并把结果
写进 job summary——macOS 支持状态在那里追踪，而不是靠假设。

## 架构

```
wallpaper.py   CLI 入口（next/browse/set/search/favorite/history/monitors/schedule/serve/config/seed）
met.py         Met API 客户端 + 本地缓存（小图/大图分文件）
render.py      排版引擎：风格注册表（@register 加新风格）
store.py       收藏/历史存储（纯数据层，web 后端可直接复用）
notes.py       作品简介：Wikipedia 摘要 + Met 官网正文兜底（支持代理）
library.py     本地图片库（SQLite）：seen/unseen 与最近曝光时间
server/        Web dashboard（FastAPI 单体）
  app.py         API + 图片按需下载路由 + 静态页挂载
  static/        前端（原生 JS，零依赖）
platforms/     平台适配层：壁纸设置 + 屏幕尺寸 + 定时调度 + 数据目录
  base.py       抽象接口 + user_data_dir()
  windows.py    SPI 设壁纸 + schtasks（已实测）
  macos.py      osascript + LaunchAgent（未确认）
  linux.py      gsettings/plasma-apply/feh + crontab（未确认）
  tools/        multiwallpaper.cs —— 每屏独立壁纸（IDesktopWallpaper COM）
assets/fonts/  内置开源字体（见上文「字体」）
seed/          预取作品，保证首次打开面板就有图
tools/         fetch_fonts.py · preview.py · doctor.py
packaging/     PyInstaller 入口（单文件 exe / .app）
```

## 定时任务存储位置

| 平台 | 位置 |
|---|---|
| Windows | `C:\Windows\System32\Tasks\MetWallpaper`（schtasks 管理） |
| Linux | 用户 crontab（`crontab -l`） |
| macOS | `~/Library/LaunchAgents/com.oldspirit.metwallpaper.plist` |

## 已知坑

- `schtasks /TR` 的 `cmd /c` 包装必须**最外层再包一对引号**（`cmd /c ""path" args > "log""`），且重定向日志目录必须预先存在，否则任务 Last Result=1
- 包名不能叫 `platform`（与 stdlib 冲突），用 `platforms/`
- Met 的 title/medium 等字段存在内嵌换行（`\r\n`）；Pillow 的 `textlength()` 对多行文本抛
  `ValueError: can't measure length of multiline text`，会让整张壁纸渲染失败。渲染入口统一清洗字段
  （`render.sanitize_info`）
- PyInstaller 打包必须加 `--paths .`，否则找不到顶层模块，冻结后的 exe 报
  `ModuleNotFoundError: No module named 'wallpaper'`

## 素材来源

作品来自 [The Met Open Access](https://www.metmuseum.org/about-the-met/policies-and-documents/open-access)（CC0）。

## 许可

代码 [MIT](LICENSE)。内置字体为 SIL OFL 1.1，见 `assets/fonts/*-OFL.txt`。
