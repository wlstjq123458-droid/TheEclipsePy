"""
얼굴인식 출결 프로그램(별도 파이썬 프로그램, insightface-attendance)과의 파일 기반 연동.
C# 버전의 FaceIntegration.cs와 정확히 같은 폴더·같은 JSON 스키마를 쓴다 — 그래야 어느 쪽
(C# 버전이든 이 파이썬 버전이든)에서 내보낸 roster.json도 얼굴인식 프로그램이 그대로 읽고,
얼굴인식 프로그램이 적어 둔 attendance.json도 그대로 읽을 수 있다.

- roster.json: [{"StudentId":.., "Name":.., "Department":.., "Phone":.., "Email":.., "Advisor":..}, ...] — 이 프로그램 → 얼굴인식
- attendance.json: [{"StudentId":.., "Name":.., "Date":"yyyy-MM-dd", "CheckIn":"HH:mm:ss"|null, "CheckOut":..}, ...] — 얼굴인식 → 이 프로그램
"""
from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field
from typing import Iterable, Optional

from . import config
from .models import StudentInfo

# 월간 출석 기준 — 그 달의 모든 주(월~일)마다 근무 20시간 이상 + 출석 3일 이상
WEEKLY_REQUIRED_HOURS = 20
WEEKLY_REQUIRED_DAYS = 3

PASSED, FAILED, IN_PROGRESS = "passed", "failed", "in_progress"


def build_roster(master_students: list[StudentInfo]) -> list[dict]:
    """학생 마스터 목록을 얼굴인식 시스템이 읽는 명단 형식으로 바꾼다 (같은 학번은 먼저 나온 한 명만)."""
    seen = set()
    roster = []
    for s in sorted(master_students, key=lambda x: x.student_id):
        if not s.student_id.strip() or s.student_id in seen:
            continue
        seen.add(s.student_id)
        # 연락처는 얼굴인식 쪽 '전화번호' 칸으로 들어간다
        roster.append({"StudentId": s.student_id, "Name": s.name, "Department": s.department,
                       "Phone": s.contact, "Email": s.email, "Advisor": s.advisor})
    return roster


def export_roster(master_students: list[StudentInfo]) -> None:
    try:
        roster = build_roster(master_students)
        os.makedirs(config.face_integration_dir(), exist_ok=True)
        with open(config.roster_path(), "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 내보내기 실패는 치명적이지 않다 — 다음 저장 때 다시 시도한다


def _is_valid_time(t: Optional[str]) -> bool:
    """00:00~06:00 사이에 찍은 기록은 인정하지 않는다 (얼굴인식 프로그램의 계산 방식과 같다)."""
    return bool(t) and t >= "06:00:00"


def format_duration(seconds: float) -> str:
    """초를 'N시간 NN분' 형태로 바꾼다."""
    total = int(max(0, seconds))
    return f"{total // 3600}시간 {(total % 3600) // 60:02d}분"


@dataclass
class FaceAttendanceEntry:
    student_id: str
    name: str
    date: str                 # "yyyy-MM-dd"
    check_in: Optional[str]   # "HH:mm:ss" — 없으면 None
    check_out: Optional[str]

    @property
    def work_seconds(self) -> float:
        """출근~퇴근 인정 시간(초). 출근/퇴근 중 하나라도 없거나 00:00~06:00 기록이면 0."""
        if not _is_valid_time(self.check_in) or not _is_valid_time(self.check_out):
            return 0
        try:
            t_in = datetime.datetime.strptime(self.check_in, "%H:%M:%S")
            t_out = datetime.datetime.strptime(self.check_out, "%H:%M:%S")
        except ValueError:
            return 0
        return max(0, (t_out - t_in).total_seconds())

    @property
    def work_time_text(self) -> str:
        return format_duration(self.work_seconds)

    @property
    def date_value(self) -> Optional[datetime.date]:
        try:
            return datetime.datetime.strptime(self.date, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            return None


def parse_attendance(raw: list) -> list[FaceAttendanceEntry]:
    return [
        FaceAttendanceEntry(
            student_id=str(e.get("StudentId", "") or ""),
            name=e.get("Name", "") or "",
            date=e.get("Date", "") or "",
            check_in=e.get("CheckIn"),
            check_out=e.get("CheckOut"),
        )
        for e in raw
    ]


def load_attendance() -> list[FaceAttendanceEntry]:
    path = config.attendance_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return parse_attendance(json.load(f))
    except Exception:
        return []


def sort_latest_first(records: Iterable[FaceAttendanceEntry]) -> list[FaceAttendanceEntry]:
    """날짜 최신순 → 출근 시각 늦은 순 → 이름순."""
    rows = sorted(records, key=lambda r: r.name)
    rows.sort(key=lambda r: r.check_in or "", reverse=True)
    rows.sort(key=lambda r: r.date, reverse=True)
    return rows


def filter_records(records: Iterable[FaceAttendanceEntry], keyword: str = "",
                   date_from: Optional[datetime.date] = None,
                   date_to: Optional[datetime.date] = None) -> list[FaceAttendanceEntry]:
    """[기록 보기] 필터 — 학번/이름(대소문자 무시) + 기간."""
    kw = keyword.strip().lower()
    rows = []
    for r in records:
        if kw and kw not in r.student_id.lower() and kw not in r.name.lower():
            continue
        d = r.date_value
        if date_from is not None and (d is None or d < date_from):
            continue
        if date_to is not None and (d is None or d > date_to):
            continue
        rows.append(r)
    return sort_latest_first(rows)


def records_summary(records: list[FaceAttendanceEntry]) -> str:
    people = len({r.student_id for r in records})
    days = len({(r.student_id, r.date) for r in records})
    unfinished = sum(1 for r in records if r.check_in and not r.check_out)
    text = (f"{len(records)}건 · {people}명 · 출석 {days}일(학생별 합) · "
            f"총 근무 {format_duration(sum(r.work_seconds for r in records))}")
    if unfinished:
        text += f" · 퇴근 기록 없음 {unfinished}건"
    return text


def quick_range(tag: str, today: datetime.date) -> tuple[Optional[datetime.date], Optional[datetime.date]]:
    """[오늘/이번 주/이번 달/전체] 버튼이 정하는 기간."""
    start = {
        "today": today,
        "week": today - datetime.timedelta(days=today.weekday()),   # 월요일부터
        "month": today.replace(day=1),
    }.get(tag)
    return start, (today if start is not None else None)


def student_summary(records: list[FaceAttendanceEntry], today: datetime.date) -> str:
    """데이터 관리 탭 학생 상세의 합계 문구. records는 그 학생의 기록(최신순)."""
    if not records:
        return "얼굴인식 출결 기록이 없습니다."
    month_start = today.replace(day=1)
    this_month = [r for r in records if r.date_value is not None and r.date_value >= month_start]
    return (f"전체 출석 {len({r.date for r in records})}일 · 총 {format_duration(sum(r.work_seconds for r in records))}\n"
            f"이번 달 {len({r.date for r in this_month})}일 · {format_duration(sum(r.work_seconds for r in this_month))}\n"
            f"최근 출석 {records[0].date}")


# ---------------------------------------------------------------- 월간 기준
def weeks_of_month(year: int, month: int) -> list[tuple[datetime.date, datetime.date]]:
    """그 달에 걸친 주(월요일 시작) 목록. 달 경계에 걸친 주는 앞뒤 달 날짜까지 포함한 한 주 전체로 본다."""
    first = datetime.date(year, month, 1)
    last = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1) - datetime.timedelta(days=1)
    start = first - datetime.timedelta(days=first.weekday())
    weeks = []
    while start <= last:
        weeks.append((start, start + datetime.timedelta(days=6)))
        start += datetime.timedelta(days=7)
    return weeks


@dataclass
class WeeklyResult:
    start: datetime.date
    end: datetime.date
    seconds: float
    days: int
    finished: bool   # 주가 이미 끝났는지 — 끝나지 않은 주는 아직 못 채웠어도 실패로 보지 않는다

    @property
    def met(self) -> bool:
        return self.seconds >= WEEKLY_REQUIRED_HOURS * 3600 and self.days >= WEEKLY_REQUIRED_DAYS

    @property
    def state(self) -> str:
        return PASSED if self.met else (FAILED if self.finished else IN_PROGRESS)

    @property
    def text(self) -> str:
        mark = {PASSED: "✅", FAILED: "❌"}.get(self.state, "⏳")
        hours = f"{self.seconds / 3600:.1f}".rstrip("0").rstrip(".")
        return f"{mark} {hours}h · {self.days}회"


@dataclass
class MonthlyRow:
    student_id: str
    name: str
    weeks: list[WeeklyResult] = field(default_factory=list)

    @property
    def state(self) -> str:
        if any(w.state == FAILED for w in self.weeks):
            return FAILED
        return PASSED if all(w.state == PASSED for w in self.weeks) else IN_PROGRESS

    @property
    def passed_weeks(self) -> int:
        return sum(1 for w in self.weeks if w.met)

    @property
    def result_text(self) -> str:
        if self.state == PASSED:
            return "✅ 충족"
        if self.state == FAILED:
            return f"❌ 미충족 ({self.passed_weeks}/{len(self.weeks)}주)"
        return f"⏳ 진행 중 ({self.passed_weeks}/{len(self.weeks)}주)"


def evaluate_month(records: Iterable[FaceAttendanceEntry], year: int, month: int,
                   today: datetime.date) -> list[MonthlyRow]:
    """기록에 나온 학생마다 그 달의 주별 근무시간·출석일과 기준 충족 여부를 계산한다."""
    groups: dict[str, list[FaceAttendanceEntry]] = {}
    for r in records:
        if r.student_id.strip():
            groups.setdefault(r.student_id, []).append(r)
    weeks = weeks_of_month(year, month)
    rows = []
    for sid in sorted(groups):
        g = groups[sid]
        row = MonthlyRow(student_id=sid, name=max(g, key=lambda r: r.date).name)
        for start, end in weeks:
            in_week = [r for r in g if r.date_value is not None and start <= r.date_value <= end]
            row.weeks.append(WeeklyResult(
                start=start, end=end,
                seconds=sum(r.work_seconds for r in in_week),
                # 출석 횟수는 출근을 찍은 날 수 (하루에 여러 번 출근해도 1회)
                days=len({r.date for r in in_week if r.check_in}),
                finished=end < today,
            ))
        rows.append(row)
    return rows


def criteria_months(records: Iterable[FaceAttendanceEntry], today: datetime.date) -> list[str]:
    """월 목록 — 기록이 있는 달 + 이번 달, 최신순."""
    months = {r.date_value.strftime("%Y-%m") for r in records if r.date_value is not None}
    months.add(today.strftime("%Y-%m"))
    return sorted(months, reverse=True)


def criteria_rule_text() -> str:
    return f"기준: 매주(월~일) {WEEKLY_REQUIRED_HOURS}시간 이상 · {WEEKLY_REQUIRED_DAYS}회 이상 출석 — 모든 주를 채워야 충족"


def criteria_summary(month_text: str, all_rows: list[MonthlyRow], shown: int) -> str:
    def count(state: str) -> int:
        return sum(1 for r in all_rows if r.state == state)

    text = (f"{month_text} · {len(all_rows)}명 중 ✅ 충족 {count(PASSED)}명 · "
            f"❌ 미충족 {count(FAILED)}명 · ⏳ 진행 중 {count(IN_PROGRESS)}명")
    if shown != len(all_rows):
        text += f"  (표시 {shown}명)"
    return text
