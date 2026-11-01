"""
[기자재 현황] 화면 — C# 버전 TabEquipment 그대로.

맨 위: 주황 알림 카드 + [📋 대여 내역] [📋 승인/반려 내역] 🔍 검색 [🗑️ 데이터 선택 삭제] [📄 데이터 양식 다운]
Section 1: 기자재 신청 현황(구글폼) | 기자재 상태 관리(고장/수리/기타) [🛠️ 기타]
Section 2: 기자재 대여 현황 — 본체(HP Z2 G9) | 노트북(HP OMEN)
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QFileDialog, QFrame,
)

from . import widgets as w
from . import approval_logic as al
from .logic import TEMPLATE_NAME, import_rentals
from .constants import TOTAL_MAINFRAME, TOTAL_LAPTOP, MAINFRAME_LABEL, LAPTOP_LABEL
from .models import RentalItem, EquipmentIssue, ApprovalRequest

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext


def _section(text: str) -> QLabel:
    return w.label(text, 16, bold=True, color="#111827")


class EquipmentTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self.undo_stack: list[RentalItem] = []
        self._build_ui()
        self.refresh_approvals()
        self.refresh_issues()
        self.bind_rentals()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        w.inset_background(self)
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(0)

        # ---- 맨 위 줄 ----
        top = QHBoxLayout()
        top.setSpacing(0)
        self.alert = w.orange_alert("기자재 승인 대기", on_click=lambda: self.ctx.win.switch_tab("equipment"))
        top.addWidget(self.alert, 0, Qt.AlignVCenter)
        top.addStretch()
        top.addWidget(w.action_btn("📋 대여 내역", on_click=self.show_rental_history))
        top.addSpacing(8)
        top.addWidget(w.action_btn("📋 승인/반려 내역", on_click=lambda: al.show_history(self.ctx, "기자재")))
        top.addSpacing(10)
        top.addWidget(w.label("🔍 검색: ", 12, weight=600, color="#374151", icon=True))
        top.addSpacing(5)
        self.txt_search = QLineEdit()
        self.txt_search.setFixedWidth(120)
        self.txt_search.setStyleSheet("QLineEdit { padding:4px; }")
        self.txt_search.textChanged.connect(self.bind_rentals)
        top.addWidget(self.txt_search)
        top.addSpacing(10)
        top.addWidget(w.action_btn("🗑️ 데이터 선택 삭제", on_click=self.delete_selected_rentals))
        top.addSpacing(6)
        top.addWidget(w.action_btn("📄 데이터 양식 다운", on_click=self.download_template))
        root.addLayout(top)
        root.addSpacing(20)

        # ---- Section 1 제목 ----
        s1 = QGridLayout()
        s1.setHorizontalSpacing(12)
        s1.setColumnStretch(0, 2)
        s1.setColumnStretch(1, 1)
        s1.addWidget(_section("기자재 신청 현황 (구글폼)"), 0, 0)
        issue_head = QHBoxLayout()
        issue_head.addWidget(_section("기자재 상태 관리 (고장/수리/기타)"))
        issue_head.addStretch()
        issue_head.addWidget(w.action_btn("🛠️ 기타", padding=(2, 10), font_size=11, on_click=self.add_issue))
        s1.addLayout(issue_head, 0, 1)

        # ---- Section 1 표 ----
        def approve_cell(a: ApprovalRequest):
            return w.cell_wrap(w.flat_btn("대여", "#10B981", padding=(4, 12), radius=4,
                                          on_click=lambda _=False, req=a: al.approve(self.ctx, req)),
                               margins=(0, 1, 0, 1), fill_height=True)

        self.grid_approvals = w.DataGrid([
            w.Col("신청 일자", 110, text=lambda a: a.request_date.strftime("%Y-%m-%d %H:%M")),
            w.Col("학번", 85, text=lambda a: a.student_id),
            w.Col("이름", 70, text=lambda a: a.student_name),
            w.Col("소속", 100, text=lambda a: a.department),
            w.Col("대여품목", 120, text=lambda a: a.equipment_type),
            w.Col("반납예정일", 90, text=lambda a: a.due_date.strftime("%Y-%m-%d") if a.due_date else ""),
            w.Col("지도교수", 85, text=lambda a: a.advisor),
            w.Col("상태", 65, text=lambda a: a.status),
            w.Col("대여 처리", stretch=True, min_width=80, widget=approve_cell),
        ], row_height=40, alternating="#F3F4F6")
        card1 = w.Card(padding=10)
        card1.vbox().addWidget(self.grid_approvals)

        def kind_badge(i: EquipmentIssue):
            bg = {"고장": "#FEE2E2", "수리": "#FEF3C7"}.get(i.issue_type, "#E5E7EB")
            lbl = QLabel(i.issue_type)
            lbl.setStyleSheet(f"QLabel {{ background:{bg}; color:#374151; font-weight:700; font-size:10px; border-radius:4px; padding:2px 6px; }}")
            return w.cell_wrap(lbl)

        def issue_details(i: EquipmentIssue):
            box = w.Card(bg="#F9FAFB", border="#E5E7EB", radius=6, padding=10)
            h = box.hbox()
            col = QVBoxLayout()
            col.addWidget(w.label(i.display_unit, 12, bold=True, color="#111827"))
            col.addSpacing(3)
            col.addWidget(w.label(i.display_detail, 12, color="#4B5563", wrap=True))
            h.addLayout(col, 1)
            h.addSpacing(10)
            h.addWidget(w.flat_btn("처리 완료", "#10B981", padding=(5, 12), radius=4,
                                   on_click=lambda _=False, iss=i: self.complete_issue(iss)), 0, Qt.AlignVCenter)
            return box

        self.grid_issues = w.DataGrid([
            w.Col("등록일", 80, text=lambda i: i.report_date.strftime("%m-%d %H:%M")),
            w.Col("기기", 95, text=lambda i: i.display_unit),
            w.Col("구분", 55, widget=kind_badge),
            w.Col("내용", stretch=True, min_width=80, text=lambda i: i.display_detail),
        ], row_height=34, alternating="#F3F4F6", font_size=11, details=issue_details)
        card2 = w.Card(padding=10)
        card2.vbox().addWidget(self.grid_issues)
        card1.setFixedHeight(200)
        card2.setFixedHeight(200)
        s1.addWidget(card1, 1, 0)
        s1.addWidget(card2, 1, 1)
        s1.setVerticalSpacing(10)
        root.addLayout(s1)
        root.addSpacing(15)

        # ---- Section 2 ----
        root.addWidget(_section("기자재 대여 현황"))
        root.addSpacing(10)
        cols = QHBoxLayout()
        cols.setSpacing(20)
        self.grid_mainframe, mf, self.lbl_mf = self._rental_column(True)
        self.grid_laptop, lt, self.lbl_lt = self._rental_column(False)
        cols.addWidget(mf, 1)
        cols.addWidget(lt, 1)
        root.addLayout(cols, 1)

    def _rental_column(self, is_mainframe: bool):
        col = QWidget()
        lay = QVBoxLayout(col)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        title = ("🖥️ " + MAINFRAME_LABEL + " 대여 현황") if is_mainframe else ("💻 " + LAPTOP_LABEL + " 대여 현황")
        head.addWidget(w.label(title, 14, bold=True, color="#374151", icon=True))
        head.addStretch()
        counts = QLabel()
        counts.setStyleSheet("QLabel { font-size:11px; background:transparent; }")
        counts.setTextFormat(Qt.RichText)
        head.addWidget(counts)
        head.addSpacing(10)
        btns = QVBoxLayout()
        btns.setSpacing(4)
        btns.addWidget(w.action_btn("📤 엑셀 추출", padding=(2, 10), font_size=11,
                                    on_click=lambda: self.export_excel(is_mainframe)))
        btns.addWidget(w.action_btn("📥 엑셀 가져오기", padding=(2, 10), font_size=11,
                                    on_click=lambda: self.import_excel(is_mainframe)))
        head.addLayout(btns)
        lay.addLayout(head)

        today = self.ctx.today

        def status_dot(r: RentalItem):
            color = "#EF4444" if r.is_overdue(today) else ("#F59E0B" if r.is_warning(today) else "#10B981")
            return w.cell_wrap(w.Dot(color), Qt.AlignCenter)

        def return_btn(r: RentalItem):
            return w.cell_wrap(w.flat_btn("반납", "#EF4444", padding=(2, 8), radius=4, font_size=11,
                                          on_click=lambda _=False, it=r: self.return_rental(it)), Qt.AlignCenter,
                               margins=(0, 1, 0, 1), fill_height=True)

        grid = w.DataGrid([
            w.Col("상태", 40, widget=status_dot),
            w.Col("수량", 45, text=lambda r: str(r.quantity)),
            w.Col("대여자", 65, text=lambda r: r.student_name),
            w.Col("대여품목", stretch=True, min_width=110, text=lambda r: r.display_equipment),
            w.Col("학번", 80, text=lambda r: r.student_id),
            w.Col("대여일", 80, text=lambda r: r.rental_date.strftime("%Y-%m-%d")),
            w.Col("반납예정", 80, text=lambda r: r.due_date.strftime("%Y-%m-%d")),
            w.Col("작업", 50, widget=return_btn),
        ], row_height=40, alternating="#F9FAFB", font_size=11, details=self._rental_details, multi_select=True)
        card = w.Card(padding=10)
        card.vbox().addWidget(grid)
        lay.addWidget(card, 1)
        return grid, col, counts

    @staticmethod
    def _rental_details(r: RentalItem) -> QWidget:
        box = w.Card(bg="#F9FAFB", border="#E5E7EB", radius=6, padding=12)
        g = QGridLayout(box)
        g.setContentsMargins(12, 12, 12, 12)
        g.setHorizontalSpacing(0)
        g.setVerticalSpacing(5)
        rows = [("전공 / 학년: ", f"{r.department} / {r.year_level}", "연락처 / 지도교수: ", f"{r.phone} / {r.advisor}"),
                ("사용 장소: ", r.location, "사용 목적: ", r.purpose),
                ("추가 물품: ", r.extra_items, "특이 사항: ", r.remarks)]
        for i, (a, b, c, d) in enumerate(rows):
            g.addWidget(w.label(a, 11, bold=True, color="#4B5563"), i, 0)
            vb = w.label(b, 11, color="#1F2937")
            g.addWidget(vb, i, 1)
            g.addWidget(w.label(c, 11, bold=True, color="#4B5563"), i, 2)
            g.addWidget(w.label(d, 11, color="#1F2937"), i, 3)
        g.setColumnStretch(1, 1)
        g.setColumnStretch(3, 1)
        g.setColumnMinimumWidth(1, 60)
        return box

    # ------------------------------------------------------------------ 바인딩
    def refresh_approvals(self):
        rows = [a for a in self.ctx.state.approvals if a.tab_type == "기자재"]
        self.alert.set_count(len(rows))
        self.grid_approvals.set_items(rows)

    def refresh_issues(self):
        self.grid_issues.set_items(list(self.ctx.state.equipment_issues))

    def bind_rentals(self):
        q = self.txt_search.text().strip().lower()
        rentals = [r for r in self.ctx.state.rentals
                   if not q or q in r.student_name.lower() or q in r.student_id.lower()
                   or q in r.department.lower() or q in r.equipment_type.lower()]
        self.grid_mainframe.set_items([r for r in rentals if r.is_mainframe])
        self.grid_laptop.set_items([r for r in rentals if not r.is_mainframe])
        mf = sum(1 for r in self.ctx.state.rentals if r.is_mainframe)
        lt = sum(1 for r in self.ctx.state.rentals if not r.is_mainframe)
        self.lbl_mf.setText(self._counts_html(TOTAL_MAINFRAME - mf, mf))
        self.lbl_lt.setText(self._counts_html(TOTAL_LAPTOP - lt, lt))

    @staticmethod
    def _counts_html(avail: int, used: int) -> str:
        return (f'<span style="color:#374151;font-weight:600">사용가능: </span>'
                f'<span style="color:#2563EB;font-weight:700">{max(0, avail)}개</span>&nbsp;&nbsp;'
                f'<span style="color:#374151;font-weight:600">사용중: </span>'
                f'<span style="color:#EF4444;font-weight:700">{used}개</span>')

    # ------------------------------------------------------------------ 동작
    def return_rental(self, rental: RentalItem):
        if not w.ask(self, f"{rental.student_name}의 '{rental.equipment_type}' 반납 처리를 하시겠습니까?", "반납 확인"):
            return
        rental.is_returned = True
        rental.return_date = self.ctx.today
        if rental in self.ctx.state.rentals:
            self.ctx.state.rentals.remove(rental)
        self.undo_stack.append(rental)
        self.ctx.save_app_state()
        self.ctx.win.update_alert_badges()
        self.bind_rentals()

    def show_rental_history(self):
        from .dialogs import RentalHistoryModal
        RentalHistoryModal(self, self.ctx.state.rental_history).exec()

    def delete_selected_rentals(self):
        selected = self.grid_mainframe.selected_items() + self.grid_laptop.selected_items()
        if not selected:
            w.warn(self, "삭제할 대여 데이터를 목록에서 먼저 선택해 주세요.")
            return
        if not w.ask_warn(self, f"선택한 {len(selected)}개의 대여 데이터를 삭제하시겠습니까?", "삭제 확인"):
            return
        for r in selected:
            if r in self.ctx.state.rentals:
                self.ctx.state.rentals.remove(r)
        self.ctx.save_app_state()
        self.bind_rentals()
        self.ctx.win.update_alert_badges()
        w.info(self, "선택한 대여 데이터가 삭제되었습니다.", "삭제 완료")

    def download_template(self):
        base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates = [os.path.join(base, "assets", TEMPLATE_NAME), os.path.join(base, "SpinnerApp", TEMPLATE_NAME),
                      os.path.join(os.getcwd(), "assets", TEMPLATE_NAME)]
        src = next((p for p in candidates if os.path.exists(p)), "")
        if not src:
            w.error(self, "기자재 대여 양식 파일을 찾을 수 없습니다. (SpinnerApp 폴더에 파일이 존재하는지 확인해 주세요)")
            return
        path, _ = QFileDialog.getSaveFileName(self, "기자재 대여 양식 다운로드", TEMPLATE_NAME, "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            shutil.copyfile(src, path)
            w.info(self, "기자재 대여 템플릿 양식 파일이 성공적으로 다운로드되었습니다.", "다운로드 완료")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일 저장 중 오류가 발생했습니다: {ex}")

    def add_issue(self):
        from .dialogs import EquipmentIssueDialog
        active = [r for r in self.ctx.state.rentals if not r.is_returned]
        dlg = EquipmentIssueDialog(self, active, list(self.ctx.state.equipment_issues), TOTAL_MAINFRAME, TOTAL_LAPTOP)
        if dlg.exec() != EquipmentIssueDialog.Accepted:
            return
        issue = EquipmentIssue(equipment_name=dlg.selected_equipment_name, unit_number=dlg.selected_unit_number,
                               issue_type=dlg.selected_issue_type, detail=dlg.detail)
        self.ctx.state.equipment_issues.insert(0, issue)
        self.ctx.save_app_state()
        self.refresh_issues()
        self.grid_issues.selectRow(0)

    def complete_issue(self, issue: EquipmentIssue):
        if not w.ask(self, f"[{issue.display_unit}] {issue.display_detail}\n\n처리 완료로 목록에서 지울까요?", "처리 완료"):
            return
        if issue in self.ctx.state.equipment_issues:
            self.ctx.state.equipment_issues.remove(issue)
        self.ctx.save_app_state()
        self.refresh_issues()

    # ------------------------------------------------------------------ 엑셀
    def export_excel(self, is_mainframe: bool):
        title = f"{MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL} 대여 현황"
        target = [r for r in self.ctx.state.rentals if r.is_mainframe == is_mainframe]
        if not target:
            w.warn(self, "추출할 대여 데이터가 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, f"{title} 엑셀 추출", f"{title}_{self.ctx.today:%Y%m%d}.xlsx", "Excel Files (*.xlsx)")
        if not path:
            return
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.append(["번호", "수량", "추가 대여물품(수량)", "사용장소", "사용목적", "특이사항", "전공", "학년", "학번",
                       "연락처", "지도교수", "성명", "대여일", "반납예정일", "반납일"])
            for i, r in enumerate(target, 1):
                ws.append([i, r.quantity, r.extra_items, r.location, r.purpose, r.remarks, r.department, r.year_level,
                           r.student_id, r.phone, r.advisor, r.student_name, r.rental_date.isoformat(),
                           r.due_date.isoformat(), r.return_date.isoformat() if r.return_date else ""])
            wb.save(path)
            w.info(self, "대여 데이터가 성공적으로 엑셀 파일로 추출되었습니다.", "추출 완료")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일 저장 중 오류가 발생했습니다: {ex}")

    def import_excel(self, is_mainframe: bool):
        target_label = MAINFRAME_LABEL if is_mainframe else LAPTOP_LABEL
        path, _ = QFileDialog.getOpenFileName(self, f"{target_label} 대여 현황 파일 가져오기", "",
                                              "대여 현황 파일 (*.xlsx *.csv);;All Files (*.*)")
        if not path:
            return
        try:
            imported, skipped = import_rentals(path, target_label, is_mainframe, self.ctx.today)
        except ValueError as ex:
            w.warn(self, str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"파일을 읽는 도중 오류가 발생했습니다: {ex}")
            return
        self.ctx.state.rentals.extend(imported)
        self.ctx.state.rental_history.extend(imported)
        self.bind_rentals()
        self.ctx.win.update_alert_badges()
        self.ctx.save_app_state()
        skip = f"\n(다른 기자재 종류 {skipped}건은 건너뛰었습니다.)" if skipped else ""
        w.info(self, f"파일로부터 {len(imported)}건의 기자재 대여 내역을 추가했습니다.{skip}", "가져오기 성공")
