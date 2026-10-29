"""Import profile: how to read the CSV export of one bank."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from typing import Any

MAPPING_FIELDS = ("col_date", "col_recipient", "col_description", "col_value")

#: Column name keywords per mapping field, most specific first. Matching is case insensitive.
COLUMN_KEYWORDS = {
    "col_date": ("buchungstag", "buchungsdatum", "buchung", "datum", "date", "valuta", "wertstellung"),
    "col_recipient": (
        "empfänger",
        "empfaenger",
        "begünstigter",
        "beguenstigter",
        "auftraggeber",
        "zahlungspflichtige",
        "payee",
        "recipient",
        "counterparty",
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
        "text",
    ),
    "col_value": ("betrag", "amount", "umsatz", "value", "wert"),
}


@dataclass
class ImportProfile:
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
    drop_duplicates: bool = True

    @property
    def mapping(self) -> dict[str, str]:
        return {f: getattr(self, f) for f in MAPPING_FIELDS}

    def missing_columns(self, available: Iterable[str]) -> list[str]:
        """Mapping fields that are not set or point to a column the file does not have."""
        available = set(available)
        return [f for f in MAPPING_FIELDS if not getattr(self, f) or getattr(self, f) not in available]

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

    def with_mapping(self, **mapping: str) -> ImportProfile:
        return replace(self, **mapping)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ImportProfile:
        known = {f.name for f in fields(cls)}
        values = {k: v for k, v in data.items() if k in known and v is not None}
        if "separator" not in values and data.get("seperator") is not None:  # spelling of version 0.1
            values["separator"] = data["seperator"]
        for key in ("name", "encoding", "separator", "decimal", "thousands", *MAPPING_FIELDS):
            if key in values:
                values[key] = str(values[key])
        if "skiprows" in values:
            values["skiprows"] = int(values["skiprows"])
        for key in ("dayfirst", "drop_duplicates"):
            if key in values:
                values[key] = bool(values[key])
        return cls(**values)

    def to_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


def guess_mapping(columns: Sequence[str]) -> dict[str, str]:
    """Propose the columns for date, recipient, description and value based on common bank export names."""
    mapping: dict[str, str] = {}
    lowered = [(c, c.lower()) for c in columns]

    def first_match(keywords: Sequence[str], exact: bool) -> str | None:
        for keyword in keywords:
            for column, low in lowered:
                if column not in mapping.values() and (low == keyword if exact else keyword in low):
                    return column
        return None

    for field_name, keywords in COLUMN_KEYWORDS.items():
        column = first_match(keywords, exact=True) or first_match(keywords, exact=False)
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
