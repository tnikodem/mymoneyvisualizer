"""Aggregations for the summary table, the detail view and the tagger overview."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from typing import Literal

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Tagger
from mymoneyvisualizer.domain.tags import matches_tag, tag_at_level

TOTAL = "total"
MONTHLY_AVERAGE = "monthly average"

MonthLike = str | pd.Period | pd.Timestamp


def to_month(value: MonthLike) -> pd.Period:
    return pd.Period(value, freq="M")


def month_key(value: MonthLike) -> str:
    return to_month(value).strftime("%Y-%m")


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
    excluded_tags: Collection[str] = (),
    transfer_accounts: Collection[str] = (),
    tag_filter: str = "",
) -> pd.DataFrame:
    """Drop excluded tags and transfers between own accounts (tagged with an account name).

    ``tag_filter`` is a free text prefix filter, so ``car`` keeps ``carsharing`` as well.
    """
    mask = pd.Series(True, index=df.index)
    if transfer_accounts:
        mask &= ~df[Col.tag].isin(list(transfer_accounts))
    if excluded_tags:
        mask &= ~df[Col.tag].isin(list(excluded_tags))
    if tag_filter:
        mask &= df[Col.tag].astype(str).str.startswith(tag_filter)
    return df.loc[mask]


def in_months(df: pd.DataFrame, start: MonthLike, end: MonthLike) -> pd.DataFrame:
    months = df[Col.date].dt.to_period("M")
    return df.loc[(months >= to_month(start)) & (months <= to_month(end))]


def _pivot(df: pd.DataFrame, tag_level: int, months: list[str]) -> pd.DataFrame:
    tags = tag_at_level(df[Col.tag], tag_level).rename(Col.tag)
    keys = df[Col.date].dt.strftime("%Y-%m").rename(Col.date)
    pivot = df[Col.value].groupby([tags, keys]).sum().unstack(fill_value=0.0)
    return pivot.reindex(columns=months, fill_value=0.0).astype(float).rename_axis(columns=None)


def summary_table(
    df: pd.DataFrame,
    start: MonthLike,
    end: MonthLike,
    *,
    tag_level: int = 0,
    tag_filter: str = "",
    excluded_tags: Collection[str] = (),
    transfer_accounts: Collection[str] = (),
) -> pd.DataFrame | None:
    """Monthly sums per tag plus ``total`` and ``monthly average`` columns and a final ``total`` row.

    Rows are sorted by total (largest expense first). Returns ``None`` if there is nothing to show.
    """
    data = filter_transactions(
        df, excluded_tags=excluded_tags, transfer_accounts=transfer_accounts, tag_filter=tag_filter
    )
    data = in_months(data, start, end)
    if data.empty:
        return None
    months = month_range(start, end)
    table = _pivot(data, tag_level, months)
    table[TOTAL] = table[months].sum(axis=1)
    table[MONTHLY_AVERAGE] = table[TOTAL] / len(months)
    table = table.sort_values(TOTAL, kind="stable").reset_index()

    total_row = table.drop(columns=Col.tag).sum().to_frame().T
    total_row.insert(0, Col.tag, TOTAL)
    return pd.concat([table, total_row], ignore_index=True)


def summary_deviations(
    df: pd.DataFrame,
    start: MonthLike,
    end: MonthLike,
    *,
    tag_level: int = 0,
    tag_filter: str = "",
    excluded_tags: Collection[str] = (),
    transfer_accounts: Collection[str] = (),
    window: int = 12,
    min_periods: int = 6,
    threshold: float = 3.0,
    min_abs: float = 50.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Unusual months of the summary table, judged against the complete history of each tag.

    Returns ``(deviation, baseline)`` indexed by tag with ``YYYY-MM`` columns for ``start..end``.
    ``deviation`` is ``value - baseline`` for flagged cells and NaN otherwise.
    """
    data = filter_transactions(
        df, excluded_tags=excluded_tags, transfer_accounts=transfer_accounts, tag_filter=tag_filter
    )
    months = month_range(start, end)
    if data.empty:
        empty = pd.DataFrame(columns=months, dtype=float)
        return empty, empty.copy()
    history = month_range(
        min(to_month(data[Col.date].min()), to_month(start)), max(to_month(data[Col.date].max()), to_month(end))
    )
    monthly = _pivot(data, tag_level, history)
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
    standard deviations (scaled median absolute deviation). ``monthly`` has tags as rows and
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
    month: MonthLike,
    tag: str | None = None,
    *,
    excluded_tags: Collection[str] = (),
    transfer_accounts: Collection[str] = (),
    tag_filter: str = "",
) -> pd.DataFrame:
    """Transactions behind one cell of the summary table. ``tag=None`` means the total row."""
    data = filter_transactions(
        df, excluded_tags=excluded_tags, transfer_accounts=transfer_accounts, tag_filter=tag_filter
    )
    data = in_months(data, month, month)
    if tag is not None:
        data = data.loc[matches_tag(data[Col.tag], tag)]
    return data.sort_values(Col.date, kind="stable").reset_index(drop=True)


def tagger_overview(tagged: pd.DataFrame, taggers: Iterable[Tagger]) -> pd.DataFrame:
    """Number of transactions and their sum per tagger."""
    groups = tagged.groupby(Col.tagger_name)[Col.value].agg(["count", "sum"])
    rows = []
    for tagger in taggers:
        count, total = groups.loc[tagger.name] if tagger.name in groups.index else (0, 0.0)
        rows.append(
            {
                "name": tagger.name,
                "tag": tagger.tag,
                "recurring": np.nan if tagger.recurring is None else float(tagger.recurring),
                "count": int(count),
                "sum": round(float(total), 2),
            }
        )
    return pd.DataFrame(rows, columns=["name", "tag", "recurring", "count", "sum"])
