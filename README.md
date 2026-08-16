# Met Wallpaper — 大都会艺术博物馆壁纸

从 Met Museum 公开 API 随机拉取高清艺术品，自动排版合成壁纸（含作品背景信息），并设置为桌面壁纸。

## 安装

```
pip install -e .        # 生成 wallpaper 命令（editable，改代码即时生效）
```

依赖：Python 3 + Pillow + requests（Windows 实测用 anaconda3）。

## 用法

```
wallpaper next [--style gallery|minimal|label|random] [--no-apply]
wallpaper browse [--count 5] [--style ...]     # 交互浏览：Enter预览/数字应用/f收藏
wallpaper set <objectID> [--style ...]         # 指定作品
wallpaper search <关键词>                       # 搜索后 set
wallpaper favorite [--add ID] [--remove ID]    # 收藏管理
wallpaper history [--limit 10]                 # 最近应用的壁纸
wallpaper schedule --install --every 4        # 每4小时自动换
wallpaper schedule --remove | --status
wallpaper serve [--host 127.0.0.1] [--port 8000]  # 启动 web dashboard
```

- `--no-apply`：只生成不设置壁纸（预览用）
- 数据目录（缓存/日志/成品/收藏/历史）：`%LOCALAPPDATA%\metwall`（Win）/ `~/.local/share/metwall`（Linux）/ `~/Library/Application Support/metwall`（macOS）
- 定时任务日志：`<数据目录>/cache/schedule.log`

## Web dashboard

`wallpaper serve` 启动浏览器管理面板（FastAPI 单体，默认 http://127.0.0.1:8000）：

- **瀑布流**网格（CSS columns，图片自然比例错落；滚动提前 1200px 触发加载、换一批去重）
- **搜索 / 部门筛选 / 艺术家浏览**：顶栏关键词搜索（回车）、部门下拉（Met 19 个部门）、详情页点艺术家名看其全部作品
- **图片库（SQLite）驱动候选**（对标 Pinterest/小红书信息流）：
  - unseen 优先（新入库排最前）；seen 按**最久未看优先**（LRU 循环——看过一张图，要等其他图轮过一遍才重现）
  - **同部门打散**：最大组均匀切段 + 其他部门作分隔符（实测同部门最大连续 3 封顶）
  - **水位补货**：unseen 池 < 60 时后台自动拉新入库，新图持续供给
  - 前端渲染后批量上报 seen（last_seen 时间戳）
- **服务预热**：serve 启动时确保缓存池达 24 件（seed 包/历史缓存直接复用，零网络，仅不足时补缺口）
- 卡片悬停 ♥ 收藏，详情抽屉：大图懒加载 + 完整元数据 + 官网链接
- **一键换壁纸**：详情里选风格（gallery/minimal/label/editorial/mono/poster/archive/random）→ 设为壁纸 → 本机立即应用并记历史
- 左侧面板：收藏管理（含取消）、历史回看（时间 + 风格）
- **作品简介**：详情抽屉内中文/English 切换（Wikipedia 多语言摘要优先，Met 官网正文兜底；失败自动隐藏，不阻塞浏览）
- API：`/api/candidates`、`/api/work/{id}`、`/api/favorites`、`/api/history`、`/api/styles`、`/api/notes/{id}?lang=zh|en`、`/api/apply/{id}?style=...`、`/media/img/{id}[_small].jpg`（按需下载+缓存）
- 图片路由按需下载，缩略图（`_small`）与高清大图分文件缓存，互不覆盖
- Met API 偶发限流：搜索自动重试 3 次，候选接口返回 503 带提示

### 种子包（发布预打包，首用用户秒开）

```
wallpaper seed --count 24    # 预下载 24 件（meta + 小图）到 seed/ 目录
```

- seed/ 目录随发布包分发；首用用户启动 serve 时自动初始化进数据目录，瀑布流直接有图
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

## 架构

```
wallpaper.py   CLI 入口（next/browse/set/search/favorite/history/schedule/serve）
met.py         Met API 客户端 + 本地缓存（小图/大图分文件）
render.py      排版引擎：风格注册表（@register 加新风格）
store.py       收藏/历史存储（纯数据层，web 后端可直接复用）
server/        Web dashboard（FastAPI 单体）
  app.py         API + 图片按需下载路由 + 静态页挂载
  static/        前端（原生 JS，零依赖）
platforms/     平台适配层：壁纸设置 + 屏幕尺寸 + 定时调度 + 数据目录 + 图片打开
  base.py       抽象接口 + user_data_dir()
  windows.py    SPI 设壁纸 + schtasks（已实测）
  linux.py      gsettings/plasma-apply/feh + crontab（未实测）
  macos.py      osascript + LaunchAgent（未实测）
```

新增平台 = 在 `platforms/` 实现 `WallpaperSetter` 和 `Scheduler` 两个接口。
新增风格 = 在 `render.py` 用 `@register("名字")` 注册一个函数。

### 风格一览

| 风格 | 形态 |
|---|---|
| `gallery` | 全幅铺底 + 左下角信息卡（标题/艺术家/部门/年代·材质）+ 品牌角标 |
| `minimal` | 整幅图为主，底部斜体细字 + 部门 |
| `label` | 展览说明牌：左图右字，米白纸色，竖排信息 |
| `editorial` | 杂志封面：上图下深色面板，大标题居中 + 刊头 |
| `mono` | 黑白摄影：去色 + 细线框 + 底部一行 |
| `poster` | 复古海报：米白底 + 粗边框 + 大号衬线标题 |
| `archive` | 档案卡：等宽字体（Courier）标签/值对齐，馆藏编号 |

**Web dashboard 预留**：`met.py`（取数）+ `store.py`（收藏/历史）是纯数据层，无 CLI 依赖——后续 web 后端直接 import 即可。

## 定时任务存储位置

| 平台 | 位置 |
|---|---|
| Windows | `C:\Windows\System32\Tasks\MetWallpaper`（schtasks 管理） |
| Linux | 用户 crontab（`crontab -l`） |
| macOS | `~/Library/LaunchAgents/com.oldspirit.metwallpaper.plist` |

## 已知坑

- `schtasks /TR` 的 `cmd /c` 包装必须**最外层再包一对引号**（`cmd /c ""path" args > "log""`），且重定向日志目录必须预先存在，否则任务 Last Result=1
- 包名不能叫 `platform`（与 stdlib 冲突），用 `platforms/`
- 分发给别人（无 Python 环境）时用 PyInstaller 打包单文件 exe
