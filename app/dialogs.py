"""
C# 버전의 대화상자/모달을 그대로 옮긴 것.

- 별도 창(Window): EquipmentSelectionDialog, EquipmentIssueDialog, CabinetSelectionDialog,
  ExpiredCleanupDialog, CabinetExpiryWarningDialog, EquipmentExpiryWarningDialog
- 창 안 오버레이(Modal*): ApprovalHistoryModal, RentalHistoryModal, StudentSelectorModal, FaceAttendanceModal
"""
from __future__ import annotations

import datetime
import re
from typing import Callable, Optional

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QLineEdit, QDateEdit, QTextEdit,
    QCheckBox, QListWidget, QListWidgetItem, QWidget, QFrame, QGridLayout, QSizePolicy,
)

from . import theme, widgets as w
from . import face_integration as fi
from .constants import MAINFRAME_LABEL, LAPTOP_LABEL
from .models import RentalItem, EquipmentIssue, ApprovalRequest, StudentInfo


def _qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _date_edit(d: datetime.date, width: int = 180) -> QDateEdit:
    de = QDateEdit(_qdate(d))
    de.setCalendarPopup(True)
    de.setDisplayFormat("yyyy-MM-dd")
    de.setFixedWidth(width)
    return de


class _WpfWindow(QDialog):
    """WPF Window 대화상자 (흰 배경, 크기 고정, 부모 가운데)."""

    def __init__(self, parent, title: str, width: int, height: int = 0):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("QDialog { background:#FFFFFF; }")
        if height:
            self.setFixedSize(width, height)
        else:
            self.setFixedWidth(width)


def _row(text: str, label_width: int, widget: QWidget) -> QHBoxLayout:
    row = QHBoxLayout()
    row.setSpacing(0)
    lbl = w.label(text, 12, bold=True)
    lbl.setFixedWidth(label_width)
    row.addWidget(lbl)
    row.addWidget(widget)
    row.addStretch()
    return row


# ==================================================================== 기자재 선택
class EquipmentSelectionDialog(_WpfWindow):
    """기자재 승인 시 [대여 기자재 및 기간 선택]."""

    def __init__(self, parent, active_rentals: list[RentalItem], initial_phone: str, requested_type: str,
                 issues: list[EquipmentIssue], initial_due: Optional[datetime.date], initial_rental: datetime.date):
        super().__init__(parent, "대여 기자재 및 기간 선택", 350, 350)
        self._active = active_rentals
        self._issues = issues
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(10)

        self.type_combo = QComboBox()
        self.type_combo.setFixedWidth(180)
        self.type_combo.addItems([MAINFRAME_LABEL, LAPTOP_LABEL])
        rt = requested_type or ""
        laptop = any(k in rt for k in ("노트북", "Laptop", "OMEN"))
        self.type_combo.setCurrentText(LAPTOP_LABEL if laptop else MAINFRAME_LABEL)
        self.type_combo.setEnabled(False)
        lay.addLayout(_row("기자재 종류:", 100, self.type_combo))

        self.number_combo = QComboBox()
        self.number_combo.setFixedWidth(180)
        lay.addLayout(_row("기자재 번호:", 100, self.number_combo))

        self.phone = QLineEdit(initial_phone)
        self.phone.setFixedSize(180, 25)
        lay.addLayout(_row("연락처:", 100, self.phone))

        self.rental_date = _date_edit(initial_rental)
        lay.addLayout(_row("대여 시작일:", 100, self.rental_date))
        self.due_date = _date_edit(initial_due or (initial_rental + datetime.timedelta(days=7)))
        lay.addLayout(_row("반납 예정일:", 100, self.due_date))
        lay.addSpacing(10)

        btns = QHBoxLayout()
        btns.addStretch()
        self.ok = w.wpf_btn("대여 완료", 80, 30, bg="#10B981", fg="#FFFFFF", bold=True, on_click=self._ok)
        self.ok.setDefault(True)
        btns.addWidget(self.ok)
        btns.addSpacing(10)
        btns.addWidget(w.wpf_btn("취소", 80, 30, on_click=self.reject))
        lay.addLayout(btns)
        lay.addStretch()
        self._fill_numbers()

        self.selected_equipment_type = ""
        self.selected_unit_number = ""
        self.selected_phone = ""
        self.selected_rental_date = initial_rental
        self.selected_due_date = initial_rental

    def _fill_numbers(self):
        self.number_combo.clear()
        is_mainframe = "본체" in self.type_combo.currentText()
        max_count = 10 if is_mainframe else 20
        busy = set()
        for r in self._active:
            if r.is_mainframe == is_mainframe:
                m = re.search(r"\d+", r.unit_number)
                if m:
                    busy.add(int(m.group()))
        for i in self._issues:
            if ("본체" in i.equipment_name) == is_mainframe:
                busy.add(i.unit_number)
        for n in range(1, max_count + 1):
            if n not in busy:
                self.number_combo.addItem(f"No. {n}")
        if self.number_combo.count() > 0:
            self.number_combo.setCurrentIndex(0)
            self.ok.setEnabled(True)
        else:
            self.number_combo.addItem("사용 가능한 기자재 없음")
            self.ok.setEnabled(False)

    def _ok(self):
        num = self.number_combo.currentText()
        if not num or num == "사용 가능한 기자재 없음":
            w.warn(self, "대여 가능한 기자재가 없습니다.", "경고")
            return
        self.selected_equipment_type = self.type_combo.currentText()
        self.selected_unit_number = num
        self.selected_phone = self.phone.text().strip()
        self.selected_rental_date = self.rental_date.date().toPython()
        self.selected_due_date = self.due_date.date().toPython()
        self.accept()


# ==================================================================== 기자재 상태 등록
class EquipmentIssueDialog(_WpfWindow):
    NONE_LABEL = "선택 가능한 번호 없음 (대여 중 / 이미 등록됨)"

    def __init__(self, parent, active_rentals: list[RentalItem], issues: list[EquipmentIssue],
                 total_mainframes: int, total_laptops: int):
        super().__init__(parent, "기자재 상태 등록", 400)
        self._active = active_rentals
        self._issues = issues
        self._totals = (total_mainframes, total_laptops)
        self.selected_equipment_name = ""
        self.selected_unit_number = 0
        self.selected_issue_type = ""
        self.detail = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)
        root.setSizeConstraint(QVBoxLayout.SetFixedSize)

        self.equip_combo = QComboBox()
        self.equip_combo.setFixedWidth(250)
        self.equip_combo.addItems([MAINFRAME_LABEL, LAPTOP_LABEL])
        self.equip_combo.setCurrentIndex(-1)
        self.equip_combo.currentIndexChanged.connect(self._equip_changed)
        root.addLayout(_row("기자재 종류:", 90, self.equip_combo))
        root.addSpacing(12)

        self.number_combo = QComboBox()
        self.number_combo.setFixedWidth(250)
        self.number_combo.setEnabled(False)
        self.number_combo.currentIndexChanged.connect(self._number_changed)
        root.addLayout(_row("기자재 번호:", 90, self.number_combo))

        self.type_panel = QWidget()
        tp = QVBoxLayout(self.type_panel)
        tp.setContentsMargins(0, 18, 0, 0)
        tp.addWidget(w.label("상태를 고르세요", 12, bold=True, color="#374151"))
        tp.addSpacing(8)
        brow = QHBoxLayout()
        for text, color in (("고장", "#EF4444"), ("수리", "#F59E0B"), ("기타", "#6B7280")):
            b = w.wpf_btn(text, 95, 34, bg=color, fg="#FFFFFF", bold=True, on_click=lambda _=False, t=text: self._type_clicked(t))
            b.setStyleSheet(b.styleSheet().replace("border:1px solid #707070", "border:none"))
            brow.addWidget(b)
            brow.addSpacing(8)
        brow.addStretch()
        tp.addLayout(brow)
        self.type_panel.setVisible(False)
        root.addWidget(self.type_panel)

        self.etc_panel = QWidget()
        ep = QVBoxLayout(self.etc_panel)
        ep.setContentsMargins(0, 14, 0, 0)
        ep.addWidget(w.label("내용을 직접 적어 주세요", 12, bold=True, color="#374151"))
        ep.addSpacing(6)
        self.detail_box = QTextEdit()
        self.detail_box.setFixedHeight(60)
        ep.addWidget(self.detail_box)
        er = QHBoxLayout()
        er.addStretch()
        reg = w.wpf_btn("등록", 80, 28, bg="#2563EB", fg="#FFFFFF", bold=True, on_click=self._register_etc)
        er.addWidget(reg)
        ep.addSpacing(8)
        ep.addLayout(er)
        self.etc_panel.setVisible(False)
        root.addWidget(self.etc_panel)

        cr = QHBoxLayout()
        cr.addStretch()
        cr.addWidget(w.wpf_btn("취소", 80, 28, on_click=self.reject))
        root.addSpacing(14)
        root.addLayout(cr)

    def _equip_changed(self, _i):
        self.type_panel.setVisible(False)
        self.etc_panel.setVisible(False)
        self._fill_numbers()

    def _fill_numbers(self):
        self.number_combo.blockSignals(True)
        self.number_combo.clear()
        sel = self.equip_combo.currentText()
        if not sel:
            self.number_combo.setEnabled(False)
            self.number_combo.blockSignals(False)
            return
        is_mainframe = sel == MAINFRAME_LABEL
        max_count = self._totals[0] if is_mainframe else self._totals[1]
        busy = set()
        for r in self._active:
            if r.is_mainframe != is_mainframe:
                continue
            m = re.search(r"\d+", r.unit_number)
            if m:
                busy.add(int(m.group()))
        for i in self._issues:
            if ("본체" in i.equipment_name) == is_mainframe:
                busy.add(i.unit_number)
        for n in range(1, max_count + 1):
            if n not in busy:
                self.number_combo.addItem(f"No. {n}")
        if self.number_combo.count() == 0:
            self.number_combo.addItem(self.NONE_LABEL)
            self.number_combo.setCurrentIndex(0)
            self.number_combo.setEnabled(False)
        else:
            self.number_combo.setEnabled(True)
            self.number_combo.setCurrentIndex(-1)
        self.number_combo.blockSignals(False)

    def _number_changed(self, _i):
        picked = self.number_combo.currentIndex() >= 0 and self.number_combo.currentText() != self.NONE_LABEL
        self.type_panel.setVisible(picked)
        if not picked:
            self.etc_panel.setVisible(False)

    def _type_clicked(self, t: str):
        if t == "기타":
            self.etc_panel.setVisible(True)
            self.detail_box.setFocus()
            return
        self.etc_panel.setVisible(False)
        self.selected_issue_type = t
        self.detail = ""
        self._commit()

    def _register_etc(self):
        text = self.detail_box.toPlainText().strip()
        if not text:
            w.warn(self, "내용을 입력해 주세요.")
            self.detail_box.setFocus()
            return
        self.selected_issue_type = "기타"
        self.detail = text
        self._commit()

    def _commit(self):
        equip = self.equip_combo.currentText()
        if not equip:
            w.warn(self, "기자재 종류를 먼저 고르세요.")
            return
        m = re.search(r"\d+", self.number_combo.currentText())
        if self.number_combo.currentText() == self.NONE_LABEL or not m:
            w.warn(self, "기자재 번호를 먼저 고르세요.")
            return
        self.selected_equipment_name = "본체" if equip == MAINFRAME_LABEL else "노트북"
        self.selected_unit_number = int(m.group())
        self.accept()


# ==================================================================== 캐비닛 번호 선택
class CabinetSelectionDialog(_WpfWindow):
    def __init__(self, parent, allocations: dict, total: int, moving_from: int = 0):
        super().__init__(parent, "캐비닛 좌석 옮기기" if moving_from else "캐비닛 번호 배정", 340, 210 if moving_from else 180)
        self.selected_cabinet_number = -1
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(0)
        if moving_from:
            g = w.label(f"현재 {moving_from}번 → 옮길 번호를 고르세요.\n(비어 있는 번호만 보입니다)", 11, color="#6B7280", wrap=True)
            lay.addWidget(g)
            lay.addSpacing(12)
        self.combo = QComboBox()
        self.combo.setFixedWidth(150)
        for n in range(1, total + 1):
            if n not in allocations:
                self.combo.addItem(str(n), n)
        empty = self.combo.count() == 0
        if empty:
            self.combo.addItem("사용 가능한 캐비닛 없음", None)
        lay.addLayout(_row("캐비닛 번호 선택:", 110, self.combo))
        lay.addSpacing(20)
        btns = QHBoxLayout()
        btns.addStretch()
        ok = w.wpf_btn("여기로 옮기기" if moving_from else "배정 승인", 100 if moving_from else 80, 30,
                       bg="#10B981", fg="#FFFFFF", bold=True, on_click=self._ok)
        ok.setDefault(True)
        ok.setEnabled(not empty)
        btns.addWidget(ok)
        btns.addSpacing(10)
        btns.addWidget(w.wpf_btn("취소", 80, 30, on_click=self.reject))
        lay.addLayout(btns)
        lay.addStretch()

    def _ok(self):
        n = self.combo.currentData()
        if isinstance(n, int):
            self.selected_cabinet_number = n
            self.accept()
        else:
            w.warn(self, "올바른 캐비닛 번호를 선택해 주세요.", "경고")


# ==================================================================== 기간 만료 정리
class ExpiredCleanupDialog(_WpfWindow):
    def __init__(self, parent, scope: str, today: datetime.date, items: list[tuple[str, str]]):
        super().__init__(parent, f"{scope} 기간 만료 정리", 520)
        self.delete_confirmed = False
        self.selected_keys: list[str] = []
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)
        root.addWidget(w.label(f"⏰ {scope} — 기간이 지난 항목 {len(items)}건", 16, bold=True, color="#111827"))
        root.addSpacing(6)
        root.addWidget(w.label(f"기준일 {today:%Y-%m-%d} 보다 기간이 먼저 끝난 항목입니다. 삭제할 항목을 선택해 주세요.", 12, color="#6B7280", wrap=True))
        root.addSpacing(14)
        self.select_all = QCheckBox("전체 선택")
        self.select_all.setChecked(True)
        self.select_all.setStyleSheet("font-weight:700;")
        root.addWidget(self.select_all)
        root.addSpacing(8)
        self.lst = QListWidget()
        self.lst.setMaximumHeight(280)
        self.lst.setStyleSheet("QListWidget { border:1px solid #E5E7EB; background:#F9FAFB; }")
        self._boxes: list[tuple[QCheckBox, str]] = []
        for key, text in items:
            cb = QCheckBox(text)
            cb.setChecked(True)
            it = QListWidgetItem()
            self.lst.addItem(it)
            holder = QWidget()
            hl = QHBoxLayout(holder)
            hl.setContentsMargins(4, 4, 4, 4)
            hl.addWidget(cb)
            it.setSizeHint(holder.sizeHint())
            self.lst.setItemWidget(it, holder)
            self._boxes.append((cb, key))
        self.select_all.toggled.connect(lambda on: [cb.setChecked(on) for cb, _ in self._boxes])
        root.addWidget(self.lst)
        root.addSpacing(18)
        br = QHBoxLayout()
        br.addStretch()
        d = w.wpf_btn("선택 삭제", 100, 34, bg="#EF4444", fg="#FFFFFF", bold=True, on_click=self._delete)
        br.addWidget(d)
        br.addSpacing(8)
        k = w.wpf_btn("유지", 100, 34, bg="#6B7280", fg="#FFFFFF", bold=True, on_click=self.reject)
        k.setDefault(True)
        br.addWidget(k)
        root.addLayout(br)

    def _delete(self):
        self.selected_keys = [key for cb, key in self._boxes if cb.isChecked()]
        if not self.selected_keys:
            w.warn(self, "삭제할 항목을 최소 하나 이상 선택해 주세요.", "선택 확인")
            return
        self.delete_confirmed = True
        self.accept()


class _ExpiryWarningDialog(_WpfWindow):
    def __init__(self, parent, title: str, heading: str, sub: str, rows: list[tuple[str, str, int]], first_w: int):
        super().__init__(parent, title, 550)
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(0)
        root.addWidget(w.label(heading, 16, bold=True, color="#DC2626"))
        root.addSpacing(6)
        root.addWidget(w.label(sub, 12, color="#6B7280", wrap=True))
        root.addSpacing(14)
        lst = QListWidget()
        lst.setMaximumHeight(350)
        lst.setStyleSheet("QListWidget { border:1px solid #E5E7EB; background:#F9FAFB; }")
        for first, info, days in rows:
            if days < 0:
                status, color = f"만료 ({abs(days)}일 경과)", "#DC2626"
            elif days == 0:
                status, color = "오늘 만료 (D-Day)", "#D97706"
            else:
                status, color = f"{days}일 남음", "#2563EB"
            holder = QWidget()
            g = QHBoxLayout(holder)
            g.setContentsMargins(6, 4, 6, 4)
            a = w.label(first, 12, bold=True, color="#374151")
            a.setFixedWidth(first_w)
            b = w.label(info, 12, color="#4B5563")
            c = w.label(status, 12, bold=True, color=color)
            c.setFixedWidth(120)
            c.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            g.addWidget(a)
            g.addWidget(b, 1)
            g.addWidget(c)
            it = QListWidgetItem()
            it.setSizeHint(holder.sizeHint())
            lst.addItem(it)
            lst.setItemWidget(it, holder)
        root.addWidget(lst)
        root.addSpacing(16)
        br = QHBoxLayout()
        br.addStretch()
        close = w.wpf_btn("닫기", 100, 34, bg="#4F46E5", fg="#FFFFFF", bold=True, on_click=self.accept)
        close.setDefault(True)
        br.addWidget(close)
        root.addLayout(br)


def cabinet_expiry_warning(parent, today: datetime.date, items: list) -> None:
    rows = [(f"{n}번 캐비닛", f"{st.name if st else ''}({st.student_id if st else ''}) · {period}", days)
            for n, st, period, days in items]
    _ExpiryWarningDialog(parent, "캐비닛 대여 기간 만료/임박 안내",
                         f"⚠️ 캐비닛 대여 기간 만료 및 임박 ({len(items)}건)",
                         f"기준일: {today:%Y-%m-%d}\n대여 기간이 만료되었거나 7일 이하로 남은 캐비닛 목록입니다.",
                         rows, 80).exec()


def equipment_expiry_warning(parent, today: datetime.date, items: list) -> None:
    rows = [(r.equipment_type, f"{r.student_name}({r.student_id}) · {r.rental_date:%Y-%m-%d} ~ {r.due_date:%Y-%m-%d}", days)
            for r, days in items]
    _ExpiryWarningDialog(parent, "기자재 대여 기간 만료/임박 안내",
                         f"⚠️ 기자재 대여 기간 만료 및 임박 ({len(items)}건)",
                         f"기준일: {today:%Y-%m-%d}\n대여 기간이 만료되었거나 7일 이하로 남은 기자재 목록입니다.",
                         rows, 140).exec()


# ==================================================================== 오버레이 모달
def _modal_header(dlg: w.OverlayDialog, title: str, extra: Optional[QWidget] = None, plain_close: bool = False) -> QLabel:
    row = QHBoxLayout()
    t = w.label(title, 18, bold=True, color="#111827")
    row.addWidget(t)
    if extra is not None:
        row.addSpacing(15)
        row.addWidget(extra)
    row.addStretch()
    # XAML: 닫기 버튼은 제목 줄과 따로 오른쪽 위에 겹쳐 둔다(ZIndex) — 제목 줄 높이에 영향을 주지 않는다
    if plain_close:
        c = w.text_close_btn(20, padding=1, on_click=dlg.reject)
    else:
        c = w.icon_btn("✕", on_click=dlg.reject)
    dlg.float_top_right(c, top=dlg.padding, right=dlg.padding)
    dlg.body.addLayout(row)
    return t


def _grid_box(grid: QWidget) -> QFrame:
    box = w.Card(bg="#F9FAFB", border="#E5E7EB", radius=8, padding=0)
    lay = box.vbox()
    lay.setContentsMargins(1, 1, 1, 1)
    lay.addWidget(grid)
    return box


class ApprovalHistoryModal(w.OverlayDialog):
    """[📋 승인/반려 내역] — 버튼의 Tag(구분)만 보여준다. [되돌리기]로 대기 목록에 복구."""

    def __init__(self, owner, history: list[ApprovalRequest], scope: str, on_restore: Callable[[ApprovalRequest], bool]):
        super().__init__(owner, 900, 520)
        self._history = history
        self._scope = scope
        self._on_restore = on_restore
        _modal_header(self, f"{scope} 승인/반려 내역 확인" if scope else "승인/반려 내역 확인")
        self.body.addSpacing(20)
        self.grid = w.DataGrid([
            w.Col("구분", 70, text=lambda a: a.tab_type),
            w.Col("신청 일자", 120, text=lambda a: a.request_date.strftime("%Y-%m-%d %H:%M")),
            w.Col("학번", 85, text=lambda a: a.student_id),
            w.Col("이름", 75, text=lambda a: a.student_name),
            w.Col("소속", 130, text=lambda a: a.department),
            w.Col("상태", 80, text=lambda a: a.status),
            w.Col("대기 목록으로 복구", stretch=True, widget=lambda a: w.cell_wrap(
                w.modal_btn("되돌리기", bg="#3B82F6", padding=(4, 12), font_size=12,
                            on_click=lambda _=False, req=a: self._restore(req)),
                fill_width=True)),
        ], row_height=40)
        self.body.addWidget(_grid_box(self.grid), 1)
        self.refresh()

    def refresh(self):
        items = [a for a in self._history if not self._scope or a.tab_type == self._scope]
        self.grid.set_items(items)

    def _restore(self, req: ApprovalRequest):
        if self._on_restore(req):
            self.accept()


class RentalHistoryModal(w.OverlayDialog):
    def __init__(self, owner, history: list[RentalItem]):
        super().__init__(owner, 900, 520)
        _modal_header(self, "기자재 대여 내역 확인", plain_close=True)
        self.body.addSpacing(20)

        def returned(r: RentalItem):
            lbl = w.label("반납 완료" if r.is_returned else "대여 중", 12, bold=True,
                          color="#10B981" if r.is_returned else "#2563EB")
            return w.cell_wrap(lbl, Qt.AlignCenter)

        grid = w.DataGrid([
            w.Col("대여자 이름", 120, text=lambda r: r.student_name),
            w.Col("대여 기자재", 250, text=lambda r: r.display_equipment),
            w.Col("대여일", 130, text=lambda r: r.rental_date.strftime("%Y-%m-%d")),
            w.Col("반납 기한", 130, text=lambda r: r.due_date.strftime("%Y-%m-%d")),
            w.Col("반납 여부", stretch=True, widget=returned),
        ], row_height=40)
        grid.set_items(history)
        self.body.addWidget(_grid_box(grid), 1)


class FaceAttendanceModal(w.OverlayDialog):
    """[얼굴인식 출결 기록] — 기록 보기(검색·기간 필터)와 월간 기준 확인(주마다 20시간·3회) 두 화면."""

    def __init__(self, owner, load: Callable[[], list], path: str, today: datetime.date):
        super().__init__(owner, 920, 640)
        self._load = load
        self._path = path
        self._today = today
        self._all: list = []
        self._criteria_mode = False

        refresh = w.action_btn("🔄 새로고침", padding=(5, 12), on_click=self.refresh)
        self.btn_records = w.action_btn("📋 기록 보기", padding=(5, 12), weight=700, on_click=lambda: self._set_mode(False))
        self.btn_criteria = w.action_btn("✅ 월간 기준 확인", padding=(5, 12), weight=400, on_click=lambda: self._set_mode(True))
        views = QWidget()
        vl = QHBoxLayout(views)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.setSpacing(0)
        vl.addWidget(refresh)
        vl.addSpacing(15)
        vl.addWidget(self.btn_records)
        vl.addSpacing(6)
        vl.addWidget(self.btn_criteria)
        _modal_header(self, "얼굴인식 출결 기록", extra=views, plain_close=True)
        self.body.addSpacing(4)
        self.info = w.label("", 11, color="#6B7280", wrap=True)
        self.body.addWidget(self.info)
        self.body.addSpacing(12)

        # 필터 — 검색어(학번/이름) · 기간 · 빠른 기간 버튼. 바꾸면 바로 다시 걸러서 보여준다
        self.panel_records = w.Card(bg="#F9FAFB", border="#E5E7EB", radius=8, padding=(8, 12))
        pr = self.panel_records.hbox()
        pr.addWidget(_filter_caption("학번/이름"))
        pr.addSpacing(6)
        self.ed_search = _filter_input(self._apply_records)
        pr.addWidget(self.ed_search)
        pr.addSpacing(14)
        pr.addWidget(_filter_caption("기간"))
        pr.addSpacing(6)
        self.dp_from = _OptionalDate(self._apply_records)
        pr.addWidget(self.dp_from)
        pr.addWidget(w.label("  ~  ", 12, color="#6B7280"))
        self.dp_to = _OptionalDate(self._apply_records)
        pr.addWidget(self.dp_to)
        pr.addSpacing(10)
        for text, tag in (("오늘", "today"), ("이번 주", "week"), ("이번 달", "month"), ("전체", "all")):
            pr.addWidget(w.action_btn(text, padding=(4, 10), on_click=lambda _=False, t=tag: self._quick(t)))
            pr.addSpacing(4)
        pr.addStretch()
        self.body.addWidget(self.panel_records)

        # 월간 기준 확인 필터 — 월 · 결과 · 학번/이름
        self.panel_criteria = w.Card(bg="#F0FDF4", border="#BBF7D0", radius=8, padding=(8, 12))
        pv = self.panel_criteria.vbox()
        pc = QHBoxLayout()
        pc.setSpacing(0)
        pv.addLayout(pc)
        pc.addWidget(_filter_caption("월"))
        pc.addSpacing(6)
        self.cmb_month = QComboBox()
        self.cmb_month.setFixedWidth(110)
        self.cmb_month.currentIndexChanged.connect(self._apply_criteria)
        pc.addWidget(self.cmb_month)
        pc.addSpacing(14)
        pc.addWidget(_filter_caption("결과"))
        pc.addSpacing(6)
        self.cmb_result = QComboBox()
        self.cmb_result.setFixedWidth(110)
        self.cmb_result.setStyleSheet(f"QComboBox, QComboBox QAbstractItemView {{ font-family:{theme.ICON_FAMILIES}; }}")
        self.cmb_result.addItems(["전체", "✅ 충족", "❌ 미충족", "⏳ 진행 중"])
        self.cmb_result.currentIndexChanged.connect(self._apply_criteria)
        pc.addWidget(self.cmb_result)
        pc.addSpacing(14)
        pc.addWidget(_filter_caption("학번/이름"))
        pc.addSpacing(6)
        self.ed_criteria = _filter_input(self._apply_criteria)
        pc.addWidget(self.ed_criteria)
        pc.addStretch()
        rule = w.label(fi.criteria_rule_text(), 11, color="#166534")
        rule.setContentsMargins(14, 0, 0, 0)
        pv.addWidget(rule)
        self.body.addWidget(self.panel_criteria)
        self.body.addSpacing(10)

        # 합계 — 걸러진 기록 기준
        self.summary = w.label("", 13, weight=600, color="#111827", wrap=True, icon=True)
        self.summary.setContentsMargins(2, 0, 0, 0)
        self.body.addWidget(self.summary)
        self.body.addSpacing(10)

        self.grid = w.DataGrid([
            w.Col("학번", 110, text=lambda r: r.student_id),
            w.Col("이름", 90, text=lambda r: r.name),
            w.Col("날짜", 110, text=lambda r: r.date),
            w.Col("출근", 100, text=lambda r: r.check_in or ""),
            w.Col("퇴근", 100, text=lambda r: r.check_out or ""),
            w.Col("근무시간", stretch=True, min_width=100, text=lambda r: r.work_time_text),
        ], row_height=35)
        self.box_records = _grid_box(self.grid)
        self.body.addWidget(self.box_records, 1)

        # 주차 열은 달마다 수가 달라서(4~6주) 고를 때마다 표를 새로 만든다
        self.box_criteria = w.Card(bg="#F9FAFB", border="#E5E7EB", radius=8, padding=0)
        self.criteria_lay = self.box_criteria.vbox()
        self.criteria_lay.setContentsMargins(1, 1, 1, 1)
        self.grid_criteria: Optional[w.DataGrid] = None
        self.body.addWidget(self.box_criteria, 1)

        self.refresh()
        self._set_mode(False)

    def refresh(self):
        self._all = self._load()
        self.info.setText(
            f"얼굴인식 프로그램(insightface-attendance)이 기록한 출근/퇴근 시간입니다. 전체 {len(self._all)}건."
            if self._all else f"아직 기록된 출결 데이터가 없습니다. (파일 위치: {self._path})"
        )
        self._fill_months()
        if self._criteria_mode:
            self._apply_criteria()
        else:
            self._apply_records()

    def _set_mode(self, criteria: bool):
        self._criteria_mode = criteria
        self.panel_records.setVisible(not criteria)
        self.box_records.setVisible(not criteria)
        self.panel_criteria.setVisible(criteria)
        self.box_criteria.setVisible(criteria)
        # 지금 보고 있는 쪽 버튼을 강조한다
        for btn, on in ((self.btn_records, not criteria), (self.btn_criteria, criteria)):
            btn.setStyleSheet(re.sub(r"font-weight:\d+", f"font-weight:{700 if on else 400}", btn.styleSheet(), count=1))
        if criteria:
            self._apply_criteria()
        else:
            self._apply_records()

    # ---- 기록 보기 ----
    def _apply_records(self, *_):
        rows = fi.filter_records(self._all, self.ed_search.text(), self.dp_from.value(), self.dp_to.value())
        self.grid.set_items(rows)
        if not self._criteria_mode:
            self.summary.setText(fi.records_summary(rows))

    def _quick(self, tag: str):
        start, end = fi.quick_range(tag, self._today)
        self.dp_from.set_value(start)
        self.dp_to.set_value(end)
        self._apply_records()

    # ---- 월간 기준 확인 ----
    def _fill_months(self):
        current = self.cmb_month.currentText()
        months = fi.criteria_months(self._all, self._today)
        self.cmb_month.blockSignals(True)
        self.cmb_month.clear()
        self.cmb_month.addItems(months)
        self.cmb_month.setCurrentText(current if current in months else months[0])
        self.cmb_month.blockSignals(False)

    def _apply_criteria(self, *_):
        if not self._criteria_mode:
            return
        month_text = self.cmb_month.currentText()
        if not month_text:
            return
        year, month = int(month_text[:4]), int(month_text[5:7])
        weeks = fi.weeks_of_month(year, month)
        all_rows = fi.evaluate_month(self._all, year, month, self._today)
        kw = self.ed_criteria.text().strip().lower()
        wanted = {1: fi.PASSED, 2: fi.FAILED, 3: fi.IN_PROGRESS}.get(self.cmb_result.currentIndex())
        rows = [r for r in all_rows
                if (not kw or kw in r.student_id.lower() or kw in r.name.lower())
                and (wanted is None or r.state == wanted)]

        cols = [w.Col("학번", 95, text=lambda r: r.student_id), w.Col("이름", 75, text=lambda r: r.name)]
        for i, (start, end) in enumerate(weeks):
            cols.append(w.Col(f"{i + 1}주차\n{start.month}-{start.day}~{end.month}-{end.day}", stretch=True, min_width=95,
                              text=lambda r, idx=i: r.weeks[idx].text))
        cols.append(w.Col("결과", 130, text=lambda r: r.result_text))
        if self.grid_criteria is not None:
            self.criteria_lay.removeWidget(self.grid_criteria)
            self.grid_criteria.deleteLater()
        self.grid_criteria = w.DataGrid(cols, row_height=35, header_height=38)
        self.grid_criteria.cell_font.setFamilies(["Segoe UI", "Malgun Gothic", theme.ICON_FONT, "Segoe UI Symbol"])
        self.grid_criteria.set_items(rows)
        self.criteria_lay.addWidget(self.grid_criteria)
        self.summary.setText(fi.criteria_summary(month_text, all_rows, len(rows)))


def _filter_caption(text: str) -> QLabel:
    return w.label(text, 12, weight=600, color="#374151")


def _filter_input(on_change: Callable) -> QLineEdit:
    ed = QLineEdit()
    ed.setFixedWidth(130)
    ed.setStyleSheet("QLineEdit { padding:4px; }")
    ed.textChanged.connect(on_change)
    return ed


class _OptionalDate(QDateEdit):
    """WPF DatePicker처럼 날짜를 비워 둘 수 있는 입력칸 — 비어 있으면 그 쪽 기간을 따지지 않는다."""

    _EMPTY = QDate(2000, 1, 1)

    def __init__(self, on_change: Callable):
        super().__init__()
        self.setCalendarPopup(True)
        self.setFixedWidth(120)
        self.setMinimumDate(self._EMPTY)
        self.setSpecialValueText("날짜 선택")
        self.setDisplayFormat("yyyy-MM-dd")
        self.setDate(self._EMPTY)
        self.dateChanged.connect(on_change)

    def value(self) -> Optional[datetime.date]:
        return None if self.date() == self._EMPTY else self.date().toPython()

    def set_value(self, d: Optional[datetime.date]):
        self.blockSignals(True)
        self.setDate(_qdate(d) if d else self._EMPTY)
        self.blockSignals(False)


class StudentSelectorModal(w.OverlayDialog):
    """학생 선택 오버레이. 캐비닛에서 열면 소속 대신 대여 기간 열을 보여준다."""

    def __init__(self, owner, students: list[StudentInfo], for_cabinet: bool,
                 on_confirm: Callable[[Optional[StudentInfo]], bool]):
        super().__init__(owner, 550, 480, padding=30)
        self._students = students
        self._on_confirm = on_confirm
        _modal_header(self, "학생 선택")
        self.body.addSpacing(15)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setFixedHeight(35)
        self.search.setStyleSheet("QLineEdit { border:1px solid #D1D5DB; padding:5px 10px; }")
        self.search.textChanged.connect(self._filter)
        row.addWidget(self.search, 1)
        row.addSpacing(8)
        row.addWidget(w.action_btn("🔍 검색", padding=(6, 15), on_click=self._filter))
        self.body.addLayout(row)
        self.body.addSpacing(15)
        cols = [w.Col("학번", 120, text=lambda s: s.student_id), w.Col("이름", 100, text=lambda s: s.name)]
        if for_cabinet:
            cols.append(w.Col("대여 기간", 200, text=lambda s: s.cabinet_period))
        else:
            cols.append(w.Col("소속", 200, text=lambda s: s.department))
        self.grid = w.DataGrid(cols, row_height=35)
        self.grid.item_double_clicked.connect(lambda _s: self._confirm())
        self.body.addWidget(_grid_box(self.grid), 1)
        self.body.addSpacing(15)
        br = QHBoxLayout()
        br.addStretch()
        br.addWidget(w.modal_btn("선택", padding=(8, 20), on_click=self._confirm))
        br.addSpacing(8)
        br.addWidget(w.modal_btn("취소", bg="#F3F4F6", fg="#374151", padding=(8, 20), on_click=self.reject))
        self.body.addLayout(br)
        self._filter()

    def _filter(self):
        q = self.search.text().strip().lower()
        items = self._students if not q else [s for s in self._students if q in s.name.lower() or q in s.student_id.lower()]
        self.grid.set_items(items)

    def _confirm(self):
        if self._on_confirm(self.grid.current_item()):
            self.accept()
