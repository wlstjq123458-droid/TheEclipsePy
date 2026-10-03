"""
동서대학교 좌석 및 기자재 관리 시스템 — Python(PySide6) 버전 진입점.

실행:
    pip install -r requirements.txt
    python run.py
"""
import os
import sys

# WPF는 이모지를 단색 기호로 그린다 — Qt가 컬러 이모지 글꼴로 바꿔 그리지 않게 한다 (QApplication 만들기 전에 정해야 한다)
os.environ.setdefault("QT_DISABLE_EMOJI_SEGMENTER", "1")

from PySide6.QtCore import QTranslator, QLibraryInfo, QLocale
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from app import theme, config
from app.context import AppContext
from app.main_window import MainWindow


def create_app(argv=None) -> QApplication:
    app = QApplication(argv if argv is not None else sys.argv)
    app.setStyle("Fusion")
    font = QFont("Segoe UI")
    font.setPixelSize(12)
    app.setFont(font)
    assets = os.path.join(config.config_dir(), "ui_assets")
    theme.load_icon_font(assets)
    app.setStyleSheet(theme.build_style_sheet(assets))
    # 메시지 상자 버튼(예/아니요/확인)을 한국어로 — WPF MessageBox가 Windows 언어를 따르는 것과 같게
    tr = QTranslator(app)
    if tr.load(QLocale(QLocale.Korean), "qtbase", "_", QLibraryInfo.path(QLibraryInfo.TranslationsPath)):
        app.installTranslator(tr)
    app._qt_tr = tr  # noqa: SLF001 (가비지 컬렉션 방지)
    return app


def main():
    app = create_app()
    ctx = AppContext()
    win = MainWindow(ctx)
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
