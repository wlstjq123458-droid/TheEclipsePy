"""
구글 시트에서 읽어 온 새 신청을 창공시스템 목록에 넣는 규칙 — 데스크톱과 웹이 같이 쓴다.

지도교수 승인을 거쳐야 하는 구분(설정의 ProfessorApprovalTypes)은 시트의 '승인상태' 칸을 본다.
  - "승인"   → 승인 대기 목록에 넣는다
  - "반려"   → 승인/반려 내역에 '반려'로 남긴다 (반려 사유 칸이 있으면 함께 적는다)
  - 그 밖    → 아직 결정 전이므로 건너뛰고, 다음 동기화 때 다시 확인한다
승인상태 칸은 교수님 메일 승인 스크립트(google_apps_script/professor_approval.gs)가 채운다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .models import ApprovalRequest

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext
    from .google_integration import FormSyncResult

APPROVAL_TYPES = ("기자재", "캐비닛", "상상Lab")
DEFAULT_APPROVAL_TYPES = ["기자재"]          # 예전부터 기자재 시트만 승인상태를 확인해 왔다

_APPROVED = {"승인", "승인완료", "승인함", "o", "y", "yes"}
_REJECTED = {"반려", "반려됨", "거절", "미승인", "불허", "x", "n", "no"}


def sheet_decision(status: str) -> str:
    """시트의 승인상태 값 → 'approved' / 'rejected' / 'pending'."""
    s = "".join((status or "").split()).lower()
    if s in _APPROVED:
        return "approved"
    if s in _REJECTED:
        return "rejected"
    return "pending"


def approval_types(settings: dict) -> list[str]:
    raw = settings.get("ProfessorApprovalTypes")
    if not isinstance(raw, list):
        return list(DEFAULT_APPROVAL_TYPES)
    return [t for t in raw if t in APPROVAL_TYPES]


@dataclass
class MergeResult:
    added: int = 0
    pending: int = 0                 # 지도교수 결정 전이라 이번에는 건너뛴 건수
    professor_rejected: list[ApprovalRequest] = field(default_factory=list)
    auto_rejected: list[ApprovalRequest] = field(default_factory=list)   # 캐비닛 기간 중복


def merge_new_requests(ctx: "AppContext", requests: list[ApprovalRequest]) -> MergeResult:
    st = ctx.state
    gated = set(approval_types(ctx.settings))
    out = MergeResult()
    for req in requests:
        if req.source_key in st.imported_source_keys:
            continue   # 시트를 읽는 사이 다른 동기화가 이미 받아 왔다
        if not req.student_name.strip():
            # 기자재 폼에는 이름 질문이 없다 — 같은 학번을 아는 곳에서 이름을 채워 넣는다
            req.student_name = (
                next((m.name for m in st.master_students if m.student_id == req.student_id), None)
                or next((a.student_name for a in st.approvals if a.student_id == req.student_id and a.student_name.strip()), None)
                or ""
            )

        if req.tab_type in gated:
            decision = sheet_decision(req.sheet_approval_status)
            if decision == "pending":
                # SourceKey를 기록하지 않는다 — 다음 동기화 때 이 행을 다시 읽어 결정이 났는지 확인한다
                out.pending += 1
                continue
            if decision == "rejected":
                st.imported_source_keys.add(req.source_key)
                req.status = "반려"
                reason = "지도교수 반려" + (f": {req.sheet_reject_reason}" if req.sheet_reject_reason.strip() else "")
                req.note = reason if not req.note.strip() else f"{req.note} / {reason}"
                st.approval_history.append(req)
                out.professor_rejected.append(req)
                continue

        st.imported_source_keys.add(req.source_key)
        if req.tab_type == "캐비닛":
            if not req.rental_period.strip():
                req.rental_period = ctx.default_cabinet_period
            # 기간이 겹치면 같은 학생이 같은 기간에 두 칸을 쓰게 되므로 자동 반려한다
            reason = ctx.find_cabinet_conflict(req)
            if reason:
                req.status = "반려"
                req.note = reason if not req.note.strip() else f"{req.note} / {reason}"
                st.approval_history.append(req)
                out.auto_rejected.append(req)
                continue
        st.approvals.append(req)
        out.added += 1
    return out


def sync_summary(now: str, result: "FormSyncResult", merged: MergeResult, approvals: list[ApprovalRequest]) -> tuple[str, bool]:
    """설정 화면의 동기화 상태 문구와 경고 여부."""
    added = len(result.new_requests) - merged.pending
    summary = f"[{now}] 응답 {result.total_rows}건 중 신규 {added}건 반영"
    if result.duplicate_count:
        summary += f" (기존 {result.duplicate_count}건 건너뜀)"
    if merged.pending:
        summary += f" (지도교수 승인 대기 {merged.pending}건 — 다음 동기화 때 재확인)"
    if merged.professor_rejected:
        summary += f" (지도교수 반려 {len(merged.professor_rejected)}건 — 승인/반려 내역에 기록)"
    by_type: dict[str, int] = {}
    for a in approvals:
        by_type[a.tab_type] = by_type.get(a.tab_type, 0) + 1
    summary += "\n승인 대기: " + (" / ".join(f"{k} {v}건" for k, v in by_type.items()) if by_type else "없음")
    if result.missing_columns:
        summary += f"\n⚠ 헤더에서 찾지 못한 항목: {', '.join(result.missing_columns)}"
    if result.unmapped_spaces:
        summary += f"\n⚠ 신청 공간을 판별하지 못한 값: {' / '.join(result.unmapped_spaces)} → '미분류'로 등록됨"
    for warning in result.warnings:
        summary += f"\n⚠ {warning}"
    return summary, bool(result.missing_columns or result.unmapped_spaces or result.warnings)


def auto_rejected_message(auto_rejected: list[ApprovalRequest]) -> str:
    lines = "\n".join(f"• {r.student_name} ({r.student_id}) — {r.rental_period}" for r in auto_rejected)
    return (f"아래 {len(auto_rejected)}건은 캐비닛 배정 기간이 중복되어 자동으로 반려 처리되었습니다.\n\n{lines}\n\n"
            "[📋 승인/반려 내역]에서 확인하거나 복구할 수 있습니다.")
