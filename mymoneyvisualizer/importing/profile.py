"""Import profile: how to read the CSV export of one bank."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from typing import Any

#: Columns chosen in the import window, each refers to one column of the export (or is empty).
MAPPING_FIELDS = ("col_date", "col_recipient", "col_description", "col_value", "col_debit", "col_credit", "col_sign")
#: Recipient and description are optional, e.g. credit card exports only have a description.
REQUIRED_FIELDS = ("col_date", "col_value")
VALUE_FIELDS = ("col_value", "col_debit", "col_credit")

#: Column name keywords per mapping field, most specific first. Matching is case insensitive.
COLUMN_KEYWORDS = {
    "col_date": ("buchungstag", "buchungsdatum", "buchung", "datum", "date"),
    "col_recipient": (
        "empfänger",
        "empfaenger",
        "begünstigter",
        "beguenstigter",
        "auftraggeber",
        "zahlungspflichtige",
        "zahlungsbeteiligter",
        "payee",
        "recipient",
        "counterparty",
        "partner",
        "name",
    ),
    "col_description": (
        "verwendungszweck",
        "buchungstext",
        "beschreibung",
        "description",
        "memo",
        "purpose",
        "details",
        "payment reference",
        "bezeichnung",
        "betreff",
        "text",
        "typ",
    ),
    "col_value": ("betrag", "amount", "umsatz", "netto", "value"),
}
#: Only used if no column matches :data:`COLUMN_KEYWORDS` (value date instead of booking date).
FALLBACK_KEYWORDS = {"col_date": ("valuta", "wertstellung")}
#: Columns that hold account data, never the name of a recipient (e.g. Commerzbank "Auftraggeberkonto").
NOT_A_NAME = {"col_recipient": re.compile(r"konto|iban|bic|blz|bankleitzahl|nummer|\bnr\b|e ?mail")}

#: Exact column names of separate debit / credit amount columns (e.g. Deutsche Bank "Soll" and "Haben").
DEBIT_COLUMNS = ("soll", "debit", "belastung", "ausgang")
CREDIT_COLUMNS = ("haben", "credit", "gutschrift", "eingang")
#: Exact column names of amounts that belong to the value, e.g. fees and taxes of a broker.
EXTRA_VALUE_COLUMNS = ("fee", "fees", "gebühr", "gebühren", "tax", "taxes", "steuer", "steuern")
#: Values of a debit/credit indicator column (e.g. Volksbank "S" / "H" next to an unsigned amount).
DEBIT_MARKERS = frozenset({"s", "soll", "d", "debit", "dr", "-", "belastung"})
CREDIT_MARKERS = frozenset({"h", "haben", "c", "credit", "cr", "+", "gutschrift"})


@dataclass
class ImportProfile:
    """How to read one export. The value of a transaction is

    ``col_value + sum(col_value_extra) - |col_debit| + |col_credit|``, then signed by ``col_sign`` if set.
    """

    name: str = ""
    encoding: str = "utf-8"
    separator: str = ";"
    decimal: str = ","
    thousands: str = "."
    dayfirst: bool = True
    skiprows: int = 0
    col_date: str = ""
    col_recipient: str = ""
    col_description: str = ""
    col_value: str = ""
    col_value_extra: list[str] = field(default_factory=list)
    col_debit: str = ""
    col_credit: str = ""
    col_sign: str = ""
    drop_duplicates: bool = True

    @property
    def mapping(self) -> dict[str, Any]:
        return {**{f: getattr(self, f) for f in MAPPING_FIELDS}, "col_value_extra": list(self.col_value_extra)}

    def missing_columns(self, available: Iterable[str]) -> list[str]:
        """Required mapping fields that are not set and fields pointing to a column the file does not have."""
        available = set(available)
        missing = []
        for name in MAPPING_FIELDS:
            column = getattr(self, name)
            unset = (name == "col_date" and not column) or (
                name == "col_value" and not any(getattr(self, f) for f in VALUE_FIELDS)
            )
            if unset or (column and column not in available):
                missing.append(name)
        if any(c not in available for c in self.col_value_extra):
            missing.append("col_value_extra")
        return missing

    def errors(self) -> dict[str, str]:
        errors = {}
        if len(self.separator) != 1:
            errors["separator"] = "separator must be exactly one character"
        if len(self.decimal) != 1:
            errors["decimal"] = "decimal mark must be exactly one character"
        if len(self.thousands) > 1:
            errors["thousands"] = "thousands separator must be at most one character"
        elif self.thousands and self.thousands == self.decimal:
            errors["thousands"] = "thousands separator and decimal mark must differ"
        if self.skiprows < 0:
            errors["skiprows"] = "header line must not be negative"
        return errors

    def with_mapping(self, **mapping: Any) -> ImportProfile:
        return replace(self, **mapping)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ImportProfile:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known and v is not None}
        for key in ("name", "encoding", "separator", "decimal", "thousands", *MAPPING_FIELDS):
            if key in values:
                values[key] = str(values[key])
        if "col_value_extra" in values:
            extra = values["col_value_extra"]
            values["col_value_extra"] = [str(c) for c in extra] if isinstance(extra, list | tuple) else []
        if "skiprows" in values:
            values["skiprows"] = int(values["skiprows"])
        for key in ("dayfirst", "drop_duplicates"):
            if key in values:
                values[key] = bool(values[key])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: list(v) if isinstance(v := getattr(self, f.name), list) else v for f in fields(self)}


def fold(name: str) -> str:
    """Lower case ASCII letters, digits and spaces only.

    Broken exports have headers like ``ZahlungsempfÃ¤nger`` or ``Beg�nstigter``; folded they still match
    the folded keywords ``empfnger`` / ``begnstigter``.
    """
    return re.sub(r"[^a-z0-9 ]", "", name.lower()).strip()


def column_candidates(columns: Sequence[str], field_name: str) -> list[str]:
    """Columns whose name fits ``field_name``, best first: exact keyword matches, then partial matches."""
    folded = [(c, fold(c)) for c in columns]
    excluded = NOT_A_NAME.get(field_name)
    candidates: list[str] = []
    for keywords in (COLUMN_KEYWORDS[field_name], FALLBACK_KEYWORDS.get(field_name, ())):
        for exact in (True, False):
            for keyword in map(fold, keywords):
                for column, name in folded:
                    if column in candidates or (excluded is not None and excluded.search(name)):
                        continue
                    if name == keyword if exact else keyword in name:
                        candidates.append(column)
    return candidates


def guess_mapping(columns: Sequence[str]) -> dict[str, str]:
    """Propose date, recipient, description and value columns from the names used by common bank exports."""
    mapping: dict[str, str] = {}
    for field_name in COLUMN_KEYWORDS:
        column = next((c for c in column_candidates(columns, field_name) if c not in mapping.values()), None)
        if column is not None:
            mapping[field_name] = column
    return mapping


def find_profile(profiles: Iterable[ImportProfile], columns: Iterable[str]) -> ImportProfile | None:
    """First profile whose mapped columns all exist in the file."""
    columns = list(columns)
    for profile in profiles:
        if not profile.missing_columns(columns):
            return profile
    return None
