"""
화면(Qt/웹)에 묶이지 않는 공용 로직 — 데스크톱 프로그램과 웹 서버가 같이 쓴다.
좌석 배치표, 좌석 정보 가리기, 응답 시트·대여 현황 파일 읽기.
"""
from __future__ import annotations

import datetime
from typing import Optional

from . import io_import as ioimp
from .models import RentalItem, StudentInfo

TEMPLATE_NAME = "2026-여름방학_기자제 (노트북(HP OMEN 게이밍 노트북) 대여 현황서양식.xlsx"

# (좌석번호, 행, 열, 열 병합, 회색 줄) — C# RenderSeatGrid의 positions 그대로 (-1 = 기둥)
POSITIONS = [
    (1, 0, 0, 1, False), (2, 0, 1, 1, False), (3, 0, 2, 1, False), (4, 0, 4, 1, False), (5, 0, 5, 1, False), (6, 0, 6, 1, False),
    (7, 1, 0, 1, False), (8, 1, 1, 1, False), (9, 1, 2, 1, False), (10, 1, 4, 1, False), (11, 1, 5, 1, False), (12, 1, 6, 1, False),
    (13, 2, 0, 1, False), (14, 2, 1, 1, False), (15, 2, 2, 1, False), (16, 2, 4, 1, False), (17, 2, 5, 1, False), (18, 2, 6, 1, False),
    (19, 3, 0, 1, False), (20, 3, 1, 1, False), (21, 3, 2, 1, False), (22, 3, 4, 1, False), (23, 3, 5, 1, False), (-1, 3, 6, 2, False),
    (24, 4, 0, 1, False), (25, 4, 1, 1, False), (26, 4, 2, 1, False), (27, 4, 4, 1, False), (28, 4, 5, 1, False),
    (29, 5, 0, 1, False), (30, 5, 1, 1, False), (31, 5, 2, 1, False), (32, 5, 4, 1, False), (33, 5, 5, 1, False), (34, 5, 6, 1, False), (35, 5, 7, 1, False),
    (36, 6, 0, 1, False), (37, 6, 1, 1, False), (38, 6, 2, 1, False), (39, 6, 4, 1, False), (40, 6, 5, 1, False), (41, 6, 6, 1, False), (42, 6, 7, 1, False),
    (43, 7, 0, 1, True), (44, 7, 1, 1, True), (45, 7, 4, 1, True), (46, 7, 5, 1, True), (47, 7, 6, 1, True),
    (48, 8, 0, 1, True), (49, 8, 1, 1, True), (50, 8, 4, 1, True), (51, 8, 5, 1, True), (52, 8, 6, 1, True),
]
COORDS = {n: (r, c) for n, r, c, _span, _g in POSITIONS if n > 0}


def mask_student_id(sid: str) -> str:
    if not sid:
        return sid
    if len(sid) == 8:
        return sid[:2] + "****" + sid[6:]
    if len(sid) <= 2:
        return sid
    hide = min(4, len(sid) - 2)
    start = (len(sid) - hide) // 2
    return sid[:start] + "*" * hide + sid[start + hide:]


def mask_name(name: str) -> str:
    if not name or len(name) < 2:
        return name
    mid = len(name) // 2
    return name[:mid] + "*" + name[mid + 1:]


def parse_sangsanglab_responses(path: str) -> list[StudentInfo]:
    """상상Labs 입실신청 응답 파일 (A 타임스탬프 / B 신청공간 / C 소속 / D 이름 / E 학번 / F 연락처 / G 이메일 / H 지도교수)."""
    table = ioimp.read_table(path)
    result: list[StudentInfo] = []
    seen: set[str] = set()
    for v in table:
        def cell(i):
            return ioimp.cell_str(ioimp.cell_at(v, i))
        space, dept, name, id_raw = cell(1), cell(2), cell(3), cell(4)
        contact = ioimp.normalize_phone(ioimp.cell_at(v, 5))
        email, advisor = cell(6), cell(7)
        if "이름을 작성" in name or "소속을 작성" in dept or "학번" in id_raw or "공간을 선택" in space:
            continue
        sid = ioimp.normalize_student_id(ioimp.cell_at(v, 4))
        if not name.strip() and not sid.strip():
            continue
        if space and "상상" not in space and "U301" not in space:
            continue
        if sid:
            if sid in seen:
                continue
            seen.add(sid)
        advisor = advisor.replace("교수님", "").replace("교수", "").strip()
        result.append(StudentInfo(student_id=sid, name=name, department=dept.strip() or "소프트웨어전공",
                                  email=email, contact=contact, advisor=advisor))
    return result


def parse_cabinet_rows(table: list[list[object]], default_period: str) -> list[tuple[int, str, str, str, str]]:
    """
    캐비닛 배정 파일의 (번호, 학번, 이름, 소속, 대여 기간) 목록.
    이 프로그램이 추출한 파일은 대여기간이 일곱째 칸이라, 제목 행에 '대여기간'이 있으면 그 칸을 읽는다.
    제목 행이 없으면 번호·학번·이름·소속·기간 순서로 본다.
    """
    period_col = 4
    rows = []
    for v in table:
        if len(v) < 2:
            continue
        c0 = ioimp.cell_str(v[0])
        if c0 in ("CabinetNumber", "캐비닛번호"):
            period_col = ioimp.find_col([ioimp.cell_str(c) for c in v], "대여기간", "대여 기간", "Period")
            continue
        try:
            num = int(float(c0))
        except ValueError:
            continue
        if not 1 <= num <= 48:
            continue
        sid = ioimp.normalize_student_id(ioimp.cell_at(v, 1))
        name = ioimp.cell_str(ioimp.cell_at(v, 2))
        dept = ioimp.cell_str(ioimp.cell_at(v, 3)) if len(v) > 3 else "소프트웨어융합학과"
        period = ioimp.cell_str(ioimp.cell_at(v, period_col)) if 0 <= period_col < len(v) else ""
        rows.append((num, sid, name, dept, period or default_period))
    return rows


def _parse_date(s: str) -> Optional[datetime.date]:
    if not s:
        return None
    s = s.strip()
    try:
        return datetime.datetime.fromisoformat(s).date()
    except ValueError:
        pass
    head = s.split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%y.%m.%d"):
        try:
            return datetime.datetime.strptime(head, fmt).date()
        except ValueError:
            continue
    return None


def import_rentals(path: str, target_label: str, is_mainframe: bool, today: datetime.date):
    """대여 현황 엑셀/CSV — 이 프로그램이 추출한 양식과 '이름·학과·학년…' 현황표 양식을 모두 읽는다."""
    table = ioimp.read_table(path)
    header_row = -1
    for i in range(min(len(table), 10)):
        texts = [ioimp.cell_str(c) for c in table[i]]
        if any("학번" in t for t in texts) and any(("성명" in t or "이름" in t) for t in texts):
            header_row = i
            break
    if header_row < 0:
        raise ValueError("학번·성명(이름) 열을 찾지 못했습니다. 대여 현황 양식의 엑셀/CSV 파일인지 확인해주세요.")
    header = [ioimp.cell_str(c) for c in table[header_row]]
    f = ioimp.find_col
    c_id, c_name = f(header, "학번"), f(header, "성명", "이름")
    c_dept, c_level = f(header, "전공", "학과", "소속"), f(header, "학년")
    c_phone, c_adv = f(header, "연락처", "전화"), f(header, "지도교수")
    c_equip, c_unit = f(header, "대여품목", "품목", "기자재"), f(header, "품목번호", "개체번호")
    c_qty, c_extra = f(header, "수량"), f(header, "추가 대여물품")
    c_loc, c_purpose, c_rem = f(header, "사용장소"), f(header, "사용목적"), f(header, "특이사항")
    c_rent, c_due, c_ret = f(header, "대여일", "대여날짜"), f(header, "반납예정"), f(header, "반납일")
    if c_ret == c_due:
        c_ret = -1

    imported, skipped = [], 0
    for row in table[header_row + 1:]:
        def cell(i):
            return ioimp.cell_str(ioimp.cell_at(row, i))
        sid = ioimp.normalize_student_id(ioimp.cell_at(row, c_id))
        name = cell(c_name)
        if not sid or not any(ch.isdigit() for ch in sid) or not name:
            continue
        equip = cell(c_equip)
        if equip and ("노트북" in equip) == is_mainframe:
            skipped += 1
            continue
        level = cell(c_level)
        if level.replace(".0", "").isdigit():
            level = level.replace(".0", "") + "학년"
        qty_t = cell(c_qty).replace(".0", "")
        rental_date = _parse_date(cell(c_rent)) or today
        due = _parse_date(cell(c_due))
        period = (due - rental_date).days if due else 7
        if period <= 0:
            period = 7
        ret = _parse_date(cell(c_ret)) if c_ret >= 0 else None
        unit = cell(c_unit).replace(".0", "")
        equip_type = f"{target_label} (No. {unit})" if unit.isdigit() else target_label
        imported.append(RentalItem(
            student_id=sid, student_name=name, department=cell(c_dept), year_level=level,
            phone=ioimp.normalize_phone(ioimp.cell_at(row, c_phone)),
            advisor=cell(c_adv).replace("교수님", "").replace("교수", "").strip(),
            equipment_type=equip_type, quantity=int(qty_t) if qty_t.isdigit() else 1,
            extra_items=cell(c_extra), location=cell(c_loc) or "DSU 창의공간",
            purpose=cell(c_purpose) or "개인 실습", remarks=cell(c_rem),
            rental_date=rental_date, rental_period_days=period, return_date=ret, is_returned=ret is not None,
        ))
    return imported, skipped
