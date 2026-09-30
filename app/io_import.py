"""
엑셀(.xlsx)/CSV 표 읽기 + 학번·연락처 정규화.
C# 버전의 ReadTable/ParseCsv/ReadTextAutoEncoding/NormalizeStudentId/NormalizePhone에 대응한다.
"""
from __future__ import annotations

import csv
import io
import os
from typing import Optional

import openpyxl


def read_table(path: str) -> list[list[object]]:
    """.xlsx/.csv 파일을 행 목록으로 읽는다. 각 행은 A, B, C… 열 순서의 값 목록이다."""
    ext = os.path.splitext(path)[1].lower()
    if ext in (".csv", ".tsv"):
        text = _read_text_auto_encoding(path)
        return [list(row) for row in _parse_csv(text)]

    wb = openpyxl.load_workbook(path, data_only=True, read_only=True)
    ws = wb.active
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    wb.close()
    return rows


def _read_text_auto_encoding(path: str) -> str:
    """UTF-8(BOM 유무 무관)로 먼저 읽고, 깨지면 엑셀에서 저장한 CSV에 흔한 CP949(EUC-KR)로 다시 읽는다."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("cp949", errors="replace")


def _parse_csv(text: str) -> list[list[str]]:
    first_line = text.split("\n", 1)[0]
    delim = "\t" if first_line.count("\t") > first_line.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delim)
    rows = [row for row in reader if any((c or "").strip() for c in row)]
    return rows


def cell_str(v: object) -> str:
    """셀 값을 사람이 읽는 문자열로 바꾼다 (앞뒤 공백 제거)."""
    if v is None:
        return ""
    return str(v).strip()


def normalize_student_id(v: object) -> str:
    """학번 셀을 문자열로 정규화한다. 숫자형(2.02e7 등)으로 들어와도 정수 학번으로 되돌린다."""
    if v is None:
        return ""
    if isinstance(v, float):
        return str(round(v))
    s = str(v).strip()
    if not s:
        return ""
    if any(c in s for c in "Ee."):
        try:
            return str(round(float(s)))
        except ValueError:
            pass
    return s


def normalize_phone(v: object) -> str:
    """
    연락처 칸을 문자열로 정리한다. 엑셀이 숫자로 저장해 앞자리 0이 빠진 번호(1084583371)는
    0을 붙여 복원한다. 하이픈이 있는 값(010-1234-5678)은 입력한 그대로 둔다.
    """
    if v is None:
        s = ""
    elif isinstance(v, float):
        s = str(round(v))
    else:
        s = str(v).strip()
    if 9 <= len(s) <= 10 and s.isdigit() and s.startswith("1"):
        s = "0" + s
    return s


def find_header_row(table: list[list[object]], must_contain: list[str], max_rows: int = 10) -> int:
    """위쪽 max_rows행 안에서, must_contain의 각 키워드가 (서로 다른 칸이라도) 모두 들어있는 행을 찾는다."""
    for i in range(min(len(table), max_rows)):
        texts = [cell_str(c) for c in table[i]]
        if all(any(key in t for t in texts) for key in must_contain):
            return i
    return -1


def find_col(header: list[str], *keys: str) -> int:
    for i, h in enumerate(header):
        if any(k in h for k in keys):
            return i
    return -1


def cell_at(row: list[object], idx: int) -> object:
    return row[idx] if 0 <= idx < len(row) else None
