"""Guess the format of a CSV bank export: encoding, separator, header line, number and date format."""

from __future__ import annotations

import codecs
import csv
import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

CANDIDATE_SEPARATORS = (";", ",", "\t", "|")

_CURRENCY = re.compile(r"[€$£\s ']|EUR|USD|CHF")
_NUMBER = re.compile(r"^[+-]?\(?\d[\d.,]*\)?[+-]?%?$")
_DATE = re.compile(r"^\d{1,4}[./-]\d{1,2}[./-]\d{1,4}")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})([./-])(\d{1,2})\2(\d{2}|\d{4})$")
_ISO_DATE = re.compile(r"^\d{4}[-/.]\d{1,2}[-/.]\d{1,2}")


@dataclass(frozen=True)
class Record:
    """One CSV record and the (0 based) line it starts on."""

    line: int
    fields: list[str]


@dataclass(frozen=True)
class CsvFormat:
    encoding: str
    separator: str
    skiprows: int
    decimal: str
    thousands: str
    dayfirst: bool
    columns: tuple[str, ...]


def detect_encoding(raw: bytes) -> str:
    """UTF-8 (with or without BOM) if the bytes decode as such, otherwise Windows-1252, otherwise Latin-1."""
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    for encoding in ("utf-8", "cp1252"):
        try:
            raw.decode(encoding)
        except UnicodeDecodeError:
            continue
        return encoding
    return "latin-1"


def read_text(path: str | Path, encoding: str | None = None) -> tuple[str, str]:
    raw = Path(path).read_bytes()
    encoding = encoding or detect_encoding(raw)
    try:
        return raw.decode(encoding, errors="replace"), encoding
    except LookupError:  # unknown encoding name entered by the user
        encoding = detect_encoding(raw)
        return raw.decode(encoding, errors="replace"), encoding


def split_records(text: str, separator: str) -> list[Record]:
    """Parse ``text`` as CSV; quoted fields may contain separators and line breaks."""
    lines = text.splitlines(keepends=True)
    reader = csv.reader(lines, delimiter=separator)
    records = []
    start = 0
    try:
        for fields in reader:
            records.append(Record(start, fields))
            start = reader.line_num
    except csv.Error:
        pass
    return records


def _table_width(records: Iterable[Record]) -> tuple[int, int]:
    """``(width, cells)`` of the record width that covers the most cells.

    Preamble lines of bank exports (``IBAN;DE...``) are often more numerous than the transactions of a
    short export, but they are narrow. Widths seen only once are ignored if possible.
    """
    counts = Counter(len(r.fields) for r in records if len(r.fields) > 1)
    candidates = {w: n for w, n in counts.items() if n >= 2} or counts
    if not candidates:
        return 0, 0
    width = max(candidates, key=lambda w: (candidates[w] * w, w))
    return width, candidates[width] * width


def detect_separator(text: str) -> str:
    best, best_cells = CANDIDATE_SEPARATORS[0], 0
    for separator in CANDIDATE_SEPARATORS:
        _, cells = _table_width(split_records(text, separator))
        if cells > best_cells:
            best, best_cells = separator, cells
    return best


def detect_header_record(records: list[Record]) -> int:
    """Index of the header: the first mostly filled record as wide as the table.

    Preamble and footer lines are ignored, also padded preamble lines such as ``Kontoauszug;;;``.
    """
    width, _ = _table_width(records)
    candidates = [i for i, record in enumerate(records) if len(record.fields) == width]
    for i in candidates:
        filled = sum(1 for f in records[i].fields if f.strip())
        if filled >= max(2, math.ceil(0.75 * width)):
            return i
    return candidates[0] if candidates else 0


def detect_decimal(values: Iterable[str]) -> str | None:
    """Decimal mark (``,`` or ``.``) voted by the number-like values; ``None`` if undecidable."""
    votes: Counter[str] = Counter()
    for value in values:
        text = _CURRENCY.sub("", value.strip())
        if not text or _DATE.match(text) or not _NUMBER.match(text):
            continue
        text = text.strip("+-()%")
        last = max(text.rfind("."), text.rfind(","))
        if last < 0:
            continue
        mark = text[last]
        digits = len(text) - last - 1
        if digits in (1, 2):
            votes[mark] += 1
        elif digits == 3 and text.count(mark) > 1:  # 1.234.567 -> '.' groups thousands
            votes["," if mark == "." else "."] += 1
    if not votes or votes[","] == votes["."]:
        return None
    return votes.most_common(1)[0][0]


def detect_dayfirst(values: Iterable[str]) -> bool | None:
    """Whether dates look like ``31.12.2024`` (True) or ``12/31/2024`` / ISO (False); ``None`` if unknown."""
    day_first = month_first = 0
    for value in values:
        text = value.strip()
        if _ISO_DATE.match(text):
            month_first += 1
            continue
        match = _DAY_MONTH_YEAR.match(text)
        if not match:
            continue
        first, separator, second = int(match[1]), match[2], int(match[3])
        if first > 12:
            day_first += 1
        elif second > 12:
            month_first += 1
        elif separator == ".":
            day_first += 1
    if day_first == month_first == 0:
        return None
    return day_first >= month_first


def clean_columns(names: Iterable[str]) -> list[str]:
    """Strip quotes/BOM, name empty columns and make names unique."""
    cleaned: list[str] = []
    for i, name in enumerate(names):
        name = name.replace("﻿", "").strip().strip("'\"").strip() or f"column {i + 1}"
        unique, n = name, 2
        while unique in cleaned:
            unique, n = f"{name} ({n})", n + 1
        cleaned.append(unique)
    return cleaned


def sniff_format(path: str | Path) -> CsvFormat:
    text, encoding = read_text(path)
    separator = detect_separator(text)
    records = split_records(text, separator)
    header = detect_header_record(records)
    columns = clean_columns(records[header].fields) if records else []
    values = [f for r in records[header + 1 :] for f in r.fields]

    decimal = detect_decimal(values) or ("," if separator == ";" else ".")
    dayfirst = detect_dayfirst(values)
    return CsvFormat(
        encoding=encoding,
        separator=separator,
        skiprows=records[header].line if records else 0,
        decimal=decimal,
        thousands="." if decimal == "," else ",",
        dayfirst=(separator == ";") if dayfirst is None else dayfirst,
        columns=tuple(columns),
    )
