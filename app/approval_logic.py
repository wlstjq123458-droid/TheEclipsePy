"""
승인 처리 공용 로직. 캐비닛/기자재/상상Lab 세 탭이 각자 자기 종류(tab_type)의 신청만
보여주면서 똑같은 승인 로직을 쓴다 — C# 버전이 _approvals 하나를 탭별로 필터링해서 보여주는
것과 같은 구조다(별도의 "승인 대기" 탭은 없다).
"""
from __future__ import annotations

import datetime

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView,
    QDialogButtonBox, QAbstractItemView,
)

from .models import ApprovalRequest, StudentInfo, CabinetAllocation, RentalItem, SeasonConfig
from .cabinet_tab import format_period, TOTAL_CABINETS
from .equipment_tab import LAPTOP_LABEL


def register_or_update_master(master_students: list[StudentInfo], req: ApprovalRequest) -> StudentInfo:
    existing = next((m for m in master_students if m.student_id == req.student_id), None)
    if existing is None:
        created = StudentInfo(
            student_id=req.student_id, name=req.student_name, department=req.department,
            advisor=req.advisor, email=req.email, contact=req.phone,
        )
        master_students.append(created)
        return created
    if not existing.name and req.student_name: existing.name = req.student_name
    if not existing.department and req.department: existing.department = req.department
    if not existing.advisor and req.advisor: existing.advisor = req.advisor
    if not existing.email and req.email: existing.email = req.email
    if not existing.contact and req.phone: existing.contact = req.phone
    return existing


def default_cabinet_period(season_config: SeasonConfig) -> str:
    today = datetime.date.today()
    season = season_config.resolve_season(today)
    if season:
        sched = season_config.get_year(season[0])
        period = next((p for p in sched.seasons if p.name == season[1]), None) if sched else None
        if period and period.end_date >= today:
            return format_period(today, period.end_date)
    try:
        nxt = today.replace(month=today.month + 1)
    except ValueError:
        nxt = today.replace(year=today.year + 1, month=1)
    return format_period(today, nxt)


class ApprovalContext:
    """탭마다 approve()에 필요한 참조를 한데 묶는다."""

    def __init__(self, master_students, cabinet_allocations, rentals, rental_history,
                 approvals, approval_history, season_config, on_save, warn):
        self.master_students = master_students
        self.cabinet_allocations = cabinet_allocations
        self.rentals = rentals
        self.rental_history = rental_history
        self.approvals = approvals
        self.approval_history = approval_history
        self.season_config = season_config
        self.on_save = on_save
        self.warn = warn  # (title, message) -> None, 보통 QMessageBox.warning 래핑


def approve(req: ApprovalRequest, ctx: ApprovalContext) -> None:
    student = register_or_update_master(ctx.master_students, req)

    if req.tab_type == "상상Lab":
        season = ctx.season_config.resolve_season(datetime.date.today())
        if season:
            student.last_active_season = f"{season[0]}_{season[1]}"

    elif req.tab_type == "캐비닛":
        dup = next((n for n, a in ctx.cabinet_allocations.items() if a.student and a.student.student_id == student.student_id), None)
        if dup is not None:
            ctx.warn("알림", f"이미 {dup}번 캐비닛을 쓰고 있어 중복 배정하지 않았습니다.")
        else:
            empty = next((n for n in range(1, TOTAL_CABINETS + 1) if n not in ctx.cabinet_allocations), None)
            if empty is None:
                ctx.warn("알림", "빈 캐비닛이 없어 배정하지 못했습니다. 승인은 완료 처리합니다.")
            else:
                period = req.rental_period or default_cabinet_period(ctx.season_config)
                ctx.cabinet_allocations[empty] = CabinetAllocation(cabinet_num=empty, student=student.clone(), period=period)

    elif req.tab_type == "기자재":
        equip_type = req.equipment_type or LAPTOP_LABEL
        rental = RentalItem(
            student_id=student.student_id, student_name=student.name,
            department=student.department, advisor=student.advisor, phone=student.contact,
            equipment_type=equip_type, year_level=req.year_level or "",
            location=req.location or "DSU 창의공간", purpose=req.purpose or "개인 실습",
            rental_date=datetime.date.today(),
            rental_period_days=(req.due_date - datetime.date.today()).days if req.due_date else 7,
        )
        ctx.rentals.append(rental)
        ctx.rental_history.append(rental)

    req.status = "승인 완료"
    _finish(req, ctx)


def reject(req: ApprovalRequest, ctx: ApprovalContext) -> None:
    req.status = "반려"
    _finish(req, ctx)


def _finish(req: ApprovalRequest, ctx: ApprovalContext) -> None:
    ctx.approvals.remove(req)
    ctx.approval_history.append(req)
    ctx.on_save()


class ApprovalHistoryDialog(QDialog):
    """[승인/반려 내역] 버튼 — C#의 ModalApprovalHistory에 대응한다."""

    def __init__(self, parent, approval_history: list[ApprovalRequest], tab_type: str):
        super().__init__(parent)
        self.setWindowTitle(f"{tab_type} 승인/반려 내역")
        self.resize(650, 400)
        lay = QVBoxLayout(self)
        rows = sorted(
            [a for a in approval_history if a.tab_type == tab_type],
            key=lambda a: a.request_date, reverse=True,
        )
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["학번", "이름", "상태", "신청일"])
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, a in enumerate(rows):
            for c, v in enumerate([a.student_id, a.student_name, a.status, a.request_date.strftime("%Y-%m-%d %H:%M")]):
                table.setItem(r, c, QTableWidgetItem(v))
        lay.addWidget(table)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)
