/* pibo-connector — 화면. 의존성 0, CDN 0. 오프라인에서 그대로 돈다. */
'use strict';

const TOKEN = new URLSearchParams(location.search).get('token') || '';
const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));

/* ── 사전 ─────────────────────────────────────────────────────────── */
const EN = {
  find: 'FIND', scan: 'Scan', refresh: 'Re-check', apscan: 'Find AP mode',
  find_note: 'Sweeps .1–.254 of the subnet. 15 robots usually take 3–8 s.',
  roster: 'ROLL CALL', roster_edit: 'Edit expected SN list', save: 'Save',
  roster_note: 'Only 8-hex-digit SNs are picked up. Any separator works.',
  list: 'FLEET', select_all: 'Select all', export: 'Export', import: 'Import',
  rules: 'Detection rules', kind: 'Kind', sn: 'SN', name: 'Name', ip: 'IP',
  os: 'OS_VERSION', temp: 'Temp', status: 'Status', seen: 'Last seen',
  empty: 'No robots yet. Hit [Scan].',
  code: 'CODE', run: 'Run', sync: 'Run in sync', stop: 'Stop',
  warn_shared: '⚠ Running stops tools · classify · llama-server on the robot. ' +
    'LLM code must call Dialog.start_llm first. The IDE console is global: output ' +
    'also shows in a teacher browser, and anyone hitting Run in the IDE kills this code.',
  warn_sync: 'Sync run: heavy imports finish first, then one UDP trigger releases ' +
    'everyone at once. Split the code with # --- GO --- — above is setup, below is the ' +
    'real thing. If the router blocks broadcast the trigger never arrives and it ends in [timeout].',
  output: 'OUTPUT',
  out_empty: 'Per-robot last line shows here. Click a line to expand the full log.',
};
let LANG = new URLSearchParams(location.search).get('lang') === 'en' ? 'en' : 'ko';
const KO = {};

function captureKo() {
  $$('[data-t]').forEach((el) => { KO[el.dataset.t] = el.innerHTML; });
}
function applyLang() {
  const dict = LANG === 'en' ? EN : KO;
  $$('[data-t]').forEach((el) => {
    const v = dict[el.dataset.t];
    if (v !== undefined) el.innerHTML = v;
  });
  $('#lang').textContent = LANG === 'en' ? '한국어' : 'EN';
  document.documentElement.lang = LANG;
  render();
}
const T = (ko, en) => (LANG === 'en' ? en : ko);

/* ── 상태 ─────────────────────────────────────────────────────────── */
let fleet = [];          // [{sn, name, ip, kind, os, temp, mode, ...}]
let roster = null;
let selected = new Set();
let outputs = {};        // sn -> {state, tail, open, full}
let busy = false;

/* ── API ──────────────────────────────────────────────────────────── */
async function api(path, body) {
  const url = path + (TOKEN ? (path.includes('?') ? '&' : '?') + 'token=' + TOKEN : '');
  const opt = { headers: { 'content-type': 'application/json' } };
  if (TOKEN) opt.headers['x-token'] = TOKEN;
  if (body !== undefined) { opt.method = 'POST'; opt.body = JSON.stringify(body); }
  const r = await fetch(url, opt);
  const text = await r.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch (e) { data = { detail: text }; }
  if (!r.ok) throw new Error((data && (data.detail || data.message)) || r.statusText);
  return data;
}

/* ── WebSocket ────────────────────────────────────────────────────── */
let ws = null, wsTimer = null;
function connect() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  ws = new WebSocket(`${proto}://${location.host}/ws${TOKEN ? '?token=' + TOKEN : ''}`);
  ws.onopen = () => { $('#conn').classList.add('on'); };
  ws.onclose = () => {
    $('#conn').classList.remove('on');
    clearTimeout(wsTimer);
    wsTimer = setTimeout(connect, 1500);
  };
  ws.onmessage = (e) => {
    let m; try { m = JSON.parse(e.data); } catch (_) { return; }
    handle(m);
  };
}

function handle(m) {
  switch (m.type) {
    case 'hello':
      $('#ver').textContent = 'v' + m.version;
      if (!$('#subnet').value && m.subnets && m.subnets.length) {
        $('#subnet').value = m.subnets[0];
      }
      fleet = m.fleet || []; roster = m.roster || null; busy = !!m.busy;
      render();
      break;
    case 'fleet':
      fleet = m.robots || fleet;
      if (m.roster) roster = m.roster;
      render();
      break;
    case 'scan':
      if (m.phase === 'found' && m.robot) {
        upsertLocal(m.robot);
        render();
      } else if (m.total) {
        const pct = Math.round((m.done / m.total) * 100);
        $('#scan-bar').style.width = pct + '%';
        const label = m.phase === 'port' ? T('포트 확인', 'probing')
          : m.phase === 'identify' ? T('기기 확인', 'identifying')
            : T('다시 확인', 're-checking');
        $('#scan-msg').textContent = `${label} ${m.done}/${m.total}` +
          (m.found ? ` · ${m.found}` + T('대 응답', ' up') : '');
      }
      break;
    case 'run':
      outputs[m.sn] = Object.assign(outputs[m.sn] || {}, {
        state: m.state,
        tail: m.tail !== undefined ? m.tail : (outputs[m.sn] || {}).tail,
      });
      renderOut();
      break;
    case 'output':
      outputs[m.sn] = Object.assign(outputs[m.sn] || {}, { tail: m.tail, len: m.len });
      if ((outputs[m.sn] || {}).open) loadFull(m.sn);
      renderOut();
      break;
    case 'job':
      if (m.state === 'start') {
        busy = true;
        outputs = {};
        (m.targets || []).forEach((sn) => { outputs[sn] = { state: 'pending', tail: '' }; });
      }
      if (m.state === 'end' || m.state === 'stopped') busy = false;
      if (m.state === 'trigger') {
        $('#run-msg').textContent = T(
          `트리거 발사 → ${(m.sent_to || []).join(', ')}` +
          ((m.not_ready || []).length ? ` · 준비 안 된 로봇 ${m.not_ready.length}대` : ''),
          `trigger sent → ${(m.sent_to || []).join(', ')}` +
          ((m.not_ready || []).length ? ` · ${m.not_ready.length} not ready` : ''));
      }
      if (m.state === 'end') {
        $('#run-msg').textContent = T(`끝 · ${m.elapsed}초`, `done · ${m.elapsed}s`);
      }
      if (m.state && m.state !== 'end') {
        const label = { start: T('시작', 'start'), running: T('실행 중', 'running'),
          preparing: T('준비 중 (import)', 'preparing'), stopped: T('정지', 'stopped') }[m.state];
        if (label) $('#run-msg').textContent = label;
      }
      renderButtons();
      break;
  }
}

function upsertLocal(row) {
  const i = fleet.findIndex((r) => r.sn === row.sn);
  if (i >= 0) fleet[i] = Object.assign({}, fleet[i], row);
  else fleet.push(row);
}

/* ── 렌더 ─────────────────────────────────────────────────────────── */
function kindBadge(r) {
  const k = r.kind || 'unknown';
  const label = k === 'pibo' ? 'Pibo' : k === 'pibrain' ? 'PiBrain' : '?';
  const low = r.kind_confidence !== 'high' ? ' low' : '';
  const ev = (r.kind_evidence || '').replace(/"/g, '&quot;');
  return `<span class="badge ${k}${low}" title="${ev}">${label}</span>`;
}

function modeLabel(r) {
  if (r.mode === 'ap') return `<span class="state ready">AP</span>`;
  if (r.mode === 'offline') return `<span class="state error">${T('응답 없음', 'no reply')}</span>`;
  const st = (outputs[r.sn] || {}).state;
  if (st) return `<span class="state ${st}">${st}</span>`;
  return `<span class="state done">${T('접속', 'up')}</span>`;
}

function render() {
  const tb = $('#tbody');
  tb.innerHTML = fleet.map((r) => {
    const off = r.mode === 'ap' || r.mode === 'offline' || !r.ip;
    return `<tr class="${off ? 'off' : ''}" data-sn="${r.sn}">
      <td><input type="checkbox" class="pick" data-sn="${r.sn}"
           ${selected.has(r.sn) ? 'checked' : ''} ${r.ip ? '' : 'disabled'}></td>
      <td>${kindBadge(r)}</td>
      <td class="mono">${r.sn}</td>
      <td><input class="name-edit" data-sn="${r.sn}" value="${(r.name || '').replace(/"/g, '&quot;')}"
           placeholder="${T('이름', 'name')}"></td>
      <td class="mono">${r.ip || '—'}</td>
      <td class="mono hide-s" title="${(r.kind_evidence || '')}">${r.os || '—'}</td>
      <td class="mono hide-s">${r.temp || '—'}</td>
      <td>${modeLabel(r)}</td>
      <td class="hide-s note">${(r.last_seen || '').slice(5, 16)}</td>
      <td><button class="small del" data-sn="${r.sn}" title="${T('목록에서 지움', 'remove')}">×</button></td>
    </tr>`;
  }).join('');
  $('#empty').style.display = fleet.length ? 'none' : '';
  $('#sel-count').textContent = selected.size
    ? T(`${selected.size}대 선택`, `${selected.size} selected`) : '';
  renderRoster();
  renderButtons();
}

function renderRoster() {
  if (!roster) { $('#roster-sum').innerHTML = ''; return; }
  const up = (roster.present || []).length;
  const ap = (roster.ap || []).length;
  const miss = roster.missing || [];
  const extra = roster.extra || [];
  if (!roster.expected) {
    $('#roster-sum').innerHTML =
      `<span class="note">${T('기대 SN 목록을 넣으면 점호가 된다.',
        'Add an expected SN list to get a roll call.')}</span>`;
    return;
  }
  $('#roster-sum').innerHTML =
    `<span><b class="ok">${up}</b> / ${roster.expected} ${T('접속', 'up')}</span>` +
    (ap ? `<span><b class="warn">${ap}</b> ${T('AP 모드', 'AP mode')}
       <span class="mono note">${roster.ap.join(' ')}</span></span>` : '') +
    (miss.length ? `<span><b class="bad">${miss.length}</b> ${T('미확인', 'missing')}
       <span class="mono note">${miss.join(' ')}</span></span>` : '') +
    (extra.length ? `<span class="note">${T('목록 밖', 'extra')}
       <span class="mono">${extra.join(' ')}</span></span>` : '');
}

function renderButtons() {
  const has = selected.size > 0;
  $('#btn-run').disabled = busy || !has;
  $('#btn-sync').disabled = busy || !has;
  $('#btn-scan').disabled = busy;
  $('#btn-refresh').disabled = busy;
}

function renderOut() {
  const sns = Object.keys(outputs);
  $('#out-empty').style.display = sns.length ? 'none' : '';
  $('#out').innerHTML = sns.map((sn) => {
    const o = outputs[sn] || {};
    const r = fleet.find((x) => x.sn === sn) || {};
    const nm = r.name ? `${r.name} · ` : '';
    return `<div class="item" data-sn="${sn}">
      <div class="head">
        <span class="mono">${nm}${sn}</span>
        <span class="state ${o.state || ''}">${o.state || ''}</span>
        <span class="note">${r.ip || ''}</span>
      </div>
      <div class="tail">${esc(o.tail || '')}</div>
      ${o.open ? `<pre>${esc(o.full || T('불러오는 중…', 'loading…'))}</pre>` : ''}
    </div>`;
  }).join('');
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

async function loadFull(sn) {
  try {
    const d = await api(`/api/output/${sn}`);
    outputs[sn] = Object.assign(outputs[sn] || {}, { full: d.record || '' });
    renderOut();
  } catch (e) { /* 실행 전이면 없을 수 있다 */ }
}

/* ── 동작 ─────────────────────────────────────────────────────────── */
function targets() { return Array.from(selected); }

function msg(el, text, cls) {
  const n = $(el);
  n.textContent = text;
  n.className = 'note' + (cls ? ' ' + cls : '');
}

async function guard(el, fn) {
  try { await fn(); } catch (e) { msg(el, '!! ' + e.message, 'bad'); }
}

$('#btn-scan').onclick = () => guard('#scan-msg', async () => {
  msg('#scan-msg', T('훑는 중…', 'scanning…'));
  $('#scan-bar').style.width = '0';
  const d = await api('/api/scan', { subnet: $('#subnet').value.trim() });
  $('#scan-bar').style.width = '100%';
  msg('#scan-msg', T(`${d.found}대 찾음`, `${d.found} found`), 'ok');
});

$('#btn-refresh').onclick = () => guard('#scan-msg', async () => {
  msg('#scan-msg', T('확인 중…', 're-checking…'));
  const d = await api('/api/refresh', {});
  $('#scan-bar').style.width = '100%';
  msg('#scan-msg', T(`${d.ok.length}대 그대로` + (d.lost.length ? `, ${d.lost.length}대 응답 없음` : ''),
    `${d.ok.length} unchanged` + (d.lost.length ? `, ${d.lost.length} not replying` : '')),
    d.lost.length ? 'warn' : 'ok');
});

$('#btn-apscan').onclick = () => guard('#scan-msg', async () => {
  msg('#scan-msg', T('전파 스캔 중…', 'scanning air…'));
  const d = await api('/api/apscan', {});
  const n = (d.found || []).length;
  let s = n
    ? T(`AP 모드 ${n}대: ` + d.found.map((f) => f.sn).join(' '),
      `${n} in AP mode: ` + d.found.map((f) => f.sn).join(' '))
    : T('AP 모드 로봇 없음 (전부 공유기에 붙었다)', 'none in AP mode');
  if (d.stale) s += T('  ※ 로봇의 캐시된 스캔 결과라 참고용',
    '  ※ cached scan from a robot — reference only');
  if (d.error) s += '  (' + d.error + ')';
  msg('#scan-msg', s, n ? 'warn' : 'ok');
});

$('#btn-roster').onclick = () => guard('#scan-msg', async () => {
  const d = await api('/api/roster', { sns: $('#roster-text').value });
  roster = d.status;
  renderRoster();
  msg('#scan-msg', T(`기대 ${d.roster.length}대 저장`, `saved ${d.roster.length} expected`), 'ok');
});

$('#chk-all').onchange = (e) => {
  selected = new Set(e.target.checked ? fleet.filter((r) => r.ip).map((r) => r.sn) : []);
  render();
};

$('#tbody').addEventListener('change', (e) => {
  if (e.target.classList.contains('pick')) {
    const sn = e.target.dataset.sn;
    if (e.target.checked) selected.add(sn); else selected.delete(sn);
    $('#sel-count').textContent = selected.size
      ? T(`${selected.size}대 선택`, `${selected.size} selected`) : '';
    renderButtons();
  }
});

$('#tbody').addEventListener('blur', async (e) => {
  if (e.target.classList.contains('name-edit')) {
    await api('/api/rename', { sn: e.target.dataset.sn, name: e.target.value });
  }
}, true);

$('#tbody').addEventListener('keydown', (e) => {
  if (e.target.classList.contains('name-edit') && e.key === 'Enter') e.target.blur();
});

$('#tbody').addEventListener('click', async (e) => {
  if (e.target.classList.contains('del')) {
    const sn = e.target.dataset.sn;
    if (!confirm(T(`${sn} 를 목록에서 지운다`, `Remove ${sn} from the list`))) return;
    await api('/api/remove', { sn });
    selected.delete(sn);
  }
});

$('#out').addEventListener('click', (e) => {
  const item = e.target.closest('.item');
  if (!item) return;
  const sn = item.dataset.sn;
  const o = outputs[sn] = outputs[sn] || {};
  o.open = !o.open;
  if (o.open) loadFull(sn);
  renderOut();
});

$('#file').onchange = (e) => {
  const f = e.target.files[0];
  if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    $('#code').value = rd.result;
    if (f.name.endsWith('.sh')) $('#codetype').value = 'shell';
  };
  rd.readAsText(f, 'utf-8');
};

$('#btn-run').onclick = () => guard('#run-msg', async () => {
  msg('#run-msg', T('던지는 중…', 'sending…'));
  await api('/api/run', {
    targets: targets(), code: $('#code').value, codetype: $('#codetype').value,
  });
});

$('#btn-sync').onclick = () => guard('#run-msg', async () => {
  msg('#run-msg', T('준비 중…', 'preparing…'));
  await api('/api/sync', { targets: targets(), code: $('#code').value });
});

$('#btn-stop').onclick = () => guard('#run-msg', async () => {
  await api('/api/stop', { targets: targets() });
  busy = false;
  renderButtons();
});

$('#btn-export').onclick = () => guard('#scan-msg', async () => {
  const d = await api('/api/export');
  const blob = new Blob([JSON.stringify(d, null, 1)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'pibo-fleet.json';
  a.click();
  URL.revokeObjectURL(a.href);
});

$('#btn-import').onclick = () => {
  const inp = document.createElement('input');
  inp.type = 'file'; inp.accept = '.json';
  inp.onchange = () => {
    const f = inp.files[0]; if (!f) return;
    const rd = new FileReader();
    rd.onload = () => guard('#scan-msg', async () => {
      const d = await api('/api/import', { payload: JSON.parse(rd.result), merge: true });
      msg('#scan-msg', T(`${d.imported}대 가져옴`, `${d.imported} imported`), 'ok');
    });
    rd.readAsText(f, 'utf-8');
  };
  inp.click();
};

$('#btn-rules').onclick = () => guard('#scan-msg', async () => {
  const d = await api('/api/rules');
  const cur = JSON.stringify(d.rules.os_contains, null, 1);
  const next = prompt(T(
    'OS_VERSION 판별 규칙 (조각 → 기종). 긴 조각을 먼저 본다.\n' +
    '값은 pibo 또는 pibrain.',
    'OS_VERSION rules (fragment → kind). Longer fragments win.\nValue is pibo or pibrain.'), cur);
  if (next === null) return;
  const parsed = JSON.parse(next);
  await api('/api/rules', { rules: Object.assign({}, d.rules, { os_contains: parsed }) });
  msg('#scan-msg', T('규칙 저장 · 목록 다시 매김', 'rules saved · fleet reclassified'), 'ok');
});

$('#lang').onclick = () => {
  LANG = LANG === 'en' ? 'ko' : 'en';
  const u = new URL(location.href);
  if (LANG === 'en') u.searchParams.set('lang', 'en'); else u.searchParams.delete('lang');
  history.replaceState(null, '', u);
  applyLang();
};

/* ── 시작 ─────────────────────────────────────────────────────────── */
captureKo();
applyLang();
connect();
api('/api/fleet').then((d) => {
  fleet = d.robots || [];
  roster = d.roster;
  $('#roster-text').value = (d.roster_list || []).join(' ');
  render();
}).catch(() => {});
setInterval(() => { if (ws && ws.readyState === 1) ws.send('ping'); }, 20000);
