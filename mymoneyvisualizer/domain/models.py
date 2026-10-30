"""Plain data objects of the application. They know how to (de)serialize themselves, nothing else."""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

CATEGORY_INCOME = "income"
CATEGORY_BASIC = "basic"
CATEGORY_OPTIONAL = "optional"
CATEGORIES = (CATEGORY_INCOME, CATEGORY_BASIC, CATEGORY_OPTIONAL)
EXPENSE_CATEGORIES = (CATEGORY_BASIC, CATEGORY_OPTIONAL)

DEFAULT_BUDGET_FACTORS = {CATEGORY_BASIC: 0.3, CATEGORY_OPTIONAL: 0.5}


def clean_recurring(value: Any) -> int | None:
    """Recurrence period in years, or ``None`` if the transaction is not recurring."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 1:
        return None
    return int(number)


def recurring_to_float(value: int | None) -> float:
    return math.nan if value is None else float(value)


def _str(value: Any) -> str:
    return "" if value is None else str(value)


@dataclass
class Tagger:
    """Rule that assigns ``tag`` to every transaction whose recipient and description match the regexes."""

    name: str
    tag: str = ""
    regex_recipient: str = ""
    regex_description: str = ""
    recurring: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Tagger:
        return cls(
            name=_str(data.get("name")),
            tag=_str(data.get("tag")),
            regex_recipient=_str(data.get("regex_recipient")),
            regex_description=_str(data.get("regex_description")),
            recurring=clean_recurring(data.get("recurring")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tag": self.tag,
            "regex_recipient": self.regex_recipient,
            "regex_description": self.regex_description,
            "recurring": self.recurring,
        }


@dataclass
class OneTimeTag:
    """Tag of a single transaction; wins over all taggers."""

    transaction_id: str
    tag: str
    recurring: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OneTimeTag:
        return cls(
            transaction_id=_str(data.get("transaction_id")),
            tag=_str(data.get("tag")),
            recurring=clean_recurring(data.get("recurring")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"transaction_id": self.transaction_id, "tag": self.tag, "recurring": self.recurring}


@dataclass
class TagCategory:
    """Assigns a base tag to income, basic or optional expenses. The list order is the stacking order."""

    name: str
    category: str = CATEGORY_BASIC

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> TagCategory:
        category = _str(data.get("category"))
        return cls(name=_str(data.get("name")), category=category if category in CATEGORIES else CATEGORY_BASIC)

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "category": self.category}


def _current_year() -> int:
    return datetime.date.today().year


@dataclass
class Settings:
    excluded_tags: list[str] = field(default_factory=list)
    budget_start: int = field(default_factory=_current_year)
    budget_end: int = field(default_factory=_current_year)
    budget_factors: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BUDGET_FACTORS))
    hide_transfers: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Settings:
        settings = cls()
        if not data:
            return settings
        excluded = data.get("excluded_tags")
        if isinstance(excluded, Sequence) and not isinstance(excluded, str):
            settings.excluded_tags = [str(t) for t in excluded]
        if "hide_transfers" in data:
            settings.hide_transfers = bool(data["hide_transfers"])

        budget = data.get("budget")
        budget = budget if isinstance(budget, Mapping) else {}
        start, end = budget.get("start"), budget.get("end")
        if isinstance(start, int) and isinstance(end, int):
            settings.budget_start, settings.budget_end = min(start, end), max(start, end)
        factors = budget.get("factors")
        factors = factors if isinstance(factors, Mapping) else {}
        for cat in EXPENSE_CATEGORIES:
            factor = factors.get(cat)
            if isinstance(factor, int | float) and 0 <= factor <= 1:
                settings.budget_factors[cat] = float(factor)
        return settings

    def to_dict(self) -> dict[str, Any]:
        return {
            "excluded_tags": list(self.excluded_tags),
            "hide_transfers": self.hide_transfers,
            "budget": {
                "start": self.budget_start,
                "end": self.budget_end,
                "factors": dict(self.budget_factors),
            },
        }


def _match_orders(old_names: list[str], new_names: list[str]) -> list[str]:
    """Merge a re-ordered subset into the full order, keeping names missing in the subset where they were."""
    new_order: list[str] = []
    i_old = i_new = 0
    while i_old < len(old_names) and i_new < len(new_names):
        old, new = old_names[i_old], new_names[i_new]
        if old == new:
            if new not in new_order:
                new_order.append(new)
            i_old += 1
            i_new += 1
        elif old not in new_names:
            new_order.append(old)
            i_old += 1
        else:
            if new not in new_order:
                new_order.append(new)
            i_new += 1
    for name in old_names[i_old:] + new_names[i_new:]:
        if name not in new_order:
            new_order.append(name)
    return new_order


def reorder_categories(current: Sequence[TagCategory], assignment: Mapping[str, Sequence[str]]) -> list[TagCategory]:
    """Apply a drag-and-drop result: ``assignment`` maps a category to the tag names shown in its list."""
    by_name = {c.name: TagCategory(c.name, c.category) for c in current}
    new_names: list[str] = []
    for category, names in assignment.items():
        for name in names:
            by_name.setdefault(name, TagCategory(name, category)).category = category
            new_names.append(name)
    order = _match_orders([c.name for c in current], new_names)
    return [by_name[name] for name in order]
