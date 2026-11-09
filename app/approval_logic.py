"""
승인/반려/복구, 구글 폼 동기화, 기간 만료 정리 — C# MainWindow의
BtnApproveRequest_Click / BtnRejectRequest_Click / BtnRestoreFromHistory_Click /
SyncFromGoogleFormAsync / CheckExpiredItems / Show*ExpiryWarningDialog 를 그대로 옮겼다.
"""
from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

from . import widgets as w
from .constants import TOTAL_CABINETS
from . import sync_merge
from .context import prefer
from .dialogs import (
    EquipmentSelectionDialog, CabinetSelectionDialog, ExpiredCleanupDialog,
    cabinet_expiry_warning, equipment_expiry_warning,
)
from .models import ApprovalRequest, CabinetAllocation, RentalItem

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext

TAB_FOR = {"상상Lab": "sangsanglab", "기자재": "equipment"}


def _tab_of(req: ApprovalRequest) -> str:
    return TAB_FOR.get(req.tab_type, "cabinet")


# ====================================================================== 승인
def approve(ctx: "AppContext", req: ApprovalRequest) -> None:
    st = ctx.state
    parent = ctx.win

    if req.tab_type == "기자재":
        # 기자재 대여는 일회성이라 학생 마스터에 등록/수정하지 않는다 (있으면 이름만 읽어 온다)
        master = next((m for m in st.master_students if m.student_id == req.student_id), None)
    else:
        master = ctx.register_or_update_master(req)
        if master is None:
            return

    chosen_cabinet = -1
    equip_dialog = None
    chosen_equip_type = ""
    chosen_phone = req.phone

    if req.tab_type == "기자재":
        active = [r for r in st.rentals if not r.is_returned]
        dlg = EquipmentSelectionDialog(parent, active, req.phone, req.equipment_type,
                                       list(st.equipment_issues), req.due_date, ctx.today)
        if dlg.exec() != EquipmentSelectionDialog.Accepted:
            return
        equip_dialog = dlg
        chosen_equip_type = f"{dlg.selected_equipment_type} ({dlg.selected_unit_number})"
        chosen_phone = dlg.selected_phone

    elif req.tab_type == "캐비닛":
        m = master
        dup = next((n for n, a in st.cabinet_allocations.items() if a.student and a.student.student_id == m.student_id), 0)
        if dup > 0:
            existing_period = st.cabinet_allocations[dup].period
            new_period = ctx.season_cabinet_period()
            if ctx.are_periods_overlapping(existing_period, new_period):
                w.warn(parent,
                       f"해당 학생({m.name} / {m.student_id})은 이미 {dup}번 캐비닛에 배정되어 있으며, "
                       f"대여 기간({existing_period})이 신청 기간({new_period})과 중복됩니다.\n먼저 기존 배정을 해제한 후 승인해 주세요.",
                       "배정 중복 오류")
                return
            merged = ctx.merge_periods(existing_period, new_period)
            if not w.ask(parent,
                         f"{m.name} ({m.student_id}) 학생은 {dup}번 캐비닛을 {existing_period} 기간으로 쓰고 있습니다.\n"
                         f"신청 기간({new_period})이 겹치지 않으므로 {dup}번 캐비닛을 {merged} 로 연장합니다.\n\n계속할까요?",
                         "대여 기간 연장"):
                return
            st.cabinet_allocations[dup] = CabinetAllocation(dup, m.clone(), merged)
            req.rental_period = merged
            chosen_cabinet = dup
        else:
            dlg = CabinetSelectionDialog(parent, st.cabinet_allocations, TOTAL_CABINETS)
            if dlg.exec() != CabinetSelectionDialog.Accepted:
                return
            chosen_cabinet = dlg.selected_cabinet_number

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

    if req.tab_type == "기자재" and equip_dialog is not None:
        days = (equip_dialog.selected_due_date - equip_dialog.selected_rental_date).days
        if days <= 0:
            days = 7
        rental = RentalItem(
            student_name=prefer(master.name if master else "", req.student_name),
            equipment_type=chosen_equip_type,
            rental_date=equip_dialog.selected_rental_date,
            rental_period_days=days,
            is_returned=False,
            student_id=prefer(req.student_id, "20261234"),
            department=prefer(req.department, "소프트웨어융합학과"),
            year_level=prefer(req.year_level, "3학년"),
            phone=prefer(chosen_phone, "010-0000-0000"),
            advisor=prefer(req.advisor, "김동욱 교수"),
            location=prefer(req.location, "DSU 창의공간"),
            purpose=prefer(req.purpose, "개인 실습"),
            remarks=req.note,
        )
        st.rentals.append(rental)
        st.rental_history.append(rental)

    ctx.win.switch_tab(_tab_of(req))
    ctx.win.dashboard.render_seat_grid()
    ctx.save_app_state()


def reject(ctx: "AppContext", req: ApprovalRequest) -> None:
    req.status = "반려"
    ctx.state.approvals.remove(req)
    ctx.state.approval_history.append(req)
    ctx.win.switch_tab(_tab_of(req))
    ctx.save_app_state()


def restore_from_history(ctx: "AppContext", req: ApprovalRequest) -> bool:
    st = ctx.state
    if not w.ask(ctx.win, f"'{req.student_name}' 학생의 내역을 대기 목록으로 되돌리시겠습니까?", "복구 확인"):
        return False
    if req.status == "승인 완료":
        if req.tab_type == "상상Lab":
            seat = next((s for s in ctx.win.dashboard.active_seats if s.student and s.student.student_id == req.student_id), None)
            if seat:
                seat.student = None
                seat.is_fixed = False
        elif req.tab_type == "캐비닛":
            key = next((n for n, a in st.cabinet_allocations.items() if a.student and a.student.student_id == req.student_id), 0)
            if key > 0:
                del st.cabinet_allocations[key]
        elif req.tab_type == "기자재":
            rental = next((r for r in st.rentals if r.student_name == req.student_name), None)
            if rental:
                st.rentals.remove(rental)
    req.status = "승인 대기"
    if req in st.approval_history:
        st.approval_history.remove(req)
    st.approvals.append(req)
    ctx.win.switch_tab(_tab_of(req))
    ctx.win.dashboard.render_seat_grid()
    ctx.win.update_alert_badges()
    w.info(ctx.win, "신청 내역이 대기 목록으로 성공적으로 복구되었습니다.", "복구 완료")
    return True


def show_history(ctx: "AppContext", scope: str) -> None:
    from .dialogs import ApprovalHistoryModal
    ApprovalHistoryModal(ctx.win, ctx.state.approval_history, scope,
                         lambda req: restore_from_history(ctx, req)).exec()


# ====================================================================== 구글 폼 동기화
def sync_from_google_form(ctx: "AppContext", silent: bool) -> None:
    win = ctx.win
    svc = win.forms_service
    if svc is None or win.is_syncing:
        return
    win.is_syncing = True
    win.settings_tab.set_sync_enabled(False)
    win.settings_tab.set_sync_status("동기화 중...", False)
    try:
        st = ctx.state
        result = svc.fetch(lambda key: key in st.imported_source_keys)
        now = datetime.datetime.now().strftime("%H:%M:%S")
        if not result.is_success:
            win.settings_tab.set_sync_status(f"[{now}] {result.error}", True)
            if not silent:
                w.error(win, result.error, "동기화 실패")
            return

        merged = sync_merge.merge_new_requests(ctx, result.new_requests)
        win.refresh_approval_views()
        if result.new_requests:
            ctx.save_app_state()

        if merged.auto_rejected:
            w.warn(win, sync_merge.auto_rejected_message(merged.auto_rejected), "배정 중복 오류")

        summary, warning = sync_merge.sync_summary(now, result, merged, st.approvals)
        win.settings_tab.set_sync_status(summary, warning)
        if not silent:
            w.info(win, summary, "동기화 완료")
    finally:
        win.is_syncing = False
        win.settings_tab.set_sync_enabled(True)


# ====================================================================== 기간 만료
def show_cabinet_expiry_warning(ctx: "AppContext") -> None:
    today = ctx.today
    items = []
    for n, a in ctx.state.cabinet_allocations.items():
        r = ctx.parse_period_dates(a.period)
        if r is None:
            continue
        days = (r[1] - today).days
        if days <= 7:
            items.append((n, a.student, a.period, days))
    if items:
        items.sort(key=lambda x: x[3])
        cabinet_expiry_warning(ctx.win, today, items)


def show_equipment_expiry_warning(ctx: "AppContext") -> None:
    today = ctx.today
    items = [(r, (r.due_date - today).days) for r in ctx.state.rentals
             if not r.is_returned and (r.due_date - today).days <= 7]
    if items:
        items.sort(key=lambda x: x[1])
        equipment_expiry_warning(ctx.win, today, items)


def check_expired_items(ctx: "AppContext", scope: str) -> None:
    today = ctx.today
    st = ctx.state
    entries: list[tuple[str, str, callable]] = []
    if scope == "대시보드":
        for seat in ctx.win.dashboard.active_seats:
            if seat.is_pillar or seat.student is None:
                continue
            period = ctx.find_student_period(seat.student)
            r = ctx.parse_period_dates(period)
            if r is None or r[1] >= today:
                continue

            def _del(s=seat):
                s.student = None
                s.is_fixed = False
            entries.append((f"좌석|{seat.seat_number}|{seat.student.student_id}|{period}",
                            f"{seat.seat_number}번 좌석 · {seat.student.name}({seat.student.student_id}) · {period}", _del))
    elif scope == "기자재":
        for rental in [r for r in st.rentals if not r.is_returned and r.due_date < today]:
            def _del(r=rental):
                r.is_returned = True
                st.rentals.remove(r)
            entries.append((f"대여|{rental.id}",
                            f"{rental.display_equipment} · {rental.student_name}({rental.student_id}) · 반납예정 {rental.due_date:%Y-%m-%d}", _del))
    elif scope == "캐비닛":
        for n, a in list(st.cabinet_allocations.items()):
            r = ctx.parse_period_dates(a.period)
            if r is None or r[1] >= today:
                continue

            def _del(num=n):
                st.cabinet_allocations.pop(num, None)
                ctx.update_master_cabinet_periods()
            name = a.student.name if a.student else ""
            sid = a.student.student_id if a.student else ""
            entries.append((f"캐비닛|{n}|{sid}|{a.period}", f"{n}번 캐비닛 · {name}({sid}) · {a.period}", _del))

    fresh = [e for e in entries if e[0] not in ctx.kept_expired_keys]
    if not fresh:
        return
    dlg = ExpiredCleanupDialog(ctx.win, scope, today, [(k, lbl) for k, lbl, _ in fresh])
    dlg.exec()
    if not dlg.delete_confirmed:
        for k, _, _ in fresh:
            ctx.kept_expired_keys.add(k)
        return
    deleted = 0
    for k, _, fn in fresh:
        if k in dlg.selected_keys:
            fn()
            deleted += 1
        else:
            ctx.kept_expired_keys.add(k)
    if scope == "대시보드":
        ctx.win.dashboard.render_seat_grid()
    elif scope == "기자재":
        ctx.win.equipment.bind_rentals()
    elif scope == "캐비닛":
        ctx.win.cabinet.render_grid()
    ctx.win.update_alert_badges()
    if deleted:
        w.info(ctx.win, f"선택한 {deleted}건을 삭제했습니다.", "정리 완료")
