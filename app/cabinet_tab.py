"""
[캐비닛 현황] 화면 — C# 버전 TabCabinet 그대로.

맨 위: 주황 알림 카드 … 🔍 검색 [📋 승인/반려 내역] [캐비닛 데이터 삭제] [캐비닛 데이터 추출] [📥 엑셀 가져오기]
캐비닛 신청 현황(구글폼) 표 → ◀ 1 / 2 ▶ → 8x3 캐비닛 칸(1~24 / 25~48) → 사용 가능/사용 중 카운터.
칸을 끌어 다른 칸에 놓으면 이동/맞교환, 끄는 중에 캐비닛 영역 밖 파란 영역에 머물면 다음/이전 페이지로 넘어간다.
"""
from __future__ import annotations

import datetime
import time
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QPoint, QMimeData, QRectF, QTimer, QDate, QRect
from PySide6.QtGui import QDrag, QColor, QPainter, QPen, QFont, QFontMetrics, QCursor, QPixmap, QTextOption
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QFileDialog, QDateEdit, QSizePolicy,
    QApplication,
)

from . import widgets as w
from . import approval_logic as al
from .constants import TOTAL_CABINETS, format_period, parse_period_dates
from .models import CabinetAllocation, StudentInfo, ApprovalRequest

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext

MIME_CABINET = "application/x-seatmanager-cabinet"
EDGE_DWELL_MS = 450
EDGE_WIDTH = 48


def _font(px: int, bold: bool = False) -> QFont:
    f = QFont("Segoe UI")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


# ====================================================================== 캐비닛 칸
class CabinetCell(QWidget):
    def __init__(self, tab: "CabinetTab", number: int):
        super().__init__()
        self.tab = tab
        self.number = number
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self._press: Optional[QPoint] = None
        self._drop = False
        self._dragging = False

    def paintEvent(self, e):
        t = self.tab
        alloc = t.ctx.state.cabinet_allocations.get(self.number)
        query = t.txt_search.text().strip().lower()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)   # Margin 2

        bg = QColor("#FFFFFF")
        border, bw, opacity = QColor("#E5E7EB"), 1.0, 1.0
        match = False
        if alloc is not None:
            bg = QColor("#EFF6FF")
            rng = parse_period_dates(alloc.period)
            if rng and (rng[1] - t.ctx.today).days <= 7:
                bg = QColor("#FEE2E2")
            stu = alloc.student
            if stu is not None:
                match = query in stu.name.lower() or query in stu.student_id.lower() or query in stu.department.lower()
        if query:
            if match:
                border, bw = QColor("#2563EB"), 2.0
            else:
                opacity = 0.2
        if self.number == t.highlighted:
            border, bw, opacity = QColor("#EA580C"), 3.0, 1.0
        if self._drop:
            border, bw, bg = QColor("#2563EB"), 3.0, QColor("#DBEAFE")
        if self._dragging:
            opacity = 0.3
        p.setOpacity(opacity)
        p.fillRect(r, bg)
        p.setPen(QPen(border, bw))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(bw / 2, bw / 2, -bw / 2, -bw / 2))

        inner = r.adjusted(bw + 5, bw + 5, -(bw + 5), -(bw + 5))
        if alloc is None or alloc.student is None:
            p.setFont(_font(20, True))
            p.setPen(QColor("#9CA3AF"))
            p.drawText(inner, Qt.AlignCenter, str(self.number))
            return

        stu = alloc.student
        lines = [(_font(15, True), "#6B7280", str(self.number), 0)]
        lines.append((_font(13), "#4B5563", stu.student_id, 3))
        lines.append((_font(15, True), "#1F2937", stu.name, 0))
        # 대여 기간(11px)은 칸이 좁으면 접는다
        f_period = _font(11)
        fm = QFontMetrics(f_period)
        period_rect = fm.boundingRect(QRect(0, 0, int(inner.width()), 1000), Qt.AlignHCenter | Qt.TextWordWrap, alloc.period)
        heights = [QFontMetrics(f).height() + top for f, _c, _t, top in lines]
        total = sum(heights) + period_rect.height() + 2
        y = inner.top() + (inner.height() - total) / 2
        for (f, color, text, top), h in zip(lines, heights):
            p.setFont(f)
            p.setPen(QColor(color))
            fmx = QFontMetrics(f)
            p.drawText(QRectF(inner.left(), y + top, inner.width(), h - top), Qt.AlignHCenter | Qt.AlignVCenter,
                       fmx.elidedText(text, Qt.ElideRight, int(inner.width())))
            y += h
        p.setFont(f_period)
        p.setPen(QColor("#6B7280"))
        opt = QTextOption(Qt.AlignHCenter)
        opt.setWrapMode(QTextOption.WordWrap)
        p.drawText(QRectF(inner.left(), y + 2, inner.width(), period_rect.height() + 2), alloc.period, opt)

    # ---------------------------------------------------------------- 마우스
    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._press = e.position().toPoint()

    def mouseMoveEvent(self, e):
        if self._press is None or not (e.buttons() & Qt.LeftButton):
            return
        if (e.position().toPoint() - self._press).manhattanLength() < QApplication.startDragDistance():
            return
        self._press = None
        if self.number not in self.tab.ctx.state.cabinet_allocations:
            return
        self.tab.start_drag(self)

    def mouseReleaseEvent(self, e):
        if self._press is not None:
            self._press = None
            self.tab.handle_cell_click(self.number)

    # ---------------------------------------------------------------- 드롭
    def _src(self, e) -> Optional[int]:
        if not e.mimeData().hasFormat(MIME_CABINET):
            return None
        return int(bytes(e.mimeData().data(MIME_CABINET)).decode())

    def dragEnterEvent(self, e):
        src = self._src(e)
        if src is None or src == self.number:
            e.ignore()
            return
        self._drop = True
        self.update()
        e.acceptProposedAction()

    def dragMoveEvent(self, e):
        e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._drop = False
        self.update()

    def dropEvent(self, e):
        src = self._src(e)
        self._drop = False
        self.update()
        if src is None:
            return
        e.acceptProposedAction()
        self.tab.handle_drop(src, self.number)


class EdgeZone(QWidget):
    """드래그 중에만 보이는 투명한 파란 영역 (#802563EB, 화살표)."""

    def __init__(self, arrow: str, left_side: bool):
        super().__init__()
        self.arrow = arrow
        self.left_side = left_side
        self.strong = False
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFixedWidth(EDGE_WIDTH)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setOpacity(1.0 if self.strong else 0.55)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(37, 99, 235, 128))
        p.drawRoundedRect(r, 8, 8)
        p.fillRect(r.adjusted(0 if self.left_side else 8, 0, -8 if self.left_side else 0, 0), QColor(37, 99, 235, 128))
        p.setPen(QPen(QColor("#2563EB"), 2))
        x = r.right() - 1 if self.left_side else r.left() + 1
        p.drawLine(int(x), 0, int(x), int(r.bottom()))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(_font(22))
        p.drawText(r, Qt.AlignCenter, self.arrow)


# ====================================================================== 캐비닛 상세 모달
class CabinetDetailModal(w.OverlayDialog):
    """C# ModalCabinetDetails (600x400)."""

    def __init__(self, tab: "CabinetTab", number: int, new_assign: bool):
        super().__init__(tab, 600, 400)
        self.tab = tab
        self.ctx = tab.ctx
        self.number = number
        self.editing = False

        head = QHBoxLayout()
        head.setSpacing(10)
        head.addStretch()
        self.btn_move = w.modal_btn("🔄 좌석 옮기기", padding=(8, 15), font_size=12, min_h=34, on_click=self._move)
        self.btn_select = w.modal_btn("학생선택", padding=(8, 15), font_size=12, min_h=34, on_click=self._select_student)
        self.btn_edit = w.modal_btn("정보 수정", bg="#F3F4F6", fg="#374151", padding=(8, 15), font_size=12, weight=600,
                                    min_h=34, min_w=86, on_click=lambda: self._set_edit(not self.editing))
        head.addWidget(self.btn_move)
        head.addWidget(self.btn_select)
        head.addWidget(self.btn_edit)
        head.addWidget(w.icon_btn("✕", size=34, on_click=self.reject))
        self.body.addLayout(head)
        self.body.addSpacing(10)

        self.title = w.label("", 18, bold=True, color="#111827")
        self.body.addWidget(self.title)
        self.body.addSpacing(20)

        grid = QGridLayout()
        grid.setContentsMargins(10, 0, 10, 0)
        grid.setColumnMinimumWidth(0, 120)
        grid.setVerticalSpacing(15)
        self.ed_name = self._field()
        self.ed_id = self._field()
        self.ed_period = self._field()
        grid.addWidget(w.label("이름 : ", 22, bold=True, color="#111827"), 0, 0)
        grid.addWidget(self.ed_name, 0, 1)
        grid.addWidget(w.label("학번 : ", 22, bold=True, color="#111827"), 1, 0)
        grid.addWidget(self.ed_id, 1, 1)
        grid.addWidget(w.label("대여 기간 : ", 22, bold=True, color="#111827"), 2, 0)
        period_host = QWidget()
        ph = QHBoxLayout(period_host)
        ph.setContentsMargins(0, 0, 0, 0)
        ph.addWidget(self.ed_period)
        self.picker = QWidget()
        pk = QHBoxLayout(self.picker)
        pk.setContentsMargins(0, 0, 0, 0)
        self.dp_start = self._date_edit()
        self.dp_end = self._date_edit()
        pk.addWidget(self.dp_start)
        pk.addWidget(w.label(" ~ ", 20, bold=True, color="#111827"))
        pk.addWidget(self.dp_end)
        pk.addStretch()
        ph.addWidget(self.picker)
        grid.addWidget(period_host, 2, 1)
        self.body.addStretch()
        self.body.addLayout(grid)
        self.body.addStretch()

        foot = QHBoxLayout()
        foot.addStretch()
        self.btn_save = w.modal_btn("저장", bg="#10B981", padding=(8, 20), min_h=36, min_w=86, on_click=self._save)
        foot.addWidget(self.btn_save)
        self.body.addSpacing(15)
        self.body.addLayout(foot)

        alloc = self.ctx.state.cabinet_allocations.get(number)
        if alloc is not None and not new_assign:
            self.title.setText(f"캐비닛 {number}번 상세 정보")
            self.ed_name.setText(alloc.student.name if alloc.student else "")
            self.ed_id.setText(alloc.student.student_id if alloc.student else "")
            self.ed_period.setText(alloc.period)
            self._set_edit(False)
        else:
            self.title.setText(f"캐비닛 {number}번 임의 배정")
            self.ed_period.setText(self.ctx.default_cabinet_period)
            self._set_edit(True)
            self.btn_move.setVisible(False)

    @staticmethod
    def _field() -> QLineEdit:
        ed = QLineEdit()
        return ed

    @staticmethod
    def _date_edit() -> QDateEdit:
        d = QDateEdit()
        d.setCalendarPopup(True)
        d.setDisplayFormat("yyyy-MM-dd")
        d.setFixedWidth(150)
        d.setStyleSheet("QDateEdit { font-size:16px; }")
        return d

    def _set_edit(self, on: bool):
        self.editing = on
        on_css = "QLineEdit { font-size:22px; font-weight:700; color:#111827; background:#FFFFFF; border:1px solid #ABADB3; }"
        off_css = "QLineEdit { font-size:22px; font-weight:700; color:#111827; background:transparent; border:none; }"
        for ed in (self.ed_name, self.ed_id, self.ed_period):
            ed.setReadOnly(not on)
            ed.setStyleSheet(on_css if on else off_css)
        self.btn_save.setVisible(on)
        self.btn_select.setVisible(on)
        has = self.number in self.ctx.state.cabinet_allocations
        self.btn_move.setVisible(not on and has)
        self.btn_edit.setText("취소" if on else "정보 수정")
        self.ed_period.setVisible(not on)
        self.picker.setVisible(on)
        if on:
            self._load_pickers()

    def _load_pickers(self):
        rng = self.ctx.parse_period_dates(self.ed_period.text()) or self.ctx.parse_period_dates(self.ctx.default_cabinet_period)
        start = rng[0] if rng else self.ctx.today
        end = rng[1] if rng else start + datetime.timedelta(days=30)
        self.dp_start.setDate(QDate(start.year, start.month, start.day))
        self.dp_end.setDate(QDate(end.year, end.month, end.day))

    def _save(self):
        name, sid = self.ed_name.text().strip(), self.ed_id.text().strip()
        if not name or not sid:
            w.warn(self, "모든 항목을 입력해 주세요.", "경고")
            return
        start, end = self.dp_start.date().toPython(), self.dp_end.date().toPython()
        if end < start:
            w.warn(self, "대여 종료일이 시작일보다 빠릅니다. 날짜를 다시 선택해 주세요.", "대여 기간")
            return
        period = format_period(start, end)
        allocs = self.ctx.state.cabinet_allocations
        existing = allocs.get(self.number)
        if existing and existing.student and existing.student.student_id == sid:
            student = existing.student
        else:
            m = next((x for x in self.ctx.state.master_students if x.student_id == sid), None)
            student = m.clone() if m else StudentInfo(student_id=sid, department="소프트웨어융합학과")
        student.name = name
        dup = next((n for n, a in allocs.items() if a.student and a.student.student_id == sid and n != self.number), 0)
        if dup:
            w.warn(self, f"해당 학번({sid})은 이미 {dup}번 캐비닛에 배정되어 있습니다. 중복 배정할 수 없습니다.", "배정 오류")
            return
        allocs[self.number] = CabinetAllocation(self.number, student, period)
        self.tab.render_grid()
        self.ctx.win.update_alert_badges()
        self.ctx.save_app_state()
        self.accept()
        w.info(self.tab, "캐비닛 정보가 저장되었습니다.", "저장 완료")

    def _move(self):
        from .dialogs import CabinetSelectionDialog
        allocs = self.ctx.state.cabinet_allocations
        src = self.number
        alloc = allocs.get(src)
        if alloc is None:
            return
        dlg = CabinetSelectionDialog(self, allocs, TOTAL_CABINETS, moving_from=src)
        dlg.setWindowTitle(f"캐비닛 {src}번 좌석 옮기기")
        if dlg.exec() != CabinetSelectionDialog.Accepted:
            return
        dst = dlg.selected_cabinet_number
        if dst <= 0 or dst == src:
            return
        del allocs[src]
        alloc.cabinet_num = dst
        allocs[dst] = alloc
        self.tab.highlighted = dst
        self.tab.page = 1 if dst <= 24 else 2
        self.tab.render_grid()
        self.ctx.win.update_alert_badges()
        self.ctx.save_app_state()
        self.accept()
        who = alloc.student.student_id if alloc.student and not alloc.student.name.strip() else \
            f"{alloc.student.name}({alloc.student.student_id})" if alloc.student else ""
        w.info(self.tab, f"{who} 학생의 좌석을 {src}번 → {dst}번으로 옮겼습니다.", "좌석 이동 완료")

    def _select_student(self):
        from .dialogs import StudentSelectorModal
        self.ctx.update_master_cabinet_periods()
        StudentSelectorModal(self, self.ctx.state.master_students, True, self._move_student_here).exec()

    def _move_student_here(self, selected: Optional[StudentInfo]) -> bool:
        if selected is None:
            w.warn(self, "배정할 학생을 먼저 선택하세요.", "경고")
            return False
        allocs = self.ctx.state.cabinet_allocations
        target = self.number
        src = next((n for n, a in allocs.items() if a.student and a.student.student_id == selected.student_id), 0)
        if src == target:
            w.info(self, f"{selected.name} 학생은 이미 {target}번 캐비닛을 쓰고 있습니다.")
            return True
        period = allocs[src].period if src else self.ctx.default_cabinet_period
        occupant = allocs.get(target)
        if occupant is not None:
            occ = "다른 학생" if occupant.student is None else (occupant.student.name or occupant.student.student_id)
            if src:
                ask = (f"{target}번은 {occ} 학생이 쓰고 있습니다.\n\n{selected.name}({src}번)와 자리를 맞바꿀까요?\n"
                       f"→ {selected.name}: {src}번 → {target}번 / {occ}: {target}번 → {src}번")
            else:
                ask = f"{target}번은 {occ} 학생이 쓰고 있습니다.\n\n{occ} 학생을 빼고 {selected.name} 학생을 넣을까요?"
            if not w.ask(self, ask, "캐비닛 사용 중"):
                return False
        if src:
            del allocs[src]
        if occupant is not None and src:
            occupant.cabinet_num = src
            allocs[src] = occupant
        allocs[target] = CabinetAllocation(target, selected.clone(), period)
        self.title.setText(f"캐비닛 {target}번 상세 정보")
        self.ed_name.setText(selected.name)
        self.ed_id.setText(selected.student_id)
        self.ed_period.setText(period)
        if self.editing:
            self._load_pickers()
        self.tab.highlighted = target
        self.tab.page = 1 if target <= 24 else 2
        self.tab.render_grid()
        self.ctx.win.update_alert_badges()
        self.ctx.save_app_state()
        done = (f"{selected.name} 학생을 {src}번 → {target}번 캐비닛으로 옮겼습니다." if src
                else f"{selected.name} 학생을 {target}번 캐비닛에 배정했습니다.")
        w.info(self, done, "캐비닛 배정 완료")
        return True


# ====================================================================== 화면
class CabinetTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self.page = 1
        self.highlighted = 0
        self._cells: dict[int, CabinetCell] = {}
        self._edge_since: Optional[float] = None
        self._edge_dir = 0
        self._build_ui()
        self.render_grid()
        self.refresh_approvals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("CabinetTab { background:#F9FAFB; }")
        # C#: 1340x785(+여백 20) 기준으로 만든 화면을 Viewbox로 감싸 창 크기에 맞춰 통째로 확대/축소한다
        self.content = QWidget()
        self.content.setObjectName("cabcontent")
        self.content.setAttribute(Qt.WA_StyledBackground, True)
        self.content.setStyleSheet("QWidget#cabcontent { background:#F9FAFB; }")
        self.content.setFixedSize(1380, 825)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.addWidget(w.ViewBox(self.content))
        outer = QVBoxLayout(self.content)
        outer.setContentsMargins(20, 20, 20, 20)
        outer.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(0)
        self.alert = w.orange_alert("캐비닛 승인 대기", on_click=lambda: self.ctx.win.switch_tab("equipment"))
        top.addWidget(self.alert, 0, Qt.AlignVCenter)
        top.addStretch()
        top.addWidget(w.label("🔍 검색: ", 12, weight=600, color="#374151", icon=True))
        top.addSpacing(5)
        self.txt_search = QLineEdit()
        self.txt_search.setFixedWidth(120)
        self.txt_search.setStyleSheet("QLineEdit { padding:4px; }")
        self.txt_search.textChanged.connect(self._search_changed)
        top.addWidget(self.txt_search)
        top.addSpacing(10)
        top.addWidget(w.action_btn("📋 승인/반려 내역", on_click=lambda: al.show_history(self.ctx, "캐비닛")))
        top.addSpacing(8)
        top.addWidget(w.action_btn("캐비닛 데이터 삭제", on_click=lambda: w.info(self, "캐비닛 데이터 삭제 기능 구현용 이벤트 핸들러입니다.", "캐비닛 삭제")))
        top.addSpacing(8)
        top.addWidget(w.action_btn("캐비닛 데이터 추출", on_click=self.export_excel))
        top.addSpacing(8)
        top.addWidget(w.action_btn("📥 엑셀 가져오기", on_click=self.import_excel))
        outer.addLayout(top)
        outer.addSpacing(20)

        outer.addWidget(w.label("캐비닛 신청 현황 (구글폼)", 16, bold=True, color="#111827"))
        outer.addSpacing(10)

        def approve_cells(a: ApprovalRequest):
            holder = QWidget()
            holder.setAttribute(Qt.WA_TranslucentBackground)
            h = QHBoxLayout(holder)
            h.setContentsMargins(0, 1, 0, 1)
            h.setSpacing(8)
            # WPF StackPanel(가로) 안의 버튼은 줄 높이만큼 위아래로 늘어난다
            for text, color, fn in (("승인", "#10B981", al.approve), ("반려", "#EF4444", al.reject)):
                b = w.flat_btn(text, color, padding=(4, 12), radius=4, on_click=lambda _=False, r=a, f=fn: f(self.ctx, r))
                b.setSizePolicy(b.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
                h.addWidget(b)
            h.addStretch()
            return holder

        self.grid_approvals = w.DataGrid([
            w.Col("신청 일자", 130, text=lambda a: a.request_date.strftime("%Y-%m-%d %H:%M")),
            w.Col("학번", 100, text=lambda a: a.student_id),
            w.Col("이름", 100, text=lambda a: a.student_name),
            w.Col("대여 기간", 150, text=lambda a: a.rental_period),
            w.Col("승인 처리", stretch=True, widget=approve_cells),
        ], row_height=40, alternating="#F3F4F6")
        card = w.Card(padding=10)
        card.vbox().addWidget(self.grid_approvals)
        card.setFixedHeight(160)
        outer.addWidget(card)
        outer.addSpacing(25)

        # ---- 페이지 넘김 ----
        pager = QHBoxLayout()
        pager.addStretch()
        prev = w.action_btn("◀", padding=(0, 0), weight=700, on_click=self.toggle_page)
        prev.setFixedSize(40, 40)
        nxt = w.action_btn("▶", padding=(0, 0), weight=700, on_click=self.toggle_page)
        nxt.setFixedSize(40, 40)
        self.lbl_page = w.label("1 / 2", 14, bold=True, color="#374151")
        self.lbl_page.setFixedWidth(60)
        self.lbl_page.setAlignment(Qt.AlignCenter)
        pager.addWidget(prev)
        pager.addSpacing(10)
        pager.addWidget(self.lbl_page)
        pager.addSpacing(10)
        pager.addWidget(nxt)
        pager.addStretch()
        outer.addLayout(pager)
        outer.addSpacing(10)

        # ---- 캐비닛 블록 (가장자리 파란 영역 포함) ----
        blocks = QHBoxLayout()
        blocks.setSpacing(0)
        blocks.addStretch()
        self.zone_left = EdgeZone("◀", True)
        self.zone_right = EdgeZone("▶", False)
        self.zone_left.setVisible(False)
        self.zone_right.setVisible(False)
        left_slot = QWidget()
        left_slot.setFixedWidth(52)
        ll = QHBoxLayout(left_slot)
        ll.setContentsMargins(0, 0, 4, 0)
        ll.addWidget(self.zone_left)
        right_slot = QWidget()
        right_slot.setFixedWidth(52)
        rl = QHBoxLayout(right_slot)
        rl.setContentsMargins(4, 0, 0, 0)
        rl.addWidget(self.zone_right)
        self.block = w.Card(bg="#FFFFFF", border="#D1D5DB", radius=8, padding=10)
        bl = QGridLayout(self.block)
        bl.setContentsMargins(10, 10, 10, 10)
        bl.setSpacing(0)
        self.block_grid = bl
        self.block.setFixedSize(922, 367)
        blocks.addWidget(left_slot)
        blocks.addWidget(self.block)
        blocks.addWidget(right_slot)
        blocks.addStretch()
        outer.addLayout(blocks)

        for i in range(24):
            cell = CabinetCell(self, 0)
            r, c = divmod(i, 8)
            bl.addWidget(cell, r, c)
            self._cells[i] = cell
        outer.addStretch()

        # ---- 하단 카운터 ----
        counters = QHBoxLayout()
        counters.addStretch()
        self.lbl_avail = self._counter("사용 가능한 캐비닛 : ")
        self.lbl_used = self._counter("사용 중인 캐비닛 : ")
        counters.addWidget(self.lbl_avail[0])
        counters.addSpacing(15)
        counters.addWidget(self.lbl_used[0])
        counters.addStretch()
        outer.addSpacing(10)
        outer.addLayout(counters)

        self._edge_timer = QTimer(self)
        self._edge_timer.setInterval(40)
        self._edge_timer.timeout.connect(self._edge_tick)

    def _counter(self, caption: str):
        box = w.Card(bg="#FFFFFF", border="#D1D5DB", radius=6, padding=(6, 15), border_width=1.5)
        h = box.hbox()
        h.addWidget(w.label(caption, 12, weight=600, color="#374151"))
        val = w.label("00개", 12, bold=True, color="#2563EB")
        h.addWidget(val)
        return box, val

    # ------------------------------------------------------------------ 표시
    @staticmethod
    def numbers_for_page(page: int) -> list[int]:
        base = 0 if page == 1 else 24
        return [base + c * 3 + r + 1 for r in range(3) for c in range(8)]

    def render_grid(self):
        for i, num in enumerate(self.numbers_for_page(self.page)):
            self._cells[i].number = num
            self._cells[i].update()
        self.lbl_page.setText(f"{self.page} / 2")
        n = len(self.ctx.state.cabinet_allocations)
        self.lbl_avail[1].setText(f"{max(0, TOTAL_CABINETS - n)}개")
        self.lbl_used[1].setText(f"{n}개")

    def toggle_page(self):
        self.page = 2 if self.page == 1 else 1
        self.render_grid()

    def _search_changed(self):
        self.highlighted = 0
        self.render_grid()

    def refresh_approvals(self):
        rows = [a for a in self.ctx.state.approvals if a.tab_type == "캐비닛"]
        self.alert.set_count(len(rows))
        self.grid_approvals.set_items(rows)

    # ------------------------------------------------------------------ 클릭
    def handle_cell_click(self, number: int):
        if self.highlighted:
            self.highlighted = 0
            self.render_grid()
        if number in self.ctx.state.cabinet_allocations:
            CabinetDetailModal(self, number, new_assign=False).exec()
        else:
            if w.ask(self, f"[캐비닛 {number}번] 사용 가능 (미배정) 상태입니다.\n이 캐비닛에 새로운 학생을 임의 배정하시겠습니까?", "캐비닛 배정"):
                CabinetDetailModal(self, number, new_assign=True).exec()

    # ------------------------------------------------------------------ 드래그
    def start_drag(self, cell: CabinetCell):
        drag = QDrag(cell)
        mime = QMimeData()
        mime.setData(MIME_CABINET, str(cell.number).encode())
        drag.setMimeData(mime)
        drag.setPixmap(QPixmap())
        cell._dragging = True
        cell.update()
        self._edge_since, self._edge_dir = None, 0
        self._show_zones(True)
        self._edge_timer.start()
        try:
            drag.exec(Qt.MoveAction)
        finally:
            self._edge_timer.stop()
            self._show_zones(False)
            cell._dragging = False
            for c in self._cells.values():
                c._drop = False
                c.update()

    def _show_zones(self, dragging: bool):
        for z in (self.zone_left, self.zone_right):
            z.strong = False
        self.zone_left.setVisible(dragging and self.page == 2)
        self.zone_right.setVisible(dragging and self.page == 1)

    def _edge_tick(self):
        cur = QCursor.pos()
        tl = self.block.mapToGlobal(QPoint(0, 0))
        br = self.block.mapToGlobal(QPoint(self.block.width(), self.block.height()))
        scale = max(0.01, (br.x() - tl.x()) / max(1, self.block.width()))
        left, right = tl.x(), br.x()
        top, bottom = tl.y() - 40 * scale, br.y() + 40 * scale
        gap = 4 * scale
        d = 0
        if top <= cur.y() <= bottom:
            if self.page == 1 and cur.x() >= right + gap:
                d = 1
            elif self.page == 2 and cur.x() <= left - gap:
                d = -1
        self.zone_left.strong = d < 0
        self.zone_right.strong = d > 0
        self.zone_left.update()
        self.zone_right.update()
        if d == 0:
            self._edge_since, self._edge_dir = None, 0
            return
        if self._edge_dir != d or self._edge_since is None:
            self._edge_dir, self._edge_since = d, time.monotonic()
            return
        if (time.monotonic() - self._edge_since) * 1000 >= EDGE_DWELL_MS:
            self.page = 2 if d > 0 else 1
            self.render_grid()
            self._show_zones(True)
            self._edge_since, self._edge_dir = None, 0

    def handle_drop(self, src: int, dst: int):
        allocs = self.ctx.state.cabinet_allocations
        if src == dst or src not in allocs:
            return
        moving = allocs[src]
        occupant = allocs.get(dst)
        if occupant is not None:
            mv = (moving.student.name or moving.student.student_id) if moving.student else ""
            occ = "다른 학생" if occupant.student is None else (occupant.student.name or occupant.student.student_id)
            if not w.ask(self, f"{dst}번 캐비닛은 {occ} 학생이 쓰고 있습니다.\n\n{mv}({src}번)과 자리를 맞바꿀까요?\n"
                               f"→ {mv}: {src}번 → {dst}번 / {occ}: {dst}번 → {src}번", "캐비닛 맞바꾸기"):
                return
            moving.cabinet_num, occupant.cabinet_num = dst, src
            allocs[src], allocs[dst] = occupant, moving
        else:
            del allocs[src]
            moving.cabinet_num = dst
            allocs[dst] = moving
        self.highlighted = dst
        self.page = 1 if dst <= 24 else 2
        self.render_grid()
        self.ctx.win.update_alert_badges()
        self.ctx.save_app_state()

    # ------------------------------------------------------------------ 엑셀
    def export_excel(self):
        allocs = self.ctx.state.cabinet_allocations
        if not allocs:
            w.warn(self, "추출할 캐비닛 배정 데이터가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "캐비닛 배정 현황 엑셀 추출",
                                              f"캐비닛_배정현황_{self.ctx.today:%Y%m%d}.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["캐비닛번호", "학번", "이름", "소속", "지도교수", "이메일", "대여기간"])
            for n in sorted(allocs):
                a = allocs[n]
                s = a.student
                ws.append([n, s.student_id if s else "", s.name if s else "", s.department if s else "",
                           s.advisor if s else "", s.email if s else "", a.period])
            wb.save(path)
            w.info(self, "캐비닛 배정 데이터가 성공적으로 엑셀 파일로 추출되었습니다.", "추출 완료")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일 저장 중 오류가 발생했습니다: {ex}")

    def import_excel(self):
        from . import io_import as ioimp
        path, _ = QFileDialog.getOpenFileName(self, "캐비닛 배정 현황 엑셀 가져오기", "", "Excel Files (*.xlsx);;All Files (*.*)")
        if not path:
            return
        try:
            table = ioimp.read_table(path)
            allocs = self.ctx.state.cabinet_allocations
            count = 0
            for v in table:
                if len(v) < 2:
                    continue
                c0 = ioimp.cell_str(v[0])
                if c0 in ("CabinetNumber", "캐비닛번호") or not c0:
                    continue
                try:
                    num = int(float(c0))
                except ValueError:
                    continue
                if num <= 0 or num > 48:
                    continue
                sid = ioimp.cell_str(ioimp.cell_at(v, 1))
                name = ioimp.cell_str(ioimp.cell_at(v, 2))
                dept = ioimp.cell_str(ioimp.cell_at(v, 3)) if len(v) > 3 else "소프트웨어융합학과"
                period = ioimp.cell_str(ioimp.cell_at(v, 4)) if len(v) > 4 else self.ctx.default_cabinet_period
                dup = next((n for n, a in allocs.items() if a.student and a.student.student_id == sid and n != num), 0)
                if dup:
                    del allocs[dup]
                allocs[num] = CabinetAllocation(num, StudentInfo(student_id=sid, name=name, department=dept), period)
                count += 1
            self.render_grid()
            self.ctx.win.update_alert_badges()
            self.ctx.save_app_state()
            w.info(self, f"엑셀 파일로부터 {count}개의 캐비닛 배정을 완료했습니다.", "가져오기 성공")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"엑셀 파일을 읽는 도중 오류가 발생했습니다: {ex}")
