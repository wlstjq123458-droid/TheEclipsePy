"""
[대시보드] 화면 — C# 버전 TabDashboard 그대로.
왼쪽: 연도/학기 조회 패널 + 동작 버튼 + 52석 좌석 배치도, 오른쪽(320px): 메모.
좌석을 누르면 ModalSeatDetails(좌석 상세) 오버레이가 뜬다.
"""
from __future__ import annotations

import datetime
import random
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QPoint, QMimeData, QRectF, QPointF
from PySide6.QtGui import QDrag, QColor, QPainter, QPen, QFont, QPixmap
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QFrame, QComboBox, QScrollArea,
    QLineEdit, QTextEdit, QListWidget, QListWidgetItem, QMenu, QFileDialog, QSizePolicy, QApplication,
)

from . import theme, widgets as w
from . import io_import as ioimp
from .config import SEASON_NAMES
from .models import Seat, StudentInfo, MemoItem

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext

MIME_SEAT = "application/x-seatmanager-seat"

# (좌석번호, 행, 열, 열 병합, 회색 줄) — C# RenderSeatGrid의 positions 그대로 (-1 = 기둥)
POSITIONS = [
    (1, 0, 0, 1, False), (2, 0, 1, 1, False), (3, 0, 2, 1, False), (4, 0, 4, 1, False), (5, 0, 5, 1, False), (6, 0, 6, 1, False),
    (7, 1, 0, 1, False), (8, 1, 1, 1, False), (9, 1, 2, 1, False), (10, 1, 4, 1, False), (11, 1, 5, 1, False), (12, 1, 6, 1, False),
    (13, 2, 0, 1, False), (14, 2, 1, 1, False), (15, 2, 2, 1, False), (16, 2, 4, 1, False), (17, 2, 5, 1, False), (18, 2, 6, 1, False),
    (19, 3, 0, 1, False), (20, 3, 1, 1, False), (21, 3, 2, 1, False), (22, 3, 4, 1, False), (23, 3, 5, 1, False), (-1, 3, 6, 2, False),
    (24, 4, 0, 1, False), (25, 4, 1, 1, False), (26, 4, 2, 1, False), (27, 4, 4, 1, False), (28, 4, 5, 1, False),
    (29, 5, 0, 1, False), (30, 5, 1, 1, False), (31, 5, 2, 1, False), (32, 5, 4, 1, False), (33, 5, 5, 1, False), (34, 5, 6, 1, False), (35, 5, 7, 1, False),
    (36, 6, 0, 1, False), (37, 6, 1, 1, False), (38, 6, 2, 1, False), (39, 6, 4, 1, False), (40, 6, 5, 1, False), (41, 6, 6, 1, False), (42, 6, 7, 1, False),
    (43, 7, 0, 1, True), (44, 7, 1, 1, True), (45, 7, 4, 1, True), (46, 7, 5, 1, True), (47, 7, 6, 1, True),
    (48, 8, 0, 1, True), (49, 8, 1, 1, True), (50, 8, 4, 1, True), (51, 8, 5, 1, True), (52, 8, 6, 1, True),
]
COORDS = {n: (r, c) for n, r, c, _span, _g in POSITIONS if n > 0}


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


def _font(px: int, bold: bool = False, family: str = "Segoe UI") -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setBold(bold)
    return f


# ====================================================================== 좌석 카드
class SeatCard(QWidget):
    """C#의 seatCard Border(두께 1.5, 둥근 모서리 4)를 직접 그린다."""

    def __init__(self, tab: "SeatTab", seat_number: int, is_gray: bool):
        super().__init__()
        self.tab = tab
        self.seat_number = seat_number
        self.is_gray = is_gray
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptDrops(True)
        self.setMinimumSize(40, 40)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._press: Optional[QPoint] = None
        self._drop_style: Optional[str] = None   # "blue" | "red"
        self._dragging = False

    def seat(self) -> Seat:
        return self.tab.seat_by_number(self.seat_number)

    def paintEvent(self, e):
        seat = self.seat()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        if self._dragging:
            p.setOpacity(0.3)
        locked = seat.is_locked()
        bg = QColor("#D1D5DB" if self.is_gray else "#FFFFFF")
        border, bw = QColor("#E5E7EB"), 1.5
        if seat.is_selected:
            border, bg = QColor("#FFFF00"), QColor("#FEF9C3")
        elif locked:
            border = QColor("#F97316")
        if self._drop_style == "blue":
            border, bg, bw = QColor("#2563EB"), QColor("#DBEAFE"), 3
        elif self._drop_style == "red":
            border, bg, bw = QColor("#EF4444"), QColor("#FEE2E2"), 3
        r = QRectF(self.rect()).adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2)
        p.setPen(QPen(border, bw))
        p.setBrush(bg)
        p.drawRoundedRect(r, 4, 4)

        inner = QRectF(self.rect()).adjusted(bw, bw, -bw, -bw)
        p.setPen(QColor("#6B7280"))
        p.setFont(_font(10, True))
        num = str(self.seat_number)
        p.drawText(QPointF(inner.left() + 5, inner.top() + 2 + 11), num)
        if locked:
            nx = inner.left() + 5 + p.fontMetrics().horizontalAdvance(num)
            lock_font = _font(9)
            lock_font.setFamilies([theme.ICON_FONT, "Segoe UI Symbol", "Segoe UI"])
            p.setFont(lock_font)
            p.setPen(QColor("#000000"))
            p.drawText(QPointF(nx, inner.top() + 2 + 11), " 🔒")

        if seat.student is not None:
            sid = mask_student_id(seat.student.student_id) if self.tab.mask_info else seat.student.student_id
            name = mask_name(seat.student.name) if self.tab.mask_info else seat.student.name
            body = QRectF(inner.left(), inner.top() + 20, inner.width(), inner.height() - 20)
            f_id, f_name = _font(9), _font(12, True)
            h_id = 12
            h_name = 16
            top = body.top() + (body.height() - (h_id + h_name)) / 2
            p.setFont(f_id)
            p.setPen(QColor("#4B5563"))
            p.drawText(QRectF(body.left(), top, body.width(), h_id), Qt.AlignHCenter | Qt.AlignVCenter, sid)
            p.setFont(f_name)
            p.setPen(QColor("#111827"))
            p.drawText(QRectF(body.left(), top + h_id, body.width(), h_name), Qt.AlignHCenter | Qt.AlignVCenter, name)

    # ---------------------------------------------------------------- 마우스
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        t = self.tab
        if t.fix_mode or t.delete_mode:
            s = self.seat()
            s.is_selected = not s.is_selected
            t.on_selection_changed()
            self.update()
            return
        self._press = e.position().toPoint()

    def mouseMoveEvent(self, e):
        t = self.tab
        if t.fix_mode or t.delete_mode or self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        seat = self.seat()
        if seat.student is None:
            return
        if seat.is_locked():
            t.show_fixed_seat_popup()
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData(MIME_SEAT, str(self.seat_number).encode())
        drag.setMimeData(mime)
        pm = self.grab()
        drag.setPixmap(QPixmap())
        self._dragging = True
        self.update()
        drag.exec(Qt.MoveAction)
        self._dragging = False
        if not self.isHidden():
            self.update()

    def mouseReleaseEvent(self, e):
        t = self.tab
        if t.fix_mode or t.delete_mode:
            return
        if self._press is not None:
            self._press = None
            t.open_seat_modal(self.seat())

    # ---------------------------------------------------------------- 드롭
    def _src(self, e) -> Optional[int]:
        if not e.mimeData().hasFormat(MIME_SEAT):
            return None
        return int(bytes(e.mimeData().data(MIME_SEAT)).decode())

    def dragEnterEvent(self, e):
        src = self._src(e)
        t = self.tab
        if src is None or t.fix_mode or t.delete_mode or src == self.seat_number:
            e.ignore()
            return
        self._drop_style = "red" if self.seat().is_locked() else "blue"
        self.update()
        e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop_style = None
        self.update()

    def dropEvent(self, e):
        src = self._src(e)
        self._drop_style = None
        self.update()
        if src is None:
            return
        e.acceptProposedAction()
        self.tab.handle_drop(src, self.seat_number)


class PillarCell(QWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor("#E5E6EB"), 1))
        p.setBrush(QColor("#F3F4F6"))
        p.drawRoundedRect(r, 4, 4)
        p.setPen(QColor("#9CA3AF"))
        p.setFont(_font(12, True))
        p.drawText(self.rect(), Qt.AlignCenter, "기둥")


# ====================================================================== 좌석 상세 모달
class SeatDetailModal(w.OverlayDialog):
    """C# ModalSeatDetails (820x300): 이름/지도 교수/이메일 | 소속/학번/캐비닛 사용, [학생선택] [✕], [좌석 수정]."""

    def __init__(self, tab: "SeatTab", seat: Seat):
        super().__init__(tab, 820, 300)
        self.tab = tab
        self.ctx = tab.ctx
        self.seat = seat
        self.editing = False

        # 오른쪽 위 [학생선택] [✕] — XAML에서 내용 위에 겹쳐(ZIndex) 둔 버튼 줄 (Margin 0,-15,0,0)
        head = QWidget()
        hl = QHBoxLayout(head)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(15)
        btn_select = w.flat_btn("학생선택", "#2563EB", padding=(6, 15), radius=6, font_size=12,
                                on_click=self._select_student)
        btn_select.setFixedHeight(42)
        hl.addWidget(btn_select)
        hl.addWidget(w.text_close_btn(24, on_click=self.reject))
        self.float_top_right(head, top=20, right=35)

        self.body.setContentsMargins(35, 55, 35, 35)
        # XAML: Margin 20,10,20,10 Grid의 * | * 두 열 (각 355px), 오른쪽 열 StackPanel은 Margin 20,0,0,0
        grid = QGridLayout()
        grid.setContentsMargins(20, 0, 20, 0)
        grid.setHorizontalSpacing(0)
        grid.setVerticalSpacing(12)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self.ed_name = self._field()
        self.ed_advisor = self._field()
        self.ed_email = self._field(300)
        self.ed_dept = self._field()
        self.lbl_id = w.label("", 20, bold=True)
        self.lbl_id.setFixedHeight(27)
        self.ed_cabinet = self._field()
        self.ed_cabinet.setReadOnly(True)
        grid.addWidget(self._pair("이름 : ", self.ed_name), 0, 0)
        grid.addWidget(self._pair("지도 교수 : ", self.ed_advisor), 1, 0)
        email_row = self._pair("이메일 : ", self.ed_email)
        grid.addWidget(email_row, 2, 0)
        grid.addWidget(self._pair("소속 : ", self.ed_dept, 20), 0, 1)
        grid.addWidget(self._pair("학번 : ", self.lbl_id, 20), 1, 1)
        grid.addWidget(self._pair("캐비닛 사용 : ", self.ed_cabinet, 20), 2, 1)
        # 이메일 칸(Width=300)은 열(355px)을 넘어가는 부분이 잘려 보인다 — 남는 폭만큼만 보이게 한다
        col_w = (820 - 70 - 40) // 2
        cap_w = email_row.layout().itemAt(0).widget().sizeHint().width()
        self.ed_email.setFixedWidth(min(300, col_w - cap_w))
        self.body.addLayout(grid)
        self.body.addStretch()

        foot = QHBoxLayout()
        foot.setContentsMargins(0, 0, 8, 0)
        foot.addStretch()
        self.btn_edit = w.flat_btn("좌석 수정", "#10B981", padding=(8, 20), radius=4, font_size=12,
                                   on_click=self._edit_save)
        foot.addWidget(self.btn_edit)
        self.body.addSpacing(15)
        self.body.addLayout(foot)

        self._load(seat.student)
        self._set_edit(False)

    def _field(self, width: int = 0) -> QLineEdit:
        """WPF TextBox(가로 크기 자동) — 글자 길이에 맞춰 폭이 늘었다 줄었다 한다. width를 주면 고정."""
        ed = QLineEdit()
        ed.setStyleSheet("QLineEdit { font-size:20px; font-weight:700; color:#000000; }")
        if width:
            ed.setFixedWidth(width)
        else:
            def fit(_t="", e=ed):
                f = QFont("Segoe UI")
                f.setPixelSize(20)
                f.setBold(True)
                from PySide6.QtGui import QFontMetrics
                e.setFixedWidth(max(12, QFontMetrics(f).horizontalAdvance(e.text()) + 10))
            ed.textChanged.connect(fit)
            fit()
        return ed

    @staticmethod
    def _pair(caption: str, field: QWidget, left: int = 0) -> QWidget:
        box = QWidget()
        # 내용 폭과 상관없이 두 열이 똑같이 나뉘도록(WPF * 열) 가로 크기 힌트를 무시한다
        box.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        row = QHBoxLayout(box)
        row.setContentsMargins(left, 0, 0, 0)
        row.setSpacing(0)
        row.addWidget(w.label(caption, 20, bold=True))
        row.addWidget(field)
        row.addStretch()
        return box

    def _load(self, stu: Optional[StudentInfo]):
        if stu is not None:
            self.ed_name.setText(stu.name)
            self.ed_dept.setText(stu.department)
            self.lbl_id.setText(stu.student_id)
            self.ed_advisor.setText(stu.advisor)
            self.ed_email.setText(stu.email)
            alloc = next((n for n, a in self.ctx.state.cabinet_allocations.items()
                          if a.student and a.student.student_id == stu.student_id), None)
            self.ed_cabinet.setText(f"사용 중 (번호: {alloc}번)" if alloc else "사용 안 함")
            for ed in (self.ed_name, self.ed_dept, self.ed_advisor, self.ed_email):
                ed.setCursorPosition(0)
        else:
            for ed in (self.ed_name, self.ed_dept, self.ed_advisor, self.ed_email):
                ed.setText("")
            self.lbl_id.setText("")
            self.ed_cabinet.setText("사용 안 함")

    def _set_edit(self, on: bool):
        self.editing = on
        for ed in (self.ed_name, self.ed_dept, self.ed_advisor, self.ed_email):
            ed.setReadOnly(not on)
            # WPF TextBox(글자 20px) 높이: 테두리 없을 때 27, 테두리 1px일 때 29
            if on:
                ed.setStyleSheet("QLineEdit { font-size:20px; font-weight:700; color:#000000; background:#FFFFFF; border:1px solid #ABADB3; padding:0; }")
                ed.setFixedHeight(29)
            else:
                ed.setStyleSheet("QLineEdit { font-size:20px; font-weight:700; color:#000000; background:transparent; border:none; padding:0; }")
                ed.setFixedHeight(27)
            ed.setCursorPosition(0)
        self.ed_cabinet.setStyleSheet("QLineEdit { font-size:20px; font-weight:700; color:#000000; background:transparent; border:none; padding:0; }")
        self.ed_cabinet.setFixedHeight(27)
        self.btn_edit.setText("저장" if on else "좌석 수정")

    def _edit_save(self):
        if not self.editing:
            self._set_edit(True)
            return
        seat = self.seat
        if seat.student is None:
            seat.student = StudentInfo(student_id="2026" + str(random.randint(1000, 9998)))
        stu = seat.student
        stu.name = self.ed_name.text()
        stu.department = self.ed_dept.text()
        stu.advisor = self.ed_advisor.text()
        stu.email = self.ed_email.text()
        if "대학원" in stu.department:
            seat.is_fixed = True
        master = next((m for m in self.ctx.state.master_students if m.student_id == stu.student_id), None)
        if master is not None:
            master.name, master.department, master.advisor, master.email = stu.name, stu.department, stu.advisor, stu.email
        else:
            self.ctx.state.master_students.append(stu.clone())
        self._set_edit(False)
        self.lbl_id.setText(stu.student_id)
        self.tab.render_seat_grid()
        self.tab.ctx.save_seat_cache()
        self.tab.ctx.save_app_state()
        self.tab.ctx.win.update_alert_badges()
        w.info(self, "학생 정보가 수정되었으며 즉시 대시보드에 데이터가 업데이트되었습니다.", "저장 완료")

    # ------------------------------------------------------------ 학생 선택
    def _select_student(self):
        from .dialogs import StudentSelectorModal
        self.ctx.update_master_cabinet_periods()
        StudentSelectorModal(self, self.ctx.state.master_students, False, self._confirm_student).exec()

    def _confirm_student(self, selected: Optional[StudentInfo]) -> bool:
        if selected is None:
            w.warn(self, "배정할 학생을 먼저 선택하세요.", "경고")
            return False
        target = self.seat
        seats = self.tab.active_seats
        source = next((s for s in seats if s.student and s.student.student_id == selected.student_id
                       and s.seat_number != target.seat_number), None)
        if source is None and target.student and target.student.student_id == selected.student_id:
            return True
        occupant = target.student
        if occupant is not None:
            occ = occupant.name or occupant.student_id
            if source is not None:
                ask = (f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n\n{selected.name} 학생과 자리를 맞바꿀까요?\n"
                       f"→ {selected.name}: {source.seat_number}번 → {target.seat_number}번 / {occ}: {target.seat_number}번 → {source.seat_number}번")
            else:
                ask = f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n\n{occ} 학생을 빼고 {selected.name} 학생을 배정할까요?"
            if not w.ask(self, ask, "좌석 사용 중"):
                return False
        moving = source.student if source is not None else selected.clone()
        if source is not None:
            source.student = occupant
            source.is_fixed = occupant is not None and "대학원" in occupant.department
        target.student = moving
        target.is_fixed = "대학원" in moving.department
        self.ctx.mark_student_active(moving)
        self.ctx.mark_student_active(occupant)
        self._load(moving)
        self.tab.render_seat_grid()
        self.ctx.win.update_alert_badges()
        if occupant is not None and source is not None:
            msg = f"{selected.name} 학생과 {occupant.name or occupant.student_id} 학생의 자리를 맞바꿨습니다. '저장'을 누르면 최종 적용됩니다."
        else:
            msg = f"학생 '{selected.name}'이(가) 좌석에 배정되었습니다. '저장'을 누르면 최종 적용됩니다."
        w.info(self, msg, "좌석 배정")
        return True


# ====================================================================== 대시보드
class SeatTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self.fix_mode = False
        self.delete_mode = False
        self.mask_info = False
        self.active_seats: list[Seat] = []
        self._cards: dict[int, SeatCard] = {}
        self._editing_memo: Optional[MemoItem] = None
        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setStyleSheet("SeatTab { background:#F9FAFB; }")
        self.setAttribute(Qt.WA_StyledBackground, True)
        outer = QHBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        left = QWidget()
        root = QVBoxLayout(left)
        root.setContentsMargins(15, 15, 15, 15)
        root.setSpacing(0)

        wrap_host = QWidget()
        wrap = w.FlowLayout(wrap_host, h_spacing=0, v_spacing=0)

        # ---- 연도/학기 조회 패널 (어두운 배경) ----
        panel = w.Card(bg="#1F2937", border="#1F2937", radius=6, padding=(10, 15), border_width=0)
        pl = panel.hbox()
        pl.addWidget(w.label("년도", 12, bold=True, color="#FFFFFF"))
        pl.addSpacing(8)
        self.combo_year = QComboBox()
        self.combo_year.setFixedWidth(100)
        for y in range(2020, self.ctx.today.year + 1):
            self.combo_year.addItem(str(y))
        self.combo_year.setCurrentIndex(self.combo_year.count() - 1)
        pl.addWidget(self.combo_year)
        pl.addSpacing(25)
        pl.addWidget(w.label("학기", 12, bold=True, color="#FFFFFF"))
        pl.addSpacing(8)
        self.combo_season = QComboBox()
        self.combo_season.setFixedWidth(120)
        self.combo_season.addItems(SEASON_NAMES)
        pl.addWidget(self.combo_season)
        pl.addSpacing(20)
        pl.addWidget(w.flat_btn("🔍 조회", "#111827", padding=(6, 15), radius=4, on_click=self.load_dashboard_layout))
        pl.addSpacing(20)
        self.season_pill = w.Card(bg="#2563EB", border="#2563EB", radius=4, padding=(5, 10), border_width=0)
        sp = self.season_pill.hbox()
        self.lbl_season = w.label("현재 시즌 판별 중", 12, bold=True, color="#FFFFFF")
        sp.addWidget(self.lbl_season)
        pl.addWidget(self.season_pill)
        wrap.addWidget(_margin(panel, right=15, bottom=8))

        # ---- 동작 버튼 ----
        actions = QWidget()
        al = QHBoxLayout(actions)
        al.setContentsMargins(0, 0, 0, 8)
        al.setSpacing(8)
        al.addWidget(w.action_btn("랜덤 배정", on_click=self.random_allocation))
        self.btn_fix = w.action_btn("좌석 고정 모드", on_click=self.toggle_fix_mode)
        al.addWidget(self.btn_fix)
        self.btn_delete_mode = w.action_btn("좌석 데이터 삭제", on_click=self._delete_menu)
        al.addWidget(self.btn_delete_mode)
        al.addWidget(w.action_btn("📥 좌석데이터 불러오기", on_click=self.load_seat_data))
        self.btn_mask = w.action_btn("🔒 정보 가리기", on_click=self.toggle_mask)
        al.addWidget(self.btn_mask)
        al.addWidget(w.action_btn("📤 엑셀 내보내기", on_click=self.export_excel))
        al.addWidget(w.action_btn("🗑️ 모두 삭제", bg="#EF4444", fg="#FFFFFF", border="#DC2626",
                                  on_click=self.delete_all_seats))
        self.btn_delete_selected = w.flat_btn("선택된 좌석 삭제", "#EF4444", padding=(8, 15), radius=6,
                                              on_click=self.delete_selected)
        self.btn_delete_selected.setVisible(False)
        al.addWidget(self.btn_delete_selected)
        wrap.addWidget(actions)

        wrap_host.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        root.addWidget(wrap_host)
        root.addSpacing(7)

        # ---- 좌석 배치도 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; } QScrollArea > QWidget > QWidget { background:transparent; }")
        card = w.Card(bg="#FFFFFF", border="#E5E7EB", radius=8, padding=15)
        cl = card.vbox()
        grid_host = QWidget()
        self.grid = QGridLayout(grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setSpacing(0)
        for c, ratio in enumerate((10, 10, 10, 4, 10, 10, 10, 10)):
            self.grid.setColumnStretch(c, ratio)
        for r in range(9):
            self.grid.setRowMinimumHeight(r, 72)
        cl.addWidget(grid_host)
        cl.addStretch()
        scroll.setWidget(card)
        root.addWidget(scroll, 1)

        outer.addWidget(left, 1)
        outer.addWidget(self._build_memo_panel())

    def _build_memo_panel(self) -> QWidget:
        panel = w.Card(bg="#FFFFFF", border="#E5E7EB", radius=0, padding=15, sides="left")
        panel.setFixedWidth(320)
        lay = panel.vbox()
        lay.addWidget(w.label("메모", 16, bold=True, color="#1F2937"))
        lay.addSpacing(15)
        self.list_memos = QListWidget()
        self.list_memos.setStyleSheet("QListWidget { background:transparent; border:none; } QListWidget::item { border:none; }")
        self.list_memos.setSelectionMode(QListWidget.NoSelection)
        self.list_memos.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        lay.addWidget(self.list_memos, 1)
        lay.addSpacing(10)
        self.txt_memo = QTextEdit()
        self.txt_memo.setFixedHeight(60)
        self.txt_memo.setStyleSheet("QTextEdit { border:1px solid #D1D5DB; padding:2px; }")
        lay.addWidget(self.txt_memo)
        lay.addSpacing(8)
        self.btn_add_memo = w.flat_btn("+ 메모 추가", "#2563EB", padding=(8, 0), radius=4, on_click=self.add_memo)
        lay.addWidget(self.btn_add_memo)
        return panel

    # ------------------------------------------------------------------ 시즌
    def combo_season_key(self) -> str:
        return f"{self.combo_year.currentText()}_{self.combo_season.currentText()}"

    def sync_combos_to_season(self, season: tuple[int, str]):
        ys = str(season[0])
        if self.combo_year.findText(ys) < 0:
            self.combo_year.addItem(ys)
        self.combo_year.setCurrentText(ys)
        self.combo_season.setCurrentText(season[1])

    def update_season_info(self):
        cs = self.ctx.current_season
        self.lbl_season.setText(f"현재 시즌: {cs[0]}년 {cs[1]} (자동)" if cs else "현재 시즌: 설정된 시즌 없음")

    def load_dashboard_layout(self):
        key = self.combo_season_key()
        if key not in self.ctx.seat_cache:
            self.ctx.seat_cache[key] = [Seat(seat_number=i) for i in range(1, 53)]
            self.ctx.save_seat_cache()
        self.active_seats = self.ctx.seat_cache[key]
        self.render_seat_grid()
        self.update_season_info()

    def seat_by_number(self, num: int) -> Seat:
        return self.active_seats[num - 1]

    # ------------------------------------------------------------------ 그리기
    def render_seat_grid(self):
        if not self.active_seats:
            return
        if not self._cards:
            for n, r, c, span, gray in POSITIONS:
                cell = PillarCell() if n == -1 else SeatCard(self, n, gray)
                holder = QWidget()
                hl = QVBoxLayout(holder)
                hl.setContentsMargins(3, 3, 3, 3)
                hl.addWidget(cell)
                holder.setFixedHeight(72)
                self.grid.addWidget(holder, r, c, 1, span)
                if n != -1:
                    self._cards[n] = cell
        for card in self._cards.values():
            card.update()

    # ------------------------------------------------------------------ 메모
    def refresh_memos(self):
        self.list_memos.clear()
        for m in self.ctx.state.memos:
            row = QFrame()
            row.setObjectName("memoRow")
            row.setStyleSheet("QFrame#memoRow { border:none; border-bottom:1px solid #F3F4F6; background:transparent; }")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 8, 0, 8)
            h.setSpacing(0)
            h.addWidget(w.label("🔵 ", 12, color="#2563EB", icon=True), 0, Qt.AlignVCenter)
            txt = w.label(m.content, 12, color="#374151", wrap=True)
            h.addWidget(txt, 1)
            h.addSpacing(8)
            e = QLabel("✎")
            e.setCursor(Qt.PointingHandCursor)
            e.setStyleSheet("QLabel { color:#2563EB; font-weight:700; background:transparent; border:none; font-size:12px; }")
            e.mousePressEvent = lambda _ev, mm=m: self.edit_memo(mm)
            h.addWidget(e)
            h.addSpacing(4)
            x = QLabel("✕")
            x.setCursor(Qt.PointingHandCursor)
            x.setStyleSheet("QLabel { color:#EF4444; font-weight:700; background:transparent; border:none; font-size:12px; }")
            x.mousePressEvent = lambda _ev, mm=m: self.delete_memo(mm)
            h.addWidget(x)
            it = QListWidgetItem()
            row.setFixedWidth(270)
            it.setSizeHint(row.sizeHint())
            self.list_memos.addItem(it)
            self.list_memos.setItemWidget(it, row)

    def add_memo(self):
        text = self.txt_memo.toPlainText().strip()
        if self._editing_memo is not None:
            if text:
                self._editing_memo.content = text
            self._editing_memo = None
            self.txt_memo.clear()
            self.btn_add_memo.setText("+ 메모 추가")
        elif text:
            self.ctx.state.memos.append(MemoItem(content=text))
            self.txt_memo.clear()
        else:
            return
        self.ctx.save_app_state()
        self.refresh_memos()

    def edit_memo(self, memo: MemoItem):
        self._editing_memo = memo
        self.txt_memo.setPlainText(memo.content)
        self.btn_add_memo.setText("편집 완료")

    def delete_memo(self, memo: MemoItem):
        if memo in self.ctx.state.memos:
            self.ctx.state.memos.remove(memo)
        self.ctx.save_app_state()
        self.refresh_memos()

    # ------------------------------------------------------------------ 모드
    def toggle_mask(self):
        self.mask_info = not self.mask_info
        self.btn_mask.setText("🔓 정보 표시" if self.mask_info else "🔒 정보 가리기")
        self.render_seat_grid()

    def _fix_btn_style(self, active: bool):
        if active:
            self.btn_fix.setStyleSheet(self.btn_fix.styleSheet().replace("background:#FFFFFF", "background:#FEF08A"))
        else:
            self.btn_fix.setStyleSheet(self.btn_fix.styleSheet().replace("background:#FEF08A", "background:#FFFFFF"))

    def toggle_fix_mode(self):
        if self.delete_mode:
            self.delete_mode = False
            self.btn_delete_selected.setVisible(False)
            self.btn_delete_mode.setText("좌석 데이터 삭제")
        if not self.fix_mode:
            self.fix_mode = True
            self.btn_fix.setText("💾 고정 저장/종료")
            self._fix_btn_style(True)
            for s in self.active_seats:
                s.is_selected = False
        else:
            self.fix_mode = False
            self.btn_fix.setText("좌석 고정 모드")
            self._fix_btn_style(False)
            for s in self.active_seats:
                if s.is_selected:
                    if s.student is not None and "대학원" in s.student.department:
                        s.is_selected = False
                        continue
                    s.is_fixed = not s.is_fixed
                    s.is_selected = False
            self.ctx.save_seat_cache()
        self.render_seat_grid()

    def _delete_menu(self):
        if self.fix_mode:
            self.fix_mode = False
            self.btn_fix.setText("좌석 고정 모드")
            self._fix_btn_style(False)
        menu = QMenu(self)
        menu.addAction("선택 삭제 모드 토글", self.toggle_delete_mode)
        menu.addAction("전체 삭제", self.delete_all_seats)
        menu.exec(self.btn_delete_mode.mapToGlobal(QPoint(0, self.btn_delete_mode.height())))

    def toggle_delete_mode(self):
        if not self.delete_mode:
            self.delete_mode = True
            self.btn_delete_mode.setText("💾 선택 삭제 모드 활성 중")
        else:
            self.delete_mode = False
            self.btn_delete_mode.setText("좌석 데이터 삭제")
            self.btn_delete_selected.setVisible(False)
        for s in self.active_seats:
            s.is_selected = False
        self.render_seat_grid()

    def on_selection_changed(self):
        if self.delete_mode:
            self.btn_delete_selected.setVisible(any(s.is_selected for s in self.active_seats))

    def delete_selected(self):
        if not w.ask(self, "선택한 좌석들의 인적사항과 출석 데이터를 삭제하시겠습니까?", "확인"):
            return
        for s in self.active_seats:
            if s.is_selected:
                s.student = None
                s.is_selected = False
                s.is_fixed = False
        self.delete_mode = False
        self.btn_delete_mode.setText("좌석 데이터 삭제")
        self.btn_delete_selected.setVisible(False)
        self.ctx.save_seat_cache()
        self.render_seat_grid()

    def delete_all_seats(self):
        if not w.ask_warn(self, "모든 좌석의 인적 사항과 출석 데이터를 삭제하시겠습니까? (좌석 번호와 고정상태는 남음)", "경고"):
            return
        for s in self.active_seats:
            s.student = None
            s.is_selected = False
        self.ctx.save_seat_cache()
        self.render_seat_grid()

    # ------------------------------------------------------------------ 드래그
    def show_fixed_seat_popup(self):
        w.warn(self, "고정된 좌석은 이동하거나 교체할 수 없습니다.\n자리를 옮기려면 먼저 [좌석 고정 모드]에서 고정을 해제해 주세요.",
               "고정된 좌석")

    def handle_drop(self, src: int, dst: int):
        source, target = self.seat_by_number(src), self.seat_by_number(dst)
        if source is target or source.student is None:
            return
        if source.is_locked() or target.is_locked():
            self.show_fixed_seat_popup()
            return
        moving, occupant = source.student, target.student
        if occupant is not None:
            occ = occupant.name or occupant.student_id
            mov = moving.name or moving.student_id
            if not w.ask(self, f"{target.seat_number}번 좌석에는 {occ} 학생이 있습니다.\n{mov} 학생과 자리를 맞바꿀까요?", "좌석 맞바꾸기"):
                return
        source.student, target.student = occupant, moving
        self.ctx.mark_student_active(moving)
        self.ctx.mark_student_active(occupant)
        self.render_seat_grid()
        self.ctx.save_seat_cache()

    def open_seat_modal(self, seat: Seat):
        SeatDetailModal(self, seat).exec()

    # ------------------------------------------------------------------ 랜덤 배정
    def random_allocation(self):
        seats = self.active_seats
        current_ids = {s.student.student_id for s in seats if s.student}
        key = self.ctx.current_season_key()
        new_students = [m for m in self.ctx.state.master_students
                        if m.last_active_season == key and m.student_id not in current_ids]
        if new_students:
            empty = sorted([s for s in seats if s.student is None and not s.is_pillar and not (43 <= s.seat_number <= 52)],
                           key=lambda s: s.seat_number)
            if len(empty) < len(new_students):
                w.warn(self, "빈 좌석이 부족하여 추가 학생을 배치할 수 없습니다.")
                return
            targets = empty[max(0, len(empty) - len(new_students)):]
            shuffled = new_students[:]
            random.shuffle(shuffled)
            for stu, seat in zip(shuffled, targets):
                stu.last_active_season = key
                seat.student = stu.clone()
                if "대학원" in seat.student.department:
                    seat.is_fixed = True
            self.render_seat_grid()
            self.ctx.save_seat_cache()
            self.ctx.win.update_alert_badges()
            w.info(self, f"신규 등록 학생 {len(shuffled)}명이 빈 자리(뒷자리 우선)에 랜덤 배치되었습니다.", "신규 배치 완료")
            return

        unfixed = sorted([s for s in seats if not s.is_fixed and not s.is_pillar
                          and not (s.student and "대학원" in s.student.department)
                          and not (43 <= s.seat_number <= 52)], key=lambda s: s.seat_number)
        if len(unfixed) <= 1:
            w.warn(self, "고정되지 않은 좌석이 부족하여 배정할 수 없습니다.")
            return
        pool = [s.student for s in unfixed if s.student is not None]
        old_seat = {stu.student_id: next(i + 1 for i, s in enumerate(seats) if s.student is stu) for stu in pool}
        for s in unfixed:
            s.student = None
        targets = unfixed[max(0, len(unfixed) - len(pool)):]
        ok = False
        shuffled = pool[:]
        for _ in range(1000):
            shuffled = random.sample(pool, len(pool))
            violation = False
            for i, stu in enumerate(shuffled):
                o = old_seat.get(stu.student_id, 0)
                n = targets[i].seat_number
                if o in COORDS and n in COORDS:
                    (or_, oc), (nr, nc) = COORDS[o], COORDS[n]
                    if or_ == nr and abs(oc - nc) < 2:
                        violation = True
                        break
            if not violation:
                ok = True
                break
        if not ok:
            w.info(self, "수평 거리 제약조건(2칸 이상)을 맞출 수 없어 기본 랜덤 배정으로 진행합니다.", "참고")
            shuffled = random.sample(pool, len(pool))
        for seat, stu in zip(targets, shuffled):
            seat.student = stu
        self.render_seat_grid()
        self.ctx.save_seat_cache()

    # ------------------------------------------------------------------ 엑셀
    def export_excel(self):
        occupied = sorted([s for s in self.active_seats if s.student is not None], key=lambda s: s.seat_number)
        if not occupied:
            w.warn(self, "대시보드에 착석한 학생 정보가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "대시보드 학생 정보 엑셀 내보내기",
                                              f"대시보드_학생현황_{self.ctx.today:%Y%m%d}.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["좌석번호", "학번", "이름", "소속", "지도교수", "이메일", "고정여부"])
            for s in occupied:
                st = s.student
                ws.append([s.seat_number, st.student_id, st.name, st.department, st.advisor, st.email,
                           "고정" if s.is_fixed else "미고정"])
            wb.save(path)
            w.info(self, "좌석 학생 정보가 성공적으로 엑셀 파일로 저장되었습니다.", "내보내기 완료")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일 저장 중 오류가 발생했습니다: {ex}")

    def load_seat_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "좌석 데이터 불러오기 (상상Labs 입실신청 응답 — 스프레드시트에서 받은 CSV/엑셀)", "",
            "응답 시트 파일 (*.csv *.xlsx);;CSV 파일 (*.csv);;Excel 파일 (*.xlsx);;모든 파일 (*.*)")
        if not path:
            return
        try:
            imported = parse_sangsanglab_responses(path)
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
            return
        if not imported:
            w.warn(self, "불러올 학생 정보를 찾지 못했습니다.\n상상Labs 입실신청(응답) 시트 양식(타임스탬프·신청공간·소속·이름·학번·연락처·이메일·지도교수 열)의 CSV/엑셀 파일인지 확인해주세요.")
            return
        cs = self.ctx.current_season
        season_label = f"{cs[0]}년 {cs[1]}" if cs else "현재 시즌"
        if not w.ask(self, f"{season_label} 좌석 데이터를 불러온 명단 {len(imported)}명으로 교체합니다.\n고정된 좌석은 그대로 유지됩니다.\n\n계속하시겠습니까?",
                     "좌석데이터 불러오기"):
            return
        fixed_ids = {s.student.student_id for s in self.active_seats if s.is_fixed and s.student and s.student.student_id}
        queue = [st for st in imported if not st.student_id or st.student_id not in fixed_ids]
        placed = 0
        for seat in sorted(self.active_seats, key=lambda s: s.seat_number):
            if seat.is_pillar or seat.is_fixed:
                continue
            if not queue:
                seat.student = None
                continue
            st = queue.pop(0)
            seat.student = st
            if "대학원" in st.department:
                seat.is_fixed = True
            placed += 1
        self.render_seat_grid()
        self.ctx.save_seat_cache()

        added = updated = 0
        key = self.ctx.current_season_key()
        masters = self.ctx.state.master_students
        for st in imported:
            master = (next((m for m in masters if m.student_id == st.student_id), None) if st.student_id
                      else next((m for m in masters if m.name == st.name and m.email == st.email), None))
            if master is None:
                c = st.clone()
                c.last_active_season = key
                masters.append(c)
                added += 1
                continue
            master.last_active_season = key
            changed = False
            for attr in ("name", "department", "advisor", "email", "contact"):
                if not getattr(master, attr).strip() and getattr(st, attr).strip():
                    setattr(master, attr, getattr(st, attr))
                    changed = True
            if changed:
                updated += 1
        self.ctx.save_app_state()
        self.ctx.win.update_alert_badges()
        leftover = f"\n\n좌석 수보다 {len(queue)}명이 많아 배치되지 못했습니다." if queue else ""
        master_msg = f"\n학생 데이터: 신규 {added}명 추가" + (f", {updated}명 정보 보완" if updated else "")
        w.info(self, f"{season_label} 좌석에 {placed}명을 배치했습니다.{master_msg}{leftover}", "불러오기 완료")


def parse_sangsanglab_responses(path: str) -> list[StudentInfo]:
    """상상Labs 입실신청 응답 파일 (A 타임스탬프 / B 신청공간 / C 소속 / D 이름 / E 학번 / F 연락처 / G 이메일 / H 지도교수)."""
    table = ioimp.read_table(path)
    result: list[StudentInfo] = []
    seen: set[str] = set()
    for v in table:
        def cell(i):
            return ioimp.cell_str(ioimp.cell_at(v, i))
        space, dept, name, id_raw = cell(1), cell(2), cell(3), cell(4)
        contact = ioimp.normalize_phone(ioimp.cell_at(v, 5))
        email, advisor = cell(6), cell(7)
        if "이름을 작성" in name or "소속을 작성" in dept or "학번" in id_raw or "공간을 선택" in space:
            continue
        sid = ioimp.normalize_student_id(ioimp.cell_at(v, 4))
        if not name.strip() and not sid.strip():
            continue
        if space and "상상" not in space and "U301" not in space:
            continue
        if sid:
            if sid in seen:
                continue
            seen.add(sid)
        advisor = advisor.replace("교수님", "").replace("교수", "").strip()
        result.append(StudentInfo(student_id=sid, name=name, department=dept.strip() or "소프트웨어전공",
                                  email=email, contact=contact, advisor=advisor))
    return result


def _margin(widget: QWidget, left=0, top=0, right=0, bottom=0) -> QWidget:
    holder = QWidget()
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(left, top, right, bottom)
    lay.addWidget(widget)
    return holder
