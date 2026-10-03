"""
C# 버전의 Models.cs에 대응하는 데이터 모델.
좌석 배정·캐비닛 현황·기자재 대여·데이터 관리 핵심 기능만 옮겼다
(구글폼 연동·출석·학사 시즌 일정 등은 다음 단계에서 추가한다).
"""
from __future__ import annotations

import datetime
import re
import uuid
from dataclasses import dataclass, field
from typing import Optional


def _parse_dt(s: str | None) -> datetime.datetime | None:
    """C# System.Text.Json 날짜("2026-09-20T15:38:12.1234567+09:00")와 파이썬 isoformat을 모두 읽는다."""
    if not s:
        return None
    s = s.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(?:\.(\d+))?)?", s)
    if not m:
        return None
    text = m.group(1)
    if m.group(2):
        text += "T" + m.group(2)
        if m.group(3):
            text += "." + m.group(3)[:6].ljust(6, "0")
    try:
        return datetime.datetime.fromisoformat(text)
    except ValueError:
        return None


def _parse_d(s: str | None) -> datetime.date | None:
    dt = _parse_dt(s)
    return dt.date() if dt else None


@dataclass
class AttendanceRecord:
    date_string: str = ""
    status: str = ""  # "출석" / "결석" / "지각"

    def to_dict(self) -> dict:
        return {"DateString": self.date_string, "Status": self.status}

    @staticmethod
    def from_dict(d: dict) -> "AttendanceRecord":
        return AttendanceRecord(
            date_string=d.get("DateString", ""),
            status=d.get("Status", ""),
        )


@dataclass
class StudentInfo:
    department: str = ""       # 소속
    name: str = ""             # 이름
    advisor: str = ""          # 지도교수
    student_id: str = ""       # 학번
    email: str = ""            # 이메일
    contact: str = ""          # 연락처
    cabinet_period: str = ""   # 대여 기간
    last_active_season: str = ""  # "{연도}_{시즌}" — 데이터 관리 탭 필터에는 안 쓰지만 좌석 배정과 맞춰둔다
    attendance: list[AttendanceRecord] = field(default_factory=list)

    def clone(self) -> "StudentInfo":
        return StudentInfo(
            department=self.department,
            name=self.name,
            advisor=self.advisor,
            student_id=self.student_id,
            email=self.email,
            contact=self.contact,
            cabinet_period=self.cabinet_period,
            last_active_season=self.last_active_season,
            attendance=[AttendanceRecord(a.date_string, a.status) for a in self.attendance],
        )

    def to_dict(self) -> dict:
        return {
            "Department": self.department,
            "Name": self.name,
            "Advisor": self.advisor,
            "StudentId": self.student_id,
            "Email": self.email,
            "Contact": self.contact,
            "CabinetPeriod": self.cabinet_period,
            "LastActiveSeason": self.last_active_season,
            "Attendance": [a.to_dict() for a in self.attendance],
        }

    @staticmethod
    def from_dict(d: dict) -> "StudentInfo":
        return StudentInfo(
            department=d.get("Department", ""),
            name=d.get("Name", ""),
            advisor=d.get("Advisor", ""),
            student_id=d.get("StudentId", ""),
            email=d.get("Email", ""),
            contact=d.get("Contact", ""),
            cabinet_period=d.get("CabinetPeriod", ""),
            last_active_season=d.get("LastActiveSeason", ""),
            attendance=[AttendanceRecord.from_dict(a) for a in d.get("Attendance", [])],
        )

    def is_graduate(self) -> bool:
        return "대학원" in (self.department or "")


@dataclass
class Seat:
    seat_number: int = 0
    student: Optional[StudentInfo] = None
    is_fixed: bool = False
    is_selected: bool = False
    is_pillar: bool = False

    def to_dict(self) -> dict:
        return {
            "SeatNumber": self.seat_number,
            "Student": self.student.to_dict() if self.student else None,
            "IsFixed": self.is_fixed,
            "IsSelected": self.is_selected,
            "IsPillar": self.is_pillar,
        }

    @staticmethod
    def from_dict(d: dict) -> "Seat":
        stu = d.get("Student")
        return Seat(
            seat_number=d.get("SeatNumber", 0),
            student=StudentInfo.from_dict(stu) if stu else None,
            is_fixed=d.get("IsFixed", False),
            is_selected=d.get("IsSelected", False),
            is_pillar=d.get("IsPillar", False),
        )

    def is_locked(self) -> bool:
        """고정된 좌석이거나 대학원생 좌석이면 옮길 수 없다."""
        return self.is_fixed or (self.student is not None and self.student.is_graduate())


@dataclass
class CabinetAllocation:
    cabinet_num: int = 0
    student: Optional[StudentInfo] = None
    period: str = ""  # "YY.MM.DD ~ YY.MM.DD"

    def to_dict(self) -> dict:
        return {
            "CabinetNum": self.cabinet_num,
            "Student": self.student.to_dict() if self.student else None,
            "Period": self.period,
        }

    @staticmethod
    def from_dict(d: dict) -> "CabinetAllocation":
        stu = d.get("Student")
        return CabinetAllocation(
            cabinet_num=d.get("CabinetNum", 0),
            student=StudentInfo.from_dict(stu) if stu else None,
            period=d.get("Period", ""),
        )


def _extract_unit_number(equipment_type: str) -> str:
    """"(No .17)" "(No.17)" "17번" 처럼 흔들리는 표기를 모두 "No. 17"로 맞춘다."""
    if not equipment_type:
        return ""
    m = re.search(r"no\s*\.?\s*(\d+)", equipment_type, re.IGNORECASE)
    if not m:
        m = re.search(r"(\d+)\s*번(?![가-힣])", equipment_type)
    return f"No. {m.group(1)}" if m else ""


@dataclass
class RentalItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    student_name: str = ""
    equipment_type: str = ""
    rental_date: datetime.date = field(default_factory=datetime.date.today)
    rental_period_days: int = 7
    is_returned: bool = False

    quantity: int = 1
    extra_items: str = ""
    location: str = "DSU 창의공간"
    purpose: str = "개인 실습"
    remarks: str = ""
    department: str = "소프트웨어융합학과"
    year_level: str = "3학년"
    student_id: str = "20261234"
    phone: str = "010-0000-0000"
    advisor: str = "김동욱 교수"
    return_date: Optional[datetime.date] = None

    @property
    def due_date(self) -> datetime.date:
        return self.rental_date + datetime.timedelta(days=self.rental_period_days)

    def is_overdue(self, today: datetime.date) -> bool:
        return not self.is_returned and self.due_date < today

    def is_warning(self, today: datetime.date) -> bool:
        return not self.is_returned and not self.is_overdue(today) and (self.due_date - today).days <= 7

    @property
    def is_mainframe(self) -> bool:
        return any(k in self.equipment_type for k in ("VR", "Quest", "본체"))

    @property
    def unit_number(self) -> str:
        return _extract_unit_number(self.equipment_type)

    @property
    def display_equipment(self) -> str:
        base = "본체" if self.is_mainframe else "노트북"
        no = self.unit_number
        return f"{base} ({no})" if no else base

    def to_dict(self) -> dict:
        return {
            "Id": self.id,
            "StudentName": self.student_name,
            "EquipmentType": self.equipment_type,
            "RentalDate": self.rental_date.isoformat(),
            "RentalPeriodDays": self.rental_period_days,
            "IsReturned": self.is_returned,
            "Quantity": self.quantity,
            "ExtraItems": self.extra_items,
            "Location": self.location,
            "Purpose": self.purpose,
            "Remarks": self.remarks,
            "Department": self.department,
            "YearLevel": self.year_level,
            "StudentId": self.student_id,
            "Phone": self.phone,
            "Advisor": self.advisor,
            "ReturnDate": self.return_date.isoformat() if self.return_date else None,
        }

    @staticmethod
    def from_dict(d: dict) -> "RentalItem":
        def pdate(s):
            return _parse_d(s)

        return RentalItem(
            id=d.get("Id") or str(uuid.uuid4()),
            student_name=d.get("StudentName", ""),
            equipment_type=d.get("EquipmentType", ""),
            rental_date=pdate(d.get("RentalDate")) or datetime.date.today(),
            rental_period_days=d.get("RentalPeriodDays", 7),
            is_returned=d.get("IsReturned", False),
            quantity=d.get("Quantity", 1),
            extra_items=d.get("ExtraItems", ""),
            location=d.get("Location", "DSU 창의공간"),
            purpose=d.get("Purpose", "개인 실습"),
            remarks=d.get("Remarks", ""),
            department=d.get("Department", ""),
            year_level=d.get("YearLevel", ""),
            student_id=d.get("StudentId", ""),
            phone=d.get("Phone", ""),
            advisor=d.get("Advisor", ""),
            return_date=pdate(d.get("ReturnDate")),
        )


@dataclass
class EquipmentIssue:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    report_date: datetime.datetime = field(default_factory=datetime.datetime.now)
    equipment_name: str = "노트북"  # "본체" 또는 "노트북"
    unit_number: int = 0
    issue_type: str = ""  # "고장" / "수리" / "기타"
    detail: str = ""

    @property
    def display_unit(self) -> str:
        return f"{self.equipment_name} No. {self.unit_number}"

    @property
    def display_detail(self) -> str:
        return self.detail if self.detail.strip() else self.issue_type

    def to_dict(self) -> dict:
        return {
            "Id": self.id,
            "ReportDate": self.report_date.isoformat(),
            "EquipmentName": self.equipment_name,
            "UnitNumber": self.unit_number,
            "IssueType": self.issue_type,
            "Detail": self.detail,
        }

    @staticmethod
    def from_dict(d: dict) -> "EquipmentIssue":
        rd = d.get("ReportDate")
        return EquipmentIssue(
            id=d.get("Id") or str(uuid.uuid4()),
            report_date=_parse_dt(rd) or datetime.datetime.now(),
            equipment_name=d.get("EquipmentName", "노트북"),
            unit_number=d.get("UnitNumber", 0),
            issue_type=d.get("IssueType", ""),
            detail=d.get("Detail", ""),
        )


@dataclass
class MemoItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""

    def to_dict(self) -> dict:
        return {"Id": self.id, "Content": self.content}

    @staticmethod
    def from_dict(d: dict) -> "MemoItem":
        return MemoItem(id=d.get("Id") or str(uuid.uuid4()), content=d.get("Content", ""))


@dataclass
class ApprovalRequest:
    """구글 폼으로 들어온 신청 1건 (상상Lab / 캐비닛 / 기자재)."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    student_name: str = ""
    department: str = ""
    student_id: str = ""
    advisor: str = ""
    email: str = ""
    tab_type: str = ""  # "상상Lab" / "캐비닛" / "기자재" / "미분류"
    equipment_type: str = ""
    request_date: datetime.datetime = field(default_factory=datetime.datetime.now)
    status: str = "승인 대기"  # "승인 대기" / "승인 완료" / "반려"
    rental_period: str = ""
    sheet_approval_status: str = ""
    phone: str = ""
    plan_url: str = ""
    note: str = ""
    year_level: str = ""
    location: str = ""
    purpose: str = ""
    due_date: Optional[datetime.date] = None
    source_key: str = ""  # 구글 폼 응답 1건의 고유 키(중복 등록 방지)

    def to_dict(self) -> dict:
        return {
            "Id": self.id,
            "StudentName": self.student_name,
            "Department": self.department,
            "StudentId": self.student_id,
            "Advisor": self.advisor,
            "Email": self.email,
            "TabType": self.tab_type,
            "EquipmentType": self.equipment_type,
            "RequestDate": self.request_date.isoformat(),
            "Status": self.status,
            "RentalPeriod": self.rental_period,
            "SheetApprovalStatus": self.sheet_approval_status,
            "Phone": self.phone,
            "PlanUrl": self.plan_url,
            "Note": self.note,
            "YearLevel": self.year_level,
            "Location": self.location,
            "Purpose": self.purpose,
            "DueDate": self.due_date.isoformat() if self.due_date else None,
            "SourceKey": self.source_key,
        }

    @staticmethod
    def from_dict(d: dict) -> "ApprovalRequest":
        rd = d.get("RequestDate")
        dd = d.get("DueDate")
        return ApprovalRequest(
            id=d.get("Id") or str(uuid.uuid4()),
            student_name=d.get("StudentName", ""),
            department=d.get("Department", ""),
            student_id=d.get("StudentId", ""),
            advisor=d.get("Advisor", ""),
            email=d.get("Email", ""),
            tab_type=d.get("TabType", ""),
            equipment_type=d.get("EquipmentType", ""),
            request_date=_parse_dt(rd) or datetime.datetime.now(),
            status=d.get("Status", "승인 대기"),
            rental_period=d.get("RentalPeriod", ""),
            sheet_approval_status=d.get("SheetApprovalStatus", ""),
            phone=d.get("Phone", ""),
            plan_url=d.get("PlanUrl", ""),
            note=d.get("Note", ""),
            year_level=d.get("YearLevel", ""),
            location=d.get("Location", ""),
            purpose=d.get("Purpose", ""),
            due_date=_parse_d(dd),
            source_key=d.get("SourceKey", ""),
        )


SEASON_NAMES = ["1학기", "여름방학", "2학기", "겨울방학"]


@dataclass
class SeasonPeriod:
    name: str = ""
    start_date: datetime.date = field(default_factory=datetime.date.today)
    end_date: datetime.date = field(default_factory=datetime.date.today)

    def to_dict(self) -> dict:
        return {"Name": self.name, "StartDate": self.start_date.isoformat(), "EndDate": self.end_date.isoformat()}

    @staticmethod
    def from_dict(d: dict) -> "SeasonPeriod":
        return SeasonPeriod(
            name=d.get("Name", ""),
            start_date=_parse_d(d.get("StartDate")) or datetime.date.today(),
            end_date=_parse_d(d.get("EndDate")) or datetime.date.today(),
        )


@dataclass
class YearSeasonSchedule:
    year: int = 0
    seasons: list[SeasonPeriod] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"Year": self.year, "Seasons": [s.to_dict() for s in self.seasons]}

    @staticmethod
    def from_dict(d: dict) -> "YearSeasonSchedule":
        return YearSeasonSchedule(year=d.get("Year", 0), seasons=[SeasonPeriod.from_dict(s) for s in d.get("Seasons", [])])


def default_seasons_for(year: int) -> list[SeasonPeriod]:
    """1학기 3/1~6/30, 여름방학 7/1~8/31, 2학기 9/1~12/31, 겨울방학 다음 해 1/1~2월 말일."""
    import calendar
    next_feb_end = calendar.monthrange(year + 1, 2)[1]
    return [
        SeasonPeriod("1학기", datetime.date(year, 3, 1), datetime.date(year, 6, 30)),
        SeasonPeriod("여름방학", datetime.date(year, 7, 1), datetime.date(year, 8, 31)),
        SeasonPeriod("2학기", datetime.date(year, 9, 1), datetime.date(year, 12, 31)),
        SeasonPeriod("겨울방학", datetime.date(year + 1, 1, 1), datetime.date(year + 1, 2, next_feb_end)),
    ]


@dataclass
class SeasonConfig:
    schedules: list[YearSeasonSchedule] = field(default_factory=list)

    def get_year(self, year: int) -> YearSeasonSchedule | None:
        return next((s for s in self.schedules if s.year == year), None)

    def has_year(self, year: int) -> bool:
        return self.get_year(year) is not None

    def ensure_year(self, year: int) -> YearSeasonSchedule:
        sched = self.get_year(year)
        if sched is None:
            sched = YearSeasonSchedule(year=year, seasons=default_seasons_for(year))
            self.schedules.append(sched)
            self.schedules.sort(key=lambda s: s.year)
        return sched

    def remove_year(self, year: int) -> None:
        self.schedules = [s for s in self.schedules if s.year != year]

    def years(self) -> list[int]:
        return sorted(s.year for s in self.schedules)

    def resolve_season(self, date: datetime.date) -> tuple[int, str] | None:
        """오늘 날짜가 포함되는 (연도, 시즌 이름). 어느 시즌에도 들지 않으면 None."""
        for sched in self.schedules:
            for p in sched.seasons:
                if p.start_date <= date <= p.end_date:
                    return sched.year, p.name
        return None

    def to_dict(self) -> dict:
        return {"Schedules": [s.to_dict() for s in self.schedules]}

    @staticmethod
    def from_dict(d: dict) -> "SeasonConfig":
        cfg = SeasonConfig(schedules=[YearSeasonSchedule.from_dict(s) for s in d.get("Schedules", [])])
        cfg.schedules.sort(key=lambda s: s.year)
        return cfg
