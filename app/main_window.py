from __future__ import annotations

import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QButtonGroup,
)

from . import storage, face_integration, theme
from .widgets import AlertChip
from .seat_tab import SeatTab
from .data_tab import DataManageTab
from .cabinet_tab import CabinetTab
from .equipment_tab import EquipmentTab
from .sangsanglab_tab import SangsangLabTab
from .settings_tab import SettingsTab

# (아이콘, 제목, 속성이름) — C# 사이드바 버튼과 정확히 같은 순서·아이콘·개수(6개)를 쓴다.
# C# 버전에는 "좌석 배정"이라는 별도 탭이 없다 — 대시보드 화면 자체가 좌석 배치도 + 메모다.
NAV_ITEMS = [
    ("🏠 대시보드", "seat_tab"),
    ("🔧 기자재 현황", "equipment_tab"),
    ("🗄️ 캐비닛 현황", "cabinet_tab"),
    ("💡 상상Lab 승인", "sangsanglab_tab"),
    ("📊 데이터 관리", "data_tab"),
    ("⚙️ 설정", "settings_tab"),
]
DASHBOARD_INDEX = 0


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("동서대학교 좌석 및 기자재 관리 시스템 (Python 버전)")
        self.resize(1600, 900)
        self.setMinimumSize(1100, 720)
        self.setStyleSheet(theme.STYLE_SHEET)

        self.seat_cache = storage.load_seat_cache()
        self.state = storage.load_app_state()
        self.season_config = storage.load_season_config()
        self.settings = storage.load_settings()

        if not self.season_config.schedules:
            cy = datetime.date.today().year
            for y in (cy - 1, cy, cy + 1):
                self.season_config.ensure_year(y)
            storage.save_season_config(self.season_config)

        face_integration.export_roster(self.state.master_students)

        self._build_ui()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_lay = QHBoxLayout(root)
        root_lay.setContentsMargins(0, 0, 0, 0)
        root_lay.setSpacing(0)

        root_lay.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("ContentArea")
        content_lay = QVBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)
        content_lay.addWidget(self._build_header())

        self.stack = QStackedWidget()
        content_lay.addWidget(self.stack, 1)
        root_lay.addWidget(content, 1)

        self._build_pages()

        self.nav_buttons[DASHBOARD_INDEX].setChecked(True)
        self.stack.setCurrentIndex(DASHBOARD_INDEX)
        self.header_alert_area.setVisible(True)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        logo = QWidget()
        logo.setFixedHeight(70)
        logo_lay = QHBoxLayout(logo)
        logo_lay.setContentsMargins(18, 0, 0, 0)
        lbl1 = QLabel("DSU")
        lbl1.setObjectName("SidebarLogo")
        lbl2 = QLabel(" 동서대학교")
        lbl2.setObjectName("SidebarLogoSub")
        logo_lay.addWidget(lbl1)
        logo_lay.addWidget(lbl2)
        logo_lay.addStretch()
        lay.addWidget(logo)

        self.nav_buttons: list[QPushButton] = []
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        for i, (label, _attr) in enumerate(NAV_ITEMS):
            btn = QPushButton(label)
            btn.setProperty("cssClass", "sidebar")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, idx=i: self.go_to(idx))
            lay.addWidget(btn)
            self.nav_buttons.append(btn)
            self.nav_group.addButton(btn, i)

        lay.addStretch()
        return sidebar

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("Header")
        header.setFixedHeight(75)
        lay = QHBoxLayout(header)
        lay.setContentsMargins(20, 0, 20, 0)

        self.lbl_header_title = QLabel(NAV_ITEMS[DASHBOARD_INDEX][0].split(" ", 1)[1])
        self.lbl_header_title.setObjectName("HeaderTitle")
        lay.addWidget(self.lbl_header_title)

        lay.addSpacing(30)
        # 대시보드 화면에서만 보이는 3종 알림 카드 (C#의 HeaderAlertArea — TabDashboard일 때만 Visible)
        self.header_alert_area = QWidget()
        area_lay = QHBoxLayout(self.header_alert_area)
        area_lay.setContentsMargins(0, 0, 0, 0)
        self.chip_sangsanglab = AlertChip("💡", "상상Lab 승인 대기", "#FEE2E2", "#FCA5A5", "#DC2626", lambda: self.go_to(self._nav_index("sangsanglab_tab")))
        self.chip_cabinet = AlertChip("🗄️", "캐비닛 승인 대기", "#FFEDD5", "#FED7AA", "#EA580C", lambda: self.go_to(self._nav_index("cabinet_tab")))
        self.chip_equipment = AlertChip("🔧", "기자재 승인 대기", "#FEE2E2", "#FCA5A5", "#DC2626", lambda: self.go_to(self._nav_index("equipment_tab")))
        for chip in (self.chip_sangsanglab, self.chip_cabinet, self.chip_equipment):
            area_lay.addWidget(chip)
            area_lay.addSpacing(10)
        lay.addWidget(self.header_alert_area)

        lay.addStretch()

        profile = QLabel("👤 관리자")
        profile.setStyleSheet(f"font-size:13px; font-weight:600; color:{theme.TEXT_SECONDARY};")
        lay.addWidget(profile)
        lay.addSpacing(15)

        self.lbl_date = QLabel()
        self.lbl_date.setObjectName("HeaderDate")
        self._update_date()
        lay.addWidget(self.lbl_date)

        return header

    def _update_date(self):
        today = datetime.date.today()
        weekday = "월화수목금토일"[today.weekday()]
        self.lbl_date.setText(f"📅 {today:%Y-%m-%d} ({weekday})")

    def _nav_index(self, attr: str) -> int:
        for i, (_label, a) in enumerate(NAV_ITEMS):
            if a == attr:
                return i
        return 0

    def go_to(self, index: int):
        self.nav_buttons[index].setChecked(True)
        self.stack.setCurrentIndex(index)
        self.lbl_header_title.setText(NAV_ITEMS[index][0].split(" ", 1)[1])
        self.header_alert_area.setVisible(index == DASHBOARD_INDEX)
        # 다른 화면에서 바뀐 값(새 학생 등록, 승인 처리 등)을 페이지를 옮길 때마다 반영한다.
        self.data_tab.refresh_table()
        self.cabinet_tab.refresh_approvals()
        self.equipment_tab.refresh_approvals()
        self.sangsanglab_tab.refresh()
        self._refresh_alert_chips()

    def _refresh_alert_chips(self):
        self.chip_sangsanglab.set_count(sum(1 for a in self.state.approvals if a.tab_type == "상상Lab"))
        self.chip_cabinet.set_count(sum(1 for a in self.state.approvals if a.tab_type == "캐비닛"))
        self.chip_equipment.set_count(sum(1 for a in self.state.approvals if a.tab_type == "기자재"))

    # ---------------------------------------------------------------- pages
    def _build_pages(self):
        self.seat_tab = SeatTab(self.seat_cache, self.state.master_students, self.state.memos, self.save_all)
        self.equipment_tab = EquipmentTab(
            self.state.rentals, self.state.rental_history, self.state.equipment_issues,
            self.state.master_students, self.state.approvals, self.state.approval_history,
            self.season_config, self.save_all,
        )
        self.cabinet_tab = CabinetTab(
            self.state.cabinet_allocations, self.state.master_students,
            self.state.approvals, self.state.approval_history, self.season_config, self.save_all,
        )
        self.sangsanglab_tab = SangsangLabTab(
            self.state.approvals, self.state.approval_history, self.state.master_students,
            self.season_config, self.save_all,
        )
        self.data_tab = DataManageTab(self.state.master_students, self.save_all)
        self.settings_tab = SettingsTab(
            self.season_config, self.settings, self.state.approvals, self.state.imported_source_keys,
            self.save_season, self.save_settings, self.save_all,
        )

        for _label, attr in NAV_ITEMS:
            self.stack.addWidget(getattr(self, attr))

        self._refresh_alert_chips()

    def save_all(self):
        storage.save_seat_cache(self.seat_cache)
        storage.save_app_state(self.state)
        face_integration.export_roster(self.state.master_students)
        self._refresh_alert_chips()

    def save_season(self):
        storage.save_season_config(self.season_config)

    def save_settings(self):
        storage.save_settings(self.settings)
