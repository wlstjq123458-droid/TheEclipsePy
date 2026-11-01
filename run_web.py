"""
창공시스템 웹 버전 실행.

내 컴퓨터에서 테스트:
    pip install -r requirements-web.txt
    python run_web.py
    → 브라우저에서 http://127.0.0.1:8000

학교 서버에서 (자세한 절차는 README_WEB.md):
    python run_web.py --set-password
    python run_web.py --host 0.0.0.0 --port 8000
"""
import argparse
import getpass
import logging
import os
import sys


def default_data_dir() -> str:
    base = os.environ.get("APPDATA")
    return os.path.join(base, "SeatManagerApp-Web") if base else os.path.join(os.path.expanduser("~"), ".seatmanager-web")


def main() -> None:
    parser = argparse.ArgumentParser(description="창공시스템 웹 서버")
    parser.add_argument("--host", default="127.0.0.1", help="접속을 받을 주소 (서버에서는 0.0.0.0). 기본: 이 컴퓨터에서만 접속")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=default_data_dir(), help="데이터를 저장할 폴더")
    parser.add_argument("--face-dir", default="", help="얼굴인식 연동 폴더 (기본: 사용자 폴더의 SeatManagerApp/face-integration)")
    parser.add_argument("--set-password", action="store_true", help="관리자 비밀번호를 정하고 끝낸다")
    parser.add_argument("--ssl-cert", default="", help="HTTPS 인증서 파일")
    parser.add_argument("--ssl-key", default="", help="HTTPS 개인키 파일")
    args = parser.parse_args()

    # app 모듈이 데이터 폴더를 읽기 전에 정해 둔다
    os.environ["SEATMANAGER_DATA_DIR"] = os.path.abspath(args.data_dir)
    if args.face_dir:
        os.environ["SEATMANAGER_FACE_DIR"] = os.path.abspath(args.face_dir)

    from web.auth import Auth, DEFAULT_USER, MIN_PASSWORD_LENGTH

    if args.set_password:
        password = getpass.getpass(f"새 관리자({DEFAULT_USER}) 비밀번호 ({MIN_PASSWORD_LENGTH}자 이상): ")
        if password != getpass.getpass("한 번 더 입력: "):
            sys.exit("두 비밀번호가 다릅니다.")
        try:
            Auth().set_password(DEFAULT_USER, password)
        except ValueError as ex:
            sys.exit(str(ex))
        print(f"비밀번호를 저장했습니다. (아이디: {DEFAULT_USER})")
        return

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    local_only = args.host in ("127.0.0.1", "localhost", "::1")
    if not local_only and not Auth().has_admin:
        sys.exit("외부 접속을 열기 전에 관리자 비밀번호를 정해야 합니다: python run_web.py --set-password")

    from web.service import import_legacy_data
    source = import_legacy_data(os.environ["SEATMANAGER_DATA_DIR"])
    if source:
        print(f"첫 실행 — 기존 프로그램 데이터를 복사했습니다: {source}")

    import uvicorn
    from web.server import create_app

    shown = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    scheme = "https" if args.ssl_cert else "http"
    print(f"데이터 폴더: {os.environ['SEATMANAGER_DATA_DIR']}")
    print(f"브라우저에서 {scheme}://{shown}:{args.port} 을 여세요.")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning",
                ssl_certfile=args.ssl_cert or None, ssl_keyfile=args.ssl_key or None)


if __name__ == "__main__":
    main()
