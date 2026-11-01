"""
창공시스템의 동작을 HTTP와 무관하게 모아 둔 곳 — C# MainWindow의 처리 순서와 문구를 그대로 옮겼다.

데스크톱은 처리 도중 확인창을 띄우고 답을 기다리지만 웹은 그럴 수 없다. 그래서 확인이 필요하면
Confirm/Choose 예외로 질문을 브라우저에 돌려보내고, 브라우저가 답을 붙여 같은 요청을 다시 보낸다.
질문을 던지기 전에는 저장하지 않으므로, 다시 보내도 같은 일이 두 번 일어나지 않는다.

모든 공개 메서드는 하나의 잠금 안에서 돈다 — 관리자가 여럿이어도 동작이 한 번에 하나씩만 적용되므로
데이터가 꼬이지 않는다.
"""
from __future__ import annotations

import datetime
import functools
import io
import json
import logging
import os
import random
import re
import shutil
import threading
import time
from typing import Iterable, Optional

from app import config, face_integration as fi, google_integration as gi, io_import as ioimp, storage
from app.constants import (
    LAPTOP_LABEL, MAINFRAME_LABEL, TOTAL_CABINETS, TOTAL_LAPTOP, TOTAL_MAINFRAME, format_period,
)
from app.context import AppContext, is_approved_on_sheet, prefer
from app.logic import COORDS, POSITIONS, TEMPLATE_NAME, import_rentals, parse_cabinet_rows, parse_sangsanglab_responses
from app.models import (
    ApprovalRequest, CabinetAllocation, EquipmentIssue, MemoItem, RentalItem, SEASON_NAMES, Seat, SeasonPeriod,
    StudentInfo, default_seasons_for,
)

log = logging.getLogger(__name__)

KST = datetime.timezone(datetime.timedelta(hours=9))
SEAT_KEY = re.compile(r"^\d{4}_(1학기|여름방학|2학기|겨울방학)$")
BOOL_RESULT = {"passed": fi.PASSED, "failed": fi.FAILED, "in_progress": fi.IN_PROGRESS}


class Problem(Exception):
    """사용자에게 그대로 보여줄 안내(경고창). 처리는 중단된다."""

    def __init__(self, message: str, title: str = "알림", level: str = "warning"):
        super().__init__(message)
        self.message, self.title, self.level = message, title, level


class Confirm(Exception):
    """예/아니요를 물어야 할 때. 브라우저가 '예'를 누르면 key를 confirmed에 넣어 다시 보낸다."""

    def __init__(self, key: str, message: str, title: str, warn: bool = False):
        super().__init__(message)
        self.key, self.message, self.title, self.warn = key, message, title, warn


class Choose(Exception):
    """번호 선택 같은 입력창이 필요할 때. 브라우저가 고른 값을 붙여 다시 보낸다."""

    def __init__(self, kind: str, data: dict):
        super().__init__(kind)
        self.kind, self.data = kind, data


def locked(fn):
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return fn(self, *args, **kwargs)
    return wrapper


def parse_date(text, field: str = "날짜") -> datetime.date:
    try:
        return datetime.date.fromisoformat(str(text))
    except (TypeError, ValueError):
        raise Problem(f"{field}를 올바르게 입력해 주세요.")


def optional_date(text) -> Optional[datetime.date]:
    return parse_date(text) if text else None


class WebContext(AppContext):
    """AppContext를 화면 없이 쓴다. 서버 시간대와 상관없이 날짜는 한국 시간으로 본다."""

    def __init__(self):
        self.view_key = ""        # 지금 요청이 보고 있는 시즌 (현재 시즌이 판별되지 않을 때 대신 쓴다)
        self.confirmed: set[str] = set()
        super().__init__()

    @property
    def today(self) -> datetime.date:
        return datetime.datetime.now(KST).date()

    def current_season_key(self) -> str:
        if self.current_season is not None:
            return f"{self.current_season[0]}_{self.current_season[1]}"
        return self.view_key or f"{self.today.year}_1학기"

    def confirm_name_conflict(self, message: str) -> bool:
        if "name_conflict" not in self.confirmed:
            raise Confirm("name_conflict", message, "학번 중복", warn=True)
        return True


# ---------------------------------------------------------------- JSON으로 내보낼 모양
def student_json(s: Optional[StudentInfo]) -> Optional[dict]:
    if s is None:
        return None
    return {"studentId": s.student_id, "name": s.name, "department": s.department, "advisor": s.advisor,
            "email": s.email, "contact": s.contact, "cabinetPeriod": s.cabinet_period}


def approval_json(a: ApprovalRequest) -> dict:
    return {"id": a.id, "studentName": a.student_name, "department": a.department, "studentId": a.student_id,
            "advisor": a.advisor, "email": a.email, "tabType": a.tab_type, "equipmentType": a.equipment_type,
            "requestDate": a.request_date.strftime("%Y-%m-%d %H:%M"), "requestDay": a.request_date.strftime("%Y-%m-%d"),
            "status": a.status, "rentalPeriod": a.rental_period, "phone": a.phone, "note": a.note,
            "dueDate": a.due_date.isoformat() if a.due_date else ""}


def issue_json(i: EquipmentIssue) -> dict:
    return {"id": i.id, "reportDate": i.report_date.strftime("%m-%d %H:%M"), "displayUnit": i.display_unit,
            "issueType": i.issue_type, "displayDetail": i.display_detail}


def attendance_json(r: fi.FaceAttendanceEntry) -> dict:
    return {"studentId": r.student_id, "name": r.name, "date": r.date, "checkIn": r.check_in or "",
            "checkOut": r.check_out or "", "workTime": r.work_time_text}


def xlsx_bytes(headers: list, rows: Iterable[list]) -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    # 구글 폼에 적힌 글자가 '='로 시작해도 엑셀에서 수식으로 실행되지 않게 글자로 고정한다
    for line in ws.iter_rows(min_row=2):
        for cell in line:
            if cell.data_type == "f":
                cell.data_type = "s"
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class Service:
    def __init__(self):
        self.lock = threading.RLock()
        self.ctx = WebContext()
        self.rev = 1                     # 데이터가 바뀔 때마다 증가 — 다른 관리자 화면이 알아채고 새로 읽는다
        self.notice: Optional[dict] = None   # 자동 동기화 중 생긴, 모든 관리자에게 알릴 안내 1건
        self.sync_status = ("대기 중", False)
        self._syncing = threading.Lock()
        with self.lock:
            self.refresh_season()
            self.ctx.migrate_students_without_season()
            self.ctx.save_settings()
            fi.export_roster(self.ctx.state.master_students)
            if not self.key_exists:
                self.sync_status = ("서비스 계정 키를 찾지 못했습니다. [키 파일 선택...]으로 지정해주세요.\n"
                                    f"찾아본 위치: {self.ctx.resolve_service_account_key_path()}", True)

    # ------------------------------------------------------------ 공통
    def _begin(self, body: dict) -> dict:
        """요청마다 사용자의 답(confirmed)과 보고 있는 시즌을 받아 둔다."""
        self.ctx.confirmed = set(body.get("confirmed") or [])
        self.ctx.view_key = body.get("key") or ""
        return body

    def _ask(self, key: str, message: str, title: str, warn: bool = False) -> None:
        if key not in self.ctx.confirmed:
            raise Confirm(key, message, title, warn)

    def _commit(self, seats: bool = False, state: bool = True) -> None:
        if seats:
            self.ctx.save_seat_cache()
        if state:
            self.ctx.save_app_state()
        self.rev += 1

    def _find(self, items: Iterable, item_id: str, what: str):
        found = next((x for x in items if x.id == item_id), None)
        if found is None:
            raise Problem(f"{what}을(를) 찾을 수 없습니다. 다른 관리자가 이미 처리했을 수 있습니다. 화면을 새로 고칩니다.")
        return found

    def _layout(self, key: str) -> list[Seat]:
        if not SEAT_KEY.match(key or ""):
            raise Problem("조회할 연도/학기가 올바르지 않습니다.")
        cache = self.ctx.seat_cache
        if key not in cache:
            # 처음 조회하는 시즌은 완전히 빈 상태로 시작한다
            cache[key] = storage.new_empty_seats()
            self.ctx.save_seat_cache()
        return cache[key]

    @staticmethod
    def _seat(seats: list[Seat], number: int) -> Seat:
        seat = next((s for s in seats if s.seat_number == number), None)
        if seat is None:
            raise Problem("좌석 번호가 올바르지 않습니다.")
        return seat

    # ------------------------------------------------------------ 시작 정보
    def refresh_season(self) -> None:
        """현재 날짜가 포함되는 시즌을 다시 판별한다 (DetectAndApplyCurrentSeason)."""
        resolved = self.ctx.season_config.resolve_season(self.ctx.today)
        if resolved != self.ctx.current_season:
            self.ctx.current_season = resolved
            self.rev += 1

    @locked
    def bootstrap(self) -> dict:
        self.refresh_season()
        ctx = self.ctx
        today = ctx.today
        cs = ctx.current_season
        years = [str(y) for y in range(2020, today.year + 1)]
        if cs and str(cs[0]) not in years:
            years.append(str(cs[0]))
        return {
            "today": today.isoformat(),
            "dateLabel": f"{today:%Y-%m-%d} ({'월화수목금토일'[today.weekday()]})",
            "years": years,
            "seasons": SEASON_NAMES,
            "selectedYear": str(cs[0]) if cs else str(today.year),
            "selectedSeason": cs[1] if cs else SEASON_NAMES[0],
            "seasonLabel": f"현재 시즌: {cs[0]}년 {cs[1]} (자동)" if cs else "현재 시즌: 설정된 시즌 없음",
            "positions": POSITIONS,
            "rev": self.rev,
            "counts": self._counts(),
        }

    def _counts(self) -> dict:
        ap = self.ctx.state.approvals
        by = {t: sum(1 for a in ap if a.status == "승인 대기" and a.tab_type == t) for t in ("상상Lab", "캐비닛", "기자재")}
        return {"lab": by["상상Lab"], "cabinet": by["캐비닛"], "equipment": by["기자재"]}

    def revision(self) -> dict:
        return {"rev": self.rev, "notice": self.notice}

    # ------------------------------------------------------------ 대시보드
    @locked
    def seats(self, key: str) -> dict:
        layout = self._layout(key)
        return {
            "key": key,
            "seats": [{"n": s.seat_number, "student": student_json(s.student), "fixed": s.is_fixed, "locked": s.is_locked()}
                      for s in layout],
            "memos": [{"id": m.id, "content": m.content} for m in self.ctx.state.memos],
        }

    @locked
    def drop_seat(self, body: dict) -> dict:
        self._begin(body)
        layout = self._layout(body["key"])
        source, target = self._seat(layout, int(body["src"])), self._seat(layout, int(body["dst"]))
        if source is target or source.student is None:
            return {}
        if source.is_locked() or target.is_locked():
            raise Problem("고정된 좌석은 이동하거나 교체할 수 없습니다.\n자리를 옮기려면 먼저 [좌석 고정 모드]에서 고정을 해제해 주세요.",
                          "고정된 좌석")
        moving, occupant = source.student, target.student
        if occupant is not None:
            occ = occupant.name.strip() and occupant.name or occupant.student_id
            mov = moving.name.strip() and moving.name or moving.student_id
            self._ask("swap", f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n{mov} 학생과 자리를 맞바꿀까요?", "좌석 맞바꾸기")
        source.student, target.student = occupant, moving
        self.ctx.mark_student_active(moving)
        self.ctx.mark_student_active(occupant)
        self._commit(seats=True)
        return {}

    @locked
    def fix_seats(self, body: dict) -> dict:
        """[고정 저장/종료] — 고른 좌석의 고정을 뒤집는다. 대학원생 좌석은 항상 고정이라 건드리지 않는다."""
        self._begin(body)
        layout = self._layout(body["key"])
        for n in body.get("numbers", []):
            s = self._seat(layout, int(n))
            if s.student is not None and s.student.is_graduate():
                continue
            s.is_fixed = not s.is_fixed
        self._commit(seats=True, state=False)
        return {}

    @locked
    def delete_seats(self, body: dict) -> dict:
        self._begin(body)
        layout = self._layout(body["key"])
        self._ask("delete", "선택한 좌석들의 인적사항과 출석 데이터를 삭제하시겠습니까?", "확인")
        for n in body.get("numbers", []):
            s = self._seat(layout, int(n))
            s.student, s.is_fixed = None, False
        self._commit(seats=True, state=False)
        return {}

    @locked
    def delete_all_seats(self, body: dict) -> dict:
        self._begin(body)
        layout = self._layout(body["key"])
        self._ask("delete_all", "모든 좌석의 인적 사항과 출석 데이터를 삭제하시겠습니까? (좌석 번호와 고정상태는 남음)", "경고", warn=True)
        for s in layout:
            s.student = None
        self._commit(seats=True, state=False)
        return {}

    @locked
    def random_seats(self, body: dict) -> dict:
        self._begin(body)
        seats = self._layout(body["key"])
        current_ids = {s.student.student_id for s in seats if s.student}
        key = self.ctx.current_season_key()
        new_students = [m for m in self.ctx.state.master_students
                        if m.last_active_season == key and m.student_id not in current_ids]
        bottom = range(43, 53)
        if new_students:
            empty = sorted((s for s in seats if s.student is None and not s.is_pillar and s.seat_number not in bottom),
                           key=lambda s: s.seat_number)
            if len(empty) < len(new_students):
                raise Problem("빈 좌석이 부족하여 추가 학생을 배치할 수 없습니다.")
            targets = empty[len(empty) - len(new_students):]
            shuffled = random.sample(new_students, len(new_students))
            for stu, seat in zip(shuffled, targets):
                stu.last_active_season = key
                seat.student = stu.clone()
                if seat.student.is_graduate():
                    seat.is_fixed = True
            self._commit(seats=True)
            return {"message": f"신규 등록 학생 {len(shuffled)}명이 빈 자리(뒷자리 우선)에 랜덤 배치되었습니다.", "title": "신규 배치 완료"}

        unfixed = sorted((s for s in seats if not s.is_fixed and not s.is_pillar
                          and not (s.student and s.student.is_graduate()) and s.seat_number not in bottom),
                         key=lambda s: s.seat_number)
        if len(unfixed) <= 1:
            raise Problem("고정되지 않은 좌석이 부족하여 배정할 수 없습니다.")
        pool = [s.student for s in unfixed if s.student is not None]
        old_seat = {id(s.student): s.seat_number for s in unfixed if s.student is not None}
        targets = unfixed[len(unfixed) - len(pool):]
        result = None
        for _ in range(1000):
            shuffled = random.sample(pool, len(pool))
            if not any(_too_close(old_seat[id(stu)], seat.seat_number) for stu, seat in zip(shuffled, targets)):
                result = shuffled
                break
        message = None
        if result is None:
            message = {"message": "수평 거리 제약조건(2칸 이상)을 맞출 수 없어 기본 랜덤 배정으로 진행합니다.", "title": "참고"}
            result = random.sample(pool, len(pool))
        for s in unfixed:
            s.student = None
        for seat, stu in zip(targets, result):
            seat.student = stu
        self._commit(seats=True, state=False)
        return message or {}

    @locked
    def edit_seat(self, body: dict) -> dict:
        """좌석 상세의 [저장]. number=0은 상상Lab [더보기]처럼 좌석 없이 학생만 고치는 경우다."""
        self._begin(body)
        number = int(body.get("number") or 0)
        sid = str(body.get("studentId") or "")
        student, seat = None, None
        if number:
            seat = self._seat(self._layout(body["key"]), number)
            if seat.student is None:
                seat.student = StudentInfo(student_id="2026" + str(random.randint(1000, 9998)))
            student = seat.student
        else:
            student = StudentInfo(student_id=sid)
        student.name = str(body.get("name", ""))
        student.department = str(body.get("department", ""))
        student.advisor = str(body.get("advisor", ""))
        student.email = str(body.get("email", ""))
        if seat is not None and student.is_graduate():
            seat.is_fixed = True
        master = next((m for m in self.ctx.state.master_students if m.student_id == student.student_id), None)
        if master is not None:
            master.name, master.department, master.advisor = student.name, student.department, student.advisor
            master.email = student.email
        else:
            self.ctx.state.master_students.append(student.clone())
        self._commit(seats=True)
        return {"message": "학생 정보가 수정되었으며 즉시 대시보드에 데이터가 업데이트되었습니다.", "title": "저장 완료",
                "student": student_json(student)}

    @locked
    def assign_seat(self, body: dict) -> dict:
        """좌석 상세의 [학생선택] — 고른 학생을 이 좌석에 앉힌다. 이미 앉은 학생이면 자리를 맞바꾼다."""
        self._begin(body)
        seats = self._layout(body["key"])
        target = self._seat(seats, int(body["number"]))
        sid = str(body.get("studentId") or "")
        selected = next((m for m in self.ctx.state.master_students if m.student_id == sid), None)
        if selected is None:
            raise Problem("배정할 학생을 먼저 선택하세요.", "경고")
        source = next((s for s in seats if s.student and s.student.student_id == sid
                       and s.seat_number != target.seat_number), None)
        if source is None and target.student and target.student.student_id == sid:
            return {"student": student_json(target.student)}
        occupant = target.student
        occ = None
        if occupant is not None:
            occ = occupant.name.strip() and occupant.name or occupant.student_id
            if source is not None:
                ask = (f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n\n{selected.name} 학생과 자리를 맞바꿀까요?\n"
                       f"→ {selected.name}: {source.seat_number}번 → {target.seat_number}번 / {occ}: {target.seat_number}번 → {source.seat_number}번")
            else:
                ask = f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n\n{occ} 학생을 빼고 {selected.name} 학생을 배정할까요?"
            self._ask("occupied", ask, "좌석 사용 중")
        moving = source.student if source is not None else selected.clone()
        if source is not None:
            source.student = occupant
            source.is_fixed = occupant is not None and occupant.is_graduate()
        target.student = moving
        target.is_fixed = moving.is_graduate()
        self.ctx.mark_student_active(moving)
        self.ctx.mark_student_active(occupant)
        self._commit(seats=True)
        message = (f"{selected.name} 학생과 {occ} 학생의 자리를 맞바꿨습니다. '저장'을 누르면 최종 적용됩니다."
                   if occupant is not None and source is not None
                   else f"학생 '{selected.name}'이(가) 좌석에 배정되었습니다. '저장'을 누르면 최종 적용됩니다.")
        return {"message": message, "title": "좌석 배정", "student": student_json(moving)}

    @locked
    def seat_detail(self, key: str, number: int) -> dict:
        seat = self._seat(self._layout(key), number)
        return {"student": student_json(seat.student), "cabinet": self._cabinet_text(seat.student)}

    def _cabinet_text(self, student: Optional[StudentInfo]) -> str:
        if student is None:
            return "사용 안 함"
        n = next((n for n, a in self.ctx.state.cabinet_allocations.items()
                  if a.student and a.student.student_id == student.student_id), None)
        return f"사용 중 (번호: {n}번)" if n else "사용 안 함"

    @locked
    def export_seats(self, key: str) -> tuple[bytes, str]:
        occupied = sorted((s for s in self._layout(key) if s.student is not None), key=lambda s: s.seat_number)
        if not occupied:
            raise Problem("대시보드에 착석한 학생 정보가 없습니다.")
        rows = [[s.seat_number, s.student.student_id, s.student.name, s.student.department, s.student.advisor,
                 s.student.email, "고정" if s.is_fixed else "미고정"] for s in occupied]
        return (xlsx_bytes(["좌석번호", "학번", "이름", "소속", "지도교수", "이메일", "고정여부"], rows),
                f"대시보드_학생현황_{self.ctx.today:%Y%m%d}.xlsx")

    @locked
    def load_seat_file(self, body: dict, path: str) -> dict:
        self._begin(body)
        ctx = self.ctx
        seats = self._layout(body["key"])
        try:
            imported = parse_sangsanglab_responses(path)
        except Exception as ex:  # noqa: BLE001
            raise Problem(f"파일을 읽는 도중 오류가 발생했습니다: {ex}", "오류", "error")
        if not imported:
            raise Problem("불러올 학생 정보를 찾지 못했습니다.\n상상Labs 입실신청(응답) 시트 양식(타임스탬프·신청공간·소속·이름·학번·연락처·이메일·지도교수 열)의 CSV/엑셀 파일인지 확인해주세요.")
        cs = ctx.current_season
        season_label = f"{cs[0]}년 {cs[1]}" if cs else "현재 시즌"
        self._ask("load_seats", f"{season_label} 좌석 데이터를 불러온 명단 {len(imported)}명으로 교체합니다.\n고정된 좌석은 그대로 유지됩니다.\n\n계속하시겠습니까?",
                  "좌석데이터 불러오기")
        fixed_ids = {s.student.student_id for s in seats if s.is_fixed and s.student and s.student.student_id}
        queue = [st for st in imported if not st.student_id or st.student_id not in fixed_ids]
        placed = 0
        for seat in sorted(seats, key=lambda s: s.seat_number):
            if seat.is_pillar or seat.is_fixed:
                continue
            if not queue:
                seat.student = None
                continue
            st = queue.pop(0)
            seat.student = st
            if st.is_graduate():
                seat.is_fixed = True
            placed += 1

        added = updated = 0
        key = ctx.current_season_key()
        masters = ctx.state.master_students
        for st in imported:
            master = (next((m for m in masters if m.student_id == st.student_id), None) if st.student_id
                      else next((m for m in masters if m.name == st.name and m.email == st.email), None))
            if master is None:
                c = st.clone()
                c.last_active_season = key
                masters.append(c)
                added += 1
                continue
            master.last_active_season = key
            changed = False
            for attr in ("name", "department", "advisor", "email", "contact"):
                if not getattr(master, attr).strip() and getattr(st, attr).strip():
                    setattr(master, attr, getattr(st, attr))
                    changed = True
            if changed:
                updated += 1
        self._commit(seats=True)
        leftover = f"\n\n좌석 수보다 {len(queue)}명이 많아 배치되지 못했습니다." if queue else ""
        master_msg = f"\n학생 데이터: 신규 {added}명 추가" + (f", {updated}명 정보 보완" if updated else "")
        return {"message": f"{season_label} 좌석에 {placed}명을 배치했습니다.{master_msg}{leftover}", "title": "불러오기 완료"}

    # ------------------------------------------------------------ 메모
    @locked
    def add_memo(self, content: str) -> dict:
        text = (content or "").strip()
        if text:
            self.ctx.state.memos.append(MemoItem(content=text))
            self._commit()
        return {}

    @locked
    def update_memo(self, memo_id: str, content: str) -> dict:
        memo = self._find(self.ctx.state.memos, memo_id, "메모")
        if (content or "").strip():
            memo.content = content.strip()
            self._commit()
        return {}

    @locked
    def delete_memo(self, memo_id: str) -> dict:
        self.ctx.state.memos.remove(self._find(self.ctx.state.memos, memo_id, "메모"))
        self._commit()
        return {}

    # ------------------------------------------------------------ 승인 / 반려 / 복구
    @locked
    def approvals(self, scope: str) -> list[dict]:
        return [approval_json(a) for a in self.ctx.state.approvals if a.tab_type == scope]

    def _equipment_choice(self, req: ApprovalRequest) -> dict:
        rt = req.equipment_type or ""
        laptop = any(k in rt for k in ("노트북", "Laptop", "OMEN"))
        rental = self.ctx.today
        due = req.due_date or (rental + datetime.timedelta(days=7))
        return {"typeLabel": LAPTOP_LABEL if laptop else MAINFRAME_LABEL, "numbers": self._free_units(not laptop),
                "phone": req.phone, "rentalDate": rental.isoformat(), "dueDate": due.isoformat()}

    def _free_units(self, is_mainframe: bool) -> list[str]:
        busy = set()
        for r in self.ctx.state.rentals:
            if not r.is_returned and r.is_mainframe == is_mainframe:
                m = re.search(r"\d+", r.unit_number)
                if m:
                    busy.add(int(m.group()))
        for i in self.ctx.state.equipment_issues:
            if ("본체" in i.equipment_name) == is_mainframe:
                busy.add(i.unit_number)
        total = TOTAL_MAINFRAME if is_mainframe else TOTAL_LAPTOP
        return [f"No. {n}" for n in range(1, total + 1) if n not in busy]

    def _free_cabinets(self) -> list[int]:
        return [n for n in range(1, TOTAL_CABINETS + 1) if n not in self.ctx.state.cabinet_allocations]

    @locked
    def approve(self, req_id: str, body: dict) -> dict:
        self._begin(body)
        ctx, st = self.ctx, self.ctx.state
        req = self._find(st.approvals, req_id, "신청")
        if req.tab_type == "기자재":
            # 기자재 대여는 일회성이라 학생 마스터에 등록/수정하지 않는다 (있으면 이름만 읽어 온다)
            master = next((m for m in st.master_students if m.student_id == req.student_id), None)
        else:
            master = ctx.register_or_update_master(req)

        chosen_cabinet = -1
        pick = body.get("equipment")
        chosen_type, chosen_phone = "", req.phone
        rental_date = due_date = None
        if req.tab_type == "기자재":
            if not pick:
                raise Choose("equipment", self._equipment_choice(req))
            info = self._equipment_choice(req)
            unit = str(pick.get("unit", ""))
            if unit not in info["numbers"]:
                raise Problem("대여 가능한 기자재가 없습니다.", "경고")
            chosen_type = f"{info['typeLabel']} ({unit})"
            chosen_phone = str(pick.get("phone", "")).strip()
            rental_date = parse_date(pick.get("rentalDate"), "대여 시작일")
            due_date = parse_date(pick.get("dueDate"), "반납 예정일")
        elif req.tab_type == "캐비닛":
            m = master
            dup = next((n for n, a in st.cabinet_allocations.items() if a.student and a.student.student_id == m.student_id), 0)
            if dup > 0:
                existing_period = st.cabinet_allocations[dup].period
                new_period = ctx.season_cabinet_period()
                if ctx.are_periods_overlapping(existing_period, new_period):
                    raise Problem(f"해당 학생({m.name} / {m.student_id})은 이미 {dup}번 캐비닛에 배정되어 있으며, "
                                  f"대여 기간({existing_period})이 신청 기간({new_period})과 중복됩니다.\n먼저 기존 배정을 해제한 후 승인해 주세요.",
                                  "배정 중복 오류")
                merged = ctx.merge_periods(existing_period, new_period)
                self._ask("extend", f"{m.name} ({m.student_id}) 학생은 {dup}번 캐비닛을 {existing_period} 기간으로 쓰고 있습니다.\n"
                                    f"신청 기간({new_period})이 겹치지 않으므로 {dup}번 캐비닛을 {merged} 로 연장합니다.\n\n계속할까요?",
                          "대여 기간 연장")
                st.cabinet_allocations[dup] = CabinetAllocation(dup, m.clone(), merged)
                req.rental_period = merged
                chosen_cabinet = dup
            else:
                chosen = body.get("cabinet")
                if not chosen:
                    raise Choose("cabinet", {"numbers": self._free_cabinets(), "movingFrom": 0})
                chosen_cabinet = int(chosen)
                if chosen_cabinet not in self._free_cabinets():
                    raise Problem("올바른 캐비닛 번호를 선택해 주세요.", "경고")

        req.status = "승인 완료"
        st.approvals.remove(req)
        st.approval_history.append(req)

        # 상상Lab 승인은 학생 마스터(데이터 관리)만 만든다 — 좌석은 관리자가 직접 배정한다.

        if req.tab_type == "캐비닛" and chosen_cabinet > 0:
            cur = st.cabinet_allocations.get(chosen_cabinet)
            if cur is None or cur.student is None or cur.student.student_id != master.student_id:
                period = ctx.season_cabinet_period()
                req.rental_period = period
                st.cabinet_allocations[chosen_cabinet] = CabinetAllocation(chosen_cabinet, master.clone(), period)

        if req.tab_type == "기자재":
            days = (due_date - rental_date).days
            if days <= 0:
                days = 7
            rental = RentalItem(
                student_name=prefer(master.name if master else "", req.student_name),
                equipment_type=chosen_type, rental_date=rental_date, rental_period_days=days, is_returned=False,
                student_id=prefer(req.student_id, "20261234"), department=prefer(req.department, "소프트웨어융합학과"),
                year_level=prefer(req.year_level, "3학년"), phone=prefer(chosen_phone, "010-0000-0000"),
                advisor=prefer(req.advisor, "김동욱 교수"), location=prefer(req.location, "DSU 창의공간"),
                purpose=prefer(req.purpose, "개인 실습"), remarks=req.note,
            )
            st.rentals.append(rental)
            st.rental_history.append(rental)
        self._commit()
        return {}

    @locked
    def reject(self, req_id: str) -> dict:
        st = self.ctx.state
        req = self._find(st.approvals, req_id, "신청")
        req.status = "반려"
        st.approvals.remove(req)
        st.approval_history.append(req)
        self._commit()
        return {}

    @locked
    def history(self, scope: str) -> list[dict]:
        return [approval_json(a) for a in self.ctx.state.approval_history if not scope or a.tab_type == scope]

    @locked
    def restore(self, req_id: str, body: dict) -> dict:
        self._begin(body)
        st = self.ctx.state
        req = self._find(st.approval_history, req_id, "신청 내역")
        self._ask("restore", f"'{req.student_name}' 학생의 내역을 대기 목록으로 되돌리시겠습니까?", "복구 확인")
        if req.status == "승인 완료":
            if req.tab_type == "상상Lab":
                seats = self.ctx.seat_cache.get(body.get("key") or "", [])
                seat = next((s for s in seats if s.student and s.student.student_id == req.student_id), None)
                if seat:
                    seat.student, seat.is_fixed = None, False
            elif req.tab_type == "캐비닛":
                key = next((n for n, a in st.cabinet_allocations.items() if a.student and a.student.student_id == req.student_id), 0)
                if key > 0:
                    del st.cabinet_allocations[key]
            elif req.tab_type == "기자재":
                rental = next((r for r in st.rentals if r.student_name == req.student_name), None)
                if rental:
                    st.rentals.remove(rental)
        req.status = "승인 대기"
        st.approval_history.remove(req)
        st.approvals.append(req)
        self._commit(seats=True)
        return {"message": "신청 내역이 대기 목록으로 성공적으로 복구되었습니다.", "title": "복구 완료"}

    # ------------------------------------------------------------ 기자재
    def _rental_json(self, r: RentalItem) -> dict:
        today = self.ctx.today
        return {"id": r.id, "studentName": r.student_name, "equipmentType": r.equipment_type,
                "displayEquipment": r.display_equipment, "studentId": r.student_id, "quantity": r.quantity,
                "rentalDate": r.rental_date.isoformat(), "dueDate": r.due_date.isoformat(),
                "isMainframe": r.is_mainframe, "isReturned": r.is_returned,
                "state": "overdue" if r.is_overdue(today) else ("warning" if r.is_warning(today) else "ok"),
                "deptYear": f"{r.department} / {r.year_level}", "phoneAdvisor": f"{r.phone} / {r.advisor}",
                "department": r.department, "location": r.location, "purpose": r.purpose,
                "extraItems": r.extra_items, "remarks": r.remarks}

    @locked
    def equipment(self) -> dict:
        st = self.ctx.state
        mf = sum(1 for r in st.rentals if r.is_mainframe)
        lt = len(st.rentals) - mf
        return {"approvals": self.approvals("기자재"), "issues": [issue_json(i) for i in st.equipment_issues],
                "rentals": [self._rental_json(r) for r in st.rentals],
                "mainframe": {"available": max(0, TOTAL_MAINFRAME - mf), "used": mf},
                "laptop": {"available": max(0, TOTAL_LAPTOP - lt), "used": lt}}

    @locked
    def rental_history(self) -> list[dict]:
        return [self._rental_json(r) for r in self.ctx.state.rental_history]

    @locked
    def return_rental(self, rental_id: str, body: dict) -> dict:
        self._begin(body)
        st = self.ctx.state
        rental = self._find(st.rentals, rental_id, "대여 건")
        self._ask("return", f"{rental.student_name}의 '{rental.equipment_type}' 반납 처리를 하시겠습니까?", "반납 확인")
        self._mark_returned(rental, self.ctx.today)
        st.rentals.remove(rental)
        self._commit()
        return {}

    def _mark_returned(self, rental: RentalItem, when: Optional[datetime.date]) -> None:
        """현황과 내역은 저장했다 불러오면 다른 객체가 되므로 같은 Id를 찾아 함께 표시한다."""
        for r in [rental, *self.ctx.state.rental_history]:
            if r.id == rental.id:
                r.is_returned = True
                r.return_date = when or r.return_date

    @locked
    def delete_rentals(self, body: dict) -> dict:
        self._begin(body)
        st = self.ctx.state
        ids = set(body.get("ids") or [])
        selected = [r for r in st.rentals if r.id in ids]
        if not selected:
            raise Problem("삭제할 대여 데이터를 목록에서 먼저 선택해 주세요.")
        self._ask("delete", f"선택한 {len(selected)}개의 대여 데이터를 삭제하시겠습니까?", "삭제 확인", warn=True)
        st.rentals[:] = [r for r in st.rentals if r.id not in ids]
        self._commit()
        return {"message": "선택한 대여 데이터가 삭제되었습니다.", "title": "삭제 완료"}

    @locked
    def issue_options(self, is_mainframe: bool) -> dict:
        return {"numbers": self._free_units(is_mainframe)}

    @locked
    def add_issue(self, body: dict) -> dict:
        is_mainframe = body.get("kind") == "mainframe"
        unit = str(body.get("unit", ""))
        if unit not in self._free_units(is_mainframe):
            raise Problem("기자재 번호를 먼저 고르세요.")
        issue_type = body.get("issueType")
        if issue_type not in ("고장", "수리", "기타"):
            raise Problem("상태를 고르세요.")
        detail = str(body.get("detail", "")).strip() if issue_type == "기타" else ""
        if issue_type == "기타" and not detail:
            raise Problem("내용을 입력해 주세요.")
        self.ctx.state.equipment_issues.insert(0, EquipmentIssue(
            equipment_name="본체" if is_mainframe else "노트북", unit_number=int(re.search(r"\d+", unit).group()),
            issue_type=issue_type, detail=detail))
        self._commit()
        return {}

    @locked
    def complete_issue(self, issue_id: str, body: dict) -> dict:
        self._begin(body)
        issues = self.ctx.state.equipment_issues
        issue = self._find(issues, issue_id, "상태 항목")
        self._ask("complete", f"[{issue.display_unit}] {issue.display_detail}\n\n처리 완료로 목록에서 지울까요?", "처리 완료")
        issues.remove(issue)
        self._commit()
        return {}

    @locked
    def export_rentals(self, is_mainframe: bool) -> tuple[bytes, str]:
        title = f"{MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL} 대여 현황"
        target = [r for r in self.ctx.state.rentals if r.is_mainframe == is_mainframe]
        if not target:
            raise Problem("추출할 대여 데이터가 없습니다.")
        headers = ["번호", "수량", "추가 대여물품(수량)", "사용장소", "사용목적", "특이사항", "전공", "학년", "학번",
                   "연락처", "지도교수", "성명", "대여일", "반납예정일", "반납일"]
        rows = [[i, r.quantity, r.extra_items, r.location, r.purpose, r.remarks, r.department, r.year_level,
                 r.student_id, r.phone, r.advisor, r.student_name, r.rental_date.isoformat(),
                 r.due_date.isoformat(), r.return_date.isoformat() if r.return_date else ""]
                for i, r in enumerate(target, 1)]
        return xlsx_bytes(headers, rows), f"{title}_{self.ctx.today:%Y%m%d}.xlsx"

    @locked
    def import_rental_file(self, is_mainframe: bool, path: str) -> dict:
        label = MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL
        try:
            imported, skipped = import_rentals(path, label, is_mainframe, self.ctx.today)
        except ValueError as ex:
            raise Problem(str(ex))
        except Exception as ex:  # noqa: BLE001
            raise Problem(f"파일을 읽는 도중 오류가 발생했습니다: {ex}", "오류", "error")
        self.ctx.state.rentals.extend(imported)
        self.ctx.state.rental_history.extend(imported)
        self._commit()
        skip = f"\n(다른 기자재 종류 {skipped}건은 건너뛰었습니다.)" if skipped else ""
        return {"message": f"파일로부터 {len(imported)}건의 기자재 대여 내역을 추가했습니다.{skip}", "title": "가져오기 성공"}

    @staticmethod
    def template_path() -> str:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(root, "assets", TEMPLATE_NAME)
        if not os.path.exists(path):
            raise Problem("기자재 대여 양식 파일을 찾을 수 없습니다. (assets 폴더에 파일이 존재하는지 확인해 주세요)", "오류", "error")
        return path

    # ------------------------------------------------------------ 캐비닛
    @locked
    def cabinets(self) -> dict:
        ctx = self.ctx
        allocs = ctx.state.cabinet_allocations
        today = ctx.today
        cells = {}
        for n, a in allocs.items():
            rng = ctx.parse_period_dates(a.period)
            cells[str(n)] = {"student": student_json(a.student), "period": a.period,
                             "expiring": bool(rng and (rng[1] - today).days <= 7)}
        return {"approvals": self.approvals("캐비닛"), "cells": cells, "used": len(allocs),
                "available": max(0, TOTAL_CABINETS - len(allocs)), "defaultPeriod": ctx.default_cabinet_period}

    @locked
    def cabinet_period_dates(self, text: str) -> dict:
        ctx = self.ctx
        rng = ctx.parse_period_dates(text) or ctx.parse_period_dates(ctx.default_cabinet_period)
        start = rng[0] if rng else ctx.today
        end = rng[1] if rng else start + datetime.timedelta(days=30)
        return {"start": start.isoformat(), "end": end.isoformat()}

    @locked
    def drop_cabinet(self, body: dict) -> dict:
        self._begin(body)
        allocs = self.ctx.state.cabinet_allocations
        src, dst = int(body["src"]), int(body["dst"])
        if src == dst or src not in allocs or not 1 <= dst <= TOTAL_CABINETS:
            return {}
        moving, occupant = allocs[src], allocs.get(dst)
        if occupant is not None:
            mv = (moving.student.name.strip() and moving.student.name or moving.student.student_id) if moving.student else ""
            occ = "다른 학생" if occupant.student is None else (occupant.student.name.strip() and occupant.student.name or occupant.student.student_id)
            self._ask("swap", f"{dst}번 캐비닛은 {occ} 학생이 쓰고 있습니다.\n\n{mv}({src}번)과 자리를 맞바꿀까요?\n"
                              f"→ {mv}: {src}번 → {dst}번 / {occ}: {dst}번 → {src}번", "캐비닛 맞바꾸기")
            moving.cabinet_num, occupant.cabinet_num = dst, src
            allocs[src], allocs[dst] = occupant, moving
        else:
            del allocs[src]
            moving.cabinet_num = dst
            allocs[dst] = moving
        self._commit()
        return {"highlight": dst}

    @locked
    def move_cabinet_options(self, number: int) -> dict:
        return {"numbers": self._free_cabinets(), "movingFrom": number}

    @locked
    def move_cabinet(self, body: dict) -> dict:
        allocs = self.ctx.state.cabinet_allocations
        src, dst = int(body["src"]), int(body["dst"])
        alloc = allocs.get(src)
        if alloc is None:
            return {}
        if dst not in self._free_cabinets():
            raise Problem("올바른 캐비닛 번호를 선택해 주세요.", "경고")
        del allocs[src]
        alloc.cabinet_num = dst
        allocs[dst] = alloc
        self._commit()
        s = alloc.student
        who = (s.student_id if not s.name.strip() else f"{s.name}({s.student_id})") if s else ""
        return {"highlight": dst, "message": f"{who} 학생의 좌석을 {src}번 → {dst}번으로 옮겼습니다.", "title": "좌석 이동 완료"}

    @locked
    def save_cabinet(self, body: dict) -> dict:
        allocs = self.ctx.state.cabinet_allocations
        number = int(body["number"])
        if not 1 <= number <= TOTAL_CABINETS:
            raise Problem("캐비닛 번호가 올바르지 않습니다.")
        name, sid = str(body.get("name", "")).strip(), str(body.get("studentId", "")).strip()
        if not name or not sid:
            raise Problem("모든 항목을 입력해 주세요.", "경고")
        if not body.get("start") or not body.get("end"):
            raise Problem("대여 시작일과 종료일을 캘린더에서 모두 선택해 주세요.", "대여 기간")
        start, end = parse_date(body["start"]), parse_date(body["end"])
        if end < start:
            raise Problem("대여 종료일이 시작일보다 빠릅니다. 날짜를 다시 선택해 주세요.", "대여 기간")
        existing = allocs.get(number)
        if existing and existing.student and existing.student.student_id == sid:
            student = existing.student
        else:
            m = next((x for x in self.ctx.state.master_students if x.student_id == sid), None)
            student = m.clone() if m else StudentInfo(student_id=sid, department="소프트웨어융합학과")
        dup = next((n for n, a in allocs.items() if a.student and a.student.student_id == sid and n != number), 0)
        if dup:
            raise Problem(f"해당 학번({sid})은 이미 {dup}번 캐비닛에 배정되어 있습니다. 중복 배정할 수 없습니다.", "배정 오류")
        student.name = name
        allocs[number] = CabinetAllocation(number, student, format_period(start, end))
        self._commit()
        return {"message": "캐비닛 정보가 저장되었습니다.", "title": "저장 완료"}

    @locked
    def assign_cabinet(self, body: dict) -> dict:
        """캐비닛 상세의 [학생선택] — 고른 학생을 이 캐비닛으로 옮긴다."""
        self._begin(body)
        ctx = self.ctx
        allocs = ctx.state.cabinet_allocations
        target = int(body["number"])
        sid = str(body.get("studentId") or "")
        selected = next((m for m in ctx.state.master_students if m.student_id == sid), None)
        if selected is None:
            raise Problem("배정할 학생을 먼저 선택하세요.", "경고")
        src = next((n for n, a in allocs.items() if a.student and a.student.student_id == sid), 0)
        if src == target:
            return {"done": True, "message": f"{selected.name} 학생은 이미 {target}번 캐비닛을 쓰고 있습니다.", "title": "알림"}
        period = allocs[src].period if src else ctx.default_cabinet_period
        occupant = allocs.get(target)
        if occupant is not None:
            occ = "다른 학생" if occupant.student is None else (occupant.student.name.strip() and occupant.student.name or occupant.student.student_id)
            if src:
                ask = (f"{target}번은 {occ} 학생이 쓰고 있습니다.\n\n{selected.name}({src}번)와 자리를 맞바꿀까요?\n"
                       f"→ {selected.name}: {src}번 → {target}번 / {occ}: {target}번 → {src}번")
            else:
                ask = f"{target}번은 {occ} 학생이 쓰고 있습니다.\n\n{occ} 학생을 빼고 {selected.name} 학생을 넣을까요?"
            self._ask("occupied", ask, "캐비닛 사용 중")
        if src:
            del allocs[src]
        if occupant is not None and src:
            occupant.cabinet_num = src
            allocs[src] = occupant
        allocs[target] = CabinetAllocation(target, selected.clone(), period)
        self._commit()
        done = (f"{selected.name} 학생을 {src}번 → {target}번 캐비닛으로 옮겼습니다." if src
                else f"{selected.name} 학생을 {target}번 캐비닛에 배정했습니다.")
        return {"highlight": target, "name": selected.name, "studentId": selected.student_id, "period": period,
                "message": done, "title": "캐비닛 배정 완료"}

    @locked
    def export_cabinets(self) -> tuple[bytes, str]:
        allocs = self.ctx.state.cabinet_allocations
        if not allocs:
            raise Problem("추출할 캐비닛 배정 데이터가 없습니다.")
        rows = []
        for n in sorted(allocs):
            s = allocs[n].student
            rows.append([n, s.student_id if s else "", s.name if s else "", s.department if s else "",
                         s.advisor if s else "", s.email if s else "", allocs[n].period])
        return (xlsx_bytes(["캐비닛번호", "학번", "이름", "소속", "지도교수", "이메일", "대여기간"], rows),
                f"캐비닛_배정현황_{self.ctx.today:%Y%m%d}.xlsx")

    @locked
    def import_cabinet_file(self, path: str) -> dict:
        allocs = self.ctx.state.cabinet_allocations
        try:
            table = ioimp.read_table(path)
        except Exception as ex:  # noqa: BLE001
            raise Problem(f"엑셀 파일을 읽는 도중 오류가 발생했습니다: {ex}", "오류", "error")
        count = 0
        for num, sid, name, dept, period in parse_cabinet_rows(table, self.ctx.default_cabinet_period):
            dup = next((n for n, a in allocs.items() if a.student and a.student.student_id == sid and n != num), 0)
            if dup:
                del allocs[dup]
            allocs[num] = CabinetAllocation(num, StudentInfo(student_id=sid, name=name, department=dept), period)
            count += 1
        self._commit()
        return {"message": f"엑셀 파일로부터 {count}개의 캐비닛 배정을 완료했습니다.", "title": "가져오기 성공"}

    # ------------------------------------------------------------ 상상Lab
    @locked
    def sangsanglab(self) -> dict:
        return {"approvals": self.approvals("상상Lab")}

    # ------------------------------------------------------------ 데이터 관리
    @locked
    def students(self) -> list[dict]:
        self.ctx.update_master_cabinet_periods()
        return [student_json(s) for s in self.ctx.state.master_students]

    @locked
    def save_student(self, old_id: str, body: dict) -> dict:
        masters = self.ctx.state.master_students
        s = next((m for m in masters if m.student_id == old_id), None)
        if s is None:
            raise Problem("학생을 찾을 수 없습니다. 다른 관리자가 이미 삭제했을 수 있습니다.")
        new_id = str(body.get("studentId", "")).strip()
        if not new_id:
            raise Problem("학번은 비워둘 수 없습니다.", "경고")
        if old_id != new_id and any(m.student_id == new_id for m in masters):
            raise Problem("이미 존재하는 학번입니다.", "경고")
        s.student_id = new_id
        s.name = str(body.get("name", ""))
        s.department = str(body.get("department", ""))
        s.advisor = str(body.get("advisor", ""))
        s.contact = str(body.get("contact", ""))
        s.email = str(body.get("email", ""))
        for layout in self.ctx.seat_cache.values():
            for seat in layout:
                if seat.student is not None and seat.student.student_id == old_id:
                    seat.student.student_id = new_id
                    seat.student.name, seat.student.department = s.name, s.department
                    seat.student.advisor, seat.student.contact, seat.student.email = s.advisor, s.contact, s.email
                    if seat.student.is_graduate():
                        seat.is_fixed = True
        self._commit(seats=True)
        return {"message": "마스터 데이터가 수정되었으며 즉시 대시보드에 데이터가 업데이트되었습니다.", "title": "완료"}

    @locked
    def delete_student(self, student_id: str, body: dict) -> dict:
        self._begin(body)
        masters = self.ctx.state.master_students
        s = next((m for m in masters if m.student_id == student_id), None)
        if s is None:
            return {}
        self._ask("delete", f"정말 {s.name} 학생을 마스터 데이터베이스에서 삭제하시겠습니까?", "삭제 확인", warn=True)
        masters.remove(s)
        self._commit()
        return {"message": "마스터 데이터가 삭제되었습니다. (기존 배치된 좌석 데이터는 유지됩니다.)", "title": "완료"}

    @locked
    def delete_all_students(self, body: dict) -> dict:
        self._begin(body)
        masters = self.ctx.state.master_students
        if not masters:
            raise Problem("삭제할 학생 정보가 없습니다.")
        self._ask("delete_all", f"등록된 모든 학생 정보({len(masters)}명)를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.", "전체 삭제 확인", warn=True)
        masters.clear()
        self._commit()
        return {"message": "모든 학생 정보가 삭제되었습니다.", "title": "삭제 완료"}

    @locked
    def import_student_file(self, path: str) -> dict:
        ctx = self.ctx
        try:
            table = ioimp.read_table(path)
            header_row = -1
            for i in range(min(len(table), 5)):
                if any(("학번" in ioimp.cell_str(x) or "StudentId" in ioimp.cell_str(x)) for x in table[i]):
                    header_row = i
                    break
            c_id, c_name, c_dept, c_adv, c_contact, c_email = 0, 1, 2, 3, 4, 5
            if header_row >= 0:
                h = [ioimp.cell_str(x).lower() for x in table[header_row]]

                def find(*keys):
                    return next((i for i, t in enumerate(h) if any(k.lower() in t for k in keys)), -1)

                c_id = find("학번", "StudentId")
                c_name = find("이름", "Name")
                c_dept = find("소속", "학과", "Department")
                c_adv = find("지도", "Advisor")
                c_contact = find("연락처", "전화", "휴대", "Contact", "Phone")
                c_email = find("이메일", "메일", "Email")

            imported = updated = 0
            masters = ctx.state.master_students
            for row in table[header_row + 1:]:
                def cell(i):
                    return ioimp.cell_str(ioimp.cell_at(row, i))

                sid = ioimp.normalize_student_id(ioimp.cell_at(row, c_id))
                if not sid.strip() or not any(ch.isdigit() for ch in sid):
                    continue
                name, dept = cell(c_name), cell(c_dept)
                advisor = cell(c_adv).replace("교수님", "").replace("교수", "").strip()
                contact = ioimp.normalize_phone(ioimp.cell_at(row, c_contact))
                email = cell(c_email)
                existing = next((m for m in masters if m.student_id == sid), None)
                if existing is None:
                    masters.append(StudentInfo(student_id=sid, name=name, department=dept.strip() or "소프트웨어전공",
                                               advisor=advisor, contact=contact, email=email,
                                               last_active_season=ctx.current_season_key()))
                    imported += 1
                    continue
                changed = False
                for attr, val in (("name", name), ("department", dept), ("advisor", advisor), ("contact", contact), ("email", email)):
                    if not getattr(existing, attr).strip() and val:
                        setattr(existing, attr, val)
                        changed = True
                if changed:
                    updated += 1
        except Exception as ex:  # noqa: BLE001
            raise Problem(f"파일을 읽는 도중 오류가 발생했습니다: {ex}", "오류", "error")
        self._commit()
        msg = f"학생 정보 {imported}명을 새로 등록했습니다."
        if updated:
            msg += f"\n기존 학생 {updated}명의 빈 항목(연락처 등)을 채웠습니다."
        return {"message": msg, "title": "가져오기 성공"}

    # ------------------------------------------------------------ 얼굴인식 출결
    @locked
    def face_records(self, keyword: str, date_from: str, date_to: str) -> dict:
        records = fi.load_attendance()
        rows = fi.filter_records(records, keyword, optional_date(date_from), optional_date(date_to))
        return {"info": self._face_info(records), "rows": [attendance_json(r) for r in rows],
                "summary": fi.records_summary(rows), "months": fi.criteria_months(records, self.ctx.today)}

    @staticmethod
    def _face_info(records: list) -> str:
        if records:
            return f"얼굴인식 프로그램(insightface-attendance)이 기록한 출근/퇴근 시간입니다. 전체 {len(records)}건."
        return "아직 기록된 출결 데이터가 없습니다. 얼굴인식 프로그램이 기록을 보내면 여기에 표시됩니다."

    def face_quick_range(self, tag: str) -> dict:
        start, end = fi.quick_range(tag, self.ctx.today)
        return {"from": start.isoformat() if start else "", "to": end.isoformat() if end else ""}

    @locked
    def face_criteria(self, month: str, result: str, keyword: str) -> dict:
        records = fi.load_attendance()
        today = self.ctx.today
        months = fi.criteria_months(records, today)
        if month not in months:
            month = months[0]
        year, mon = int(month[:4]), int(month[5:7])
        weeks = fi.weeks_of_month(year, mon)
        all_rows = fi.evaluate_month(records, year, mon, today)
        kw = keyword.strip().lower()
        wanted = BOOL_RESULT.get(result)
        rows = [r for r in all_rows if (not kw or kw in r.student_id.lower() or kw in r.name.lower())
                and (wanted is None or r.state == wanted)]
        return {
            "info": self._face_info(records), "months": months, "month": month, "rule": fi.criteria_rule_text(),
            "weeks": [f"{i + 1}주차\n{a.month}-{a.day}~{b.month}-{b.day}" for i, (a, b) in enumerate(weeks)],
            "rows": [{"studentId": r.student_id, "name": r.name, "weeks": [w.text for w in r.weeks],
                      "result": r.result_text} for r in rows],
            "summary": fi.criteria_summary(month, all_rows, len(rows)),
        }

    @locked
    def face_student(self, student_id: str) -> dict:
        records = fi.sort_latest_first(r for r in fi.load_attendance() if r.student_id == student_id)
        return {"rows": [attendance_json(r) for r in records], "summary": fi.student_summary(records, self.ctx.today)}

    @locked
    def store_attendance(self, raw) -> int:
        """얼굴인식 쪽이 보낸 출결 전체를 attendance.json으로 저장한다 (형식은 얼굴인식 프로그램이 쓰는 파일과 같다)."""
        if not isinstance(raw, list) or not all(isinstance(e, dict) for e in raw):
            raise Problem("출결 데이터는 기록 목록(JSON 배열)이어야 합니다.")
        for e in raw:
            if not e.get("StudentId") or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(e.get("Date", ""))):
                raise Problem("출결 기록에는 StudentId와 Date(yyyy-MM-dd)가 있어야 합니다.")
        storage.write_json(config.attendance_path(), raw, indent=2)
        self.rev += 1
        return len(raw)

    @locked
    def roster(self) -> list[dict]:
        return fi.build_roster(self.ctx.state.master_students)

    # ------------------------------------------------------------ 기간 만료
    @locked
    def checks(self, scope: str, key: str) -> dict:
        ctx = self.ctx
        return {"expired": self._expired(scope, key), "warnings": self._warnings(scope), "today": ctx.today.isoformat()}

    def _expired_entries(self, scope: str, key: str) -> list[tuple]:
        ctx, st, today = self.ctx, self.ctx.state, self.ctx.today
        entries = []
        if scope == "대시보드" and key in ctx.seat_cache:
            for seat in ctx.seat_cache[key]:
                if seat.is_pillar or seat.student is None:
                    continue
                period = ctx.find_student_period(seat.student)
                r = ctx.parse_period_dates(period)
                if r is None or r[1] >= today:
                    continue

                def delete(s=seat):
                    s.student, s.is_fixed = None, False
                entries.append((f"좌석|{seat.seat_number}|{seat.student.student_id}|{period}",
                                f"{seat.seat_number}번 좌석 · {seat.student.name}({seat.student.student_id}) · {period}", delete))
        elif scope == "기자재":
            for rental in [r for r in st.rentals if not r.is_returned and r.due_date < today]:
                def delete(r=rental):
                    self._mark_returned(r, None)
                    st.rentals.remove(r)
                entries.append((f"대여|{rental.id}",
                                f"{rental.display_equipment} · {rental.student_name}({rental.student_id}) · 반납예정 {rental.due_date:%Y-%m-%d}", delete))
        return [e for e in entries if e[0] not in ctx.kept_expired_keys]

    def _expired(self, scope: str, key: str) -> list[dict]:
        return [{"key": k, "label": label} for k, label, _ in self._expired_entries(scope, key)]

    def _warnings(self, scope: str) -> list[dict]:
        ctx, today = self.ctx, self.ctx.today
        rows = []
        if scope == "캐비닛":
            for n, a in ctx.state.cabinet_allocations.items():
                r = ctx.parse_period_dates(a.period)
                if r is None or (r[1] - today).days > 7:
                    continue
                s = a.student
                rows.append({"first": f"{n}번 캐비닛", "info": f"{s.name if s else ''}({s.student_id if s else ''}) · {a.period}",
                             "days": (r[1] - today).days})
        elif scope == "기자재":
            for r in ctx.state.rentals:
                if not r.is_returned and (r.due_date - today).days <= 7:
                    rows.append({"first": r.equipment_type,
                                 "info": f"{r.student_name}({r.student_id}) · {r.rental_date:%Y-%m-%d} ~ {r.due_date:%Y-%m-%d}",
                                 "days": (r.due_date - today).days})
        rows.sort(key=lambda x: x["days"])
        return rows

    @locked
    def resolve_expired(self, body: dict) -> dict:
        """만료 정리 창의 결과 — 고른 항목은 지우고, 나머지는 다시 묻지 않게 기억한다."""
        scope, key = body.get("scope", ""), body.get("key", "")
        selected = set(body.get("delete") or [])
        deleted = 0
        for k, _label, fn in self._expired_entries(scope, key):
            if k in selected:
                fn()
                deleted += 1
            else:
                self.ctx.kept_expired_keys.add(k)
        if deleted:
            self._commit(seats=True)
            return {"message": f"선택한 {deleted}건을 삭제했습니다.", "title": "정리 완료"}
        return {}

    # ------------------------------------------------------------ 구글 시트 연동
    @property
    def key_exists(self) -> bool:
        return os.path.exists(self.ctx.resolve_service_account_key_path())

    def _forms_service(self) -> gi.GoogleFormsService:
        s = self.ctx.settings
        svc = gi.GoogleFormsService(self.ctx.resolve_service_account_key_path(), gi.extract_spreadsheet_id(s.get("SangsangLabFormUrl", "")))
        svc.equipment_spreadsheet_id = gi.extract_spreadsheet_id(s.get("EquipmentFormUrl", ""))
        svc.cabinet_spreadsheet_id = gi.extract_spreadsheet_id(s.get("CabinetFormUrl", ""))
        return svc

    def sync(self, silent: bool) -> dict:
        """구글 시트에서 새 신청을 읽어 온다. 시트를 읽는 동안에는 잠그지 않아 화면이 멈추지 않는다."""
        if not self._syncing.acquire(blocking=False):
            return {}
        try:
            self.sync_status = ("동기화 중...", False)
            with self.lock:
                if not self.key_exists:
                    raise Problem("서비스 계정 키를 찾지 못했습니다. [키 파일 선택...]으로 지정해주세요.", "동기화 실패", "error")
                svc = self._forms_service()
                known = set(self.ctx.state.imported_source_keys)
            result = svc.fetch(lambda key: key in known)
            now = datetime.datetime.now(KST).strftime("%H:%M:%S")
            if not result.is_success:
                self.sync_status = (f"[{now}] {result.error}", True)
                if silent:
                    return {}
                raise Problem(result.error, "동기화 실패", "error")
            with self.lock:
                return self._merge_sync(result, now, silent)
        finally:
            self._syncing.release()

    def _merge_sync(self, result, now: str, silent: bool) -> dict:
        ctx, st = self.ctx, self.ctx.state
        auto_rejected, equipment_pending = [], 0
        for req in result.new_requests:
            if req.source_key in st.imported_source_keys:
                continue   # 시트를 읽는 사이 다른 동기화가 이미 받아 왔다
            if not req.student_name.strip():
                req.student_name = (
                    next((m.name for m in st.master_students if m.student_id == req.student_id), None)
                    or next((a.student_name for a in st.approvals if a.student_id == req.student_id and a.student_name.strip()), None)
                    or ""
                )
            if req.tab_type == "기자재":
                if is_approved_on_sheet(req.sheet_approval_status):
                    st.imported_source_keys.add(req.source_key)
                    st.approvals.append(req)
                else:
                    equipment_pending += 1
                continue
            st.imported_source_keys.add(req.source_key)
            if req.tab_type == "캐비닛":
                if not req.rental_period.strip():
                    req.rental_period = ctx.default_cabinet_period
                reason = ctx.find_cabinet_conflict(req)
                if reason:
                    req.status = "반려"
                    req.note = reason if not req.note.strip() else f"{req.note} / {reason}"
                    st.approval_history.append(req)
                    auto_rejected.append(req)
                    continue
            st.approvals.append(req)
        if result.new_requests:
            self._commit()

        added = len(result.new_requests) - equipment_pending
        summary = f"[{now}] 응답 {result.total_rows}건 중 신규 {added}건 반영"
        if result.duplicate_count:
            summary += f" (기존 {result.duplicate_count}건 건너뜀)"
        if equipment_pending:
            summary += f" (기자재 시트 승인 대기 {equipment_pending}건 — 다음 동기화 때 재확인)"
        by_type: dict[str, int] = {}
        for a in st.approvals:
            by_type[a.tab_type] = by_type.get(a.tab_type, 0) + 1
        summary += "\n승인 대기: " + (" / ".join(f"{k} {v}건" for k, v in by_type.items()) if by_type else "없음")
        if result.missing_columns:
            summary += f"\n⚠ 헤더에서 찾지 못한 항목: {', '.join(result.missing_columns)}"
        if result.unmapped_spaces:
            summary += f"\n⚠ 신청 공간을 판별하지 못한 값: {' / '.join(result.unmapped_spaces)} → '미분류'로 등록됨"
        for warning in result.warnings:
            summary += f"\n⚠ {warning}"
        self.sync_status = (summary, bool(result.missing_columns or result.unmapped_spaces or result.warnings))

        if auto_rejected:
            lines = "\n".join(f"• {r.student_name} ({r.student_id}) — {r.rental_period}" for r in auto_rejected)
            self.notice = {"id": time.time_ns(), "title": "배정 중복 오류", "level": "warning",
                           "message": f"아래 {len(auto_rejected)}건은 캐비닛 배정 기간이 중복되어 자동으로 반려 처리되었습니다.\n\n{lines}\n\n"
                                      "[📋 승인/반려 내역]에서 확인하거나 복구할 수 있습니다."}
        return {"message": summary, "title": "동기화 완료"} if not silent else {}

    def _read_key_email(self) -> str:
        path = self.ctx.resolve_service_account_key_path()
        if not os.path.exists(path):
            return "(키 파일 없음)"
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f).get("client_email") or "(확인 불가)"
        except Exception:  # noqa: BLE001
            return "(확인 불가)"

    @locked
    def settings(self) -> dict:
        s, ctx = self.ctx.settings, self.ctx
        path = ctx.resolve_service_account_key_path()
        cs = ctx.current_season
        ds = ctx.today.strftime("%Y-%m-%d")
        return {
            "sangsangLabFormUrl": s.get("SangsangLabFormUrl", ""), "cabinetFormUrl": s.get("CabinetFormUrl", ""),
            "equipmentFormUrl": s.get("EquipmentFormUrl", ""), "pollingEnabled": bool(s.get("PollingEnabled", True)),
            "pollingIntervalSeconds": s.get("PollingIntervalSeconds", 60),
            "serviceAccountEmail": self._read_key_email(),
            "keyPath": path if os.path.exists(path) else f"(없음) {path}",
            "syncStatus": self.sync_status[0], "syncWarning": self.sync_status[1],
            "currentInfo": (f"현재 시즌: {cs[0]}년 {cs[1]}  ·  기준 날짜 {ds}" if cs
                            else f"오늘({ds})이 포함되는 시즌이 없습니다. 연도별 시작일·종료일을 확인해주세요."),
            "currentYear": cs[0] if cs else None,
            "years": sorted(ctx.season_config.years(), reverse=True),
        }

    @locked
    def save_sync_settings(self, body: dict) -> dict:
        s = self.ctx.settings
        main_url = str(body.get("sangsangLabFormUrl", "")).strip()
        cab_url = str(body.get("cabinetFormUrl", "")).strip()
        eq_url = str(body.get("equipmentFormUrl", "")).strip()
        try:
            sec = int(str(body.get("pollingIntervalSeconds", "")).strip())
        except ValueError:
            sec = 0
        if sec < 15:
            raise Problem("동기화 주기는 15초 이상의 숫자로 입력해주세요.", "설정 오류")
        main_id, eq_id, cab_id = gi.extract_spreadsheet_id(main_url), gi.extract_spreadsheet_id(eq_url), gi.extract_spreadsheet_id(cab_url)
        if not main_id:
            raise Problem("상상Lab 신청 폼 URL 칸의 주소로는 시트를 읽을 수 없습니다.\n\n" +
                          ("폼 편집 화면의 [응답] → [시트에서 보기]로 열리는 " if gi.is_form_url(main_url) else "") +
                          "스프레드시트 주소(docs.google.com/spreadsheets/d/...)를 붙여넣어 주세요.\n\n"
                          "이 값이 없으면 상상Lab 신청과, 전용 시트를 지정하지 않은 캐비닛·기자재 신청을 전혀 받아올 수 없습니다.", "설정 오류")
        s["PollingEnabled"] = bool(body.get("pollingEnabled"))
        s["SangsangLabFormUrl"], s["CabinetFormUrl"], s["EquipmentFormUrl"] = main_url, cab_url, eq_url
        s["PollingIntervalSeconds"] = sec
        self.ctx.save_settings()
        notes = [n for n in (_describe_sheet("캐비닛", cab_url, cab_id), _describe_sheet("기자재", eq_url, eq_id)) if n]
        msg = f"연동 설정을 저장했습니다. (메인 시트 ID: {main_id})"
        if notes:
            msg += "\n\n" + "\n\n".join(notes) + "\n\n전용 시트도 서비스 계정에 '뷰어'로 공유되어 있어야 합니다."
        return {"message": msg, "title": "저장 완료"}

    @locked
    def save_key_file(self, data: bytes) -> dict:
        try:
            parsed = json.loads(data.decode("utf-8"))
            if parsed.get("type") != "service_account" or "private_key" not in parsed or "client_email" not in parsed:
                raise Problem("이 파일은 서비스 계정 키가 아닙니다.\nGoogle Cloud에서 발급한 서비스 계정 JSON 키를 선택해주세요.", "잘못된 키 파일")
        except (ValueError, AttributeError) as ex:
            raise Problem(f"키 파일을 읽지 못했습니다.\n{ex}", "오류", "error")
        target = config.google_service_account_path()
        storage.write_json(target, parsed, indent=2)
        self.ctx.settings["KeyPathOverride"] = ""
        self.ctx.save_settings()
        self.sync_status = ("대기 중", False)
        return {"message": f"키를 등록했습니다.\n\n서비스 계정: {parsed.get('client_email', '')}\n보관 위치: {target}\n\n"
                           "이 주소로 응답 스프레드시트를 '뷰어' 공유해야 읽을 수 있습니다.", "title": "키 등록 완료"}

    # ------------------------------------------------------------ 학사 시즌 일정
    @locked
    def season_rows(self, year: int) -> dict:
        cfg = self.ctx.season_config
        sched = cfg.get_year(year)
        base = sched.seasons if sched else default_seasons_for(year)
        by = {p.name: p for p in base}
        defaults = {p.name: p for p in default_seasons_for(year)}
        rows = [(by.get(n) or defaults[n]) for n in SEASON_NAMES]
        return {"year": year, "rows": [{"name": p.name, "start": p.start_date.isoformat(), "end": p.end_date.isoformat()} for p in rows]}

    @locked
    def add_season_year(self, body: dict) -> dict:
        self._begin(body)
        cfg = self.ctx.season_config
        years = cfg.years()
        ny = years[-1] + 1 if years else self.ctx.today.year
        while cfg.has_year(ny):
            ny += 1
        self._ask("add_year", f"{ny}년 시즌 일정을 기본값으로 추가하시겠습니까?\n"
                              "(1학기 3/1~6/30, 여름방학 7/1~8/31, 2학기 9/1~12/31, 겨울방학 익년 1/1~2월 말일)\n\n"
                              "추가한 뒤 각 시즌 날짜를 원하는 대로 수정하고 [💾 시즌 일정 저장]을 누르세요.", "연도 추가")
        cfg.ensure_year(ny)
        self.ctx.save_seasons()
        self.refresh_season()
        self.rev += 1
        return {"year": ny}

    @locked
    def delete_season_year(self, year: int, body: dict) -> dict:
        self._begin(body)
        cfg = self.ctx.season_config
        if not cfg.has_year(year):
            raise Problem("삭제할 연도 일정이 없습니다.", "연도 삭제")
        self._ask("delete_year", f"{year}년 시즌 일정을 삭제하시겠습니까?\n(해당 시즌의 좌석 데이터 자체는 그대로 보관됩니다.)", "연도 삭제", warn=True)
        cfg.remove_year(year)
        self.ctx.save_seasons()
        self.refresh_season()
        self.rev += 1
        return {"message": f"{year}년 시즌 일정을 삭제했습니다.", "title": "완료"}

    @locked
    def save_season_year(self, year: int, body: dict) -> dict:
        self._begin(body)
        rows = [SeasonPeriod(str(r["name"]), parse_date(r["start"]), parse_date(r["end"])) for r in body.get("rows", [])]
        for p in rows:
            if p.end_date < p.start_date:
                raise Problem(f"[{p.name}] 종료일이 시작일보다 빠릅니다.", "저장 실패")
        ordered = sorted(rows, key=lambda p: p.start_date)
        if any(b.start_date <= a.end_date for a, b in zip(ordered, ordered[1:])):
            self._ask("overlap", "시즌 기간이 서로 겹칩니다. 그래도 저장하시겠습니까?\n(겹치는 날짜는 먼저 시작하는 시즌으로 판별됩니다.)", "겹침 확인", warn=True)
        by = {p.name: p for p in rows}
        defaults = {p.name: p for p in default_seasons_for(year)}
        sched = self.ctx.season_config.ensure_year(year)
        sched.seasons = [by.get(n) or defaults[n] for n in SEASON_NAMES]
        self.ctx.save_seasons()
        self.refresh_season()
        self.rev += 1
        return {"message": f"{year}년 시즌 일정을 저장했습니다.", "title": "완료"}


def _too_close(old_seat: int, new_seat: int) -> bool:
    """같은 줄에서 두 칸 이상 떨어져야 한다 (랜덤 배정의 수평 거리 제약)."""
    if old_seat in COORDS and new_seat in COORDS:
        (or_, oc), (nr, nc) = COORDS[old_seat], COORDS[new_seat]
        return or_ == nr and abs(oc - nc) < 2
    return False


def _describe_sheet(label: str, entered: str, sheet_id: str) -> Optional[str]:
    if not entered:
        return None
    if sheet_id:
        return f"· {label} 신청은 별도 시트에서 받아옵니다. (시트 ID: {sheet_id})"
    return (f"· {label} 칸의 주소로는 시트를 읽을 수 없어, {label} 신청도 '상상Lab 신청 폼 URL' 시트에서만 받아옵니다.\n  "
            + ("폼 편집 화면의 [응답] → [시트에서 보기]로 열리는 " if gi.is_form_url(entered) else "")
            + "스프레드시트 주소(docs.google.com/spreadsheets/d/...)를 붙여넣어 주세요.")


def import_legacy_data(target_dir: str) -> Optional[str]:
    """
    첫 실행 때만 C# 프로그램의 데이터를 복사해 온다. 원본은 건드리지 않고, 이미 웹 데이터가 있으면 아무것도 하지 않는다.
    서버처럼 C# 프로그램이 없는 곳에서는 조용히 넘어간다.
    """
    if os.path.exists(os.path.join(target_dir, "appstate.json")):
        return None
    source = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "SeatManagerApp")
    names = ("seats.json", "appstate.json", "seasons.json", "settings.json", "google-service-account.json")
    if not os.path.exists(os.path.join(source, "appstate.json")):
        return None
    os.makedirs(target_dir, exist_ok=True)
    for name in names:
        src = os.path.join(source, name)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(target_dir, name))
    return source
