// NEUROCORP — конвейер: КЛИЕНТЫ → 2 МЕНЕДЖЕРА → РП → [ТЫ: Проект+КП] → КОМАНДА → СДАНО
const $ = (id) => document.getElementById(id);
const state = { workforce: [], byName: {}, byId: {}, paused: false };
const CH_LABEL = { call: 'ЗВОНОК', telegram: 'TG', whatsapp: 'WA', email: 'MAIL', meeting: 'ВСТРЕЧА', task: 'ЗАДАЧА' };

// ── Узлы конвейера (позиции в долях canvas) ──────────────────────────────────
const NODE = {
  clients:    { x: .06, y: .22, c: '#00e5ff', label: 'КЛИЕНТЫ', big: .7 },
  m1:         { x: .20, y: .14, c: '#00e5ff', label: 'МЕН-1' },
  m2:         { x: .20, y: .38, c: '#18b6ff', label: 'МЕН-2' },
  rp:         { x: .35, y: .25, c: '#ff2bd6', label: 'РП', big: 1.15 },
  you:        { x: .52, y: .10, c: '#ffd24a', label: 'ТЫ', hex: true, big: 1.15 },
  analyst:    { x: .21, y: .78, c: '#7c5cff', label: 'АНАЛИТИК' },
  developer:  { x: .38, y: .68, c: '#39ff14', label: 'РАЗРАБ' },
  consultant: { x: .38, y: .90, c: '#ffb000', label: 'КОНСУЛЬТ' },
  tester:     { x: .57, y: .79, c: '#00d0c0', label: 'ТЕСТ' },
  acceptor:   { x: .75, y: .79, c: '#ff8a3d', label: 'ПРИЁМКА' },
  done:       { x: .92, y: .79, c: '#39ff14', label: 'СДАНО', hex: true },
};
const LANES = [
  ['clients', 'm1'], ['clients', 'm2'], ['m1', 'rp'], ['m2', 'rp'], ['rp', 'you'],
  ['rp', 'analyst'], ['analyst', 'developer'], ['analyst', 'consultant'],
  ['developer', 'tester'], ['consultant', 'tester'], ['tester', 'acceptor'], ['acceptor', 'done'],
];
const NODE_TITLE = { m1: 'МЕНЕДЖЕР-1', m2: 'МЕНЕДЖЕР-2', rp: 'РП', you: 'ТЫ', analyst: 'АНАЛИТИК',
  developer: 'РАЗРАБОТЧИК', consultant: 'КОНСУЛЬТАНТ', tester: 'ТЕСТИРОВЩИК', acceptor: 'ПРИЁМЩИК',
  done: 'СДАНО', clients: 'КЛИЕНТЫ' };
const DELIVERY_NODES = ['analyst', 'developer', 'consultant', 'tester', 'acceptor'];
const nodeTask = {};

// ── Часы ─────────────────────────────────────────────────────────────────────
setInterval(() => { $('clock').textContent = new Date().toLocaleTimeString('ru-RU', { hour12: false }); }, 1000);

// ── WebSocket ────────────────────────────────────────────────────────────────
let ws;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onmessage = (e) => handle(JSON.parse(e.data));
  ws.onclose = () => { setLive(false, 'RECONNECT'); setTimeout(connect, 1500); };
  ws.onopen = () => setLive(!state.paused);
}
function setLive(on, label) { const el = $('live-dot'); el.classList.toggle('paused', !on); el.lastChild.textContent = ' ' + (label || (on ? 'LIVE' : 'PAUSED')); }

// ── Маршрутизатор ────────────────────────────────────────────────────────────
function handle(evt) {
  const d = evt.data || {};
  switch (evt.type) {
    case 'snapshot': initSnapshot(d); break;
    case 'log': addFeed(d, evt.ts); break;
    case 'agent_status': onAgentStatus(d); break;
    case 'flow': onFlow(d); break;
    case 'interaction': if (d.contact && (d.channel !== 'task')) ensureClient(d.contact); break;
    case 'approval_new': addApproval(d.approval); break;
    case 'approval_resolved': onApprovalResolved(d.approval_id, d.decision); break;
    case 'contact_new': if (d.contact && d.contact.stage !== 'DELIVERY') ensureClient(d.contact); break;
  }
}
function initSnapshot(d) {
  state.workforce = d.workforce; state.paused = d.paused;
  state.byName = {}; state.byId = {};
  d.workforce.forEach((a) => { state.byName[a.name] = a; state.byId[a.id] = a; });
  $('mode-badge').textContent = d.demo ? 'DEMO' : 'LIVE-API';
  $('mode-badge').classList.toggle('badge-live', !d.demo);
  renderWorkforce(d.workforce); renderPipeline(d.pipeline); renderMetrics(d.metrics);
  $('approvals').innerHTML = ''; (d.approvals || []).forEach(addApproval);
  if (!(d.approvals || []).length) emptyApprovals();
  $('feed').innerHTML = ''; (d.feed || []).filter((e) => e.type === 'log').forEach((e) => addFeed(e.data, e.ts));
  setLive(!d.paused); setPauseBtn(d.paused);
  (d.contacts || []).filter((c) => ['NEW', 'CONTACTED', 'RP_REVIEW'].includes(c.stage)).slice(0, MAX_CLIENTS).forEach(ensureClient);
}

// ── ИИ-штат ──────────────────────────────────────────────────────────────────
function renderWorkforce(wf) {
  $('wf-count').textContent = wf.length;
  $('workforce').innerHTML = wf.map((a) => `
    <div class="wf ${a.status === 'working' ? 'active' : ''}" id="wf-${a.id}" style="--c:${a.color}">
      <div class="wf-dot"></div>
      <div class="wf-body"><div class="wf-name">${a.name}</div><div class="wf-role">${a.role}</div>
        ${a.task ? `<div class="wf-task">▸ ${a.task}</div>` : ''}</div>
      <div class="wf-stat">${a.status === 'working' ? 'BUSY' : 'IDLE'}</div>
    </div>`).join('');
}
function onAgentStatus(d) {
  const a = state.byId[d.agent_id]; if (a) { a.status = d.status; a.task = d.task; }
  const el = $('wf-' + d.agent_id);
  if (el) {
    el.classList.toggle('active', d.status === 'working');
    el.querySelector('.wf-stat').textContent = d.status === 'working' ? 'BUSY' : 'IDLE';
    let t = el.querySelector('.wf-task');
    if (d.status === 'working' && d.task) { if (!t) { t = document.createElement('div'); t.className = 'wf-task'; el.querySelector('.wf-body').appendChild(t); } t.textContent = '▸ ' + d.task; }
    else if (t) t.remove();
  }
  nodeTask[d.agent_id] = d.status === 'working' ? (d.task || '') : '';
  if (d.status === 'working') flash(d.agent_id);
}

// ── Реальная анимация: только по событиям flow ───────────────────────────────
function onFlow(d) {
  let blip = null;
  if (d.src === 'client' || d.dst === 'client') blip = ensureClient({ id: d.contact_id, name: d.name });
  const from = d.src === 'client' ? blip : d.src;
  const to = d.dst === 'client' ? blip : d.dst;
  if (!from || !to) return;
  flowPath([from, to], d.color || '#00e5ff');
  if (typeof to === 'string') flash(to); else if (to) to.flash = 1;
}
function flash(key) { if (stations[key]) stations[key].flash = 1; }

// ── Воронка / метрики / лента ────────────────────────────────────────────────
const STAGE_LABEL = { NEW: 'Новый запрос', CONTACTED: 'Менеджер', RP_REVIEW: 'Оценка РП',
  APPROVAL: 'На согласовании', DELIVERY: 'В работе', WON: 'Сдано', LOST: 'Отсеяно' };
function renderPipeline(p) {
  const order = ['NEW', 'CONTACTED', 'RP_REVIEW', 'APPROVAL', 'DELIVERY', 'WON', 'LOST'];
  const max = Math.max(1, ...order.map((s) => p[s] || 0));
  $('pipeline').innerHTML = order.map((s) => `
    <div class="stage"><div class="stage-top"><span>${STAGE_LABEL[s] || s}</span><b>${p[s] || 0}</b></div>
    <div class="stage-bar"><div class="stage-fill" style="width:${Math.round(100 * (p[s] || 0) / max)}%"></div></div></div>`).join('');
}
function renderMetrics(m) {
  $('m-req').textContent = m.requests; $('m-dialog').textContent = m.dialog;
  $('m-await').textContent = m.awaiting; $('m-work').textContent = m.delivery;
  $('m-won').textContent = m.won; $('m-lost').textContent = m.lost; $('m-conv').textContent = m.conversion + '%';
}
function addFeed(d, ts) {
  const f = $('feed'), div = document.createElement('div'); div.className = 'fl ' + (d.level || 'info');
  const t = new Date((ts || Date.now() / 1000) * 1000).toLocaleTimeString('ru-RU', { hour12: false });
  div.innerHTML = `<span class="t">${t}</span>${esc(d.line)}`;
  f.appendChild(div); while (f.children.length > 120) f.removeChild(f.firstChild); f.scrollTop = f.scrollHeight;
}
const esc = (s) => { const d = document.createElement('div'); d.textContent = s || ''; return d.innerHTML; };

// ── Стол одобрений (Проект+КП) ───────────────────────────────────────────────
function apCard(a) {
  const c = a.contact || {}, p = a.payload || {};
  return `<div class="ap-kind">ПРОЕКТ + КП · ${esc(a.proposed_by)}</div>
    <div class="ap-title">${esc(a.title)}</div>
    <div class="ap-meta">${esc(c.company || '')}${c.role ? ' · ' + esc(c.role) : ''}</div>
    ${p.scope ? `<div class="ap-note">${esc(p.scope)} · оценка €${p.amount}</div>` : ''}
    <div class="ap-actions">
      <button class="btn btn-ok" onclick="resolveAp(${a.id},'approved')">✓ Согласовать</button>
      <button class="btn btn-no" onclick="resolveAp(${a.id},'rejected')">✗ Отклонить</button>
    </div>`;
}
function addApproval(a) {
  if ($('ap-' + a.id)) return;
  const e = $('approvals').querySelector('.empty'); if (e) e.remove();
  const el = document.createElement('div'); el.className = 'ap'; el.id = 'ap-' + a.id;
  el.innerHTML = apCard(a); $('approvals').prepend(el); bumpAp(1);
}
function removeApproval(id) { const el = $('ap-' + id); if (el) el.remove(); bumpAp(-1); if (!$('approvals').children.length) emptyApprovals(); }
function bumpAp(d) { $('ap-count').textContent = Math.max(0, (+$('ap-count').textContent || 0) + d); }
function emptyApprovals() { $('approvals').innerHTML = '<div class="empty">Очередь пуста — всё под контролем ◢</div>'; }
function onApprovalResolved(id, decision) {
  removeApproval(id);
  flowPath(['you', 'rp'], decision === 'approved' ? '#39ff14' : '#ff4d6d');
  if (drawerView) refreshDrawer();
}
async function resolveAp(id, decision, override) {
  await fetch(`/api/approvals/${id}/resolve`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ decision, override }) });
  if (drawerView) refreshDrawer();
}
window.resolveAp = resolveAp;

// ── Управление ───────────────────────────────────────────────────────────────
function setPauseBtn(p) { state.paused = p; $('btn-pause').textContent = p ? '▶ RESUME' : '⏸ PAUSE'; setLive(!p); }
$('btn-pause').onclick = async () => { const action = state.paused ? 'resume' : 'pause';
  const r = await (await fetch('/api/control', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) })).json(); setPauseBtn(r.paused); };
$('btn-lead').onclick = () => $('lead-modal').classList.remove('hidden');
$('ld-cancel').onclick = () => $('lead-modal').classList.add('hidden');
$('ld-save').onclick = async () => {
  const body = { name: $('ld-name').value, company: $('ld-company').value, role: $('ld-role').value, email: $('ld-email').value, telegram: $('ld-telegram').value, lang: $('ld-lang').value };
  await fetch('/api/leads', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  ['ld-name', 'ld-company', 'ld-role', 'ld-email', 'ld-telegram'].forEach((id) => ($(id).value = '')); $('lead-modal').classList.add('hidden');
};
setInterval(async () => { try { const d = await (await fetch('/api/state')).json(); renderPipeline(d.pipeline); renderMetrics(d.metrics); } catch (e) {} }, 3000);

// ══ CANVAS ═══════════════════════════════════════════════════════════════════
const cv = $('ops'), ctx = cv.getContext('2d');
const MAX_CLIENTS = 8;
let W = 0, H = 0, t0 = performance.now();
let stations = {}, particles = [];
const clients = new Map();

function resize() { const r = cv.getBoundingClientRect(); cv.width = W = Math.max(380, r.width); cv.height = H = Math.max(300, r.height); buildLayout(); positionClients(); }
new ResizeObserver(resize).observe(cv);
function buildLayout() {
  const base = Math.max(15, Math.min(28, Math.min(W, H) * 0.05));
  stations = {};
  for (const [k, n] of Object.entries(NODE)) stations[k] = { x: n.x * W, y: n.y * H, r: base * (n.big || 1), c: n.c, label: n.label, hex: !!n.hex, flash: 0, key: k };
}
function positionClients() {
  const arr = [...clients.values()].sort((a, b) => b.lastAt - a.lastAt).slice(0, MAX_CLIENTS);
  const x = stations.clients ? stations.clients.x : W * 0.06;
  const top = H * 0.30, bot = H * 0.66, n = Math.max(1, arr.length);
  arr.forEach((cl, i) => { cl.x = x; cl.y = top + (bot - top) * (n === 1 ? 0.1 : i / (n - 1)); });
}
function ensureClient(c) {
  if (!c || c.id == null) return null;
  let cl = clients.get(c.id);
  if (cl) { cl.lastAt = Date.now(); if (c.stage) cl.stage = c.stage; return cl; }
  cl = { id: c.id, name: (c.name || '').split(' ')[0] || ('#' + c.id), full: c.name || '#' + c.id, stage: c.stage, x: W * 0.06, y: H * 0.5, flash: 1, lastAt: Date.now() };
  clients.set(c.id, cl);
  if (clients.size > MAX_CLIENTS) { const o = [...clients.values()].sort((a, b) => a.lastAt - b.lastAt)[0]; if (o) clients.delete(o.id); }
  positionClients(); return cl;
}
function resolvePt(p) { if (typeof p === 'string') { const s = stations[p]; return s ? { x: s.x, y: s.y } : { x: 0, y: 0 }; } return { x: p.x, y: p.y }; }
function flowPath(points, color, sp = 0.022) { const pts = points.map(resolvePt); if (pts.length >= 2) particles.push({ pts, seg: 0, t: 0, sp, color }); }

// ── Клик / hover ─────────────────────────────────────────────────────────────
function canvasXY(e) { const r = cv.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; }
function hit(x, y) {
  for (const k of Object.keys(stations)) { const s = stations[k]; if (Math.hypot(x - s.x, y - s.y) <= s.r + 7) return { node: k }; }
  for (const cl of clients.values()) if (Math.hypot(x - cl.x, y - cl.y) <= 9) return { contact: cl.id };
  return null;
}
cv.addEventListener('click', (e) => { const { x, y } = canvasXY(e); const h = hit(x, y); if (!h) return; if (h.node) openNode(h.node); else openContact(h.contact); });
cv.addEventListener('mousemove', (e) => { const { x, y } = canvasXY(e); cv.style.cursor = hit(x, y) ? 'pointer' : 'default'; });

// ── Отрисовка ─────────────────────────────────────────────────────────────────
function draw(now) {
  const dt = now - t0; t0 = now; ctx.clearRect(0, 0, W, H);
  if (!stations.rp) { requestAnimationFrame(draw); return; }
  ctx.strokeStyle = 'rgba(0,229,255,0.04)'; ctx.lineWidth = 1;
  for (let x = 0; x < W; x += 38) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, H); ctx.stroke(); }
  for (let y = 0; y < H; y += 38) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); }
  // линии клиент → менеджеры
  ctx.strokeStyle = 'rgba(0,229,255,0.08)'; ctx.lineWidth = 1;
  clients.forEach((cl) => { [stations.m1, stations.m2].forEach((m) => { ctx.beginPath(); ctx.moveTo(cl.x, cl.y); ctx.lineTo(m.x, m.y); ctx.stroke(); }); });
  // лейны конвейера с бегущими штрихами + стрелки
  ctx.save(); ctx.setLineDash([5, 12]); ctx.lineDashOffset = -(now / 24) % 17;
  LANES.forEach(([a, b]) => { const s = stations[a], t = stations[b]; ctx.strokeStyle = 'rgba(130,180,220,0.22)'; ctx.lineWidth = 1.6; ctx.beginPath(); ctx.moveTo(s.x, s.y); ctx.lineTo(t.x, t.y); ctx.stroke(); }); ctx.restore();
  LANES.forEach(([a, b]) => arrow(stations[a], stations[b]));
  // блипы клиентов
  ctx.textAlign = 'center';
  clients.forEach((cl) => {
    cl.flash = Math.max(0, cl.flash - 0.018);
    ctx.shadowColor = '#00e5ff'; ctx.shadowBlur = 6 + cl.flash * 16; ctx.fillStyle = cl.flash > 0.05 ? '#9bf3ff' : 'rgba(0,229,255,0.7)';
    ctx.beginPath(); ctx.arc(cl.x, cl.y, 3.4 + cl.flash * 2, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    ctx.fillStyle = 'rgba(180,210,225,0.7)'; ctx.font = '9px JetBrains Mono, monospace'; ctx.fillText(cl.name, cl.x, cl.y - 7);
  });
  // частицы
  particles = particles.filter((p) => p.seg < p.pts.length - 1);
  particles.forEach((p) => {
    p.t += p.sp * (dt / 16); while (p.t >= 1 && p.seg < p.pts.length - 1) { p.t -= 1; p.seg++; }
    if (p.seg >= p.pts.length - 1) return;
    const a = p.pts[p.seg], b = p.pts[p.seg + 1], e = p.t * (2 - p.t), x = a.x + (b.x - a.x) * e, y = a.y + (b.y - a.y) * e;
    ctx.strokeStyle = p.color + '44'; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(x, y); ctx.stroke();
    ctx.fillStyle = p.color; ctx.shadowColor = p.color; ctx.shadowBlur = 14; ctx.beginPath(); ctx.arc(x, y, 3.4, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
  });
  // станции
  for (const k of Object.keys(stations)) drawStation(stations[k], subFor(k));
  requestAnimationFrame(draw);
}
function subFor(k) {
  if (k === 'clients') return String(clients.size);
  if (k === 'you') return (+($('ap-count').textContent || 0)) + ' на решении';
  if (nodeTask[k]) return '▸ ' + clip(nodeTask[k]);
  return '';
}
function clip(s) { return s && s.length > 15 ? s.slice(0, 14) + '…' : s; }
function arrow(a, b) {
  const ang = Math.atan2(b.y - a.y, b.x - a.x), mx = a.x + (b.x - a.x) * 0.62, my = a.y + (b.y - a.y) * 0.62, sz = 5.5;
  ctx.fillStyle = 'rgba(150,200,230,0.45)'; ctx.beginPath();
  ctx.moveTo(mx + Math.cos(ang) * sz, my + Math.sin(ang) * sz);
  ctx.lineTo(mx + Math.cos(ang + 2.5) * sz, my + Math.sin(ang + 2.5) * sz);
  ctx.lineTo(mx + Math.cos(ang - 2.5) * sz, my + Math.sin(ang - 2.5) * sz);
  ctx.closePath(); ctx.fill();
}
function drawStation(s, sub) {
  s.flash = Math.max(0, s.flash - 0.02);
  const r = s.r + s.flash * 4;
  ctx.shadowColor = s.c; ctx.shadowBlur = 12 + s.flash * 26;
  ctx.fillStyle = s.c; ctx.globalAlpha = 0.14 + s.flash * 0.4; nodePath(s, r); ctx.fill();
  ctx.globalAlpha = 1; ctx.shadowBlur = 0; ctx.strokeStyle = s.c; ctx.lineWidth = 2; nodePath(s, r); ctx.stroke();
  ctx.textAlign = 'center'; ctx.fillStyle = '#fff'; ctx.font = 'bold 10px JetBrains Mono, monospace';
  ctx.fillText(s.label, s.x, s.y - r - 7);
  if (sub) { ctx.fillStyle = s.c; ctx.font = '8px JetBrains Mono, monospace'; ctx.fillText(sub, s.x, s.y + r + 12); }
}
function nodePath(s, r) { ctx.beginPath(); if (s.hex) { for (let i = 0; i <= 6; i++) { const a = i / 6 * Math.PI * 2 - Math.PI / 2; ctx[i ? 'lineTo' : 'moveTo'](s.x + Math.cos(a) * r, s.y + Math.sin(a) * r); } } else ctx.arc(s.x, s.y, r, 0, 7); }

// ══ ИНСПЕКТОР ════════════════════════════════════════════════════════════════
let drawerView = null, drawerTimer = null;
function openNode(node) { drawerView = { kind: 'node', node }; showDrawer(); refreshDrawer(); }
function openContact(cid) { drawerView = { kind: 'contact', cid }; showDrawer(); refreshDrawer(); }
window.openNode = openNode; window.openContact = openContact;
function showDrawer() { $('drawer').classList.remove('hidden'); clearInterval(drawerTimer); drawerTimer = setInterval(refreshDrawer, 2500); }
$('drawer-close').onclick = () => { $('drawer').classList.add('hidden'); drawerView = null; clearInterval(drawerTimer); };
async function refreshDrawer() {
  if (!drawerView) return;
  try {
    if (drawerView.kind === 'contact') { renderContact(await (await fetch('/api/contact/' + drawerView.cid)).json()); return; }
    const node = drawerView.node, d = await (await fetch('/api/inspect/' + node)).json();
    if (node === 'you') renderYou(d);
    else if (node === 'clients') renderClients(d);
    else if (DELIVERY_NODES.includes(node)) renderDelivery(node, d);
    else renderDialogues(node, d);
  } catch (e) {}
}
const setDrawer = (title, html) => { $('drawer-title').textContent = title; $('drawer-body').innerHTML = html; };
const fmtTime = (ts) => ts ? new Date(ts * 1000).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' }) : '';
const sentChip = (s) => `<span class="chip ${s === 'positive' ? 'pos' : s === 'negative' ? 'neg' : 'neu'}">${s || 'neutral'}</span>`;
const arrowOf = (dir) => dir === 'in' ? '←' : '→';

function renderDialogues(node, d) {
  const rows = d.dialogues || [];
  const html = rows.length ? rows.map((c) => `
    <div class="row click" onclick="openContact(${c.id})">
      <div class="row-top"><b>${esc(c.name)}</b><span>${esc(c.company || '')}${c.role ? ' · ' + esc(c.role) : ''}</span></div>
      ${c.last_summary ? `<div class="row-msg">[${CH_LABEL[c.last_channel] || ''}] ${arrowOf(c.last_dir)} ${esc(c.last_summary)}</div>` : '<div class="row-msg">— ещё не было контакта —</div>'}
      <div class="row-meta"><span>${STAGE_LABEL[c.stage] || c.stage}</span><span>${c.msg_count} сообщ.</span>${c.last_sentiment ? sentChip(c.last_sentiment) : ''}<span>${fmtTime(c.last_at)}</span></div>
    </div>`).join('') : '<div class="empty">Очередь пуста</div>';
  setDrawer(`${NODE_TITLE[node]} · очередь (${rows.length})`, html);
}
function renderClients(d) {
  const rows = d.contacts || [];
  setDrawer(`КЛИЕНТЫ (${rows.length})`, rows.map((c) => `
    <div class="row click" onclick="openContact(${c.id})">
      <div class="row-top"><b>${esc(c.name)}</b><span>${esc(c.company || '')}</span></div>
      <div class="row-meta"><span>${STAGE_LABEL[c.stage] || c.stage}</span><span>score ${c.score}</span><span>${(c.lang || '').toUpperCase()}</span></div>
    </div>`).join('') || '<div class="empty">Нет клиентов</div>');
}
function renderDelivery(node, d) {
  const board = d.board || [], reports = d.reports || [];
  let html = '<div class="dsec">Сейчас на этом узле</div>';
  html += board.length ? board.map((c) => `
    <div class="row click" onclick="openContact(${c.id})">
      <div class="row-top"><b>${esc(c.name)}</b><span>${esc(c.company || '')}</span></div>
      <div class="row-msg">▸ ${esc(c.cur_step || '')}</div></div>`).join('') : '<div class="empty">Сейчас задач нет</div>';
  html += '<div class="dsec">Последние действия / отчёты</div>';
  html += reports.length ? reports.map((r) => `
    <div class="row"><div class="row-top"><b>${esc(r.contact_name || '—')}</b><span>${fmtTime(r.created_at)}</span></div>
      <div class="row-msg">${esc(r.summary)}${r.outcome === 'report' ? ' 📄' : ''}</div></div>`).join('') : '<div class="empty">Пока нет</div>';
  setDrawer(`${NODE_TITLE[node]} · в работе (${board.length})`, html);
}
function renderYou(d) {
  const ap = d.approvals || [];
  setDrawer(`ТЫ · согласование Проект+КП (${ap.length})`, ap.length ? ap.map((a) => `<div class="ap">${apCard(a)}</div>`).join('') : '<div class="empty">Очередь решений пуста ◢</div>');
}
function renderContact(d) {
  const c = d.contact || {}, it = d.interactions || [];
  const head = `<div class="row"><div class="row-top"><b>${esc(c.name)}</b><span>${esc(c.company || '')}${c.role ? ' · ' + esc(c.role) : ''}</span></div>
    <div class="row-meta"><span>${STAGE_LABEL[c.stage] || c.stage}</span><span>score ${c.score}</span><span>${(c.lang || '').toUpperCase()}</span><span>${esc(c.source || '')}</span></div></div>`;
  const tl = it.length ? `<div class="tl">${it.map((m) => `
    <div class="msg ${m.direction}"><div class="who">${m.direction === 'in' ? 'клиент' : esc(m.agent || 'AI')}<br>${fmtTime(m.created_at)}</div>
    <div class="body"><span class="ch">${CH_LABEL[m.channel] || m.channel} ${arrowOf(m.direction)}</span><br>${esc(m.summary)}</div></div>`).join('')}</div>` : '<div class="empty">Истории пока нет</div>';
  setDrawer(`КЛИЕНТ · ${esc(c.name || '#' + (c.id || ''))}`, head + '<div class="dsec">История</div>' + tl);
}

// ── Старт ─────────────────────────────────────────────────────────────────────
resize(); requestAnimationFrame(draw); connect();
