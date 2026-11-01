// 화면 공용 도구 — DOM 만들기, 서버 호출, 확인창, 표(DataGrid), 모달.
// 학생 이름처럼 외부에서 들어온 글자는 h()의 글자 노드로만 넣는다 (HTML로 해석되지 않게).

export class Cancelled extends Error {}

export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') Object.assign(el.style, v);
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'value') el.value = v;
    else if (k === 'checked' || k === 'readOnly' || k === 'disabled' || k === 'draggable') el[k] = v;
    else el.setAttribute(k, v);
  }
  add(el, children);
  return el;
}

function add(el, children) {
  for (const c of children.flat()) {
    if (c === undefined || c === null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
}

export function clear(el, ...children) {
  el.replaceChildren();
  add(el, children);
  return el;
}

// ---------------------------------------------------------------- 아이콘 (WPF가 그리는 단색 윤곽선 모양)
const ICONS = {
  home: '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v10h13V10"/><path d="M10 20v-6h4v6"/>',
  wrench: '<path d="M14.7 6.3a4 4 0 0 0-5 5L4 17l3 3 5.7-5.7a4 4 0 0 0 5-5l-2.6 2.6-2.4-.6-.6-2.4z"/>',
  cabinet: '<rect x="5" y="3" width="14" height="18" rx="1"/><path d="M5 9h14M5 15h14M10 6h4M10 12h4M10 18h4"/>',
  bulb: '<path d="M9 17h6M10 20h4"/><path d="M8.5 14A6 6 0 1 1 15.5 14c-.7.7-1 1.5-1 3h-5c0-1.5-.3-2.3-1-3z"/>',
  chart: '<rect x="3" y="4" width="18" height="16" rx="1"/><path d="M8 16v-4M12 16V8M16 16v-6"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M18.4 5.6l-2.1 2.1M7.7 16.3l-2.1 2.1"/><circle cx="12" cy="12" r="7"/>',
  user: '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c1-4 4-6 7.5-6s6.5 2 7.5 6z"/>',
  calendar: '<rect x="4" y="5" width="16" height="15" rx="1"/><path d="M4 10h16M8 3v4M16 3v4"/>',
  search: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21" stroke-width="3"/>',
  download: '<path d="M12 4v10M8 10l4 4 4-4"/><path d="M4 15v4h16v-4"/>',
  upload: '<path d="M12 14V4M8 8l4-4 4 4"/><path d="M4 15v4h16v-4"/>',
  trash: '<path d="M5 7h14M9 7V4h6v3M7 7l1 13h8l1-13"/>',
  clipboard: '<rect x="5" y="5" width="14" height="16" rx="1"/><path d="M9 3h6v4H9zM8 11h8M8 15h8"/>',
  file: '<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4M9 12h6M9 16h6"/>',
  lock: '<rect x="5" y="11" width="14" height="10" rx="1"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
  unlock: '<rect x="5" y="11" width="14" height="10" rx="1"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l4 2"/>',
  refresh: '<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 3v5h-5"/>',
  folder: '<path d="M3 19V6h6l2 2h10v11z"/>',
  save: '<path d="M4 4h13l3 3v13H4z"/><path d="M8 4v6h8V4M8 20v-6h8v6"/>',
  video: '<rect x="3" y="7" width="13" height="10" rx="1"/><path d="m16 11 5-3v8l-5-3"/>',
  monitor: '<rect x="3" y="4" width="18" height="12" rx="1"/><path d="M9 20h6M12 16v4"/>',
  laptop: '<rect x="5" y="5" width="14" height="10" rx="1"/><path d="M2 19h20l-3-4H5z"/>',
  tools: '<path d="M14.7 6.3a4 4 0 0 0-5 5L4 17l3 3 5.7-5.7a4 4 0 0 0 5-5l-2.6 2.6-2.4-.6-.6-2.4z"/><path d="m4 4 5 5"/>',
  check: '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="m8 12 3 3 5-6"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5v.5"/>',
  warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v5M12 17.5v.5"/>',
  error: '<circle cx="12" cy="12" r="9"/><path d="m9 9 6 6M15 9l-6 6"/>',
  ask: '<circle cx="12" cy="12" r="9"/><path d="M9.5 9.5a2.5 2.5 0 1 1 3.7 2.2c-.8.5-1.2 1-1.2 2M12 16.8v.5"/>',
};

export function icon(name, size = 14, cls = '') {
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  el.setAttribute('viewBox', '0 0 24 24');
  el.setAttribute('width', size);
  el.setAttribute('height', size);
  el.setAttribute('class', `icon ${cls}`);
  el.innerHTML = ICONS[name] || '';   // 위 표의 고정된 값만 쓴다
  return el;
}

// ---------------------------------------------------------------- 메시지 상자
function messageBox(text, title, kind, buttons) {
  return new Promise((resolve) => {
    const iconName = { info: 'info', warning: 'warn', error: 'error', ask: 'ask' }[kind] || 'info';
    const color = { info: '#2563EB', warning: '#D97706', error: '#DC2626', ask: '#2563EB' }[kind] || '#2563EB';
    const done = (v) => { overlay.remove(); document.removeEventListener('keydown', onKey, true); resolve(v); };
    const onKey = (e) => {
      if (e.key === 'Escape') { e.stopPropagation(); done(buttons[buttons.length - 1].value); }
      if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); done(buttons[0].value); }
    };
    const overlay = h('div', { class: 'overlay msg-overlay' },
      h('div', { class: 'msgbox', role: 'dialog' },
        h('div', { class: 'bar' }, title || '알림'),
        h('div', { class: 'body' }, icon(iconName, 30), h('span', { style: { color: '#111827', alignSelf: 'center' } }, text)),
        h('div', { class: 'foot' }, buttons.map((b) => h('button', { class: 'btn-wpf', onclick: () => done(b.value) }, b.label)))));
    overlay.querySelector('.body svg').style.color = color;
    document.body.append(overlay);
    document.addEventListener('keydown', onKey, true);
    overlay.querySelector('.foot button').focus();
  });
}

export const say = (text, title = '알림', kind = 'info') => messageBox(text, title, kind, [{ label: '확인', value: true }]);
export const warn = (text, title = '알림') => say(text, title, 'warning');
export const ask = (text, title = '확인', isWarn = false) =>
  messageBox(text, title, isWarn ? 'warning' : 'ask', [{ label: '예', value: true }, { label: '아니요', value: false }]);

// ---------------------------------------------------------------- 서버 호출
let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => { onUnauthorized = fn; };

async function raw(method, url, options = {}) {
  let res;
  try {
    res = await fetch(url, { method, credentials: 'same-origin', ...options,
      headers: { 'X-Requested-With': 'SeatManager', ...(options.headers || {}) } });
  } catch (e) {
    await say('서버에 연결할 수 없습니다. 서버가 켜져 있는지 확인해 주세요.', '연결 오류', 'error');
    throw new Cancelled();
  }
  if (res.status === 401) { onUnauthorized(); throw new Cancelled(); }
  return res;
}

async function readJson(res) {
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    await say(data.error || data.detail || '요청을 처리하지 못했습니다.', data.title || '오류', data.level || 'error');
    throw new Cancelled();
  }
  return data;
}

export const get = async (url) => readJson(await raw('GET', url));

function json(method, url, body) {
  return raw(method, url, { body: JSON.stringify(body), headers: { 'Content-Type': 'application/json' } });
}

const choosers = {};
export const registerChooser = (kind, fn) => { choosers[kind] = fn; };

// 서버가 확인이나 선택을 요구하면 답을 받아 같은 요청을 다시 보낸다
async function converse(send, body) {
  const data = { ...body, confirmed: [...(body.confirmed || [])] };
  for (;;) {
    const r = await readJson(await send(data));
    if (r.need === 'confirm') {
      if (!(await ask(r.message, r.title, r.warn))) throw new Cancelled();
      data.confirmed.push(r.key);
    } else if (r.need === 'choose') {
      const picked = await choosers[r.kind](r.data);
      if (picked === null || picked === undefined) throw new Cancelled();
      Object.assign(data, picked);
    } else {
      if (r.message) await say(r.message, r.title);
      return r;
    }
  }
}

export const post = (url, body = {}) => converse((d) => json('POST', url, d), body);
export const put = (url, body = {}) => converse((d) => json('PUT', url, d), body);
export const del = async (url) => readJson(await raw('DELETE', url));

export function pickFile(accept) {
  return new Promise((resolve) => {
    const input = h('input', { type: 'file', accept, style: { display: 'none' } });
    input.addEventListener('change', () => { resolve(input.files[0] || null); input.remove(); });
    input.addEventListener('cancel', () => { resolve(null); input.remove(); });
    document.body.append(input);
    input.click();
  });
}

export function upload(url, file, query = {}) {
  return converse((d) => {
    const params = new URLSearchParams({ ...query, confirmed: d.confirmed.join(',') });
    return raw('POST', `${url}?${params}`, { body: file, headers: { 'X-Filename': encodeURIComponent(file.name), 'Content-Type': 'application/octet-stream' } });
  }, {});
}

export async function download(url) {
  const res = await raw('GET', url);
  if (!res.ok) { await readJson(res); return; }
  const header = res.headers.get('Content-Disposition') || '';
  const match = header.match(/filename\*=UTF-8''([^;]+)/);
  const a = h('a', { href: URL.createObjectURL(await res.blob()), download: match ? decodeURIComponent(match[1]) : 'download.xlsx' });
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(a.href), 10000);
}

// 버튼 동작을 감싼다 — 사용자가 취소하면 조용히 끝내고, 예상 못 한 오류는 알려 준다
export function run(fn) {
  return async (...args) => {
    try {
      return await fn(...args);
    } catch (e) {
      if (!(e instanceof Cancelled)) { console.error(e); await say(String(e.message || e), '오류', 'error'); }
    }
  };
}

// ---------------------------------------------------------------- 버튼 모음
export function actionBtn(label, onclick, opts = {}) {
  return h('button', { class: `btn-action ${opts.cls || ''}`, onclick: run(onclick) }, opts.icon && icon(opts.icon, opts.iconSize || 14), label);
}
export function flatBtn(label, color, onclick, opts = {}) {
  return h('button', { class: `btn-flat ${opts.cls || ''}`, style: { background: color, ...(opts.style || {}) }, onclick: run(onclick), disabled: opts.disabled }, label);
}
export function modalBtn(label, onclick, opts = {}) {
  return h('button', { class: `btn-modal ${opts.cls || ''}`, style: opts.style, onclick: run(onclick) }, opts.icon && icon(opts.icon, 14), label);
}
export function alertCard(iconName, title, color, sub, onclick) {
  const count = h('div', { class: 'c' }, '0건');
  const el = h('div', { class: `alert-card ${color}`, onclick }, icon(iconName, 24),
    h('div', null, h('div', { class: 't' }, title), count, h('div', { class: 's' }, sub)));
  el.setCount = (n) => { count.textContent = `${n}건`; };
  return el;
}

// ---------------------------------------------------------------- 표 (WPF DataGrid와 같은 동작)
// cols: {header, width, stretch, minWidth, text(row), cell(row), widget}
// 다시 누르면 선택 해제, multi면 Ctrl/Shift 다중 선택, details(row)는 선택한 줄 아래에 펼친다.
export function dataGrid({ cols, rowId = (r) => r.id, rowHeight = 40, alternating, fontSize = 12, details, multi, onSelect, onDouble, headerHeight }) {
  const table = h('table', { style: { fontSize: `${fontSize}px` } });
  const wrap = h('div', { class: 'grid' }, table);
  const hasStretch = cols.some((c) => c.stretch);
  const colgroup = h('colgroup', null, cols.map((c) => h('col', { style: c.stretch ? { minWidth: `${c.minWidth || 0}px` } : { width: `${c.width}px` } })),
    !hasStretch && h('col'));
  const headRow = h('tr', null, cols.map((c) => h('th', { style: headerHeight ? { height: `${headerHeight}px` } : null }, c.header)), !hasStretch && h('th', { style: { borderRight: 0 } }));
  table.append(colgroup, h('thead', null, headRow));
  const tbody = h('tbody');
  table.append(tbody);
  if (hasStretch) {
    const min = cols.reduce((sum, c) => sum + (c.stretch ? (c.minWidth || 60) : c.width), 0);
    table.style.minWidth = `${min}px`;
  }

  let rows = [];
  let selected = new Set();
  let anchor = null;

  function render() {
    tbody.replaceChildren();
    rows.forEach((row, i) => {
      const id = rowId(row);
      const isSel = selected.has(id);
      const tr = h('tr', { class: isSel ? 'sel' : '', style: { height: `${rowHeight}px` },
        onmousedown: (e) => { if (e.detail > 1) e.preventDefault(); },
        onclick: (e) => click(e, row, id), ondblclick: () => onDouble && onDouble(row) });
      if (alternating && i % 2 === 1) tr.style.background = alternating;
      else tr.style.background = '#fff';
      for (const c of cols) {
        if (c.cell) tr.append(h('td', { class: 'widget', style: { height: `${rowHeight}px` }, onclick: c.passClick ? null : (e) => { if (e.target.closest('button')) e.stopPropagation(); } }, c.cell(row)));
        else {
          const text = c.text(row) ?? '';
          tr.append(h('td', { title: String(text) }, text));
        }
      }
      if (!hasStretch) tr.append(h('td', { class: 'filler' }));
      tbody.append(tr);
      if (details && isSel) {
        tbody.append(h('tr', { class: 'detail' }, h('td', { colspan: cols.length + (hasStretch ? 0 : 1) }, details(row))));
      }
    });
  }

  function click(e, row, id) {
    if (e.target.closest('button')) return;
    const additive = multi && (e.ctrlKey || e.metaKey);
    if (multi && e.shiftKey && anchor !== null) {
      const ids = rows.map(rowId);
      const [a, b] = [ids.indexOf(anchor), ids.indexOf(id)].sort((x, y) => x - y);
      selected = new Set(ids.slice(a, b + 1));
    } else if (additive) {
      if (selected.has(id)) selected.delete(id); else selected.add(id);
      anchor = id;
    } else if (selected.has(id)) {
      selected = new Set();   // 이미 선택된 줄을 다시 누르면 선택을 푼다
      anchor = null;
    } else {
      selected = new Set([id]);
      anchor = id;
    }
    render();
    onSelect && onSelect(current());
  }

  const current = () => rows.find((r) => selected.has(rowId(r))) || null;

  return {
    el: wrap,
    setRows(next) {
      rows = next;
      const ids = new Set(rows.map(rowId));
      selected = new Set([...selected].filter((id) => ids.has(id)));
      render();
    },
    selectedRows: () => rows.filter((r) => selected.has(rowId(r))),
    current,
    clearSelection() { selected = new Set(); render(); },
    select(id) { selected = new Set([id]); render(); },
  };
}

// ---------------------------------------------------------------- 모달
const modalStack = [];
export const modalOpen = () => modalStack.length > 0 || document.querySelector('.msg-overlay, .dialog-overlay') !== null;

export function modal({ width, height, padding = 35 }) {
  const box = h('div', { class: 'modal', style: { width: `${width}px`, height: height ? `${height}px` : null, padding: `${padding}px` } });
  const overlay = h('div', { class: 'overlay' }, box);
  const close = () => {
    overlay.remove();
    modalStack.splice(modalStack.indexOf(overlay), 1);
    document.removeEventListener('keydown', onKey);
  };
  const onKey = (e) => { if (e.key === 'Escape' && modalStack[modalStack.length - 1] === overlay && !document.querySelector('.msg-overlay, .dialog-overlay')) close(); };
  modalStack.push(overlay);
  document.body.append(overlay);
  document.addEventListener('keydown', onKey);
  return { box, close };
}

export const closeButton = (size, onclick, style) =>
  h('button', { class: 'btn-x x', style, onclick, title: '닫기' }, icon('close', size));

// 데스크톱의 작은 별도 창(대화상자) 모양
export function dialog({ title, width, build }) {
  return new Promise((resolve) => {
    const done = (v) => { overlay.remove(); document.removeEventListener('keydown', onKey, true); resolve(v); };
    const onKey = (e) => { if (e.key === 'Escape') { e.stopPropagation(); done(null); } };
    const content = h('div', { class: 'content' });
    const overlay = h('div', { class: 'overlay dialog-overlay' },
      h('div', { class: 'dialog', style: { width: `${width}px` } }, h('div', { class: 'bar' }, title), content));
    build(content, done);
    document.body.append(overlay);
    document.addEventListener('keydown', onKey, true);
  });
}

export const line = (text, labelWidth, control) =>
  h('div', { class: 'line' }, h('span', { style: { width: `${labelWidth}px` } }, text), control);
