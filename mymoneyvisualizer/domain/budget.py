"""Budget view: spread recurring transactions over time and compare expenses with income."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.analysis import filter_transactions
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import GROUP_INCOME, GroupAssignment

#: Recurring transactions of the last ``n`` years are projected this many years past the budget period.
HORIZON_YEARS = 5
#: Transactions recurring every 10 or more years are never projected into the future.
MAX_PROJECTED_RECURRENCE = 9


def _month_number(dates: pd.Series) -> np.ndarray:
    return (dates.dt.year * 12 + dates.dt.month - 1).to_numpy()


def _period(month_number: int) -> pd.Period:
    return pd.Period(year=month_number // 12, month=month_number % 12 + 1, freq="M")


def amortize_recurring(df: pd.DataFrame, horizon_end: pd.Period) -> pd.DataFrame:
    """Monthly amounts per category where a transaction recurring every ``r`` years is spread over ``12 * r`` months.

    Recurring transactions of the most recent ``r`` years are expected to happen again and are continued
    up to ``horizon_end``; older ones only cover their own ``12 * r`` months. ``df`` needs the columns
    date, category, value and recurring (NaN means every year). Returns months as rows and categories as columns.
    """
    if df.empty:
        return pd.DataFrame(index=pd.PeriodIndex([], freq="M"))
    recurring = df[Col.recurring].fillna(1).clip(lower=1).astype(int)
    last_recorded = df[Col.date].max()
    current = np.zeros(len(df), dtype=bool)
    for years in range(1, MAX_PROJECTED_RECURRENCE + 1):
        current |= ((recurring == years) & (df[Col.date] > last_recorded - pd.DateOffset(years=years))).to_numpy()

    groups = (
        pd.DataFrame(
            {
                Col.category: df[Col.category].to_numpy(),
                "years": recurring.to_numpy(),
                "month": _month_number(df[Col.date]),
                "current": current,
                Col.value: df[Col.value].to_numpy(),
            }
        )
        .groupby([Col.category, "years", "month", "current"], as_index=False)[Col.value]
        .sum()
    )
    horizon = horizon_end.year * 12 + horizon_end.month - 1
    start = groups["month"].to_numpy()
    span_end = start + 12 * groups["years"].to_numpy() - 1
    end = np.where(groups["current"].to_numpy(), horizon, np.minimum(span_end, horizon))
    keep = start <= horizon
    if not keep.any():
        return pd.DataFrame(index=pd.PeriodIndex([], freq="M"))
    groups, start, end = groups.loc[keep], start[keep], end[keep]
    amount = (groups[Col.value] / (12 * groups["years"])).to_numpy()

    categories = sorted(groups[Col.category].unique())
    category_index = pd.Index(categories).get_indexer(groups[Col.category])
    first, last = int(start.min()), int(end.max())
    steps = np.zeros((len(categories), last - first + 2))
    np.add.at(steps, (category_index, start - first), amount)
    np.add.at(steps, (category_index, end - first + 1), -amount)
    values = np.cumsum(steps, axis=1)[:, :-1]
    index = pd.period_range(_period(first), _period(last), freq="M")
    return pd.DataFrame(values.T, index=index, columns=categories)


@dataclass
class BudgetSeries:
    monthly: pd.DataFrame
    last_recorded_date: pd.Timestamp | None


def budget_series(
    categorized: pd.DataFrame,
    *,
    budget_end_year: int,
    own_accounts: Collection[str] = (),
    excluded_categories: Collection[str] = (),
    horizon_years: int = HORIZON_YEARS,
) -> BudgetSeries:
    """Amortized monthly amounts per main category, ignoring transfers between own accounts."""
    data = filter_transactions(categorized, excluded_categories=excluded_categories, own_accounts=own_accounts)
    if data.empty:
        return BudgetSeries(pd.DataFrame(index=pd.PeriodIndex([], freq="M")), None)
    data = data.assign(**{Col.category: data[Col.category].astype(str).str.split(".", n=1).str[0]})
    horizon = pd.Period(year=budget_end_year + horizon_years, month=12, freq="M")
    return BudgetSeries(amortize_recurring(data, horizon), data[Col.date].max())


def income_series(monthly: pd.DataFrame, groups: Sequence[GroupAssignment]) -> pd.Series:
    income = pd.Series(0.0, index=monthly.index)
    for assignment in groups:
        if assignment.group == GROUP_INCOME and assignment.category in monthly.columns:
            income = income + monthly[assignment.category]
    return income


def stacked_expenses(
    monthly: pd.DataFrame, groups: Sequence[GroupAssignment], group: str
) -> list[tuple[str, np.ndarray]]:
    """Cumulative expense curves (positive numbers) of one group, in reverse group order."""
    curves = []
    level = np.zeros(len(monthly))
    for assignment in reversed(groups):
        if assignment.group != group or assignment.category not in monthly.columns:
            continue
        level = level - monthly[assignment.category].to_numpy()
        curves.append((assignment.category, level))
    return curves


@dataclass
class BudgetReport:
    group: str
    start_year: int
    end_year: int
    share: float
    expected_total: float
    consumed: list[tuple[str, float]]
    total_consumed: float
    total_days: int
    covered_days: int
    last_recorded_date: pd.Timestamp

    @property
    def is_complete(self) -> bool:
        return self.covered_days >= self.total_days

    @property
    def covered_percent(self) -> float:
        return 100.0 * self.covered_days / self.total_days

    @property
    def remaining_months(self) -> float:
        return (self.total_days - self.covered_days) / 30.0

    @property
    def balance(self) -> float:
        """Difference between budget and consumption (positive means money left)."""
        return self.expected_total - self.total_consumed

    @property
    def remaining_per_month(self) -> float | None:
        if self.remaining_months <= 0:
            return None
        return self.balance / self.remaining_months

    @property
    def trend(self) -> float | None:
        """Expected balance at the end of the period if spending continues at the current rate."""
        if self.covered_days <= 0:
            return None
        return self.expected_total - self.total_consumed * self.total_days / self.covered_days


def covered_days(start_year: int, end_year: int, last_recorded_date: pd.Timestamp) -> tuple[int, int]:
    """``(covered, total)`` days of the budget period up to and including ``last_recorded_date``."""
    first = pd.Timestamp(start_year, 1, 1)
    total = (pd.Timestamp(end_year, 12, 31) - first).days + 1
    covered = (pd.Timestamp(last_recorded_date).normalize() - first).days + 1
    return int(min(max(covered, 0), total)), int(total)


def budget_report(
    series: BudgetSeries,
    groups: Sequence[GroupAssignment],
    group: str,
    start_year: int,
    end_year: int,
    share: float,
) -> BudgetReport | None:
    monthly = series.monthly
    if monthly.empty or series.last_recorded_date is None:
        return None
    in_period = (monthly.index.year >= start_year) & (monthly.index.year <= end_year)
    expected = float(income_series(monthly, groups)[in_period].sum() * share)

    consumed = [
        (a.category, float(-monthly.loc[in_period, a.category].sum()))
        for a in reversed(groups)
        if a.group == group and a.category in monthly.columns
    ]
    consumed.sort(key=lambda item: item[1], reverse=True)
    covered, total = covered_days(start_year, end_year, series.last_recorded_date)
    return BudgetReport(
        group=group,
        start_year=start_year,
        end_year=end_year,
        share=share,
        expected_total=expected,
        consumed=consumed,
        total_consumed=float(sum(amount for _, amount in consumed)),
        total_days=total,
        covered_days=covered,
        last_recorded_date=series.last_recorded_date,
    )
