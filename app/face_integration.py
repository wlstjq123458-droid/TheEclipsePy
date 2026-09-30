"""
얼굴인식 출결 프로그램(별도 파이썬 프로그램, insightface-attendance)과의 파일 기반 연동.
C# 버전의 FaceIntegration.cs와 정확히 같은 폴더·같은 JSON 스키마를 쓴다 — 그래야 어느 쪽
(C# 버전이든 이 파이썬 버전이든)에서 내보낸 roster.json도 얼굴인식 프로그램이 그대로 읽고,
얼굴인식 프로그램이 적어 둔 attendance.json도 그대로 읽을 수 있다.

- roster.json: [{"StudentId":.., "Name":.., "Department":..}, ...] — 이 프로그램 → 얼굴인식
- attendance.json: [{"StudentId":.., "Name":.., "Date":"yyyy-MM-dd", "CheckIn":"HH:mm:ss"|null, "CheckOut":..}, ...] — 얼굴인식 → 이 프로그램
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

from . import config
from .models import StudentInfo


def export_roster(master_students: list[StudentInfo]) -> None:
    try:
        seen = set()
        roster = []
        for s in sorted(master_students, key=lambda x: x.student_id):
            if not s.student_id or s.student_id in seen:
                continue
            seen.add(s.student_id)
            roster.append({"StudentId": s.student_id, "Name": s.name, "Department": s.department})
        os.makedirs(config.face_integration_dir(), exist_ok=True)
        with open(config.roster_path(), "w", encoding="utf-8") as f:
            json.dump(roster, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 내보내기 실패는 치명적이지 않다 — 다음 저장 때 다시 시도한다


@dataclass
class FaceAttendanceEntry:
    student_id: str
    name: str
    date: str
    check_in: str | None
    check_out: str | None


def load_attendance() -> list[FaceAttendanceEntry]:
    path = config.attendance_path()
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return [
            FaceAttendanceEntry(
                student_id=e.get("StudentId", ""),
                name=e.get("Name", ""),
                date=e.get("Date", ""),
                check_in=e.get("CheckIn"),
                check_out=e.get("CheckOut"),
            )
            for e in raw
        ]
    except Exception:
        return []
