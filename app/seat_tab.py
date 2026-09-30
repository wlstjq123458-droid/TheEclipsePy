"""
[좌석 배정] 탭 — 52석 좌석 배치도.
C# 버전의 RenderSeatGrid / SeatCard_* / ShowStudentDetailsModal 등에 대응한다.
"""
from __future__ import annotations

import datetime
import random

from PySide6.QtCore import Qt, QPoint, QMimeData, QSize
from PySide6.QtGui import QDrag, QColor
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame,
    QPushButton, QComboBox, QMessageBox, QDialog, QFormLayout, QLineEdit,
    QCheckBox, QDialogButtonBox, QFileDialog, QScrollArea, QGraphicsOpacityEffect,
    QListWidget, QListWidgetItem, QTextEdit,
)

from . import io_import as ioimp
from .models import Seat, StudentInfo, MemoItem
from .config import SEASON_NAMES

MIME_SEAT = "application/x-seatmanager-seat"

# (seat_num, row, col, colspan, is_gray) — C#의 RenderSeatGrid 배치 그대로.
POSITIONS = [
    (1, 0, 0, 1, False), (2, 0, 1, 1, False), (3, 0, 2, 1, False),
    (4, 0, 4, 1, False), (5, 0, 5, 1, False), (6, 0, 6, 1, False),

    (7, 1, 0, 1, False), (8, 1, 1, 1, False), (9, 1, 2, 1, False),
    (10, 1, 4, 1, False), (11, 1, 5, 1, False), (12, 1, 6, 1, False),

    (13, 2, 0, 1, False), (14, 2, 1, 1, False), (15, 2, 2, 1, False),
    (16, 2, 4, 1, False), (17, 2, 5, 1, False), (18, 2, 6, 1, False),

    (19, 3, 0, 1, False), (20, 3, 1, 1, False), (21, 3, 2, 1, False),
    (22, 3, 4, 1, False), (23, 3, 5, 1, False), (-1, 3, 6, 2, False),  # 기둥

    (24, 4, 0, 1, False), (25, 4, 1, 1, False), (26, 4, 2, 1, False),
    (27, 4, 4, 1, False), (28, 4, 5, 1, False),

    (29, 5, 0, 1, False), (30, 5, 1, 1, False), (31, 5, 2, 1, False),
    (32, 5, 4, 1, False), (33, 5, 5, 1, False), (34, 5, 6, 1, False), (35, 5, 7, 1, False),

    (36, 6, 0, 1, False), (37, 6, 1, 1, False), (38, 6, 2, 1, False),
    (39, 6, 4, 1, False), (40, 6, 5, 1, False), (41, 6, 6, 1, False), (42, 6, 7, 1, False),

    (43, 7, 0, 1, True), (44, 7, 1, 1, True), (45, 7, 4, 1, True), (46, 7, 5, 1, True), (47, 7, 6, 1, True),

    (48, 8, 0, 1, True), (49, 8, 1, 1, True), (50, 8, 4, 1, True), (51, 8, 5, 1, True), (52, 8, 6, 1, True),
]

DRAG_THRESHOLD = 8


def mask_student_id(sid: str) -> str:
    if not sid:
        return sid
    if len(sid) == 8:
        return sid[:2] + "****" + sid[6:]
    if len(sid) <= 2:
        return sid
    hide = min(4, len(sid) - 2)
    start = (len(sid) - hide) // 2
    return sid[:start] + "*" * hide + sid[start + hide:]


def mask_name(name: str) -> str:
    if not name or len(name) < 2:
        return name
    mid = len(name) // 2
    return name[:mid] + "*" + name[mid + 1:]


class SeatCard(QFrame):
    """좌석 카드 하나. 클릭이면 상세 모달, 누른 채 움직이면 드래그로 자리를 바꾼다."""

    def __init__(self, tab: "SeatTab", seat_number: int, is_gray: bool):
        super().__init__()
        self.tab = tab
        self.seat_number = seat_number
        self.is_gray = is_gray
        self.setFixedSize(96, 68)
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self._press_pos: QPoint | None = None
        self._dragging_candidate = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 3, 6, 3)
        outer.setSpacing(1)

        top = QHBoxLayout()
        top.setSpacing(2)
        self.lbl_num = QLabel(str(seat_number))
        self.lbl_num.setStyleSheet("font-size:10px; font-weight:bold; color:#6B7280;")
        top.addWidget(self.lbl_num)
        self.lbl_lock = QLabel("")
        self.lbl_lock.setStyleSheet("font-size:9px;")
        top.addWidget(self.lbl_lock)
        top.addStretch()
        outer.addLayout(top)

        self.lbl_id = QLabel("")
        self.lbl_id.setAlignment(Qt.AlignCenter)
        self.lbl_id.setStyleSheet("font-size:9px; color:#4B5563;")
        self.lbl_name = QLabel("")
        self.lbl_name.setAlignment(Qt.AlignCenter)
        self.lbl_name.setStyleSheet("font-size:12px; font-weight:bold; color:#111827;")
        outer.addWidget(self.lbl_id)
        outer.addWidget(self.lbl_name)
        outer.addStretch()

        self.refresh()

    def seat(self) -> Seat:
        return self.tab.seat_by_number(self.seat_number)

    def refresh(self):
        seat = self.seat()
        locked = seat.is_locked()
        self.lbl_lock.setText("🔒" if locked else "")

        if seat.student is not None:
            sid = mask_student_id(seat.student.student_id) if self.tab.mask_info else seat.student.student_id
            name = mask_name(seat.student.name) if self.tab.mask_info else seat.student.name
            self.lbl_id.setText(sid)
            self.lbl_name.setText(name)
        else:
            self.lbl_id.setText("")
            self.lbl_name.setText("")

        self._apply_style()

    def _apply_style(self, drag_over: str | None = None):
        seat = self.seat()
        bg = "#D1D5DB" if self.is_gray else "#FFFFFF"
        border = "#E5E7EB"
        width = "1.5px"

        if drag_over == "blue":
            bg, border, width = "#DBEAFE", "#2563EB", "3px"
        elif drag_over == "red":
            bg, border, width = "#FEE2E2", "#EF4444", "3px"
        elif seat.is_selected:
            bg, border = "#FEF9C3", "#EAB308"
        elif seat.is_locked():
            border = "#F97316"

        self.setStyleSheet(
            f"SeatCard {{ background:{bg}; border:{width} solid {border}; border-radius:4px; }}"
        )

    # ------------------------------------------------------------- mouse
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.tab.fix_mode or self.tab.delete_mode:
            seat = self.seat()
            seat.is_selected = not seat.is_selected
            self.tab.on_selection_changed()
            self.refresh()
            return
        self._press_pos = e.position().toPoint()
        self._dragging_candidate = self.seat().student is not None

    def mouseMoveEvent(self, e):
        if self.tab.fix_mode or self.tab.delete_mode:
            return
        if self._press_pos is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press_pos).manhattanLength() < DRAG_THRESHOLD:
            return

        seat = self.seat()
        self._press_pos = None
        if not self._dragging_candidate or seat.student is None:
            return
        if seat.is_locked():
            self.tab.show_fixed_seat_popup()
            return

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_SEAT, str(self.seat_number).encode("utf-8"))
        drag.setMimeData(mime)
        effect = QGraphicsOpacityEffect(self)
        effect.setOpacity(0.3)
        self.setGraphicsEffect(effect)
        drag.exec(Qt.MoveAction)
        self.setGraphicsEffect(None)
        self.refresh()

    def mouseReleaseEvent(self, e):
        if self.tab.fix_mode or self.tab.delete_mode:
            return
        if self._press_pos is not None:
            self._press_pos = None
            self.tab.open_seat_modal(self.seat_number)

    # ---------------------------------------------------------- drag/drop
    def dragEnterEvent(self, e):
        if not e.mimeData().hasFormat(MIME_SEAT) or self.tab.fix_mode or self.tab.delete_mode:
            e.ignore()
            return
        src_num = int(bytes(e.mimeData().data(MIME_SEAT)).decode("utf-8"))
        if src_num == self.seat_number:
            e.ignore()
            return
        locked = self.seat().is_locked() or self.tab.seat_by_number(src_num).is_locked()
        self._apply_style("red" if locked else "blue")
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.refresh()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dropEvent(self, e):
        if not e.mimeData().hasFormat(MIME_SEAT):
            return
        src_num = int(bytes(e.mimeData().data(MIME_SEAT)).decode("utf-8"))
        self.tab.handle_drop(src_num, self.seat_number)
        e.acceptProposedAction()


class SeatDetailDialog(QDialog):
    """좌석 상세/편집 모달. C#의 ShowStudentDetailsModal에 대응한다."""

    def __init__(self, parent, seat: Seat):
        super().__init__(parent)
        self.seat = seat
        self.setWindowTitle(f"좌석 {seat.seat_number}")
        form = QFormLayout(self)

        stu = seat.student
        self.ed_name = QLineEdit(stu.name if stu else "")
        self.ed_dept = QLineEdit(stu.department if stu else "")
        self.ed_advisor = QLineEdit(stu.advisor if stu else "")
        self.ed_email = QLineEdit(stu.email if stu else "")
        self.ed_contact = QLineEdit(stu.contact if stu else "")
        self.ed_id = QLineEdit(stu.student_id if stu else "")
        if stu is not None:
            self.ed_id.setReadOnly(True)  # 이미 배정된 학생의 학번은 여기서 바꾸지 않는다 (데이터 관리에서 변경)

        form.addRow("학번" + (" (신규 배정 시 자동 부여)" if stu is None else ""), self.ed_id)
        form.addRow("이름", self.ed_name)
        form.addRow("소속", self.ed_dept)
        form.addRow("지도교수", self.ed_advisor)
        form.addRow("이메일", self.ed_email)
        form.addRow("연락처", self.ed_contact)

        self.chk_fixed = QCheckBox("이 좌석 고정 (드래그로 옮길 수 없음)")
        self.chk_fixed.setChecked(seat.is_fixed)
        is_grad = stu is not None and stu.is_graduate()
        if is_grad:
            self.chk_fixed.setChecked(True)
            self.chk_fixed.setEnabled(False)
            self.chk_fixed.setToolTip("대학원생 좌석은 항상 고정됩니다.")
        form.addRow(self.chk_fixed)

        btns = QDialogButtonBox()
        btn_save = btns.addButton("저장", QDialogButtonBox.AcceptRole)
        btn_save.clicked.connect(self.accept)
        if stu is not None:
            btn_vacate = btns.addButton("좌석 비우기", QDialogButtonBox.DestructiveRole)
            btn_vacate.clicked.connect(self._vacate)
        btn_cancel = btns.addButton("닫기", QDialogButtonBox.RejectRole)
        btn_cancel.clicked.connect(self.reject)
        form.addRow(btns)

        self.vacate_requested = False

    def _vacate(self):
        self.vacate_requested = True
        self.accept()


class SeatTab(QWidget):
    """
    C# 버전의 [대시보드](TabDashboard) 화면 — 좌석 배치도 + 오른쪽 메모장.
    C# 버전에는 "좌석 배정"이라는 별도 탭이 없고 이 화면이 곧 대시보드다.
    """

    def __init__(self, seat_cache: dict[str, list[Seat]], master_students: list[StudentInfo], memos: list[MemoItem], on_save):
        super().__init__()
        self.seat_cache = seat_cache
        self.master_students = master_students
        self.memos = memos
        self.on_save = on_save
        self._editing_memo: MemoItem | None = None

        self.fix_mode = False
        self.delete_mode = False
        self.mask_info = False
        self.active_seats: list[Seat] = []
        self.season_key = ""
        self._cards: dict[int, SeatCard] = {}

        self._build_ui()
        self.load_season()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        left = QWidget()
        root = QVBoxLayout(left)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("년도"))
        self.combo_year = QComboBox()
        cur_year = datetime.date.today().year
        for y in range(cur_year - 1, cur_year + 3):
            self.combo_year.addItem(str(y))
        self.combo_year.setCurrentText(str(cur_year))
        bar.addWidget(self.combo_year)

        bar.addWidget(QLabel("학기"))
        self.combo_season = QComboBox()
        self.combo_season.addItems(SEASON_NAMES)
        bar.addWidget(self.combo_season)

        btn_search = QPushButton("🔍 조회")
        btn_search.clicked.connect(self.load_season)
        bar.addWidget(btn_search)

        bar.addSpacing(20)
        self.btn_fix_mode = QPushButton("좌석 고정 모드")
        self.btn_fix_mode.clicked.connect(self.toggle_fix_mode)
        bar.addWidget(self.btn_fix_mode)

        self.btn_delete_mode = QPushButton("좌석 데이터 삭제")
        self.btn_delete_mode.clicked.connect(self.toggle_delete_mode)
        bar.addWidget(self.btn_delete_mode)

        self.btn_delete_selected = QPushButton("선택 좌석 비우기")
        self.btn_delete_selected.clicked.connect(self.delete_selected)
        self.btn_delete_selected.setVisible(False)
        bar.addWidget(self.btn_delete_selected)

        self.btn_delete_all = QPushButton("🗑️ 모두 삭제")
        self.btn_delete_all.setStyleSheet("background:#EF4444; color:white; font-weight:bold;")
        self.btn_delete_all.clicked.connect(self.delete_all_seats)
        bar.addWidget(self.btn_delete_all)

        self.btn_random = QPushButton("🎲 랜덤 배정")
        self.btn_random.clicked.connect(self.random_allocation)
        bar.addWidget(self.btn_random)

        self.btn_mask = QPushButton("🔒 정보 가리기")
        self.btn_mask.clicked.connect(self.toggle_mask)
        bar.addWidget(self.btn_mask)

        btn_import = QPushButton("📥 좌석데이터 불러오기")
        btn_import.clicked.connect(self.import_seat_data)
        bar.addWidget(btn_import)

        bar.addStretch()
        root.addLayout(bar)

        self.lbl_season_info = QLabel("")
        self.lbl_season_info.setStyleSheet("color:#2563EB; font-weight:bold;")
        root.addWidget(self.lbl_season_info)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setSpacing(6)
        scroll.setWidget(grid_host)
        root.addWidget(scroll, 1)

        outer.addWidget(left, 1)
        outer.addWidget(self._build_memo_panel())

    def _build_memo_panel(self) -> QWidget:
        """C#의 오른쪽 메모 사이드바(대시보드 탭)와 같은 구성: 목록 + 입력창 + 추가 버튼."""
        panel = QFrame()
        panel.setObjectName("MemoPanel")
        panel.setFixedWidth(320)
        panel.setStyleSheet("#MemoPanel { background:white; border-left:1px solid #E5E7EB; }")
        lay = QVBoxLayout(panel)
        lay.setContentsMargins(15, 15, 15, 15)

        title = QLabel("메모")
        title.setStyleSheet("font-size:16px; font-weight:bold; color:#1F2937; border:none;")
        lay.addWidget(title)

        self.list_memos = QListWidget()
        self.list_memos.setStyleSheet("QListWidget { border:none; }")
        lay.addWidget(self.list_memos, 1)

        self.txt_new_memo = QTextEdit()
        self.txt_new_memo.setFixedHeight(60)
        lay.addWidget(self.txt_new_memo)

        self.btn_add_memo = QPushButton("+ 메모 추가")
        self.btn_add_memo.setStyleSheet("background:#2563EB; color:white; font-weight:bold; border:none;")
        self.btn_add_memo.clicked.connect(self.add_or_finish_edit_memo)
        lay.addWidget(self.btn_add_memo)

        self.refresh_memos()
        return panel

    # ---------------------------------------------------------------- memo
    def refresh_memos(self):
        self.list_memos.clear()
        for m in self.memos:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 4, 0, 4)
            lbl = QLabel("🔵 " + m.content)
            lbl.setWordWrap(True)
            lbl.setStyleSheet("border:none; color:#374151; font-size:12px;")
            h.addWidget(lbl, 1)
            btn_edit = QPushButton("✎")
            btn_edit.setFixedWidth(26)
            btn_edit.setStyleSheet("border:none; color:#2563EB; font-weight:bold; background:transparent;")
            btn_edit.clicked.connect(lambda _, mm=m: self.edit_memo(mm))
            btn_del = QPushButton("✕")
            btn_del.setFixedWidth(26)
            btn_del.setStyleSheet("border:none; color:#EF4444; font-weight:bold; background:transparent;")
            btn_del.clicked.connect(lambda _, mm=m: self.delete_memo(mm))
            h.addWidget(btn_edit)
            h.addWidget(btn_del)

            item = QListWidgetItem()
            item.setSizeHint(row.sizeHint())
            self.list_memos.addItem(item)
            self.list_memos.setItemWidget(item, row)

    def add_or_finish_edit_memo(self):
        text = self.txt_new_memo.toPlainText().strip()
        if self._editing_memo is not None:
            if text:
                self._editing_memo.content = text
            self._editing_memo = None
            self.btn_add_memo.setText("+ 메모 추가")
            self.txt_new_memo.clear()
        elif text:
            self.memos.append(MemoItem(content=text))
            self.txt_new_memo.clear()
        else:
            return
        self.on_save()
        self.refresh_memos()

    def edit_memo(self, memo: MemoItem):
        self._editing_memo = memo
        self.txt_new_memo.setPlainText(memo.content)
        self.btn_add_memo.setText("편집 완료")

    def delete_memo(self, memo: MemoItem):
        self.memos.remove(memo)
        self.on_save()
        self.refresh_memos()

    # --------------------------------------------------------------- data
    def seat_by_number(self, num: int) -> Seat:
        return self.active_seats[num - 1]

    def current_season_key(self) -> str:
        return f"{self.combo_year.currentText()}_{self.combo_season.currentText()}"

    def load_season(self):
        key = self.current_season_key()
        if key not in self.seat_cache:
            self.seat_cache[key] = [Seat(seat_number=i) for i in range(1, 53)]
            self.on_save()
        self.season_key = key
        self.active_seats = self.seat_cache[key]
        self.fix_mode = False
        self.delete_mode = False
        self.btn_fix_mode.setText("좌석 고정 모드")
        self.btn_delete_mode.setText("좌석 데이터 삭제")
        self.btn_delete_selected.setVisible(False)
        self.render_grid()

    def render_grid(self):
        # 기존 카드 정리
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards.clear()

        occupied = sum(1 for s in self.active_seats if s.student is not None)
        self.lbl_season_info.setText(f"{self.season_key} — 배정 {occupied}/52석")

        for seat_num, row, col, colspan, is_gray in POSITIONS:
            if seat_num == -1:
                pillar = QFrame()
                pillar.setFixedSize(96 * colspan + 6 * (colspan - 1), 68)
                pillar.setStyleSheet("background:#F3F4F6; border:1px solid #E5E7EB; border-radius:4px;")
                lay = QVBoxLayout(pillar)
                lbl = QLabel("기둥")
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("color:#9CA3AF; font-weight:bold;")
                lay.addWidget(lbl)
                self.grid.addWidget(pillar, row, col, 1, colspan)
                continue

            card = SeatCard(self, seat_num, is_gray)
            self._cards[seat_num] = card
            self.grid.addWidget(card, row, col, 1, colspan)

    # ------------------------------------------------------------- modes
    def toggle_mask(self):
        self.mask_info = not self.mask_info
        self.btn_mask.setText("🔓 정보 표시" if self.mask_info else "🔒 정보 가리기")
        for c in self._cards.values():
            c.refresh()

    def toggle_fix_mode(self):
        if self.delete_mode:
            self.delete_mode = False
            self.btn_delete_mode.setText("좌석 데이터 삭제")
            self.btn_delete_selected.setVisible(False)

        if not self.fix_mode:
            self.fix_mode = True
            self.btn_fix_mode.setText("💾 고정 저장/종료")
            for s in self.active_seats:
                s.is_selected = False
        else:
            self.fix_mode = False
            self.btn_fix_mode.setText("좌석 고정 모드")
            for s in self.active_seats:
                if s.is_selected:
                    if s.student is not None and s.student.is_graduate():
                        s.is_selected = False
                        continue
                    s.is_fixed = not s.is_fixed
                    s.is_selected = False
            self.on_save()
        self.render_grid()

    def toggle_delete_mode(self):
        if self.fix_mode:
            self.fix_mode = False
            self.btn_fix_mode.setText("좌석 고정 모드")

        self.delete_mode = not self.delete_mode
        self.btn_delete_mode.setText("💾 선택 삭제 모드 활성 중" if self.delete_mode else "좌석 데이터 삭제")
        if not self.delete_mode:
            self.btn_delete_selected.setVisible(False)
        for s in self.active_seats:
            s.is_selected = False
        self.render_grid()

    def on_selection_changed(self):
        if self.delete_mode:
            any_selected = any(s.is_selected for s in self.active_seats)
            self.btn_delete_selected.setVisible(any_selected)

    def delete_selected(self):
        res = QMessageBox.question(self, "확인", "선택한 좌석들의 인적사항을 삭제하시겠습니까?")
        if res != QMessageBox.Yes:
            return
        for s in self.active_seats:
            if s.is_selected:
                s.student = None
                s.is_selected = False
                s.is_fixed = False
        self.delete_mode = False
        self.btn_delete_mode.setText("좌석 데이터 삭제")
        self.btn_delete_selected.setVisible(False)
        self.on_save()
        self.render_grid()

    def delete_all_seats(self):
        """이번 시즌 모든 좌석의 학생 정보를 지운다. 좌석 번호·고정 상태는 그대로 남는다."""
        res = QMessageBox.warning(
            self, "경고",
            "모든 좌석의 인적 사항을 삭제하시겠습니까? (좌석 번호와 고정상태는 남습니다)\n이 작업은 되돌릴 수 없습니다.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        for s in self.active_seats:
            s.student = None
            s.is_selected = False
        self.on_save()
        self.render_grid()

    # --------------------------------------------------------------- D&D
    def show_fixed_seat_popup(self):
        QMessageBox.warning(
            self, "고정된 좌석",
            "고정된 좌석은 이동하거나 교체할 수 없습니다.\n자리를 옮기려면 먼저 [좌석 고정 모드]에서 고정을 해제해 주세요.",
        )

    def handle_drop(self, src_num: int, dst_num: int):
        if src_num == dst_num:
            return
        source = self.seat_by_number(src_num)
        target = self.seat_by_number(dst_num)
        if source.student is None:
            return
        if source.is_locked() or target.is_locked():
            self.show_fixed_seat_popup()
            self._cards[dst_num].refresh()
            return

        moving = source.student
        occupant = target.student
        if occupant is not None:
            occ_name = occupant.name or occupant.student_id
            mov_name = moving.name or moving.student_id
            res = QMessageBox.question(
                self, "좌석 맞바꾸기",
                f"{target.seat_number}번 좌석에는 {occ_name} 학생이 있습니다.\n{mov_name} 학생과 자리를 맞바꿀까요?",
            )
            if res != QMessageBox.Yes:
                self._cards[dst_num].refresh()
                return

        source.student = occupant
        target.student = moving
        self._mark_active_this_season(moving)
        self._mark_active_this_season(occupant)
        self.on_save()
        self.render_grid()

    def _mark_active_this_season(self, student: StudentInfo | None):
        if student is None or not student.student_id:
            return
        master = next((m for m in self.master_students if m.student_id == student.student_id), None)
        if master is not None:
            master.last_active_season = self.season_key

    # -------------------------------------------------------------- modal
    def open_seat_modal(self, seat_num: int):
        seat = self.seat_by_number(seat_num)
        dlg = SeatDetailDialog(self, seat)
        if dlg.exec() != QDialog.Accepted:
            return

        if dlg.vacate_requested:
            seat.student = None
            seat.is_fixed = False
        else:
            if seat.student is None:
                seat.student = StudentInfo(student_id=dlg.ed_id.text().strip() or f"NEW{random.randint(1000, 9999)}")
            seat.student.name = dlg.ed_name.text()
            seat.student.department = dlg.ed_dept.text()
            seat.student.advisor = dlg.ed_advisor.text()
            seat.student.email = dlg.ed_email.text()
            seat.student.contact = dlg.ed_contact.text()
            seat.student.last_active_season = self.season_key

            if seat.student.is_graduate():
                seat.is_fixed = True
            else:
                seat.is_fixed = dlg.chk_fixed.isChecked()

            master = next((m for m in self.master_students if m.student_id == seat.student.student_id), None)
            if master is None:
                self.master_students.append(seat.student.clone())
            else:
                master.name = seat.student.name
                master.department = seat.student.department
                master.advisor = seat.student.advisor
                master.email = seat.student.email
                master.contact = seat.student.contact
                master.last_active_season = self.season_key

        self.on_save()
        self.render_grid()

    # ------------------------------------------------------------- random
    def random_allocation(self):
        current_ids = {s.student.student_id for s in self.active_seats if s.student is not None}
        new_students = [
            m for m in self.master_students
            if m.last_active_season == self.season_key and m.student_id not in current_ids
        ]

        if new_students:
            empty_seats = [
                s for s in self.active_seats
                if s.student is None and not s.is_pillar and not (43 <= s.seat_number <= 52)
            ]
            empty_seats.sort(key=lambda s: s.seat_number)
            if len(empty_seats) < len(new_students):
                QMessageBox.warning(self, "알림", "빈 좌석이 부족하여 추가 학생을 배치할 수 없습니다.")
                return
            targets = empty_seats[max(0, len(empty_seats) - len(new_students)):]
            shuffled = new_students[:]
            random.shuffle(shuffled)
            for stu, seat in zip(shuffled, targets):
                stu.last_active_season = self.season_key
                seat.student = stu.clone()
                if seat.student.is_graduate():
                    seat.is_fixed = True
            self.on_save()
            self.render_grid()
            QMessageBox.information(self, "신규 배치 완료", f"신규 등록 학생 {len(shuffled)}명이 빈 자리(뒷자리 우선)에 랜덤 배치되었습니다.")
            return

        unfixed = [
            s for s in self.active_seats
            if not s.is_fixed and not s.is_pillar and not (s.student is not None and s.student.is_graduate())
            and not (43 <= s.seat_number <= 52)
        ]
        unfixed.sort(key=lambda s: s.seat_number)
        if len(unfixed) <= 1:
            QMessageBox.warning(self, "알림", "고정되지 않은 좌석이 부족하여 배정할 수 없습니다.")
            return

        pool = [s.student for s in unfixed if s.student is not None]
        for s in unfixed:
            s.student = None
        random.shuffle(pool)
        for seat, stu in zip(unfixed, pool):
            seat.student = stu
        self.on_save()
        self.render_grid()
        QMessageBox.information(self, "재배치 완료", "고정되지 않은 좌석의 학생을 다시 섞어 배치했습니다.")

    # -------------------------------------------------------------- import
    def import_seat_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "좌석 데이터 불러오기 (상상Labs 입실신청 응답)", "", "응답 시트 파일 (*.xlsx *.csv)"
        )
        if not path:
            return
        try:
            table = ioimp.read_table(path)
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
            return

        imported: list[StudentInfo] = []
        seen_ids = set()
        for row in table:
            def cell(i):
                return ioimp.cell_str(ioimp.cell_at(row, i))

            space, dept, name = cell(1), cell(2), cell(3)
            id_raw = cell(4)
            contact = ioimp.normalize_phone(ioimp.cell_at(row, 5))
            email = cell(6)
            advisor = cell(7)

            if "이름을 작성" in name or "소속을 작성" in dept or "학번" in id_raw or "공간을 선택" in space:
                continue

            sid = ioimp.normalize_student_id(ioimp.cell_at(row, 4))
            if not name and not sid:
                continue
            if space and ("상상" not in space and "U301" not in space):
                continue
            if sid and sid in seen_ids:
                continue
            if sid:
                seen_ids.add(sid)

            advisor = advisor.replace("교수님", "").replace("교수", "").strip()
            imported.append(StudentInfo(
                student_id=sid, name=name,
                department=dept or "소프트웨어전공",
                email=email, contact=contact, advisor=advisor,
            ))

        if not imported:
            QMessageBox.warning(self, "알림", "불러올 학생 정보를 찾지 못했습니다.")
            return

        res = QMessageBox.question(
            self, "좌석데이터 불러오기",
            f"{self.season_key} 좌석 데이터를 불러온 명단 {len(imported)}명으로 교체합니다.\n"
            "고정된 좌석은 그대로 유지됩니다.\n\n계속하시겠습니까?",
        )
        if res != QMessageBox.Yes:
            return

        fixed_ids = {
            s.student.student_id for s in self.active_seats
            if s.is_fixed and s.student is not None and s.student.student_id
        }
        queue = [s for s in imported if not s.student_id or s.student_id not in fixed_ids]

        placed = 0
        for seat in sorted(self.active_seats, key=lambda s: s.seat_number):
            if seat.is_pillar or seat.is_fixed:
                continue
            if not queue:
                seat.student = None
                continue
            stu = queue.pop(0)
            seat.student = stu
            if stu.is_graduate():
                seat.is_fixed = True
            placed += 1

        added = 0
        for stu in imported:
            master = None
            if stu.student_id:
                master = next((m for m in self.master_students if m.student_id == stu.student_id), None)
            if master is None:
                clone = stu.clone()
                clone.last_active_season = self.season_key
                self.master_students.append(clone)
                added += 1
            else:
                master.last_active_season = self.season_key
                if not master.name and stu.name: master.name = stu.name
                if not master.department and stu.department: master.department = stu.department
                if not master.advisor and stu.advisor: master.advisor = stu.advisor
                if not master.contact and stu.contact: master.contact = stu.contact
                if not master.email and stu.email: master.email = stu.email

        self.on_save()
        self.render_grid()
        leftover = f"\n\n좌석 수보다 {len(queue)}명이 많아 배치되지 못했습니다." if queue else ""
        QMessageBox.information(
            self, "불러오기 완료",
            f"{self.season_key} 좌석에 {placed}명을 배치했습니다.\n학생 데이터: 신규 {added}명 추가{leftover}",
        )
