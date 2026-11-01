"""
[데이터 관리] 화면 — C# 버전 TabDataManage 그대로.
제목/안내 → 검색 카드(검색어, 🔍 검색, 검색 초기화, 📥 엑셀 가져오기, 🎥 얼굴인식 출결 기록, 🗑️ 전체 삭제)
→ 학생 표 | 학생 정보 상세(300px).
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QFileDialog, QScrollArea,
)

from . import widgets as w
from . import io_import as ioimp
from . import face_integration, config
from .models import StudentInfo

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext


class DataManageTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self.selected: Optional[StudentInfo] = None
        self._build_ui()
        self.refresh_table()

    def _build_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        w.inset_background(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        root.addWidget(w.label("데이터 관리 (마스터 데이터베이스)", 18, bold=True, color="#111827"))
        root.addSpacing(4)
        root.addWidget(w.label("학생 정보는 시즌이 바뀌어도 지워지지 않고 계속 보관됩니다.", 12, color="#6B7280", wrap=True))
        root.addSpacing(15)

        bar = w.Card(padding=15)
        bl = bar.hbox()
        bl.addWidget(w.label("검색어 (학번/이름/지도교수): ", 13, weight=600, color="#374151"))
        bl.addSpacing(8)
        self.txt_search = QLineEdit()
        self.txt_search.setFixedWidth(200)
        self.txt_search.setStyleSheet("QLineEdit { padding:4px; }")
        self.txt_search.returnPressed.connect(self.refresh_table)
        bl.addWidget(self.txt_search)
        bl.addSpacing(10)
        bl.addWidget(w.action_btn("🔍 검색", padding=(6, 15), on_click=self.refresh_table))
        bl.addSpacing(5)
        bl.addWidget(w.action_btn("↻ 검색 초기화", padding=(6, 15), on_click=self._clear_search))
        bl.addSpacing(12)
        bl.addWidget(w.action_btn("📥 엑셀 가져오기", padding=(6, 15), on_click=self.import_excel))
        bl.addSpacing(8)
        bl.addWidget(w.action_btn("🎥 얼굴인식 출결 기록", padding=(6, 15), on_click=self.show_face_attendance))
        bl.addSpacing(8)
        bl.addWidget(w.action_btn("🗑️ 전체 삭제", padding=(6, 15), bg="#EF4444", fg="#FFFFFF", border="#DC2626",
                                  on_click=self.delete_all))
        bl.addStretch()
        root.addWidget(bar)
        root.addSpacing(15)

        main = w.Card(padding=15)
        ml = main.hbox()
        self.grid = w.DataGrid([
            w.Col("학번", 100, text=lambda s: s.student_id),
            w.Col("이름", 100, text=lambda s: s.name),
            w.Col("소속", 150, text=lambda s: s.department),
            w.Col("지도교수", 100, text=lambda s: s.advisor),
            w.Col("연락처", 120, text=lambda s: s.contact),
            w.Col("이메일", 150, text=lambda s: s.email),
        ], row_height=35)
        self.grid.item_selected.connect(self._on_selected)
        ml.addWidget(self.grid, 1)
        ml.addSpacing(15)

        side = w.Card(bg="#FFFFFF", border="#E5E7EB", radius=0, padding=(0, 0), sides="left")
        side.setFixedWidth(285)   # XAML ColumnDefinition Width=300 안에 Margin 15가 들어 있다
        sl = QVBoxLayout(side)
        sl.setContentsMargins(15, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; } QScrollArea > QWidget > QWidget { background:transparent; }")
        self.panel = QWidget()
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(0)
        pl.addWidget(w.label("학생 정보 상세", 14, bold=True, color="#374151"))
        pl.addSpacing(10)
        self.ed_id = self._field(pl, "학번")
        self.ed_name = self._field(pl, "이름")
        self.ed_dept = self._field(pl, "소속")
        self.ed_advisor = self._field(pl, "지도교수")
        self.ed_contact = self._field(pl, "연락처")
        self.ed_email = self._field(pl, "이메일", last=True)
        pl.addWidget(w.flat_btn("변경 사항 저장", "#10B981", padding=(8, 0), radius=0, on_click=self.save_selected))
        pl.addSpacing(8)
        pl.addWidget(w.flat_btn("마스터에서 삭제", "#EF4444", padding=(8, 0), radius=0, on_click=self.delete_selected))

        # 이 학생의 얼굴인식 출결 기록 (attendance.json, 학번으로 연결)
        pl.addSpacing(22)
        pl.addWidget(w.label("얼굴인식 출석", 14, bold=True, color="#374151"))
        pl.addSpacing(6)
        self.lbl_face_summary = w.label("", 11, color="#4B5563", wrap=True)
        pl.addWidget(self.lbl_face_summary)
        pl.addSpacing(8)
        self.grid_face = w.DataGrid([
            w.Col("날짜", 80, text=lambda r: r.date),
            w.Col("출근", 60, text=lambda r: r.check_in or ""),
            w.Col("퇴근", 60, text=lambda r: r.check_out or ""),
            w.Col("근무", stretch=True, text=lambda r: r.work_time_text),
        ], row_height=28, font_size=11)
        box = w.Card(bg="#FFFFFF", border="#E5E7EB", radius=0, padding=0)
        box.vbox().addWidget(self.grid_face)
        box.setFixedHeight(220)
        pl.addWidget(box)
        pl.addStretch()
        self.panel.setEnabled(False)
        scroll.setWidget(self.panel)
        sl.addWidget(scroll)
        ml.addWidget(side)
        root.addWidget(main, 1)

    @staticmethod
    def _field(layout: QVBoxLayout, caption: str, last: bool = False) -> QLineEdit:
        layout.addWidget(w.label(caption, 11, color="#6B7280"))
        layout.addSpacing(2)
        ed = QLineEdit()
        ed.setStyleSheet("QLineEdit { padding:4px; } QLineEdit:disabled { background:#F4F4F4; border-color:#ADB2B5; }")
        layout.addWidget(ed)
        layout.addSpacing(15 if last else 8)
        return ed

    # ------------------------------------------------------------------ 표
    def refresh_table(self):
        q = self.txt_search.text().strip().lower()
        view = [s for s in self.ctx.state.master_students
                if not q or q in s.student_id.lower() or q in s.name.lower()
                or q in s.advisor.lower() or q in s.department.lower()]
        self.grid.set_items(view)

    def _clear_search(self):
        self.txt_search.clear()
        self.refresh_table()

    def _on_selected(self, student: Optional[StudentInfo]):
        if student is None:
            self.panel.setEnabled(False)
            self._show_face_attendance(None)
            return
        self.selected = student
        self.ed_id.setText(student.student_id)
        self.ed_name.setText(student.name)
        self.ed_dept.setText(student.department)
        self.ed_advisor.setText(student.advisor)
        self.ed_contact.setText(student.contact)
        self.ed_email.setText(student.email)
        self.panel.setEnabled(True)
        self._show_face_attendance(student)

    def _show_face_attendance(self, student: Optional[StudentInfo]):
        """학생 상세 — 그 학생(학번)의 얼굴인식 출결 기록과 합계를 보여준다."""
        if student is None or not student.student_id.strip():
            self.grid_face.set_items([])
            self.lbl_face_summary.setText("")
            return
        records = face_integration.sort_latest_first(
            r for r in face_integration.load_attendance() if r.student_id == student.student_id)
        self.grid_face.set_items(records)
        self.lbl_face_summary.setText(face_integration.student_summary(records, self.ctx.today))

    # ------------------------------------------------------------------ 동작
    def save_selected(self):
        s = self.selected
        if s is None:
            return
        old_id, new_id = s.student_id, self.ed_id.text().strip()
        if not new_id:
            w.warn(self, "학번은 비워둘 수 없습니다.", "경고")
            return
        if old_id != new_id and any(m.student_id == new_id for m in self.ctx.state.master_students):
            w.warn(self, "이미 존재하는 학번입니다.", "경고")
            return
        s.student_id = new_id
        s.name = self.ed_name.text()
        s.department = self.ed_dept.text()
        s.advisor = self.ed_advisor.text()
        s.contact = self.ed_contact.text()
        s.email = self.ed_email.text()
        for layout in self.ctx.seat_cache.values():
            for seat in layout:
                if seat.student is not None and seat.student.student_id == old_id:
                    seat.student.student_id = new_id
                    seat.student.name, seat.student.department = s.name, s.department
                    seat.student.advisor, seat.student.contact, seat.student.email = s.advisor, s.contact, s.email
                    if "대학원" in seat.student.department:
                        seat.is_fixed = True
        self.refresh_table()
        self.ctx.win.dashboard.render_seat_grid()
        self.ctx.save_seat_cache()
        self.ctx.save_app_state()
        w.info(self, "마스터 데이터가 수정되었으며 즉시 대시보드에 데이터가 업데이트되었습니다.", "완료")

    def delete_selected(self):
        s = self.selected
        if s is None:
            return
        if not w.ask_warn(self, f"정말 {s.name} 학생을 마스터 데이터베이스에서 삭제하시겠습니까?", "삭제 확인"):
            return
        if s in self.ctx.state.master_students:
            self.ctx.state.master_students.remove(s)
        self.selected = None
        self.refresh_table()
        self.panel.setEnabled(False)
        self.ctx.save_app_state()
        w.info(self, "마스터 데이터가 삭제되었습니다. (기존 배치된 좌석 데이터는 유지됩니다.)", "완료")

    def delete_all(self):
        students = self.ctx.state.master_students
        if not students:
            w.warn(self, "삭제할 학생 정보가 없습니다.")
            return
        if not w.ask_warn(self, f"등록된 모든 학생 정보({len(students)}명)를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.", "전체 삭제 확인"):
            return
        students.clear()
        self.refresh_table()
        self.ctx.save_app_state()
        w.info(self, "모든 학생 정보가 삭제되었습니다.", "삭제 완료")

    def show_face_attendance(self):
        from .dialogs import FaceAttendanceModal
        FaceAttendanceModal(self, face_integration.load_attendance, config.attendance_path(), self.ctx.today).exec()

    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "마스터 학생 데이터베이스 가져오기", "",
                                              "학생 명단 (*.xlsx *.csv);;All Files (*.*)")
        if not path:
            return
        try:
            table = ioimp.read_table(path)
            header_row = -1
            for i in range(min(len(table), 5)):
                if any(("학번" in ioimp.cell_str(x) or "StudentId" in ioimp.cell_str(x)) for x in table[i]):
                    header_row = i
                    break
            c_id, c_name, c_dept, c_adv, c_contact, c_email = 0, 1, 2, 3, 4, 5
            if header_row >= 0:
                h = [ioimp.cell_str(x).lower() for x in table[header_row]]

                def find(*keys):
                    for i, t in enumerate(h):
                        if any(k.lower() in t for k in keys):
                            return i
                    return -1
                c_id = find("학번", "StudentId")
                c_name = find("이름", "Name")
                c_dept = find("소속", "학과", "Department")
                c_adv = find("지도", "Advisor")
                c_contact = find("연락처", "전화", "휴대", "Contact", "Phone")
                c_email = find("이메일", "메일", "Email")

            imported = updated = 0
            masters = self.ctx.state.master_students
            for row in table[header_row + 1:]:
                def cell(i):
                    return ioimp.cell_str(ioimp.cell_at(row, i))
                sid = ioimp.normalize_student_id(ioimp.cell_at(row, c_id))
                if not sid.strip() or not any(ch.isdigit() for ch in sid):
                    continue
                name, dept = cell(c_name), cell(c_dept)
                advisor = cell(c_adv).replace("교수님", "").replace("교수", "").strip()
                contact = ioimp.normalize_phone(ioimp.cell_at(row, c_contact))
                email = cell(c_email)
                existing = next((m for m in masters if m.student_id == sid), None)
                if existing is None:
                    masters.append(StudentInfo(student_id=sid, name=name, department=dept.strip() or "소프트웨어전공",
                                               advisor=advisor, contact=contact, email=email,
                                               last_active_season=self.ctx.current_season_key()))
                    imported += 1
                    continue
                changed = False
                for attr, val in (("name", name), ("department", dept), ("advisor", advisor), ("contact", contact), ("email", email)):
                    if not getattr(existing, attr).strip() and val:
                        setattr(existing, attr, val)
                        changed = True
                if changed:
                    updated += 1
            self.refresh_table()
            self.ctx.save_app_state()
            msg = f"학생 정보 {imported}명을 새로 등록했습니다."
            if updated:
                msg += f"\n기존 학생 {updated}명의 빈 항목(연락처 등)을 채웠습니다."
            w.info(self, msg, "가져오기 성공")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
