"""
창공시스템 웹 서버 (FastAPI). 화면은 web/static의 정적 파일이고, 여기서는 JSON API만 제공한다.

- 관리자 API: 로그인 세션 쿠키 필요. 쓰기 요청은 X-Requested-With 헤더까지 있어야 받는다(다른 사이트에서의 위조 요청 차단).
- 얼굴인식 API(/api/face/attendance, /api/face/roster): X-API-Key 연동 키로만 접근한다.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
import urllib.parse
from typing import Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from app.logic import TEMPLATE_NAME

from .auth import Auth, DEFAULT_USER
from .service import Choose, Confirm, Problem, Service

log = logging.getLogger("seatmanager.web")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
COOKIE = "sm_session"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
LOCAL_CLIENTS = ("127.0.0.1", "::1")
# 테스트용 더미 로그인: 이 컴퓨터(127.0.0.1)에서 열면 아이디·비밀번호를 아무렇게나 넣어도(빈칸도) 로그인된다.
# 다른 컴퓨터에서 접속하면 기존처럼 실제 비밀번호를 확인한다. 끄려면 False로 바꾼다.
DEMO_LOGIN = True


def _demo(request: Request) -> bool:
    return DEMO_LOGIN and _client(request) in LOCAL_CLIENTS
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

service: Service
auth: Auth


def create_app() -> FastAPI:
    global service, auth
    auth = Auth()
    service = Service()
    app = FastAPI(title="창공시스템", docs_url=None, redoc_url=None, openapi_url=None)
    threading.Thread(target=_background_loop, daemon=True, name="google-sync").start()

    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path
        if (path.startswith("/api/") and request.method not in ("GET", "HEAD")
                and path not in FACE_PATHS and request.headers.get("x-requested-with") != "SeatManager"):
            return JSONResponse({"error": "잘못된 요청입니다."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; frame-ancestors 'none'")
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"   # 수정본을 바로 받도록 매번 서버에 확인한다
        return response

    app.add_exception_handler(Problem, _on_problem)
    app.add_exception_handler(Confirm, _on_confirm)
    app.add_exception_handler(Choose, _on_choose)
    app.add_exception_handler(KeyError, _on_bad_request)
    app.add_exception_handler(ValueError, _on_bad_request)
    app.add_exception_handler(TypeError, _on_bad_request)
    app.include_router(_routes(app))
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    def index():
        return FileResponse(os.path.join(STATIC_DIR, "index.html"), headers={"Cache-Control": "no-cache"})

    return app


FACE_PATHS = ("/api/face/attendance",)


def _on_problem(_request, ex: Problem):
    return JSONResponse({"error": ex.message, "title": ex.title, "level": ex.level}, status_code=400)


def _on_confirm(_request, ex: Confirm):
    return JSONResponse({"need": "confirm", "key": ex.key, "message": ex.message, "title": ex.title, "warn": ex.warn})


def _on_choose(_request, ex: Choose):
    return JSONResponse({"need": "choose", "kind": ex.kind, "data": ex.data})


def _on_bad_request(_request, ex: Exception):
    log.warning("잘못된 요청: %r", ex)
    return JSONResponse({"error": "요청 내용이 올바르지 않습니다.", "title": "오류", "level": "error"}, status_code=400)


def require_admin(request: Request) -> str:
    user = auth.session_user(request.cookies.get(COOKIE))
    if user is None:
        raise HTTPException(401, "로그인이 필요합니다.")
    return user


def require_face_key(request: Request) -> None:
    if not auth.check_face_key(request.headers.get("x-api-key")):
        raise HTTPException(401, "연동 키가 올바르지 않습니다.")


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _login_response(request: Request, username: str, payload: Optional[dict] = None) -> JSONResponse:
    response = JSONResponse(payload or {"ok": True, "user": username})
    response.set_cookie(COOKIE, auth.create_session(username), httponly=True, samesite="strict",
                        secure=request.url.scheme == "https", max_age=12 * 3600)
    return response


def _download(data: bytes, filename: str) -> Response:
    quoted = urllib.parse.quote(filename)
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quoted}"})


async def _upload_body(request: Request) -> tuple[bytes, str]:
    """파일은 multipart 없이 본문 그대로 받는다. 파일 이름은 X-Filename 헤더로 온다."""
    length = request.headers.get("content-length")
    if length and int(length) > MAX_UPLOAD_BYTES:
        raise Problem("파일이 너무 큽니다. (최대 20MB)", "오류", "error")
    data = await request.body()
    if len(data) > MAX_UPLOAD_BYTES:
        raise Problem("파일이 너무 큽니다. (최대 20MB)", "오류", "error")
    if not data:
        raise Problem("빈 파일입니다.")
    return data, urllib.parse.unquote(request.headers.get("x-filename", "upload.xlsx"))


def _with_temp_file(data: bytes, filename: str, fn):
    suffix = os.path.splitext(filename)[1].lower()
    if suffix not in (".xlsx", ".csv", ".tsv"):
        raise Problem("엑셀(.xlsx) 또는 CSV 파일만 올릴 수 있습니다.")
    fd, path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        return fn(path)
    finally:
        os.unlink(path)


def _background_loop() -> None:
    """자동 동기화(설정 주기, 최소 15초)와 자정이 지났을 때의 현재 시즌 다시 판별."""
    last_sync, started = 0.0, False
    while True:
        try:
            with service.lock:
                service.refresh_season()
            s = service.ctx.settings
            interval = max(15, int(s.get("PollingIntervalSeconds", 60)))
            due = not started or time.time() - last_sync >= interval
            if due and service.key_exists and (s.get("PollingEnabled", True) or not started):
                started, last_sync = True, time.time()
                service.sync(silent=True)
        except Problem as ex:
            log.warning("자동 동기화: %s", ex.message)
        except Exception:  # noqa: BLE001 — 한 번 실패해도 서버는 계속 돈다
            log.exception("자동 동기화 실패")
        time.sleep(5)


def _routes(app: FastAPI):
    from fastapi import APIRouter
    r = APIRouter(prefix="/api")
    admin = [Depends(require_admin)]

    # -------------------------------------------------------- 로그인
    @r.get("/auth/status")
    def auth_status(request: Request):
        user = auth.session_user(request.cookies.get(COOKIE))
        return {"user": user, "setupRequired": not auth.has_admin and not _demo(request),
                "local": _client(request) in LOCAL_CLIENTS, "demo": _demo(request)}

    @r.post("/auth/setup")
    def auth_setup(request: Request, body: dict = Body(...)):
        # 첫 비밀번호는 서버 컴퓨터에서 직접 열었을 때만 만들 수 있다 (외부에서는 run_web.py --set-password)
        if auth.has_admin or _client(request) not in LOCAL_CLIENTS:
            raise HTTPException(403, "관리자 계정을 만들 수 없습니다.")
        try:
            auth.set_password(DEFAULT_USER, str(body.get("password", "")))
        except ValueError as ex:
            raise Problem(str(ex))
        return _login_response(request, DEFAULT_USER)

    @r.post("/auth/login")
    def auth_login(request: Request, body: dict = Body(...)):
        client = _client(request)
        wait = auth.locked_seconds(client)
        if wait:
            raise Problem(f"로그인을 여러 번 실패했습니다. {wait}초 후에 다시 시도해 주세요.", "로그인", "warning")
        username = str(body.get("username", ""))
        password = str(body.get("password", ""))
        if _demo(request):
            return _login_response(request, username or DEFAULT_USER)
        if not auth.verify(username, str(body.get("password", ""))):
            auth.record_failure(client)
            raise Problem("아이디 또는 비밀번호가 올바르지 않습니다.", "로그인")
        auth.clear_failures(client)
        return _login_response(request, username)

    @r.post("/auth/logout")
    def auth_logout(request: Request):
        auth.end_session(request.cookies.get(COOKIE))
        response = JSONResponse({"ok": True})
        response.delete_cookie(COOKIE)
        return response

    @r.post("/auth/password", dependencies=admin)
    def auth_password(request: Request, body: dict = Body(...)):
        user = require_admin(request)
        if not auth.verify(user, str(body.get("current", ""))):
            raise Problem("현재 비밀번호가 올바르지 않습니다.")
        try:
            auth.set_password(user, str(body.get("password", "")))
        except ValueError as ex:
            raise Problem(str(ex))
        # 비밀번호를 바꾸면 기존 세션이 끊기므로 이 화면에는 새 세션을 준다
        return _login_response(request, user, {"message": "비밀번호를 변경했습니다.", "title": "완료"})

    # -------------------------------------------------------- 공통
    @r.get("/bootstrap", dependencies=admin)
    def bootstrap():
        return service.bootstrap()

    @r.get("/rev", dependencies=admin)
    def rev():
        return service.revision()

    @r.get("/checks", dependencies=admin)
    def checks(scope: str, key: str = ""):
        return service.checks(scope, key)

    @r.post("/checks/resolve", dependencies=admin)
    def resolve(body: dict = Body(...)):
        return service.resolve_expired(body)

    # -------------------------------------------------------- 대시보드
    @r.get("/seats", dependencies=admin)
    def seats(key: str):
        return service.seats(key)

    @r.get("/seats/detail", dependencies=admin)
    def seat_detail(key: str, number: int):
        return service.seat_detail(key, number)

    r.post("/seats/drop", dependencies=admin)(lambda body=Body(...): service.drop_seat(body))
    r.post("/seats/fix", dependencies=admin)(lambda body=Body(...): service.fix_seats(body))
    r.post("/seats/delete", dependencies=admin)(lambda body=Body(...): service.delete_seats(body))
    r.post("/seats/delete-all", dependencies=admin)(lambda body=Body(...): service.delete_all_seats(body))
    r.post("/seats/random", dependencies=admin)(lambda body=Body(...): service.random_seats(body))
    r.post("/seats/edit", dependencies=admin)(lambda body=Body(...): service.edit_seat(body))
    r.post("/seats/assign", dependencies=admin)(lambda body=Body(...): service.assign_seat(body))

    @r.get("/seats/export", dependencies=admin)
    def export_seats(key: str):
        return _download(*service.export_seats(key))

    @r.post("/seats/load", dependencies=admin)
    async def load_seats(request: Request):
        data, name = await _upload_body(request)
        body = {"key": request.query_params.get("key", ""),
                "confirmed": [x for x in request.query_params.get("confirmed", "").split(",") if x]}
        return await run_in_threadpool(_with_temp_file, data, name, lambda p: service.load_seat_file(body, p))

    @r.post("/memos", dependencies=admin)
    def add_memo(body: dict = Body(...)):
        return service.add_memo(str(body.get("content", "")))

    @r.put("/memos/{memo_id}", dependencies=admin)
    def update_memo(memo_id: str, body: dict = Body(...)):
        return service.update_memo(memo_id, str(body.get("content", "")))

    @r.delete("/memos/{memo_id}", dependencies=admin)
    def delete_memo(memo_id: str):
        return service.delete_memo(memo_id)

    # -------------------------------------------------------- 승인
    @r.post("/approvals/{req_id}/approve", dependencies=admin)
    def approve(req_id: str, body: dict = Body(...)):
        return service.approve(req_id, body)

    @r.post("/approvals/{req_id}/reject", dependencies=admin)
    def reject(req_id: str):
        return service.reject(req_id)

    @r.get("/history", dependencies=admin)
    def history(scope: str = ""):
        return {"rows": service.history(scope)}

    @r.post("/history/{req_id}/restore", dependencies=admin)
    def restore(req_id: str, body: dict = Body(...)):
        return service.restore(req_id, body)

    # -------------------------------------------------------- 기자재
    @r.get("/equipment", dependencies=admin)
    def equipment():
        return service.equipment()

    @r.get("/rentals/history", dependencies=admin)
    def rental_history():
        return {"rows": service.rental_history()}

    @r.post("/rentals/{rental_id}/return", dependencies=admin)
    def return_rental(rental_id: str, body: dict = Body(...)):
        return service.return_rental(rental_id, body)

    r.post("/rentals/delete", dependencies=admin)(lambda body=Body(...): service.delete_rentals(body))

    @r.get("/rentals/export", dependencies=admin)
    def export_rentals(kind: str):
        return _download(*service.export_rentals(kind == "mainframe"))

    @r.post("/rentals/import", dependencies=admin)
    async def import_rentals(request: Request):
        data, name = await _upload_body(request)
        is_mainframe = request.query_params.get("kind") == "mainframe"
        return await run_in_threadpool(_with_temp_file, data, name, lambda p: service.import_rental_file(is_mainframe, p))

    @r.get("/rentals/template", dependencies=admin)
    def template():
        return FileResponse(service.template_path(), media_type=XLSX, filename=TEMPLATE_NAME)

    @r.get("/issues/options", dependencies=admin)
    def issue_options(kind: str):
        return service.issue_options(kind == "mainframe")

    r.post("/issues", dependencies=admin)(lambda body=Body(...): service.add_issue(body))

    @r.post("/issues/{issue_id}/complete", dependencies=admin)
    def complete_issue(issue_id: str, body: dict = Body(...)):
        return service.complete_issue(issue_id, body)

    # -------------------------------------------------------- 캐비닛
    @r.get("/cabinets", dependencies=admin)
    def cabinets():
        return service.cabinets()

    @r.get("/cabinets/period", dependencies=admin)
    def cabinet_period(text: str = ""):
        return service.cabinet_period_dates(text)

    @r.get("/cabinets/move-options", dependencies=admin)
    def move_options(number: int):
        return service.move_cabinet_options(number)

    r.post("/cabinets/drop", dependencies=admin)(lambda body=Body(...): service.drop_cabinet(body))
    r.post("/cabinets/move", dependencies=admin)(lambda body=Body(...): service.move_cabinet(body))
    r.post("/cabinets/save", dependencies=admin)(lambda body=Body(...): service.save_cabinet(body))
    r.post("/cabinets/assign", dependencies=admin)(lambda body=Body(...): service.assign_cabinet(body))

    @r.get("/cabinets/export", dependencies=admin)
    def export_cabinets():
        return _download(*service.export_cabinets())

    @r.post("/cabinets/import", dependencies=admin)
    async def import_cabinets(request: Request):
        data, name = await _upload_body(request)
        return await run_in_threadpool(_with_temp_file, data, name, service.import_cabinet_file)

    # -------------------------------------------------------- 상상Lab / 데이터 관리
    @r.get("/sangsanglab", dependencies=admin)
    def sangsanglab():
        return service.sangsanglab()

    @r.get("/students", dependencies=admin)
    def students():
        return {"rows": service.students()}

    @r.put("/students/{student_id}", dependencies=admin)
    def save_student(student_id: str, body: dict = Body(...)):
        return service.save_student(student_id, body)

    @r.post("/students/delete-all", dependencies=admin)
    def delete_all_students(body: dict = Body(...)):
        return service.delete_all_students(body)

    @r.post("/students/import", dependencies=admin)
    async def import_students(request: Request):
        data, name = await _upload_body(request)
        return await run_in_threadpool(_with_temp_file, data, name, service.import_student_file)

    @r.post("/students/{student_id}/delete", dependencies=admin)
    def delete_student(student_id: str, body: dict = Body(...)):
        return service.delete_student(student_id, body)

    # -------------------------------------------------------- 얼굴인식 (관리자 화면)
    @r.get("/face/records", dependencies=admin)
    def face_records(q: str = "", date_from: str = "", date_to: str = ""):
        return service.face_records(q, date_from, date_to)

    @r.get("/face/quick-range", dependencies=admin)
    def face_quick(tag: str):
        return service.face_quick_range(tag)

    @r.get("/face/criteria", dependencies=admin)
    def face_criteria(month: str = "", result: str = "", q: str = ""):
        return service.face_criteria(month, result, q)

    @r.get("/face/student/{student_id}", dependencies=admin)
    def face_student(student_id: str):
        return service.face_student(student_id)

    @r.get("/face/link-info", dependencies=admin)
    def face_link():
        return {"apiKey": auth.face_api_key}

    @r.post("/face/link-info/regenerate", dependencies=admin)
    def face_regenerate():
        return {"apiKey": auth.regenerate_face_key()}

    # -------------------------------------------------------- 얼굴인식 (연동 키로 접근)
    @r.post("/face/attendance", dependencies=[Depends(require_face_key)])
    async def face_attendance(request: Request):
        data = await request.body()
        if len(data) > MAX_UPLOAD_BYTES:
            raise Problem("출결 데이터가 너무 큽니다.", "오류", "error")
        count = await run_in_threadpool(service.store_attendance, json.loads(data.decode("utf-8")))
        return {"ok": True, "records": count}

    @r.get("/face/roster", dependencies=[Depends(require_face_key)])
    def face_roster():
        return service.roster()

    # -------------------------------------------------------- 설정
    @r.get("/settings", dependencies=admin)
    def settings():
        return service.settings()

    @r.put("/settings/sync", dependencies=admin)
    def save_sync(body: dict = Body(...)):
        return service.save_sync_settings(body)

    @r.post("/settings/sync-now", dependencies=admin)
    def sync_now():
        return service.sync(silent=False)

    @r.post("/settings/key", dependencies=admin)
    async def upload_key(request: Request):
        data, _name = await _upload_body(request)
        return await run_in_threadpool(service.save_key_file, data)

    @r.get("/seasons/{year}", dependencies=admin)
    def season_rows(year: int):
        return service.season_rows(year)

    @r.post("/seasons", dependencies=admin)
    def add_year(body: dict = Body(...)):
        return service.add_season_year(body)

    @r.put("/seasons/{year}", dependencies=admin)
    def save_year(year: int, body: dict = Body(...)):
        return service.save_season_year(year, body)

    @r.post("/seasons/{year}/delete", dependencies=admin)
    def delete_year(year: int, body: dict = Body(...)):
        return service.delete_season_year(year, body)

    return r
