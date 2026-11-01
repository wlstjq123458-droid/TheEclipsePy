"""
얼굴인식 컴퓨터(또는 라즈베리파이)와 창공시스템 서버를 이어 주는 연동 프로그램.

얼굴인식 프로그램은 지금처럼 attendance.json을 쓰고 roster.json을 읽기만 하면 된다.
이 프로그램이 그 두 파일을 서버와 주고받는다.

    출결: 얼굴인식 → attendance.json → (이 프로그램) → 서버
    명단: 서버 → (이 프로그램) → roster.json → 얼굴인식

실행 (파이썬 표준 라이브러리만 쓰므로 추가 설치가 필요 없다):
    python face_bridge.py --server http://서버주소:8000 --key 연동키

연동 키는 창공시스템 [설정] → [얼굴인식 출결 연동]에서 확인한다. 키가 명령 기록에 남지 않게
환경변수 SEATMANAGER_FACE_KEY로 줘도 된다.
"""
import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request


def default_dir() -> str:
    return os.path.join(os.path.expanduser("~"), "SeatManagerApp", "face-integration")


def request(server: str, key: str, path: str, data: bytes = None) -> bytes:
    req = urllib.request.Request(server.rstrip("/") + path, data=data, headers={"X-API-Key": key})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=20) as res:
        return res.read()


def push_attendance(server: str, key: str, path: str, last_hash: str) -> str:
    """파일 내용이 바뀌었을 때만 올린다."""
    if not os.path.exists(path):
        return last_hash
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest == last_hash:
        return last_hash
    json.loads(data.decode("utf-8"))   # 얼굴인식 프로그램이 쓰는 도중이면 다음 차례에 다시 읽는다
    result = json.loads(request(server, key, "/api/face/attendance", data))
    print(f"[{time.strftime('%H:%M:%S')}] 출결 {result['records']}건 전송")
    return digest


def pull_roster(server: str, key: str, path: str) -> None:
    """바뀌었을 때만 쓴다. 쓰는 도중 얼굴인식 프로그램이 읽어도 깨지지 않게 바꿔치기한다."""
    text = json.dumps(json.loads(request(server, key, "/api/face/roster")), ensure_ascii=False, indent=2)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            if f.read() == text:
                return
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    print(f"[{time.strftime('%H:%M:%S')}] 학생 명단 갱신")


def main() -> None:
    parser = argparse.ArgumentParser(description="얼굴인식 ↔ 창공시스템 서버 연동")
    parser.add_argument("--server", required=True, help="서버 주소 (예: http://192.168.0.10:8000)")
    parser.add_argument("--key", default=os.environ.get("SEATMANAGER_FACE_KEY", ""), help="연동 키")
    parser.add_argument("--dir", default=default_dir(), help="roster.json / attendance.json이 있는 폴더")
    parser.add_argument("--interval", type=int, default=30, help="확인 주기(초)")
    parser.add_argument("--once", action="store_true", help="한 번만 주고받고 끝낸다")
    args = parser.parse_args()
    if not args.key:
        sys.exit("연동 키가 없습니다. --key 또는 환경변수 SEATMANAGER_FACE_KEY로 주세요.")

    os.makedirs(args.dir, exist_ok=True)
    attendance = os.path.join(args.dir, "attendance.json")
    roster = os.path.join(args.dir, "roster.json")
    print(f"연동 시작: {args.server} / 폴더: {args.dir}")
    last_hash = ""
    while True:
        try:
            last_hash = push_attendance(args.server, args.key, attendance, last_hash)
            pull_roster(args.server, args.key, roster)
        except urllib.error.HTTPError as ex:
            if ex.code == 401:
                sys.exit("연동 키가 올바르지 않습니다. 창공시스템 [설정]에서 키를 확인하세요.")
            print(f"[{time.strftime('%H:%M:%S')}] 서버 오류 {ex.code} — 다음 차례에 다시 시도합니다.")
        except (urllib.error.URLError, OSError, ValueError) as ex:
            print(f"[{time.strftime('%H:%M:%S')}] 연결 실패: {ex} — 다음 차례에 다시 시도합니다.")
        if args.once:
            return
        time.sleep(max(5, args.interval))


if __name__ == "__main__":
    main()
