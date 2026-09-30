"""
구글 폼(구글 시트) 연동 — 상상Lab · 캐비닛 · 기자재 신청 응답 시트를 읽어 ApprovalRequest로 만든다.
C# 버전의 구글 시트 폴링 로직(응답 헤더를 보고 학번/이름/연락처/이메일/지도교수 열을 찾는 방식)과
같은 방식을 쓴다. 실제 동기화에는 google-api-python-client와 서비스 계정 키가 필요하다
(둘 다 없으면 GoogleIntegrationError를 던진다 — 화면에서 안내 메시지로 보여주면 된다).
"""
from __future__ import annotations

import datetime
import re

from . import io_import as ioimp
from .models import ApprovalRequest


class GoogleIntegrationError(Exception):
    pass


def _extract_sheet_id(url_or_id: str) -> str:
    url_or_id = url_or_id.strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]+)", url_or_id)
    if m:
        return m.group(1)
    return url_or_id  # 이미 순수 ID로 입력했을 수도 있다


def fetch_sheet_rows(spreadsheet_url_or_id: str, service_account_path: str, sheet_range: str = "A1:Z1000") -> list[list[str]]:
    """지정한 구글 시트의 첫 번째 시트 값을 읽어 행 목록으로 돌려준다."""
    try:
        from google.oauth2.service_account import Credentials
        from googleapiclient.discovery import build
    except ImportError as ex:
        raise GoogleIntegrationError(
            "구글 연동 라이브러리가 설치되어 있지 않습니다. "
            "`pip install google-api-python-client google-auth` 를 실행해 주세요."
        ) from ex

    import os
    if not os.path.exists(service_account_path):
        raise GoogleIntegrationError("구글 서비스 계정 키 파일이 설정되어 있지 않습니다. [설정] 탭에서 등록해 주세요.")

    try:
        creds = Credentials.from_service_account_file(
            service_account_path, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        service = build("sheets", "v4", credentials=creds)
        sheet_id = _extract_sheet_id(spreadsheet_url_or_id)
        result = service.spreadsheets().values().get(spreadsheetId=sheet_id, range=sheet_range).execute()
        return result.get("values", [])
    except GoogleIntegrationError:
        raise
    except Exception as ex:
        raise GoogleIntegrationError(f"구글 시트를 읽는 중 오류가 발생했습니다: {ex}") from ex


def parse_rows_to_approvals(rows: list[list[str]], tab_type: str, imported_source_keys: set[str]) -> list[ApprovalRequest]:
    """
    응답 시트 행을 ApprovalRequest 목록으로 만든다. 헤더 문구(학번/이름 또는 성명)로 열을 찾고,
    타임스탬프+학번+구분으로 SourceKey를 만들어 이미 가져온 응답은 건너뛴다.
    """
    if not rows:
        return []

    header_row = ioimp.find_header_row(rows, ["학번"], max_rows=5)
    if header_row < 0:
        raise GoogleIntegrationError("응답 시트에서 '학번' 열을 찾지 못했습니다. 시트 형식을 확인해 주세요.")

    header = [ioimp.cell_str(c) for c in rows[header_row]]
    col_timestamp = ioimp.find_col(header, "타임스탬프", "Timestamp")
    col_space = ioimp.find_col(header, "신청") if tab_type == "상상Lab" else -1
    col_dept = ioimp.find_col(header, "소속", "학과", "전공")
    col_name = ioimp.find_col(header, "이름", "성명")
    col_id = ioimp.find_col(header, "학번")
    col_contact = ioimp.find_col(header, "연락처", "전화")
    col_email = ioimp.find_col(header, "이메일", "메일")
    col_advisor = ioimp.find_col(header, "지도교수")
    col_note = ioimp.find_col(header, "기타", "의견")
    # 캐비닛/기자재 신청 폼에만 있는 열 (없으면 -1 → 그냥 빈 값으로 처리된다)
    col_period = ioimp.find_col(header, "대여기간", "대여 기간")
    col_equip = ioimp.find_col(header, "대여품목", "대여 가능 품목", "기자재")
    col_location = ioimp.find_col(header, "사용장소", "사용 장소")
    col_purpose = ioimp.find_col(header, "사용목적", "사용 목적")
    col_year = ioimp.find_col(header, "학년")
    col_due = ioimp.find_col(header, "반납예정", "반납 예정")

    results = []
    for r in range(header_row + 1, len(rows)):
        row = rows[r]

        def cell(i):
            return ioimp.cell_str(ioimp.cell_at(row, i))

        sid = ioimp.normalize_student_id(ioimp.cell_at(row, col_id))
        name = cell(col_name)
        if not sid or not any(ch.isdigit() for ch in sid) or not name:
            continue

        timestamp = cell(col_timestamp)
        source_key = f"{timestamp}|{sid}|{tab_type}"
        if source_key in imported_source_keys:
            continue

        advisor = cell(col_advisor).replace("교수님", "").replace("교수", "").strip()
        req = ApprovalRequest(
            student_name=name,
            department=cell(col_dept) or "소프트웨어전공",
            student_id=sid,
            advisor=advisor,
            email=cell(col_email),
            phone=ioimp.normalize_phone(ioimp.cell_at(row, col_contact)),
            note=cell(col_note),
            tab_type=tab_type,
            source_key=source_key,
            rental_period=cell(col_period),
            equipment_type=cell(col_equip),
            location=cell(col_location),
            purpose=cell(col_purpose),
            year_level=cell(col_year),
            due_date=_parse_loose_date(cell(col_due)),
        )
        results.append(req)

    return results


def _parse_loose_date(text: str):
    """"2026/08/25", "2026-08-25", "2026. 8. 25" 등 구글폼이 흔히 쓰는 날짜 표기를 읽는다."""
    if not text:
        return None
    m = re.search(r"(\d{4})[.\-/]\s*(\d{1,2})[.\-/]\s*(\d{1,2})", text)
    if not m:
        return None
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def sync_all(settings: dict, service_account_path: str, imported_source_keys: set[str]) -> tuple[list[ApprovalRequest], list[str]]:
    """
    settings.json에 등록된 3개 시트 URL을 모두 동기화한다.
    돌려주는 값: (새로 추가된 ApprovalRequest 목록, 각 시트별 오류 메시지 목록).
    URL이 비어 있는 시트는 조용히 건너뛴다.
    """
    sheets = [
        ("상상Lab", settings.get("SangsangLabFormUrl", "")),
        ("캐비닛", settings.get("CabinetFormUrl", "")),
        ("기자재", settings.get("EquipmentFormUrl", "")),
    ]
    added: list[ApprovalRequest] = []
    errors: list[str] = []
    for tab_type, url in sheets:
        if not url.strip():
            continue
        try:
            rows = fetch_sheet_rows(url, service_account_path)
            added.extend(parse_rows_to_approvals(rows, tab_type, imported_source_keys))
        except GoogleIntegrationError as ex:
            errors.append(f"[{tab_type}] {ex}")
    return added, errors
