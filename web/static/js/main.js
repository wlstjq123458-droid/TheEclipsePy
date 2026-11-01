// 앱 시작 — 로그인, 틀(사이드바·헤더), 탭 전환, 다른 관리자의 변경 감지.
import {
  h, clear, icon, get, post, say, run, alertCard, modalOpen, setUnauthorizedHandler,
} from './core.js';
import { runChecks } from './dialogs.js';
import { createDashboard } from './dashboard.js';
import { createEquipment } from './equipment.js';
import { createCabinet } from './cabinet.js';
import { createData, createSangsangLab, createSettings } from './pages.js';

const root = document.getElementById('root');
const POLL_MS = 10000;

const NAV = [
  ['dashboard', 'home', '대시보드', '대시보드'], ['equipment', 'wrench', '기자재 현황', '기자재 현황'],
  ['cabinet', 'cabinet', '캐비닛 현황', '캐비닛 현황'], ['sangsanglab', 'bulb', '상상Lab 승인', '상상Lab 승인'],
  ['data', 'chart', '데이터 관리', '데이터 관리'], ['settings', 'gear', '설정', '설정'],
];

function loginPage(status) {
  const setup = status.setupRequired;
  const username = h('input', { type: 'text', value: 'admin', autocomplete: 'username' });
  const password = h('input', { type: 'password', autocomplete: setup ? 'new-password' : 'current-password' });
  const again = h('input', { type: 'password', autocomplete: 'new-password' });
  const err = h('div', { class: 'err' });
  const submit = run(async (e) => {
    e.preventDefault();
    err.textContent = '';
    if (setup && password.value !== again.value) { err.textContent = '두 비밀번호가 다릅니다.'; return; }
    const res = await fetch(setup ? '/api/auth/setup' : '/api/auth/login', {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'SeatManager' },
      body: JSON.stringify({ username: username.value, password: password.value }) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { err.textContent = data.error || data.detail || '로그인하지 못했습니다.'; return; }
    await start();
  });
  const form = setup && !status.local
    ? [h('p', null, '서버에서 관리자 비밀번호를 먼저 정해 주세요.'), h('code', null, 'python run_web.py --set-password')]
    : h('form', { onsubmit: submit }, !setup && [h('label', null, '아이디'), username],
      h('label', null, setup ? '새 비밀번호 (8자 이상)' : '비밀번호'), password,
      setup && [h('label', null, '비밀번호 확인'), again],
      err, h('button', { class: 'btn-modal', type: 'submit' }, setup ? '계정 만들기' : '로그인'));
  clear(root, h('div', { class: 'login-page' }, h('div', { class: 'login-card' },
    h('h1', null, '창공시스템'), h('p', null, setup ? '처음 실행입니다. 관리자 비밀번호를 정해 주세요.' : '동서대학교 좌석 및 기자재 관리 시스템'), form)));
  password.focus();
}

function createShell(boot) {
  const app = {
    boot, dragging: null, current: 'dashboard', rev: boot.rev, noticeId: null,
    viewKey: () => pages.dashboard.viewKey(),
    async switchTab(name) { await run(() => openTab(name))(); },
    async refresh() { await refreshAll(); },
    async refreshBadges() { await refreshBoot(); },
  };

  const navButtons = {};
  const sidebar = h('div', { class: 'sidebar' },
    h('div', { class: 'logo' }, h('b', null, 'DSU'), h('span', null, '동서대학교')),
    NAV.map(([name, ic, label]) => (navButtons[name] = h('button', { class: 'nav', onclick: () => app.switchTab(name) }, icon(ic, 16), label))));

  const title = h('h1', null, '대시보드');
  const chipLab = alertCard('bulb', '상상Lab 승인 대기', 'red', '승인 필요', () => app.switchTab('sangsanglab'));
  const chipCab = alertCard('cabinet', '캐비닛 승인 대기', 'orange', '승인 필요', () => app.switchTab('cabinet'));
  const chipEq = alertCard('wrench', '기자재 승인 대기', 'red', '승인 필요', () => app.switchTab('equipment'));
  const alerts = h('div', { class: 'alerts' }, chipLab, chipCab, chipEq);
  const dateLabel = h('span');
  const menu = h('div', { class: 'profile-menu', style: { display: 'none' } },
    h('button', { onclick: run(async () => { await post('/api/auth/logout', {}); await start(); }) }, '로그아웃'));
  const profile = h('div', { class: 'profile', onclick: (e) => { e.stopPropagation(); menu.style.display = menu.style.display === 'none' ? '' : 'none'; } },
    icon('user', 16), '관리자', h('small', null, ' ∨'), menu);
  document.addEventListener('click', () => { menu.style.display = 'none'; });
  const header = h('div', { class: 'header' }, title, alerts, h('div', { class: 'spacer' }), profile,
    h('div', { class: 'date-pill' }, icon('calendar', 13), dateLabel));
  const workspace = h('div', { class: 'workspace' });

  const pages = {
    dashboard: createDashboard(app), equipment: createEquipment(app), cabinet: createCabinet(app),
    sangsanglab: createSangsangLab(app), data: createData(app), settings: createSettings(app),
  };
  const holders = {};
  for (const [name, page] of Object.entries(pages)) {
    holders[name] = h('div', { class: `page${name === 'dashboard' || name === 'cabinet' ? '' : ' inset'}` }, page.el);
    workspace.append(holders[name]);
  }
  pages.dashboard.init(boot);

  clear(root, h('div', { class: 'shell' }, sidebar, h('div', { class: 'main' }, header, workspace)));

  function applyBoot(b) {
    app.boot = b;
    app.rev = b.rev;
    dateLabel.textContent = b.dateLabel;
    pages.dashboard.update(b);
    chipLab.setCount(b.counts.lab);
    chipCab.setCount(b.counts.cabinet);
    chipEq.setCount(b.counts.equipment);
    chipLab.style.display = b.counts.lab > 0 ? '' : 'none';
    chipCab.style.display = b.counts.cabinet > 0 ? '' : 'none';
    chipEq.style.display = b.counts.equipment > 0 ? '' : 'none';
  }

  async function refreshBoot() { applyBoot(await get('/api/bootstrap')); }

  async function refreshAll() {
    await refreshBoot();
    await pages[app.current].refresh();
  }

  async function openTab(name) {
    app.current = name;
    for (const [n, btn] of Object.entries(navButtons)) btn.classList.toggle('active', n === name);
    for (const [n, el] of Object.entries(holders)) el.classList.toggle('active', n === name);
    title.textContent = NAV.find(([n]) => n === name)[3];
    alerts.style.display = name === 'dashboard' ? '' : 'none';
    await refreshAll();
    if (name === 'dashboard') await runChecks('대시보드', app.viewKey(), app);
    else if (name === 'equipment') await runChecks('기자재', '', app);
    else if (name === 'cabinet') await runChecks('캐비닛', '', app);
  }

  // 다른 관리자의 변경이나 구글 폼 새 신청이 있으면 화면을 새로 읽는다 (작업 중이면 기다린다)
  const poll = async () => {
    try {
      const r = await fetch('/api/rev', { credentials: 'same-origin' });
      if (r.status === 401) { await start(); return; }
      const { rev, notice } = await r.json();
      const idle = !app.dragging && !modalOpen() && !pages[app.current].busy?.();
      if (notice && notice.id !== app.noticeId && app.noticeId !== null && idle) {
        app.noticeId = notice.id;
        await say(notice.message, notice.title, notice.level);
      } else if (app.noticeId === null) {
        app.noticeId = notice ? notice.id : 0;
      }
      if (rev !== app.rev && idle) await refreshAll();
    } catch (e) { /* 서버가 잠시 꺼져 있으면 다음 차례에 다시 시도한다 */ }
    if (root.contains(workspace)) setTimeout(poll, POLL_MS);
  };

  applyBoot(boot);
  run(() => openTab('dashboard'))();
  setTimeout(poll, POLL_MS);
  // 날짜·시즌은 자정에 바뀌므로 1분마다 다시 읽는다
  const dateTimer = setInterval(() => {
    if (!root.contains(workspace)) { clearInterval(dateTimer); return; }
    run(refreshBoot)();
  }, 60000);
  return app;
}

async function start() {
  const status = await (await fetch('/api/auth/status', { credentials: 'same-origin' })).json();
  if (!status.user) { loginPage(status); return; }
  createShell(await get('/api/bootstrap'));
}

setUnauthorizedHandler(() => { document.querySelectorAll('.overlay').forEach((o) => o.remove()); start(); });
start().catch((e) => { root.textContent = `서버에 연결할 수 없습니다: ${e.message}`; });
