"""
[상상Lab 승인] 화면 — C# 버전 TabSangsangLab 그대로.
주황 알림 카드 + [📋 승인/반려 내역], "상상Lab 신청 및 승인 대기 (구글폼)",
신청서 카드(300x190, 둥근 모서리 12, 그림자)가 가로로 흘러가며 줄바꿈된다(WrapPanel).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea, QFrame, QGraphicsDropShadowEffect, QPushButton,
)

from . import widgets as w
from . import approval_logic as al
from .models import ApprovalRequest, Seat, StudentInfo

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext


class ApprovalCard(QFrame):
    def __init__(self, tab: "SangsangLabTab", req: ApprovalRequest):
        super().__init__()
        self.setObjectName("apcard")
        self.setStyleSheet("QFrame#apcard { background:#FFFFFF; border:1px solid #E5E7EB; border-radius:12px; }")
        self.setFixedSize(300, 190)
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(10)
        sh.setOffset(0, 2)
        sh.setColor(QColor(156, 163, 175, 38))
        self.setGraphicsEffect(sh)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.addWidget(w.label("상상Lab 신청", 14, bold=True, color="#1F2937"))
        head.addStretch()
        badge = QLabel("신규 요청")
        badge.setStyleSheet("QLabel { background:#EFF6FF; border:1px solid #BFDBFE; border-radius:4px; padding:2px 6px; "
                            "font-size:9px; font-weight:700; color:#2563EB; }")
        head.addWidget(badge)
        lay.addLayout(head)
        lay.addSpacing(10)

        def row(caption: str, value_widget: QWidget, extra: QWidget = None):
            r = QHBoxLayout()
            r.setSpacing(0)
            cap = w.label(caption, 11, color="#4B5563", icon=True)
            cap.setFixedWidth(70)
            r.addWidget(cap)
            r.addWidget(value_widget, 1)
            if extra is not None:
                r.addWidget(extra)
            lay.addLayout(r)
            lay.addSpacing(4)

        more = QPushButton("더보기")
        more.setCursor(Qt.PointingHandCursor)
        more.setStyleSheet("QPushButton { background:transparent; border:none; color:#4B5563; font-size:10px; padding:0 2px; }"
                           "QPushButton:hover { background:#BEE6FD; }")
        more.clicked.connect(lambda: tab.view_details(req))
        row("👤 신청자", w.label(req.student_name, 11, bold=True, color="#1F2937"), more)
        row("🕒 요청 시간", w.label(req.request_date.strftime("%Y-%m-%d") + " 14:00 ~ 16:00", 11, color="#1F2937"))
        row("🏢 희망 공간", w.label("u301", 11, bold=True, color="#1F2937"))
        lay.addStretch()

        act = QHBoxLayout()
        act.setSpacing(10)
        act.addWidget(w.flat_btn("✓ 승인", "#2563EB", padding=(8, 0), radius=6, on_click=lambda: al.approve(tab.ctx, req)))
        act.addWidget(w.flat_btn("✕ 반려", "#FFFFFF", fg="#EF4444", padding=(7, 0), radius=6, border="#EF4444",
                                 on_click=lambda: al.reject(tab.ctx, req)))
        lay.addLayout(act)


class SangsangLabTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        w.inset_background(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        top = QHBoxLayout()
        self.alert = w.orange_alert("상상Lab 승인 대기", on_click=lambda: self.ctx.win.switch_tab("equipment"))
        top.addWidget(self.alert, 0, Qt.AlignVCenter)
        top.addStretch()
        top.addWidget(w.action_btn("📋 승인/반려 내역", padding=(8, 15),
                                   on_click=lambda: al.show_history(self.ctx, "상상Lab")), 0, Qt.AlignVCenter)
        root.addLayout(top)
        root.addSpacing(15)
        root.addWidget(w.label("상상Lab 신청 및 승인 대기 (구글폼)", 16, bold=True, color="#111827"))
        root.addSpacing(15)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; } QScrollArea > QWidget > QWidget { background:transparent; }")
        host = QWidget()
        self.flow = w.FlowLayout(host, h_spacing=20, v_spacing=20)
        self.flow.setContentsMargins(0, 0, 0, 0)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

    def refresh(self):
        while self.flow.count():
            it = self.flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        rows = [a for a in self.ctx.state.approvals if a.tab_type == "상상Lab"]
        self.alert.set_count(len(rows))
        for req in rows:
            self.flow.addWidget(ApprovalCard(self, req))

    def view_details(self, req: ApprovalRequest):
        from .seat_tab import SeatDetailModal
        dummy = Seat(seat_number=0, student=StudentInfo(student_id=req.student_id, name=req.student_name,
                                                         department=req.department, advisor=req.advisor, email=req.email))
        SeatDetailModal(self.ctx.win.dashboard, dummy).exec()
