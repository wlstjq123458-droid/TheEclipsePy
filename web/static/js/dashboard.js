// [대시보드] — 연도/학기 조회, 좌석 배치도(드래그로 이동), 고정·삭제 모드, 메모.
import {
  h, clear, icon, get, post, put, del, warn, run, modal, actionBtn, flatBtn, pickFile, upload, download,
} from './core.js';
import { studentSelector } from './dialogs.js';

const maskId = (id) => {
  if (!id) return id;
  if (id.length === 8) return `${id.slice(0, 2)}****${id.slice(6)}`;
  if (id.length <= 2) return id;
  const hide = Math.min(4, id.length - 2);
  const start = Math.floor((id.length - hide) / 2);
  return id.slice(0, start) + '*'.repeat(hide) + id.slice(start + hide);
};
const maskName = (name) => {
  if (!name || name.length < 2) return name;
  const mid = Math.floor(name.length / 2);
  return `${name.slice(0, mid)}*${name.slice(mid + 1)}`;
};

export function createDashboard(app) {
  const state = { fixMode: false, deleteMode: false, mask: false, selected: new Set(), seats: [], editingMemo: null };
  const page = h('div', { class: 'dash' });

  const year = h('select');
  const semester = h('select', { class: 'sem' });
  const pill = h('div', { class: 'season-pill' }, '현재 시즌 판별 중');
  const grid = h('div', { class: 'seat-grid' });
  const memoList = h('div', { class: 'memo-list' });
  const memoText = h('textarea');
  const memoAdd = flatBtn('+ 메모 추가', '#2563EB', () => addMemo(), { cls: 'memo-add' });

  const key = () => `${year.value}_${semester.value}`;
  const refresh = async () => { renderSeats(await get(`/api/seats?key=${encodeURIComponent(key())}`)); };

  const btnFix = actionBtn('좌석 고정 모드', () => toggleFix());
  const btnDeleteMode = actionBtn('좌석 데이터 삭제', () => deleteMenu());
  const btnMask = actionBtn('정보 가리기', () => toggleMask(), { icon: 'lock' });
  const btnDeleteSelected = flatBtn('선택된 좌석 삭제', '#EF4444', () => deleteSelected(), { style: { padding: '8px 15px', borderRadius: '6px', display: 'none' } });
  const actions = h('div', { class: 'actions' },
    actionBtn('랜덤 배정', async () => { await post('/api/seats/random', { key: key() }); await app.refresh(); }),
    btnFix, btnDeleteMode,
    actionBtn('좌석데이터 불러오기', loadFile, { icon: 'download' }),
    btnMask,
    actionBtn('엑셀 내보내기', () => download(`/api/seats/export?key=${encodeURIComponent(key())}`), { icon: 'upload' }),
    actionBtn('모두 삭제', deleteAll, { icon: 'trash', cls: 'danger' }),
    btnDeleteSelected);

  page.append(
    h('div', { class: 'dash-left' },
      h('div', { class: 'toolbar' },
        h('div', { class: 'season-panel' }, '년도', year, '학기', semester,
          h('button', { class: 'btn-flat go', style: { padding: '6px 15px' }, onclick: run(refresh) }, icon('search', 13), ' 조회'), pill),
        actions),
      h('div', { class: 'seat-scroll' }, h('div', { class: 'seat-card-wrap' }, grid))),
    h('div', { class: 'memo-panel' }, h('h2', null, '메모'), memoList, memoText, memoAdd));

  // -------------------------------------------------------------- 좌석
  function renderSeats(data) {
    state.seats = data.seats;
    const byNo = new Map(data.seats.map((s) => [s.n, s]));
    clear(grid, app.boot.positions.map(([n, row, col, span, gray]) => {
      const place = { gridRow: row + 1, gridColumn: `${col + 1} / span ${span}` };
      if (n === -1) return h('div', { class: 'pillar', style: place }, '기둥');
      return seatCard(byNo.get(n), gray, place);
    }));
    renderMemos(data.memos);
  }

  function seatCard(seat, gray, place) {
    const stu = seat.student;
    const cls = ['seat', gray && 'gray', state.selected.has(seat.n) ? 'selected' : (seat.locked && 'locked')].filter(Boolean).join(' ');
    const el = h('div', { class: cls, style: place, draggable: !state.fixMode && !state.deleteMode && !!stu, onclick: () => clickSeat(seat) },
      h('div', { class: 'num' }, seat.n, seat.locked && h('span', { style: { marginLeft: '3px', color: '#000' } }, icon('lock', 9))),
      stu && h('div', { class: 'who' },
        h('div', { class: 'sid' }, state.mask ? maskId(stu.studentId) : stu.studentId),
        h('div', { class: 'name' }, state.mask ? maskName(stu.name) : stu.name)));

    el.addEventListener('dragstart', (e) => {
      if (seat.locked) { e.preventDefault(); showLocked(); return; }
      e.dataTransfer.setData('application/x-seat', String(seat.n));
      e.dataTransfer.effectAllowed = 'move';
      app.dragging = seat.n;
      setTimeout(() => el.classList.add('dragging'));
    });
    el.addEventListener('dragend', () => { el.classList.remove('dragging'); app.dragging = null; });
    el.addEventListener('dragover', (e) => {
      if (!app.dragging || app.dragging === seat.n) return;
      e.preventDefault();
      el.classList.add(seat.locked ? 'drop-red' : 'drop-blue');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop-red', 'drop-blue'));
    el.addEventListener('drop', run(async (e) => {
      e.preventDefault();
      el.classList.remove('drop-red', 'drop-blue');
      const src = Number(e.dataTransfer.getData('application/x-seat'));
      if (!src || src === seat.n) return;
      await post('/api/seats/drop', { key: key(), src, dst: seat.n });
      await app.refresh();
    }));
    return el;
  }

  const showLocked = () => warn('고정된 좌석은 이동하거나 교체할 수 없습니다.\n자리를 옮기려면 먼저 [좌석 고정 모드]에서 고정을 해제해 주세요.', '고정된 좌석');

  function clickSeat(seat) {
    if (state.fixMode || state.deleteMode) {
      if (state.selected.has(seat.n)) state.selected.delete(seat.n); else state.selected.add(seat.n);
      btnDeleteSelected.style.display = state.deleteMode && state.selected.size ? '' : 'none';
      renderSeats({ seats: state.seats, memos: state.memos });
      return;
    }
    run(() => openSeatModal(seat.n))();
  }

  async function openSeatModal(number) {
    const detail = await get(`/api/seats/detail?key=${encodeURIComponent(key())}&number=${number}`);
    seatModal(app, { number, key: key(), student: detail.student, cabinet: detail.cabinet });
  }

  // -------------------------------------------------------------- 모드
  async function toggleFix() {
    if (state.deleteMode) {
      state.deleteMode = false;
      btnDeleteSelected.style.display = 'none';
      setLabel(btnDeleteMode, '좌석 데이터 삭제');
    }
    if (!state.fixMode) {
      state.fixMode = true;
      setLabel(btnFix, '고정 저장/종료', 'save');
      btnFix.classList.add('fix-on');
    } else {
      state.fixMode = false;
      setLabel(btnFix, '좌석 고정 모드');
      btnFix.classList.remove('fix-on');
      await post('/api/seats/fix', { key: key(), numbers: [...state.selected] });
    }
    state.selected.clear();
    await refresh();
  }

  const setLabel = (btn, text, iconName) => clear(btn, iconName && icon(iconName, 14), text);

  function deleteMenu() {
    if (state.fixMode) {
      state.fixMode = false;
      setLabel(btnFix, '좌석 고정 모드');
      btnFix.classList.remove('fix-on');
    }
    const menu = h('div', { class: 'popup-menu', style: { left: `${btnDeleteMode.offsetLeft}px`, top: `${btnDeleteMode.offsetTop + btnDeleteMode.offsetHeight}px` } },
      h('button', { onclick: run(toggleDelete) }, '선택 삭제 모드 토글'),
      h('button', { onclick: run(deleteAll) }, '전체 삭제'));
    actions.append(menu);
    setTimeout(() => document.addEventListener('click', () => menu.remove(), { once: true }));
  }

  async function toggleDelete() {
    state.deleteMode = !state.deleteMode;
    setLabel(btnDeleteMode, state.deleteMode ? '선택 삭제 모드 활성 중' : '좌석 데이터 삭제', state.deleteMode ? 'save' : null);
    btnDeleteSelected.style.display = 'none';
    state.selected.clear();
    await refresh();
  }

  async function deleteSelected() {
    await post('/api/seats/delete', { key: key(), numbers: [...state.selected] });
    state.deleteMode = false;
    state.selected.clear();
    setLabel(btnDeleteMode, '좌석 데이터 삭제');
    btnDeleteSelected.style.display = 'none';
    await app.refresh();
  }

  async function deleteAll() {
    await post('/api/seats/delete-all', { key: key() });
    await app.refresh();
  }

  async function toggleMask() {
    state.mask = !state.mask;
    setLabel(btnMask, state.mask ? '정보 표시' : '정보 가리기', state.mask ? 'unlock' : 'lock');
    renderSeats({ seats: state.seats, memos: state.memos });
  }

  async function loadFile() {
    const file = await pickFile('.csv,.xlsx');
    if (!file) return;
    await upload('/api/seats/load', file, { key: key() });
    await app.refresh();
  }

  // -------------------------------------------------------------- 메모
  function renderMemos(memos) {
    state.memos = memos;
    clear(memoList, memos.map((m) => h('div', { class: 'memo-row' },
      h('span', { class: 'dot', style: { width: '10px', height: '10px', background: '#2563EB', marginTop: '3px', flex: 'none' } }),
      h('span', { class: 'txt' }, m.content),
      h('button', { style: { color: '#2563EB' }, title: '편집', onclick: () => {
        state.editingMemo = m;
        memoText.value = m.content;
        memoAdd.textContent = '편집 완료';
      } }, '✎'),
      h('button', { style: { color: '#EF4444' }, title: '삭제', onclick: run(async () => { await del(`/api/memos/${m.id}`); await app.refresh(); }) }, '✕'))));
  }

  async function addMemo() {
    const text = memoText.value.trim();
    if (state.editingMemo) {
      if (text) await put(`/api/memos/${state.editingMemo.id}`, { content: text });
      state.editingMemo = null;
      memoAdd.textContent = '+ 메모 추가';
    } else if (text) {
      await post('/api/memos', { content: text });
    } else {
      return;
    }
    memoText.value = '';
    await app.refresh();
  }

  return {
    el: page, refresh,
    init(boot) {
      clear(year, boot.years.map((y) => h('option', null, y)));
      clear(semester, boot.seasons.map((s) => h('option', null, s)));
      year.value = boot.selectedYear;
      semester.value = boot.selectedSeason;
    },
    update(boot) { pill.textContent = boot.seasonLabel; },
    viewKey: key,
    busy: () => state.fixMode || state.deleteMode || !!state.editingMemo || document.activeElement === memoText,
  };
}

// ---------------------------------------------------------------- 좌석 상세 (상상Lab [더보기]에서도 쓴다)
export function seatModal(app, { number, key, student, cabinet }) {
  const m = modal({ width: 820, height: 300 });
  const body = h('div', { class: 'seat-modal-grid' });
  let editing = false;
  const field = (value, width) => {
    const el = h('input', { type: 'text', readOnly: true, value: value || '', style: { width: width || 'auto' } });
    const fit = () => { if (!width) el.size = Math.max(1, (el.value.length || 1) * 2); };
    el.addEventListener('input', fit);
    fit();
    return el;
  };
  const s = student || {};
  const name = field(s.name);
  const advisor = field(s.advisor);
  const email = field(s.email, '276px');
  const dept = field(s.department);
  const sid = h('span', null, s.studentId || '');
  const cab = h('span', null, cabinet);
  const pair = (cap, el, right) => h('div', { class: `pair${right ? ' right' : ''}` }, cap, el);
  body.append(pair('이름 : ', name), pair('소속 : ', dept, true),
    pair('지도 교수 : ', advisor), pair('학번 : ', sid, true),
    pair('이메일 : ', email), pair('캐비닛 사용 : ', cab, true));

  const load = (st) => {
    name.value = st.name; dept.value = st.department; advisor.value = st.advisor; email.value = st.email;
    sid.textContent = st.studentId;
    for (const el of [name, dept, advisor]) el.dispatchEvent(new Event('input'));
  };

  const setEdit = (on) => {
    editing = on;
    for (const el of [name, advisor, email, dept]) el.readOnly = !on;
    body.classList.toggle('editing', on);
    btnEdit.textContent = on ? '저장' : '좌석 수정';
  };

  const btnEdit = flatBtn('좌석 수정', '#10B981', async () => {
    if (!editing) { setEdit(true); return; }
    const r = await post('/api/seats/edit', { key, number, studentId: sid.textContent, name: name.value, department: dept.value, advisor: advisor.value, email: email.value });
    setEdit(false);
    if (r.student) load(r.student);
    await app.refresh();
  }, { style: { padding: '8px 20px' } });

  const pick = () => studentSelector(false, async (picked) => {
    const r = await post('/api/seats/assign', { key, number, studentId: picked.studentId });
    if (r.student) load(r.student);
    await app.refresh();
    return true;
  });

  m.box.append(
    h('div', { class: 'row', style: { position: 'absolute', top: '20px', right: '35px', gap: '15px', zIndex: 2 } },
      number ? h('button', { class: 'btn-flat', style: { background: '#2563EB', padding: '6px 15px', height: '42px', borderRadius: '6px' }, onclick: run(pick) }, '학생선택') : null,
      h('button', { class: 'btn-x', onclick: m.close }, icon('close', 24))),
    h('div', { style: { height: '20px', flex: 'none' } }), body,
    h('div', { class: 'row', style: { justifyContent: 'flex-end', marginTop: 'auto', paddingRight: '8px' } }, btnEdit));
  setEdit(false);
}
