"""
설정/데이터 저장 위치.

C# 버전(SeatManagerApp)과 같은 컴퓨터에서 동시에 실행될 수 있으므로,
데이터가 서로 덮어써지지 않도록 별도 폴더(SeatManagerApp-Python)를 쓴다.
C# 쪽 데이터를 가져오고 싶으면 [데이터 관리] 탭의 엑셀/CSV 가져오기를 쓰면 된다
(C# 쪽에서 엑셀로 추출한 뒤 이 프로그램으로 불러오는 방식).
"""
import os

APP_DIR_NAME = "SeatManagerApp-Python"


def config_dir() -> str:
    # 웹 서버는 SEATMANAGER_DATA_DIR로 자기 데이터 폴더를 따로 지정한다
    path = os.environ.get("SEATMANAGER_DATA_DIR") or os.path.join(
        os.environ.get("APPDATA") or os.path.expanduser("~"), APP_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def seats_path() -> str:
    return os.path.join(config_dir(), "seats.json")


def appstate_path() -> str:
    return os.path.join(config_dir(), "appstate.json")


def seasons_path() -> str:
    return os.path.join(config_dir(), "seasons.json")


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def google_service_account_path() -> str:
    return os.path.join(config_dir(), "google-service-account.json")


def face_integration_dir() -> str:
    """얼굴인식 프로그램(insightface-attendance)과 주고받는 파일 위치.
    C# 버전과 똑같이 %USERPROFILE%\\SeatManagerApp\\face-integration 을 쓴다 —
    같은 컴퓨터에서 두 프로그램(C#/Python 중 어느 쪽이든)과 얼굴인식 프로그램이 이 폴더로 통신하게 하기 위해서다."""
    path = os.environ.get("SEATMANAGER_FACE_DIR") or os.path.join(
        os.path.expanduser("~"), "SeatManagerApp", "face-integration")
    os.makedirs(path, exist_ok=True)
    return path


def roster_path() -> str:
    return os.path.join(face_integration_dir(), "roster.json")


def attendance_path() -> str:
    return os.path.join(face_integration_dir(), "attendance.json")


# 좌석 대시보드의 [학기] 콤보에 쓰는 4개 시즌 이름 (C# SeasonConfig.SeasonNames와 동일한 순서)
SEASON_NAMES = ["1학기", "여름방학", "2학기", "겨울방학"]
