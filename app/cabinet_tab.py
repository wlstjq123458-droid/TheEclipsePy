"""
[캐비닛 현황] 탭 — 48칸(1~24번 1페이지, 25~48번 2페이지) 배정.
C# 버전의 RenderCabinetGrid / CreateCabinetCell / CabinetCell_* / HandleCabinetCellClick 등에 대응한다.
"""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QPoint, QMimeData, QDate
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QMessageBox, QDialog, QFormLayout, QDateEdit,
    QDialogButtonBox, QComboBox, QGraphicsOpacityEffect, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView,
)

from .models import CabinetAllocation, StudentInfo, ApprovalRequest, SeasonConfig
from .constants import TOTAL_CABINETS, format_period, parse_period_dates, default_cabinet_period as default_period

MIME_CABINET = "application/x-seatmanager-cabinet"
DRAG_THRESHOLD = 8


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size:16px; font-weight:bold; color:#111827; margin-top:8px; margin-bottom:4px;")
    return lbl


class CabinetCell(QFrame):
    def __init__(self, tab: "CabinetTab", number: int):
        super().__init__()
        self.tab = tab
        self.number = number
        self.setFixedSize(96, 92)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self._press_pos: QPoint | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(1)
        self.lbl_num = QLabel(str(number))
        self.lbl_num.setAlignment(Qt.AlignCenter)
        outer.addWidget(self.lbl_num)
        self.lbl_id = QLabel("")
        self.lbl_id.setAlignment(Qt.AlignCenter)
        self.lbl_id.setStyleSheet("font-size:11px; color:#4B5563;")
        outer.addWidget(self.lbl_id)
        self.lbl_name = QLabel("")
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setStyleSheet("font-size:13px; font-weight:bold; color:#1F2937;")
        outer.addWidget(self.lbl_name)
        self.lbl_period = QLabel("")
        self.lbl_period.setAlignment(Qt.AlignCenter)
        self.lbl_period.setWordWrap(True)
        self.lbl_period.setStyleSheet("font-size:10px; color:#6B7280;")
        outer.addWidget(self.lbl_period)

        self.refresh()

    def alloc(self) -> CabinetAllocation | None:
        return self.tab.allocations.get(self.number)

    def refresh(self):
        a = self.alloc()
        query = self.tab.txt_search.text().strip().lower()
        is_match = False

        if a is not None:
            self.lbl_num.setStyleSheet("font-size:15px; font-weight:bold; color:#6B7280;")
            self.lbl_id.setText(a.student.student_id if a.student else "")
            self.lbl_name.setText(a.student.name if a.student else "")
            self.lbl_period.setText(a.period)
            bg = "#EFF6FF"
            rng = parse_period_dates(a.period)
            if rng and (rng[1] - datetime.date.today()).days <= 7:
                bg = "#FEE2E2"
            if query:
                is_match = (
                    query in (a.student.name or "").lower()
                    or query in (a.student.student_id or "").lower()
                    or query in (a.student.department or "").lower()
                )
        else:
            self.lbl_num.setStyleSheet("font-size:20px; font-weight:bold; color:#9CA3AF;")
            self.lbl_id.setText("")
            self.lbl_name.setText("")
            self.lbl_period.setText("")
            bg = "#FFFFFF"

        border, width, opacity = "#E5E7EB", "1px", 1.0
        if query:
            if is_match:
                border, width = "#2563EB", "2px"
            else:
                opacity = 0.25
        if self.number == self.tab.highlighted:
            border, width, opacity = "#EA580C", "3px", 1.0

        self.setStyleSheet(f"CabinetCell {{ background:{bg}; border:{width} solid {border}; border-radius:4px; }}")
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(opacity)
        self.setGraphicsEffect(effect if opacity < 1.0 else None)

    def _apply_drag_style(self, kind: str | None):
        if kind == "blue":
            self.setStyleSheet("CabinetCell { background:#DBEAFE; border:3px solid #2563EB; border-radius:4px; }")
        elif kind == "occupied":
            self.setStyleSheet("CabinetCell { background:#FEF3C7; border:3px solid #D97706; border-radius:4px; }")
        else:
            self.refresh()

    # ------------------------------------------------------------- mouse
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press_pos = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
            return
        self._press_pos = None
        if self.alloc() is None:
            return  # 빈 칸은 끌 게 없다

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_CABINET, str(self.number).encode("utf-8"))
        drag.setMimeData(mime)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.3)
        self.setGraphicsEffect(effect)
        drag.exec(Qt.MoveAction)
        self.setGraphicsEffect(None)
        self.refresh()

    def mouseReleaseEvent(self, e):
        if self._press_pos is not None:
            self._press_pos = None
            self.tab.handle_cell_click(self.number)

    # ---------------------------------------------------------- drag/drop
    def dragEnterEvent(self, e):
        if not e.mimeData().hasFormat(MIME_CABINET):
            e.ignore()
            return
        src = int(bytes(e.mimeData().data(MIME_CABINET)).decode("utf-8"))
        if src == self.number:
            e.ignore()
            return
        self._apply_drag_style("occupied" if self.alloc() is not None else "blue")
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.refresh()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_CABINET):
            return
        src = int(bytes(e.mimeData().data(MIME_CABINET)).decode("utf-8"))
        self.tab.handle_drop(src, self.number)
        e.acceptProposedAction()


class CabinetEditDialog(QDialog):
    """캐비닛 배정/정보 수정 모달. 학생을 마스터에서 고르거나 직접 입력할 수 있다."""

    def __init__(self, parent, number: int, alloc: CabinetAllocation | None, master_students: list[StudentInfo]):
        super().__init__(parent)
        self.number = number
        self.setWindowTitle(f"캐비닛 {number}번" + (" 상세 정보" if alloc else " 배정"))
        form = QFormLayout(self)

        self.combo_master = QComboBox()
        self.combo_master.addItem("(직접 입력)", None)
        for m in master_students:
            self.combo_master.addItem(f"{m.student_id} · {m.name}", m)
        self.combo_master.currentIndexChanged.connect(self._on_master_picked)
        form.addRow("마스터에서 선택", self.combo_master)

        self.ed_id = QLineEdit(alloc.student.student_id if alloc and alloc.student else "")
        self.ed_name = QLineEdit(alloc.student.name if alloc and alloc.student else "")
        form.addRow("학번", self.ed_id)
        form.addRow("이름", self.ed_name)

        rng = parse_period_dates(alloc.period) if alloc else None
        if rng is None:
            rng = parse_period_dates(default_period())
        self.dt_start = QDateEdit(QDate(rng[0].year, rng[0].month, rng[0].day))
        self.dt_end = QDateEdit(QDate(rng[1].year, rng[1].month, rng[1].day))
        for dt in (self.dt_start, self.dt_end):
            dt.setCalendarPopup(True)
            dt.setDisplayFormat("yyyy-MM-dd")
        form.addRow("대여 시작일", self.dt_start)
        form.addRow("대여 종료일", self.dt_end)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _on_master_picked(self, idx: int):
        stu: StudentInfo | None = self.combo_master.currentData()
        if stu is not None:
            self.ed_id.setText(stu.student_id)
            self.ed_name.setText(stu.name)

    def result_values(self):
        start = self.dt_start.date().toPython()
        end = self.dt_end.date().toPython()
        return self.ed_id.text().strip(), self.ed_name.text().strip(), start, end


class CabinetDetailDialog(QDialog):
    """이미 배정된 칸을 눌렀을 때 뜨는 요약 모달 — 수정/이동/반납 버튼을 고른다."""

    EDIT, MOVE, VACATE, CLOSE = "edit", "move", "vacate", "close"

    def __init__(self, parent, number: int, alloc: CabinetAllocation):
        super().__init__(parent)
        self.setWindowTitle(f"캐비닛 {number}번 상세 정보")
        self.action = self.CLOSE
        form = QFormLayout(self)
        form.addRow("학번", QLabel(alloc.student.student_id if alloc.student else ""))
        form.addRow("이름", QLabel(alloc.student.name if alloc.student else ""))
        form.addRow("대여 기간", QLabel(alloc.period))

        btns = QHBoxLayout()
        b_edit = QPushButton("정보 수정")
        b_edit.clicked.connect(lambda: self._choose(self.EDIT))
        b_move = QPushButton("다른 번호로 이동")
        b_move.clicked.connect(lambda: self._choose(self.MOVE))
        b_vacate = QPushButton("반납 처리 (비우기)")
        b_vacate.setStyleSheet("background:#EF4444; color:white;")
        b_vacate.clicked.connect(lambda: self._choose(self.VACATE))
        b_close = QPushButton("닫기")
        b_close.clicked.connect(self.reject)
        for b in (b_edit, b_move, b_vacate, b_close):
            btns.addWidget(b)
        form.addRow(btns)

    def _choose(self, action: str):
        self.action = action
        self.accept()


class CabinetTab(QWidget):
    """
    C# 버전의 [캐비닛 현황](TabCabinet) 화면.
    캐비닛 신청(구글폼) 승인 대기 목록을 이 화면 위쪽에 그대로 갖고 있다 — C# 버전도
    별도의 "승인 대기" 탭이 아니라 각 화면(캐비닛/기자재/상상Lab)이 자기 종류만 보여준다.
    """

    def __init__(
        self,
        allocations: dict[int, CabinetAllocation],
        master_students: list[StudentInfo],
        approvals: list[ApprovalRequest],
        approval_history: list[ApprovalRequest],
        season_config: SeasonConfig,
        on_save,
    ):
        super().__init__()
        self.allocations = allocations
        self.master_students = master_students
        self.approvals = approvals
        self.approval_history = approval_history
        self.season_config = season_config
        self.on_save = on_save
        self.page = 1
        self.highlighted = 0
        self._cells: dict[int, CabinetCell] = {}

        self._build_ui()
        self.render_grid()
        self.refresh_approvals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        top = QHBoxLayout()
        from .widgets import AlertChip
        self.chip = AlertChip("🕒", "캐비닛 승인 대기", "#FFEDD5", "#FED7AA", "#EA580C")
        top.addWidget(self.chip)
        top.addStretch()
        top.addWidget(QLabel("검색"))
        self.txt_search = QLineEdit()
        self.txt_search.setFixedWidth(180)
        self.txt_search.setPlaceholderText("학번/이름/소속")
        self.txt_search.textChanged.connect(self.render_grid)
        top.addWidget(self.txt_search)
        btn_history = QPushButton("📋 승인/반려 내역")
        btn_history.clicked.connect(self.show_history)
        top.addWidget(btn_history)
        root.addLayout(top)

        # ---- Section 1: 캐비닛 신청 현황 (구글폼) ----
        root.addWidget(_section_title("캐비닛 신청 현황 (구글폼)"))
        self.approval_table = QTableWidget(0, 5)
        self.approval_table.setHorizontalHeaderLabels(["신청 일자", "학번", "이름", "대여 기간", ""])
        self.approval_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.approval_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.approval_table.setFixedHeight(160)
        root.addWidget(self.approval_table)

        # ---- Section 2: 캐비닛 배치도 및 현황 ----
        root.addWidget(_section_title("캐비닛 배치도 및 현황"))

        page_bar = QHBoxLayout()
        page_bar.addStretch()
        self.btn_prev = QPushButton("◀ 이전 페이지 (1~24번)")
        self.btn_prev.clicked.connect(lambda: self.set_page(1))
        self.btn_next = QPushButton("다음 페이지 (25~48번) ▶")
        self.btn_next.clicked.connect(lambda: self.set_page(2))
        self.lbl_page = QLabel("1 / 2")
        self.lbl_page.setAlignment(Qt.AlignCenter)
        page_bar.addWidget(self.btn_prev)
        page_bar.addWidget(self.lbl_page)
        page_bar.addWidget(self.btn_next)
        page_bar.addStretch()
        root.addLayout(page_bar)

        self.grid = QGridLayout()
        self.grid.setSpacing(4)
        grid_row = QHBoxLayout()
        grid_row.addStretch()
        grid_row.addLayout(self.grid)
        grid_row.addStretch()
        root.addLayout(grid_row)

        # ---- 하단 상태 카운터 ----
        self.lbl_summary = QLabel("")
        self.lbl_summary.setAlignment(Qt.AlignCenter)
        self.lbl_summary.setStyleSheet("color:#374151; font-weight:600; padding-top:8px;")
        root.addWidget(self.lbl_summary)
        root.addStretch()

    # ------------------------------------------------------------ 승인 대기
    def refresh_approvals(self):
        rows = [a for a in self.approvals if a.tab_type == "캐비닛"]
        self.chip.set_count(len(rows))
        self.approval_table.setRowCount(len(rows))
        for r, req in enumerate(rows):
            for c, v in enumerate([req.request_date.strftime("%Y-%m-%d %H:%M"), req.student_id, req.student_name, req.rental_period]):
                self.approval_table.setItem(r, c, QTableWidgetItem(v))

            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(0, 0, 0, 0)
            btn_ok = QPushButton("승인")
            btn_ok.setStyleSheet("background:#10B981; color:white;")
            btn_ok.clicked.connect(lambda _, req=req: self._approve(req))
            btn_no = QPushButton("반려")
            btn_no.setStyleSheet("background:#EF4444; color:white;")
            btn_no.clicked.connect(lambda _, req=req: self._reject(req))
            h.addWidget(btn_ok)
            h.addWidget(btn_no)
            self.approval_table.setCellWidget(r, 4, cell)

    def _ctx(self) -> "ApprovalContext":
        from .approval_logic import ApprovalContext
        return ApprovalContext(
            self.master_students, self.allocations, [], [], self.approvals, self.approval_history,
            self.season_config, self.on_save, lambda title, msg: QMessageBox.warning(self, title, msg),
        )

    def _approve(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.approve(req, self._ctx())
        self.refresh_approvals()
        self.render_grid()

    def _reject(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.reject(req, self._ctx())
        self.refresh_approvals()

    def show_history(self):
        from .approval_logic import ApprovalHistoryDialog
        ApprovalHistoryDialog(self, self.approval_history, "캐비닛").exec()

    # ---------------------------------------------------------------- grid
    @staticmethod
    def _numbers_for_page(page: int) -> list[int]:
        base = 0 if page == 1 else 24
        # C# RenderCabinetGrid와 같은 순서: 열 우선, 한 열에 3칸 (1,2,3 / 4,5,6 / ...)
        return [base + (c * 3) + r + 1 for r in range(3) for c in range(8)]

    def set_page(self, page: int):
        self.page = page
        self.render_grid()

    def render_grid(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cells.clear()

        numbers = self._numbers_for_page(self.page)
        for i, num in enumerate(numbers):
            r, c = divmod(i, 8)
            cell = CabinetCell(self, num)
            self._cells[num] = cell
            self.grid.addWidget(cell, r, c)

        self.lbl_page.setText(f"{self.page} / 2")
        self.btn_prev.setEnabled(self.page != 1)
        self.btn_next.setEnabled(self.page != 2)
        rented = len(self.allocations)
        self.lbl_summary.setText(f"대여 중 {rented}개 / 사용가능 {max(0, TOTAL_CABINETS - rented)}개 (전체 {TOTAL_CABINETS}개)")

    # ------------------------------------------------------------- click
    def handle_cell_click(self, number: int):
        if self.highlighted:
            self.highlighted = 0

        alloc = self.allocations.get(number)
        if alloc is not None:
            dlg = CabinetDetailDialog(self, number, alloc)
            if dlg.exec() != QDialog.Accepted:
                self.render_grid()
                return
            if dlg.action == CabinetDetailDialog.EDIT:
                self._open_edit(number, alloc)
            elif dlg.action == CabinetDetailDialog.MOVE:
                self._move_cabinet(number)
            elif dlg.action == CabinetDetailDialog.VACATE:
                res = QMessageBox.question(self, "반납 확인", f"{number}번 캐비닛을 반납 처리(비우기) 할까요?")
                if res == QMessageBox.Yes:
                    del self.allocations[number]
                    self.on_save()
                    self.render_grid()
        else:
            res = QMessageBox.question(
                self, "캐비닛 배정",
                f"[캐비닛 {number}번] 사용 가능(미배정) 상태입니다.\n이 캐비닛에 새로운 학생을 배정하시겠습니까?",
            )
            if res == QMessageBox.Yes:
                self._open_edit(number, None)

    def _open_edit(self, number: int, alloc: CabinetAllocation | None):
        dlg = CabinetEditDialog(self, number, alloc, self.master_students)
        if dlg.exec() != QDialog.Accepted:
            return
        sid, name, start, end = dlg.result_values()
        if not sid or not name:
            QMessageBox.warning(self, "경고", "모든 항목을 입력해 주세요.")
            return
        if end < start:
            QMessageBox.warning(self, "대여 기간", "대여 종료일이 시작일보다 빠릅니다.")
            return

        dup = next((n for n, a in self.allocations.items() if n != number and a.student and a.student.student_id == sid), None)
        if dup is not None:
            QMessageBox.warning(self, "배정 오류", f"해당 학번({sid})은 이미 {dup}번 캐비닛에 배정되어 있습니다. 중복 배정할 수 없습니다.")
            return

        if alloc is not None and alloc.student is not None and alloc.student.student_id == sid:
            student = alloc.student
        else:
            master = next((m for m in self.master_students if m.student_id == sid), None)
            student = master.clone() if master is not None else StudentInfo(student_id=sid, department="소프트웨어융합학과")
        student.name = name

        self.allocations[number] = CabinetAllocation(cabinet_num=number, student=student, period=format_period(start, end))
        self.on_save()
        self.render_grid()
        QMessageBox.information(self, "저장 완료", "캐비닛 정보가 저장되었습니다.")

    def _move_cabinet(self, from_num: int):
        empty = [n for n in range(1, TOTAL_CABINETS + 1) if n not in self.allocations and n != from_num]
        if not empty:
            QMessageBox.warning(self, "알림", "옮길 수 있는 빈 캐비닛이 없습니다.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(f"캐비닛 {from_num}번 옮기기")
        form = QFormLayout(dlg)
        combo = QComboBox()
        for n in empty:
            combo.addItem(f"{n}번", n)
        form.addRow("옮길 빈 캐비닛", combo)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        form.addRow(btns)
        if dlg.exec() != QDialog.Accepted:
            return

        to_num = combo.currentData()
        alloc = self.allocations.pop(from_num)
        alloc.cabinet_num = to_num
        self.allocations[to_num] = alloc
        self.highlighted = to_num
        self.page = 1 if to_num <= 24 else 2
        self.on_save()
        self.render_grid()

    # --------------------------------------------------------------- D&D
    def handle_drop(self, src: int, dst: int):
        if src == dst or src not in self.allocations:
            return
        moving = self.allocations[src]
        occupant = self.allocations.get(dst)

        if occupant is not None:
            moving_name = moving.student.name if moving.student and moving.student.name else (moving.student.student_id if moving.student else "")
            occ_name = occupant.student.name if occupant.student and occupant.student.name else (occupant.student.student_id if occupant.student else "다른 학생")
            res = QMessageBox.question(
                self, "캐비닛 맞바꾸기",
                f"{dst}번 캐비닛은 {occ_name} 학생이 쓰고 있습니다.\n\n"
                f"{moving_name}({src}번)과 자리를 맞바꿀까요?\n"
                f"→ {moving_name}: {src}번 → {dst}번 / {occ_name}: {dst}번 → {src}번",
            )
            if res != QMessageBox.Yes:
                self.render_grid()
                return
            moving.cabinet_num, occupant.cabinet_num = dst, src
            self.allocations[src] = occupant
            self.allocations[dst] = moving
        else:
            moving.cabinet_num = dst
            del self.allocations[src]
            self.allocations[dst] = moving

        self.highlighted = dst
        self.on_save()
        self.render_grid()
