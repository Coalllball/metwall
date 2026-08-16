// Met Wallpaper dashboard —— 原生 JS，零依赖
const grid = document.getElementById("grid");
const loading = document.getElementById("loading");
const end = document.getElementById("end");
const countEl = document.getElementById("count");

const seen = new Set();        // 已显示的作品 ID（翻页去重）
const favSet = new Set();      // 已收藏 ID
let busy = false;
let exhausted = false;

// ── 工具 ────────────────────────────────────────────────────
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

let toastTimer = null;
function toast(msg, isErr = false) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.className = "toast" + (isErr ? " err" : "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.add("hidden"), 3200);
}

async function api(path, opts = {}) {
  // 30 秒超时：慢请求（首次拉详情/限流）不至于无限挂起
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 30000);
  try {
    const r = await fetch(path, { ...opts, signal: ctrl.signal });
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `HTTP ${r.status}`);
    return data;
  } catch (e) {
    if (e.name === "AbortError") throw new Error("请求超时（30s），请重试");
    throw e;
  } finally {
    clearTimeout(timer);
  }
}

// ── 主题（Met 品牌双主题：默认跟随系统，手动切换记忆）──────
const themeBtn = document.getElementById("themeBtn");

function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  themeBtn.textContent = t === "dark" ? "☀" : "☾";
  try { localStorage.setItem("metwall-theme", t); } catch (e) {}
}

(function initTheme() {
  let t = null;
  try { t = localStorage.getItem("metwall-theme"); } catch (e) {}
  if (!t) t = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  applyTheme(t);
})();

themeBtn.addEventListener("click", () => {
  const cur = document.documentElement.dataset.theme === "dark" ? "dark" : "light";
  applyTheme(cur === "dark" ? "light" : "dark");
});

// ── 收藏状态 ────────────────────────────────────────────────
async function refreshFavCount() {
  try {
    const d = await api("/api/favorites");
    favSet.clear();
    d.items.forEach(c => favSet.add(c.id));
    document.getElementById("favCount").textContent = favSet.size;
  } catch (e) { console.error(e); }
}

async function toggleFav(id) {
  try {
    if (favSet.has(id)) {
      await api(`/api/favorites/${id}`, { method: "DELETE" });
      favSet.delete(id);
      toast("已取消收藏");
    } else {
      await api(`/api/favorites/${id}`, { method: "POST" });
      favSet.add(id);
      toast("♥ 已收藏");
    }
    document.getElementById("favCount").textContent = favSet.size;
    syncCardFavs();
    if (!panel.classList.contains("hidden")) renderPanel(panelTab);
  } catch (e) { toast("操作失败: " + e.message, true); }
}

// ── 候选加载 ────────────────────────────────────────────────
// 当前浏览模式：null=随机瀑布流 / {type:'search', q}
let mode = null;
const searchBox = document.getElementById("searchBox");

async function loadBatch() {
  if (busy || exhausted) return;
  busy = true;
  loading.classList.remove("hidden");
  try {
    const exclude = [...seen].join(",");
    let url;
    if (mode && mode.type === "search") {
      url = `/api/search?q=${encodeURIComponent(mode.q)}&count=24`;
    } else {
      url = `/api/candidates?count=24&exclude=${encodeURIComponent(exclude)}`;
    }
    const data = await api(url);
    const cards = data.cards;
    if (!cards.length) { exhausted = true; showEnd(); return; }
    cards.forEach(renderCard);
    countEl.textContent = (mode ? "找到 " : "已浏览 ") + seen.size + " 件";
    if (!mode) reportSeen(cards.map(c => c.id));  // 随机浏览才标记已看过
  } catch (e) {
    toast("加载失败: " + e.message, true);
  } finally {
    busy = false;
    loading.classList.add("hidden");
  }
}

// 渲染后批量上报"已看过"（图片库 seen 标记，unseen 优先展示新图）
function reportSeen(ids) {
  fetch("/api/seen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ids }),
  }).catch(() => {});
}

function renderCard(c) {
  seen.add(c.id);
  const card = document.createElement("div");
  card.className = "card";
  const favCls = favSet.has(c.id) ? "on" : "";

  // 占位层：按真实宽高比撑高（图片加载完成零跳动）
  const ph = document.createElement("div");
  ph.className = "ph";
  ph.style.aspectRatio = String(c.ratio || 4 / 3);
  ph.innerHTML = `<div class="ph-t">${escapeHtml(c.title)}</div><div class="ph-dot"></div>`;

  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = c.title;
  img.src = c.thumb;
  if (c.cached) {
    img.classList.add("ready");  // 本地缓存：直接显示
    ph.remove();
  } else {
    img.onload = () => { img.classList.add("ready"); ph.remove(); };
    // 下载慢/失败：不删卡，3 秒后重试（最多 2 次）——新图首次下载常见
    let retries = 0;
    img.onerror = () => {
      if (retries < 2) {
        retries++;
        setTimeout(() => { img.src = c.thumb + "?r=" + retries; }, 3000);
      } else {
        ph.querySelector(".ph-dot").textContent = "加载失败";
      }
    };
  }

  const fav = document.createElement("button");
  fav.className = `fav ${favCls}`;
  fav.dataset.id = c.id;
  fav.title = "收藏";
  fav.textContent = "♥";
  fav.addEventListener("click", e => { e.stopPropagation(); toggleFav(c.id); });

  // 同组堆叠：角标 ×N + hover 时整个堆叠组轮播播放
  const g = c.group || { count: 1, ids: [c.id] };
  if (g.count > 1) {
    const badge = document.createElement("div");
    badge.className = "stack-badge";
    badge.textContent = `×${g.count}`;
    badge.title = `同系列还有 ${g.count - 1} 件`;
    card.appendChild(badge);

    // hover 轮播：代表 + 组员依次播放（鼠标移入开始，移出恢复）
    const allIds = [c.id, ...g.ids.filter(i => i !== c.id)];
    let timer = null, idx = 0, playSeq = 0;
    const playNext = () => {
      const seq = ++playSeq;                       // 竞态保护：旧图 onload 丢弃
      idx = (idx + 1) % allIds.length;
      const mid = allIds[idx];
      const simg = new Image();
      simg.onload = () => {
        if (seq !== playSeq) return;
        img.classList.remove("ready");          // 淡出当前
        setTimeout(() => {
          if (seq !== playSeq) return;
          img.src = simg.src;                    // 换组内下一张
          img.classList.add("ready");            // 淡入
        }, 160);
      };
      simg.src = `/media/img/${mid}_small.jpg`;
    };
    card.addEventListener("mouseenter", () => {
      if (timer) return;
      timer = setInterval(playNext, 1500);       // 每 1.5s 播下一张
    });
    card.addEventListener("mouseleave", () => {
      clearInterval(timer);
      timer = null;
      playSeq++;                                  // 丢弃挂起的切换
      img.src = c.thumb;
      img.classList.add("ready");
    });
  }

  const cap = document.createElement("div");
  cap.className = "cap";
  cap.innerHTML = `
    <div class="t">${escapeHtml(c.title)}</div>
    <div class="a">${escapeHtml(c.artist)} · ${escapeHtml(c.date)}</div>`;

  card.append(ph, img, fav, cap);
  card.addEventListener("click", () => openDetail(c.id));
  grid.appendChild(card);
}

function syncCardFavs() {
  grid.querySelectorAll(".card").forEach(card => {
    const btn = card.querySelector(".fav");
    if (!btn) return;
    const id = btn.dataset.id;
    btn.classList.toggle("on", favSet.has(Number(id)));
  });
}

// ── 详情抽屉 ────────────────────────────────────────────────
const drawer = document.getElementById("drawer");
const detail = document.getElementById("detail");
let currentDetail = null;
let styles = ["gallery", "minimal", "label", "random"];

async function openDetail(id) {
  drawer.classList.remove("hidden");
  detail.innerHTML = `<div class="loading">加载详情…</div>`;
  try {
    const w = await api(`/api/work/${id}`);
    currentDetail = id;
    // 默认风格：竖幅（ratio<1）→ 竖幅友好（pedestal）；横幅 → 🎲 随机
    const defaultStyle = (w.ratio || 1) < 1 ? "pedestal" : "random";
    const meta = [
      ["创作日期", w.date],
      ["部门", w.department],
      ["材质", w.medium],
      ["文化", w.culture],
      ["尺寸", w.dimensions],
      ["来源", w.creditLine],
      ["藏品编号", w.accessionNumber],
    ].filter(x => x[1]).map(([k, v]) => `<span><b>${k}</b>${escapeHtml(v)}</span>`).join("");

    detail.innerHTML = `
      <div class="dgallery" id="dgallery">
        <img class="dbig" src="${w.thumb}" data-big="${w.image}" alt="${escapeHtml(w.title)}">
        <button class="g-nav g-prev hidden" id="gPrev" title="上一张">‹</button>
        <button class="g-nav g-next hidden" id="gNext" title="下一张">›</button>
        <div class="g-idx hidden" id="gIdx"></div>
      </div>
      <h2>${escapeHtml(w.title)}</h2>
      <div class="dartist"><a href="#" id="artistLink" title="查看该艺术家全部作品">${escapeHtml(w.artist)}</a></div>
      <div class="dmeta">${meta}</div>
      <div class="d-actions">
        <select id="styleSel">${styles.map(s =>
          `<option value="${s}"${(s === defaultStyle) ? " selected" : ""}>${s === "random" ? "🎲 随机风格" : s}</option>`).join("")}</select>
        <button id="applyBtn" class="btn">设为壁纸</button>
        <button id="dfavBtn" class="btn accent small${favSet.has(id) ? " on" : ""}">${favSet.has(id) ? "♥ 已收藏" : "♡ 收藏"}</button>
      </div>
      <div id="dstatus" class="d-status"></div>
      <div class="d-notes hidden" id="dnotes">
        <div class="notes-head">
          <b>作品简介</b>
          <div class="notes-tabs" id="notesTabs">
            <button class="on" data-lang="zh">中文</button>
            <button data-lang="en">English</button>
          </div>
        </div>
        <p class="notes-text" id="notesText"></p>
        <a class="notes-src" id="notesSrc" target="_blank" rel="noopener">Wikipedia 原文 ↗</a>
      </div>
      <div class="durl"><a href="${w.url}" target="_blank" rel="noopener">Met 官网原页 ↗</a></div>`;

    // 简介（异步加载，无则隐藏）
    let notesLang = "zh";
    const notesBox = detail.querySelector("#dnotes");
    const notesText = detail.querySelector("#notesText");
    const notesSrc = detail.querySelector("#notesSrc");
    async function loadNotes() {
      try {
        const nd = await api(`/api/notes/${id}?lang=${notesLang}`);
        if (nd.note) {
          notesText.textContent = nd.note.extract;
          notesSrc.href = nd.note.url;
          notesBox.classList.remove("hidden");
        } else {
          notesBox.classList.add("hidden");
        }
      } catch (e) { notesBox.classList.add("hidden"); }
    }
    detail.querySelectorAll("#notesTabs button").forEach(btn => {
      btn.addEventListener("click", () => {
        notesLang = btn.dataset.lang;
        detail.querySelectorAll("#notesTabs button").forEach(b => b.classList.toggle("on", b === btn));
        notesBox.classList.add("hidden");
        loadNotes();
      });
    });
    loadNotes();
    // 艺术家链接 → 搜索该艺术家作品
    const artistLink = detail.querySelector("#artistLink");
    if (artistLink) {
      artistLink.addEventListener("click", e => {
        e.preventDefault();
        closeDrawer();
        searchBox.value = w.artist;
        mode = { type: "search", q: w.artist };
        refreshGrid();
      });
    }
    // 堆叠组轮播：左右滑动/箭头切换组内图，选中的那张作为壁纸
    const img = detail.querySelector("img.dbig");
    const gPrev = detail.querySelector("#gPrev");
    const gNext = detail.querySelector("#gNext");
    const gIdx = detail.querySelector("#gIdx");
    let galleryIds = [id];
    let galleryIdx = 0;
    let applyId = id;   // 当前选中的组员（设为壁纸用）

    function galleryShow(i, immediate) {
      galleryIdx = (i + galleryIds.length) % galleryIds.length;
      const gid = galleryIds[galleryIdx];
      applyId = gid;
      img.src = `/media/img/${gid}_small.jpg`;   // 小图秒显
      const big = new Image();
      big.onload = () => { img.src = big.src; }; // 大图后台替换
      big.src = `/media/img/${gid}.jpg`;
      gIdx.textContent = `${galleryIdx + 1}/${galleryIds.length}`;
      if (immediate) return;
      detail.querySelector("#dfavBtn").textContent = favSet.has(gid) ? "♥ 已收藏" : "♡ 收藏";
    }

    if (w.group && w.group.count > 1) {
      galleryIds = w.group.ids;
      gPrev.classList.remove("hidden");
      gNext.classList.remove("hidden");
      gIdx.classList.remove("hidden");
      gIdx.textContent = `1/${galleryIds.length}`;
      gPrev.addEventListener("click", () => galleryShow(galleryIdx - 1));
      gNext.addEventListener("click", () => galleryShow(galleryIdx + 1));
      // 触控左右滑动
      let tx = 0;
      detail.querySelector("#dgallery").addEventListener("touchstart", e => {
        tx = e.touches[0].clientX;
      }, { passive: true });
      detail.querySelector("#dgallery").addEventListener("touchend", e => {
        const dx = e.changedTouches[0].clientX - tx;
        if (dx > 40) galleryShow(galleryIdx - 1);
        else if (dx < -40) galleryShow(galleryIdx + 1);
      }, { passive: true });
    }

    // 收藏按钮（跟随轮播选中项）
    detail.querySelector("#dfavBtn").addEventListener("click", async () => {
      await toggleFav(applyId);
      const b = detail.querySelector("#dfavBtn");
      const isFav = favSet.has(applyId);
      b.textContent = isFav ? "♥ 已收藏" : "♡ 收藏";
      b.classList.toggle("on", isFav);   // 已收藏 → 金色字
    });

    // 设为壁纸（用轮播选中的那张）
    detail.querySelector("#applyBtn").addEventListener("click", async () => {
      const btn = detail.querySelector("#applyBtn");
      const st = detail.querySelector("#dstatus");
      btn.disabled = true;
      st.textContent = "渲染中…（首次需下载高清大图，可能 10-30 秒）";
      try {
        const style = detail.querySelector("#styleSel").value;
        const r = await api(`/api/apply/${applyId}?style=${style}`, { method: "POST" });
        st.textContent = `✓ 已应用 [${r.style}]：${r.title}`;
        toast(`✓ 壁纸已应用 [${r.style}]`);
      } catch (e) {
        st.textContent = "✗ " + e.message;
        toast("应用失败: " + e.message, true);
      } finally {
        btn.disabled = false;
      }
    });
  } catch (e) {
    detail.innerHTML = `<div class="loading">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function closeDrawer() {
  drawer.classList.add("hidden");
  currentDetail = null;
}
document.getElementById("drawerClose").addEventListener("click", closeDrawer);
document.getElementById("drawerBackdrop").addEventListener("click", closeDrawer);

// ── 左侧面板（收藏/历史）───────────────────────────────────
const panel = document.getElementById("panel");
const panelBody = document.getElementById("panelBody");
let panelTab = "fav";

function openPanel(tab) {
  panelTab = tab;
  panel.classList.remove("hidden");
  document.querySelectorAll(".panel-tabs .tab").forEach(t =>
    t.classList.toggle("active", t.dataset.tab === tab));
  renderPanel(tab);
}

function closePanel() { panel.classList.add("hidden"); }

async function renderPanel(tab) {
  panelBody.innerHTML = `<div class="loading">加载中…</div>`;
  try {
    const d = await api(tab === "fav" ? "/api/favorites" : "/api/history");
    const items = d.items;
    if (!items.length) {
      panelBody.innerHTML = `<div class="panel-empty">${
        tab === "fav" ? "收藏为空<br>网格卡片上点 ♥ 收藏喜欢的作品" : "暂无历史<br>应用过壁纸后会记录在这里"}</div>`;
      return;
    }
    panelBody.innerHTML = items.map(itemHtml(tab)).join("");
    // 事件
    panelBody.querySelectorAll(".panel-item").forEach(el => {
      const id = Number(el.dataset.id);
      el.addEventListener("click", e => {
        if (e.target.classList.contains("pi-rm")) return;
        closePanel();
        openDetail(id);
      });
      const rm = el.querySelector(".pi-rm");
      if (rm) rm.addEventListener("click", async e => {
        e.stopPropagation();
        await toggleFav(id);
      });
    });
  } catch (e) {
    panelBody.innerHTML = `<div class="panel-empty">加载失败：${escapeHtml(e.message)}</div>`;
  }
}

function itemHtml(tab) {
  return c => `
    <div class="panel-item" data-id="${c.id}">
      <img loading="lazy" src="${c.thumb}" alt="">
      <div class="pi-main">
        <div class="pi-t">${escapeHtml(c.title)}</div>
        <div class="pi-a">${escapeHtml(c.artist)} · ${escapeHtml(c.date)}${c.style ? ` · [${c.style}]` : ""}</div>
      </div>
      ${tab === "fav" ? `<span class="pi-tag">${escapeHtml(c.department || "")}</span>
      <button class="pi-rm" title="取消收藏">✕</button>` : ""}
    </div>`;
}

document.getElementById("favBtn").addEventListener("click", () => openPanel("fav"));
document.getElementById("histBtn").addEventListener("click", () => openPanel("hist"));
document.getElementById("panelBackdrop").addEventListener("click", closePanel);
document.querySelectorAll(".panel-tabs .tab").forEach(t =>
  t.addEventListener("click", () => openPanel(t.dataset.tab)));

// ── 滚动加载 / 换一批 / 快捷键 ─────────────────────────────
window.addEventListener("scroll", () => {
  // 提前 1200px 触发：滚动到底部前新一批已就绪
  if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 1200) loadBatch();
});

// 换一批：交叉淡入淡出（防屏闪）
async function refreshGrid() {
  grid.classList.add("fading");
  await new Promise(r => setTimeout(r, 190));   // 等淡出完成
  grid.innerHTML = "";
  seen.clear();
  exhausted = false;
  busy = false;                                 // 释放可能的滚动加载占用
  await loadBatch();                            // 渲染新批
  grid.classList.remove("fading");              // 淡入
  window.scrollTo({ top: 0, behavior: "smooth" });
}
document.getElementById("refresh").addEventListener("click", refreshGrid);

// ── 搜索 ───────────────────────────────────────────────────
function applyMode() {
  // 模式同步到 URL hash：刷新/换一批/分享都保持当前搜索
  const h = mode ? `q=${encodeURIComponent(mode.q)}` : "";
  history.replaceState(null, "", h ? `#${h}` : "#");
}
function restoreMode() {
  // 页面加载时从 hash 恢复搜索状态
  const h = location.hash.replace(/^#/, "");
  if (h.startsWith("q=")) {
    const q = decodeURIComponent(h.slice(2));
    mode = { type: "search", q };
    searchBox.value = q;
  }
}
searchBox.addEventListener("keydown", e => {
  if (e.key !== "Enter") return;
  const q = searchBox.value.trim();
  mode = q ? { type: "search", q } : null;
  applyMode();
  refreshGrid();
});
document.addEventListener("keydown", e => {
  if (e.key === "Escape") { closeDrawer(); closePanel(); }
});

function showEnd() { end.classList.remove("hidden"); }

// ── 启动 ────────────────────────────────────────────────────
(async function init() {
  try {
    const s = await api("/api/styles");
    styles = s.styles;
  } catch (e) { /* 默认风格列表兜底 */ }
  await refreshFavCount();
  restoreMode();  // 从 URL hash 恢复部门/搜索状态（F5 后保持）
  fetch("/api/prefetch", { method: "POST" }).catch(() => {});  // 一进来即后台拉新入库
  loadBatch();
})();
