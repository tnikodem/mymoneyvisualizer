"""Aggregations for the income & expenses table, the transaction list and the rule overview."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping, Sequence
from typing import Literal

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.categories import category_at_level, matches_category
from mymoneyvisualizer.domain.categorization import readable_pattern
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import CONSUMPTION_GROUPS, GROUP_INCOME, GROUP_SAVINGS, Rule

TOTAL = "total"
MONTHLY_AVERAGE = "monthly average"

#: Column of the income & expenses table that marks the summary rows below the categories ("" for categories).
SUMMARY = "summary"
INCOME, EXPENSES, SAVINGS, NET = "income", "expenses", "savings", "net"
SUMMARY_LABELS = {INCOME: "Einnahmen", EXPENSES: "Ausgaben", SAVINGS: "Sparen", NET: "Saldo"}

MonthLike = str | pd.Period | pd.Timestamp


def to_month(value: MonthLike) -> pd.Period:
    return pd.Period(value, freq="M")


def month_key(value: MonthLike) -> str:
    return to_month(value).strftime("%Y-%m")


def last_complete_month(last_date: MonthLike, today: MonthLike | None = None) -> pd.Period:
    """The month of the last transaction, but at most the previous month: the current month is not over yet."""
    current = to_month(today if today is not None else pd.Timestamp.today())
    return min(to_month(last_date), current - 1)


def month_range(start: MonthLike, end: MonthLike) -> list[str]:
    """All months from ``start`` to ``end`` (inclusive) as ``YYYY-MM``."""
    return [p.strftime("%Y-%m") for p in pd.period_range(to_month(start), to_month(end), freq="M")]


def ordered_month_range(start: MonthLike, end: MonthLike, changed: Literal["start", "end"]) -> tuple[str, str]:
    """Keep ``start <= end`` by moving the bound the user did not change."""
    first, last = to_month(start), to_month(end)
    if first > last:
        if changed == "start":
            last = first
        else:
            first = last
    return month_key(first), month_key(last)


def filter_transactions(
    df: pd.DataFrame,
    *,
    excluded_categories: Collection[str] = (),
    own_accounts: Collection[str] = (),
    category_filter: str = "",
) -> pd.DataFrame:
    """Drop excluded categories and internal transfers (categorized with the name of an own account).

    ``category_filter`` is a free text prefix filter, so ``car`` keeps ``carsharing`` as well.
    """
    mask = pd.Series(True, index=df.index)
    if own_accounts:
        mask &= ~df[Col.category].isin(list(own_accounts))
    if excluded_categories:
        mask &= ~df[Col.category].isin(list(excluded_categories))
    if category_filter:
        mask &= df[Col.category].astype(str).str.startswith(category_filter)
    return df.loc[mask]


def summary_groups(kind: str) -> tuple[str, ...] | None:
    """Budget groups added up in a summary row; ``None`` for the net row, which adds up everything."""
    return {INCOME: (GROUP_INCOME,), EXPENSES: CONSUMPTION_GROUPS, SAVINGS: (GROUP_SAVINGS,)}.get(kind)


def in_months(df: pd.DataFrame, start: MonthLike, end: MonthLike) -> pd.DataFrame:
    months = df[Col.date].dt.to_period("M")
    return df.loc[(months >= to_month(start)) & (months <= to_month(end))]


def _pivot(df: pd.DataFrame, level: int, months: list[str]) -> pd.DataFrame:
    categories = category_at_level(df[Col.category], level).rename(Col.category)
    keys = df[Col.date].dt.strftime("%Y-%m").rename(Col.date)
    pivot = df[Col.value].groupby([categories, keys]).sum().unstack(fill_value=0.0)
    return pivot.reindex(columns=months, fill_value=0.0).astype(float).rename_axis(columns=None)


def income_expenses_table(
    df: pd.DataFrame,
    start: MonthLike,
    end: MonthLike,
    *,
    level: int = 0,
    category_filter: str = "",
    excluded_categories: Collection[str] = (),
    own_accounts: Collection[str] = (),
    groups: Mapping[str, str] | None = None,
) -> pd.DataFrame | None:
    """Monthly sums per category plus ``total`` and ``monthly average`` columns, as paid (cash basis).

    Categories are sorted by total (largest expense first). Below them follow summary rows, marked in the column
    :data:`SUMMARY`: income, expenses (needs and wants), savings (only if there are savings categories) and the net
    change of the accounts. ``groups`` maps main categories to their budget group; categories without a group, e.g.
    internal transfers, only count in the net row. Returns ``None`` if there is nothing to show.
    """
    data = filter_transactions(
        df, excluded_categories=excluded_categories, own_accounts=own_accounts, category_filter=category_filter
    )
    data = in_months(data, start, end)
    if data.empty:
        return None
    months = month_range(start, end)
    table = _pivot(data, level, months)
    table[TOTAL] = table[months].sum(axis=1)
    table[MONTHLY_AVERAGE] = table[TOTAL] / len(months)
    table = table.sort_values(TOTAL, kind="stable").reset_index()
    table[SUMMARY] = ""

    values = [*months, TOTAL, MONTHLY_AVERAGE]
    group = category_at_level(table[Col.category], 0).map(groups or {})
    rows = []
    for kind in (INCOME, EXPENSES, SAVINGS, NET):
        members = summary_groups(kind)
        selected = pd.Series(True, index=table.index) if members is None else group.isin(members)
        if kind == SAVINGS and not selected.any():
            continue
        row = table.loc[selected, values].sum()
        rows.append({Col.category: SUMMARY_LABELS[kind], **row.to_dict(), SUMMARY: kind})
    return pd.concat([table, pd.DataFrame(rows)], ignore_index=True)


def income_expenses_deviations(
    df: pd.DataFrame,
    start: MonthLike,
    end: MonthLike,
    *,
    level: int = 0,
    category_filter: str = "",
    excluded_categories: Collection[str] = (),
    own_accounts: Collection[str] = (),
    window: int = 12,
    min_periods: int = 6,
    threshold: float = 3.0,
    min_abs: float = 50.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unusual months of the income & expenses table, judged against the complete history of each category.

    Returns ``(deviation, baseline)`` indexed by category with ``YYYY-MM`` columns for ``start..end``.
    ``deviation`` is ``value - baseline`` for flagged cells and NaN otherwise.
    """
    data = filter_transactions(
        df, excluded_categories=excluded_categories, own_accounts=own_accounts, category_filter=category_filter
    )
    months = month_range(start, end)
    if data.empty:
        empty = pd.DataFrame(columns=months, dtype=float)
        return empty, empty.copy()
    history = month_range(
        min(to_month(data[Col.date].min()), to_month(start)), max(to_month(data[Col.date].max()), to_month(end))
    )
    monthly = _pivot(data, level, history)
    deviation, baseline = monthly_deviations(
        monthly, window=window, min_periods=min_periods, threshold=threshold, min_abs=min_abs
    )
    return deviation[months], baseline[months]


def _mad(window: np.ndarray) -> float:
    return float(np.nanmedian(np.abs(window - np.nanmedian(window))))


def monthly_deviations(
    monthly: pd.DataFrame,
    *,
    window: int = 12,
    min_periods: int = 6,
    threshold: float = 3.0,
    min_abs: float = 50.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Flag months that differ from the median of the preceding ``window`` months.

    A month is flagged if it differs by more than ``min_abs`` and more than ``threshold`` robust
    standard deviations (scaled median absolute deviation). ``monthly`` has categories as rows and
    consecutive months as columns.
    """
    by_month = monthly.T.astype(float)
    previous = by_month.shift(1).rolling(window, min_periods=min_periods)
    baseline = previous.median()
    scale = 1.4826 * previous.apply(_mad, raw=True)
    diff = by_month - baseline
    limit = np.maximum(min_abs, threshold * scale)
    flagged = (diff.abs() > limit) & baseline.notna()
    return diff.where(flagged).T, baseline.T


def detail_transactions(
    df: pd.DataFrame,
    month: MonthLike | None,
    categories: Sequence[str] | None = None,
    *,
    excluded_categories: Collection[str] = (),
    own_accounts: Collection[str] = (),
    category_filter: str = "",
    end: MonthLike | None = None,
) -> pd.DataFrame:
    """Transactions of ``categories`` (with their subcategories) in ``month`` (to ``end``), oldest first.

    ``categories=None`` means all categories, ``month=None`` all months.
    """
    data = filter_transactions(
        df, excluded_categories=excluded_categories, own_accounts=own_accounts, category_filter=category_filter
    )
    if month is not None:
        data = in_months(data, month, month if end is None else end)
    if categories is not None:
        mask = pd.Series(False, index=data.index)
        for category in categories:
            mask |= matches_category(data[Col.category], category)
        data = data.loc[mask]
    return data.sort_values(Col.date, kind="stable").reset_index(drop=True)


def rule_overview(categorized: pd.DataFrame, rules: Iterable[Rule]) -> pd.DataFrame:
    """One row per rule in the order they are applied: what it matches, what it sets and what it categorizes.

    ``position`` counts from 1, ``recipient`` and ``description`` are the regexes for reading, ``count`` and ``sum``
    cover the transactions the rule categorizes (not those a later rule or a manual category takes).
    """
    groups = categorized.groupby(Col.rule)[Col.value].agg(["count", "sum"])
    rows = []
    for position, rule in enumerate(rules, start=1):
        count, total = groups.loc[rule.id] if rule.id in groups.index else (0, 0.0)
        rows.append(
            {
                "id": rule.id,
                "position": position,
                "recipient": readable_pattern(rule.regex_recipient),
                "description": readable_pattern(rule.regex_description),
                Col.category: rule.category,
                Col.spread_months: rule.spread_months,
                Col.residual_percent: rule.residual_percent,
                "count": int(count),
                "sum": round(float(total), 2),
            }
        )
    columns = [
        "id",
        "position",
        "recipient",
        "description",
        Col.category,
        Col.spread_months,
        Col.residual_percent,
        "count",
        "sum",
    ]
    return pd.DataFrame(rows, columns=columns)
