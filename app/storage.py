"""
JSON 파일 저장/불러오기. C# 버전의 SaveSeatCache/LoadSeatCache, AppState.Load/Save,
SeasonConfig.Load/Save에 대응한다.

좌석 데이터(seats.json)·학사 시즌 일정(seasons.json)은 각자 파일로,
나머지(학생 마스터·캐비닛·기자재 대여·승인 신청·메모 등)는 appstate.json 하나에 모아 저장한다
— 저장할 때마다 파일을 여러 번 읽고 쓰지 않도록 AppState를 한 번에 불러오고 한 번에 저장한다.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

from . import config
from .models import (
    Seat, StudentInfo, CabinetAllocation, RentalItem, EquipmentIssue,
    ApprovalRequest, MemoItem, SeasonConfig,
)


# ============================================================== 좌석 데이터
def load_seat_cache() -> dict[str, list[Seat]]:
    """시즌 키("{연도}_{시즌}") -> 좌석 52개 목록."""
    path = config.seats_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return {key: [Seat.from_dict(s) for s in seats] for key, seats in raw.items()}
    except Exception:
        return {}  # 손상된 파일이면 빈 캐시로 시작한다 (기존 파일은 그대로 둔다)


def save_seat_cache(cache: dict[str, list[Seat]]) -> None:
    try:
        raw = {key: [s.to_dict() for s in seats] for key, seats in cache.items()}
        with open(config.seats_path(), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
    except Exception:
        pass  # 저장 실패는 치명적이지 않다 — 다음 저장 때 다시 시도한다


def new_empty_seats() -> list[Seat]:
    """새 시즌을 처음 조회할 때: 52개 빈 좌석으로 시작한다 (기둥은 좌석이 아니라 화면에 따로 그려진다)."""
    return [Seat(seat_number=i) for i in range(1, 53)]


# ========================================================== 학사 시즌 일정
def load_season_config() -> SeasonConfig:
    path = config.seasons_path()
    if not os.path.exists(path):
        return SeasonConfig()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return SeasonConfig.from_dict(json.load(f))
    except Exception:
        return SeasonConfig()


def save_season_config(cfg: SeasonConfig) -> None:
    try:
        with open(config.seasons_path(), "w", encoding="utf-8") as f:
            json.dump(cfg.to_dict(), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# =============================================================== 설정(구글 시트 연동 등)
def load_settings() -> dict:
    path = config.settings_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    try:
        with open(config.settings_path(), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ================================================================ AppState
@dataclass
class AppState:
    master_students: list[StudentInfo] = field(default_factory=list)
    cabinet_allocations: dict[int, CabinetAllocation] = field(default_factory=dict)
    rentals: list[RentalItem] = field(default_factory=list)
    rental_history: list[RentalItem] = field(default_factory=list)
    equipment_issues: list[EquipmentIssue] = field(default_factory=list)
    approvals: list[ApprovalRequest] = field(default_factory=list)
    approval_history: list[ApprovalRequest] = field(default_factory=list)
    imported_source_keys: set[str] = field(default_factory=set)
    memos: list[MemoItem] = field(default_factory=list)


def load_app_state() -> AppState:
    path = config.appstate_path()
    if not os.path.exists(path):
        return AppState()
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return AppState()

    cabinets: dict[int, CabinetAllocation] = {}
    for entry in raw.get("CabinetAllocations", []):
        alloc = CabinetAllocation.from_dict(entry)
        if alloc.cabinet_num:
            cabinets[alloc.cabinet_num] = alloc

    try:
        return AppState(
            master_students=[StudentInfo.from_dict(s) for s in raw.get("MasterStudents", [])],
            cabinet_allocations=cabinets,
            rentals=[RentalItem.from_dict(r) for r in raw.get("Rentals", [])],
            rental_history=[RentalItem.from_dict(r) for r in raw.get("RentalHistory", [])],
            equipment_issues=[EquipmentIssue.from_dict(i) for i in raw.get("EquipmentIssues", [])],
            approvals=[ApprovalRequest.from_dict(a) for a in raw.get("Approvals", [])],
            approval_history=[ApprovalRequest.from_dict(a) for a in raw.get("ApprovalHistory", [])],
            imported_source_keys=set(raw.get("ImportedSourceKeys", [])),
            memos=[MemoItem.from_dict(m) for m in raw.get("Memos", [])],
        )
    except Exception:
        return AppState()


def save_app_state(state: AppState) -> None:
    try:
        raw = {
            "MasterStudents": [s.to_dict() for s in state.master_students],
            "CabinetAllocations": [a.to_dict() for a in state.cabinet_allocations.values()],
            "Rentals": [r.to_dict() for r in state.rentals],
            "RentalHistory": [r.to_dict() for r in state.rental_history],
            "EquipmentIssues": [i.to_dict() for i in state.equipment_issues],
            "Approvals": [a.to_dict() for a in state.approvals],
            "ApprovalHistory": [a.to_dict() for a in state.approval_history],
            "ImportedSourceKeys": sorted(state.imported_source_keys),
            "Memos": [m.to_dict() for m in state.memos],
        }
        os.makedirs(config.config_dir(), exist_ok=True)
        with open(config.appstate_path(), "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
    except Exception:
        pass  # 저장 실패는 치명적이지 않다 — 다음 종료 때 다시 시도한다
