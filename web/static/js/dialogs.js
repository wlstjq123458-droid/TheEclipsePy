// 여러 화면이 같이 쓰는 창 — 번호 선택, 학생 선택, 내역, 기간 만료 안내, 얼굴인식 출결 기록.
import {
  h, clear, icon, get, post, warn, run, dialog, modal, closeButton, dataGrid, line, actionBtn, modalBtn, registerChooser,
} from './core.js';

// ---------------------------------------------------------------- 승인할 때 뜨는 선택 창
registerChooser('cabinet', (data) => chooseCabinet(data.numbers, 0).then((n) => (n ? { cabinet: n } : null)));
registerChooser('equipment', (data) => dialog({
  title: '대여 기자재 및 기간 선택', width: 350,
  build(c, done) {
    const none = data.numbers.length === 0;
    const number = h('select', { style: { width: '180px' } },
      none ? h('option', null, '사용 가능한 기자재 없음') : data.numbers.map((n) => h('option', null, n)));
    const phone = h('input', { type: 'text', value: data.phone, style: { width: '180px', height: '25px' } });
    const rental = h('input', { type: 'date', value: data.rentalDate, style: { width: '180px' } });
    const due = h('input', { type: 'date', value: data.dueDate, style: { width: '180px' } });
    c.append(
      line('기자재 종류:', 100, h('select', { style: { width: '180px' }, disabled: true }, h('option', null, data.typeLabel))),
      line('기자재 번호:', 100, number), line('연락처:', 100, phone),
      line('대여 시작일:', 100, rental), line('반납 예정일:', 100, due),
      h('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' } },
        h('button', { class: 'btn-wpf colored', style: { width: '80px', background: '#10B981' }, disabled: none,
          onclick: () => done({ equipment: { unit: number.value, phone: phone.value, rentalDate: rental.value, dueDate: due.value } }) }, '대여 완료'),
        h('button', { class: 'btn-wpf', style: { width: '80px' }, onclick: () => done(null) }, '취소')));
  },
}));

export function chooseCabinet(numbers, movingFrom) {
  return dialog({
    title: movingFrom ? `캐비닛 ${movingFrom}번 좌석 옮기기` : '캐비닛 번호 배정', width: 340,
    build(c, done) {
      const none = numbers.length === 0;
      const combo = h('select', { style: { width: '150px' } },
        none ? h('option', null, '사용 가능한 캐비닛 없음') : numbers.map((n) => h('option', null, n)));
      c.append(
        movingFrom ? h('div', { style: { fontSize: '11px', color: '#6B7280', marginBottom: '12px', whiteSpace: 'pre-line' } },
          `현재 ${movingFrom}번 → 옮길 번호를 고르세요.\n(비어 있는 번호만 보입니다)`) : '',
        line('캐비닛 번호 선택:', 110, combo),
        h('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '20px' } },
          h('button', { class: 'btn-wpf colored', style: { width: movingFrom ? '100px' : '80px', background: '#10B981' }, disabled: none,
            onclick: () => done(Number(combo.value)) }, movingFrom ? '여기로 옮기기' : '배정 승인'),
          h('button', { class: 'btn-wpf', style: { width: '80px' }, onclick: () => done(null) }, '취소')));
    },
  });
}

// ---------------------------------------------------------------- 학생 선택
// onPick(student)이 true를 돌려주면 창을 닫는다.
export async function studentSelector(forCabinet, onPick) {
  const { rows: students } = await get('/api/students');
  const m = modal({ width: 550, height: 480, padding: 30 });
  const search = h('input', { type: 'text', style: { flex: 1, height: '35px', padding: '5px 10px', borderColor: '#D1D5DB', minWidth: 0 } });
  const confirm = run(async () => {
    const picked = grid.current();
    if (!picked) { await warn('배정할 학생을 먼저 선택하세요.', '경고'); return; }
    if (await onPick(picked)) m.close();
  });
  const grid = dataGrid({
    cols: [{ header: '학번', width: 120, text: (s) => s.studentId }, { header: '이름', width: 100, text: (s) => s.name },
      forCabinet ? { header: '대여 기간', width: 200, text: (s) => s.cabinetPeriod } : { header: '소속', width: 200, text: (s) => s.department }],
    rowId: (s) => s.studentId, rowHeight: 35, onDouble: confirm,
  });
  const filter = () => {
    const q = search.value.trim().toLowerCase();
    grid.setRows(q ? students.filter((s) => s.name.toLowerCase().includes(q) || s.studentId.toLowerCase().includes(q)) : students);
  };
  search.addEventListener('input', filter);
  filter();
  m.box.append(
    closeButton(16, m.close, { top: '30px', right: '30px' }),
    h('div', { class: 'modal-title', style: { marginBottom: '15px' } }, '학생 선택'),
    h('div', { class: 'row', style: { marginBottom: '15px', gap: '8px' } }, search, actionBtn('검색', filter, { icon: 'search', cls: 'mid' })),
    h('div', { class: 'grid-box' }, grid.el),
    h('div', { class: 'row', style: { justifyContent: 'flex-end', gap: '8px', marginTop: '15px' } },
      modalBtn('선택', confirm, { style: { padding: '8px 20px' } }),
      modalBtn('취소', m.close, { cls: 'gray', style: { padding: '8px 20px' } })));
  search.focus();
}

// ---------------------------------------------------------------- 내역
export async function approvalHistory(scope, app) {
  const load = () => get(`/api/history?scope=${encodeURIComponent(scope)}`);
  const m = modal({ width: 900, height: 520 });
  const grid = dataGrid({
    cols: [
      { header: '구분', width: 70, text: (a) => a.tabType }, { header: '신청 일자', width: 120, text: (a) => a.requestDate },
      { header: '학번', width: 85, text: (a) => a.studentId }, { header: '이름', width: 75, text: (a) => a.studentName },
      { header: '소속', width: 130, text: (a) => a.department }, { header: '상태', width: 80, text: (a) => a.status },
      { header: '대기 목록으로 복구', stretch: true, minWidth: 100, cell: (a) => h('div', { class: 'cell-center', style: { padding: '0 2px' } },
        modalBtn('되돌리기', async () => {
          await post(`/api/history/${a.id}/restore`, { key: app.viewKey() });
          m.close();
          app.switchTab({ 상상Lab: 'sangsanglab', 기자재: 'equipment' }[a.tabType] || 'cabinet');
        }, { style: { background: '#3B82F6', padding: '4px 12px', fontSize: '12px', width: '100%' } })) },
    ],
    rowHeight: 40,
  });
  grid.setRows((await load()).rows);
  m.box.append(closeButton(16, m.close, { top: '35px', right: '35px' }),
    h('div', { class: 'modal-title', style: { marginBottom: '20px' } }, scope ? `${scope} 승인/반려 내역 확인` : '승인/반려 내역 확인'),
    h('div', { class: 'grid-box' }, grid.el));
}

export async function rentalHistory() {
  const { rows } = await get('/api/rentals/history');
  const m = modal({ width: 900, height: 520 });
  const grid = dataGrid({
    cols: [
      { header: '대여자 이름', width: 120, text: (r) => r.studentName }, { header: '대여 기자재', width: 250, text: (r) => r.displayEquipment },
      { header: '대여일', width: 130, text: (r) => r.rentalDate }, { header: '반납 기한', width: 130, text: (r) => r.dueDate },
      { header: '반납 여부', stretch: true, minWidth: 100, cell: (r) => h('div', { class: 'cell-center', style: { fontWeight: 700, color: r.isReturned ? '#10B981' : '#2563EB' } }, r.isReturned ? '반납 완료' : '대여 중') },
    ],
    rowHeight: 40,
  });
  grid.setRows(rows);
  m.box.append(closeButton(18, m.close, { top: '35px', right: '35px' }),
    h('div', { class: 'modal-title', style: { marginBottom: '20px' } }, '기자재 대여 내역 확인'),
    h('div', { class: 'grid-box' }, grid.el));
}

// ---------------------------------------------------------------- 기간 만료
function expiredDialog(scope, today, items) {
  return dialog({
    title: `${scope} 기간 만료 정리`, width: 520,
    build(c, done) {
      const boxes = items.map((it) => ({ key: it.key, cb: h('input', { type: 'checkbox', checked: true }), label: it.label }));
      const all = h('input', { type: 'checkbox', checked: true, onchange: () => boxes.forEach((b) => { b.cb.checked = all.checked; }) });
      c.append(
        h('div', { style: { fontSize: '16px', fontWeight: 700, color: '#111827', marginBottom: '6px' } }, icon('clock', 16), ` ${scope} — 기간이 지난 항목 ${items.length}건`),
        h('div', { style: { color: '#6B7280', marginBottom: '14px' } }, `기준일 ${today} 보다 기간이 먼저 끝난 항목입니다. 삭제할 항목을 선택해 주세요.`),
        h('label', { style: { display: 'block', fontWeight: 700, marginBottom: '8px' } }, all, ' 전체 선택'),
        h('div', { class: 'list-box', style: { maxHeight: '280px', marginBottom: '18px' } },
          boxes.map((b) => h('label', { style: { display: 'block', margin: '4px' } }, b.cb, ` ${b.label}`))),
        h('div', { style: { display: 'flex', justifyContent: 'flex-end', gap: '8px' } },
          h('button', { class: 'btn-wpf colored', style: { width: '100px', height: '34px', background: '#EF4444' }, onclick: run(async () => {
            const keys = boxes.filter((b) => b.cb.checked).map((b) => b.key);
            if (!keys.length) { await warn('삭제할 항목을 최소 하나 이상 선택해 주세요.', '선택 확인'); return; }
            done(keys);
          }) }, '선택 삭제'),
          h('button', { class: 'btn-wpf colored', style: { width: '100px', height: '34px', background: '#6B7280' }, onclick: () => done([]) }, '유지')));
    },
  }).then((keys) => keys || []);
}

function expiryWarning(scope, today, rows) {
  const unit = scope === '캐비닛' ? '캐비닛' : '기자재';
  return dialog({
    title: `${unit} 대여 기간 만료/임박 안내`, width: 550,
    build(c, done) {
      const firstWidth = scope === '캐비닛' ? '80px' : '140px';
      c.append(
        h('div', { style: { fontSize: '16px', fontWeight: 700, color: '#DC2626', marginBottom: '6px' } }, icon('warn', 16), ` ${unit} 대여 기간 만료 및 임박 (${rows.length}건)`),
        h('div', { style: { color: '#6B7280', marginBottom: '14px', whiteSpace: 'pre-line' } }, `기준일: ${today}\n대여 기간이 만료되었거나 7일 이하로 남은 ${unit} 목록입니다.`),
        h('div', { class: 'list-box', style: { maxHeight: '350px', marginBottom: '16px' } }, rows.map((r) => {
          const [status, color] = r.days < 0 ? [`만료 (${Math.abs(r.days)}일 경과)`, '#DC2626']
            : r.days === 0 ? ['오늘 만료 (D-Day)', '#D97706'] : [`${r.days}일 남음`, '#2563EB'];
          return h('div', { style: { display: 'flex', margin: '4px 6px', alignItems: 'center' } },
            h('b', { style: { width: firstWidth, flex: 'none', color: '#374151', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' } }, r.first),
            h('span', { style: { flex: 1, minWidth: 0, color: '#4B5563', overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis' } }, r.info),
            h('b', { style: { width: '120px', flex: 'none', textAlign: 'right', color } }, status));
        })),
        h('div', { style: { display: 'flex', justifyContent: 'flex-end' } },
          h('button', { class: 'btn-wpf colored', style: { width: '100px', height: '34px', background: '#4F46E5' }, onclick: () => done(true) }, '닫기')));
    },
  });
}

// 탭을 열 때 — 기간이 지난 항목 정리 → 만료 임박 안내 순서
export async function runChecks(scope, key, app) {
  const c = await get(`/api/checks?scope=${encodeURIComponent(scope)}&key=${encodeURIComponent(key)}`);
  if (c.expired.length) {
    const keys = await expiredDialog(scope, c.today, c.expired);
    await post('/api/checks/resolve', { scope, key, delete: keys });
    if (keys.length) await app.refresh();
  }
  if (c.warnings.length) await expiryWarning(scope, c.today, c.warnings);
}

// ---------------------------------------------------------------- 얼굴인식 출결 기록
export function faceAttendance() {
  const m = modal({ width: 920, height: 640 });
  let criteria = false;
  const info = h('div', { style: { fontSize: '11px', color: '#6B7280', marginBottom: '12px' } });
  const summary = h('div', { class: 'face-summary-line' });

  const search = h('input', { type: 'text' });
  const from = h('input', { type: 'date' });
  const to = h('input', { type: 'date' });
  const quick = (tag, label) => actionBtn(label, async () => {
    const r = await get(`/api/face/quick-range?tag=${tag}`);
    from.value = r.from;
    to.value = r.to;
    await loadRecords();
  }, { cls: 'tiny' });
  const recordFilter = h('div', { class: 'face-filter rec' },
    h('span', { class: 'cap' }, '학번/이름'), search, h('span', { class: 'cap' }, '기간'), from,
    h('span', { style: { color: '#6B7280', margin: '0 6px' } }, '~'), to, h('span', { style: { width: '10px' } }),
    h('div', { class: 'row', style: { gap: '4px' } }, quick('today', '오늘'), quick('week', '이번 주'), quick('month', '이번 달'), quick('all', '전체')));

  const month = h('select');
  const result = h('select', null, [['', '전체'], ['passed', '충족'], ['failed', '미충족'], ['in_progress', '진행 중']].map(([v, t]) => h('option', { value: v }, t)));
  const critSearch = h('input', { type: 'text' });
  const rule = h('div', { class: 'rule' });
  const critFilter = h('div', { class: 'face-filter crit', style: { display: 'none' } },
    h('span', { class: 'cap' }, '월'), month, h('span', { class: 'cap' }, '결과'), result, h('span', { class: 'cap' }, '학번/이름'), critSearch, rule);

  const records = dataGrid({
    cols: [{ header: '학번', width: 110, text: (r) => r.studentId }, { header: '이름', width: 90, text: (r) => r.name },
      { header: '날짜', width: 110, text: (r) => r.date }, { header: '출근', width: 100, text: (r) => r.checkIn },
      { header: '퇴근', width: 100, text: (r) => r.checkOut }, { header: '근무시간', stretch: true, minWidth: 100, text: (r) => r.workTime }],
    rowId: (r) => `${r.studentId}|${r.date}|${r.checkIn}`, rowHeight: 35,
  });
  const recordBox = h('div', { class: 'grid-box' }, records.el);
  const critBox = h('div', { class: 'grid-box', style: { display: 'none' } });

  function fillMonths(months, current) {
    clear(month, months.map((x) => h('option', null, x)));
    month.value = months.includes(current) ? current : months[0];
  }

  async function loadRecords() {
    const q = new URLSearchParams({ q: search.value, date_from: from.value, date_to: to.value });
    const d = await get(`/api/face/records?${q}`);
    info.textContent = d.info;
    records.setRows(d.rows);
    summary.textContent = d.summary;
    if (!month.options.length) fillMonths(d.months, '');
  }

  async function loadCriteria() {
    const q = new URLSearchParams({ month: month.value, result: result.value, q: critSearch.value });
    const d = await get(`/api/face/criteria?${q}`);
    info.textContent = d.info;
    fillMonths(d.months, d.month);
    rule.textContent = d.rule;
    summary.textContent = d.summary;
    const grid = dataGrid({
      cols: [{ header: '학번', width: 95, text: (r) => r.studentId }, { header: '이름', width: 75, text: (r) => r.name },
        ...d.weeks.map((w, i) => ({ header: w, stretch: true, minWidth: 95, text: (r) => r.weeks[i] })),
        { header: '결과', width: 130, text: (r) => r.result }],
      rowId: (r) => r.studentId, rowHeight: 35, headerHeight: 38,
    });
    grid.setRows(d.rows);
    clear(critBox, grid.el);
  }

  const reload = run(() => (criteria ? loadCriteria() : loadRecords()));
  const setMode = (on) => {
    criteria = on;
    recordFilter.style.display = on ? 'none' : '';
    recordBox.style.display = on ? 'none' : '';
    critFilter.style.display = on ? '' : 'none';
    critBox.style.display = on ? '' : 'none';
    btnRecords.style.fontWeight = on ? 400 : 700;
    btnCriteria.style.fontWeight = on ? 700 : 400;
    reload();
  };
  const btnRecords = actionBtn('기록 보기', () => setMode(false), { icon: 'clipboard', cls: 'mid' });
  const btnCriteria = actionBtn('월간 기준 확인', () => setMode(true), { icon: 'check', cls: 'mid' });
  for (const el of [search, from, to]) el.addEventListener('input', reload);
  for (const el of [month, result]) el.addEventListener('change', reload);
  critSearch.addEventListener('input', reload);

  m.box.append(closeButton(18, m.close, { top: '35px', right: '35px' }),
    h('div', { class: 'row', style: { marginBottom: '4px' } },
      h('div', { class: 'modal-title' }, '얼굴인식 출결 기록'),
      h('span', { style: { width: '15px' } }), actionBtn('새로고침', reload, { icon: 'refresh', cls: 'mid' }),
      h('span', { style: { width: '15px' } }), btnRecords, h('span', { style: { width: '6px' } }), btnCriteria),
    info, recordFilter, critFilter, summary, recordBox, critBox);
  setMode(false);
}
