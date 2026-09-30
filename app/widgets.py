"""여러 화면이 함께 쓰는 작은 위젯 모음."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QVBoxLayout, QLabel


class AlertChip(QFrame):
    """승인 대기 알림 카드. C#의 CardSangsangLabAlert/CardCabinetAlert/CardEquipmentAlert에 대응한다."""

    def __init__(self, icon: str, title: str, bg: str, border: str, text_color: str, on_click=None):
        super().__init__()
        self.setStyleSheet(
            f"AlertChip {{ background:{bg}; border:1px solid {border}; border-radius:8px; }}"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 10, 6)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet(f"background:transparent; border:none; font-size:16px; color:{text_color};")
        lay.addWidget(icon_lbl)

        text_col = QVBoxLayout()
        text_col.setSpacing(0)
        title_lbl = QLabel(title)
        title_lbl.setStyleSheet(f"background:transparent; border:none; font-size:10px; font-weight:bold; color:{text_color};")
        self.count_lbl = QLabel("0건")
        self.count_lbl.setStyleSheet(f"background:transparent; border:none; font-size:12px; font-weight:bold; color:{text_color};")
        text_col.addWidget(title_lbl)
        text_col.addWidget(self.count_lbl)
        lay.addLayout(text_col)

        self._on_click = on_click
        if on_click is not None:
            self.setCursor(Qt.PointingHandCursor)

    def set_count(self, n: int):
        self.count_lbl.setText(f"{n}건")

    def mousePressEvent(self, e):
        if self._on_click is not None:
            self._on_click()
