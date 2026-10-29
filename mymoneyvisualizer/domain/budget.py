"""Budget view: spread recurring transactions over time and compare expenses with income."""

from __future__ import annotations

from collections.abc import Collection, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.analysis import filter_transactions
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import CATEGORY_INCOME, TagCategory

#: Recurring transactions of the last ``n`` years are projected this many years past the budget period.
HORIZON_YEARS = 5
#: Transactions recurring every 10 or more years are never projected into the future.
MAX_PROJECTED_RECURRENCE = 9


def _month_number(dates: pd.Series) -> np.ndarray:
    return (dates.dt.year * 12 + dates.dt.month - 1).to_numpy()


def _period(month_number: int) -> pd.Period:
    return pd.Period(year=month_number // 12, month=month_number % 12 + 1, freq="M")


def amortize_recurring(df: pd.DataFrame, horizon_end: pd.Period) -> pd.DataFrame:
    """Monthly amounts per tag where a transaction recurring every ``r`` years is spread over ``12 * r`` months.

    Recurring transactions of the most recent ``r`` years are expected to happen again and are continued
    up to ``horizon_end``; older ones only cover their own ``12 * r`` months. ``df`` needs the columns
    date, tag, value and recurring (NaN means every year). Returns months as rows and tags as columns.
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
                Col.tag: df[Col.tag].to_numpy(),
                "years": recurring.to_numpy(),
                "month": _month_number(df[Col.date]),
                "current": current,
                Col.value: df[Col.value].to_numpy(),
            }
        )
        .groupby([Col.tag, "years", "month", "current"], as_index=False)[Col.value]
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

    tags = sorted(groups[Col.tag].unique())
    tag_index = pd.Index(tags).get_indexer(groups[Col.tag])
    first, last = int(start.min()), int(end.max())
    steps = np.zeros((len(tags), last - first + 2))
    np.add.at(steps, (tag_index, start - first), amount)
    np.add.at(steps, (tag_index, end - first + 1), -amount)
    values = np.cumsum(steps, axis=1)[:, :-1]
    index = pd.period_range(_period(first), _period(last), freq="M")
    return pd.DataFrame(values.T, index=index, columns=tags)


@dataclass
class BudgetSeries:
    monthly: pd.DataFrame
    last_recorded_date: pd.Timestamp | None


def budget_series(
    tagged: pd.DataFrame,
    *,
    budget_end_year: int,
    transfer_accounts: Collection[str] = (),
    excluded_tags: Collection[str] = (),
    horizon_years: int = HORIZON_YEARS,
) -> BudgetSeries:
    """Amortized monthly amounts per base tag, ignoring transfers between own accounts."""
    data = filter_transactions(tagged, excluded_tags=excluded_tags, transfer_accounts=transfer_accounts)
    if data.empty:
        return BudgetSeries(pd.DataFrame(index=pd.PeriodIndex([], freq="M")), None)
    data = data.assign(**{Col.tag: data[Col.tag].astype(str).str.split(".", n=1).str[0]})
    horizon = pd.Period(year=budget_end_year + horizon_years, month=12, freq="M")
    return BudgetSeries(amortize_recurring(data, horizon), data[Col.date].max())


def income_series(monthly: pd.DataFrame, categories: Sequence[TagCategory]) -> pd.Series:
    income = pd.Series(0.0, index=monthly.index)
    for category in categories:
        if category.category == CATEGORY_INCOME and category.name in monthly.columns:
            income = income + monthly[category.name]
    return income


def stacked_expenses(
    monthly: pd.DataFrame, categories: Sequence[TagCategory], category: str
) -> list[tuple[str, np.ndarray]]:
    """Cumulative expense curves (positive numbers) of one category, in reverse category order."""
    curves = []
    level = np.zeros(len(monthly))
    for tag_category in reversed(categories):
        if tag_category.category != category or tag_category.name not in monthly.columns:
            continue
        level = level - monthly[tag_category.name].to_numpy()
        curves.append((tag_category.name, level))
    return curves


@dataclass
class BudgetReport:
    category: str
    start_year: int
    end_year: int
    factor: float
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
    categories: Sequence[TagCategory],
    category: str,
    start_year: int,
    end_year: int,
    factor: float,
) -> BudgetReport | None:
    monthly = series.monthly
    if monthly.empty or series.last_recorded_date is None:
        return None
    in_period = (monthly.index.year >= start_year) & (monthly.index.year <= end_year)
    expected = float(income_series(monthly, categories)[in_period].sum() * factor)

    consumed = [
        (c.name, float(-monthly.loc[in_period, c.name].sum()))
        for c in reversed(categories)
        if c.category == category and c.name in monthly.columns
    ]
    consumed.sort(key=lambda item: item[1], reverse=True)
    covered, total = covered_days(start_year, end_year, series.last_recorded_date)
    return BudgetReport(
        category=category,
        start_year=start_year,
        end_year=end_year,
        factor=factor,
        expected_total=expected,
        consumed=consumed,
        total_consumed=float(sum(amount for _, amount in consumed)),
        total_days=total,
        covered_days=covered,
        last_recorded_date=series.last_recorded_date,
    )
