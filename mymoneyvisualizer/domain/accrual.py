"""Accrual basis (Periodisierung): count payments in the months in which they are used.

The income & expenses table shows when money was paid (cash basis). The budget spreads payments that cover a
longer time over that time, as accounting does:

* **Prepaid expenses** (Rechnungsabgrenzung): a payment for a service period, e.g. a yearly insurance, is spread
  evenly over the service period.
* **Depreciation** (Abschreibung): the price of a durable good, e.g. furniture or a car, minus its expected residual
  value is spread evenly over its useful life (straight-line). The residual value is not consumed; it remains part
  of the household's assets.
* **Sale**: a sale linked to its purchase replaces the estimate by the facts. The real loss of value (price minus
  sale proceeds) is spread over the months from the purchase to the sale, and the proceeds are no income.

Only real payments are spread, nothing is projected. Other payments count in the month in which they were paid.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from mymoneyvisualizer.domain.columns import Col

FIRST, LAST, AMOUNT = "first", "last", "amount"


def month_numbers(dates: pd.Series) -> np.ndarray:
    """Months counted from year 0, so that consecutive months differ by one."""
    return (dates.dt.year * 12 + dates.dt.month - 1).to_numpy(dtype=np.int64)


def to_period(month_number: int) -> pd.Period:
    return pd.Period(year=month_number // 12, month=month_number % 12 + 1, freq="M")


def linked_sales(df: pd.DataFrame) -> dict[int, list[int]]:
    """Row positions of the sales per row position of their purchase.

    A link counts if the purchase exists and was not made after the sale; other links are ignored, and those
    sales are ordinary payments.
    """
    links = df[Col.sale_of].to_numpy(dtype=object)
    selling = np.flatnonzero(links != "")
    if not len(selling):
        return {}
    positions: dict[str, int] = {}
    for position, transaction_id in enumerate(df[Col.transaction_id]):
        positions.setdefault(transaction_id, position)
    months = month_numbers(df[Col.date])
    sales: dict[int, list[int]] = {}
    for sale in selling:
        purchase = positions.get(links[sale])
        if purchase is not None and purchase != sale and months[purchase] <= months[sale]:
            sales.setdefault(purchase, []).append(int(sale))
    return sales


def schedule(df: pd.DataFrame) -> pd.DataFrame:
    """How every transaction is counted: its category, the ``first`` and ``last`` month and the ``amount`` per month.

    Months are month numbers (see :func:`month_numbers`). Linked sales are part of the schedule of their purchase
    and have no row of their own. ``df`` needs the columns transaction_id, date, value, category, spread_months,
    residual_percent and sale_of; the index of the result is the one of ``df``.
    """
    first = month_numbers(df[Col.date])
    value = df[Col.value].to_numpy(dtype=float)
    spread = df[Col.spread_months].to_numpy(dtype=np.int64)
    residual = df[Col.residual_percent].to_numpy(dtype=float) / 100

    spread_rows = spread > 0
    total = np.where(spread_rows, value * (1 - residual), value)
    last = np.where(spread_rows, first + spread - 1, first)
    keep = np.ones(len(df), dtype=bool)
    for purchase, sales in linked_sales(df).items():
        total[purchase] = value[purchase] + value[sales].sum()
        last[purchase] = first[sales].max()
        keep[sales] = False

    plan = pd.DataFrame(
        {Col.category: df[Col.category].to_numpy(), FIRST: first, LAST: last, AMOUNT: total / (last - first + 1)},
        index=df.index,
    )
    return plan.loc[keep]


def accrue(df: pd.DataFrame) -> pd.DataFrame:
    """Monthly amounts per category on the accrual basis: months (``PeriodIndex``) as rows, categories as columns.

    The months run from the first payment to the end of the longest spread, without gaps.
    """
    plan = schedule(df)
    if plan.empty:
        return pd.DataFrame(index=pd.PeriodIndex([], freq="M"))
    categories = sorted(plan[Col.category].unique())
    rows = pd.Index(categories).get_indexer(plan[Col.category])
    first, last, amount = plan[FIRST].to_numpy(), plan[LAST].to_numpy(), plan[AMOUNT].to_numpy()
    start, end = int(first.min()), int(last.max())
    # every amount starts in its first month and stops after its last one: one cumulative sum does all the spreading
    steps = np.zeros((len(categories), end - start + 2))
    np.add.at(steps, (rows, first - start), amount)
    np.add.at(steps, (rows, last - start + 1), -amount)
    values = np.round(np.cumsum(steps, axis=1)[:, :-1], 9)
    index = pd.period_range(to_period(start), to_period(end), freq="M")
    return pd.DataFrame(values.T, index=index, columns=categories)
