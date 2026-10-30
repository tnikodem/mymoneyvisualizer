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

from mymoneyvisualizer.domain.accrual import (
    AMOUNT,
    FIRST,
    LAST,
    accrue,
    linked_sales,
    month_numbers,
    schedule,
    to_period,
)
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
    LAST_12_MONTHS,
    GroupAssignment,
)

#: Months of the moving average that smooths the budget graph.
SMOOTHING_MONTHS = 12
#: Column of :func:`group_totals`: income minus needs and wants.
SAVED = "saved"
#: Columns of :func:`contributions`.
IN_PERIOD, SPREAD_AMOUNT, SPREAD_FROM, SPREAD_TO, SOLD = (
    "in_period",
    "spread_amount",
    "spread_from",
    "spread_to",
    "sold",
)


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
    """Moving average over the last :data:`SMOOTHING_MONTHS` months, for a calm long-term view.

    It starts with the first month that has a full year before it: an average of fewer months would show a
    single bonus or yearly payment as a spike.
    """
    return monthly.rolling(SMOOTHING_MONTHS).mean().dropna(how="all")


def period_months(period: str, last_month: pd.Period) -> tuple[pd.Period, pd.Period]:
    """First and last month of a budget period, at most up to ``last_month`` (the last complete month).

    :data:`LAST_12_MONTHS` are the twelve months up to ``last_month``; a year such as ``"2025"`` is that calendar year,
    ``"2025-03:2026-02"`` the months from March 2025 to February 2026.
    """
    if period == LAST_12_MONTHS:
        return last_month - (SMOOTHING_MONTHS - 1), last_month
    if ":" in period:
        start, end = period.split(":")
        return pd.Period(start, freq="M"), min(pd.Period(end, freq="M"), last_month)
    year = int(period)
    return pd.Period(f"{year}-01", freq="M"), min(pd.Period(f"{year}-12", freq="M"), last_month)


def previous_months(start: pd.Period, end: pd.Period) -> tuple[pd.Period, pd.Period]:
    """The year before: the same months one year earlier."""
    return start - 12, end - 12


def contributions(
    categorized: pd.DataFrame,
    start: pd.Period,
    end: pd.Period,
    *,
    own_accounts: Collection[str] = (),
    excluded_categories: Collection[str] = (),
    categories: Collection[str] | None = None,
) -> pd.DataFrame:
    """Every transaction that counts in the months ``start`` to ``end`` on the accrual basis, oldest first.

    That includes payments made before ``start`` and spread into the period, and of a payment spread beyond the
    period only its share. :data:`IN_PERIOD` is the amount the transaction contributes to the period,
    :data:`SPREAD_AMOUNT` the whole amount that is spread (without the residual value or the proceeds of a sale),
    :data:`SPREAD_FROM` and :data:`SPREAD_TO` the months it is spread over, :data:`SOLD` marks a purchase whose sale is
    included (its sale has no row of its own). ``categories`` are main categories (``None``: all). Together the rows add
    up to the budget of the period.
    """
    data = filter_transactions(categorized, excluded_categories=excluded_categories, own_accounts=own_accounts)
    plan = schedule(data)
    if categories is not None:
        plan = plan.loc[category_at_level(plan[Col.category], 0).isin(list(categories)).to_numpy()]
    first, last = month_numbers(pd.Series([start.start_time, end.start_time]))
    overlap = (np.minimum(plan[LAST], last) - np.maximum(plan[FIRST], first) + 1).clip(lower=0)
    plan, overlap = plan.loc[overlap > 0], overlap[overlap > 0]
    rows = data.loc[plan.index].copy()
    rows[IN_PERIOD] = (plan[AMOUNT] * overlap).round(2)
    rows[SPREAD_AMOUNT] = (plan[AMOUNT] * (plan[LAST] - plan[FIRST] + 1)).round(2)
    rows[SPREAD_FROM] = [to_period(int(m)) for m in plan[FIRST]]
    rows[SPREAD_TO] = [to_period(int(m)) for m in plan[LAST]]
    sold = data.index[list(linked_sales(data))]
    rows[SOLD] = rows.index.isin(sold)
    return rows.sort_values(Col.date, kind="stable").reset_index(drop=True)


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
    #: first and last month of the budget period
    start: pd.Period
    end: pd.Period
    #: months of the budget period with data
    months: int
    last_date: pd.Timestamp
    income: float
    #: (category, amount that came in), largest first
    income_categories: list[tuple[str, float]]
    needs: GroupReport
    wants: GroupReport
    #: transfers to savings and investments that are not tracked as an account
    savings: GroupReport

    @property
    def period_months(self) -> int:
        return (self.end - self.start).n + 1

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
    start: pd.Period,
    end: pd.Period,
    shares: Mapping[str, float],
) -> BudgetReport | None:
    """Income, needs, wants and savings in the months ``start`` to ``end``.

    ``shares`` are the target shares of needs and wants; the rest of the income is the savings target.
    """
    monthly = series.monthly
    if monthly.empty or series.last_date is None:
        return None
    period = monthly.loc[(monthly.index >= start) & (monthly.index <= end)]
    group_of = _group_of(groups)
    totals = period.sum()

    def amounts(group: str, sign: float) -> list[tuple[str, float]]:
        """(category, amount), largest first, without empty categories; ``sign`` -1 makes spending positive."""
        members = [c for c in period.columns if group_of.get(c, GROUP_NEEDS) == group]
        used = [(c, float(sign * totals[c])) for c in members if abs(totals[c]) >= 0.005]
        return sorted(used, key=lambda item: item[1], reverse=True)

    def report(group: str, target: float) -> GroupReport:
        used = amounts(group, -1.0)
        return GroupReport(group, target, float(sum(amount for _, amount in used)), used)

    needs, wants = shares.get(GROUP_NEEDS, 0.0), shares.get(GROUP_WANTS, 0.0)
    income_categories = amounts(GROUP_INCOME, 1.0)
    return BudgetReport(
        start=start,
        end=end,
        months=len(period),
        last_date=series.last_date,
        income=float(sum(amount for _, amount in income_categories)),
        income_categories=income_categories,
        needs=report(GROUP_NEEDS, needs),
        wants=report(GROUP_WANTS, wants),
        savings=report(GROUP_SAVINGS, max(0.0, 1.0 - needs - wants)),
    )
