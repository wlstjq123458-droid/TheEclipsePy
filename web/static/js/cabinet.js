// [캐비닛 현황] — 신청 현황, 48칸 배치(드래그 이동·맞교환, 가장자리에 머물면 페이지 넘김), 상세 창.
import {
  h, clear, icon, get, post, say, ask, run, dataGrid, modal, actionBtn, flatBtn, modalBtn, alertCard, pickFile, upload, download,
} from './core.js';
import { approvalHistory, chooseCabinet, studentSelector } from './dialogs.js';

const EDGE_DWELL_MS = 450;
const pageNumbers = (page) => {
  const base = page === 1 ? 0 : 24;
  const out = [];
  for (let r = 0; r < 3; r++) for (let c = 0; c < 8; c++) out.push(base + c * 3 + r + 1);
  return out;
};

export function createCabinet(app) {
  const root = h('div', { class: 'cab-page' });
  const content = h('div', { class: 'cab-content' });
  root.append(content);
  const alert = alertCard('clock', '캐비닛 승인 대기', 'orange', '빠른 확인 필요', () => app.switchTab('equipment'));
  const search = h('input', { type: 'text', style: { width: '120px' } });
  const block = h('div', { class: 'cab-block' });
  const pageLabel = h('span', null, '1 / 2');
  const avail = h('b');
  const used = h('b');
  const zoneL = h('div', { class: 'edge left' }, '◀');
  const zoneR = h('div', { class: 'edge right' }, '▶');

  const state = { page: 1, highlight: 0, data: null, drag: null };

  const approvals = dataGrid({
    cols: [
      { header: '신청 일자', width: 130, text: (a) => a.requestDate }, { header: '학번', width: 100, text: (a) => a.studentId },
      { header: '이름', width: 100, text: (a) => a.studentName }, { header: '대여 기간', width: 150, text: (a) => a.rentalPeriod },
      { header: '승인 처리', stretch: true, minWidth: 110, cell: (a) => h('div', { class: 'row', style: { gap: '8px', height: '100%' } },
        flatBtn('승인', '#10B981', async () => { await post(`/api/approvals/${a.id}/approve`, {}); await app.refresh(); }, { cls: 'fill-btn' }),
        flatBtn('반려', '#EF4444', async () => { await post(`/api/approvals/${a.id}/reject`, {}); await app.refresh(); }, { cls: 'fill-btn' })) },
    ],
    rowHeight: 40, alternating: '#F3F4F6',
  });

  const togglePage = () => { state.page = state.page === 1 ? 2 : 1; renderCells(); };

  content.append(
    h('div', { class: 'row', style: { marginBottom: '20px' } }, alert, h('div', { class: 'spacer' }),
      h('span', { style: { fontWeight: 600, color: '#374151', marginRight: '5px' } }, icon('search', 14), ' 검색: '), search, h('span', { style: { width: '10px' } }),
      actionBtn('승인/반려 내역', () => approvalHistory('캐비닛', app), { icon: 'clipboard' }), h('span', { style: { width: '8px' } }),
      actionBtn('캐비닛 데이터 삭제', () => say('캐비닛 데이터 삭제 기능 구현용 이벤트 핸들러입니다.', '캐비닛 삭제')), h('span', { style: { width: '8px' } }),
      actionBtn('캐비닛 데이터 추출', () => download('/api/cabinets/export')), h('span', { style: { width: '8px' } }),
      actionBtn('엑셀 가져오기', importFile, { icon: 'download' })),
    h('div', { class: 'section', style: { marginBottom: '10px' } }, '캐비닛 신청 현황 (구글폼)'),
    h('div', { class: 'grid-card', style: { height: '160px', flex: 'none' } }, approvals.el),
    h('div', { class: 'pager' }, actionBtn('◀', togglePage), pageLabel, actionBtn('▶', togglePage)),
    h('div', { class: 'cab-blocks' }, h('div', { class: 'cab-slot' }, zoneL), block, h('div', { class: 'cab-slot' }, zoneR)),
    h('div', { class: 'counters' }, h('div', { class: 'counter' }, '사용 가능한 캐비닛 : ', avail), h('div', { class: 'counter' }, '사용 중인 캐비닛 : ', used)));

  async function importFile() {
    const file = await pickFile('.xlsx');
    if (!file) return;
    await upload('/api/cabinets/import', file);
    await app.refresh();
  }

  // -------------------------------------------------------------- 칸
  function renderCells() {
    pageLabel.textContent = `${state.page} / 2`;
    const q = search.value.trim().toLowerCase();
    clear(block, pageNumbers(state.page).map((n) => cell(n, q)));
    showZones(state.drag !== null);
  }

  function cell(n, q) {
    const alloc = state.data?.cells[String(n)];
    const stu = alloc?.student;
    const match = stu && [stu.name, stu.studentId, stu.department].some((v) => v.toLowerCase().includes(q));
    const cls = ['cab', alloc ? 'used' : 'empty', alloc?.expiring && 'soon', q && (match ? 'match' : 'dim'), state.highlight === n && 'hl'].filter(Boolean).join(' ');
    const el = h('div', { class: cls, draggable: !!alloc, onclick: run(() => clickCell(n)) },
      h('div', { class: 'n' }, n),
      alloc && [h('div', { class: 'i' }, stu?.studentId), h('div', { class: 'm' }, stu?.name), h('div', { class: 'p' }, alloc.period)]);
    el.addEventListener('dragstart', (e) => {
      e.dataTransfer.setData('application/x-cabinet', String(n));
      e.dataTransfer.effectAllowed = 'move';
      startDrag(n, el);
    });
    el.addEventListener('dragend', endDrag);
    el.addEventListener('dragover', (e) => {
      if (state.drag === null || state.drag === n) return;
      e.preventDefault();
      el.classList.add('drop');
    });
    el.addEventListener('dragleave', () => el.classList.remove('drop'));
    el.addEventListener('drop', run(async (e) => {
      e.preventDefault();
      el.classList.remove('drop');
      const src = Number(e.dataTransfer.getData('application/x-cabinet'));
      if (!src || src === n) return;
      const r = await post('/api/cabinets/drop', { src, dst: n });
      afterMove(r);
      await app.refresh();
    }));
    return el;
  }

  const afterMove = (r) => {
    if (r.highlight) {
      state.highlight = r.highlight;
      state.page = r.highlight <= 24 ? 1 : 2;
    }
  };

  async function clickCell(n) {
    if (state.highlight) { state.highlight = 0; renderCells(); }
    if (state.data.cells[String(n)]) {
      cabinetModal(n, false);
    } else {
      if (await ask(`[캐비닛 ${n}번] 사용 가능 (미배정) 상태입니다.\n이 캐비닛에 새로운 학생을 임의 배정하시겠습니까?`, '캐비닛 배정')) cabinetModal(n, true);
    }
  }

  // -------------------------------------------------------------- 드래그 중 가장자리 페이지 넘김
  const edge = { since: null, dir: 0, x: 0, y: 0, timer: null };

  function startDrag(n, el) {
    state.drag = n;
    app.dragging = n;
    setTimeout(() => el.classList.add('dragging'));
    edge.since = null;
    edge.dir = 0;
    showZones(true);
    document.addEventListener('dragover', trackDrag);
    edge.timer = setInterval(edgeTick, 40);
  }

  function endDrag() {
    state.drag = null;
    app.dragging = null;
    clearInterval(edge.timer);
    document.removeEventListener('dragover', trackDrag);
    showZones(false);
    block.querySelectorAll('.dragging, .drop').forEach((c) => c.classList.remove('dragging', 'drop'));
  }

  const trackDrag = (e) => { edge.x = e.clientX; edge.y = e.clientY; };

  function showZones(on) {
    zoneL.classList.toggle('on', on && state.page === 2);
    zoneR.classList.toggle('on', on && state.page === 1);
  }

  function edgeTick() {
    const r = block.getBoundingClientRect();
    const scale = r.width / block.offsetWidth || 1;
    let dir = 0;
    if (edge.y >= r.top - 40 * scale && edge.y <= r.bottom + 40 * scale) {
      if (state.page === 1 && edge.x >= r.right + 4 * scale) dir = 1;
      else if (state.page === 2 && edge.x && edge.x <= r.left - 4 * scale) dir = -1;
    }
    zoneL.classList.toggle('strong', dir < 0);
    zoneR.classList.toggle('strong', dir > 0);
    if (dir === 0) { edge.since = null; edge.dir = 0; return; }
    if (edge.dir !== dir || edge.since === null) { edge.dir = dir; edge.since = Date.now(); return; }
    if (Date.now() - edge.since >= EDGE_DWELL_MS) {
      state.page = dir > 0 ? 2 : 1;
      edge.since = null;
      edge.dir = 0;
      renderCells();
    }
  }

  // -------------------------------------------------------------- 상세 창
  function cabinetModal(number, isNew) {
    const m = modal({ width: 600, height: 400 });
    const alloc = state.data.cells[String(number)];
    let editing = false;
    const title = h('div', { class: 'modal-title', style: { marginTop: '10px' } }, isNew ? `캐비닛 ${number}번 임의 배정` : `캐비닛 ${number}번 상세 정보`);
    const name = h('input', { type: 'text', value: alloc?.student?.name || '' });
    const sid = h('input', { type: 'text', value: alloc?.student?.studentId || '' });
    const periodText = h('input', { type: 'text', value: isNew ? state.data.defaultPeriod : alloc.period, readOnly: true, class: 'ro' });
    const start = h('input', { type: 'date' });
    const end = h('input', { type: 'date' });
    const pickers = h('div', { class: 'cab-dates' }, start, '~', end);

    const btnMove = modalBtn('좌석 옮기기', moveTo, { icon: 'refresh', style: { padding: '8px 15px', fontSize: '12px', minHeight: '34px' } });
    const btnSelect = modalBtn('학생선택', selectStudent, { style: { padding: '8px 15px', fontSize: '12px', minHeight: '34px' } });
    const btnEdit = modalBtn('정보 수정', () => setEdit(!editing), { cls: 'gray', style: { padding: '8px 15px', fontSize: '12px', fontWeight: 600, minHeight: '34px', minWidth: '86px' } });
    const btnSave = modalBtn('저장', save, { style: { background: '#10B981', padding: '8px 20px', minHeight: '36px', minWidth: '86px' } });

    async function setEdit(on) {
      editing = on;
      for (const el of [name, sid]) {
        el.readOnly = !on;
        el.classList.toggle('ro', !on);
      }
      btnSave.style.visibility = on ? 'visible' : 'hidden';
      btnSelect.style.display = on ? '' : 'none';
      btnMove.style.display = !on && state.data.cells[String(number)] ? '' : 'none';
      btnEdit.textContent = on ? '취소' : '정보 수정';
      periodText.style.display = on ? 'none' : '';
      pickers.style.display = on ? '' : 'none';
      if (on) await loadPickers();
    }

    async function loadPickers() {
      const r = await get(`/api/cabinets/period?text=${encodeURIComponent(periodText.value)}`);
      start.value = r.start;
      end.value = r.end;
    }

    async function save() {
      await post('/api/cabinets/save', { number, name: name.value, studentId: sid.value, start: start.value, end: end.value });
      m.close();
      await app.refresh();
    }

    async function moveTo() {
      const { numbers } = await get(`/api/cabinets/move-options?number=${number}`);
      const dst = await chooseCabinet(numbers, number);
      if (!dst || dst === number) return;
      const r = await post('/api/cabinets/move', { src: number, dst });
      afterMove(r);
      m.close();
      await app.refresh();
    }

    async function selectStudent() {
      await studentSelector(true, async (picked) => {
        const r = await post('/api/cabinets/assign', { number, studentId: picked.studentId });
        if (!r.done) {
          title.textContent = `캐비닛 ${number}번 상세 정보`;
          name.value = r.name;
          sid.value = r.studentId;
          periodText.value = r.period;
          if (editing) await loadPickers();
          afterMove(r);
          await app.refresh();
        }
        return true;
      });
    }

    m.box.append(
      h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '10px' } }, btnMove, btnSelect, btnEdit,
        h('button', { class: 'btn-x', style: { width: '34px', height: '34px', padding: '9px' }, onclick: m.close }, icon('close', 16))),
      title,
      h('div', { style: { flex: 1, display: 'flex', alignItems: 'center' } },
        h('div', { class: 'cab-fields', style: { width: '100%' } }, '이름 : ', name, '학번 : ', sid, '대여 기간 : ', h('div', null, periodText, pickers))),
      h('div', { style: { textAlign: 'right', marginTop: '15px' } }, btnSave));
    run(() => setEdit(isNew))();
  }

  search.addEventListener('input', () => { state.highlight = 0; renderCells(); });

  // 데스크톱의 Viewbox처럼 1380x825 화면을 창 크기에 맞춰 통째로 확대/축소한다
  const fit = () => {
    const scale = Math.min(root.clientWidth / 1380, root.clientHeight / 825) || 1;
    content.style.transform = `scale(${scale})`;
    content.style.left = `${Math.max(0, (root.clientWidth - 1380 * scale) / 2)}px`;
    content.style.top = `${Math.max(0, (root.clientHeight - 825 * scale) / 2)}px`;
  };
  new ResizeObserver(fit).observe(root);

  return {
    el: root,
    async refresh() {
      state.data = await get('/api/cabinets');
      alert.setCount(state.data.approvals.length);
      approvals.setRows(state.data.approvals);
      avail.textContent = `${state.data.available}개`;
      used.textContent = `${state.data.used}개`;
      renderCells();
    },
  };
}
