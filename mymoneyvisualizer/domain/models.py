"""Plain data objects of the application. They know how to (de)serialize themselves, nothing else."""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

GROUP_INCOME = "income"
GROUP_NEEDS = "needs"
GROUP_WANTS = "wants"
GROUPS = (GROUP_INCOME, GROUP_NEEDS, GROUP_WANTS)
EXPENSE_GROUPS = (GROUP_NEEDS, GROUP_WANTS)

DEFAULT_BUDGET_SHARES = {GROUP_NEEDS: 0.3, GROUP_WANTS: 0.5}


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
class Rule:
    """Rule that assigns ``category`` to every transaction whose recipient and description match the regexes."""

    name: str
    category: str = ""
    regex_recipient: str = ""
    regex_description: str = ""
    recurring: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        return cls(
            name=_str(data.get("name")),
            category=_str(data.get("category")),
            regex_recipient=_str(data.get("regex_recipient")),
            regex_description=_str(data.get("regex_description")),
            recurring=clean_recurring(data.get("recurring")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "regex_recipient": self.regex_recipient,
            "regex_description": self.regex_description,
            "recurring": self.recurring,
        }


@dataclass
class ManualCategory:
    """Category of a single transaction; wins over all rules."""

    transaction_id: str
    category: str
    recurring: int | None = None

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ManualCategory:
        return cls(
            transaction_id=_str(data.get("transaction_id")),
            category=_str(data.get("category")),
            recurring=clean_recurring(data.get("recurring")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"transaction_id": self.transaction_id, "category": self.category, "recurring": self.recurring}


@dataclass
class GroupAssignment:
    """Puts a main category into a budget group. The list order is the stacking order of the budget graph."""

    category: str
    group: str = GROUP_NEEDS

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> GroupAssignment:
        group = _str(data.get("group"))
        return cls(category=_str(data.get("category")), group=group if group in GROUPS else GROUP_NEEDS)

    def to_dict(self) -> dict[str, Any]:
        return {"category": self.category, "group": self.group}


def _current_year() -> int:
    return datetime.date.today().year


@dataclass
class Settings:
    excluded_categories: list[str] = field(default_factory=list)
    budget_start: int = field(default_factory=_current_year)
    budget_end: int = field(default_factory=_current_year)
    budget_shares: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BUDGET_SHARES))
    hide_internal_transfers: bool = True

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Settings:
        settings = cls()
        if not data:
            return settings
        excluded = data.get("excluded_categories")
        if isinstance(excluded, Sequence) and not isinstance(excluded, str):
            settings.excluded_categories = [str(t) for t in excluded]
        if "hide_internal_transfers" in data:
            settings.hide_internal_transfers = bool(data["hide_internal_transfers"])

        budget = data.get("budget")
        budget = budget if isinstance(budget, Mapping) else {}
        start, end = budget.get("start"), budget.get("end")
        if isinstance(start, int) and isinstance(end, int):
            settings.budget_start, settings.budget_end = min(start, end), max(start, end)
        shares = budget.get("shares")
        shares = shares if isinstance(shares, Mapping) else {}
        for group in EXPENSE_GROUPS:
            share = shares.get(group)
            if isinstance(share, int | float) and 0 <= share <= 1:
                settings.budget_shares[group] = float(share)
        return settings

    def to_dict(self) -> dict[str, Any]:
        return {
            "excluded_categories": list(self.excluded_categories),
            "hide_internal_transfers": self.hide_internal_transfers,
            "budget": {
                "start": self.budget_start,
                "end": self.budget_end,
                "shares": dict(self.budget_shares),
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


def reorder_groups(
    current: Sequence[GroupAssignment], assignment: Mapping[str, Sequence[str]]
) -> list[GroupAssignment]:
    """Apply a drag-and-drop result: ``assignment`` maps a group to the categories shown in its list."""
    by_category = {a.category: GroupAssignment(a.category, a.group) for a in current}
    new_order: list[str] = []
    for group, categories in assignment.items():
        for category in categories:
            by_category.setdefault(category, GroupAssignment(category, group)).group = group
            new_order.append(category)
    order = _match_orders([a.category for a in current], new_order)
    return [by_category[category] for category in order]
