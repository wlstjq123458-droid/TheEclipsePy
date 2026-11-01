"""
관리자 로그인과 얼굴인식 연동 키.

비밀번호는 PBKDF2로 해시해서 web_auth.json에만 저장한다. 로그인 세션은 서버 메모리에 두므로
서버를 다시 켜면 다시 로그인해야 한다. 얼굴인식 PC가 쓰는 연동 키는 관리자 비밀번호와 별개다.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from typing import Optional

from app import config, storage

ITERATIONS = 310_000
SESSION_SECONDS = 12 * 3600
MAX_FAILS = 5
LOCK_SECONDS = 60
MIN_PASSWORD_LENGTH = 8
DEFAULT_USER = "admin"


def _auth_path() -> str:
    return os.path.join(config.config_dir(), "web_auth.json")


def _hash(password: str, salt: bytes, iterations: int) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations).hex()


class Auth:
    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, tuple[str, float]] = {}
        self._fails: dict[str, tuple[int, float]] = {}
        self._data = self._load()

    def _load(self) -> dict:
        try:
            with open(_auth_path(), "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):
            return {"users": {}, "faceApiKey": ""}

    def _save(self) -> None:
        storage.write_json(_auth_path(), self._data, indent=2)

    @property
    def has_admin(self) -> bool:
        return bool(self._data["users"])

    # ------------------------------------------------------------ 계정
    def set_password(self, username: str, password: str) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"비밀번호는 {MIN_PASSWORD_LENGTH}자 이상이어야 합니다.")
        salt = secrets.token_bytes(16)
        with self._lock:
            self._data["users"][username] = {"salt": salt.hex(), "iterations": ITERATIONS,
                                             "hash": _hash(password, salt, ITERATIONS)}
            self._save()
            # 비밀번호를 바꾸면 이 계정으로 열려 있던 다른 세션은 끊는다
            self._sessions = {t: v for t, v in self._sessions.items() if v[0] != username}

    def verify(self, username: str, password: str) -> bool:
        user = self._data["users"].get(username)
        if user is None:
            _hash(password, b"0" * 16, ITERATIONS)   # 없는 계정도 같은 시간이 걸리게 한다
            return False
        expected = _hash(password, bytes.fromhex(user["salt"]), user["iterations"])
        return hmac.compare_digest(expected, user["hash"])

    # ------------------------------------------------------------ 로그인 시도 제한
    def locked_seconds(self, client: str) -> int:
        count, until = self._fails.get(client, (0, 0.0))
        return max(0, int(until - time.time()) + 1) if count >= MAX_FAILS and until > time.time() else 0

    def record_failure(self, client: str) -> None:
        with self._lock:
            count, until = self._fails.get(client, (0, 0.0))
            count = 1 if until and until <= time.time() else count + 1
            self._fails[client] = (count, time.time() + LOCK_SECONDS)

    def clear_failures(self, client: str) -> None:
        with self._lock:
            self._fails.pop(client, None)

    # ------------------------------------------------------------ 세션
    def create_session(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            now = time.time()
            self._sessions = {t: v for t, v in self._sessions.items() if v[1] > now}
            self._sessions[token] = (username, now + SESSION_SECONDS)
        return token

    def session_user(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        entry = self._sessions.get(token)
        if entry is None or entry[1] < time.time():
            return None
        return entry[0]

    def end_session(self, token: Optional[str]) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)

    # ------------------------------------------------------------ 얼굴인식 연동 키
    @property
    def face_api_key(self) -> str:
        with self._lock:
            if not self._data.get("faceApiKey"):
                self._data["faceApiKey"] = secrets.token_urlsafe(32)
                self._save()
            return self._data["faceApiKey"]

    def regenerate_face_key(self) -> str:
        with self._lock:
            self._data["faceApiKey"] = secrets.token_urlsafe(32)
            self._save()
            return self._data["faceApiKey"]

    def check_face_key(self, key: Optional[str]) -> bool:
        return bool(key) and hmac.compare_digest(key.encode("utf-8"), self.face_api_key.encode("utf-8"))
