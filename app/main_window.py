"""
메인 창 — C# 버전 MainWindow.xaml의 바깥 틀(왼쪽 사이드바 220px + 위쪽 헤더 75px + 작업 영역) 그대로.
"""
from __future__ import annotations

import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QStackedWidget, QButtonGroup,
)

from . import theme, widgets as w
from . import approval_logic as al
from . import google_integration as gi
from .context import AppContext
from .seat_tab import SeatTab
from .equipment_tab import EquipmentTab
from .cabinet_tab import CabinetTab
from .sangsanglab_tab import SangsangLabTab
from .data_tab import DataManageTab
from .settings_tab import SettingsTab

# (버튼 글자, 화면 이름, 헤더 제목) — C# 사이드바 버튼과 같은 순서·아이콘
NAV = [
    ("🏠 대시보드", "dashboard", "대시보드"),
    ("🔧 기자재 현황", "equipment", "기자재 현황"),
    ("🗄️ 캐비닛 현황", "cabinet", "캐비닛 현황"),
    ("💡 상상Lab 승인", "sangsanglab", "상상Lab 승인"),
    ("📊 데이터 관리", "data", "데이터 관리"),
    ("⚙️ 설정", "settings", "설정"),
]

SIDEBAR_CSS = f"""
QPushButton#side {{
    background: transparent; color: #E5E7EB; border: none; border-left: 4px solid transparent;
    padding: 15px 20px 15px 20px; text-align: left; font-size: 14px; font-weight: 600;
    font-family: {theme.ICON_FAMILIES};
}}
QPushButton#side:hover {{ background: #111827; border-left: 4px solid #3B82F6; }}
QPushButton#side:checked {{ background: #2563EB; color: #FFFFFF; border-left: 4px solid #60A5FA; }}
"""


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        ctx.win = self
        self.forms_service = None
        self.is_syncing = False
        self.current = "dashboard"
        self.setWindowTitle("동서대학교 좌석 및 기자재 관리 시스템")
        self.resize(1600, 900)
        self.setMinimumSize(1100, 720)

        self._build_ui()

        # 1분마다 날짜를 갱신하고, 날짜가 바뀌면 현재 시즌을 다시 판별한다
        self._date_timer = QTimer(self)
        self._date_timer.setInterval(60_000)
        self._date_timer.timeout.connect(self._tick)
        self._date_timer.start()
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(lambda: self.sync_now(True))

        self.update_alert_badges()
        self.detect_and_apply_current_season(initial=True)
        ctx.migrate_students_without_season()
        self.data.refresh_table()
        self.dashboard.refresh_memos()
        self.settings_tab.load_season_settings_ui()
        QTimer.singleShot(0, self._init_google_form_sync)

    # ------------------------------------------------------------------ 틀
    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        root.setStyleSheet("QWidget#root { background:#F3F4F6; }")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ---- 사이드바 ----
        side = QWidget()
        side.setObjectName("sidebar")
        side.setAttribute(Qt.WA_StyledBackground, True)
        side.setStyleSheet("QWidget#sidebar { background:#0A1C3E; }" + SIDEBAR_CSS)
        side.setFixedWidth(220)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.setSpacing(0)
        logo = QWidget()
        logo.setFixedHeight(70)
        ll = QHBoxLayout(logo)
        ll.setContentsMargins(15, 0, 15, 0)
        ll.setSpacing(0)
        ll.addWidget(w.label("DSU", 22, bold=True, color="#FFFFFF"), 0, Qt.AlignVCenter)
        sub = w.label(" 동서대학교", 15, weight=600, color="#93C5FD")
        sub.setContentsMargins(5, 3, 0, 0)
        ll.addWidget(sub, 0, Qt.AlignVCenter)
        ll.addStretch()
        sl.addWidget(logo)
        sl.addSpacing(10)
        self.nav_group = QButtonGroup(self)
        self.nav_buttons: dict[str, QPushButton] = {}
        for text, name, _title in NAV:
            b = QPushButton(text)
            b.setObjectName("side")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(lambda _=False, n=name: self.switch_tab(n))
            self.nav_group.addButton(b)
            self.nav_buttons[name] = b
            sl.addWidget(b)
        sl.addStretch()
        h.addWidget(side)

        # ---- 작업 영역 ----
        main = QWidget()
        ml = QVBoxLayout(main)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(0)
        ml.addWidget(self._build_header())
        self.stack = QStackedWidget()
        ml.addWidget(self.stack, 1)
        h.addWidget(main, 1)

        self.dashboard = SeatTab(self.ctx)
        self.equipment = EquipmentTab(self.ctx)
        self.cabinet = CabinetTab(self.ctx)
        self.sangsanglab = SangsangLabTab(self.ctx)
        self.data = DataManageTab(self.ctx)
        self.settings_tab = SettingsTab(self.ctx)
        self.pages = {"dashboard": self.dashboard, "equipment": self.equipment, "cabinet": self.cabinet,
                      "sangsanglab": self.sangsanglab, "data": self.data, "settings": self.settings_tab}
        for _t, name, _ in NAV:
            self.stack.addWidget(self.pages[name])
        self.nav_buttons["dashboard"].setChecked(True)
        self.stack.setCurrentWidget(self.dashboard)

    def _build_header(self) -> QWidget:
        header = w.Card(bg="#FFFFFF", border="#E5E7EB", radius=0, padding=(0, 20), sides="bottom")
        header.setFixedHeight(75)
        lay = header.hbox()
        self.lbl_title = w.label("대시보드", 18, bold=True, color="#111827")
        lay.addWidget(self.lbl_title, 0, Qt.AlignVCenter)
        lay.addSpacing(30)
        self.alert_area = QWidget()
        al_ = QHBoxLayout(self.alert_area)
        al_.setContentsMargins(0, 0, 0, 0)
        al_.setSpacing(12)
        self.chip_lab = w.AlertCard("💡", "상상Lab 승인 대기", "승인 필요", "#FEE2E2", "#FCA5A5", "#DC2626", "#991B1B", "#DC2626",
                                    on_click=lambda: self.switch_tab("sangsanglab"))
        self.chip_cab = w.AlertCard("🗄️", "캐비닛 승인 대기", "승인 필요", "#FFEDD5", "#FED7AA", "#EA580C", "#9A3412", "#EA580C",
                                    on_click=lambda: self.switch_tab("cabinet"))
        self.chip_eq = w.AlertCard("🔧", "기자재 승인 대기", "승인 필요", "#FEE2E2", "#FCA5A5", "#DC2626", "#991B1B", "#DC2626",
                                   on_click=lambda: self.switch_tab("equipment"))
        for chip in (self.chip_lab, self.chip_cab, self.chip_eq):
            al_.addWidget(chip)
        lay.addWidget(self.alert_area, 0, Qt.AlignVCenter)
        lay.addStretch()

        prof = QHBoxLayout()
        prof.setSpacing(0)
        prof.addWidget(w.label("👤", 16, color="#4B5563", icon=True))
        prof.addSpacing(5)
        prof.addWidget(w.label("관리자", 13, weight=600, color="#374151"))
        prof.addWidget(w.label(" ∨", 10, color="#9CA3AF"))
        lay.addLayout(prof)
        lay.addSpacing(20)
        pill = w.Card(bg="#F3F4F6", border="#F3F4F6", radius=6, padding=(6, 10), border_width=0)
        pl = pill.hbox()
        pl.addWidget(w.label("📅 ", 12, color="#4B5563", icon=True))
        self.lbl_date = w.label("", 12, weight=600, color="#374151")
        pl.addWidget(self.lbl_date)
        lay.addWidget(pill, 0, Qt.AlignVCenter)
        self._update_date()
        return header

    def _update_date(self):
        d = self.ctx.today
        self.lbl_date.setText(f"{d:%Y-%m-%d} ({'월화수목금토일'[d.weekday()]})")

    def _tick(self):
        self._update_date()
        self.detect_and_apply_current_season()
        self.update_alert_badges()

    # ------------------------------------------------------------------ 탭 전환
    def switch_tab(self, name: str):
        self.current = name
        self.nav_buttons[name].setChecked(True)
        self.stack.setCurrentWidget(self.pages[name])
        self.lbl_title.setText(next(t for _x, n, t in NAV if n == name))
        self.alert_area.setVisible(name == "dashboard")
        if name == "equipment":
            self.equipment.refresh_approvals()
            self.equipment.bind_rentals()
        elif name == "cabinet":
            self.cabinet.refresh_approvals()
            self.cabinet.render_grid()
        elif name == "sangsanglab":
            self.sangsanglab.refresh()
        elif name == "data":
            self.data.refresh_table()
        elif name == "settings":
            self.settings_tab.load_season_settings_ui()
        self.update_alert_badges()
        if name == "dashboard":
            al.check_expired_items(self.ctx, "대시보드")
        elif name == "equipment":
            al.check_expired_items(self.ctx, "기자재")
            al.show_equipment_expiry_warning(self.ctx)
        elif name == "cabinet":
            al.show_cabinet_expiry_warning(self.ctx)

    def update_alert_badges(self):
        ap = self.ctx.state.approvals
        n_lab = sum(1 for a in ap if a.status == "승인 대기" and a.tab_type == "상상Lab")
        n_cab = sum(1 for a in ap if a.status == "승인 대기" and a.tab_type == "캐비닛")
        n_eq = sum(1 for a in ap if a.status == "승인 대기" and a.tab_type == "기자재")
        for chip, n in ((self.chip_lab, n_lab), (self.chip_cab, n_cab), (self.chip_eq, n_eq)):
            chip.set_count(n)
            chip.setVisible(n > 0)
        self.equipment.alert.set_count(sum(1 for a in ap if a.tab_type == "기자재"))
        self.equipment.bind_rentals()
        self.cabinet.alert.set_count(sum(1 for a in ap if a.tab_type == "캐비닛"))
        self.cabinet.render_grid()
        self.sangsanglab.alert.set_count(sum(1 for a in ap if a.tab_type == "상상Lab"))

    def refresh_approval_views(self):
        self.sangsanglab.refresh()
        self.cabinet.refresh_approvals()
        self.equipment.refresh_approvals()
        self.update_alert_badges()

    # ------------------------------------------------------------------ 시즌
    def detect_and_apply_current_season(self, initial: bool = False):
        resolved = self.ctx.season_config.resolve_season(self.ctx.today)
        if resolved is None:
            if initial:
                self.dashboard.load_dashboard_layout()
            else:
                self.dashboard.update_season_info()
            self.settings_tab.update_current_info()
            return
        changed = self.ctx.current_season != resolved
        if initial or changed:
            self.ctx.current_season = resolved
            self.dashboard.sync_combos_to_season(resolved)
            self.dashboard.load_dashboard_layout()
            self.data.refresh_table()
        self.settings_tab.update_current_info()

    # ------------------------------------------------------------------ 구글 연동
    def _init_google_form_sync(self):
        s = self.ctx.settings
        self.ctx.save_settings()
        main_id = gi.extract_spreadsheet_id(s.get("SangsangLabFormUrl", ""))
        self.forms_service = gi.GoogleFormsService(self.ctx.resolve_service_account_key_path(), main_id)
        self.forms_service.equipment_spreadsheet_id = gi.extract_spreadsheet_id(s.get("EquipmentFormUrl", ""))
        self.forms_service.cabinet_spreadsheet_id = gi.extract_spreadsheet_id(s.get("CabinetFormUrl", ""))
        self.settings_tab.update_key_display()
        if not self.forms_service.key_file_exists:
            self.settings_tab.set_sync_status(
                "서비스 계정 키를 찾지 못했습니다. [키 파일 선택...]으로 지정해주세요.\n"
                f"찾아본 위치: {self.forms_service.key_path}", True)
            return
        self.apply_polling_timer()
        self.sync_now(True)   # 시작 직후 1회 동기화 (조용히)

    def apply_polling_timer(self):
        self._poll_timer.stop()
        if not self.ctx.settings.get("PollingEnabled", True):
            return
        if self.forms_service is None or not self.forms_service.key_file_exists:
            return
        self._poll_timer.start(max(15, int(self.ctx.settings.get("PollingIntervalSeconds", 60))) * 1000)

    def sync_now(self, silent: bool):
        al.sync_from_google_form(self.ctx, silent)

    # ------------------------------------------------------------------ 종료
    def closeEvent(self, e):
        self.ctx.save_all()
        super().closeEvent(e)
