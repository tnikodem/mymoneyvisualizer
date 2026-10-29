"""Turn a CSV export into normalized transactions and find the ones that are already known."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from mymoneyvisualizer.domain.columns import Col, empty_transactions, normalize_transactions
from mymoneyvisualizer.importing.profile import ImportProfile
from mymoneyvisualizer.importing.sniff import clean_columns, read_text

ISO_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S", "%Y%m%d")
DAYFIRST_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y")
MONTHFIRST_FORMATS = ("%m/%d/%Y", "%m/%d/%y", "%m-%d-%Y", "%m-%d-%y", "%m.%d.%Y")


class ImportFormatError(ValueError):
    """The file cannot be read with the given profile."""


def read_table(path: str | Path, profile: ImportProfile) -> pd.DataFrame:
    """All cells of the export as strings; the header is the line ``profile.skiprows``."""
    errors = profile.errors()
    if "separator" in errors or "skiprows" in errors:
        raise ImportFormatError(errors.get("separator") or errors["skiprows"])
    text, _ = read_text(path, profile.encoding)
    lines = text.splitlines(keepends=True)[profile.skiprows :]
    try:
        records = list(csv.reader(lines, delimiter=profile.separator))
    except csv.Error as e:
        raise ImportFormatError(str(e)) from e
    records = [r for r in records if any(cell.strip() for cell in r)]
    if not records:
        return pd.DataFrame()
    columns = clean_columns(records[0])
    width = len(columns)
    rows = [(r + [""] * width)[:width] for r in records[1:]]
    return pd.DataFrame(rows, columns=columns, dtype=str)


def parse_amounts(values: pd.Series, decimal: str = ",", thousands: str = ".") -> pd.Series:
    """Parse ``1.234,56``, ``-3,50 €``, ``(12.00)`` or ``50,00-`` style amounts. Invalid values become NaN."""
    text = values.astype(str).str.strip()
    text = text.str.replace(r"[€$£\s ']|EUR|USD|CHF", "", regex=True)
    negative = text.str.match(r"^\(.*\)$") | (text.str.endswith("-") & ~text.str.startswith("-"))
    text = text.str.strip("()").str.rstrip("-")
    if thousands:
        text = text.str.replace(thousands, "", regex=False)
    if decimal != ".":
        text = text.str.replace(decimal, ".", regex=False)
    numbers = pd.to_numeric(text, errors="coerce").astype(float)
    return numbers.where(~negative, -numbers.abs())


def parse_dates(values: pd.Series, dayfirst: bool = True) -> pd.Series:
    """Parse dates with the format that understands the most values (day first formats preferred if asked)."""
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
    return best.astype("datetime64[ns]")


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


def to_transactions(table: pd.DataFrame, profile: ImportProfile) -> tuple[pd.DataFrame, int, int]:
    """``(transactions, invalid, zero)``: rows without a valid date/amount and zero amounts are dropped."""
    missing = profile.missing_columns(table.columns)
    if missing:
        raise ImportFormatError("please select a column for " + ", ".join(m.removeprefix("col_") for m in missing))
    errors = profile.errors()
    if errors:
        raise ImportFormatError(next(iter(errors.values())))
    df = pd.DataFrame(
        {
            Col.date: parse_dates(table[profile.col_date], profile.dayfirst),
            Col.recipient: table[profile.col_recipient].astype(str).str.strip(),
            Col.description: table[profile.col_description].astype(str).str.strip(),
            Col.value: parse_amounts(table[profile.col_value], profile.decimal, profile.thousands),
        }
    )
    invalid = df[Col.date].isna() | df[Col.value].isna()
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
