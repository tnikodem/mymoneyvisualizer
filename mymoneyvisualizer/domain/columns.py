"""Column names and the canonical schema of the transaction table."""

from __future__ import annotations

import uuid

import numpy as np
import pandas as pd


class Col:
    transaction_id = "transaction_id"
    account = "account"
    date = "date"
    recipient = "recipient"
    description = "description"
    value = "value"
    category = "category"
    rule = "rule"
    spread_months = "spread_months"
    residual_percent = "residual_percent"
    sale_of = "sale_of"


#: Columns that are imported from the bank and persisted. Categories are always derived.
RAW_COLUMNS = (Col.transaction_id, Col.date, Col.recipient, Col.description, Col.value)
#: Columns derived from the rules and the manual categories.
CATEGORY_COLUMNS = (Col.category, Col.rule, Col.spread_months, Col.residual_percent, Col.sale_of)

#: Category of a transaction that no rule matched.
UNCATEGORIZED = ""
#: Rule name shown for transactions that were categorized individually.
MANUAL_RULE = "(manual)"


def new_transaction_ids(n: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(n)]


def empty_transactions() -> pd.DataFrame:
    return normalize_transactions(pd.DataFrame({col: [] for col in RAW_COLUMNS}))


def normalize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` with exactly :data:`RAW_COLUMNS` and canonical dtypes.

    Missing or empty transaction ids are generated, missing texts become empty strings.
    """
    src = df.reset_index(drop=True)
    n = len(src)
    out = pd.DataFrame(index=pd.RangeIndex(n))

    ids = src[Col.transaction_id] if Col.transaction_id in src else pd.Series([None] * n, dtype=object)
    ids = ids.astype(object).where(ids.notna() & (ids.astype(str).str.len() > 0), None)
    missing = ids.isna()
    if missing.any():
        ids[missing] = new_transaction_ids(int(missing.sum()))
    out[Col.transaction_id] = ids.astype(str)

    dates = src[Col.date] if Col.date in src else pd.Series([pd.NaT] * n)
    out[Col.date] = pd.to_datetime(dates, format="ISO8601", errors="coerce").astype("datetime64[ns]")

    for col in (Col.recipient, Col.description):
        values = src[col] if col in src else pd.Series([""] * n)
        out[col] = values.astype(object).where(values.notna(), "").astype(str)

    values = src[Col.value] if Col.value in src else pd.Series([np.nan] * n)
    out[Col.value] = pd.to_numeric(values, errors="coerce").astype(float)

    return out[list(RAW_COLUMNS)]
