"""Budget by the 50/30/20 rule on the accrual basis.

Needs, wants and savings are compared with shares of the net income (by default 50 %, 30 % and 20 %). The savings
rate is what is left of the income after consumption (needs and wants); it should neither fall below its target,
which would not keep up the standard of living, nor stay far above it, which would be a life not lived.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.accrual import accrue
from mymoneyvisualizer.domain.analysis import filter_transactions
from mymoneyvisualizer.domain.categories import category_at_level
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import (
    CONSUMPTION_GROUPS,
    GROUP_INCOME,
    GROUP_NEEDS,
    GROUP_SAVINGS,
    GROUP_WANTS,
    GROUPS,
    GroupAssignment,
)

#: Months of the moving average that smooths the budget graph.
SMOOTHING_MONTHS = 12
#: Column of :func:`group_totals`: income minus needs and wants.
SAVED = "saved"


@dataclass
class BudgetSeries:
    """Accrued monthly amounts per main category from the first to the last recorded month."""

    monthly: pd.DataFrame
    last_date: pd.Timestamp | None


def budget_series(
    categorized: pd.DataFrame,
    *,
    own_accounts: Collection[str] = (),
    excluded_categories: Collection[str] = (),
) -> BudgetSeries:
    """Accrued monthly amounts per main category, without internal transfers and excluded categories.

    The part of a spread payment after the last recorded transaction is not used yet and left out.
    """
    data = filter_transactions(categorized, excluded_categories=excluded_categories, own_accounts=own_accounts)
    if data.empty:
        return BudgetSeries(pd.DataFrame(index=pd.PeriodIndex([], freq="M")), None)
    data = data.assign(**{Col.category: category_at_level(data[Col.category], 0)})
    last_date = data[Col.date].max()
    monthly = accrue(data)
    return BudgetSeries(monthly.loc[: pd.Period(last_date, freq="M")], last_date)


def smooth(monthly: pd.DataFrame) -> pd.DataFrame:
    """Moving average over the last :data:`SMOOTHING_MONTHS` months, for a calm long-term view."""
    return monthly.rolling(SMOOTHING_MONTHS, min_periods=1).mean()


def _group_of(groups: Sequence[GroupAssignment]) -> dict[str, str]:
    return {a.category: a.group for a in groups}


def group_totals(monthly: pd.DataFrame, groups: Sequence[GroupAssignment]) -> pd.DataFrame:
    """Per month: the income, the money used per budget group (positive) and :data:`SAVED`.

    Main categories without a group count as needs.
    """
    group_of = _group_of(groups)
    totals = pd.DataFrame(0.0, index=monthly.index, columns=[*GROUPS, SAVED])
    for category in monthly.columns:
        group = group_of.get(category, GROUP_NEEDS)
        sign = 1.0 if group == GROUP_INCOME else -1.0
        totals[group] += sign * monthly[category]
    totals[SAVED] = totals[GROUP_INCOME] - totals[list(CONSUMPTION_GROUPS)].sum(axis=1)
    return totals


def stacked_curves(
    monthly: pd.DataFrame, groups: Sequence[GroupAssignment], group: str
) -> list[tuple[str, np.ndarray]]:
    """Cumulative curves of the money used per category of one group (positive), from the bottom up.

    The bottom category is the last one of the group in ``groups``, so the order of ``groups`` is the stacking
    order from the top.
    """
    curves = []
    level = np.zeros(len(monthly))
    for assignment in reversed(groups):
        if assignment.group != group or assignment.category not in monthly.columns:
            continue
        level = level - monthly[assignment.category].to_numpy()
        curves.append((assignment.category, level))
    return curves


@dataclass
class GroupReport:
    group: str
    #: target share of the income
    target: float
    #: money used in the months of the report (positive)
    amount: float
    #: (category, amount), largest first
    categories: list[tuple[str, float]]


@dataclass
class BudgetReport:
    start_year: int
    end_year: int
    #: months of the budget period with data
    months: int
    period_months: int
    last_date: pd.Timestamp
    income: float
    needs: GroupReport
    wants: GroupReport
    #: transfers to savings and investments that are not tracked as an account
    savings: GroupReport

    @property
    def is_complete(self) -> bool:
        return self.months >= self.period_months

    @property
    def saved(self) -> float:
        """Income minus consumption: transferred to savings, left on the accounts or kept as residual value."""
        return self.income - self.needs.amount - self.wants.amount

    def share(self, amount: float) -> float | None:
        return amount / self.income if self.income > 0 else None

    @property
    def savings_rate(self) -> float | None:
        return self.share(self.saved)

    @property
    def room_per_month(self) -> float | None:
        """How much more could be spent per month while still reaching the savings target (negative: too much)."""
        if self.months <= 0 or self.income <= 0:
            return None
        return (self.saved - self.savings.target * self.income) / self.months

    def per_month(self, amount: float) -> float:
        return amount / self.months if self.months else 0.0


def budget_report(
    series: BudgetSeries,
    groups: Sequence[GroupAssignment],
    start_year: int,
    end_year: int,
    shares: Mapping[str, float],
) -> BudgetReport | None:
    """Income, needs, wants and savings in the budget period ``start_year``-``end_year`` (whole years).

    ``shares`` are the target shares of needs and wants; the rest of the income is the savings target.
    """
    monthly = series.monthly
    if monthly.empty or series.last_date is None:
        return None
    period = monthly.loc[(monthly.index.year >= start_year) & (monthly.index.year <= end_year)]
    group_of = _group_of(groups)
    totals = period.sum()

    def report(group: str, target: float) -> GroupReport:
        members = [c for c in period.columns if group_of.get(c, GROUP_NEEDS) == group]
        used = [(c, float(-totals[c])) for c in members if abs(totals[c]) >= 0.005]  # without empty categories
        used.sort(key=lambda item: item[1], reverse=True)
        return GroupReport(group, target, float(sum(amount for _, amount in used)), used)

    needs, wants = shares.get(GROUP_NEEDS, 0.0), shares.get(GROUP_WANTS, 0.0)
    income = sum(float(totals[c]) for c in period.columns if group_of.get(c) == GROUP_INCOME)
    return BudgetReport(
        start_year=start_year,
        end_year=end_year,
        months=len(period),
        period_months=12 * (end_year - start_year + 1),
        last_date=series.last_date,
        income=income,
        needs=report(GROUP_NEEDS, needs),
        wants=report(GROUP_WANTS, wants),
        savings=report(GROUP_SAVINGS, max(0.0, 1.0 - needs - wants)),
    )
