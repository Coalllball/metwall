# Met Wallpaper — Art from the Met on your desktop

[中文](README.md) | **English**

Pulls random high-resolution artworks from The Met's public API, composes them into a wallpaper with the artwork's
background information laid out on the canvas, and applies it as your desktop wallpaper.

## Install

```
pip install -e .        # creates the `wallpaper` command (editable — code changes take effect immediately)
```

Dependencies: Python 3 + Pillow + requests (verified on Windows with anaconda3).

## Usage

```
wallpaper next [--style gallery|minimal|label|...|random] [--pool all|favorites]
               [--avoid-recent N] [--no-apply]
wallpaper browse [--count 5] [--style ...]     # interactive: Enter preview / number apply / f favorite
wallpaper set <objectID> [--style ...]         # a specific artwork
wallpaper search <query>                       # search, then set
wallpaper favorite [--add ID] [--remove ID]    # manage favorites
wallpaper history [--limit 10]                 # recently applied wallpapers
wallpaper monitors                             # list all displays + multi-monitor diagnostics
wallpaper schedule --install --every 4         # auto-rotate every 4 hours
wallpaper schedule --remove | --status
wallpaper serve [--host 127.0.0.1] [--port 8000]  # launch the web dashboard
wallpaper config [proxy_url]                   # view / set / clear config (e.g. proxy)
```

- `--no-apply`: compose only, don't touch the current wallpaper (for previewing)
- `--pool favorites`: draw from your favorites instead of a random pull
- `--avoid-recent N`: skip the artworks applied in the last N history entries (no repeats)
- Data directory (cache / logs / output / favorites / history): `%LOCALAPPDATA%\metwall` (Windows) ·
  `~/.local/share/metwall` (Linux) · `~/Library/Application Support/metwall` (macOS)
- Scheduled-task log: `<data dir>/cache/schedule.log`

## Web dashboard

`wallpaper serve` starts a browser-based management panel (single-process FastAPI app, default http://127.0.0.1:8000):

- **Masonry grid** (CSS columns — images keep their natural aspect ratio and stagger; infinite scroll triggers 1200px
  ahead of the fold, each new batch is de-duplicated)
- **Search / department filter / artist browsing**: keyword search in the top bar (Enter to submit), department
  dropdown (all 19 Met departments), click an artist name on a detail page to see all of their works
- **A SQLite image library drives the candidate feed** (modeled on Pinterest / Xiaohongshu feeds):
  - unseen first (newly ingested works rank at the top); seen works ordered by **longest-unseen-first** (an LRU cycle —
    after viewing one image it won't reappear until every other image has had a turn)
  - **department shuffling**: the largest department group is split into even segments and separated by other
    departments (measured: max 3 consecutive works from the same department)
  - **low-water restocking**: when the unseen pool drops below 60, a background job fetches more (continuous supply of
    new work)
  - the frontend reports `seen` in batches after render (with a `last_seen` timestamp)
- **Warm start**: `serve` tops the cache pool up to 24 works on boot (reusing the seed pack and existing cache with zero
  network calls; only the shortfall is fetched)
- Hover a card and hit ♥ to favorite; detail drawer: lazy-loaded full image + full metadata + link to the official page
- **One-click apply**: pick a style in the detail drawer (gallery / minimal / label / editorial / mono / poster /
  archive / random) → set as wallpaper → applied locally immediately and recorded in history
- Left panel: favorites management (including removal) and history browsing (time + style)
- **Artwork notes**: Chinese/English toggle inside the detail drawer (Wikipedia multilingual summary first, Met's own
  page text as fallback; hidden automatically on failure so browsing is never blocked)
- API: `/api/search`, `/api/candidates`, `/api/seen`, `/api/prefetch`, `/api/work/{id}`, `/api/favorites`,
  `/api/history`, `/api/styles`, `/api/notes/{id}?lang=zh|en`, `/api/apply/{id}?style=...`,
  `/media/img/{id}[_small].jpg` (downloaded and cached on demand)
- Image routes download on demand; thumbnails (`_small`) and full-resolution images are cached as separate files and
  never overwrite each other
- Met's API rate-limits occasionally: searches retry 3 times automatically, the candidates endpoint returns 503 with a
  message

### Seed pack (pre-bundled for releases, so first-run users see images instantly)

```
wallpaper seed --count 24    # pre-download 24 works (metadata + thumbnails) into seed/
```

- The `seed/` directory ships with the release; on first `serve` it is initialized into the data directory so the
  masonry grid has images right away
- Downloaded works automatically join the local cache pool and are returned first by the candidates endpoint (no extra
  logic needed)

### LAN sharing

```
wallpaper serve --host 0.0.0.0
```

The LAN address is printed on startup; Windows Firewall may block inbound traffic — run the suggested allow command.

### Proxy configuration for artwork notes

Wikipedia domains are often unreachable from mainland China on a direct connection (the Met page-text fallback needs no
proxy). With a proxy such as Clash running:

```
wallpaper config http://127.0.0.1:7897   # set proxy (enables Wikipedia notes)
wallpaper config                         # show current config
wallpaper config ""                      # clear
```

## Architecture

```
wallpaper.py   CLI entry point (next/browse/set/search/favorite/history/monitors/schedule/serve/config/seed)
met.py         Met API client + local cache (separate files for thumbnails and full images)
render.py      Layout engine: style registry (add a style with @register)
store.py       Favorites / history storage (pure data layer, reusable by the web backend as-is)
notes.py       Artwork notes: Wikipedia summaries + Met page-text fallback (proxy-aware)
library.py     Local image library (SQLite): seen/unseen and last-exposure tracking
server/        Web dashboard (single-process FastAPI app)
  app.py         API + on-demand image download routes + static page mounting
  static/        Frontend (vanilla JS, zero dependencies)
platforms/     Platform adapter layer: wallpaper setting + screen size + scheduling + data dir + image opening
  base.py        Abstract interfaces + user_data_dir()
  windows.py     Wallpaper via SPI + schtasks (verified)
  linux.py       gsettings/plasma-apply/feh + crontab (untested)
  macos.py       osascript + LaunchAgent (untested)
  tools/         multiwallpaper.cs — per-monitor wallpapers via the IDesktopWallpaper COM interface
```

New platform = implement the `WallpaperSetter` and `Scheduler` interfaces under `platforms/`.
New style = register a function in `render.py` with `@register("name")`.

### Styles

| Style | Appearance |
|---|---|
| `gallery` | Full-bleed image + info card in the lower-left (title / artist / department / date · medium) + brand corner mark |
| `minimal` | Image-dominant; a slim italic line and the department along the bottom |
| `label` | Exhibition label: image left, text right, cream paper tone, stacked information |
| `editorial` | Magazine cover: image on top, dark panel below, large centered title + masthead |
| `mono` | Black-and-white photography: desaturated + thin frame + a single footer line |
| `poster` | Vintage poster: cream background + heavy border + large serif title |
| `archive` | Archive card: monospace (Courier) label/value alignment, accession number |
| `pedestal` | Plinth: uncropped artwork centered on a dark base, title above, artist · date · department below (portrait-friendly) |
| `column` | Sidebar: uncropped artwork at left, dark information column at right (widescreen-friendly) |

**Reserved for the web dashboard**: `met.py` (data access) + `store.py` (favorites/history) are pure data layers with no
CLI dependency — a backend can import them directly.

## Scheduled task locations

| Platform | Location |
|---|---|
| Windows | `C:\Windows\System32\Tasks\MetWallpaper` (managed by schtasks) |
| Linux | User crontab (`crontab -l`) |
| macOS | `~/Library/LaunchAgents/com.oldspirit.metwallpaper.plist` |

## Known pitfalls

- `schtasks /TR` requires the `cmd /c` wrapper to be **wrapped in one more pair of outer quotes**
  (`cmd /c ""path" args > "log""`), and the log directory for the redirect must already exist — otherwise the task
  reports Last Result = 1
- The package must not be named `platform` (conflicts with the stdlib) — hence `platforms/`
- Distributing to someone without Python: build a single-file exe with PyInstaller
