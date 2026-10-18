/* ==========================================================================
 * 电视直播 - 前端应用逻辑
 * 通过 window.pywebview.api 调用 Python 后端, 前端负责渲染与 HLS 播放
 * ========================================================================== */
'use strict';

/* ---------- 状态 ---------- */
const state = {
  categories: [],
  channels: [],
  activeCat: null,
  activeChannel: null,
  sourceIndex: 0,       // 当前播放源在 sources 中的下标
  statusCache: {},      // url -> {ok, latency_ms}
  byChannel: {},        // name -> {ok, source_index, latency_ms}
  favSet: new Set(),
  history: [],
  onlyGood: false,      // 只看可用
  filterText: '',
  initialized: false,
  proxyBase: 'http://127.0.0.1:8000/proxy?url=', // 默认值会被后端的真实端口覆盖
};

const video = document.getElementById('video');
let hls = null;

/* ---------- 工具 ---------- */
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function latencyLevel(lat) {
  if (lat < 0) return 'bad';     // 未检测/失败
  if (lat < 500) return 'ok';
  if (lat < 2500) return 'slow';
  return 'bad';
}

/* ---------- 数据加载 ---------- */
async function loadAll() {
  try {
    setStatus('正在加载数据…');
    const [data, cache, prefs] = await Promise.all([
      window.pywebview.api.get_channels(),
      window.pywebview.api.get_cache(),
      window.pywebview.api.get_prefs(),
    ]);
    state.categories = data.categories;
    state.channels = data.channels;
    state.statusCache = (cache && cache.source_status) || {};
    state.byChannel = (cache && cache.by_channel) || {};
    state.favSet = new Set((prefs && prefs.favorites) || []);
    state.history = (prefs && prefs.history) || [];
    state.initialized = true;
    // 取本地代理基址(端口随机), 播放地址统一走 /proxy?url= 绕开 CORS
    try {
      const pb = await window.pywebview.api.get_proxy_base();
      if (pb) state.proxyBase = pb;
    } catch (e) { console.warn('获取代理基址失败', e); }
    renderCategories();
    renderChannels();
    updateStats();
    // 恢复最后播放
    if (prefs && prefs.last_channel) {
      const last = state.channels.find(c => c.name === prefs.last_channel);
      if (last) {
        state.activeCat = last.category;
        renderCategories();
        selectChannel(last.name, true);
      } else {
        setStatus('就绪');
      }
    } else {
      setStatus('就绪');
    }
  } catch (e) {
    console.error(e);
    setStatus('加载失败: ' + e.message);
  }
}

/* ---------- 渲染 ---------- */
function renderCategories() {
  const ul = $('cat-list');
  ul.innerHTML = '';
  const items = [];
  if (state.favSet.size > 0 || true) {
    items.push({ key: '__fav__', label: '★ 我的收藏' });
  }
  items.push({ key: '__all__', label: '全部频道' });
  for (const c of state.categories) {
    items.push({ key: c, label: c });
  }
  for (const it of items) {
    const li = document.createElement('li');
    li.dataset.cat = it.key;
    if (it.key === state.activeCat) li.classList.add('active');
    li.textContent = it.label;
    if (it.key !== '__fav__' && it.key !== '__all__') {
      const count = state.channels.filter(c => c.category === it.key).length;
      li.innerHTML += ` <span class="cat-count">${count}</span>`;
    }
    li.onclick = () => {
      state.activeCat = it.key;
      state.filterText = '';
      $('search').value = '';
      renderCategories();
      renderChannels();
    };
    ul.appendChild(li);
  }
}

function visibleChannels() {
  let list = [];
  if (state.activeCat === '__fav__') {
    list = state.channels.filter(c => state.favSet.has(c.name));
  } else if (state.activeCat === '__all__') {
    list = state.channels;
  } else {
    list = state.channels.filter(c => c.category === state.activeCat);
  }
  const t = state.filterText.trim().toLowerCase();
  if (t) list = list.filter(c => c.name.toLowerCase().includes(t));
  if (state.onlyGood) {
    list = list.filter(c => state.byChannel[c.name] && state.byChannel[c.name].ok);
  }
  return list;
}

function renderChannels() {
  const ul = $('channel-list');
  ul.innerHTML = '';
  const list = visibleChannels();
  $('channel-count').textContent = list.length;
  if (list.length === 0) {
    ul.innerHTML = '<li style="color:#5a6572;padding:16px;text-align:center">暂无频道</li>';
    return;
  }
  for (const ch of list) {
    const li = document.createElement('li');
    li.dataset.name = ch.name;
    if (state.activeChannel === ch.name) li.classList.add('active');

    const logo = document.createElement('div');
    logo.className = 'ch-logo';
    if (ch.logo) {
      const img = document.createElement('img');
      img.loading = 'lazy';
      img.alt = '';
      img.src = ch.logo;
      img.onerror = () => { logo.textContent = ch.name.slice(0, 2); };
      logo.appendChild(img);
    } else {
      logo.textContent = ch.name.slice(0, 2);
    }

    const name = document.createElement('span');
    name.className = 'ch-name';
    name.textContent = ch.name;
    const favMark = state.favSet.has(ch.name) ? ' ★' : '';
    if (favMark) name.textContent += favMark;

    const st = state.byChannel[ch.name];
    const dot = document.createElement('span');
    dot.className = 'ch-status';
    if (st) {
      dot.style.background = st.ok
        ? (latencyLevel(st.latency_ms) === 'ok' ? 'var(--ok)' : 'var(--slow)')
        : 'var(--bad)';
    } else {
      dot.style.background = 'var(--text-dim)';
      dot.style.opacity = '.4';
    }

    li.append(logo, name, dot);
    li.ondblclick = () => selectChannel(ch.name, false);
    li.onclick = () => {
      document.querySelectorAll('#channel-list li.active').forEach(e => e.classList.remove('active'));
      li.classList.add('active');
      state.activeChannel = ch.name;
      $('now-playing').textContent = ch.name;
    };
    ul.appendChild(li);
  }
}

/* ---------- 状态统计 ---------- */
function updateStats() {
  const stats = state.statusCache;
  const okCount = state.channels.filter(c => state.byChannel[c.name] && state.byChannel[c.name].ok).length;
  $('status-text').textContent = `可用 ${okCount}/${state.channels.length}`;
}

/* ---------- 播放 ---------- */
async function playSource(url, sourceIdx, totalSrc, chName) {
  destroyHls();
  const mask = $('video-mask');
  const title = $('mask-title');
  const sub = $('mask-sub');

  if (Hls.isSupported()) {
    hls = new Hls({
      enableWorker: true,
      lowLatencyMode: true,
      maxBufferLength: 30,
      maxMaxBufferLength: 60,
      manifestLoadingTimeOut: 12000,
      levelLoadingTimeOut: 12000,
      fragLoadingTimeOut: 15000,
    });
    hls.loadSource(url);
    hls.attachMedia(video);
    hls.on(Hls.Events.ERROR, (evt, data) => {
      if (!data.fatal) return;
      console.warn('[hls] fatal', data.type, data.details);
      if (data.type === Hls.ErrorTypes.NETWORK_ERROR || data.type === Hls.ErrorTypes.MEDIA_ERROR) {
        hls.recoverMediaError();
        // 网络错误: 尝试自动切到下一条源
        if (totalSrc > 1) {
          autoNextSource(chName);
        }
      }
    });
    hls.on(Hls.Events.MANIFEST_PARSED, () => {
      mask.classList.add('hidden');
      video.play().catch(() => {});
      setStatus('');
    });
    hls.on(Hls.Events.LEVEL_LOADED, (e, d) => {
      const lat = Math.round(d.details && d.details.live ? 0 : 0);
      $('source-info').textContent = `源 ${sourceIdx + 1}/${totalSrc}`;
    });
  } else if (video.canPlayType('application/vnd.apple.mpegurl')) {
    video.src = url;
    video.play().catch(() => {});
    mask.classList.add('hidden');
    $('source-info').textContent = `源 ${sourceIdx + 1}/${totalSrc}`;
  } else {
    title.textContent = '当前内核不支持 HLS 播放';
    sub.textContent = '请安装新版 Edge/Chrome';
  }

  $('source-info').textContent = `源 ${sourceIdx + 1}/${totalSrc} · ${chName}`;
}

function destroyHls() {
  if (hls) {
    hls.destroy();
    hls = null;
  }
  video.pause();
  video.removeAttribute('src');
  video.load();
}

/* 选择频道并播放其第一条可用源 */
async function selectChannel(name, fromHistory) {
  const ch = state.channels.find(c => c.name === name);
  if (!ch) return;
  state.activeChannel = name;
  state.activeCat = ch.category;
  renderCategories();
  renderChannels();

  const st = state.byChannel[name];
  let idx = 0;
  if (st && st.ok && typeof st.source_index === 'number') {
    idx = st.source_index; // 默认播最快的那条
  }
  state.sourceIndex = idx;

  const updater = $('now-playing');
  updater.textContent = ch.name;
  // 显示加载遮罩
  const mask = $('video-mask');
  mask.classList.remove('hidden');
  $('mask-title').textContent = ch.name;
  $('mask-sub').textContent = '正在连接直播源…';

  const rawUrl = ch.sources[idx];
  if (rawUrl) {
    // 走本地代理: 解决 hls.js 拉 http 直播源的 CORS 拦截
    const url = state.proxyBase + encodeURIComponent(rawUrl);
    playSource(url, idx, ch.sources.length, ch.name);
    // 记录历史
    try { await window.pywebview.api.add_history(name); } catch (e) {}
  } else {
    $('mask-title').textContent = ch.name + ' 无可用源';
    $('mask-sub').textContent = '请点击"更新源"后再试';
  }
}

/* 切到下一条可用源 */
function autoNextSource(chName) {
  const ch = state.channels.find(c => c.name === chName);
  if (!ch) return;
  const n = ch.sources.length;
  let next = (state.sourceIndex + 1) % n;
  let tried = 0;
  while (tried < n) {
    const rawUrl = ch.sources[next];
    const st = state.statusCache[rawUrl];
    if (!st || st.ok) {
      state.sourceIndex = next;
      playSource(state.proxyBase + encodeURIComponent(rawUrl), next, n, chName);
      return;
    }
    next = (next + 1) % n;
    tried++;
  }
  $('mask-title').textContent = chName + ' 所有源不可用';
  $('mask-sub').textContent = '请更新源或稍后再试';
}

/* 手动换源 */
function manualSwitch() {
  const ch = state.channels.find(c => c.name === state.activeChannel);
  if (!ch || ch.sources.length === 0) return;
  autoNextSource(ch.name);
}

/* ---------- 收藏 ---------- */
async function toggleFav() {
  if (!state.activeChannel) return;
  const name = state.activeChannel;
  const has = state.favSet.has(name);
  if (has) state.favSet.delete(name); else state.favSet.add(name);
  try { await window.pywebview.api.set_favorite(name, !has); } catch (e) {}
  renderChannels();
  const btn = $('btn-fav');
  if (btn) btn.classList.toggle('active', !has);
}

/* ---------- 状态文本 ---------- */
function setStatus(t) {
  $('status-text').textContent = t;
}

/* ---------- 事件绑定 ---------- */
function bindEvents() {
  // 搜索
  $('search').addEventListener('input', (e) => {
    state.filterText = e.target.value;
    renderChannels();
  });
  // 上下频道
  $('btn-prev').onclick = () => stepChannel(-1);
  $('btn-next').onclick = () => stepChannel(1);
  // 换源
  $('btn-switch').onclick = manualSwitch;
  // 只看可用
  $('btn-filter').onclick = () => {
    state.onlyGood = !state.onlyGood;
    $('btn-filter').classList.toggle('active', state.onlyGood);
    renderChannels();
  };
  // 收藏
  const favBtn = document.createElement('button');
  favBtn.id = 'btn-fav';
  favBtn.className = 'btn bar-btn';
  favBtn.textContent = '☆ 收藏';
  favBtn.title = '收藏当前频道';
  favBtn.onclick = toggleFav;
  $('player-bar').insertBefore(favBtn, $('btn-switch'));
  // 键盘
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT') return;
    switch (e.key) {
      case 'ArrowUp': stepChannel(-1); e.preventDefault(); break;
      case 'ArrowDown': stepChannel(1); e.preventDefault(); break;
      case 's': case 'S': manualSwitch(); break;
      case 'f': case 'F': toggleFav(); break;
      case ' ': 
        if (video.paused) video.play().catch(()=>{}); else video.pause();
        e.preventDefault(); break;
    }
  });
  // 检查源 / 更新源 (由后端处理, 前端仅确认)
  $('btn-check').onclick = async () => {
    setStatus('正在检测全部源…');
    try {
      await window.pywebview.api.check_sources();
      const cache = await window.pywebview.api.get_cache();
      state.statusCache = (cache && cache.source_status) || {};
      state.byChannel = (cache && cache.by_channel) || {};
      renderChannels(); updateStats();
      setStatus('检测完成');
    } catch (e) { setStatus('检测失败: ' + e.message); }
  };
  $('btn-update').onclick = async () => {
    setStatus('正在更新源…');
    try {
      const res = await window.pywebview.api.update_sources();
      const fresh = await window.pywebview.api.get_channels();
      state.channels = fresh.channels;
      state.categories = fresh.categories;
      renderCategories(); renderChannels(); updateStats();
      setStatus(res && res.message ? res.message : '更新完成');
    } catch (e) { setStatus('更新失败: ' + e.message); }
  };
  video.addEventListener('error', () => {
    if (hls) return; // hls 错误自行处理
    const ch = state.channels.find(c => c.name === state.activeChannel);
    if (ch && ch.sources.length > 1) autoNextSource(ch.name);
  });
}

function stepChannel(dir) {
  const list = visibleChannels();
  if (list.length === 0) return;
  let idx = list.findIndex(c => c.name === state.activeChannel);
  if (idx < 0) idx = 0;
  else idx = (idx + dir + list.length) % list.length;
  try { window.pywebview.api.add_history(list[idx].name); } catch (e) {}
  selectChannel(list[idx].name);
}

/* ---------- 启动 ---------- */
document.addEventListener('DOMContentLoaded', () => {
  bindEvents();
  // pywebview 注入完成后再加载
  function tryLoad() {
    if (window.pywebview && window.pywebview.api) {
      loadAll();
    } else {
      setTimeout(tryLoad, 100);
    }
  }
  tryLoad();
});