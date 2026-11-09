// [상상Lab 승인] [데이터 관리] [설정] 화면.
import {
  h, clear, icon, get, post, put, ask, run, dataGrid, actionBtn, flatBtn, alertCard, pickFile, upload,
} from './core.js';
import { approvalHistory, faceAttendance } from './dialogs.js';
import { seatModal } from './dashboard.js';

// ---------------------------------------------------------------- 상상Lab
export function createSangsangLab(app) {
  const page = h('div', { class: 'page-body' });
  const alert = alertCard('clock', '상상Lab 승인 대기', 'orange', '빠른 확인 필요', () => app.switchTab('equipment'));
  const flow = h('div', { class: 'lab-flow' });
  page.append(
    h('div', { class: 'row', style: { marginBottom: '15px' } }, alert, h('div', { class: 'spacer' }),
      actionBtn('승인/반려 내역', () => approvalHistory('상상Lab', app), { icon: 'clipboard' })),
    h('div', { class: 'section', style: { marginBottom: '15px' } }, '상상Lab 신청 및 승인 대기 (구글폼)'), flow);

  const card = (a) => h('div', { class: 'lab-card' },
    h('div', { class: 'row', style: { marginBottom: '10px' } }, h('div', { class: 'ttl' }, '상상Lab 신청'), h('span', { class: 'new' }, '신규 요청')),
    h('div', { class: 'lab-row' }, h('span', { class: 'cap' }, icon('user', 11), ' 신청자'), h('b', { class: 'val' }, a.studentName),
      h('button', { class: 'more', onclick: () => seatModal(app, { number: 0, key: '', student: {
        studentId: a.studentId, name: a.studentName, department: a.department, advisor: a.advisor, email: a.email }, cabinet: '사용 안 함' }) }, '더보기')),
    h('div', { class: 'lab-row' }, h('span', { class: 'cap' }, icon('clock', 11), ' 요청 시간'), h('span', { class: 'val' }, `${a.requestDay} 14:00 ~ 16:00`)),
    h('div', { class: 'lab-row' }, h('span', { class: 'cap' }, icon('folder', 11), ' 희망 공간'), h('b', { class: 'val' }, 'u301')),
    h('div', { class: 'lab-actions' },
      h('button', { style: { background: '#2563EB', color: '#fff', border: 0 }, onclick: run(async () => { await post(`/api/approvals/${a.id}/approve`, {}); await app.refresh(); }) }, '✓ 승인'),
      h('button', { style: { background: '#fff', color: '#EF4444', border: '1px solid #EF4444' }, onclick: run(async () => { await post(`/api/approvals/${a.id}/reject`, {}); await app.refresh(); }) }, '✕ 반려')));

  return {
    el: page,
    async refresh() {
      const { approvals } = await get('/api/sangsanglab');
      alert.setCount(approvals.length);
      clear(flow, approvals.map(card));
    },
  };
}

// ---------------------------------------------------------------- 데이터 관리
export function createData(app) {
  const page = h('div', { class: 'page-body' });
  const search = h('input', { type: 'text' });
  let students = [];
  let selected = null;

  const fields = {
    studentId: h('input', { type: 'text', disabled: true }), name: h('input', { type: 'text', disabled: true }),
    department: h('input', { type: 'text', disabled: true }), advisor: h('input', { type: 'text', disabled: true }),
    contact: h('input', { type: 'text', disabled: true }), email: h('input', { type: 'text', disabled: true, style: { marginBottom: '15px' } }),
  };
  const faceSummary = h('div', { class: 'face-summary' });
  const faceGrid = dataGrid({
    cols: [{ header: '날짜', width: 80, text: (r) => r.date }, { header: '출근', width: 60, text: (r) => r.checkIn },
      { header: '퇴근', width: 60, text: (r) => r.checkOut }, { header: '근무', stretch: true, minWidth: 40, text: (r) => r.workTime }],
    rowId: (r) => `${r.date}|${r.checkIn}`, rowHeight: 28, fontSize: 11,
  });
  const btnSave = flatBtn('변경 사항 저장', '#10B981', save, { cls: 'wide', disabled: true });
  const btnDelete = flatBtn('마스터에서 삭제', '#EF4444', remove, { cls: 'wide', disabled: true, style: { marginTop: '8px' } });

  const grid = dataGrid({
    cols: [{ header: '학번', width: 100, text: (s) => s.studentId }, { header: '이름', width: 100, text: (s) => s.name },
      { header: '소속', width: 150, text: (s) => s.department }, { header: '지도교수', width: 100, text: (s) => s.advisor },
      { header: '연락처', width: 120, text: (s) => s.contact }, { header: '이메일', width: 150, text: (s) => s.email }],
    rowId: (s) => s.studentId, rowHeight: 35, onSelect: run(pick),
  });

  async function pick(student) {
    selected = student;
    for (const [k, el] of Object.entries(fields)) { el.disabled = !student; if (student) el.value = student[k]; }
    btnSave.disabled = !student;
    btnDelete.disabled = !student;
    if (!student) { faceGrid.setRows([]); faceSummary.textContent = ''; return; }
    const d = await get(`/api/face/student/${encodeURIComponent(student.studentId)}`);
    faceGrid.setRows(d.rows);
    faceSummary.textContent = d.summary;
  }

  async function save() {
    if (!selected) return;
    await put(`/api/students/${encodeURIComponent(selected.studentId)}`, Object.fromEntries(Object.entries(fields).map(([k, el]) => [k, el.value])));
    await app.refresh();
  }

  async function remove() {
    if (!selected) return;
    await post(`/api/students/${encodeURIComponent(selected.studentId)}/delete`, {});
    await pick(null);
    await app.refresh();
  }

  const filter = () => {
    const q = search.value.trim().toLowerCase();
    grid.setRows(students.filter((s) => !q || [s.studentId, s.name, s.advisor, s.department].some((v) => v.toLowerCase().includes(q))));
    if (selected && !grid.current()) run(pick)(null);
  };
  search.addEventListener('keyup', (e) => { if (e.key === 'Enter') filter(); });

  async function importFile() {
    const file = await pickFile('.xlsx,.csv');
    if (!file) return;
    await upload('/api/students/import', file);
    await app.refresh();
  }

  const lbl = (text, el) => [h('label', null, text), el];
  page.append(
    h('div', { style: { fontSize: '18px', fontWeight: 700, color: '#111827', marginBottom: '4px' } }, '데이터 관리 (마스터 데이터베이스)'),
    h('div', { style: { color: '#6B7280' } }, '학생 정보는 시즌이 바뀌어도 지워지지 않고 계속 보관됩니다.'),
    h('div', { class: 'data-search' }, h('span', { class: 'cap' }, '검색어 (학번/이름/지도교수): '), search, h('span', { style: { width: '10px' } }),
      actionBtn('검색', filter, { icon: 'search', cls: 'mid' }), h('span', { style: { width: '5px' } }),
      actionBtn('검색 초기화', () => { search.value = ''; filter(); }, { icon: 'refresh', iconSize: 12, cls: 'mid' }), h('span', { style: { width: '12px' } }),
      actionBtn('엑셀 가져오기', importFile, { icon: 'download', cls: 'mid' }), h('span', { style: { width: '8px' } }),
      actionBtn('얼굴인식 출결 기록', faceAttendance, { icon: 'video', cls: 'mid' }), h('span', { style: { width: '8px' } }),
      actionBtn('전체 삭제', async () => { await post('/api/students/delete-all', {}); await pick(null); await app.refresh(); }, { icon: 'trash', cls: 'mid danger' })),
    h('div', { class: 'data-main' }, h('div', { style: { flex: 1, minWidth: 0 } }, grid.el),
      h('div', { class: 'data-side' }, h('h3', null, '학생 정보 상세'),
        lbl('학번', fields.studentId), lbl('이름', fields.name), lbl('소속', fields.department), lbl('지도교수', fields.advisor),
        lbl('연락처', fields.contact), lbl('이메일', fields.email), btnSave, btnDelete,
        h('h3', { style: { margin: '22px 0 6px' } }, '얼굴인식 출석'), faceSummary, h('div', { class: 'face-mini' }, faceGrid.el))));

  return {
    el: page,
    async refresh() {
      students = (await get('/api/students')).rows;
      filter();
    },
    busy: () => !!selected && document.activeElement?.closest('.data-side'),
  };
}

// ---------------------------------------------------------------- 설정
export function createSettings(app) {
  const page = h('div', { class: 'page-body' });
  const scroll = h('div', { class: 'settings-scroll' });
  page.append(scroll);
  const url = () => h('input', { type: 'text', class: 'url' });
  const main = url();
  const cabinet = url();
  const equipment = url();
  const email = h('input', { type: 'text', class: 'small-ro', readOnly: true });
  const keyPath = h('input', { type: 'text', class: 'small-ro', readOnly: true, style: { flex: 1 } });
  const polling = h('input', { type: 'checkbox' });
  const interval = h('input', { type: 'text', style: { width: '70px', height: '28px', padding: '0 8px', borderColor: '#D1D5DB' } });
  const approvalBoxes = h('div', { class: 'row', style: { gap: '14px', margin: '4px 0 12px' } });
  let approvalChecks = [];
  const status = h('div', { style: { fontSize: '11px', whiteSpace: 'pre-line', marginTop: '10px' } });
  const years = h('div', { class: 'year-cards' });
  const editor = h('div', { class: 'box', style: { background: '#fff', borderColor: '#E5E7EB' } });
  const current = h('div', { style: { fontWeight: 700, color: '#1D4ED8' } });
  const faceKey = h('input', { type: 'text', class: 'small-ro', readOnly: true, style: { flex: 1 } });
  const serverUrl = h('input', { type: 'text', class: 'small-ro', readOnly: true });
  const pwNow = h('input', { type: 'password', autocomplete: 'current-password', style: { width: '200px' } });
  const pwNew = h('input', { type: 'password', autocomplete: 'new-password', style: { width: '200px' } });
  let selectedYear = null;
  let info = null;

  const block = (caption, input, hint) => [h('div', { class: 'fld' }, caption), input, h('div', { class: 'hint', style: { marginTop: '4px' } }, hint)];

  scroll.append(
    h('div', { style: { fontSize: '18px', fontWeight: 700, color: '#111827', marginBottom: '15px' } }, '설정'),
    h('div', { class: 'settings-card' },
      h('h3', null, '시스템 정보'),
      h('div', { style: { lineHeight: '21px' } }, '프로그램명: 동서대학교 좌석 및 기자재 대여 관리 프로그램', h('br'), '버전: v1.1.0', h('br'), '플랫폼: Python 3 / FastAPI Web Application'),

      h('h3', null, '구글 폼 연동 설정'),
      h('div', { class: 'box', style: { background: '#F9FAFB', borderColor: '#E5E7EB' } },
        h('h4', { style: { color: '#374151' } }, '신청 폼 응답 시트'),
        h('div', { class: 'hint' }, '상상Lab 신청 폼 URL은 실제 동기화에 쓰입니다 — 상상Lab 신청과, 캐비닛·기자재 전용 시트를 따로 지정하지 않은 신청이 모두 이 시트에서 들어옵니다. 캐비닛·기자재는 신청을 별도 시트로 따로 받고 싶을 때만 채우세요.'),
        block('상상Lab 신청 폼 URL  (실제 동기화에 사용됨)', main, "※ 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트를 아래 서비스 계정에 '뷰어'로 공유해야 합니다."),
        block('캐비닛 응답 시트 주소  (선택 — 넣으면 캐비닛 신청만 이 시트에서 따로 받습니다)', cabinet, "※ 캐비닛 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트도 아래 서비스 계정에 '뷰어' 공유가 필요합니다."),
        block('기자재 응답 시트 주소  (선택 — 넣으면 기자재 신청만 이 시트에서 따로 받습니다)', equipment, "※ 기자재 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트도 아래 서비스 계정에 '뷰어' 공유가 필요합니다.")),
      h('div', { class: 'box', style: { background: '#F0FDF4', borderColor: '#BBF7D0' } },
        h('h4', { style: { color: '#166534' } }, '구글 시트 연동 (서비스 계정 · 동기화 설정)'),
        h('div', { style: { fontSize: '10px', color: '#4D7C60' } }, "위에서 넣은 시트 주소들을 이 서비스 계정으로 읽어옵니다. 시트마다 이 주소를 '뷰어'로 공유해 두어야 합니다."),
        h('div', { class: 'fld', style: { marginTop: '10px' } }, "서비스 계정 (이 주소로 시트를 '뷰어' 공유해야 합니다)"), email,
        h('div', { class: 'fld', style: { marginTop: '8px' } }, '키 파일 위치'),
        h('div', { class: 'row', style: { gap: '8px' } }, keyPath, actionBtn('키 파일 선택...', pickKey, { icon: 'folder', cls: 'mid' })),
        h('div', { class: 'row', style: { margin: '12px 0' } }, h('label', null, polling, ' 자동 동기화'), h('span', { style: { width: '20px' } }),
          h('span', { style: { color: '#6B7280', marginRight: '6px' } }, '주기(초):'), interval),
        h('div', { class: 'fld', style: { marginTop: '0' } }, "지도교수 승인을 거친 신청만 받기 — 시트의 '승인상태'가 \"승인\"인 행만 들어오고, \"반려\"는 승인/반려 내역에 기록됩니다"),
        approvalBoxes,
        h('div', { class: 'row', style: { gap: '10px' } }, actionBtn('지금 동기화', syncNow, { icon: 'refresh' }), actionBtn('연동 설정 저장', saveSync, { icon: 'save' })),
        status),

      h('h3', null, '얼굴인식 출결 연동'),
      h('div', { class: 'box', style: { background: '#F9FAFB', borderColor: '#E5E7EB' } },
        h('div', { class: 'hint', style: { color: '#6B7280', fontSize: '11px' } }, '얼굴인식 컴퓨터에서 연동 프로그램(tools/face_bridge.py)을 실행하면 출결 기록이 이 서버로 올라오고, 학생 명단은 얼굴인식 쪽으로 내려갑니다. 얼굴인식 프로그램이 이 서버와 같은 컴퓨터에 있으면 연동 프로그램 없이 바로 읽습니다.'),
        h('div', { class: 'fld' }, '서버 주소'), serverUrl,
        h('div', { class: 'fld' }, '연동 키 (관리자 비밀번호와 별개입니다. 외부에 공유하지 마세요)'),
        h('div', { class: 'row', style: { gap: '8px' } }, faceKey, actionBtn('키 다시 만들기', regenerateKey, { cls: 'mid' }))),

      h('h3', null, '학사 시즌 일정 관리'),
      h('div', { class: 'box', style: { background: '#EFF6FF', borderColor: '#BFDBFE' } },
        h('div', { style: { fontSize: '11px', color: '#6B7280' } }, '연도 카드를 누르면 그 연도의 1학기 / 여름방학 / 2학기 / 겨울방학 시작일·종료일을 입력할 수 있습니다. 현재 날짜가 포함되는 시즌이 대시보드에 자동으로 표시됩니다.'),
        years, editor, current),

      h('h3', null, '관리자 비밀번호 변경'),
      h('div', { class: 'row', style: { gap: '8px' } }, '현재 비밀번호', pwNow, '새 비밀번호', pwNew, actionBtn('변경', changePassword, { cls: 'mid' }))));

  async function pickKey() {
    const file = await pickFile('.json');
    if (!file) return;
    await upload('/api/settings/key', file);
    await refresh();
    await syncNow();
  }

  async function syncNow() {
    status.textContent = '동기화 중...';
    try {
      await post('/api/settings/sync-now', {});
    } finally {
      await refresh();
      await app.refreshBadges();
    }
  }

  async function saveSync() {
    await put('/api/settings/sync', { sangsangLabFormUrl: main.value, cabinetFormUrl: cabinet.value, equipmentFormUrl: equipment.value,
      pollingEnabled: polling.checked, pollingIntervalSeconds: interval.value,
      approvalTypes: approvalChecks.filter(([, cb]) => cb.checked).map(([t]) => t) });
    await refresh();
  }

  async function regenerateKey() {
    if (!(await ask('연동 키를 새로 만들면 지금 쓰는 얼굴인식 연동 프로그램의 키도 바꿔야 합니다.\n계속할까요?', '연동 키', true))) return;
    faceKey.value = (await post('/api/face/link-info/regenerate', {})).apiKey;
  }

  async function changePassword() {
    await post('/api/auth/password', { current: pwNow.value, password: pwNew.value });
    pwNow.value = '';
    pwNew.value = '';
  }

  // -------------------------------------------------------------- 시즌
  function renderYears() {
    clear(years, info.years.map((y) => h('div', {
      class: ['year-card', y === info.currentYear && 'current', y === selectedYear && 'selected'].filter(Boolean).join(' '),
      onclick: run(async () => { selectedYear = y; renderYears(); await loadRows(); }),
    }, y, y === info.currentYear && h('small', null, '● 현재 시즌'))),
    h('div', { class: 'year-card add', onclick: run(addYear) }, '＋ 연도 추가'));
  }

  async function loadRows() {
    if (selectedYear === null) { editor.style.display = 'none'; return; }
    editor.style.display = '';
    const { rows } = await get(`/api/seasons/${selectedYear}`);
    const inputs = rows.map((r) => ({ name: r.name, start: h('input', { type: 'date', value: r.start }), end: h('input', { type: 'date', value: r.end }) }));
    clear(editor,
      h('div', { class: 'row' }, h('b', { style: { fontSize: '13px', color: '#111827', flex: 1 } }, `${selectedYear}년 시즌 일정`), actionBtn('이 연도 삭제', deleteYear, { icon: 'trash', cls: 'mid' })),
      h('table', { class: 'season-table' }, h('thead', null, h('tr', null, h('th', { style: { width: '120px' } }, '시즌'), h('th', null, '시작일'), h('th', null, '종료일'))),
        h('tbody', null, inputs.map((r) => h('tr', null, h('td', null, r.name), h('td', null, r.start), h('td', null, r.end))))),
      actionBtn('시즌 일정 저장', async () => {
        await put(`/api/seasons/${selectedYear}`, { rows: inputs.map((r) => ({ name: r.name, start: r.start.value, end: r.end.value })) });
        await refresh();
        await app.refreshBadges();
      }, { icon: 'save' }));
  }

  async function addYear() {
    const r = await post('/api/seasons', {});
    selectedYear = r.year;
    await refresh();
  }

  async function deleteYear() {
    await post(`/api/seasons/${selectedYear}/delete`, {});
    selectedYear = null;
    await refresh();
    await app.refreshBadges();
  }

  async function refresh() {
    info = await get('/api/settings');
    if (document.activeElement?.tagName !== 'INPUT' || !scroll.contains(document.activeElement)) {
      main.value = info.sangsangLabFormUrl;
      cabinet.value = info.cabinetFormUrl;
      equipment.value = info.equipmentFormUrl;
      interval.value = info.pollingIntervalSeconds;
      polling.checked = info.pollingEnabled;
      approvalChecks = info.allApprovalTypes.map((t) => [t, h('input', { type: 'checkbox', checked: info.approvalTypes.includes(t) })]);
      clear(approvalBoxes, approvalChecks.map(([t, cb]) => h('label', null, cb, ` ${t}`)));
    }
    email.value = info.serviceAccountEmail;
    keyPath.value = info.keyPath;
    status.textContent = info.syncStatus;
    status.style.color = info.syncWarning ? '#B45309' : '#6B7280';
    current.textContent = info.currentInfo;
    serverUrl.value = window.location.origin;
    faceKey.value = (await get('/api/face/link-info')).apiKey;
    if (selectedYear === null || !info.years.includes(selectedYear)) {
      selectedYear = info.currentYear ?? (info.years.includes(new Date().getFullYear()) ? new Date().getFullYear() : info.years[info.years.length - 1] ?? null);
    }
    renderYears();
    await loadRows();
  }

  return { el: page, refresh, busy: () => scroll.contains(document.activeElement) && document.activeElement.tagName === 'INPUT' };
}
