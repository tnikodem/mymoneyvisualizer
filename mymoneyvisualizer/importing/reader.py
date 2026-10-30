"""Turn a CSV export into normalized transactions and find the ones that are already known."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mymoneyvisualizer.domain.columns import Col, empty_transactions, normalize_transactions
from mymoneyvisualizer.importing.profile import (
    CREDIT_COLUMNS,
    CREDIT_MARKERS,
    DEBIT_COLUMNS,
    DEBIT_MARKERS,
    EXTRA_VALUE_COLUMNS,
    ImportProfile,
    column_candidates,
    find_profile,
    guess_mapping,
)
from mymoneyvisualizer.importing.sniff import clean_columns, lines, read_text, sniff_format

ISO_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d")
DAYFIRST_FORMATS = (
    "%d.%m.%Y",
    "%d.%m.%y",
    "%d/%m/%Y",
    "%d/%m/%y",
    "%d-%m-%Y",
    "%d-%m-%y",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
)
MONTHFIRST_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%m.%d.%Y")


#: Cells marking balance lines, which some banks write like transactions (e.g. Volksbank "Endsaldo").
BALANCE_WORDS = frozenset(
    {
        "anfangssaldo",
        "endsaldo",
        "saldo",
        "kontostand",
        "alter kontostand",
        "neuer kontostand",
        "opening balance",
        "closing balance",
    }
)


#: names of the profile fields in messages
FIELD_NAMES = {
    "col_date": "Datum",
    "col_recipient": "Empfänger",
    "col_description": "Verwendungszweck",
    "col_value": "Betrag",
    "col_debit": "Soll",
    "col_credit": "Haben",
    "col_sign": "Soll/Haben-Kennzeichen",
    "col_value_extra": "Zum Betrag addieren",
}


class ImportFormatError(ValueError):
    """The file cannot be read with the given profile."""


def read_table(path: str | Path, profile: ImportProfile) -> pd.DataFrame:
    """All cells of the export as strings; the header is the line ``profile.skiprows``.

    Rows with more cells than the header usually have an unquoted separator in their text; the surplus
    cells are joined back into the description column. Missing cells are empty.
    """
    errors = profile.errors()
    if "separator" in errors or "skiprows" in errors:
        raise ImportFormatError(errors.get("separator") or errors["skiprows"])
    text, _ = read_text(path, profile.encoding)
    try:
        records = list(csv.reader(lines(text)[profile.skiprows :], delimiter=profile.separator))
    except csv.Error as e:
        raise ImportFormatError(str(e)) from e
    records = [r for r in records if any(cell.strip() for cell in r)]
    if not records:
        return pd.DataFrame()
    columns = clean_columns(records[0])
    width = len(columns)
    target = profile.col_description or guess_mapping(columns).get("col_description")
    merge_at = columns.index(target) if target in columns else None
    rows = []
    for record in records[1:]:
        while len(record) > width and not record[-1].strip():
            record = record[:-1]
        if len(record) > width and merge_at is not None:
            end = merge_at + len(record) - width + 1
            record = [*record[:merge_at], profile.separator.join(record[merge_at:end]), *record[end:]]
        rows.append((record + [""] * width)[:width])
    return pd.DataFrame(rows, columns=columns, dtype=str)


def parse_amounts(values: pd.Series, decimal: str = ",", thousands: str = ".") -> pd.Series:
    """Parse ``1.234,56``, ``-3,50 €``, ``(12.00)``, ``50,00-``, ``−4,20`` or ``23,45 S`` style amounts.

    Invalid values become NaN. A trailing ``S`` (Soll) makes the amount negative, ``H`` (Haben) positive.
    """
    text = values.astype(str).str.strip()
    text = text.str.replace(r"[‐‒–—−]", "-", regex=True)
    debit = text.str.contains(r"\d\s*S$", regex=True)
    credit = text.str.contains(r"\d\s*H$", regex=True)
    text = text.str.replace(r"(?<=\d)\s*[SH]$", "", regex=True)
    text = text.str.replace(r"[€$£\s']|EUR|USD|CHF", "", regex=True)
    negative = text.str.match(r"^\(.*\)$") | (text.str.endswith("-") & ~text.str.startswith("-")) | debit
    text = text.str.strip("()").str.rstrip("-")
    if thousands:
        # thousands separators group exactly three digits; "28.10.2026" is a date, not 28102026
        grouped = re.compile(rf"^[+-]?\d{{1,3}}({re.escape(thousands)}\d{{3}})+({re.escape(decimal)}\d*)?$")
        text = text.where(~text.str.contains(thousands, regex=False) | text.str.match(grouped), "invalid")
        text = text.str.replace(thousands, "", regex=False)
    if decimal != ".":
        text = text.str.replace(decimal, ".", regex=False)
    numbers = pd.to_numeric(text, errors="coerce").astype(float)
    numbers = numbers.where(~negative, -numbers.abs())
    return numbers.where(~credit, numbers.abs())


def parse_dates(values: pd.Series, dayfirst: bool = True) -> pd.Series:
    """Parse dates with the format that understands the most values (day first formats preferred if asked).

    ISO timestamps with time zone (``2025-08-02T21:19:49.402Z``) are understood as well. The time is dropped.
    """
    text = values.astype(str).str.strip()
    formats = ISO_FORMATS + (
        DAYFIRST_FORMATS + MONTHFIRST_FORMATS if dayfirst else MONTHFIRST_FORMATS + DAYFIRST_FORMATS
    )
    best, best_count = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]"), 0
    for fmt in formats:
        parsed = pd.to_datetime(text, format=fmt, errors="coerce")
        count = int(parsed.notna().sum())
        if count > best_count:
            best, best_count = parsed, count
        if count == len(text):
            break
    if best_count < len(text):
        iso = pd.to_datetime(text, format="ISO8601", errors="coerce", utc=True)
        if int(iso.notna().sum()) > best_count:
            best = iso.dt.tz_convert(None)
    return best.astype("datetime64[ns]").dt.normalize()


def _amount_column(table: pd.DataFrame, column: str, decimal: str, thousands: str, share: float = 0.8) -> bool:
    """Whether most non-empty cells of ``column`` are amounts."""
    filled = table[column].astype(str).str.strip() != ""
    if not filled.any():
        return False
    parsed = parse_amounts(table.loc[filled, column], decimal, thousands)
    return parsed.notna().mean() >= share


def propose_mapping(table: pd.DataFrame, decimal: str = ",", thousands: str = ".", dayfirst: bool = True) -> dict:
    """Column mapping for an unknown export: candidates by column name, checked against the content.

    - date and value columns must contain dates / amounts
    - recipient and description: the first fitting column that is mostly filled (Deutsche Bank has an
      empty "Abweichender Empfänger", PayPal an often empty "Artikelbezeichnung")
    - without a value column, separate debit/credit columns are used (Deutsche Bank "Soll" / "Haben")
    - fee and tax columns are added to the value (brokers), unless the value already is a net amount
    - unsigned amounts get a debit/credit indicator column (Volksbank "S" / "H")
    """
    columns = list(table.columns)
    mapping: dict = {}

    def filled(column: str) -> float:
        return float((table[column].astype(str).str.strip() != "").mean()) if len(table) else 0.0

    def amounts(column: str) -> bool:
        return _amount_column(table, column, decimal, thousands)

    def dates(column: str) -> bool:
        return bool(parse_dates(table[column], dayfirst).notna().mean() >= 0.5)

    def unused(field_name: str) -> list[str]:
        return [c for c in column_candidates(columns, field_name) if c not in mapping.values()]

    mapping["col_date"] = next((c for c in unused("col_date") if dates(c)), "")
    mapping["col_value"] = next((c for c in unused("col_value") if amounts(c)), "")
    for field_name in ("col_recipient", "col_description"):
        candidates = unused(field_name)
        mostly_filled = next((c for c in candidates if filled(c) >= 0.5), None)
        mapping[field_name] = mostly_filled or max(candidates, key=filled, default="")

    value = mapping["col_value"]
    if not value:
        mapping["col_debit"] = next((c for c in columns if c.lower() in DEBIT_COLUMNS and amounts(c)), "")
        mapping["col_credit"] = next((c for c in columns if c.lower() in CREDIT_COLUMNS and amounts(c)), "")
    elif "net" not in value.lower():
        mapping["col_value_extra"] = [
            c for c in columns if c != value and c.lower() in EXTRA_VALUE_COLUMNS and amounts(c)
        ]
    if value and not (parse_amounts(table[value], decimal, thousands) < 0).any():
        used = {v for v in mapping.values() if isinstance(v, str)}
        for column in columns:
            cells = table[column].astype(str).str.strip().str.lower()
            cells = cells[cells != ""]
            if column in used or cells.empty:
                continue
            if cells.isin(DEBIT_MARKERS | CREDIT_MARKERS).mean() >= 0.9 and cells.isin(DEBIT_MARKERS).any():
                mapping["col_sign"] = column
                break
    return {k: v for k, v in mapping.items() if v}


def propose_profile(
    path: str | Path, profiles: list[ImportProfile] | tuple[ImportProfile, ...] = ()
) -> tuple[ImportProfile, ImportProfile | None]:
    """``(profile, matched)``: a stored profile that fits the columns of the file, or a detected one."""
    fmt = sniff_format(path)
    matched = find_profile(profiles, fmt.columns)
    if matched is not None:
        return matched, matched
    profile = ImportProfile(
        encoding=fmt.encoding,
        separator=fmt.separator,
        skiprows=fmt.skiprows,
        decimal=fmt.decimal,
        thousands=fmt.thousands,
        dayfirst=fmt.dayfirst,
    )
    try:
        table = read_table(path, profile)
    except ImportFormatError:
        return profile, None
    if table.empty:
        return profile, None
    return profile.with_mapping(**propose_mapping(table, fmt.decimal, fmt.thousands, fmt.dayfirst)), None


@dataclass
class ImportPreview:
    """What an import would do. ``transactions`` are the rows that would be added."""

    transactions: pd.DataFrame
    duplicates: pd.DataFrame = field(default_factory=empty_transactions)
    invalid: int = 0
    zero: int = 0
    before_since: int = 0
    first_date: pd.Timestamp | None = None
    last_date: pd.Timestamp | None = None


def transaction_values(table: pd.DataFrame, profile: ImportProfile) -> pd.Series:
    """``value + extras - |debit| + |credit|`` (empty cells count as 0), signed by the indicator column.

    NaN if none of the value columns of a row holds an amount.
    """

    def amounts(column: str) -> pd.Series:
        return parse_amounts(table[column], profile.decimal, profile.thousands)

    parts = [amounts(c) for c in (profile.col_value, *profile.col_value_extra) if c]
    if profile.col_debit:
        parts.append(-amounts(profile.col_debit).abs())
    if profile.col_credit:
        parts.append(amounts(profile.col_credit).abs())
    values = pd.concat(parts, axis=1).sum(axis=1, min_count=1)
    if profile.col_sign:
        marker = table[profile.col_sign].astype(str).str.strip().str.lower()
        values = values.where(~marker.isin(DEBIT_MARKERS), -values.abs())
        values = values.where(~marker.isin(CREDIT_MARKERS), values.abs())
    return values


def to_transactions(table: pd.DataFrame, profile: ImportProfile) -> tuple[pd.DataFrame, int, int]:
    """``(transactions, invalid, zero)``: rows without a valid date/amount and zero amounts are dropped."""
    missing = profile.missing_columns(table.columns)
    if missing:
        raise ImportFormatError("Bitte eine Spalte wählen für: " + ", ".join(FIELD_NAMES.get(m, m) for m in missing))
    errors = profile.errors()
    if errors:
        raise ImportFormatError(next(iter(errors.values())))

    def text(column: str) -> pd.Series:  # optional columns are empty if not mapped
        return table[column].astype(str).str.strip() if column else pd.Series("", index=table.index)

    df = pd.DataFrame(
        {
            Col.date: parse_dates(table[profile.col_date], profile.dayfirst),
            Col.recipient: text(profile.col_recipient),
            Col.description: text(profile.col_description),
            Col.value: transaction_values(table, profile),
        }
    )
    cells = table.apply(lambda column: column.astype(str).str.strip().str.lower().str.rstrip(":"))
    balance = cells.isin(BALANCE_WORDS).any(axis=1)
    invalid = df[Col.date].isna() | df[Col.value].isna() | balance
    zero = ~invalid & (df[Col.value] == 0)
    return normalize_transactions(df.loc[~invalid & ~zero]), int(invalid.sum()), int(zero.sum())


def duplicate_keys(df: pd.DataFrame) -> pd.Series:
    """Content based key; identical transactions on the same day get an occurrence counter."""

    def text(col: str) -> pd.Series:
        return df[col].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)

    base = (
        df[Col.date].dt.strftime("%Y-%m-%d")
        + "\x1f"
        + text(Col.recipient)
        + "\x1f"
        + text(Col.description)
        + "\x1f"
        + df[Col.value].map("{:.2f}".format)
    )
    return base + "\x1f" + base.groupby(base).cumcount().astype(str)


def split_duplicates(new: pd.DataFrame, existing: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``(unknown, already_known)`` rows of ``new`` compared with ``existing``."""
    if new.empty or existing.empty:
        return new, new.iloc[0:0]
    known = duplicate_keys(new).isin(set(duplicate_keys(existing)))
    return new.loc[~known].reset_index(drop=True), new.loc[known].reset_index(drop=True)


def preview_import(
    table: pd.DataFrame,
    profile: ImportProfile,
    existing: pd.DataFrame | None = None,
    since: pd.Timestamp | None = None,
) -> ImportPreview:
    transactions, invalid, zero = to_transactions(table, profile)
    preview = ImportPreview(transactions, invalid=invalid, zero=zero)
    if not transactions.empty:
        preview.first_date = transactions[Col.date].min()
        preview.last_date = transactions[Col.date].max()
    if since is not None:
        keep = transactions[Col.date] >= pd.Timestamp(since)
        preview.before_since = int((~keep).sum())
        transactions = transactions.loc[keep].reset_index(drop=True)
    if profile.drop_duplicates and existing is not None:
        transactions, preview.duplicates = split_duplicates(transactions, existing)
    preview.transactions = transactions
    return preview
