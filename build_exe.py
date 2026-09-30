"""
설치용 실행파일(.exe) 빌드 스크립트.

사용법:
    pip install pyinstaller
    python build_exe.py

결과물: dist/SeatManagerApp-Python.exe (단일 파일, 콘솔창 없음)
Inno Setup 등으로 감싸 설치파일(Setup.exe)을 만들고 싶으면 C# 버전의
installer/SeatManagerApp.iss를 참고해 dist 폴더를 Source로 지정하면 된다.
"""
import PyInstaller.__main__

PyInstaller.__main__.run([
    "run.py",
    "--name=SeatManagerApp-Python",
    "--onefile",
    "--windowed",  # 콘솔창 없이 실행 (오류가 나면 --console으로 바꿔서 원인을 본다)
    "--noconfirm",
    "--clean",
])
