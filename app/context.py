"""
앱 전체가 함께 쓰는 상태와 화면을 가로지르는 로직.
C# 버전은 MainWindow 한 클래스(partial)에 모든 상태·로직이 있었는데, 파이썬 버전은 화면을
파일별로 나누었으므로 그 공용 부분(현재 시즌, 대여 기간 계산, 마스터 등록, 승인/반려/복구,
구글 동기화, 기간 만료 정리 등)을 여기로 모았다. 각 메서드는 같은 이름의 C# 메서드를 그대로 옮긴 것이다.
"""
from __future__ import annotations

import datetime
import os
import re
from typing import Optional, TYPE_CHECKING

from . import storage, face_integration, config
from .constants import TOTAL_CABINETS, format_period, parse_period_dates
from .models import (
    StudentInfo, AttendanceRecord, ApprovalRequest, CabinetAllocation, RentalItem, SeasonConfig,
)

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

DEFAULT_SPREADSHEET_ID = "1TejlN7HTU7n2mvkKIilCrMlSivHsey3h-nOuFOeR7t4"
DEFAULT_EQUIPMENT_SPREADSHEET_ID = "152AqDmrq6LF82E41bMNVOeD74h0Ks4VXAAyzHlA4gVw"
DEFAULT_CABINET_SPREADSHEET_ID = "1JL6TKyzYUFd2K7_66JXk6_SPr1me0Rr3UqwRua7DZtk"


class AppContext:
    def __init__(self):
        self.seat_cache = storage.load_seat_cache()
        for seats in self.seat_cache.values():   # 예전 데이터에서 22번 좌석을 기둥으로 잘못 저장했으면 바로잡는다
            for s in seats:
                if s.seat_number == 22:
                    s.is_pillar = False
        self.state = storage.load_app_state()
        self.season_config: SeasonConfig = storage.load_season_config()
        self.settings: dict = storage.load_settings()
        self.current_season: Optional[tuple[int, str]] = None
        self.active_cabinet_period = ""
        self.kept_expired_keys: set[str] = set()
        self.win: "MainWindow" = None  # type: ignore  (MainWindow가 만들어진 뒤 채운다)
        self._seed_default_season_years()
        self._migrate_settings()

    # ------------------------------------------------------------------ 날짜
    @property
    def today(self) -> datetime.date:
        return datetime.date.today()

    # ------------------------------------------------------------------ 저장
    def save_seat_cache(self):
        storage.save_seat_cache(self.seat_cache)

    def save_app_state(self):
        storage.save_app_state(self.state)
        face_integration.export_roster(self.state.master_students)

    def save_seasons(self):
        storage.save_season_config(self.season_config)

    def save_settings(self):
        storage.save_settings(self.settings)

    def save_all(self):
        self.save_seat_cache()
        self.save_app_state()
        self.save_seasons()

    # ------------------------------------------------------------------ 설정
    def _migrate_settings(self):
        s = self.settings
        if "PollingIntervalSec" in s and "PollingIntervalSeconds" not in s:
            s["PollingIntervalSeconds"] = s.pop("PollingIntervalSec")
        s.setdefault("PollingEnabled", True)
        s.setdefault("PollingIntervalSeconds", 60)
        s.setdefault("KeyPathOverride", "")
        if not s.get("SangsangLabFormUrl") and s.get("SpreadsheetId"):
            s["SangsangLabFormUrl"] = s["SpreadsheetId"]
        if not s.get("SangsangLabFormUrl"):
            s["SangsangLabFormUrl"] = DEFAULT_SPREADSHEET_ID
        if not s.get("EquipmentFormUrl"):
            s["EquipmentFormUrl"] = DEFAULT_EQUIPMENT_SPREADSHEET_ID
        if not s.get("CabinetFormUrl"):
            s["CabinetFormUrl"] = DEFAULT_CABINET_SPREADSHEET_ID

    def resolve_service_account_key_path(self) -> str:
        """지정 경로 → 표준 위치 → 실행 파일 옆 순으로 키 파일을 찾는다 (AppConfig.ResolveServiceAccountKeyPath)."""
        import sys
        exe_dir = os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(sys.argv[0] or "."))
        for c in (self.settings.get("KeyPathOverride", ""), config.google_service_account_path(),
                  os.path.join(exe_dir, "google-service-account.json")):
            if c and os.path.exists(c):
                return c
        return config.google_service_account_path()

    # ------------------------------------------------------------------ 시즌
    def _seed_default_season_years(self):
        if self.season_config.schedules:
            return
        cy = self.today.year
        for y in (cy - 1, cy, cy + 1):
            self.season_config.ensure_year(y)
        self.save_seasons()

    def current_season_key(self) -> str:
        if self.current_season is not None:
            return f"{self.current_season[0]}_{self.current_season[1]}"
        if self.win is not None:
            return self.win.dashboard.combo_season_key()
        return f"{self.today.year}_1학기"

    def current_season_end_date(self) -> Optional[datetime.date]:
        if self.current_season is None:
            return None
        sched = self.season_config.get_year(self.current_season[0])
        if sched is None:
            return None
        p = next((x for x in sched.seasons if x.name == self.current_season[1]), None)
        return p.end_date if p else None

    def season_cabinet_period(self) -> str:
        """캐비닛 대여 기간 — 오늘부터 이번 시즌 마지막 날까지. 시즌이 없거나 끝났으면 오늘부터 한 달."""
        end = self.current_season_end_date()
        if end is None or end < self.today:
            return format_period(self.today, _add_months(self.today, 1))
        return format_period(self.today, end)

    @property
    def default_cabinet_period(self) -> str:
        if self.current_season_end_date() is not None:
            return self.season_cabinet_period()
        return self.active_cabinet_period or format_period(self.today, _add_months(self.today, 1))

    # ------------------------------------------------------------------ 기간 계산
    def parse_period_dates(self, period: str):
        r = parse_period_dates(period or "")
        if r:
            return r
        md = re.findall(r"(\d{1,2})/(\d{1,2})", period or "")
        if len(md) >= 2:
            y = self.today.year
            try:
                start = datetime.date(y, int(md[0][0]), int(md[0][1]))
                end = datetime.date(y, int(md[1][0]), int(md[1][1]))
                if end < start:
                    end = end.replace(year=y + 1)
                return start, end
            except ValueError:
                return None
        return None

    def are_periods_overlapping(self, p1: str, p2: str) -> bool:
        if not (p1 or "").strip() or not (p2 or "").strip():
            return True
        r1, r2 = self.parse_period_dates(p1), self.parse_period_dates(p2)
        if r1 is None or r2 is None:
            return p1.strip().lower() == p2.strip().lower()
        return r1[0] <= r2[1] and r2[0] <= r1[1]

    def merge_periods(self, p1: str, p2: str) -> str:
        r1, r2 = self.parse_period_dates(p1), self.parse_period_dates(p2)
        if r1 is None or r2 is None:
            return f"{p1} / {p2}"
        return format_period(min(r1[0], r2[0]), max(r1[1], r2[1]))

    def find_cabinet_conflict(self, req: ApprovalRequest) -> str:
        allocated = next(((n, a) for n, a in self.state.cabinet_allocations.items()
                          if a.student and a.student.student_id == req.student_id), None)
        if allocated and self.are_periods_overlapping(req.rental_period, allocated[1].period):
            return f"이미 {allocated[0]}번 캐비닛에 배정됨 ({allocated[1].period})"
        pending = next((a for a in self.state.approvals
                        if a.tab_type == "캐비닛" and a.student_id == req.student_id
                        and self.are_periods_overlapping(req.rental_period, a.rental_period)), None)
        if pending:
            return f"승인 대기 중인 신청과 기간 중복 ({pending.rental_period})"
        return ""

    def update_master_cabinet_periods(self):
        for st in self.state.master_students:
            alloc = next((a for a in self.state.cabinet_allocations.values()
                          if a.student and a.student.student_id == st.student_id), None)
            st.cabinet_period = alloc.period if alloc else ""

    def find_student_period(self, student: StudentInfo) -> str:
        if (student.cabinet_period or "").strip():
            return student.cabinet_period
        alloc = next((a for a in self.state.cabinet_allocations.values()
                      if a.student and a.student.student_id == student.student_id), None)
        if alloc and alloc.period.strip():
            return alloc.period
        approved = [a for a in self.state.approval_history
                    if a.student_id == student.student_id and a.status == "승인 완료" and a.rental_period.strip()]
        return approved[-1].rental_period if approved else ""

    # ------------------------------------------------------------------ 마스터
    def confirm_name_conflict(self, message: str) -> bool:
        from . import widgets as w
        return w.ask_warn(self.win, message, "학번 중복")

    def mark_student_active(self, student: Optional[StudentInfo]):
        if student is None or not student.student_id.strip():
            return
        m = next((x for x in self.state.master_students if x.student_id == student.student_id), None)
        if m:
            m.last_active_season = self.current_season_key()

    def migrate_students_without_season(self):
        key = self.current_season_key()
        for st in self.state.master_students:
            if not st.last_active_season.strip():
                st.last_active_season = key

    def register_or_update_master(self, req: ApprovalRequest) -> Optional[StudentInfo]:
        existing = next((m for m in self.state.master_students if m.student_id == req.student_id), None)
        if existing is None:
            created = StudentInfo(
                student_id=req.student_id, name=req.student_name, department=req.department,
                advisor=req.advisor, email=req.email, last_active_season=self.current_season_key(),
            )
            created.attendance.append(AttendanceRecord(self.today.isoformat(), "출석"))
            self.state.master_students.append(created)
            return created

        if req.student_name.strip() and existing.name != req.student_name:
            ok = self.confirm_name_conflict(
                f"학번 {req.student_id}이(가) 이미 다른 이름으로 등록되어 있습니다.\n\n"
                f"[기존]  {existing.name} / {existing.department} / {existing.advisor}\n"
                f"[신청]  {req.student_name} / {req.department} / {req.advisor}\n\n"
                "신청 내용으로 덮어쓸까요?\n"
                "· 예    → 마스터를 신청 내용으로 수정하고 승인합니다\n"
                "· 아니오 → 승인을 취소합니다 (학번을 확인해주세요)"
            )
            if not ok:
                return None

        existing.name = prefer(req.student_name, existing.name)
        existing.department = prefer(req.department, existing.department)
        existing.advisor = prefer(req.advisor, existing.advisor)
        existing.email = prefer(req.email, existing.email)
        existing.last_active_season = self.current_season_key()
        return existing


def prefer(incoming: str, current: str) -> str:
    return current if not (incoming or "").strip() else incoming


def _add_months(d: datetime.date, n: int) -> datetime.date:
    import calendar
    m = d.month - 1 + n
    y = d.year + m // 12
    m = m % 12 + 1
    return datetime.date(y, m, min(d.day, calendar.monthrange(y, m)[1]))
