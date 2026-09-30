"""
[설정] 탭 — 시스템 정보 + 구글 폼 연동 설정(응답 시트 URL · 서비스 계정 · 자동 동기화) +
학사 시즌 일정 관리. C# 버전의 TabSettings와 같은 순서·구성이다.
"""
from __future__ import annotations

import datetime
import json
import os

from PySide6.QtCore import QDate, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit,
    QPushButton, QMessageBox, QDateEdit, QFormLayout, QScrollArea,
    QFileDialog, QCheckBox, QFrame,
)

from . import config
from .models import SeasonConfig, SEASON_NAMES, ApprovalRequest


def _qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _colored_box(bg: str, border: str) -> tuple[QFrame, QVBoxLayout]:
    box = QFrame()
    box.setStyleSheet(f"QFrame {{ background:{bg}; border:1px solid {border}; border-radius:6px; }}")
    lay = QVBoxLayout(box)
    lay.setContentsMargins(15, 15, 15, 15)
    return box, lay


def _hint(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("color:#9CA3AF; font-size:10px; border:none; background:transparent;")
    lbl.setWordWrap(True)
    return lbl


class SettingsTab(QWidget):
    def __init__(
        self,
        season_config: SeasonConfig,
        settings: dict,
        approvals: list[ApprovalRequest],
        imported_source_keys: set[str],
        on_save_season,
        on_save_settings,
        on_save_all,
    ):
        super().__init__()
        self.season_config = season_config
        self.settings = settings
        self.approvals = approvals
        self.imported_source_keys = imported_source_keys
        self.on_save_season = on_save_season
        self.on_save_settings = on_save_settings
        self.on_save_all = on_save_all
        self.selected_year: int | None = None
        self._season_edits: dict[str, tuple[QDateEdit, QDateEdit]] = {}

        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(lambda: self.sync_now(silent=True))

        self._build_ui()
        self.refresh_years()
        self._apply_polling_setting()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        outer = QVBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)

        card, card_lay = _colored_box("white", "#E5E7EB")
        root.addWidget(card)

        card_lay.addWidget(_bold("시스템 정보", 14))
        card_lay.addWidget(_plain("프로그램명: 동서대학교 좌석 및 기자재 대여 관리 프로그램 (Python 버전)"))
        card_lay.addWidget(_plain("플랫폼: Python 3 / PySide6 (Qt)"))

        # -------- 구글 폼 연동 설정 --------
        card_lay.addWidget(_bold("구글 폼 연동 설정", 14, top=15))

        sheet_box, sheet_lay = _colored_box("#F9FAFB", "#E5E7EB")
        sheet_lay.addWidget(_bold("신청 폼 응답 시트", 13))
        sheet_lay.addWidget(_hint(
            "상상Lab 신청 폼 URL은 실제 동기화에 쓰입니다. 캐비닛·기자재는 별도 시트로 따로 받고 싶을 때만 채우세요."
        ))
        self.ed_sangsanglab_url = QLineEdit(self.settings.get("SangsangLabFormUrl", ""))
        self.ed_cabinet_url = QLineEdit(self.settings.get("CabinetFormUrl", ""))
        self.ed_equipment_url = QLineEdit(self.settings.get("EquipmentFormUrl", ""))
        sheet_lay.addWidget(_hint("상상Lab 신청 폼 URL (실제 동기화에 사용됨)"))
        sheet_lay.addWidget(self.ed_sangsanglab_url)
        sheet_lay.addWidget(_hint("캐비닛 응답 시트 주소 (선택)"))
        sheet_lay.addWidget(self.ed_cabinet_url)
        sheet_lay.addWidget(_hint("기자재 응답 시트 주소 (선택)"))
        sheet_lay.addWidget(self.ed_equipment_url)
        card_lay.addWidget(sheet_box)

        sync_box, sync_lay = _colored_box("#F0FDF4", "#BBF7D0")
        sync_lay.addWidget(_bold("구글 시트 연동 (서비스 계정 · 동기화 설정)", 13, color="#166534"))
        sync_lay.addWidget(_hint("위 시트 주소들을 이 서비스 계정으로 읽어옵니다. 시트마다 이 이메일에 '뷰어' 공유가 필요합니다."))

        sync_lay.addWidget(_hint("서비스 계정 이메일"))
        self.lbl_service_email = QLineEdit()
        self.lbl_service_email.setReadOnly(True)
        sync_lay.addWidget(self.lbl_service_email)

        key_row = QHBoxLayout()
        self.lbl_key_path = QLineEdit()
        self.lbl_key_path.setReadOnly(True)
        btn_pick_sa = QPushButton("📂 키 파일 선택...")
        btn_pick_sa.clicked.connect(self.pick_service_account)
        key_row.addWidget(self.lbl_key_path)
        key_row.addWidget(btn_pick_sa)
        sync_lay.addLayout(key_row)
        self._refresh_service_account_label()

        poll_row = QHBoxLayout()
        self.chk_polling = QCheckBox("자동 동기화")
        self.chk_polling.setChecked(bool(self.settings.get("PollingEnabled", False)))
        self.chk_polling.toggled.connect(self._on_polling_toggled)
        poll_row.addWidget(self.chk_polling)
        poll_row.addWidget(QLabel("주기(초):"))
        self.ed_interval = QLineEdit(str(self.settings.get("PollingIntervalSec", 60)))
        self.ed_interval.setFixedWidth(60)
        poll_row.addWidget(self.ed_interval)
        poll_row.addStretch()
        sync_lay.addLayout(poll_row)

        sync_btn_row = QHBoxLayout()
        btn_sync = QPushButton("🔄 지금 동기화")
        btn_sync.clicked.connect(lambda: self.sync_now(silent=False))
        sync_btn_row.addWidget(btn_sync)
        btn_save_settings = QPushButton("💾 연동 설정 저장")
        btn_save_settings.clicked.connect(self.save_settings)
        sync_btn_row.addWidget(btn_save_settings)
        sync_btn_row.addStretch()
        sync_lay.addLayout(sync_btn_row)

        self.lbl_sync_status = QLabel("대기 중")
        self.lbl_sync_status.setStyleSheet("color:#6B7280; font-size:11px; border:none; background:transparent;")
        self.lbl_sync_status.setWordWrap(True)
        sync_lay.addWidget(self.lbl_sync_status)
        card_lay.addWidget(sync_box)

        # -------- 학사 시즌 일정 --------
        card_lay.addWidget(_bold("학사 시즌 일정 관리", 14, top=15))
        season_box, season_lay = _colored_box("#EFF6FF", "#BFDBFE")
        season_lay.addWidget(_hint(
            "연도 버튼을 누르면 그 연도의 1학기/여름방학/2학기/겨울방학 시작일·종료일을 입력할 수 있습니다. "
            "현재 날짜가 포함되는 시즌이 대시보드에 자동으로 표시됩니다."
        ))

        year_bar = QHBoxLayout()
        self.year_row = QHBoxLayout()
        year_bar.addLayout(self.year_row)
        btn_add_year = QPushButton("+ 연도 추가")
        btn_add_year.clicked.connect(self.add_year)
        year_bar.addWidget(btn_add_year)
        year_bar.addStretch()
        season_lay.addLayout(year_bar)

        editor_box, editor_lay = _colored_box("white", "#E5E7EB")
        self.editor_box = editor_box
        header_row = QHBoxLayout()
        self.lbl_season_editor_title = QLabel("연도 시즌 일정")
        self.lbl_season_editor_title.setStyleSheet("font-weight:bold; font-size:13px; border:none; background:transparent;")
        header_row.addWidget(self.lbl_season_editor_title)
        header_row.addStretch()
        btn_del_year = QPushButton("🗑 이 연도 삭제")
        btn_del_year.clicked.connect(self.delete_year)
        header_row.addWidget(btn_del_year)
        editor_lay.addLayout(header_row)

        self.season_grid = QGridLayout()
        editor_lay.addLayout(self.season_grid)

        btn_save_season = QPushButton("💾 시즌 일정 저장")
        btn_save_season.clicked.connect(self.save_season_schedule)
        editor_lay.addWidget(btn_save_season)
        season_lay.addWidget(editor_box)

        self.lbl_current_season = QLabel("현재 시즌: (판별 전)")
        self.lbl_current_season.setStyleSheet("color:#1D4ED8; font-weight:bold; border:none; background:transparent;")
        season_lay.addWidget(self.lbl_current_season)
        card_lay.addWidget(season_box)

        root.addStretch()

    # ---------------------------------------------------------------- helpers
    def _refresh_service_account_label(self):
        path = config.google_service_account_path()
        if os.path.exists(path):
            self.lbl_key_path.setText(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.lbl_service_email.setText(data.get("client_email", "(client_email 없음)"))
            except Exception:
                self.lbl_service_email.setText("(키 파일을 읽지 못했습니다)")
        else:
            self.lbl_key_path.setText("(설정 안 됨)")
            self.lbl_service_email.setText("(설정 안 됨)")

    def pick_service_account(self):
        path, _ = QFileDialog.getOpenFileName(self, "구글 서비스 계정 JSON 파일 선택", "", "JSON (*.json)")
        if not path:
            return
        import shutil
        try:
            shutil.copyfile(path, config.google_service_account_path())
            self._refresh_service_account_label()
            QMessageBox.information(self, "완료", "서비스 계정 키를 저장했습니다.")
        except Exception as ex:
            QMessageBox.critical(self, "오류", f"파일을 복사하지 못했습니다: {ex}")

    def save_settings(self):
        self.settings["SangsangLabFormUrl"] = self.ed_sangsanglab_url.text().strip()
        self.settings["CabinetFormUrl"] = self.ed_cabinet_url.text().strip()
        self.settings["EquipmentFormUrl"] = self.ed_equipment_url.text().strip()
        self.settings["PollingEnabled"] = self.chk_polling.isChecked()
        try:
            self.settings["PollingIntervalSec"] = max(10, int(self.ed_interval.text().strip()))
        except ValueError:
            self.settings["PollingIntervalSec"] = 60
        self.on_save_settings()
        self._apply_polling_setting()
        QMessageBox.information(self, "저장 완료", "연동 설정이 저장되었습니다.")

    def _on_polling_toggled(self, _checked: bool):
        # 체크박스만 바꾼 상태로는 저장하지 않는다 — [연동 설정 저장]을 눌러야 반영된다(오조작 방지).
        pass

    def _apply_polling_setting(self):
        if self.settings.get("PollingEnabled", False):
            interval_ms = max(10, int(self.settings.get("PollingIntervalSec", 60))) * 1000
            self._poll_timer.start(interval_ms)
        else:
            self._poll_timer.stop()

    def sync_now(self, silent: bool = False):
        from . import google_integration as gi
        added, errors = gi.sync_all(self.settings, config.google_service_account_path(), self.imported_source_keys)
        for req in added:
            self.approvals.append(req)
            self.imported_source_keys.add(req.source_key)
        if added or errors:
            self.on_save_all()

        status = f"[{datetime.datetime.now():%H:%M:%S}] 신규 {len(added)}건"
        if errors:
            status += " · 오류: " + " / ".join(errors)
        self.lbl_sync_status.setText(status)

        if not silent:
            msg = f"신규 신청 {len(added)}건을 가져왔습니다."
            if errors:
                msg += "\n\n" + "\n".join(errors)
            QMessageBox.information(self, "동기화 결과", msg)

    # ------------------------------------------------------------- 시즌 일정
    def refresh_years(self):
        while self.year_row.count():
            item = self.year_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for year in self.season_config.years():
            btn = QPushButton(str(year))
            btn.setCheckable(True)
            btn.setChecked(year == self.selected_year)
            btn.clicked.connect(lambda _, y=year: self.select_year(y))
            self.year_row.addWidget(btn)

        if self.selected_year is None and self.season_config.years():
            self.selected_year = self.season_config.years()[0]
        self.render_season_rows()
        self._update_current_season_label()

    def add_year(self):
        years = self.season_config.years()
        new_year = (max(years) + 1) if years else datetime.date.today().year
        while self.season_config.has_year(new_year):
            new_year += 1
        self.season_config.ensure_year(new_year)
        self.on_save_season()
        self.selected_year = new_year
        self.refresh_years()

    def delete_year(self):
        if self.selected_year is None:
            return
        res = QMessageBox.question(self, "삭제 확인", f"{self.selected_year}년 시즌 일정을 삭제할까요?")
        if res != QMessageBox.Yes:
            return
        self.season_config.remove_year(self.selected_year)
        self.on_save_season()
        self.selected_year = None
        self.refresh_years()

    def select_year(self, year: int):
        self.selected_year = year
        self.refresh_years()

    def render_season_rows(self):
        while self.season_grid.count():
            item = self.season_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._season_edits.clear()

        if self.selected_year is None:
            self.lbl_season_editor_title.setText("연도를 추가해 주세요")
            self.editor_box.setVisible(False)
            return
        self.editor_box.setVisible(True)
        self.lbl_season_editor_title.setText(f"{self.selected_year}년 시즌 일정")

        sched = self.season_config.ensure_year(self.selected_year)
        by_name = {p.name: p for p in sched.seasons}
        for r, name in enumerate(SEASON_NAMES):
            p = by_name.get(name)
            lbl = QLabel(name)
            lbl.setStyleSheet("border:none; background:transparent;")
            self.season_grid.addWidget(lbl, r, 0)
            dt_start = QDateEdit(_qdate(p.start_date) if p else QDate.currentDate())
            dt_end = QDateEdit(_qdate(p.end_date) if p else QDate.currentDate())
            for dt in (dt_start, dt_end):
                dt.setCalendarPopup(True)
                dt.setDisplayFormat("yyyy-MM-dd")
            self.season_grid.addWidget(dt_start, r, 1)
            tilde = QLabel("~")
            tilde.setStyleSheet("border:none; background:transparent;")
            self.season_grid.addWidget(tilde, r, 2)
            self.season_grid.addWidget(dt_end, r, 3)
            self._season_edits[name] = (dt_start, dt_end)

    def save_season_schedule(self):
        if self.selected_year is None:
            return
        sched = self.season_config.ensure_year(self.selected_year)
        from .models import SeasonPeriod
        new_seasons = []
        for name in SEASON_NAMES:
            dt_start, dt_end = self._season_edits[name]
            new_seasons.append(SeasonPeriod(name, dt_start.date().toPython(), dt_end.date().toPython()))
        sched.seasons = new_seasons
        self.on_save_season()
        self._update_current_season_label()
        QMessageBox.information(self, "저장 완료", f"{self.selected_year}년 시즌 일정이 저장되었습니다.")

    def _update_current_season_label(self):
        season = self.season_config.resolve_season(datetime.date.today())
        if season:
            self.lbl_current_season.setText(f"현재 시즌: {season[0]}년 {season[1]}  ·  기준 날짜 {datetime.date.today():%Y-%m-%d}")
        else:
            self.lbl_current_season.setText("현재 시즌: 판별 안 됨 (일정을 등록해 주세요)")


def _bold(text: str, size: int, top: int = 0, color: str = "#374151") -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"font-size:{size}px; font-weight:bold; color:{color}; margin-top:{top}px; border:none; background:transparent;")
    return lbl


def _plain(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet("border:none; background:transparent;")
    return lbl
