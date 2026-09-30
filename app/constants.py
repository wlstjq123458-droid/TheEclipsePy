"""
캐비닛/기자재 탭과 승인 처리(approval_logic)가 함께 쓰는 상수·헬퍼.
순환 참조(양쪽 탭 ↔ approval_logic)를 피하려고 따로 뺐다.
"""
from __future__ import annotations

import datetime
import re

TOTAL_CABINETS = 48
TOTAL_MAINFRAME = 10
TOTAL_LAPTOP = 20

MAINFRAME_LABEL = "본체 (HP Z2 G9)"
LAPTOP_LABEL = "노트북(HP OMEN 게이밍 노트북)"


def format_period(start: datetime.date, end: datetime.date) -> str:
    return f"{start.strftime('%y.%m.%d')} ~ {end.strftime('%y.%m.%d')}"


def parse_period_dates(period: str):
    """"26.03.02 ~ 26.06.20" 등을 관대하게 읽는다. 못 읽으면 None."""
    matches = re.findall(r"(\d{2,4})[./-](\d{1,2})[./-](\d{1,2})", period or "")
    if len(matches) >= 2:
        def to_date(m):
            y, mo, d = int(m[0]), int(m[1]), int(m[2])
            if y < 100:
                y += 2000
            return datetime.date(y, mo, d)
        try:
            return to_date(matches[0]), to_date(matches[1])
        except ValueError:
            return None
    return None


def default_cabinet_period() -> str:
    today = datetime.date.today()
    try:
        nxt = today.replace(month=today.month + 1)
    except ValueError:
        nxt = today.replace(year=today.year + 1, month=1)
    return format_period(today, nxt)
