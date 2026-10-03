"""
구글 폼 응답 시트 동기화 — C# 버전 GoogleFormsService.cs를 그대로 옮겼다.

- 메인 시트(상상Lab 신청 폼 응답)는 "원하는 공간" 답으로 상상Lab/캐비닛/기자재를 가른다.
- 캐비닛·기자재 전용 시트를 지정하면 그 시트의 모든 행을 해당 구분으로 받는다.
- 폼 질문 문구가 학기마다 바뀌므로 정규화한 헤더의 키워드로 열을 찾는다.
- SourceKey = "{시트ID}|{타임스탬프}|{학번}|{구분값}" — 이미 가져온 응답은 다시 들어오지 않는다.
"""
from __future__ import annotations

import datetime
import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .models import ApprovalRequest


@dataclass
class FormSyncResult:
    new_requests: list[ApprovalRequest] = field(default_factory=list)
    total_rows: int = 0
    duplicate_count: int = 0
    unmapped_spaces: list[str] = field(default_factory=list)
    missing_columns: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def is_success(self) -> bool:
        return self.error is None


def extract_spreadsheet_id(url_or_id: Optional[str]) -> str:
    """스프레드시트 주소나 ID에서 시트 ID만 뽑는다. 폼 주소처럼 API로 못 읽는 값이면 빈 문자열."""
    s = (url_or_id or "").strip()
    if not s:
        return ""
    m = re.search(r"/spreadsheets/d/([A-Za-z0-9_-]{20,})", s)
    if m:
        return m.group(1)
    if "/" not in s and re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return s
    return ""


def is_form_url(url_or_id: Optional[str]) -> bool:
    s = (url_or_id or "").lower()
    return "/forms/" in s or "forms.gle/" in s


def normalize(s: Optional[str]) -> str:
    """공백·줄바꿈·별표 등 장식 문자를 걷어내 비교 가능한 형태로 만든다."""
    if not s:
        return ""
    return "".join(ch.lower() for ch in s if not ch.isspace() and ch not in "*:~,.")


def map_tab_type(raw: Optional[str]) -> str:
    v = normalize(raw)
    if not v:
        return ""
    if "상상" in v or "lab" in v or "랩" in v:
        return "상상Lab"
    if any(k in v for k in ("캐비닛", "캐비넷", "사물함", "락커", "라커")):
        return "캐비닛"
    if any(k in v for k in ("기자재", "장비", "대여")):
        return "기자재"
    return ""


_KO_TS = re.compile(
    r"(\d{4})\s*[.\-/]\s*(\d{1,2})\s*[.\-/]\s*(\d{1,2})\.?\s*(?:(오전|오후|AM|PM)\s*)?(?:(\d{1,2}):(\d{2})(?::(\d{2}))?)?"
)


def _parse_ko(raw: str) -> Optional[datetime.datetime]:
    m = _KO_TS.search(raw)
    if not m:
        return None
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    ampm, hh, mm, ss = m.group(4), m.group(5), m.group(6), m.group(7)
    h = int(hh) if hh else 0
    if ampm in ("오후", "PM") and h < 12:
        h += 12
    if ampm in ("오전", "AM") and h == 12:
        h = 0
    try:
        return datetime.datetime(y, mo, d, h, int(mm) if mm else 0, int(ss) if ss else 0)
    except ValueError:
        return None


def parse_timestamp(raw: Optional[str]) -> datetime.datetime:
    if not raw or not raw.strip():
        return datetime.datetime.now()
    dt = _parse_ko(raw)
    if dt:
        return dt
    try:
        serial = float(raw)
        return datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)
    except (ValueError, OverflowError):
        return datetime.datetime.now()


def parse_optional_date(raw: Optional[str]) -> Optional[datetime.date]:
    if not raw or not raw.strip():
        return None
    dt = _parse_ko(raw)
    if dt:
        return dt.date()
    try:
        serial = float(raw)
        return (datetime.datetime(1899, 12, 30) + datetime.timedelta(days=serial)).date()
    except (ValueError, OverflowError):
        return None


class ColumnMap:
    """헤더 행에서 각 항목의 열 위치를 키워드로 찾아둔다 (구체적인 키워드부터 순서대로)."""

    def __init__(self, header: list, is_main_form: bool = True):
        self._header = [normalize(str(h) if h is not None else "") for h in header]
        f = self._find
        self.timestamp = f("타임스탬프", "timestamp")
        self.space = f("공간을선택", "공간")
        self.department = f("소속", "전공")
        self.name = f("이름")
        self.student_id = f("학번")
        self.phone = f("연락처", "전화", "휴대")
        self.email = f("이메일", "메일")
        self.advisor = f("지도교수", "교수")
        self.plan = f("계획서")
        self.note = f("기타의견", "기타", "특이사항")
        self.equipment = f("대여품목", "기자재종류", "대여물품", "기자재", "장비", "품목")
        self.year_level = f("학년")
        self.location = f("사용장소", "장소")
        self.purpose = f("사용목적", "목적")
        self.due_date = f("반납예정일", "반납예정", "반납")
        self.rental_period = f("대여기간", "신청기간", "사용기간", "기간")
        self.approval_status = f("승인상태", "승인여부", "승인", "상태")

        # "원하는 공간" 질문의 보기 안에 '기자재'가 들어 있으면 같은 열이 잡힌다 — 떼어낸다
        if self.equipment >= 0 and self.equipment == self.space:
            self.equipment = -1

        self.missing: list[str] = []
        self._check(self.department, "소속")
        self._check(self.student_id, "학번")
        self._check(self.advisor, "지도교수")
        if is_main_form:
            self._check(self.space, "원하는 공간")
            self._check(self.name, "이름")
            self._check(self.email, "이메일")

    def _check(self, idx: int, label: str):
        if idx < 0:
            self.missing.append(label)

    def _find(self, *keywords: str) -> int:
        for kw in keywords:
            for i, h in enumerate(self._header):
                if kw in h:
                    return i
        return -1

    @staticmethod
    def get(row: list, idx: int) -> str:
        if idx < 0 or idx >= len(row):
            return ""
        v = row[idx]
        return str(v).strip() if v is not None else ""


class GoogleFormsService:
    def __init__(self, key_path: str, spreadsheet_id: str):
        self._key_path = key_path
        self._service = None
        self.spreadsheet_id = spreadsheet_id
        self.equipment_spreadsheet_id = ""
        self.cabinet_spreadsheet_id = ""
        self.service_account_email = ""

    @property
    def key_path(self) -> str:
        return self._key_path

    @key_path.setter
    def key_path(self, value: str):
        if value != self._key_path:
            self._key_path = value
            self._service = None
            self.service_account_email = ""

    @property
    def key_file_exists(self) -> bool:
        return os.path.exists(self._key_path)

    def _get_service(self):
        if self._service is not None:
            return self._service
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
        creds = Credentials.from_service_account_file(
            self._key_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        self.service_account_email = creds.service_account_email or ""
        self._service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        return self._service

    def fetch(self, is_already_known: Callable[[str], bool]) -> FormSyncResult:
        result = FormSyncResult()
        if not self.spreadsheet_id.strip():
            result.error = "스프레드시트 ID가 설정되지 않았습니다. [설정] 탭에서 입력해주세요."
            return result
        if not self.key_file_exists:
            result.error = f"서비스 계정 키 파일을 찾을 수 없습니다.\n{self._key_path}"
            return result
        try:
            import googleapiclient  # noqa: F401
        except ImportError:
            result.error = ("구글 연동 라이브러리가 설치되어 있지 않습니다.\n"
                            "pip install google-api-python-client google-auth 를 실행해 주세요.")
            return result

        self._fetch_sheet(result, self.spreadsheet_id.strip(), None, is_already_known)
        if not result.is_success:
            return result

        fetched = {self.spreadsheet_id.strip()}
        self._merge_dedicated(result, self.equipment_spreadsheet_id, "기자재", fetched, is_already_known)
        self._merge_dedicated(result, self.cabinet_spreadsheet_id, "캐비닛", fetched, is_already_known)
        return result

    def _merge_dedicated(self, target: FormSyncResult, sheet_id: str, tab_type: str,
                         fetched: set, is_already_known):
        sid = (sheet_id or "").strip()
        if not sid or sid in fetched:
            return
        fetched.add(sid)
        sheet = FormSyncResult()
        self._fetch_sheet(sheet, sid, tab_type, is_already_known)
        if not sheet.is_success:
            target.warnings.append(f"{tab_type} 시트를 읽지 못했습니다 — {sheet.error}")
            return
        target.new_requests.extend(sheet.new_requests)
        target.total_rows += sheet.total_rows
        target.duplicate_count += sheet.duplicate_count
        for m in sheet.missing_columns:
            target.missing_columns.append(f"({tab_type} 시트) {m}")

    def _fetch_sheet(self, result: FormSyncResult, sheet_id: str, forced_tab_type: Optional[str], is_already_known):
        try:
            service = self._get_service()
            meta = service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            sheets = meta.get("sheets") or []
            if not sheets:
                result.error = "스프레드시트에 시트가 없습니다."
                return
            tab_name = sheets[0]["properties"]["title"]
            resp = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{tab_name}'!A:Z").execute()
            rows = resp.get("values") or []
            if not rows:
                result.error = "시트가 비어 있습니다."
                return

            cmap = ColumnMap(rows[0], is_main_form=forced_tab_type is None)
            result.missing_columns.extend(cmap.missing)
            if cmap.student_id < 0:
                result.error = "시트 헤더에서 '학번' 컬럼을 찾지 못했습니다.\n구글 폼 질문 문구를 확인해주세요."
                return
            if cmap.name < 0 and forced_tab_type is None:
                result.error = "시트 헤더에서 '이름' 컬럼을 찾지 못했습니다.\n구글 폼 질문 문구를 확인해주세요."
                return

            result.total_rows = len(rows) - 1
            g = ColumnMap.get
            for row in rows[1:]:
                name = g(row, cmap.name)
                student_id = g(row, cmap.student_id)
                if not name.strip() and not student_id.strip():
                    result.total_rows -= 1
                    continue

                raw_ts = g(row, cmap.timestamp)
                equipment_type = g(row, cmap.equipment)
                raw_space = g(row, cmap.space) if forced_tab_type is None else ""
                tab_type = forced_tab_type or map_tab_type(raw_space)
                if not tab_type and raw_space and raw_space not in result.unmapped_spaces:
                    result.unmapped_spaces.append(raw_space)

                discriminator = raw_space if forced_tab_type is None else equipment_type
                source_key = f"{sheet_id}|{raw_ts}|{student_id}|{discriminator}"
                if is_already_known(source_key):
                    result.duplicate_count += 1
                    continue

                result.new_requests.append(ApprovalRequest(
                    student_name=name,
                    student_id=student_id,
                    department=g(row, cmap.department),
                    advisor=g(row, cmap.advisor),
                    email=g(row, cmap.email),
                    phone=g(row, cmap.phone),
                    plan_url=g(row, cmap.plan),
                    note=g(row, cmap.note),
                    equipment_type=equipment_type,
                    year_level=g(row, cmap.year_level),
                    location=g(row, cmap.location),
                    purpose=g(row, cmap.purpose),
                    due_date=parse_optional_date(g(row, cmap.due_date)),
                    rental_period=g(row, cmap.rental_period),
                    tab_type=tab_type or "미분류",
                    request_date=parse_timestamp(raw_ts),
                    source_key=source_key,
                    status="승인 대기",
                    sheet_approval_status=g(row, cmap.approval_status) if cmap.approval_status >= 0 else "",
                ))
        except Exception as ex:  # noqa: BLE001
            status = getattr(getattr(ex, "resp", None), "status", None)
            if status == 403:
                result.error = ("시트 접근이 거부되었습니다(403).\n"
                                f"스프레드시트를 서비스 계정({self.service_account_email})에 '뷰어'로 공유했는지, "
                                "Google Cloud에서 Sheets API를 사용 설정했는지 확인해주세요.")
            elif status == 404:
                result.error = "스프레드시트를 찾을 수 없습니다(404). ID를 확인해주세요."
            elif status is not None:
                result.error = f"구글 API 오류: {ex}"
            else:
                result.error = f"동기화 실패: {ex}"
