"""Plain data objects of the application. They know how to (de)serialize themselves, nothing else."""

from __future__ import annotations

import datetime
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

#: Budget groups of the 50/30/20 rule. Needs and wants are consumption, savings is what is put aside.
GROUP_INCOME = "income"
GROUP_NEEDS = "needs"
GROUP_WANTS = "wants"
GROUP_SAVINGS = "savings"
GROUPS = (GROUP_INCOME, GROUP_NEEDS, GROUP_WANTS, GROUP_SAVINGS)
CONSUMPTION_GROUPS = (GROUP_NEEDS, GROUP_WANTS)

#: Shares of the net income for needs and wants; the rest is the savings target.
DEFAULT_BUDGET_SHARES = {GROUP_NEEDS: 0.5, GROUP_WANTS: 0.3}

#: Longest spread: 50 years.
MAX_SPREAD_MONTHS = 600


def clean_months(value: Any) -> int:
    """Number of months a payment is spread over; 0 means it counts in the month of payment."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return int(min(max(number, 0), MAX_SPREAD_MONTHS))


def clean_percent(value: Any) -> int:
    """Expected residual value in whole percent of the price (0-99)."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0
    if not math.isfinite(number):
        return 0
    return int(min(max(number, 0), 99))


def _str(value: Any) -> str:
    return "" if value is None else str(value)


def _spread_dict(spread_months: int, residual_percent: int) -> dict[str, int]:
    """Spread fields for YAML, left out when the payment is not spread."""
    if not spread_months:
        return {}
    spread = {"spread_months": spread_months}
    if residual_percent:
        spread["residual_percent"] = residual_percent
    return spread


@dataclass
class Rule:
    """Assigns ``category`` to every transaction whose recipient and description match the regexes.

    ``spread_months`` > 0 spreads every matched payment over that many months, starting with the month of payment:
    the service period of a prepayment or the useful life of a purchase. ``residual_percent`` of the price is the
    expected residual value of a purchase; it is not consumed.
    """

    name: str
    category: str = ""
    regex_recipient: str = ""
    regex_description: str = ""
    spread_months: int = 0
    residual_percent: int = 0

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Rule:
        return cls(
            name=_str(data.get("name")),
            category=_str(data.get("category")),
            regex_recipient=_str(data.get("regex_recipient")),
            regex_description=_str(data.get("regex_description")),
            spread_months=clean_months(data.get("spread_months")),
            residual_percent=clean_percent(data.get("residual_percent")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "regex_recipient": self.regex_recipient,
            "regex_description": self.regex_description,
            **_spread_dict(self.spread_months, self.residual_percent),
        }


@dataclass
class ManualCategory:
    """Category and spread of a single transaction; wins over all rules.

    ``sale_of`` links the sale of a spread purchase (e.g. a used car) to the purchase: the real loss of value,
    price minus sale proceeds, is then spread over the months from the purchase to the sale.
    """

    transaction_id: str
    category: str
    spread_months: int = 0
    residual_percent: int = 0
    sale_of: str = ""

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> ManualCategory:
        return cls(
            transaction_id=_str(data.get("transaction_id")),
            category=_str(data.get("category")),
            spread_months=clean_months(data.get("spread_months")),
            residual_percent=clean_percent(data.get("residual_percent")),
            sale_of=_str(data.get("sale_of")),
        )

    def to_dict(self) -> dict[str, Any]:
        data = {"transaction_id": self.transaction_id, "category": self.category}
        data.update(_spread_dict(self.spread_months, self.residual_percent))
        if self.sale_of:
            data["sale_of"] = self.sale_of
        return data


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
    hide_internal_transfers: bool = True
    budget_start: int = field(default_factory=_current_year)
    budget_end: int = field(default_factory=_current_year)
    #: target shares of the net income for needs and wants
    budget_shares: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_BUDGET_SHARES))

    @property
    def savings_share(self) -> float:
        """The savings target is what the needs and wants leave of the income."""
        return max(0.0, 1.0 - sum(self.budget_shares.values()))

    @classmethod
    def from_dict(cls, data: Mapping[str, Any] | None) -> Settings:
        settings = cls()
        if not data:
            return settings
        excluded = data.get("excluded_categories")
        if isinstance(excluded, Sequence) and not isinstance(excluded, str):
            settings.excluded_categories = [str(c) for c in excluded]
        if "hide_internal_transfers" in data:
            settings.hide_internal_transfers = bool(data["hide_internal_transfers"])

        budget = data.get("budget")
        budget = budget if isinstance(budget, Mapping) else {}
        start, end = budget.get("start"), budget.get("end")
        if isinstance(start, int) and isinstance(end, int):
            settings.budget_start, settings.budget_end = min(start, end), max(start, end)
        shares = budget.get("shares")
        shares = shares if isinstance(shares, Mapping) else {}
        for group in CONSUMPTION_GROUPS:
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
