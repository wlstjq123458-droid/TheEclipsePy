"""
WPF 원본(MainWindow.xaml)의 공용 모양을 그대로 흉내 내는 위젯 모음.

- 버튼: ActionBarBtn / ModalBtn / IconBtn / 기본 Button(+CornerRadius 리소스) 스타일
- Card: 흰 배경 + 테두리 + 둥근 모서리 Border
- AlertCard: "승인 대기" 알림 카드
- DataGrid: WPF DataGrid(헤더 그라데이션, 검은 가로줄, 행 높이, 줄무늬, RowDetails, 다시 누르면 선택 해제)
- OverlayDialog: 창 전체를 반투명 검정으로 덮고 가운데 흰 카드를 띄우는 모달 (ModalSeatDetails 등)
- FlowLayout: WrapPanel
"""
from __future__ import annotations

import itertools
from typing import Callable, Optional

from PySide6.QtCore import Qt, QRect, QSize, QPoint, Signal, QEvent, QObject
from PySide6.QtGui import QColor, QPainter, QPen, QFont, QLinearGradient, QBrush
from PySide6.QtWidgets import (
    QWidget, QFrame, QLabel, QPushButton, QHBoxLayout, QVBoxLayout, QLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QStyledItemDelegate,
    QStyleOptionViewItem, QStyle, QDialog, QGraphicsDropShadowEffect, QMessageBox,
    QSizePolicy, QWidgetItem, QGraphicsView, QGraphicsScene,
)

from . import theme

_ids = itertools.count(1)


def _uid(prefix: str) -> str:
    return f"{prefix}{next(_ids)}"


def _blend(hex_color: str, toward: str, amount: float) -> str:
    """hex_color를 toward 쪽으로 amount(0~1)만큼 섞는다. WPF의 Opacity 0.88 같은 효과를 흉내 낼 때 쓴다."""
    a, b = QColor(hex_color), QColor(toward)
    r = round(a.red() + (b.red() - a.red()) * amount)
    g = round(a.green() + (b.green() - a.green()) * amount)
    bl = round(a.blue() + (b.blue() - a.blue()) * amount)
    return QColor(r, g, bl).name()


# ====================================================================== 글자
def label(text: str = "", size: int = 12, bold: bool = False, color: str = "#000000",
          weight: Optional[int] = None, wrap: bool = False, icon: bool = False) -> QLabel:
    lbl = QLabel(text)
    w = weight if weight is not None else (700 if bold else 400)
    family = f'font-family: {theme.ICON_FAMILIES};' if icon else ""
    lbl.setStyleSheet(
        f"QLabel {{ {family} font-size:{size}px; font-weight:{w}; color:{color}; background:transparent; border:none; }}"
    )
    if wrap:
        lbl.setWordWrap(True)
    return lbl


def icon_text(text: str) -> str:
    """버튼 글자 안의 이모지를 단색 기호 글꼴로 보이게 하는 데 쓰는 글꼴 목록(QSS용)."""
    return theme.ICON_FAMILIES


class _InsetBackground(QObject):
    def __init__(self, owner: QWidget, margin: int, outer: str, inner: str):
        super().__init__(owner)
        self.margin, self.outer, self.inner = margin, QColor(outer), QColor(inner)

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Paint:
            p = QPainter(obj)
            m = self.margin
            p.fillRect(obj.rect(), self.outer)
            p.fillRect(obj.rect().adjusted(m, m, -m, -m), self.inner)
            p.end()
        return False


def inset_background(page: QWidget, margin: int = 20, outer: str = "#F3F4F6", inner: str = "#F9FAFB") -> None:
    """XAML <Grid Background="#F9FAFB" Margin="20"> — 창 배경(#F3F4F6) 위에 20px 안쪽으로 화면 배경을 깐다."""
    page.installEventFilter(_InsetBackground(page, margin, outer, inner))


# ====================================================================== 버튼
def _apply(btn: QPushButton, css: str, cursor: bool = True) -> QPushButton:
    name = _uid("btn")
    btn.setObjectName(name)
    btn.setStyleSheet(css.replace("#ID", f"QPushButton#{name}"))
    if cursor:
        btn.setCursor(Qt.PointingHandCursor)
    return btn


def action_btn(text: str, padding: tuple[int, int] = (8, 15), font_size: int = 12,
               bg: str = "#FFFFFF", fg: str = "#374151", border: str = "#D1D5DB",
               weight: int = 600, on_click: Optional[Callable] = None) -> QPushButton:
    """XAML ActionBarBtn: 흰 배경, 회색 테두리, 둥근 모서리 6, 마우스를 올리면 옅은 회색."""
    btn = QPushButton(text)
    v, h = padding
    hover_bg = "#F9FAFB" if bg.upper() == "#FFFFFF" else bg
    hover_border = "#9CA3AF" if bg.upper() == "#FFFFFF" else border
    _apply(btn, f"""
        #ID {{ background:{bg}; color:{fg}; border:1px solid {border}; border-radius:6px;
               padding:{v}px {h}px; font-size:{font_size}px; font-weight:{weight};
               font-family:{icon_text(text)}; }}
        #ID:hover {{ background:{hover_bg}; border-color:{hover_border}; }}
        #ID:disabled {{ color:{_blend(fg, "#FFFFFF", 0.5)}; border-color:{_blend(border, "#FFFFFF", 0.5)}; background:{_blend(bg, "#FFFFFF", 0.5)}; }}
    """)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def modal_btn(text: str, bg: str = "#2563EB", fg: str = "#FFFFFF", padding: tuple[int, int] = (8, 18),
              font_size: int = 13, weight: int = 700, on_click: Optional[Callable] = None,
              min_h: int = 0, min_w: int = 0) -> QPushButton:
    """XAML ModalBtn: 테두리 없는 색 버튼, 둥근 모서리 6, 마우스를 올리면 살짝 흐려진다(Opacity 0.88)."""
    btn = QPushButton(text)
    v, h = padding
    _apply(btn, f"""
        #ID {{ background:{bg}; color:{fg}; border:none; border-radius:6px; padding:{v}px {h}px;
               font-size:{font_size}px; font-weight:{weight}; font-family:{icon_text(text)}; }}
        #ID:hover {{ background:{_blend(bg, "#FFFFFF", 0.12)}; }}
        #ID:pressed {{ background:{_blend(bg, "#FFFFFF", 0.25)}; }}
        #ID:disabled {{ background:{_blend(bg, "#FFFFFF", 0.5)}; }}
    """)
    if min_h:
        btn.setMinimumHeight(min_h)
    if min_w:
        btn.setMinimumWidth(min_w)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def icon_btn(text: str = "✕", size: int = 28, font_size: int = 16, on_click: Optional[Callable] = None) -> QPushButton:
    """XAML IconBtn: 투명 정사각형, 마우스를 올리면 옅은 회색."""
    btn = QPushButton(text)
    btn.setFixedSize(size, size)
    _apply(btn, f"""
        #ID {{ background:transparent; color:#111827; border:none; border-radius:6px; padding:0;
               font-size:{font_size}px; }}
        #ID:hover {{ background:#E5E7EB; }}
        #ID:pressed {{ background:#D1D5DB; }}
    """)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def flat_btn(text: str, bg: str, fg: str = "#FFFFFF", padding: tuple[int, int] = (4, 12),
             radius: int = 4, font_size: int = 12, weight: int = 700, border: Optional[str] = None,
             on_click: Optional[Callable] = None) -> QPushButton:
    """
    XAML에서 Background/Foreground만 바꾸고 <Button.Resources>로 CornerRadius를 준 버튼.
    WPF 기본 버튼 템플릿을 그대로 쓰므로 마우스를 올리면 배경이 하늘색(#BEE6FD)으로 바뀐다 — 원본과 같게 둔다.
    """
    btn = QPushButton(text)
    v, h = padding
    b = f"1px solid {border}" if border else "none"
    _apply(btn, f"""
        #ID {{ background:{bg}; color:{fg}; border:{b}; border-radius:{radius}px; padding:{v}px {h}px;
               font-size:{font_size}px; font-weight:{weight}; font-family:{icon_text(text)}; }}
        #ID:hover {{ background:#BEE6FD; border:1px solid #3C7FB1; }}
        #ID:pressed {{ background:#C4E5F6; border:1px solid #2C628B; }}
        #ID:disabled {{ background:#F4F4F4; color:{fg}; border:none; }}
    """)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def text_close_btn(font_size: int = 24, padding: int = 5, on_click: Optional[Callable] = None) -> QPushButton:
    """<Button Background=Transparent BorderThickness=0><TextBlock Text="✕" FontSize=.../></Button> — 마우스를 올리면 WPF 기본 하늘색."""
    btn = QPushButton("✕")
    _apply(btn, f"""
        #ID {{ background:transparent; color:#111827; border:none; padding:{padding}px; font-size:{font_size}px; font-weight:400; }}
        #ID:hover {{ background:#BEE6FD; border:1px solid #3C7FB1; }}
        #ID:pressed {{ background:#C4E5F6; border:1px solid #2C628B; }}
    """)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


def wpf_btn(text: str, width: int = 0, height: int = 0, bg: Optional[str] = None, fg: Optional[str] = None,
            bold: bool = False, on_click: Optional[Callable] = None) -> QPushButton:
    """스타일을 주지 않은 WPF 기본 Button (대화상자의 [취소] 등). bg를 주면 그 색으로 칠한다."""
    btn = QPushButton(text)
    if width:
        btn.setFixedWidth(width)
    if height:
        btn.setFixedHeight(height)
    if bg:
        _apply(btn, f"""
            #ID {{ background:{bg}; color:{fg or '#000000'}; border:1px solid #707070; padding:1px 6px;
                   font-weight:{700 if bold else 400}; }}
            #ID:hover {{ background:#BEE6FD; border-color:#3C7FB1; }}
            #ID:pressed {{ background:#C4E5F6; border-color:#2C628B; }}
            #ID:disabled {{ background:#F4F4F4; border-color:#ADB2B5; color:#838383; }}
        """, cursor=False)
    elif bold:
        _apply(btn, "#ID { font-weight:700; }", cursor=False)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


# ====================================================================== 카드
class Card(QFrame):
    """흰 배경 + 테두리 + 둥근 모서리 Border."""

    def __init__(self, bg: str = "#FFFFFF", border: str = "#E5E7EB", radius: int = 8,
                 padding: int | tuple = 10, border_width: float = 1, sides: Optional[str] = None):
        super().__init__()
        name = _uid("card")
        self.setObjectName(name)
        bw = f"{border_width}px"
        if sides:  # "left" 처럼 한쪽만 테두리
            border_css = f"border:none; border-{sides}:{bw} solid {border};"
        else:
            border_css = f"border:{bw} solid {border};"
        self.setStyleSheet(f"QFrame#{name} {{ background:{bg}; {border_css} border-radius:{radius}px; }}")
        if isinstance(padding, int):
            padding = (padding, padding, padding, padding)
        elif len(padding) == 2:
            padding = (padding[1], padding[0], padding[1], padding[0])
        self._padding = padding

    def vbox(self, spacing: int = 0) -> QVBoxLayout:
        lay = QVBoxLayout(self)
        lay.setContentsMargins(*self._padding)
        lay.setSpacing(spacing)
        return lay

    def hbox(self, spacing: int = 0) -> QHBoxLayout:
        lay = QHBoxLayout(self)
        lay.setContentsMargins(*self._padding)
        lay.setSpacing(spacing)
        return lay


class AlertCard(QFrame):
    """
    승인 대기 알림 카드 (아이콘 + 제목 / 건수 / 안내 세 줄).
    헤더용(상상Lab 빨강·캐비닛 주황·기자재 빨강)과 각 탭 안의 주황 카드 모두 이걸로 만든다.
    """

    def __init__(self, icon: str, title: str, sub: str, bg: str, border: str,
                 icon_color: str, title_color: str, count_color: str, on_click: Optional[Callable] = None):
        super().__init__()
        name = _uid("alert")
        self.setObjectName(name)
        self.setStyleSheet(f"QFrame#{name} {{ background:{bg}; border:1px solid {border}; border-radius:8px; }}")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)
        lay.addWidget(label(icon, 18, color=icon_color, icon=True), 0, Qt.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addWidget(label(title, 10, bold=True, color=title_color))
        self.count = label("0건", 12, bold=True, color=count_color)
        col.addWidget(self.count)
        col.addWidget(label(sub, 9, color=title_color))
        lay.addLayout(col)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._on_click = on_click
        if on_click:
            self.setCursor(Qt.PointingHandCursor)

    def set_count(self, n: int):
        self.count.setText(f"{n}건")

    def mousePressEvent(self, e):
        if self._on_click and e.button() == Qt.LeftButton:
            self._on_click()


def orange_alert(title: str, on_click: Optional[Callable] = None) -> AlertCard:
    """각 탭 맨 위의 주황색 '○○ 승인 대기 / N건 / 빠른 확인 필요' 카드."""
    return AlertCard("🕒", title, "빠른 확인 필요", "#FFEDD5", "#FED7AA", "#EA580C", "#9A3412", "#EA580C", on_click)


class Dot(QWidget):
    """DataGrid 상태 열의 동그라미 (Ellipse 12x12)."""

    def __init__(self, color: str, size: int = 12):
        super().__init__()
        self._color = QColor(color)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawEllipse(self.rect())


# ====================================================================== WrapPanel
class FlowLayout(QLayout):
    def __init__(self, parent=None, h_spacing: int = 0, v_spacing: int = 0):
        super().__init__(parent)
        self._items: list = []
        self._h = h_spacing
        self._v = v_spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return size + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _do_layout(self, rect, test_only):
        m = self.contentsMargins()
        r = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = r.x(), r.y(), 0
        for it in self._items:
            hint = it.sizeHint()
            nx = x + hint.width() + self._h
            if nx - self._h > r.right() + 1 and line_h > 0:
                x = r.x()
                y = y + line_h + self._v
                nx = x + hint.width() + self._h
                line_h = 0
            if not test_only:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x = nx
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y() + m.bottom()


# ====================================================================== DataGrid
class Col:
    """
    DataGrid 열 정의.
    width: 고정 폭(px). stretch=True면 남는 폭을 차지한다(XAML Width="*").
    text: 행 객체 → 글자. widget: 행 객체 → 셀 위젯(Template 열).
    """

    def __init__(self, header: str, width: int = 100, stretch: bool = False, min_width: int = 0,
                 text: Optional[Callable] = None, widget: Optional[Callable] = None):
        self.header = header
        self.width = width
        self.stretch = stretch
        self.min_width = min_width
        self.text = text
        self.widget = widget


class _GridDelegate(QStyledItemDelegate):
    """WPF DataGrid 칸: 글자는 왼쪽 위, 아래쪽에 검은 가로줄, 선택된 줄은 파랑."""

    def __init__(self, grid: "DataGrid"):
        super().__init__(grid)
        self.grid = grid

    def paint(self, p: QPainter, opt: QStyleOptionViewItem, index):
        grid = self.grid
        row = index.row()
        is_detail = grid._row_kind(row) == "detail"
        selected = bool(opt.state & QStyle.State_Selected) and not is_detail
        rect = opt.rect

        if selected:
            p.fillRect(rect, QColor("#0078D7"))
        else:
            bg = grid._row_bg(row)
            if bg:
                p.fillRect(rect, QColor(bg))

        if not is_detail:
            text = index.data(Qt.DisplayRole)
            if text:
                p.setPen(QColor("#FFFFFF") if selected else QColor(grid.text_color))
                p.setFont(grid.cell_font)
                p.drawText(rect.adjusted(2, 1, -2, 0), Qt.AlignLeft | Qt.AlignTop | Qt.TextSingleLine,
                           p.fontMetrics().elidedText(str(text), Qt.ElideRight, rect.width() - 4))

        if grid.gridline_color and grid._row_kind(row) == "item" and not grid._next_is_detail(row):
            p.setPen(QPen(QColor(grid.gridline_color), 1))
            p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        elif is_detail and grid.gridline_color:
            p.setPen(QPen(QColor(grid.gridline_color), 1))
            p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())


class _GridHeader(QHeaderView):
    """WPF DataGridColumnHeader: 흰색→옅은 회색 그라데이션, 칸 사이 옅은 구분선, 글자 왼쪽."""

    def __init__(self, parent, font: QFont):
        super().__init__(Qt.Horizontal, parent)
        self._font = font
        self.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.setHighlightSections(False)
        self.setSectionsClickable(False)

    def paintSection(self, p: QPainter, rect: QRect, logical: int):
        if not rect.isValid():
            return
        p.save()
        g = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        g.setColorAt(0, QColor("#FFFFFF"))
        g.setColorAt(0.45, QColor("#F6F7F9"))
        g.setColorAt(1, QColor("#F3F4F6"))
        p.fillRect(rect, QBrush(g))
        p.setPen(QColor("#D5D5D5"))
        p.drawLine(rect.right(), rect.top() + 2, rect.right(), rect.bottom() - 2)
        p.setPen(QColor("#E5E5E5"))
        p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        text = self.model().headerData(logical, Qt.Horizontal, Qt.DisplayRole)
        p.setPen(QColor("#000000"))
        p.setFont(self._font)
        p.drawText(rect.adjusted(5, 0, -3, 0), Qt.AlignLeft | Qt.AlignVCenter, str(text or ""))
        p.restore()


class DataGrid(QTableWidget):
    """
    WPF DataGrid 흉내. set_items(list)로 행을 채운다.
    details: 행 객체 → 위젯. 행을 누르면 그 아래에 상세(RowDetails)가 펼쳐지고, 다시 누르면 접힌다.
    """

    item_selected = Signal(object)        # 선택된 행 객체 (없으면 None)
    item_double_clicked = Signal(object)

    def __init__(self, cols: list[Col], row_height: int = 40, alternating: Optional[str] = None,
                 font_size: int = 12, details: Optional[Callable] = None, multi_select: bool = False,
                 gridline_color: Optional[str] = "#000000", text_color: str = "#000000",
                 header_height: int = 23, bg: Optional[str] = None, row_bg: str = "#FFFFFF"):
        super().__init__(0, len(cols))
        self.cols = cols
        self.row_h = row_height
        self.alternating = alternating
        self.row_bg = row_bg
        self.details = details
        self.gridline_color = gridline_color
        self.text_color = text_color
        self.cell_font = QFont("Segoe UI")
        self.cell_font.setPixelSize(font_size)
        self._items: list = []
        self._rows: list[tuple[str, int]] = []   # ("item"|"detail", 항목 인덱스)
        self._expanded: Optional[int] = None

        header = _GridHeader(self, self.cell_font)
        self.setHorizontalHeader(header)
        self.setHorizontalHeaderLabels([c.header for c in cols])
        header.setFixedHeight(header_height)
        header.setStretchLastSection(False)
        for i, c in enumerate(cols):
            if c.stretch:
                header.setSectionResizeMode(i, QHeaderView.Stretch)
            else:
                header.setSectionResizeMode(i, QHeaderView.Interactive)
                self.setColumnWidth(i, c.width)
        header.setMinimumSectionSize(20)

        self.verticalHeader().setVisible(False)
        self.verticalHeader().setMinimumSectionSize(1)
        self.setShowGrid(False)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection if multi_select else QAbstractItemView.SingleSelection)
        self.setFocusPolicy(Qt.NoFocus)
        self.setWordWrap(False)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setItemDelegate(_GridDelegate(self))
        bgc = bg or "transparent"
        self.setStyleSheet(f"QTableWidget {{ background:{bgc}; border:none; }} QTableWidget::item {{ border:none; }}")
        self.viewport().setAutoFillBackground(False)

        self.itemSelectionChanged.connect(self._on_selection)
        self.cellDoubleClicked.connect(self._on_double)
        self._building = False

    # ---------------------------------------------------------------- 데이터
    def set_items(self, items: list):
        keep = None
        if self._expanded is not None and self._expanded < len(self._items):
            old = self._items[self._expanded]
            keep = next((i for i, it in enumerate(items) if it is old), None)
        self._items = list(items)
        self._expanded = keep
        self._render()

    def items(self) -> list:
        return list(self._items)

    def current_item(self):
        rows = self.selectionModel().selectedRows()
        for r in rows:
            kind, idx = self._rows[r.row()] if r.row() < len(self._rows) else ("", -1)
            if kind == "item":
                return self._items[idx]
        return None

    def selected_items(self) -> list:
        result = []
        for r in sorted({i.row() for i in self.selectionModel().selectedRows()}):
            kind, idx = self._rows[r]
            if kind == "item":
                result.append(self._items[idx])
        return result

    def clear_selection(self):
        self.clearSelection()

    # ---------------------------------------------------------------- 그리기
    def paintEvent(self, e):
        super().paintEvent(e)
        # WPF DataGrid는 열이 표 폭보다 좁아도 줄(배경·아래 가로줄)이 오른쪽 끝까지 이어진다 (빈 채움 열)
        right = self.horizontalHeader().length() - self.horizontalOffset()
        vw = self.viewport().width()
        if right >= vw or not self._rows:
            return
        p = QPainter(self.viewport())
        vh = self.viewport().height()
        for r in range(len(self._rows)):
            y = self.rowViewportPosition(r)
            h = self.rowHeight(r)
            if y + h < 0:
                continue
            if y > vh:
                break
            rect = QRect(right, y, vw - right, h)
            bg = self._row_bg(r)
            if bg:
                p.fillRect(rect, QColor(bg))
            kind = self._row_kind(r)
            if self.gridline_color and (kind == "detail" or not self._next_is_detail(r)):
                p.setPen(QPen(QColor(self.gridline_color), 1))
                p.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        p.end()

    def _row_kind(self, row: int) -> str:
        return self._rows[row][0] if 0 <= row < len(self._rows) else ""

    def _next_is_detail(self, row: int) -> bool:
        return self._row_kind(row + 1) == "detail"

    def _row_bg(self, row: int) -> Optional[str]:
        if not (0 <= row < len(self._rows)):
            return None
        kind, idx = self._rows[row]
        if kind == "detail":
            return self.row_bg
        if self.alternating and idx % 2 == 1:
            return self.alternating
        return self.row_bg

    def _render(self):
        self._building = True
        sel_obj = self._items[self._expanded] if self._expanded is not None else None
        self.clearSpans()
        self.setRowCount(0)
        self._rows = []
        for idx, it in enumerate(self._items):
            self._rows.append(("item", idx))
            if self.details is not None and self._expanded == idx:
                self._rows.append(("detail", idx))
        self.setRowCount(len(self._rows))
        for r, (kind, idx) in enumerate(self._rows):
            it = self._items[idx]
            if kind == "detail":
                self.setSpan(r, 0, 1, len(self.cols))
                w = self.details(it)
                w.setAttribute(Qt.WA_TranslucentBackground, False)
                holder = QWidget()
                hl = QVBoxLayout(holder)
                hl.setContentsMargins(4, 4, 4, 4)
                hl.addWidget(w)
                holder.setStyleSheet("background:transparent;")
                self.setCellWidget(r, 0, holder)
                self.setRowHeight(r, holder.sizeHint().height() + 2)
                continue
            self.setRowHeight(r, self.row_h)
            for c, col in enumerate(self.cols):
                cell = QTableWidgetItem("" if col.text is None else str(col.text(it) or ""))
                cell.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                self.setItem(r, c, cell)
                if col.widget is not None:
                    w = col.widget(it)
                    if w is not None:
                        holder = QWidget()
                        holder.setAttribute(Qt.WA_TranslucentBackground)
                        holder.setStyleSheet("background:transparent;")
                        hl = QHBoxLayout(holder)
                        hl.setContentsMargins(0, 0, 0, 1)
                        hl.addWidget(w)
                        self.setCellWidget(r, c, holder)
        if sel_obj is not None:
            row = next((r for r, (k, i) in enumerate(self._rows) if k == "item" and self._items[i] is sel_obj), None)
            if row is not None:
                self.selectRow(row)
        self._building = False

    # ---------------------------------------------------------------- 이벤트
    def mousePressEvent(self, e):
        # XAML DataGrid_PreviewMouseLeftButtonDown: 이미 선택된 줄을 다시 누르면 선택을 푼다 (상세도 접힌다)
        if e.button() == Qt.LeftButton:
            idx = self.indexAt(e.position().toPoint())
            if idx.isValid() and self._row_kind(idx.row()) == "item":
                if self.selectionModel().isRowSelected(idx.row()) and not (e.modifiers() & (Qt.ControlModifier | Qt.ShiftModifier)):
                    self.clearSelection()
                    return
            elif idx.isValid() and self._row_kind(idx.row()) == "detail":
                return
        super().mousePressEvent(e)

    def _on_selection(self):
        if self._building:
            return
        item = self.current_item()
        if self.details is not None:
            new_exp = self._items.index(item) if item is not None else None
            if new_exp != self._expanded:
                self._expanded = new_exp
                self._render()
        self.item_selected.emit(item)

    def _on_double(self, row, _col):
        kind, idx = self._rows[row] if row < len(self._rows) else ("", -1)
        if kind == "item":
            self.item_double_clicked.emit(self._items[idx])


def cell_wrap(widget: QWidget, align=Qt.AlignLeft | Qt.AlignVCenter, margins=(0, 0, 0, 0),
              fill_height: bool = False, fill_width: bool = False) -> QWidget:
    """DataGrid Template 칸 안에 위젯을 정렬해 넣는다.
    fill_height / fill_width: WPF 칸 안의 버튼처럼 Alignment=Stretch — 칸 높이/너비만큼 늘린다."""
    holder = QWidget()
    holder.setAttribute(Qt.WA_TranslucentBackground)
    lay = QHBoxLayout(holder)
    lay.setContentsMargins(*margins)
    if fill_height:
        widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)
        align = align & Qt.AlignHorizontal_Mask
    if fill_width:
        widget.setSizePolicy(QSizePolicy.Expanding, widget.sizePolicy().verticalPolicy())
        lay.addWidget(widget, 1, align & Qt.AlignVertical_Mask)
        return holder
    lay.addWidget(widget, 0, align)
    if not (align & Qt.AlignRight) and not (align & Qt.AlignHCenter):
        lay.addStretch()
    return holder


# ====================================================================== 오버레이 모달
class OverlayDialog(QDialog):
    """
    XAML의 Modal*(Background="#80000000" + 가운데 흰 Border CornerRadius=20 + DropShadow) 모달.
    창 전체를 반투명 검정으로 덮고 가운데에 카드를 띄운다. exec()로 띄우면 닫힐 때까지 기다린다.
    """

    def __init__(self, owner: QWidget, width: int, height: int, radius: int = 20, padding: int = 35,
                 dim: int = 128):
        super().__init__(owner.window())
        self._owner = owner.window()
        self._dim = dim
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Dialog)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch()
        row = QHBoxLayout()
        row.addStretch()
        self.card = QFrame()
        name = _uid("modal")
        self.card.setObjectName(name)
        self.card.setStyleSheet(f"QFrame#{name} {{ background:#FFFFFF; border-radius:{radius}px; }}")
        if width:
            self.card.setFixedWidth(width)
        if height:
            self.card.setFixedHeight(height)
        shadow = QGraphicsDropShadowEffect(self.card)
        shadow.setBlurRadius(25)
        shadow.setOffset(0, 0)
        shadow.setColor(QColor(0, 0, 0, 64))
        self.card.setGraphicsEffect(shadow)
        row.addWidget(self.card)
        row.addStretch()
        outer.addLayout(row)
        outer.addStretch()

        self.padding = padding
        self.body = QVBoxLayout(self.card)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(0)

    def showEvent(self, e):
        # 메인 창의 안쪽(제목 표시줄 제외) 영역을 그대로 덮는다
        w = self._owner
        top_left = w.mapToGlobal(QPoint(0, 0))
        self.setGeometry(QRect(top_left, w.size()))
        super().showEvent(e)
        self._place_floats()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, self._dim))

    def float_top_right(self, widget: QWidget, top: int, right: int):
        """레이아웃과 상관없이 카드 오른쪽 위에 위젯을 겹쳐 둔다 (XAML의 겹친 헤더 버튼)."""
        widget.setParent(self.card)
        self._floats = getattr(self, "_floats", [])
        self._floats.append((widget, top, right))
        widget.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_floats()

    def _place_floats(self):
        for widget, top, right in getattr(self, "_floats", []):
            widget.adjustSize()
            widget.move(self.card.width() - right - widget.width(), top)
            widget.raise_()

    def close_button_row(self, *buttons: QWidget, close: bool = True) -> QHBoxLayout:
        """카드 오른쪽 위 버튼 줄 (… + ✕)."""
        row = QHBoxLayout()
        row.setSpacing(10)
        row.addStretch()
        for b in buttons:
            row.addWidget(b)
        if close:
            row.addWidget(icon_btn("✕", on_click=self.reject))
        return row


# ====================================================================== Viewbox
class ViewBox(QGraphicsView):
    """
    XAML <Viewbox Stretch="Uniform">: 정해진 크기로 만든 화면을 가로세로 비율을 지킨 채
    창 크기에 맞춰 통째로 확대/축소한다 (캐비닛 현황 화면).
    """

    def __init__(self, content: QWidget, bg: str = "#F9FAFB"):
        super().__init__()
        self._content = content
        self.setScene(QGraphicsScene(self))
        self.proxy = self.scene().addWidget(content)
        self.setFrameShape(QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing | QPainter.SmoothPixmapTransform)
        self.setBackgroundBrush(QColor(bg))
        self.setStyleSheet(f"QGraphicsView {{ background:{bg}; border:none; }}")
        self.setAlignment(Qt.AlignCenter)
        self.setViewportUpdateMode(QGraphicsView.FullViewportUpdate)
        self.setAcceptDrops(True)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cw, ch = self._content.width(), self._content.height()
        if cw <= 0 or ch <= 0:
            return
        s = min(self.viewport().width() / cw, self.viewport().height() / ch)
        self.resetTransform()
        self.scale(s, s)
        self.setSceneRect(0, 0, cw, ch)
        self.centerOn(cw / 2, ch / 2)


# ====================================================================== 메시지 상자
def _box(parent, icon, title, text, buttons, default=None):
    box = QMessageBox(parent)
    box.setIcon(icon)
    box.setWindowTitle(title)
    box.setText(text)
    box.setStandardButtons(buttons)
    if default is not None:
        box.setDefaultButton(default)
    return box.exec()


def info(parent, text: str, title: str = "알림"):
    _box(parent, QMessageBox.Information, title, text, QMessageBox.Ok)


def warn(parent, text: str, title: str = "알림"):
    _box(parent, QMessageBox.Warning, title, text, QMessageBox.Ok)


def error(parent, text: str, title: str = "오류"):
    _box(parent, QMessageBox.Critical, title, text, QMessageBox.Ok)


def ask(parent, text: str, title: str, icon=QMessageBox.Question) -> bool:
    return _box(parent, icon, title, text, QMessageBox.Yes | QMessageBox.No) == QMessageBox.Yes


def ask_warn(parent, text: str, title: str) -> bool:
    return ask(parent, text, title, QMessageBox.Warning)
