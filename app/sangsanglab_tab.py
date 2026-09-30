"""
[상상Lab 승인] 탭 — 상상Lab 신청(구글폼)을 카드 형태로 보여주고 승인/반려한다.
C# 버전의 TabSangsangLab(LstSangsangLabCards, 카드 300x190)에 대응한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox,
)

from .models import ApprovalRequest, StudentInfo, SeasonConfig
from .widgets import AlertChip

CARD_COLUMNS = 3


class ApprovalCard(QFrame):
    def __init__(self, req: ApprovalRequest, on_approve, on_reject):
        super().__init__()
        self.setFixedSize(300, 190)
        self.setStyleSheet(
            "ApprovalCard { background:white; border:1px solid #E5E7EB; border-radius:12px; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)

        head = QHBoxLayout()
        title = QLabel("상상Lab 신청")
        title.setStyleSheet("border:none; font-size:14px; font-weight:bold; color:#1F2937;")
        head.addWidget(title)
        head.addStretch()
        badge = QLabel("신규 요청")
        badge.setStyleSheet(
            "border:1px solid #BFDBFE; background:#EFF6FF; color:#2563EB; "
            "font-size:9px; font-weight:bold; border-radius:4px; padding:3px 6px;"
        )
        head.addWidget(badge)
        lay.addLayout(head)

        def info_row(icon_label: str, value: str):
            row = QHBoxLayout()
            lbl = QLabel(icon_label)
            lbl.setStyleSheet("border:none; font-size:11px; color:#4B5563;")
            lbl.setFixedWidth(75)
            val = QLabel(value)
            val.setStyleSheet("border:none; font-size:11px; font-weight:bold; color:#1F2937;")
            row.addWidget(lbl)
            row.addWidget(val, 1)
            lay.addLayout(row)

        info_row("👤 신청자", req.student_name or req.student_id)
        info_row("🎓 학번", req.student_id)
        info_row("🕒 신청일", req.request_date.strftime("%Y-%m-%d %H:%M"))
        info_row("🏢 희망 공간", "U301")
        lay.addStretch()

        actions = QHBoxLayout()
        btn_ok = QPushButton("✓ 승인")
        btn_ok.setStyleSheet("background:#2563EB; color:white; font-weight:bold; border:none; border-radius:6px; padding:8px 0;")
        btn_ok.clicked.connect(lambda: on_approve(req))
        btn_no = QPushButton("✕ 반려")
        btn_no.setStyleSheet("background:white; color:#EF4444; border:1px solid #EF4444; font-weight:bold; border-radius:6px; padding:8px 0;")
        btn_no.clicked.connect(lambda: on_reject(req))
        actions.addWidget(btn_ok)
        actions.addWidget(btn_no)
        lay.addLayout(actions)


class SangsangLabTab(QWidget):
    def __init__(
        self,
        approvals: list[ApprovalRequest],
        approval_history: list[ApprovalRequest],
        master_students: list[StudentInfo],
        season_config: SeasonConfig,
        on_save,
    ):
        super().__init__()
        self.approvals = approvals
        self.approval_history = approval_history
        self.master_students = master_students
        self.season_config = season_config
        self.on_save = on_save

        self._build_ui()
        self.refresh()

    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        self.chip = AlertChip("🕒", "상상Lab 승인 대기", "#FFEDD5", "#FED7AA", "#EA580C")
        top.addWidget(self.chip)
        top.addStretch()
        btn_history = QPushButton("📋 승인/반려 내역")
        btn_history.clicked.connect(self.show_history)
        top.addWidget(btn_history)
        root.addLayout(top)

        title = QLabel("상상Lab 신청 및 승인 대기 (구글폼)")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#111827; margin:10px 0;")
        root.addWidget(title)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        host = QWidget()
        self.cards_grid = QGridLayout(host)
        self.cards_grid.setSpacing(10)
        self.cards_grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        scroll.setWidget(host)
        root.addWidget(scroll, 1)

        self.empty_label = QLabel("승인 대기 중인 상상Lab 신청이 없습니다.")
        self.empty_label.setStyleSheet("color:#9CA3AF; padding:20px;")
        root.addWidget(self.empty_label)

    def refresh(self):
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        rows = [a for a in self.approvals if a.tab_type == "상상Lab"]
        self.chip.set_count(len(rows))
        self.empty_label.setVisible(len(rows) == 0)

        for i, req in enumerate(rows):
            r, c = divmod(i, CARD_COLUMNS)
            self.cards_grid.addWidget(ApprovalCard(req, self.approve, self.reject), r, c)

    def _ctx(self):
        from .approval_logic import ApprovalContext
        return ApprovalContext(
            self.master_students, {}, [], [], self.approvals, self.approval_history,
            self.season_config, self.on_save, lambda title, msg: QMessageBox.warning(self, title, msg),
        )

    def approve(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.approve(req, self._ctx())
        self.refresh()

    def reject(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.reject(req, self._ctx())
        self.refresh()

    def show_history(self):
        from .approval_logic import ApprovalHistoryDialog
        ApprovalHistoryDialog(self, self.approval_history, "상상Lab").exec()
