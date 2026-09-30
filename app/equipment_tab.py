"""
[기자재 현황] 탭 — 본체(HP Z2 G9)·노트북(HP OMEN) 대여 현황 + 기자재 상태 관리(고장/수리/기타).
C# 버전의 BindEquipmentRentals / ImportEquipmentExcel / ExportEquipmentExcel /
BtnReturnEquipment_Click / EquipmentIssueDialog 등에 대응한다.
"""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QFileDialog, QDialog, QFormLayout, QComboBox, QSpinBox, QDateEdit,
    QTextEdit, QDialogButtonBox, QAbstractItemView, QGroupBox,
)

from . import io_import as ioimp
from .models import RentalItem, EquipmentIssue, StudentInfo, ApprovalRequest, SeasonConfig
from .constants import TOTAL_MAINFRAME, TOTAL_LAPTOP, MAINFRAME_LABEL, LAPTOP_LABEL
from .widgets import AlertChip

RENTAL_COLUMNS = ["상태", "수량", "대여자", "대여품목", "학번", "대여일", "반납예정", ""]


def _section_title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("font-size:16px; font-weight:bold; color:#111827; margin-top:8px; margin-bottom:4px;")
    return lbl


def today() -> datetime.date:
    return datetime.date.today()


class RentalDetailDialog(QDialog):
    """대여 상세/등록 모달 — 마스터에서 학생을 고르거나 직접 입력한다."""

    def __init__(self, parent, rental: RentalItem | None, is_mainframe: bool, master_students: list[StudentInfo]):
        super().__init__(parent)
        self.is_mainframe = is_mainframe
        self.setWindowTitle("대여 정보" if rental else "새 대여 등록")
        form = QFormLayout(self)

        self.combo_master = QComboBox()
        self.combo_master.addItem("(직접 입력)", None)
        for m in master_students:
            self.combo_master.addItem(f"{m.student_id} · {m.name}", m)
        self.combo_master.currentIndexChanged.connect(self._on_master_picked)
        form.addRow("마스터에서 선택", self.combo_master)

        self.ed_id = QLineEdit(rental.student_id if rental else "")
        self.ed_name = QLineEdit(rental.student_name if rental else "")
        self.ed_dept = QLineEdit(rental.department if rental else "소프트웨어전공")
        self.ed_year = QLineEdit(rental.year_level if rental else "3학년")
        self.ed_phone = QLineEdit(rental.phone if rental else "")
        self.ed_advisor = QLineEdit(rental.advisor if rental else "")
        form.addRow("학번", self.ed_id)
        form.addRow("이름", self.ed_name)
        form.addRow("전공", self.ed_dept)
        form.addRow("학년", self.ed_year)
        form.addRow("연락처", self.ed_phone)
        form.addRow("지도교수", self.ed_advisor)

        self.sp_unit = QSpinBox()
        self.sp_unit.setRange(0, 99)
        self.sp_unit.setSpecialValueText("(미지정)")
        self.sp_unit.setValue(int(rental.unit_number.replace("No. ", "")) if rental and rental.unit_number else 0)
        form.addRow("개체 번호", self.sp_unit)

        self.sp_qty = QSpinBox()
        self.sp_qty.setRange(1, 99)
        self.sp_qty.setValue(rental.quantity if rental else 1)
        form.addRow("수량", self.sp_qty)

        self.ed_extra = QLineEdit(rental.extra_items if rental else "")
        self.ed_loc = QLineEdit(rental.location if rental else "DSU 창의공간")
        self.ed_purpose = QLineEdit(rental.purpose if rental else "개인 실습")
        self.ed_remarks = QLineEdit(rental.remarks if rental else "")
        form.addRow("추가 대여물품", self.ed_extra)
        form.addRow("사용장소", self.ed_loc)
        form.addRow("사용목적", self.ed_purpose)
        form.addRow("특이사항", self.ed_remarks)

        self.dt_rental = QDateEdit(_to_qdate(rental.rental_date if rental else today()))
        self.dt_rental.setCalendarPopup(True)
        self.dt_rental.setDisplayFormat("yyyy-MM-dd")
        form.addRow("대여일", self.dt_rental)

        self.sp_period = QSpinBox()
        self.sp_period.setRange(1, 365)
        self.sp_period.setSuffix("일")
        self.sp_period.setValue(rental.rental_period_days if rental else 7)
        form.addRow("대여 기간", self.sp_period)

        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _on_master_picked(self, _idx: int):
        stu: StudentInfo | None = self.combo_master.currentData()
        if stu is not None:
            self.ed_id.setText(stu.student_id)
            self.ed_name.setText(stu.name)
            self.ed_dept.setText(stu.department)
            self.ed_phone.setText(stu.contact)
            self.ed_advisor.setText(stu.advisor)

    def build_rental(self) -> RentalItem:
        base = MAINFRAME_LABEL if self.is_mainframe else LAPTOP_LABEL
        equip = f"{base} (No. {self.sp_unit.value()})" if self.sp_unit.value() > 0 else base
        return RentalItem(
            student_id=self.ed_id.text().strip(),
            student_name=self.ed_name.text().strip(),
            department=self.ed_dept.text().strip(),
            year_level=self.ed_year.text().strip(),
            phone=self.ed_phone.text().strip(),
            advisor=self.ed_advisor.text().strip(),
            equipment_type=equip,
            quantity=self.sp_qty.value(),
            extra_items=self.ed_extra.text().strip(),
            location=self.ed_loc.text().strip(),
            purpose=self.ed_purpose.text().strip(),
            remarks=self.ed_remarks.text().strip(),
            rental_date=self.dt_rental.date().toPython(),
            rental_period_days=self.sp_period.value(),
        )


def _to_qdate(d: datetime.date):
    from PySide6.QtCore import QDate
    return QDate(d.year, d.month, d.day)


class IssueRegisterDialog(QDialog):
    """기자재 상태(고장/수리/기타) 등록 모달."""

    def __init__(self, parent, busy_mainframe: set[int], busy_laptop: set[int]):
        super().__init__(parent)
        self.setWindowTitle("기자재 상태 등록")
        self.busy = {"본체": busy_mainframe, "노트북": busy_laptop}
        self.total = {"본체": TOTAL_MAINFRAME, "노트북": TOTAL_LAPTOP}
        form = QFormLayout(self)

        self.combo_equip = QComboBox()
        self.combo_equip.addItems(["본체", "노트북"])
        self.combo_equip.currentTextChanged.connect(self._reload_numbers)
        form.addRow("기자재 종류", self.combo_equip)

        self.combo_num = QComboBox()
        form.addRow("기자재 번호", self.combo_num)
        self._reload_numbers(self.combo_equip.currentText())

        self.combo_type = QComboBox()
        self.combo_type.addItems(["고장", "수리", "기타"])
        self.combo_type.currentTextChanged.connect(self._toggle_detail)
        form.addRow("구분", self.combo_type)

        self.ed_detail = QTextEdit()
        self.ed_detail.setFixedHeight(70)
        self.ed_detail.setVisible(False)
        form.addRow("내용 (기타)", self.ed_detail)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._try_accept)
        btns.rejected.connect(self.reject)
        form.addRow(btns)

    def _reload_numbers(self, equip_name: str):
        self.combo_num.clear()
        busy = self.busy.get(equip_name, set())
        for i in range(1, self.total.get(equip_name, 0) + 1):
            if i not in busy:
                self.combo_num.addItem(f"No. {i}", i)
        if self.combo_num.count() == 0:
            self.combo_num.addItem("선택 가능한 번호 없음 (대여 중 / 이미 등록됨)", None)

    def _toggle_detail(self, issue_type: str):
        self.ed_detail.setVisible(issue_type == "기타")

    def _try_accept(self):
        if self.combo_num.currentData() is None:
            QMessageBox.warning(self, "알림", "등록할 수 있는 번호가 없습니다.")
            return
        if self.combo_type.currentText() == "기타" and not self.ed_detail.toPlainText().strip():
            QMessageBox.warning(self, "알림", "내용을 입력해 주세요.")
            return
        self.accept()

    def build_issue(self) -> EquipmentIssue:
        return EquipmentIssue(
            equipment_name=self.combo_equip.currentText(),
            unit_number=self.combo_num.currentData(),
            issue_type=self.combo_type.currentText(),
            detail=self.ed_detail.toPlainText().strip() if self.combo_type.currentText() == "기타" else "",
        )


class RentalHistoryDialog(QDialog):
    def __init__(self, parent, history: list[RentalItem]):
        super().__init__(parent)
        self.setWindowTitle("대여 이력")
        self.resize(700, 400)
        lay = QVBoxLayout(self)
        table = QTableWidget(len(history), 6)
        table.setHorizontalHeaderLabels(["대여자", "학번", "대여품목", "대여일", "반납예정", "반납일"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        for r, item in enumerate(sorted(history, key=lambda x: x.rental_date, reverse=True)):
            values = [
                item.student_name, item.student_id, item.display_equipment,
                item.rental_date.isoformat(), item.due_date.isoformat(),
                item.return_date.isoformat() if item.return_date else "",
            ]
            for c, v in enumerate(values):
                table.setItem(r, c, QTableWidgetItem(v))
        lay.addWidget(table)
        btns = QDialogButtonBox(QDialogButtonBox.Close)
        btns.rejected.connect(self.reject)
        btns.accepted.connect(self.accept)
        lay.addWidget(btns)


class EquipmentTab(QWidget):
    """
    C# 버전의 [기자재 현황](TabEquipment) 화면.
    위쪽 Section 1에 기자재 신청(구글폼) 승인 대기 + 기자재 상태 관리를 나란히 두고,
    아래쪽 Section 2에 본체/노트북 대여 현황을 나란히 둔다 — C# 버전과 같은 2단 구성이다.
    """

    def __init__(
        self,
        rentals: list[RentalItem],
        rental_history: list[RentalItem],
        issues: list[EquipmentIssue],
        master_students: list[StudentInfo],
        approvals: list[ApprovalRequest],
        approval_history: list[ApprovalRequest],
        season_config: SeasonConfig,
        on_save,
    ):
        super().__init__()
        self.rentals = rentals
        self.rental_history = rental_history
        self.issues = issues
        self.master_students = master_students
        self.approvals = approvals
        self.approval_history = approval_history
        self.season_config = season_config
        self.on_save = on_save
        self._undo_stack: list[RentalItem] = []

        self._build_ui()
        self.refresh()
        self.refresh_approvals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        bar = QHBoxLayout()
        self.chip = AlertChip("🕒", "기자재 승인 대기", "#FFEDD5", "#FED7AA", "#EA580C")
        bar.addWidget(self.chip)
        bar.addStretch()
        btn_history = QPushButton("📋 대여 내역")
        btn_history.clicked.connect(self.show_history)
        bar.addWidget(btn_history)
        btn_approval_history = QPushButton("📋 승인/반려 내역")
        btn_approval_history.clicked.connect(self.show_approval_history)
        bar.addWidget(btn_approval_history)
        bar.addWidget(QLabel("검색"))
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("대여자/학번/전공/품목")
        self.txt_search.setFixedWidth(160)
        self.txt_search.textChanged.connect(self.refresh)
        bar.addWidget(self.txt_search)
        self.btn_undo = QPushButton("↩ 반납 취소")
        self.btn_undo.clicked.connect(self.undo_return)
        self.btn_undo.setEnabled(False)
        bar.addWidget(self.btn_undo)
        root.addLayout(bar)

        # ---- Section 1: 기자재 신청 현황 (구글폼) | 기자재 상태 관리 ----
        sec1_titles = QHBoxLayout()
        sec1_titles.addWidget(_section_title("기자재 신청 현황 (구글폼)"), 2)
        issue_title_row = QHBoxLayout()
        issue_title_row.addWidget(_section_title("기자재 상태 관리 (고장/수리/기타)"))
        issue_title_row.addStretch()
        btn_add_issue = QPushButton("🛠️ 기타")
        btn_add_issue.clicked.connect(self.add_issue)
        issue_title_row.addWidget(btn_add_issue)
        sec1_titles.addLayout(issue_title_row, 1)
        root.addLayout(sec1_titles)

        sec1 = QHBoxLayout()
        self.approval_table = QTableWidget(0, 6)
        self.approval_table.setHorizontalHeaderLabels(["신청 일자", "학번", "이름", "대여품목", "반납예정일", ""])
        self.approval_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.approval_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.approval_table.setFixedHeight(180)
        sec1.addWidget(self.approval_table, 2)

        self.issue_table = QTableWidget(0, 4)
        self.issue_table.setHorizontalHeaderLabels(["등록일", "기기", "구분", "내용"])
        self.issue_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.issue_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.issue_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.issue_table.setFixedHeight(180)
        self.issue_table.cellDoubleClicked.connect(self._complete_issue)
        sec1.addWidget(self.issue_table, 1)
        root.addLayout(sec1)

        # ---- Section 2: 기자재 대여 현황 ----
        root.addWidget(_section_title("기자재 대여 현황"))
        cols = QHBoxLayout()
        self.mainframe_table, mf_box = self._build_section(True, "🖥️ " + MAINFRAME_LABEL + " 대여 현황", TOTAL_MAINFRAME)
        self.laptop_table, lt_box = self._build_section(False, "💻 " + LAPTOP_LABEL + " 대여 현황", TOTAL_LAPTOP)
        cols.addWidget(mf_box, 1)
        cols.addWidget(lt_box, 1)
        root.addLayout(cols, 1)

    # ------------------------------------------------------------ 승인 대기
    def refresh_approvals(self):
        rows = [a for a in self.approvals if a.tab_type == "기자재"]
        self.chip.set_count(len(rows))
        self.approval_table.setRowCount(len(rows))
        for r, req in enumerate(rows):
            due = req.due_date.isoformat() if req.due_date else ""
            values = [req.request_date.strftime("%Y-%m-%d %H:%M"), req.student_id, req.student_name, req.equipment_type, due]
            for c, v in enumerate(values):
                self.approval_table.setItem(r, c, QTableWidgetItem(v))

            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(0, 0, 0, 0)
            btn_ok = QPushButton("대여")
            btn_ok.setStyleSheet("background:#10B981; color:white;")
            btn_ok.clicked.connect(lambda _, req=req: self._approve(req))
            btn_no = QPushButton("반려")
            btn_no.setStyleSheet("background:#EF4444; color:white;")
            btn_no.clicked.connect(lambda _, req=req: self._reject(req))
            h.addWidget(btn_ok)
            h.addWidget(btn_no)
            self.approval_table.setCellWidget(r, 5, cell)

    def _ctx(self):
        from .approval_logic import ApprovalContext
        return ApprovalContext(
            self.master_students, {}, self.rentals, self.rental_history, self.approvals, self.approval_history,
            self.season_config, self.on_save, lambda title, msg: QMessageBox.warning(self, title, msg),
        )

    def _approve(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.approve(req, self._ctx())
        self.refresh_approvals()
        self.refresh()

    def _reject(self, req: ApprovalRequest):
        from . import approval_logic as al
        al.reject(req, self._ctx())
        self.refresh_approvals()

    def show_approval_history(self):
        from .approval_logic import ApprovalHistoryDialog
        ApprovalHistoryDialog(self, self.approval_history, "기자재").exec()

    def _build_section(self, is_mainframe: bool, title: str, total: int):
        box = QGroupBox()
        lay = QVBoxLayout(box)

        head = QHBoxLayout()
        lbl_title = QLabel(title)
        lbl_title.setStyleSheet("font-weight:bold;")
        head.addWidget(lbl_title)
        head.addStretch()
        counts = QLabel("")
        counts.setObjectName("mf_counts" if is_mainframe else "lt_counts")
        head.addWidget(counts)
        setattr(self, "_lbl_mf_counts" if is_mainframe else "_lbl_lt_counts", counts)
        lay.addLayout(head)

        btn_row = QHBoxLayout()
        btn_add = QPushButton("+ 새 대여 등록")
        btn_add.clicked.connect(lambda: self.add_rental(is_mainframe))
        btn_export = QPushButton("📤 엑셀 추출")
        btn_export.clicked.connect(lambda: self.export_excel(is_mainframe))
        btn_import = QPushButton("📥 엑셀/CSV 가져오기")
        btn_import.clicked.connect(lambda: self.import_excel(is_mainframe))
        for b in (btn_add, btn_export, btn_import):
            btn_row.addWidget(b)
        lay.addLayout(btn_row)

        table = QTableWidget(0, len(RENTAL_COLUMNS))
        table.setHorizontalHeaderLabels(RENTAL_COLUMNS)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.cellDoubleClicked.connect(lambda r, c, mf=is_mainframe: self._open_detail(mf, r))
        lay.addWidget(table)
        return table, box

    # --------------------------------------------------------------- refresh
    def _filtered(self) -> list[RentalItem]:
        q = self.txt_search.text().strip().lower()
        if not q:
            return self.rentals
        return [
            r for r in self.rentals
            if q in r.student_name.lower() or q in r.student_id.lower()
            or q in r.department.lower() or q in r.equipment_type.lower()
        ]

    def refresh(self):
        filtered = self._filtered()
        self._fill_table(self.mainframe_table, [r for r in filtered if r.is_mainframe], True)
        self._fill_table(self.laptop_table, [r for r in filtered if not r.is_mainframe], False)

        mf_rented = sum(1 for r in self.rentals if r.is_mainframe)
        lt_rented = sum(1 for r in self.rentals if not r.is_mainframe)
        self._lbl_mf_counts.setText(f"사용가능 {max(0, TOTAL_MAINFRAME - mf_rented)}개 · 사용중 {mf_rented}개")
        self._lbl_lt_counts.setText(f"사용가능 {max(0, TOTAL_LAPTOP - lt_rented)}개 · 사용중 {lt_rented}개")

        self.btn_undo.setEnabled(len(self._undo_stack) > 0)
        self._fill_issue_table()

    def _fill_table(self, table: QTableWidget, rows: list[RentalItem], is_mainframe: bool):
        table.setRowCount(len(rows))
        tday = today()
        for r, item in enumerate(rows):
            if item.is_overdue(tday):
                status, color = "연체됨", "#EF4444"
            elif item.is_warning(tday):
                status, color = "반납 임박", "#F59E0B"
            else:
                status, color = "대여중", "#10B981"

            values = [status, str(item.quantity), item.student_name, item.display_equipment,
                      item.student_id, item.rental_date.isoformat(), item.due_date.isoformat()]
            for c, v in enumerate(values):
                cell = QTableWidgetItem(v)
                cell.setData(Qt.UserRole, item)
                if c == 0:
                    cell.setForeground(_qcolor("#FFFFFF"))
                    cell.setBackground(_qcolor(color))
                table.setItem(r, c, cell)

            btn = QPushButton("반납")
            btn.setStyleSheet("background:#EF4444; color:white; font-weight:bold;")
            btn.clicked.connect(lambda _, it=item: self.return_rental(it))
            table.setCellWidget(r, len(RENTAL_COLUMNS) - 1, btn)

    def _fill_issue_table(self):
        # 줄을 더블클릭하면 [처리 완료]로 지울 수 있다 (_complete_issue, _build_ui에서 연결)
        self.issue_table.setRowCount(len(self.issues))
        for r, issue in enumerate(sorted(self.issues, key=lambda x: x.report_date, reverse=True)):
            values = [issue.report_date.strftime("%m-%d %H:%M"), issue.display_unit, issue.issue_type, issue.display_detail]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, issue)
                self.issue_table.setItem(r, c, item)

    def _complete_issue(self, row: int, _col: int):
        item = self.issue_table.item(row, 0)
        if item is None:
            return
        issue: EquipmentIssue = item.data(Qt.UserRole)
        res = QMessageBox.question(self, "처리 완료", f"[{issue.display_unit}] {issue.display_detail}\n\n처리 완료로 목록에서 지울까요?")
        if res == QMessageBox.Yes:
            self.issues.remove(issue)
            self.on_save()
            self.refresh()

    # ------------------------------------------------------------- actions
    def _open_detail(self, is_mainframe: bool, row: int):
        table = self.mainframe_table if is_mainframe else self.laptop_table
        item = table.item(row, 0)
        if item is None:
            return
        rental: RentalItem = item.data(Qt.UserRole)
        dlg = RentalDetailDialog(self, rental, is_mainframe, self.master_students)
        if dlg.exec() != QDialog.Accepted:
            return
        updated = dlg.build_rental()
        updated.id = rental.id
        idx = self.rentals.index(rental)
        self.rentals[idx] = updated
        self.on_save()
        self.refresh()

    def add_rental(self, is_mainframe: bool):
        dlg = RentalDetailDialog(self, None, is_mainframe, self.master_students)
        if dlg.exec() != QDialog.Accepted:
            return
        rental = dlg.build_rental()
        if not rental.student_id or not rental.student_name:
            QMessageBox.warning(self, "경고", "학번과 이름은 비워둘 수 없습니다.")
            return
        self.rentals.append(rental)
        self.rental_history.append(rental)
        self.on_save()
        self.refresh()

    def return_rental(self, rental: RentalItem):
        res = QMessageBox.question(self, "반납 확인", f"{rental.student_name}의 '{rental.equipment_type}' 반납 처리를 하시겠습니까?")
        if res != QMessageBox.Yes:
            return
        rental.is_returned = True
        rental.return_date = today()
        self.rentals.remove(rental)
        self._undo_stack.append(rental)
        self.on_save()
        self.refresh()

    def undo_return(self):
        if not self._undo_stack:
            return
        rental = self._undo_stack.pop()
        rental.is_returned = False
        rental.return_date = None
        self.rentals.append(rental)
        self.on_save()
        self.refresh()

    def show_history(self):
        RentalHistoryDialog(self, self.rental_history).exec()

    def add_issue(self):
        busy_mf, busy_lt = set(), set()
        for r in self.rentals:
            no = r.unit_number.replace("No. ", "")
            if no.isdigit():
                (busy_mf if r.is_mainframe else busy_lt).add(int(no))
        for i in self.issues:
            (busy_mf if i.equipment_name == "본체" else busy_lt).add(i.unit_number)

        dlg = IssueRegisterDialog(self, busy_mf, busy_lt)
        if dlg.exec() != QDialog.Accepted:
            return
        self.issues.insert(0, dlg.build_issue())
        self.on_save()
        self.refresh()

    # -------------------------------------------------------------- import/export
    def export_excel(self, is_mainframe: bool):
        target = [r for r in self.rentals if r.is_mainframe == is_mainframe]
        if not target:
            QMessageBox.warning(self, "알림", "추출할 대여 데이터가 없습니다.")
            return
        title = MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL
        path, _ = QFileDialog.getSaveFileName(
            self, f"{title} 대여 현황 엑셀 추출", f"{title}_{today():%Y%m%d}.xlsx", "Excel Files (*.xlsx)"
        )
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            headers = ["번호", "수량", "추가 대여물품(수량)", "사용장소", "사용목적", "특이사항",
                       "전공", "학년", "학번", "연락처", "지도교수", "성명", "대여일", "반납예정일", "반납일"]
            ws.append(headers)
            for i, item in enumerate(target, start=1):
                ws.append([
                    i, item.quantity, item.extra_items, item.location, item.purpose, item.remarks,
                    item.department, item.year_level, item.student_id, item.phone, item.advisor,
                    item.student_name, item.rental_date.isoformat(), item.due_date.isoformat(),
                    item.return_date.isoformat() if item.return_date else "",
                ])
            wb.save(path)
            QMessageBox.information(self, "추출 완료", "대여 데이터가 성공적으로 엑셀 파일로 추출되었습니다.")
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"파일 저장 중 오류가 발생했습니다: {ex}")

    def import_excel(self, is_mainframe: bool):
        target_label = MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL
        path, _ = QFileDialog.getOpenFileName(self, f"{target_label} 대여 현황 파일 가져오기", "", "대여 현황 파일 (*.xlsx *.csv)")
        if not path:
            return
        try:
            table = ioimp.read_table(path)
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
            return

        header_row = ioimp.find_header_row(table, ["학번"], max_rows=10)
        # "성명"/"이름"도 같이 있어야 진짜 헤더로 본다 (없으면 못 찾은 것으로 처리)
        if header_row >= 0:
            texts = [ioimp.cell_str(c) for c in table[header_row]]
            if not any(("성명" in t or "이름" in t) for t in texts):
                header_row = -1
        if header_row < 0:
            QMessageBox.warning(self, "알림", "학번·성명(이름) 열을 찾지 못했습니다. 대여 현황 양식의 파일인지 확인해주세요.")
            return

        header = [ioimp.cell_str(c) for c in table[header_row]]
        col_id = ioimp.find_col(header, "학번")
        col_name = ioimp.find_col(header, "성명", "이름")
        col_dept = ioimp.find_col(header, "전공", "학과", "소속")
        col_level = ioimp.find_col(header, "학년")
        col_phone = ioimp.find_col(header, "연락처", "전화")
        col_advisor = ioimp.find_col(header, "지도교수")
        col_equip = ioimp.find_col(header, "대여품목", "품목", "기자재")
        col_unit = ioimp.find_col(header, "품목번호", "개체번호")
        col_qty = ioimp.find_col(header, "수량")
        col_extra = ioimp.find_col(header, "추가 대여물품")
        col_loc = ioimp.find_col(header, "사용장소")
        col_purpose = ioimp.find_col(header, "사용목적")
        col_remarks = ioimp.find_col(header, "특이사항")
        col_rental_date = ioimp.find_col(header, "대여일", "대여날짜")
        col_due = ioimp.find_col(header, "반납예정")
        col_return = ioimp.find_col(header, "반납일")
        if col_return == col_due:
            col_return = -1

        imported, skipped_other = 0, 0
        for r in range(header_row + 1, len(table)):
            row = table[r]

            def cell(i):
                return ioimp.cell_str(ioimp.cell_at(row, i))

            sid = ioimp.normalize_student_id(ioimp.cell_at(row, col_id))
            name = cell(col_name)
            if not sid or not any(ch.isdigit() for ch in sid) or not name:
                continue

            equip_cell = cell(col_equip)
            if equip_cell:
                row_is_laptop = "노트북" in equip_cell
                if row_is_laptop == is_mainframe:
                    skipped_other += 1
                    continue

            dept = cell(col_dept)
            level = cell(col_level)
            if level and level.replace(".0", "").isdigit():
                level = level.replace(".0", "") + "학년"
            phone = ioimp.normalize_phone(ioimp.cell_at(row, col_phone))
            advisor = cell(col_advisor).replace("교수님", "").replace("교수", "").strip()

            qty_txt = cell(col_qty)
            qty = int(qty_txt) if qty_txt.isdigit() else 1
            extra = cell(col_extra)
            loc = cell(col_loc) or "DSU 창의공간"
            purpose = cell(col_purpose) or "개인 실습"
            remarks = cell(col_remarks)

            rental_date = _parse_date(cell(col_rental_date)) or today()
            due = _parse_date(cell(col_due))
            period = (due - rental_date).days if due else 7
            if period <= 0:
                period = 7
            ret = _parse_date(cell(col_return)) if col_return >= 0 else None

            equip_type = target_label
            unit_txt = cell(col_unit).replace(".0", "")
            if unit_txt.isdigit():
                equip_type = f"{target_label} (No. {unit_txt})"

            rental = RentalItem(
                student_id=sid, student_name=name, department=dept, year_level=level,
                phone=phone, advisor=advisor, equipment_type=equip_type,
                quantity=qty, extra_items=extra, location=loc, purpose=purpose, remarks=remarks,
                rental_date=rental_date, rental_period_days=period, return_date=ret, is_returned=ret is not None,
            )
            self.rentals.append(rental)
            self.rental_history.append(rental)
            imported += 1

        self.on_save()
        self.refresh()
        skip_msg = f"\n(다른 기자재 종류 {skipped_other}건은 건너뛰었습니다.)" if skipped_other else ""
        QMessageBox.information(self, "가져오기 성공", f"파일로부터 {imported}건의 기자재 대여 내역을 추가했습니다.{skip_msg}")


def _parse_date(s: str) -> datetime.date | None:
    if not s:
        return None
    s = s.strip()
    for fmt in ("%Y-%m-%d", "%Y.%m.%d", "%Y/%m/%d", "%y.%m.%d"):
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    # "2026-01-02 오후 03:04:05" 처럼 날짜만 앞에 있는 경우
    try:
        return datetime.date.fromisoformat(s[:10])
    except ValueError:
        return None


def _qcolor(hex_str: str):
    from PySide6.QtGui import QColor
    return QColor(hex_str)
