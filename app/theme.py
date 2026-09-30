"""
C# / WPF 버전(MainWindow.xaml)과 같은 색상·스타일을 쓰는 전역 테마.
색상 값은 XAML의 SidebarBtn/SidebarBtnActive/ActionBarBtn 스타일과 각 화면의 Border 색을 그대로 옮겼다.
"""

# ---- 색상 토큰 (XAML 색상값 그대로) ----
WINDOW_BG = "#F3F4F6"
CONTENT_BG = "#F9FAFB"

SIDEBAR_BG = "#0A1C3E"
SIDEBAR_HOVER_BG = "#111827"
SIDEBAR_HOVER_BORDER = "#3B82F6"
SIDEBAR_ACTIVE_BG = "#2563EB"
SIDEBAR_ACTIVE_BORDER = "#60A5FA"
SIDEBAR_TEXT = "#E5E7EB"
SIDEBAR_LOGO_ACCENT = "#93C5FD"

HEADER_BG = "#FFFFFF"
HEADER_BORDER = "#E5E7EB"
HEADER_TITLE = "#111827"

CARD_BG = "#FFFFFF"
CARD_BORDER = "#E5E7EB"

TEXT_PRIMARY = "#111827"
TEXT_SECONDARY = "#374151"
TEXT_MUTED = "#6B7280"
TEXT_FAINT = "#9CA3AF"

BLUE = "#2563EB"
GREEN = "#10B981"
RED = "#EF4444"
ORANGE = "#F97316"
DARK_ORANGE = "#EA580C"
YELLOW_BG = "#FEF9C3"
YELLOW_BORDER = "#EAB308"

BORDER = "#D1D5DB"


STYLE_SHEET = f"""
QWidget {{
    font-family: "Malgun Gothic", "Segoe UI";
    font-size: 13px;
    color: {TEXT_SECONDARY};
}}

QMainWindow, #ContentArea {{
    background: {WINDOW_BG};
}}

/* ---------------- 사이드바 ---------------- */
#Sidebar {{
    background: {SIDEBAR_BG};
}}
#SidebarLogo {{
    color: white;
    font-size: 22px;
    font-weight: bold;
}}
#SidebarLogoSub {{
    color: {SIDEBAR_LOGO_ACCENT};
    font-size: 14px;
    font-weight: 600;
}}
QPushButton[cssClass="sidebar"] {{
    background: transparent;
    color: {SIDEBAR_TEXT};
    border: none;
    border-left: 4px solid transparent;
    text-align: left;
    padding: 14px 20px;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton[cssClass="sidebar"]:hover {{
    background: {SIDEBAR_HOVER_BG};
    border-left: 4px solid {SIDEBAR_HOVER_BORDER};
}}
QPushButton[cssClass="sidebar"]:checked {{
    background: {SIDEBAR_ACTIVE_BG};
    color: white;
    border-left: 4px solid {SIDEBAR_ACTIVE_BORDER};
}}

/* ---------------- 헤더 ---------------- */
#Header {{
    background: {HEADER_BG};
    border-bottom: 1px solid {HEADER_BORDER};
}}
#HeaderTitle {{
    color: {HEADER_TITLE};
    font-size: 18px;
    font-weight: bold;
}}
#HeaderDate {{
    background: #F3F4F6;
    color: {TEXT_SECONDARY};
    border-radius: 6px;
    padding: 6px 10px;
    font-weight: 600;
    font-size: 12px;
}}

/* ---------------- 카드(GroupBox) ---------------- */
QGroupBox {{
    background: {CARD_BG};
    border: 1px solid {CARD_BORDER};
    border-radius: 8px;
    margin-top: 14px;
    padding: 12px;
    font-weight: bold;
    color: {TEXT_SECONDARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: {TEXT_SECONDARY};
}}

/* ---------------- 버튼 (ActionBarBtn 기본값) ---------------- */
QPushButton {{
    background: white;
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 14px;
    font-weight: 600;
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}
QPushButton:hover {{
    background: {CONTENT_BG};
    border-color: #9CA3AF;
}}
QPushButton:pressed {{
    background: #E5E7EB;
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
}}

/* ---------------- 입력 위젯 ---------------- */
QLineEdit, QComboBox, QDateEdit, QSpinBox, QTextEdit {{
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 5px 7px;
    background: white;
    selection-background-color: {BLUE};
    selection-color: white;
}}
QLineEdit:focus, QComboBox:focus, QDateEdit:focus, QSpinBox:focus, QTextEdit:focus {{
    border: 1px solid {BLUE};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}

/* ---------------- 표 ---------------- */
QTableWidget, QListWidget {{
    background: white;
    border: 1px solid {CARD_BORDER};
    border-radius: 6px;
    gridline-color: #F3F4F6;
    selection-background-color: #DBEAFE;
    selection-color: {TEXT_PRIMARY};
}}
QHeaderView::section {{
    background: {CONTENT_BG};
    color: {TEXT_MUTED};
    padding: 6px;
    border: none;
    border-bottom: 1px solid {CARD_BORDER};
    font-weight: bold;
}}
QTableWidget::item, QListWidget::item {{
    padding: 4px;
}}

/* ---------------- 스크롤 영역 ---------------- */
QScrollArea {{
    border: none;
    background: transparent;
}}

/* ---------------- 다이얼로그 ---------------- */
QDialog {{
    background: {CONTENT_BG};
}}
"""
