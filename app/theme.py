"""
C# / WPF 버전(MainWindow.xaml)과 같은 색상·스타일.
색상 값은 XAML의 SidebarBtn/SidebarBtnActive/ActionBarBtn/ModalBtn/IconBtn 스타일과
각 화면 Border 색을 그대로 옮겼다. WPF 기본 컨트롤(TextBox/ComboBox/Button 등)을
스타일 없이 쓴 곳은 Windows 10 WPF 기본 모양에 맞춘다.
"""

WINDOW_BG = "#F3F4F6"
CONTENT_BG = "#F9FAFB"

SIDEBAR_BG = "#0A1C3E"

TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#374151"
TEXT_MUTED = "#6B7280"
TEXT_FAINT = "#9CA3AF"

BLUE = "#2563EB"
GREEN = "#10B981"
RED = "#EF4444"

# 아이콘(이모지) 글꼴 — WPF는 컬러 이모지를 못 그려서 Segoe UI Emoji의 단색 윤곽선 글리프로 그린다.
# 같은 모양이 나오도록 Segoe UI Emoji에서 색상 표(COLR/CPAL)만 뺀 사본을 만들어 쓴다 (load_icon_font).
# 사본을 못 만들면 다음 순서의 Segoe UI Symbol(단색 기호)로 그려진다.
ICON_FONT = "Segoe UI Emoji Mono"
ICON_FAMILIES = f'"{ICON_FONT}", "Segoe UI Symbol", "Segoe UI", "Malgun Gothic"'

_BASE_STYLE = """
QWidget {
    font-family: "Segoe UI", "Malgun Gothic";
    font-size: 12px;
}
QMainWindow { background: #F3F4F6; }
QToolTip { background: #FFFFE1; color: #000000; border: 1px solid #767676; }

/* ---- WPF 기본 TextBox ---- */
QLineEdit, QTextEdit, QPlainTextEdit {
    background: #FFFFFF;
    border: 1px solid #ABADB3;
    color: #000000;
    selection-background-color: #3399FF;
    selection-color: #FFFFFF;
}
QLineEdit:hover, QTextEdit:hover { border-color: #7EB4EA; }
QLineEdit:focus, QTextEdit:focus { border-color: #569DE5; }
QLineEdit:read-only { color: #000000; }

/* ---- WPF 기본 ComboBox ---- */
QComboBox {
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #F0F0F0, stop:1 #E5E5E5);
    border: 1px solid #ACACAC;
    color: #000000;
    padding: 3px 4px;
}
QComboBox:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 #ECF4FC, stop:1 #DCECFC); border-color: #7EB4EA; }
QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 20px; }
QComboBox::down-arrow { image: url(@ASSETS@/arrow_down.png); width: 9px; height: 6px; }
QComboBox QAbstractItemView { background: #FFFFFF; border: 1px solid #ACACAC; selection-background-color: #3399FF; color: #000000; }

/* ---- WPF 기본 DatePicker ---- */
QDateEdit {
    background: #FFFFFF;
    border: 1px solid #ABADB3;
    color: #000000;
    padding: 2px 4px;
}
QDateEdit:hover { border-color: #7EB4EA; }
QDateEdit::drop-down { subcontrol-origin: padding; subcontrol-position: center right; width: 22px; border: none; }
QDateEdit::down-arrow { image: url(@ASSETS@/calendar.png); width: 14px; height: 14px; }

/* ---- WPF 기본 Button (스타일을 따로 주지 않은 버튼) ---- */
QPushButton {
    background: #DDDDDD;
    border: 1px solid #707070;
    color: #000000;
    padding: 1px 6px;
}
QPushButton:hover { background: #BEE6FD; border-color: #3C7FB1; }
QPushButton:pressed { background: #C4E5F6; border-color: #2C628B; }
QPushButton:disabled { background: #F4F4F4; border-color: #ADB2B5; color: #838383; }

QCheckBox { color: #000000; }
QScrollArea { border: none; background: transparent; }
QSplitter::handle { background: transparent; }

/* ---- WPF(Windows 10) 기본 ScrollBar ---- */
QScrollBar:vertical { background: #F0F0F0; width: 17px; margin: 17px 0 17px 0; border: none; }
QScrollBar::handle:vertical { background: #CDCDCD; min-height: 20px; margin: 0 1px; }
QScrollBar::handle:vertical:hover { background: #A6A6A6; }
QScrollBar::handle:vertical:pressed { background: #606060; }
QScrollBar::sub-line:vertical { height: 17px; subcontrol-position: top; subcontrol-origin: margin; background: #F0F0F0; border: none; }
QScrollBar::add-line:vertical { height: 17px; subcontrol-position: bottom; subcontrol-origin: margin; background: #F0F0F0; border: none; }
QScrollBar::up-arrow:vertical { image: url(@ASSETS@/arrow_up.png); width: 9px; height: 6px; }
QScrollBar::down-arrow:vertical { image: url(@ASSETS@/arrow_down.png); width: 9px; height: 6px; }
QScrollBar:horizontal { background: #F0F0F0; height: 17px; margin: 0 17px 0 17px; border: none; }
QScrollBar::handle:horizontal { background: #CDCDCD; min-width: 20px; margin: 1px 0; }
QScrollBar::handle:horizontal:hover { background: #A6A6A6; }
QScrollBar::handle:horizontal:pressed { background: #606060; }
QScrollBar::sub-line:horizontal { width: 17px; subcontrol-position: left; subcontrol-origin: margin; background: #F0F0F0; border: none; }
QScrollBar::add-line:horizontal { width: 17px; subcontrol-position: right; subcontrol-origin: margin; background: #F0F0F0; border: none; }
QScrollBar::left-arrow:horizontal { image: url(@ASSETS@/arrow_left.png); width: 6px; height: 9px; }
QScrollBar::right-arrow:horizontal { image: url(@ASSETS@/arrow_right.png); width: 6px; height: 9px; }
QScrollBar::add-page, QScrollBar::sub-page { background: none; }
"""


def _draw_assets(folder: str) -> None:
    """콤보박스 화살표·스크롤바 화살표·달력 아이콘을 WPF 모양으로 그려 PNG로 둔다 (실행할 때마다 다시 만든다)."""
    import os
    from PySide6.QtCore import Qt, QPointF, QRectF
    from PySide6.QtGui import QFont, QImage, QPainter, QPen, QColor, QPolygonF

    os.makedirs(folder, exist_ok=True)
    gray = QColor("#606060")

    def chevron(name, w, h, pts):
        img = QImage(w * 4, h * 4, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QPen(gray, 4.4, Qt.SolidLine, Qt.FlatCap, Qt.MiterJoin))
        p.drawPolyline(QPolygonF([QPointF(x * 4, y * 4) for x, y in pts]))
        p.end()
        img.save(os.path.join(folder, name))

    chevron("arrow_down.png", 9, 6, [(0.6, 0.8), (4.5, 4.8), (8.4, 0.8)])
    chevron("arrow_up.png", 9, 6, [(0.6, 5.2), (4.5, 1.2), (8.4, 5.2)])
    chevron("arrow_left.png", 6, 9, [(5.2, 0.6), (1.2, 4.5), (5.2, 8.4)])
    chevron("arrow_right.png", 6, 9, [(0.8, 0.6), (4.8, 4.5), (0.8, 8.4)])

    img = QImage(56, 56, QImage.Format_ARGB32)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor("#5F5F5F"), 3))
    p.setBrush(QColor("#FFFFFF"))
    p.drawRect(QRectF(4, 8, 48, 44))
    p.fillRect(QRectF(4, 8, 48, 10), QColor("#5F5F5F"))
    # WPF DatePicker 아이콘처럼 달력 안에 "15"를 적는다
    font = QFont("Segoe UI")
    font.setPixelSize(27)
    font.setBold(True)
    p.setFont(font)
    p.setPen(QColor("#5F5F5F"))
    p.drawText(QRectF(4, 18, 48, 34), Qt.AlignCenter, "15")
    p.end()
    img.save(os.path.join(folder, "calendar.png"))


def load_icon_font(folder: str) -> bool:
    """Windows의 Segoe UI Emoji에서 컬러 표를 빼고 이름을 바꾼 사본(ICON_FONT)을 만들어 앱 글꼴로 등록한다.
    WPF가 이모지를 그리는 단색 윤곽선 모양과 똑같아진다. 한 번 만든 사본은 다시 쓴다."""
    import os
    from PySide6.QtGui import QFontDatabase

    path = os.path.join(folder, "seguiemj-mono-2.ttf")
    if not os.path.exists(path):
        src = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "seguiemj.ttf")
        if not os.path.exists(src):
            return False
        try:
            from fontTools.ttLib import TTFont
            font = TTFont(src)
            for tag in ("COLR", "CPAL", "SVG ", "CBDT", "CBLC", "sbix", "DSIG"):
                if tag in font:
                    del font[tag]
            # WPF가 Segoe UI Emoji로 그리는 영역(기타 기호 U+2600~, 이모지)만 남긴다.
            # 숫자·화살표·◀▶ 같은 도형은 원본처럼 Segoe UI / Segoe UI Symbol에서 그려진다.
            for table in font["cmap"].tables:
                table.cmap = {cp: g for cp, g in table.cmap.items() if cp >= 0x2600}
            for rec in font["name"].names:
                if rec.nameID in (1, 16):
                    rec.string = ICON_FONT
                elif rec.nameID in (4,):
                    rec.string = ICON_FONT
                elif rec.nameID == 6:
                    rec.string = ICON_FONT.replace(" ", "")
            os.makedirs(folder, exist_ok=True)
            tmp = path + ".tmp"
            font.save(tmp)
            os.replace(tmp, path)
        except Exception:  # noqa: BLE001 — 글꼴을 못 만들면 Segoe UI Symbol로 대신 그린다
            return False
    return QFontDatabase.addApplicationFont(path) >= 0


def build_style_sheet(asset_folder: str) -> str:
    _draw_assets(asset_folder)
    return _BASE_STYLE.replace("@ASSETS@", asset_folder.replace("\\", "/"))


# 에셋 없이 쓰는 경우(테스트 등)를 위한 기본값 — 화살표 그림만 빠진다
STYLE_SHEET = _BASE_STYLE.replace("url(@ASSETS@/", "url(:/missing/")
