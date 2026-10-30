"""Small builders shared by the tests."""

import pandas as pd

from mymoneyvisualizer.domain.columns import Col, normalize_transactions
from mymoneyvisualizer.domain.tagging import apply_taggers


def transactions(*rows, account=None):
    """Build a normalized transaction table from ``(date, recipient, description, value)`` tuples."""
    df = pd.DataFrame(rows, columns=[Col.date, Col.recipient, Col.description, Col.value])
    df = normalize_transactions(df)
    if account is not None:
        df[Col.account] = account
    return df


def tagged(*rows, tags, account="giro", recurring=None):
    """Transactions with explicit tags (one per row), as produced by :func:`apply_taggers`."""
    df = apply_taggers(transactions(*rows, account=account), [])
    df[Col.tag] = list(tags)
    if recurring is not None:
        df[Col.recurring] = [float("nan") if r is None else float(r) for r in recurring]
    return df
