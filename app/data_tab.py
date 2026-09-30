"""
[데이터 관리] 탭 — 마스터 학생 데이터베이스.
C# 버전의 TabDataManage / BtnImportDataManageExcel_Click 등에 대응한다.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox, QFileDialog,
    QGroupBox, QFormLayout, QAbstractItemView, QSplitter,
)

from . import io_import as ioimp
from .models import StudentInfo

COLUMNS = ["학번", "이름", "소속", "지도교수", "연락처", "이메일"]


class DataManageTab(QWidget):
    students_changed = Signal()  # 좌석 탭 등에서 마스터 목록을 다시 참조하고 싶을 때 쓰라고 남겨둔다

    def __init__(self, students: list[StudentInfo], on_save):
        super().__init__()
        self.students = students          # main_window가 들고 있는 리스트를 그대로 공유한다
        self.on_save = on_save            # 변경될 때마다 디스크에 저장하도록 콜백
        self.selected: StudentInfo | None = None
        self._build_ui()
        self.refresh_table()

    # ---------------------------------------------------------------- UI
    def _build_ui(self):
        root = QVBoxLayout(self)

        title = QLabel("데이터 관리 (마스터 데이터베이스)")
        title.setStyleSheet("font-size:18px; font-weight:bold;")
        root.addWidget(title)
        info = QLabel("학생 정보는 시즌이 바뀌어도 지워지지 않고 계속 보관됩니다.")
        info.setStyleSheet("color:#6B7280; font-size:12px;")
        root.addWidget(info)

        # 검색 바
        search_bar = QHBoxLayout()
        search_bar.addWidget(QLabel("검색어 (학번/이름/지도교수):"))
        self.txt_search = QLineEdit()
        self.txt_search.setFixedWidth(220)
        self.txt_search.textChanged.connect(self.refresh_table)
        search_bar.addWidget(self.txt_search)

        btn_clear = QPushButton("검색 초기화")
        btn_clear.clicked.connect(lambda: self.txt_search.setText(""))
        search_bar.addWidget(btn_clear)

        btn_import = QPushButton("📥 엑셀/CSV 가져오기")
        btn_import.clicked.connect(self.import_excel)
        search_bar.addWidget(btn_import)

        btn_add = QPushButton("+ 새 학생")
        btn_add.clicked.connect(self.add_new_student)
        search_bar.addWidget(btn_add)

        search_bar.addStretch()

        btn_delete_all = QPushButton("🗑️ 전체 삭제")
        btn_delete_all.setStyleSheet("background:#EF4444; color:white; font-weight:bold;")
        btn_delete_all.clicked.connect(self.delete_all)
        search_bar.addWidget(btn_delete_all)
        root.addLayout(search_bar)

        # 표 + 상세 편집 패널
        splitter = QSplitter(Qt.Horizontal)

        self.table = QTableWidget(0, len(COLUMNS))
        self.table.setHorizontalHeaderLabels(COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.itemSelectionChanged.connect(self._on_row_selected)
        splitter.addWidget(self.table)

        panel = QGroupBox("학생 정보 상세")
        form = QFormLayout(panel)
        self.ed_id = QLineEdit()
        self.ed_name = QLineEdit()
        self.ed_dept = QLineEdit()
        self.ed_advisor = QLineEdit()
        self.ed_contact = QLineEdit()
        self.ed_email = QLineEdit()
        form.addRow("학번", self.ed_id)
        form.addRow("이름", self.ed_name)
        form.addRow("소속", self.ed_dept)
        form.addRow("지도교수", self.ed_advisor)
        form.addRow("연락처", self.ed_contact)
        form.addRow("이메일", self.ed_email)

        btn_row = QHBoxLayout()
        btn_save = QPushButton("변경 사항 저장")
        btn_save.setStyleSheet("background:#10B981; color:white; font-weight:bold;")
        btn_save.clicked.connect(self.save_selected)
        btn_del = QPushButton("마스터에서 삭제")
        btn_del.setStyleSheet("background:#EF4444; color:white; font-weight:bold;")
        btn_del.clicked.connect(self.delete_selected)
        btn_row.addWidget(btn_save)
        btn_row.addWidget(btn_del)
        form.addRow(btn_row)

        panel.setEnabled(False)
        self.panel = panel
        splitter.addWidget(panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)  # 표+상세 패널이 탭의 남는 세로 공간을 전부 채우게 한다

    # ------------------------------------------------------------ helpers
    def _filtered(self) -> list[StudentInfo]:
        q = self.txt_search.text().strip().lower()
        if not q:
            return self.students
        return [
            s for s in self.students
            if q in s.student_id.lower() or q in s.name.lower() or q in s.advisor.lower() or q in s.department.lower()
        ]

    def refresh_table(self):
        rows = self._filtered()
        self.table.setRowCount(len(rows))
        for r, s in enumerate(rows):
            values = [s.student_id, s.name, s.department, s.advisor, s.contact, s.email]
            for c, v in enumerate(values):
                item = QTableWidgetItem(v)
                item.setData(Qt.UserRole, s)
                self.table.setItem(r, c, item)

    def _on_row_selected(self):
        items = self.table.selectedItems()
        if not items:
            self.selected = None
            self.panel.setEnabled(False)
            return
        student: StudentInfo = items[0].data(Qt.UserRole)
        self.selected = student
        self.panel.setEnabled(True)
        self.ed_id.setText(student.student_id)
        self.ed_name.setText(student.name)
        self.ed_dept.setText(student.department)
        self.ed_advisor.setText(student.advisor)
        self.ed_contact.setText(student.contact)
        self.ed_email.setText(student.email)

    # ------------------------------------------------------------- CRUD
    def add_new_student(self):
        s = StudentInfo(student_id=f"NEW{len(self.students) + 1}")
        self.students.append(s)
        self.on_save()
        self.refresh_table()

    def save_selected(self):
        if self.selected is None:
            return
        new_id = self.ed_id.text().strip()
        if not new_id:
            QMessageBox.warning(self, "경고", "학번은 비워둘 수 없습니다.")
            return
        if new_id != self.selected.student_id and any(s.student_id == new_id for s in self.students):
            QMessageBox.warning(self, "경고", "이미 존재하는 학번입니다.")
            return

        self.selected.student_id = new_id
        self.selected.name = self.ed_name.text()
        self.selected.department = self.ed_dept.text()
        self.selected.advisor = self.ed_advisor.text()
        self.selected.contact = self.ed_contact.text()
        self.selected.email = self.ed_email.text()

        self.on_save()
        self.refresh_table()
        QMessageBox.information(self, "저장 완료", "학생 정보가 저장되었습니다.")

    def delete_selected(self):
        if self.selected is None:
            return
        res = QMessageBox.question(self, "삭제 확인", f"{self.selected.name or self.selected.student_id} 학생을 마스터에서 삭제할까요?")
        if res != QMessageBox.Yes:
            return
        self.students.remove(self.selected)
        self.selected = None
        self.panel.setEnabled(False)
        self.on_save()
        self.refresh_table()

    def delete_all(self):
        if not self.students:
            QMessageBox.information(self, "알림", "삭제할 학생 정보가 없습니다.")
            return
        res = QMessageBox.question(
            self, "전체 삭제 확인",
            f"등록된 모든 학생 정보({len(self.students)}명)를 삭제하시겠습니까? 되돌릴 수 없습니다.",
        )
        if res != QMessageBox.Yes:
            return
        self.students.clear()
        self.on_save()
        self.refresh_table()

    # -------------------------------------------------------------- import
    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "마스터 학생 데이터베이스 가져오기", "", "학생 명단 (*.xlsx *.csv)")
        if not path:
            return
        try:
            table = ioimp.read_table(path)
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
            return

        header_row = ioimp.find_header_row(table, ["학번"])
        col_id, col_name, col_dept, col_advisor, col_contact, col_email = 0, 1, 2, 3, 4, 5
        if header_row >= 0:
            header = [ioimp.cell_str(c) for c in table[header_row]]
            col_id = ioimp.find_col(header, "학번", "StudentId")
            col_name = ioimp.find_col(header, "이름", "성명", "Name")
            col_dept = ioimp.find_col(header, "소속", "학과", "Department")
            col_advisor = ioimp.find_col(header, "지도", "Advisor")
            col_contact = ioimp.find_col(header, "연락처", "전화", "휴대", "Contact", "Phone")
            col_email = ioimp.find_col(header, "이메일", "메일", "Email")

        imported = 0
        updated = 0
        for r in range(header_row + 1, len(table)):
            row = table[r]

            def cell(i):
                return ioimp.cell_str(ioimp.cell_at(row, i))

            sid = ioimp.normalize_student_id(ioimp.cell_at(row, col_id))
            if not sid or not any(ch.isdigit() for ch in sid):
                continue  # 학번이 없거나 숫자가 없으면 제목/안내 행

            name = cell(col_name)
            dept = cell(col_dept)
            advisor = cell(col_advisor).replace("교수님", "").replace("교수", "").strip()
            contact = ioimp.normalize_phone(ioimp.cell_at(row, col_contact))
            email = cell(col_email)

            existing = next((s for s in self.students if s.student_id == sid), None)
            if existing is None:
                self.students.append(StudentInfo(
                    student_id=sid, name=name,
                    department=dept or "소프트웨어전공",
                    advisor=advisor, contact=contact, email=email,
                ))
                imported += 1
                continue

            changed = False
            if not existing.name and name: existing.name = name; changed = True
            if not existing.department and dept: existing.department = dept; changed = True
            if not existing.advisor and advisor: existing.advisor = advisor; changed = True
            if not existing.contact and contact: existing.contact = contact; changed = True
            if not existing.email and email: existing.email = email; changed = True
            if changed:
                updated += 1

        self.on_save()
        self.refresh_table()
        msg = f"학생 정보 {imported}명을 새로 등록했습니다."
        if updated > 0:
            msg += f"\n기존 학생 {updated}명의 빈 항목(연락처 등)을 채웠습니다."
        QMessageBox.information(self, "가져오기 성공", msg)
