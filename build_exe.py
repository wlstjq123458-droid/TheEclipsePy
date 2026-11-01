"""
실행파일 + 설치파일 빌드 스크립트.

사용법:
    pip install -r requirements.txt pyinstaller
    python build_exe.py            # dist/SeatManagerApp-Python/ (폴더형 실행파일)
    python build_exe.py --setup    # 위 + Inno Setup으로 installer_output/SeatManagerApp-Python_Setup_v*.exe

폴더형(--onedir)으로 만든다 — 한 파일(--onefile)은 실행할 때마다 임시 폴더에 풀어서 켜지는 데 오래 걸린다.
Inno Setup 6(ISCC.exe)이 설치되어 있어야 --setup이 동작한다.
"""
import os
import shutil
import subprocess
import sys

import PyInstaller.__main__

ROOT = os.path.dirname(os.path.abspath(__file__))
NAME = "SeatManagerApp-Python"


def build_exe() -> None:
    PyInstaller.__main__.run([
        os.path.join(ROOT, "run.py"),
        f"--name={NAME}",
        "--onedir",
        "--windowed",  # 콘솔창 없이 실행 (오류가 나면 --console으로 바꿔서 원인을 본다)
        "--noconfirm",
        "--clean",
        f"--distpath={os.path.join(ROOT, 'dist')}",
        f"--workpath={os.path.join(ROOT, 'build')}",
        f"--specpath={ROOT}",
        # 기자재 데이터 양식(엑셀) 템플릿
        f"--add-data={os.path.join(ROOT, 'assets')}{os.pathsep}assets",
        # 아이콘 글꼴 사본을 만들 때 fontTools가 글꼴 표 모듈을 이름으로 불러온다
        "--collect-submodules=fontTools.ttLib.tables",
        # 구글 시트 API 정의 파일(discovery 문서)
        "--collect-data=googleapiclient",
    ])


def find_iscc() -> str:
    candidates = [
        shutil.which("ISCC.exe") or "",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Inno Setup 6", "ISCC.exe"),
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
    ]
    for c in candidates:
        if c and os.path.exists(c):
            return c
    raise SystemExit("Inno Setup 6(ISCC.exe)을 찾지 못했습니다. https://jrsoftware.org/isdl.php 에서 설치하세요.")


def build_setup() -> None:
    iss = os.path.join(ROOT, "installer", f"{NAME}.iss")
    subprocess.run([find_iscc(), iss], check=True)


if __name__ == "__main__":
    build_exe()
    if "--setup" in sys.argv:
        build_setup()
