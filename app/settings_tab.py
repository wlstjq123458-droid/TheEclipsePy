"""
[설정] 화면 — C# 버전 TabSettings 그대로.
설정 → 시스템 정보 → 구글 폼 연동 설정(신청 폼 응답 시트 / 구글 시트 연동) → 학사 시즌 일정 관리(연도 카드) → 화면 해상도 설정.
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
from typing import TYPE_CHECKING, Optional

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea, QCheckBox, QComboBox, QFileDialog, QDateEdit, QFrame,
)

from . import widgets as w
from . import config
from . import google_integration as gi
from .models import SEASON_NAMES, SeasonPeriod, default_seasons_for

if TYPE_CHECKING:  # pragma: no cover
    from .context import AppContext


def _qdate(d: datetime.date) -> QDate:
    return QDate(d.year, d.month, d.day)


def _box(bg: str, border: str, radius: int = 6, padding: int = 15) -> tuple[w.Card, QVBoxLayout]:
    card = w.Card(bg=bg, border=border, radius=radius, padding=padding)
    return card, card.vbox()


def _input(height: int = 35, read_only: bool = False, padding: str = "10px", font: int = 12, bg: Optional[str] = None) -> QLineEdit:
    ed = QLineEdit()
    ed.setFixedHeight(height)
    ed.setReadOnly(read_only)
    b = f"background:{bg};" if bg else ""
    ed.setStyleSheet(f"QLineEdit {{ border:1px solid #D1D5DB; padding:0 {padding}; font-size:{font}px; {b} }}")
    return ed


class YearCard(QFrame):
    def __init__(self, year: int, selected: bool, current: bool, on_click):
        super().__init__()
        name = f"yc{year}"
        self.setObjectName(name)
        border = "#F59E0B" if selected else ("#93C5FD" if current else "#0F5132")
        bw = 3 if (selected or current) else 1
        self.setStyleSheet(f"QFrame#{name} {{ background:#1E7A5F; border:{bw}px solid {border}; border-radius:6px; }}")
        self.setFixedSize(150, 74)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        lay.setSpacing(0)
        lay.addStretch()
        y = w.label(str(year), 18, bold=True, color="#FFFFFF")
        y.setAlignment(Qt.AlignCenter)
        lay.addWidget(y)
        if current:
            c = w.label("● 현재 시즌", 10, weight=600, color="#DBEAFE")
            c.setAlignment(Qt.AlignCenter)
            lay.addSpacing(3)
            lay.addWidget(c)
        lay.addStretch()
        self._on_click = on_click

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_click()


class AddYearCard(QFrame):
    def __init__(self, on_click):
        super().__init__()
        self.setObjectName("ycadd")
        self.setStyleSheet("QFrame#ycadd { background:#ECFDF5; border:2px solid #10B981; border-radius:6px; }")
        self.setFixedSize(150, 74)
        self.setCursor(Qt.PointingHandCursor)
        lay = QVBoxLayout(self)
        t = w.label("＋ 연도 추가", 13, bold=True, color="#047857")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        self._on_click = on_click

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._on_click()


class SettingsTab(QWidget):
    def __init__(self, ctx: "AppContext"):
        super().__init__()
        self.ctx = ctx
        self.selected_year: Optional[int] = None
        self._edit_rows: list[SeasonPeriod] = []
        self._build_ui()
        self._load_sync_settings()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        self.setAttribute(Qt.WA_StyledBackground, True)
        w.inset_background(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 20, 20, 20)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background:transparent; border:none; } QScrollArea > QWidget > QWidget { background:transparent; }")
        outer.addWidget(scroll)
        host = QWidget()
        scroll.setWidget(host)
        root = QVBoxLayout(host)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(w.label("설정", 18, bold=True, color="#111827"))
        root.addSpacing(15)

        card, c = _box("#FFFFFF", "#E5E7EB", radius=8, padding=20)
        root.addWidget(card)
        root.addStretch()

        c.addWidget(w.label("시스템 정보", 14, bold=True, color="#374151"))
        c.addSpacing(10)
        c.addWidget(w.label("프로그램명: 동서대학교 좌석 및 기자재 대여 관리 프로그램"))
        c.addSpacing(5)
        c.addWidget(w.label("버전: v1.1.0"))
        c.addSpacing(5)
        c.addWidget(w.label("플랫폼: Python 3 / PySide6 (Qt) Application"))
        c.addSpacing(15)

        # -------- 구글 폼 연동 설정 --------
        c.addSpacing(15)
        c.addWidget(w.label("구글 폼 연동 설정", 14, bold=True, color="#374151"))
        c.addSpacing(10)

        sheet, s = _box("#F9FAFB", "#E5E7EB")
        s.addWidget(w.label("신청 폼 응답 시트", 13, bold=True, color="#374151"))
        s.addSpacing(4)
        s.addWidget(w.label("상상Lab 신청 폼 URL은 실제 동기화에 쓰입니다 — 상상Lab 신청과, 캐비닛·기자재 전용 시트를 따로 지정하지 않은 신청이 모두 이 시트에서 들어옵니다. 캐비닛·기자재는 신청을 별도 시트로 따로 받고 싶을 때만 채우세요.",
                            10, color="#9CA3AF", wrap=True))
        s.addSpacing(14)
        self.ed_main = self._url_block(s, "상상Lab 신청 폼 URL  (실제 동기화에 사용됨)",
                                       "※ 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트를 아래 서비스 계정에 '뷰어'로 공유해야 합니다.")
        s.addSpacing(14)
        self.ed_cabinet = self._url_block(s, "캐비닛 응답 시트 주소  (선택 — 넣으면 캐비닛 신청만 이 시트에서 따로 받습니다)",
                                          "※ 캐비닛 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트도 아래 서비스 계정에 '뷰어' 공유가 필요합니다.")
        s.addSpacing(14)
        self.ed_equipment = self._url_block(s, "기자재 응답 시트 주소  (선택 — 넣으면 기자재 신청만 이 시트에서 따로 받습니다)",
                                            "※ 기자재 폼의 [응답] → [시트에서 보기] 주소를 넣으세요. 이 시트도 아래 서비스 계정에 '뷰어' 공유가 필요합니다.")
        c.addWidget(sheet)
        c.addSpacing(15)

        sync, y = _box("#F0FDF4", "#BBF7D0")
        y.addWidget(w.label("구글 시트 연동 (서비스 계정 · 동기화 설정)", 13, bold=True, color="#166534"))
        y.addSpacing(4)
        y.addWidget(w.label("위에서 넣은 시트 주소들을 이 서비스 계정으로 읽어옵니다. 시트마다 이 주소를 '뷰어'로 공유해 두어야 합니다.",
                            10, color="#4D7C60", wrap=True))
        y.addSpacing(10)
        y.addWidget(w.label("서비스 계정 (이 주소로 시트를 '뷰어' 공유해야 합니다)", 11, color="#6B7280"))
        y.addSpacing(4)
        self.ed_email = _input(30, read_only=True, padding="10px", font=11, bg="#F3F4F6")
        y.addWidget(self.ed_email)
        y.addSpacing(8)
        y.addWidget(w.label("키 파일 위치", 11, color="#6B7280"))
        y.addSpacing(4)
        kr = QHBoxLayout()
        self.ed_key = _input(30, read_only=True, padding="10px", font=11, bg="#F3F4F6")
        kr.addWidget(self.ed_key, 1)
        kr.addSpacing(8)
        kr.addWidget(w.action_btn("📂 키 파일 선택...", padding=(6, 12), on_click=self.pick_key_file))
        y.addLayout(kr)
        y.addSpacing(12)
        pr = QHBoxLayout()
        self.chk_poll = QCheckBox("자동 동기화")
        self.chk_poll.setStyleSheet("QCheckBox { font-size:12px; }")
        self.chk_poll.toggled.connect(self._poll_changed)
        pr.addWidget(self.chk_poll)
        pr.addSpacing(20)
        pr.addWidget(w.label("주기(초):", 12, color="#6B7280"))
        pr.addSpacing(6)
        self.ed_interval = QLineEdit()
        self.ed_interval.setFixedSize(70, 28)
        self.ed_interval.setStyleSheet("QLineEdit { border:1px solid #D1D5DB; padding:0 8px; }")
        pr.addWidget(self.ed_interval)
        pr.addStretch()
        y.addLayout(pr)
        y.addSpacing(12)
        br = QHBoxLayout()
        self.btn_sync = w.action_btn("🔄 지금 동기화", padding=(8, 15), on_click=lambda: self.ctx.win.sync_now(False))
        br.addWidget(self.btn_sync)
        br.addSpacing(10)
        br.addWidget(w.action_btn("💾 연동 설정 저장", padding=(8, 15), on_click=self.save_sync_settings))
        br.addStretch()
        y.addLayout(br)
        y.addSpacing(10)
        self.lbl_status = w.label("대기 중", 11, color="#6B7280", wrap=True)
        y.addWidget(self.lbl_status)
        c.addWidget(sync)
        c.addSpacing(15)

        # -------- 학사 시즌 일정 --------
        c.addSpacing(15)
        c.addWidget(w.label("학사 시즌 일정 관리", 14, bold=True, color="#374151"))
        c.addSpacing(10)
        season, sb = _box("#EFF6FF", "#BFDBFE")
        sb.addWidget(w.label("연도 카드를 누르면 그 연도의 1학기 / 여름방학 / 2학기 / 겨울방학 시작일·종료일을 입력할 수 있습니다. 현재 날짜가 포함되는 시즌이 대시보드에 자동으로 표시됩니다.",
                             11, color="#6B7280", wrap=True))
        sb.addSpacing(12)
        years_box = w.Card(bg="#D1FAE5", border="#A7F3D0", radius=8, padding=12)
        yl = years_box.vbox()
        years_host = QWidget()
        self.years_flow = w.FlowLayout(years_host, h_spacing=14, v_spacing=14)
        yl.addWidget(years_host)
        sb.addWidget(years_box)
        sb.addSpacing(14)

        self.editor, ed = _box("#FFFFFF", "#E5E7EB")
        er = QHBoxLayout()
        self.lbl_editor_title = w.label("연도 시즌 일정", 13, bold=True, color="#111827")
        er.addWidget(self.lbl_editor_title)
        er.addStretch()
        er.addWidget(w.action_btn("🗑 이 연도 삭제", padding=(6, 12), on_click=self.delete_year))
        ed.addLayout(er)
        ed.addSpacing(10)
        self.season_grid = w.DataGrid([
            w.Col("시즌", 120, text=lambda p: p.name),
            w.Col("시작일", 180, widget=lambda p: self._date_cell(p, True)),
            w.Col("종료일", 180, widget=lambda p: self._date_cell(p, False)),
        ], row_height=40)
        self.season_grid.setFixedHeight(23 + 40 * 4 + 4)
        grid_wrap = w.Card(bg="#FFFFFF", border="#D1D5DB", radius=0, padding=0)
        grid_wrap.vbox().addWidget(self.season_grid)
        ed.addWidget(grid_wrap)
        ed.addSpacing(10)
        save_row = QHBoxLayout()
        save_row.addWidget(w.action_btn("💾 시즌 일정 저장", padding=(8, 15), on_click=self.save_season_schedule))
        save_row.addStretch()
        ed.addLayout(save_row)
        sb.addWidget(self.editor)
        sb.addSpacing(10)
        self.lbl_current = w.label("현재 시즌: (판별 전)", 12, bold=True, color="#1D4ED8", wrap=True)
        sb.addWidget(self.lbl_current)
        c.addWidget(season)
        c.addSpacing(15)

        # -------- 화면 해상도 --------
        c.addSpacing(10)
        c.addWidget(w.label("화면 해상도 설정", 14, bold=True, color="#374151"))
        c.addSpacing(10)
        self.combo_res = QComboBox()
        self.combo_res.setFixedWidth(200)
        self.combo_res.addItems(["기본 (1600 x 900)", "소형 (1024 x 768)", "중형 (1200 x 780)", "대형 (1920 x 1080)"])
        self.combo_res.currentTextChanged.connect(self._resolution_changed)
        c.addWidget(self.combo_res)
        c.addSpacing(15)

    def _url_block(self, lay: QVBoxLayout, caption: str, hint: str) -> QLineEdit:
        lay.addWidget(w.label(caption, 11, color="#6B7280"))
        lay.addSpacing(4)
        ed = _input(35)
        lay.addWidget(ed)
        lay.addSpacing(4)
        lay.addWidget(w.label(hint, 10, color="#9CA3AF", wrap=True))
        return ed

    def _date_cell(self, p: SeasonPeriod, start: bool) -> QWidget:
        d = QDateEdit(_qdate(p.start_date if start else p.end_date))
        d.setCalendarPopup(True)
        d.setDisplayFormat("yyyy-MM-dd")
        d.setStyleSheet("QDateEdit { border:none; background:transparent; }")

        def changed(qd, pp=p, s=start):
            if s:
                pp.start_date = qd.toPython()
            else:
                pp.end_date = qd.toPython()
        d.dateChanged.connect(changed)
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(d)
        return holder

    # ------------------------------------------------------------------ 연동
    def _load_sync_settings(self):
        s = self.ctx.settings
        self.ed_interval.setText(str(s.get("PollingIntervalSeconds", 60)))
        self.ed_main.setText(s.get("SangsangLabFormUrl", ""))
        self.ed_cabinet.setText(s.get("CabinetFormUrl", ""))
        self.ed_equipment.setText(s.get("EquipmentFormUrl", ""))
        self.update_key_display()
        self.chk_poll.blockSignals(True)
        self.chk_poll.setChecked(bool(s.get("PollingEnabled", True)))
        self.chk_poll.blockSignals(False)

    def update_key_display(self):
        path = self.ctx.resolve_service_account_key_path()
        exists = os.path.exists(path)
        self.ed_key.setText(path if exists else f"(없음) {path}")
        if not exists:
            self.ed_email.setText("(키 파일 없음)")
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.ed_email.setText(json.load(f).get("client_email", "(확인 불가)") or "(확인 불가)")
        except Exception:  # noqa: BLE001
            self.ed_email.setText("(확인 불가)")

    def set_sync_status(self, message: str, warning: bool):
        self.lbl_status.setText(message)
        color = "#B45309" if warning else "#6B7280"
        self.lbl_status.setStyleSheet(f"QLabel {{ font-size:11px; color:{color}; background:transparent; border:none; }}")

    def set_sync_enabled(self, on: bool):
        self.btn_sync.setEnabled(on)

    def _poll_changed(self, on: bool):
        if self.ctx.win is None or self.ctx.win.forms_service is None:
            return
        self.ctx.settings["PollingEnabled"] = on
        self.ctx.win.apply_polling_timer()

    def pick_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "구글 서비스 계정 키(JSON) 선택", "",
                                              "서비스 계정 키 (*.json);;모든 파일 (*.*)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("type") != "service_account" or "private_key" not in data or "client_email" not in data:
                w.warn(self, "이 파일은 서비스 계정 키가 아닙니다.\nGoogle Cloud에서 발급한 서비스 계정 JSON 키를 선택해주세요.", "잘못된 키 파일")
                return
            email = data.get("client_email", "")
        except Exception as ex:  # noqa: BLE001
            w.error(self, f"키 파일을 읽지 못했습니다.\n{ex}")
            return
        target = config.google_service_account_path()
        try:
            if os.path.abspath(path).lower() != os.path.abspath(target).lower():
                shutil.copyfile(path, target)
            self.ctx.settings["KeyPathOverride"] = ""
        except Exception:  # noqa: BLE001
            target = path
            self.ctx.settings["KeyPathOverride"] = path
        self.ctx.save_settings()
        if self.ctx.win.forms_service is not None:
            self.ctx.win.forms_service.key_path = target
        self.update_key_display()
        self.ctx.win.apply_polling_timer()
        w.info(self, f"키를 등록했습니다.\n\n서비스 계정: {email}\n보관 위치: {target}\n\n"
                     "이 주소로 응답 스프레드시트를 '뷰어' 공유해야 읽을 수 있습니다.", "키 등록 완료")
        self.ctx.win.sync_now(False)

    def save_sync_settings(self):
        s = self.ctx.settings
        s["PollingEnabled"] = self.chk_poll.isChecked()
        s["SangsangLabFormUrl"] = self.ed_main.text().strip()
        s["CabinetFormUrl"] = self.ed_cabinet.text().strip()
        s["EquipmentFormUrl"] = self.ed_equipment.text().strip()
        try:
            sec = int(self.ed_interval.text().strip())
        except ValueError:
            sec = 0
        if sec < 15:
            w.warn(self, "동기화 주기는 15초 이상의 숫자로 입력해주세요.", "설정 오류")
            self.ed_interval.setText(str(s.get("PollingIntervalSeconds", 60)))
            return
        s["PollingIntervalSeconds"] = sec
        main_id = gi.extract_spreadsheet_id(s["SangsangLabFormUrl"])
        eq_id = gi.extract_spreadsheet_id(s["EquipmentFormUrl"])
        cab_id = gi.extract_spreadsheet_id(s["CabinetFormUrl"])
        if not main_id:
            w.warn(self, "상상Lab 신청 폼 URL 칸의 주소로는 시트를 읽을 수 없습니다.\n\n" +
                   ("폼 편집 화면의 [응답] → [시트에서 보기]로 열리는 " if gi.is_form_url(s["SangsangLabFormUrl"]) else "") +
                   "스프레드시트 주소(docs.google.com/spreadsheets/d/...)를 붙여넣어 주세요.\n\n"
                   "이 값이 없으면 상상Lab 신청과, 전용 시트를 지정하지 않은 캐비닛·기자재 신청을 전혀 받아올 수 없습니다.", "설정 오류")
            return
        self.ctx.save_settings()
        svc = self.ctx.win.forms_service
        if svc is not None:
            svc.spreadsheet_id, svc.equipment_spreadsheet_id, svc.cabinet_spreadsheet_id = main_id, eq_id, cab_id
        self.ctx.win.apply_polling_timer()
        notes = [n for n in (_describe("캐비닛", s["CabinetFormUrl"], cab_id), _describe("기자재", s["EquipmentFormUrl"], eq_id)) if n]
        msg = f"연동 설정을 저장했습니다. (메인 시트 ID: {main_id})"
        if notes:
            msg += "\n\n" + "\n\n".join(notes) + "\n\n전용 시트도 서비스 계정에 '뷰어'로 공유되어 있어야 합니다."
        w.info(self, msg, "저장 완료")

    # ------------------------------------------------------------------ 시즌
    def load_season_settings_ui(self):
        cy = self.ctx.today.year
        target = self.ctx.current_season[0] if self.ctx.current_season else cy
        cfg = self.ctx.season_config
        if not cfg.has_year(target):
            years = cfg.years()
            target = cy if cy in years else (years[-1] if years else cy)
        self.selected_year = target if cfg.has_year(target) else None
        self.rebuild_year_cards()
        self.load_rows()
        self.update_current_info()

    def rebuild_year_cards(self):
        while self.years_flow.count():
            it = self.years_flow.takeAt(0)
            if it and it.widget():
                it.widget().deleteLater()
        cur = self.ctx.current_season[0] if self.ctx.current_season else None
        for y in sorted(self.ctx.season_config.years(), reverse=True):
            self.years_flow.addWidget(YearCard(y, y == self.selected_year, y == cur, lambda yy=y: self._select_year(yy)))
        self.years_flow.addWidget(AddYearCard(self.add_year))

    def _select_year(self, y: int):
        self.selected_year = y
        self.rebuild_year_cards()
        self.load_rows()

    def load_rows(self):
        y = self.selected_year
        if y is None:
            self._edit_rows = []
            self.season_grid.set_items([])
            self.editor.setVisible(False)
            return
        sched = self.ctx.season_config.get_year(y)
        base = sched.seasons if sched else default_seasons_for(y)
        by = {p.name: p for p in base}
        defaults = {p.name: p for p in default_seasons_for(y)}
        self._edit_rows = [SeasonPeriod(n, (by.get(n) or defaults[n]).start_date, (by.get(n) or defaults[n]).end_date)
                           for n in SEASON_NAMES]
        self.season_grid.set_items(self._edit_rows)
        self.lbl_editor_title.setText(f"{y}년 시즌 일정")
        self.editor.setVisible(True)

    def update_current_info(self):
        cs = self.ctx.current_season
        ds = self.ctx.today.strftime("%Y-%m-%d")
        self.lbl_current.setText(f"현재 시즌: {cs[0]}년 {cs[1]}  ·  기준 날짜 {ds}" if cs
                                 else f"오늘({ds})이 포함되는 시즌이 없습니다. 연도별 시작일·종료일을 확인해주세요.")

    def add_year(self):
        cfg = self.ctx.season_config
        years = cfg.years()
        ny = years[-1] + 1 if years else self.ctx.today.year
        while cfg.has_year(ny):
            ny += 1
        if not w.ask(self, f"{ny}년 시즌 일정을 기본값으로 추가하시겠습니까?\n"
                           "(1학기 3/1~6/30, 여름방학 7/1~8/31, 2학기 9/1~12/31, 겨울방학 익년 1/1~2월 말일)\n\n"
                           "추가한 뒤 각 시즌 날짜를 원하는 대로 수정하고 [💾 시즌 일정 저장]을 누르세요.", "연도 추가"):
            return
        cfg.ensure_year(ny)
        self.ctx.save_seasons()
        self.selected_year = ny
        self.rebuild_year_cards()
        self.load_rows()
        self.ctx.win.detect_and_apply_current_season(initial=True)

    def delete_year(self):
        y = self.selected_year
        if y is None or not self.ctx.season_config.has_year(y):
            w.warn(self, "삭제할 연도 일정이 없습니다.", "연도 삭제")
            return
        if not w.ask_warn(self, f"{y}년 시즌 일정을 삭제하시겠습니까?\n(해당 시즌의 좌석 데이터 자체는 그대로 보관됩니다.)", "연도 삭제"):
            return
        self.ctx.season_config.remove_year(y)
        self.ctx.save_seasons()
        self.load_season_settings_ui()
        self.ctx.win.detect_and_apply_current_season(initial=True)
        w.info(self, f"{y}년 시즌 일정을 삭제했습니다.", "완료")

    def save_season_schedule(self):
        y = self.selected_year
        if y is None:
            w.warn(self, "연도 카드를 먼저 선택하세요.", "저장 실패")
            return
        for p in self._edit_rows:
            if p.end_date < p.start_date:
                w.warn(self, f"[{p.name}] 종료일이 시작일보다 빠릅니다.", "저장 실패")
                return
        ordered = sorted(self._edit_rows, key=lambda p: p.start_date)
        for a, b in zip(ordered, ordered[1:]):
            if b.start_date <= a.end_date:
                if not w.ask_warn(self, "시즌 기간이 서로 겹칩니다. 그래도 저장하시겠습니까?\n(겹치는 날짜는 먼저 시작하는 시즌으로 판별됩니다.)", "겹침 확인"):
                    return
                break
        sched = self.ctx.season_config.ensure_year(y)
        sched.seasons = [SeasonPeriod(p.name, p.start_date, p.end_date) for p in self._edit_rows]
        self.ctx.save_seasons()
        self.ctx.win.detect_and_apply_current_season(initial=True)
        self.rebuild_year_cards()
        self.update_current_info()
        w.info(self, f"{y}년 시즌 일정을 저장했습니다.", "완료")

    def _resolution_changed(self, text: str):
        if self.ctx.win is None or not self.ctx.win.isVisible():
            return
        sizes = {"기본 (1600 x 900)": (1600, 900), "소형 (1024 x 768)": (1024, 768),
                 "중형 (1200 x 780)": (1200, 780), "대형 (1920 x 1080)": (1920, 1080)}
        if text in sizes:
            self.ctx.win.fit_to_screen_and_center(*sizes[text])


def _describe(label: str, entered: str, sheet_id: str) -> Optional[str]:
    if not entered:
        return None
    if sheet_id:
        return f"· {label} 신청은 별도 시트에서 받아옵니다. (시트 ID: {sheet_id})"
    return (f"· {label} 칸의 주소로는 시트를 읽을 수 없어, {label} 신청도 '상상Lab 신청 폼 URL' 시트에서만 받아옵니다.\n  "
            + ("폼 편집 화면의 [응답] → [시트에서 보기]로 열리는 " if gi.is_form_url(entered) else "")
            + "스프레드시트 주소(docs.google.com/spreadsheets/d/...)를 붙여넣어 주세요.")
