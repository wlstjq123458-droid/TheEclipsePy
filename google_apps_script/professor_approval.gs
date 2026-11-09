/**
 * 창공시스템 — 지도교수 승인 메일
 *
 * 구글폼 응답 스프레드시트에 붙여서 쓴다 ([확장 프로그램] → [Apps Script]).
 *   1. 폼이 제출되면 지도교수님께 신청 내용과 [승인] [반려] 버튼이 든 메일을 보낸다.
 *   2. 교수님이 버튼을 누르면 확인 화면이 열리고, 거기서 한 번 더 누르면 시트의 '승인상태' 칸에 "승인"/"반려"가 기록된다.
 *   3. 창공시스템은 동기화할 때 '승인상태'가 "승인"인 행만 대기 목록에 넣는다.
 *
 * 설정 절차는 같은 폴더의 README.md를 본다.
 */

// ======================================================================== 설정
const CONFIG = {
  // 교수님 이메일을 찾지 못했을 때 대신 받을 관리자 주소 (비워 두면 그런 행은 보내지 않고 기록만 남긴다)
  ADMIN_EMAIL: '',

  // 교수님 이름 → 이메일 목록을 적어 두는 시트 탭 이름
  PROFESSOR_SHEET: '교수목록',

  // 응답이 쌓이는 시트 탭 이름 (비우면 첫 번째 탭)
  RESPONSE_SHEET: '',

  // 메일을 보낼 신청. '원하는 공간' 질문이 있는 시트(상상Lab 폼)는 그 답에 아래 낱말이 들어간 행만 보낸다.
  // 그 질문이 없는 시트(기자재 폼, 캐비닛 폼)는 모든 행에 보낸다.
  // 창공시스템 [설정]의 "지도교수 승인을 거친 신청만 받기"와 맞춰야 한다.
  REQUIRE_FOR: ['기자재', '장비', '캐비닛', '캐비넷', '사물함', '상상', 'lab', '랩'],

  // 이 시트의 신청을 메일 제목에 뭐라고 부를지 ('원하는 공간' 답이 있으면 그 답을 쓴다)
  REQUEST_LABEL: '창공시스템',

  // 웹 앱 주소 — [배포] → [배포 관리]에 나오는 '웹 앱' URL(끝이 /exec)을 붙여 넣는다.
  // 비워 두면 자동으로 찾지만, 실행 환경에 따라 교수님이 열 수 없는 시험용 주소(/dev)가 나올 수 있어 넣어 두는 것이 안전하다.
  WEB_APP_URL: '',

  // 결정이 없으면 며칠 뒤 다시 보낼지, 최대 몇 번까지
  REMIND_AFTER_DAYS: 2,
  MAX_REMINDERS: 2,

  SENDER_NAME: '창공시스템',
};

// 이 스크립트가 응답 시트 오른쪽에 붙이는 칸.
// 창공시스템이 열 제목의 낱말로 폼 질문을 찾기 때문에 '메일·교수·기간·반납·이름' 같은 낱말을 넣지 않는다.
const COL = {
  STATUS: '승인상태',     // 대기 / 승인 / 반려 — 창공시스템이 읽는 칸
  CODE: '확인코드',       // 버튼 링크에 들어가는 일회용 값
  TO: '수신자',
  SENT: '발송시각',
  REMIND: '재발송횟수',
  DONE: '처리시각',
  REASON: '반려사유',     // 창공시스템이 반려 내역에 함께 적는다
};
const STATUS_WAITING = '대기';
const STATUS_APPROVED = '승인';
const STATUS_REJECTED = '반려';
const HELPER_HEADERS = Object.keys(COL).map(function (k) { return COL[k]; });

// ======================================================================== 메뉴 / 설치
function onOpen() {
  SpreadsheetApp.getUi().createMenu('창공시스템')
    .addItem('처음 설정 (트리거·칸 만들기)', 'setup')
    .addItem('선택한 행에 승인 메일 보내기', 'sendSelectedRows')
    .addItem('아직 안 보낸 행 모두 보내기', 'sendAllUnsent')
    .addToUi();
}

/** 처음 한 번 실행 — 필요한 칸·교수목록 탭·트리거를 만든다. 여러 번 실행해도 된다. */
function setup() {
  requireSheetUser_();
  const ss = SpreadsheetApp.getActive();
  const sheet = responseSheet_();
  ensureColumns_(sheet);

  if (!ss.getSheetByName(CONFIG.PROFESSOR_SHEET)) {
    const tab = ss.insertSheet(CONFIG.PROFESSOR_SHEET);
    tab.getRange(1, 1, 1, 2).setValues([['이름', '이메일']]);
  }

  // 같은 트리거가 겹치지 않게 지우고 다시 만든다
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (['onFormSubmitHandler', 'sendReminders'].indexOf(t.getHandlerFunction()) >= 0) ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('onFormSubmitHandler').forSpreadsheet(ss).onFormSubmit().create();
  ScriptApp.newTrigger('sendReminders').timeBased().everyDays(1).atHour(9).create();

  const problems = [];
  if (!webAppUrl_()) problems.push('· 웹 앱 주소를 찾지 못했습니다. [배포] → [배포 관리]의 웹 앱 URL(끝이 /exec)을 CONFIG.WEB_APP_URL에 넣고 저장하세요.');
  if (professorMap_().size === 0) problems.push(`· '${CONFIG.PROFESSOR_SHEET}' 탭에 교수님 이름과 이메일을 적어 주세요.`);
  if (!CONFIG.ADMIN_EMAIL) problems.push('· CONFIG.ADMIN_EMAIL(관리자 주소)이 비어 있습니다. 교수님 이메일을 못 찾은 신청은 보내지 못합니다.');
  notify_('설정 완료' + (problems.length ? '\n\n확인할 것:\n' + problems.join('\n') : '\n\n새 폼 응답부터 지도교수님께 메일이 갑니다.'));
}

// ======================================================================== 메일 보내기
/** 폼 제출 트리거 — 새로 들어온 행에 메일을 보낸다. */
function onFormSubmitHandler(e) {
  const sheet = responseSheet_();
  if (!e || !e.range || e.range.getSheet().getName() !== sheet.getName()) return;
  withLock_(function () { processRow_(sheet, e.range.getRow(), false); });
}

/** 메뉴 — 선택한 행에 (다시) 보낸다. 이미 승인/반려된 행은 건너뛴다. */
function sendSelectedRows() {
  requireSheetUser_();
  const sheet = responseSheet_();
  const range = sheet.getActiveRange();
  if (!range) return;
  const results = [];
  withLock_(function () {
    for (let r = range.getRow(); r < range.getRow() + range.getNumRows(); r++) {
      if (r > 1) results.push(r + '행: ' + processRow_(sheet, r, true));
    }
  });
  notify_(results.join('\n') || '보낼 행을 선택해 주세요.');
}

/** 메뉴 — 승인이 필요한데 아직 메일을 보내지 않은 행에 모두 보낸다 (스크립트를 붙이기 전 응답 등). */
function sendAllUnsent() {
  requireSheetUser_();
  const sheet = responseSheet_();
  let sent = 0;
  const skipped = [];
  withLock_(function () {
    const cols = ensureColumns_(sheet);
    const rows = sheet.getDataRange().getValues();
    for (let i = 1; i < rows.length; i++) {
      const status = String(rows[i][cols[COL.STATUS]] || '').trim();
      if (rows[i][cols[COL.SENT]] || status === STATUS_APPROVED || status === STATUS_REJECTED) continue;
      const result = processRow_(sheet, i + 1, false);
      if (result === '보냄') sent++;
      else if (result !== '승인 대상 아님') skipped.push((i + 1) + '행: ' + result);
    }
  });
  notify_(`${sent}건 보냈습니다.` + (skipped.length ? '\n\n보내지 못한 행:\n' + skipped.join('\n') : ''));
}

/** 매일 — 결정이 없는 신청을 다시 보낸다. */
function sendReminders() {
  const sheet = responseSheet_();
  withLock_(function () {
    const cols = ensureColumns_(sheet);
    const rows = sheet.getDataRange().getValues();
    const limit = Date.now() - CONFIG.REMIND_AFTER_DAYS * 24 * 3600 * 1000;
    for (let i = 1; i < rows.length; i++) {
      const row = rows[i];
      const sent = row[cols[COL.SENT]];
      const count = Number(row[cols[COL.REMIND]] || 0);
      if (String(row[cols[COL.STATUS]]).trim() !== STATUS_WAITING || !(sent instanceof Date)) continue;
      if (sent.getTime() > limit || count >= CONFIG.MAX_REMINDERS) continue;
      if (sendMail_(sheet, i + 1, cols, true) === '보냄') {
        sheet.getRange(i + 1, cols[COL.REMIND] + 1).setValue(count + 1);
      }
    }
  });
}

/** 한 행 처리. 결과를 사람이 읽을 문구로 돌려준다. */
function processRow_(sheet, rowNumber, force) {
  const cols = ensureColumns_(sheet);
  const row = sheet.getRange(rowNumber, 1, 1, sheet.getLastColumn()).getValues()[0];
  const status = String(row[cols[COL.STATUS]] || '').trim();
  if (status === STATUS_APPROVED || status === STATUS_REJECTED) return '이미 ' + status + '됨';
  if (!needsApproval_(sheet, row)) return '승인 대상 아님';
  if (row[cols[COL.SENT]] && !force) return '이미 보냄';
  if (!row[cols[COL.CODE]]) {
    sheet.getRange(rowNumber, cols[COL.CODE] + 1).setValue(Utilities.getUuid().replace(/-/g, '') + Utilities.getUuid().replace(/-/g, ''));
  }
  sheet.getRange(rowNumber, cols[COL.STATUS] + 1).setValue(STATUS_WAITING);
  return sendMail_(sheet, rowNumber, cols, false);
}

function sendMail_(sheet, rowNumber, cols, isReminder) {
  const header = headerRow_(sheet);
  const row = sheet.getRange(rowNumber, 1, 1, header.length).getValues()[0];
  const url = webAppUrl_();
  if (!url) return '웹 앱 주소(CONFIG.WEB_APP_URL)가 없어 보내지 못함';
  if (MailApp.getRemainingDailyQuota() < 1) return '오늘 메일 발송 한도를 다 써서 보내지 못함 (내일 메뉴로 다시 보내세요)';

  const advisor = cell_(row, header, ['지도교수', '교수']);
  let to = professorMap_().get(normalizeName_(advisor));
  let notice = '';
  if (!to) {
    if (!CONFIG.ADMIN_EMAIL) return `교수님(${advisor || '이름 없음'}) 이메일을 '${CONFIG.PROFESSOR_SHEET}' 탭에서 찾지 못함`;
    to = CONFIG.ADMIN_EMAIL;
    notice = `지도교수 "${advisor || '(빈칸)'}"의 이메일을 '${CONFIG.PROFESSOR_SHEET}' 탭에서 찾지 못해 관리자에게 보냅니다. ` +
             '교수님께 전달하거나 직접 결정해 주세요.';
  }

  const student = [cell_(row, header, ['이름', '성명']), cell_(row, header, ['학번'])].filter(String).join(' · ');
  const label = requestLabel_(row, header);
  const code = row[cols[COL.CODE]];
  const subject = `[${CONFIG.SENDER_NAME}]${isReminder ? ' (다시 알림)' : ''} ${student || '학생'} — ${label} 승인 요청`;
  MailApp.sendEmail({
    to: to,
    subject: subject,
    name: CONFIG.SENDER_NAME,
    htmlBody: mailHtml_(header, row, label, student, notice, url + '?t=' + encodeURIComponent(code)),
  });
  sheet.getRange(rowNumber, cols[COL.TO] + 1).setValue(to);
  sheet.getRange(rowNumber, cols[COL.SENT] + 1).setValue(new Date());
  return '보냄';
}

function mailHtml_(header, row, label, student, notice, link) {
  const lines = header.map(function (h, i) {
    if (!h || HELPER_HEADERS.indexOf(String(h).trim()) >= 0 || row[i] === '' || row[i] === null) return '';
    return `<tr><td style="padding:6px 10px;background:#F3F4F6;font-weight:bold;white-space:nowrap;vertical-align:top">${esc_(h)}</td>` +
           `<td style="padding:6px 10px;white-space:pre-wrap">${esc_(formatValue_(row[i]))}</td></tr>`;
  }).join('');
  const button = function (text, color, action) {
    return `<a href="${esc_(link + '&a=' + action)}" style="display:inline-block;padding:10px 26px;margin-right:8px;border-radius:6px;` +
           `background:${color};color:#fff;font-weight:bold;text-decoration:none">${text}</a>`;
  };
  return `<div style="font-family:'Malgun Gothic',sans-serif;font-size:14px;color:#111827;max-width:640px">` +
    (notice ? `<p style="padding:10px;background:#FEF3C7;border:1px solid #F59E0B">${esc_(notice)}</p>` : '') +
    `<p>교수님, 안녕하세요. ${esc_(student || '학생')}의 <b>${esc_(label)}</b> 신청에 대한 지도교수 승인을 요청드립니다.</p>` +
    `<table style="border-collapse:collapse;border:1px solid #E5E7EB;margin:12px 0">${lines}</table>` +
    `<p>${button('승인', '#10B981', 'approve')}${button('반려', '#EF4444', 'reject')}</p>` +
    `<p style="color:#6B7280;font-size:12px">버튼을 누르면 확인 화면이 열리고, 그 화면에서 한 번 더 누르셔야 처리됩니다.<br>` +
    `이 메일은 ${esc_(CONFIG.SENDER_NAME)}에서 자동으로 보냈습니다. 링크는 이 신청에만 쓸 수 있으니 다른 분께 전달하지 말아 주세요.</p></div>`;
}

// ======================================================================== 승인 화면 (웹 앱)
/** 메일의 버튼 링크가 여는 화면. 링크를 여는 것만으로는 처리되지 않는다 (메일 보안 검사가 링크를 미리 열어 보기 때문). */
function doGet(e) {
  const code = (e && e.parameter && e.parameter.t) || '';
  const action = (e && e.parameter && e.parameter.a) === 'reject' ? 'reject' : 'approve';
  const found = findByCode_(code);
  let body;
  if (!found) {
    body = '<h2>링크가 올바르지 않습니다</h2><p>메일의 버튼을 다시 눌러 주세요. 계속 안 되면 관리자에게 문의해 주세요.</p>';
  } else if (found.status === STATUS_APPROVED || found.status === STATUS_REJECTED) {
    body = `<h2>이미 처리된 신청입니다</h2><p>${esc_(found.student)} — <b>${esc_(found.status)}</b> (${esc_(formatValue_(found.done))})</p>`;
  } else {
    body = `<h2>${esc_(found.label)} 신청</h2><p>${esc_(found.student)}</p>` +
      `<table>${found.lines}</table>` +
      `<p style="margin-top:18px"><label><input type="radio" name="a" value="approve" ${action === 'approve' ? 'checked' : ''}> 승인</label> ` +
      `<label style="margin-left:14px"><input type="radio" name="a" value="reject" ${action === 'reject' ? 'checked' : ''}> 반려</label></p>` +
      `<p id="reasonBox" style="display:${action === 'reject' ? 'block' : 'none'}"><textarea id="reason" rows="3" style="width:100%" placeholder="반려 사유 (선택)"></textarea></p>` +
      `<button id="go" onclick="go()">처리하기</button><p id="msg"></p>` +
      `<script>` +
      `document.querySelectorAll('input[name=a]').forEach(function(r){r.onchange=function(){document.getElementById('reasonBox').style.display=` +
      `document.querySelector('input[name=a]:checked').value==='reject'?'block':'none';};});` +
      `function go(){var b=document.getElementById('go');b.disabled=true;b.textContent='처리 중...';` +
      `google.script.run.withSuccessHandler(function(m){document.getElementById('msg').textContent=m;b.style.display='none';})` +
      `.withFailureHandler(function(err){document.getElementById('msg').textContent='처리하지 못했습니다: '+err.message;b.disabled=false;b.textContent='처리하기';})` +
      `.decide(${JSON.stringify(code)},document.querySelector('input[name=a]:checked').value,document.getElementById('reason').value);}` +
      `</script>`;
  }
  const page = `<!doctype html><html><head><meta charset="utf-8"><style>` +
    `body{font-family:'Malgun Gothic',sans-serif;max-width:640px;margin:24px auto;padding:0 16px;color:#111827}` +
    `td{padding:6px 10px;border-bottom:1px solid #E5E7EB;vertical-align:top;white-space:pre-wrap}td:first-child{font-weight:bold;background:#F9FAFB;white-space:nowrap}` +
    `button{padding:10px 30px;font-size:15px;font-weight:bold;color:#fff;background:#2563EB;border:0;border-radius:6px;cursor:pointer}` +
    `</style></head><body>${body}</body></html>`;
  return HtmlService.createHtmlOutput(page).setTitle(CONFIG.SENDER_NAME + ' 승인')
    .addMetaTag('viewport', 'width=device-width, initial-scale=1');
}

/** 확인 화면의 [처리하기]. 코드가 맞고 아직 결정 전일 때만 기록한다. */
function decide(code, action, reason) {
  return withLock_(function () {
    const found = findByCode_(code);
    if (!found) throw new Error('링크가 올바르지 않습니다.');
    if (found.status === STATUS_APPROVED || found.status === STATUS_REJECTED) return `이미 ${found.status}된 신청입니다.`;
    const status = action === 'reject' ? STATUS_REJECTED : STATUS_APPROVED;
    const sheet = found.sheet;
    sheet.getRange(found.rowNumber, found.cols[COL.STATUS] + 1).setValue(status);
    sheet.getRange(found.rowNumber, found.cols[COL.DONE] + 1).setValue(new Date());
    if (status === STATUS_REJECTED) {
      sheet.getRange(found.rowNumber, found.cols[COL.REASON] + 1).setValue(String(reason || '').slice(0, 500));
    }
    return status === STATUS_APPROVED
      ? '승인했습니다. 창공시스템 관리자에게 전달됩니다. 이 창은 닫으셔도 됩니다.'
      : '반려했습니다. 이 창은 닫으셔도 됩니다.';
  });
}

// ======================================================================== 도우미
function responseSheet_() {
  const ss = SpreadsheetApp.getActive();
  const sheet = CONFIG.RESPONSE_SHEET ? ss.getSheetByName(CONFIG.RESPONSE_SHEET) : ss.getSheets()[0];
  if (!sheet) throw new Error(`응답 시트 '${CONFIG.RESPONSE_SHEET}'를 찾지 못했습니다.`);
  return sheet;
}

function headerRow_(sheet) {
  return sheet.getRange(1, 1, 1, sheet.getLastColumn()).getValues()[0].map(function (h) { return String(h || '').trim(); });
}

/** 도우미 칸을 확인하고 없으면 오른쪽 끝에 만든다. {칸 이름: 0부터 센 열 번호}를 돌려준다. */
function ensureColumns_(sheet) {
  const header = headerRow_(sheet);
  const cols = {};
  // 관리자가 손으로 쓰던 '승인상태'/'승인여부' 칸이 있으면 그 칸을 그대로 쓴다 (창공시스템도 이 순서로 찾는다)
  const statusAt = findHeader_(header, ['승인상태', '승인여부']);
  if (statusAt >= 0) cols[COL.STATUS] = statusAt;
  HELPER_HEADERS.forEach(function (name) {
    if (cols[name] !== undefined) return;
    let at = header.indexOf(name);
    if (at < 0) {
      at = header.length;
      sheet.getRange(1, at + 1).setValue(name);
      header.push(name);
    }
    cols[name] = at;
  });
  return cols;
}

function findHeader_(header, keywords) {
  for (let k = 0; k < keywords.length; k++) {
    for (let i = 0; i < header.length; i++) {
      if (normalize_(header[i]).indexOf(normalize_(keywords[k])) >= 0) return i;
    }
  }
  return -1;
}

function cell_(row, header, keywords) {
  const at = findHeader_(header.map(function (h) { return HELPER_HEADERS.indexOf(h) >= 0 ? '' : h; }), keywords);
  return at >= 0 ? String(row[at] === null || row[at] === undefined ? '' : row[at]).trim() : '';
}

/** '원하는 공간' 질문이 있으면 그 답으로, 없으면 시트 전체를 승인 대상으로 본다. */
function needsApproval_(sheet, row) {
  const header = headerRow_(sheet);
  const at = findHeader_(header, ['공간을선택', '공간']);
  if (at < 0) return true;
  const space = normalize_(row[at]);
  return CONFIG.REQUIRE_FOR.some(function (k) { return space.indexOf(normalize_(k)) >= 0; });
}

function requestLabel_(row, header) {
  return cell_(row, header, ['공간을선택', '공간']) || CONFIG.REQUEST_LABEL;
}

function findByCode_(code) {
  if (!code || String(code).length < 32) return null;
  const sheet = responseSheet_();
  const cols = ensureColumns_(sheet);
  const header = headerRow_(sheet);
  const rows = sheet.getDataRange().getValues();
  for (let i = 1; i < rows.length; i++) {
    if (String(rows[i][cols[COL.CODE]]) !== String(code)) continue;
    const row = rows[i];
    const lines = header.map(function (h, j) {
      if (!h || HELPER_HEADERS.indexOf(h) >= 0 || row[j] === '' || row[j] === null) return '';
      return `<tr><td>${esc_(h)}</td><td>${esc_(formatValue_(row[j]))}</td></tr>`;
    }).join('');
    return {
      sheet: sheet, rowNumber: i + 1, cols: cols, lines: lines,
      status: String(row[cols[COL.STATUS]] || '').trim(), done: row[cols[COL.DONE]],
      student: [cell_(row, header, ['이름', '성명']), cell_(row, header, ['학번'])].filter(String).join(' · '),
      label: requestLabel_(row, header),
    };
  }
  return null;
}

/** 교수목록 탭 → Map(정리한 이름 → 이메일) */
function professorMap_() {
  const tab = SpreadsheetApp.getActive().getSheetByName(CONFIG.PROFESSOR_SHEET);
  const map = new Map();
  if (!tab || tab.getLastRow() < 2) return map;
  tab.getRange(2, 1, tab.getLastRow() - 1, 2).getValues().forEach(function (r) {
    const name = normalizeName_(r[0]);
    const email = String(r[1] || '').trim();
    if (name && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) map.set(name, email);
  });
  return map;
}

/** "김동현 교수님" → "김동현" */
function normalizeName_(name) {
  return String(name || '').replace(/\s+/g, '').replace(/교수님|교수|님$/g, '');
}

function normalize_(s) {
  return String(s === null || s === undefined ? '' : s).replace(/[\s*:~,.]/g, '').toLowerCase();
}

function formatValue_(v) {
  if (v instanceof Date) return Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm');
  return String(v === null || v === undefined ? '' : v);
}

function esc_(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

function webAppUrl_() {
  const fixed = String(CONFIG.WEB_APP_URL || '').trim();
  if (fixed) return fixed;
  // 편집기·트리거에서 실행하면 편집자만 열 수 있는 시험용 주소(/dev)가 나올 때가 있다 — 그런 주소는 쓰지 않는다
  const url = ScriptApp.getService().getUrl() || '';
  return /\/exec$/.test(url) ? url : '';
}

/**
 * 메뉴용 함수는 시트를 연 사람만 실행할 수 있게 한다.
 * 웹 앱 화면에서는 개발자 도구로 공개 함수를 직접 부를 수 있는데, 그때는 실행자가 확인되지 않으므로 막는다.
 */
function requireSheetUser_() {
  const active = Session.getActiveUser().getEmail();
  if (!active || active !== Session.getEffectiveUser().getEmail()) {
    throw new Error('스프레드시트에서 직접 실행해 주세요.');
  }
}

function withLock_(fn) {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    return fn();
  } finally {
    lock.releaseLock();
  }
}

function notify_(message) {
  try {
    SpreadsheetApp.getUi().alert(message);
  } catch (err) {
    Logger.log(message);   // 트리거처럼 화면이 없는 곳에서 실행되면 로그로 남긴다
  }
}
