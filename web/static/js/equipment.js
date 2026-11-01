// [기자재 현황] — 신청 현황, 상태 관리(고장/수리/기타), 본체·노트북 대여 현황.
import {
  h, clear, icon, get, post, warn, run, dataGrid, dialog, line, actionBtn, flatBtn, alertCard, pickFile, upload, download,
} from './core.js';
import { approvalHistory, rentalHistory } from './dialogs.js';

const MAINFRAME = '본체 (HP Z2 G9)';
const LAPTOP = '노트북(HP OMEN 게이밍 노트북)';
const DOT = { overdue: '#EF4444', warning: '#F59E0B', ok: '#10B981' };

export function createEquipment(app) {
  const page = h('div', { class: 'page-body' });
  const alert = alertCard('clock', '기자재 승인 대기', 'orange', '빠른 확인 필요', () => app.switchTab('equipment'));
  const search = h('input', { type: 'text', style: { width: '120px' } });
  let data = null;

  const approvals = dataGrid({
    cols: [
      { header: '신청 일자', width: 110, text: (a) => a.requestDate }, { header: '학번', width: 85, text: (a) => a.studentId },
      { header: '이름', width: 70, text: (a) => a.studentName }, { header: '소속', width: 100, text: (a) => a.department },
      { header: '대여품목', width: 120, text: (a) => a.equipmentType }, { header: '반납예정일', width: 90, text: (a) => a.dueDate },
      { header: '지도교수', width: 85, text: (a) => a.advisor }, { header: '상태', width: 65, text: (a) => a.status },
      { header: '대여 처리', stretch: true, minWidth: 80, cell: (a) => flatBtn('대여', '#10B981', async () => {
        await post(`/api/approvals/${a.id}/approve`, {});
        await app.refresh();
      }, { cls: 'fill-btn' }) },
    ],
    rowHeight: 40, alternating: '#F3F4F6',
  });

  const issues = dataGrid({
    cols: [
      { header: '등록일', width: 80, text: (i) => i.reportDate }, { header: '기기', width: 95, text: (i) => i.displayUnit },
      { header: '구분', width: 55, cell: (i) => h('span', { class: 'badge', style: { background: { 고장: '#FEE2E2', 수리: '#FEF3C7' }[i.issueType] || '#E5E7EB' } }, i.issueType) },
      { header: '내용', stretch: true, minWidth: 80, text: (i) => i.displayDetail },
    ],
    rowHeight: 34, alternating: '#F3F4F6', fontSize: 11,
    details: (i) => h('div', { class: 'issue-detail' },
      h('div', { style: { flex: 1, minWidth: 0 } }, h('b', { style: { color: '#111827' } }, i.displayUnit),
        h('div', { style: { color: '#4B5563', marginTop: '3px' } }, i.displayDetail)),
      flatBtn('처리 완료', '#10B981', async () => { await post(`/api/issues/${i.id}/complete`, {}); await app.refresh(); }, { style: { padding: '5px 12px' } })),
  });

  function rentalGrid() {
    return dataGrid({
      cols: [
        { header: '상태', width: 40, cell: (r) => h('div', { class: 'cell-center' }, h('span', { class: 'dot', style: { background: DOT[r.state] } })) },
        { header: '수량', width: 45, text: (r) => r.quantity }, { header: '대여자', width: 65, text: (r) => r.studentName },
        { header: '대여품목', stretch: true, minWidth: 110, text: (r) => r.displayEquipment }, { header: '학번', width: 80, text: (r) => r.studentId },
        { header: '대여일', width: 80, text: (r) => r.rentalDate }, { header: '반납예정', width: 80, text: (r) => r.dueDate },
        { header: '작업', width: 50, cell: (r) => h('div', { class: 'cell-center' }, flatBtn('반납', '#EF4444', async () => {
          await post(`/api/rentals/${r.id}/return`, {});
          await app.refresh();
        }, { cls: 'fill-btn', style: { padding: '2px 8px', fontSize: '11px' } })) },
      ],
      rowHeight: 40, alternating: '#F9FAFB', fontSize: 11, multi: true,
      details: (r) => h('div', { class: 'detail-box' },
        h('b', null, '전공 / 학년: '), h('span', null, r.deptYear), h('b', null, '연락처 / 지도교수: '), h('span', null, r.phoneAdvisor),
        h('b', null, '사용 장소: '), h('span', null, r.location), h('b', null, '사용 목적: '), h('span', null, r.purpose),
        h('b', null, '추가 물품: '), h('span', null, r.extraItems), h('b', null, '특이 사항: '), h('span', null, r.remarks)),
    });
  }
  const gridMf = rentalGrid();
  const gridLt = rentalGrid();
  const countMf = h('div', { class: 'cnt' });
  const countLt = h('div', { class: 'cnt' });

  const column = (iconName, title, counts, grid, kind) => h('div', { class: 'equip-col' },
    h('div', { class: 'equip-head' }, h('div', { class: 'ttl' }, icon(iconName, 16), ` ${title} 대여 현황`), counts,
      h('div', { class: 'btns' },
        actionBtn('엑셀 추출', () => download(`/api/rentals/export?kind=${kind}`), { icon: 'upload', iconSize: 12, cls: 'small' }),
        actionBtn('엑셀 가져오기', () => importFile(kind), { icon: 'download', iconSize: 12, cls: 'small' }))),
    h('div', { class: 'grid-card' }, grid.el));

  async function importFile(kind) {
    const file = await pickFile('.xlsx,.csv');
    if (!file) return;
    await upload('/api/rentals/import', file, { kind });
    await app.refresh();
  }

  async function deleteSelected() {
    const ids = [...gridMf.selectedRows(), ...gridLt.selectedRows()].map((r) => r.id);
    await post('/api/rentals/delete', { ids });
    await app.refresh();
  }

  page.append(
    h('div', { class: 'equip-top' }, alert, h('div', { class: 'spacer' }),
      actionBtn('대여 내역', rentalHistory, { icon: 'clipboard' }), h('span', { style: { width: '8px' } }),
      actionBtn('승인/반려 내역', () => approvalHistory('기자재', app), { icon: 'clipboard' }), h('span', { style: { width: '10px' } }),
      h('span', { style: { fontWeight: 600, color: '#374151', marginRight: '5px' } }, icon('search', 14), ' 검색: '), search, h('span', { style: { width: '10px' } }),
      actionBtn('데이터 선택 삭제', deleteSelected, { icon: 'trash' }), h('span', { style: { width: '6px' } }),
      actionBtn('데이터 양식 다운', () => download('/api/rentals/template'), { icon: 'file' })),
    h('div', { class: 'equip-s1' },
      h('div', { class: 'section' }, '기자재 신청 현황 (구글폼)'),
      h('div', { class: 'row' }, h('div', { class: 'section', style: { flex: 1 } }, '기자재 상태 관리 (고장/수리/기타)'),
        actionBtn('기타', () => addIssue(app), { icon: 'tools', iconSize: 12, cls: 'small' })),
      h('div', { class: 'grid-card' }, approvals.el), h('div', { class: 'grid-card' }, issues.el)),
    h('div', { class: 'section' }, '기자재 대여 현황'),
    h('div', { class: 'equip-cols' }, column('monitor', MAINFRAME, countMf, gridMf, 'mainframe'), column('laptop', LAPTOP, countLt, gridLt, 'laptop')));

  function bind() {
    if (!data) return;
    const q = search.value.trim().toLowerCase();
    const rows = data.rentals.filter((r) => !q || [r.studentName, r.studentId, r.department, r.equipmentType].some((v) => (v || '').toLowerCase().includes(q)));
    gridMf.setRows(rows.filter((r) => r.isMainframe));
    gridLt.setRows(rows.filter((r) => !r.isMainframe));
  }
  search.addEventListener('input', bind);

  const counts = (el, c) => clear(el, '사용가능: ', h('b', { class: 'a' }, `${c.available}개`), '  사용중: ', h('b', { class: 'u' }, `${c.used}개`));

  return {
    el: page,
    async refresh() {
      data = await get('/api/equipment');
      alert.setCount(data.approvals.length);
      approvals.setRows(data.approvals);
      issues.setRows(data.issues);
      counts(countMf, data.mainframe);
      counts(countLt, data.laptop);
      bind();
    },
  };
}

async function addIssue(app) {
  const picked = await dialog({
    title: '기자재 상태 등록', width: 400,
    build(c, done) {
      const equip = h('select', { style: { width: '250px' } }, h('option', { value: '' }, ''),
        h('option', { value: 'mainframe' }, MAINFRAME), h('option', { value: 'laptop' }, LAPTOP));
      const number = h('select', { style: { width: '250px' }, disabled: true });
      const detail = h('textarea', { style: { width: '100%', height: '60px', padding: '5px' } });
      const etc = h('div', { style: { display: 'none', marginTop: '14px' } }, h('b', { style: { color: '#374151' } }, '내용을 직접 적어 주세요'),
        h('div', { style: { height: '6px' } }), detail,
        h('div', { style: { textAlign: 'right', marginTop: '8px' } },
          h('button', { class: 'btn-wpf colored', style: { width: '80px', height: '28px', background: '#2563EB' }, onclick: run(async () => {
            if (!detail.value.trim()) { await warn('내용을 입력해 주세요.'); detail.focus(); return; }
            finish('기타', detail.value.trim());
          }) }, '등록')));
      const typeBtn = (t, color) => h('button', { class: 'btn-wpf colored', style: { width: '95px', height: '34px', background: color, border: 0, marginRight: '8px' }, onclick: () => {
        if (t === '기타') { etc.style.display = ''; detail.focus(); return; }
        etc.style.display = 'none';
        finish(t, '');
      } }, t);
      const types = h('div', { style: { display: 'none', marginTop: '18px' } }, h('b', { style: { color: '#374151' } }, '상태를 고르세요'),
        h('div', { style: { marginTop: '8px' } }, typeBtn('고장', '#EF4444'), typeBtn('수리', '#F59E0B'), typeBtn('기타', '#6B7280')));
      const finish = (issueType, text) => done({ kind: equip.value, unit: number.value, issueType, detail: text });

      equip.addEventListener('change', run(async () => {
        types.style.display = 'none';
        etc.style.display = 'none';
        clear(number);
        number.disabled = true;
        if (!equip.value) return;
        const { numbers } = await get(`/api/issues/options?kind=${equip.value}`);
        if (!numbers.length) { number.append(h('option', null, '선택 가능한 번호 없음 (대여 중 / 이미 등록됨)')); return; }
        number.append(h('option', { value: '' }, ''), ...numbers.map((n) => h('option', null, n)));
        number.disabled = false;
      }));
      number.addEventListener('change', () => {
        types.style.display = number.value ? '' : 'none';
        if (!number.value) etc.style.display = 'none';
      });
      c.append(line('기자재 종류:', 90, equip), line('기자재 번호:', 90, number), types, etc,
        h('div', { style: { textAlign: 'right', marginTop: '14px' } },
          h('button', { class: 'btn-wpf', style: { width: '80px', height: '28px' }, onclick: () => done(null) }, '취소')));
    },
  });
  if (!picked) return;
  await post('/api/issues', picked);
  await app.refresh();
}
