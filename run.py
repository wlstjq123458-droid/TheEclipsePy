"""
동서대학교 좌석 및 기자재 관리 시스템 — Python(PySide6) 버전 진입점.

실행:
    pip install -r requirements.txt
    python run.py
"""
import sys

from PySide6.QtWidgets import QApplication

from app.main_window import MainWindow
from app import theme


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(theme.STYLE_SHEET)  # 모달 다이얼로그 등 메인 창 바깥의 위젯도 같은 테마를 쓰게 한다
    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
