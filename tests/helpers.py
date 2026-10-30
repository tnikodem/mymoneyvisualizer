"""Small builders shared by the tests."""

import pandas as pd

from mymoneyvisualizer.domain.categorization import apply_rules
from mymoneyvisualizer.domain.columns import Col, normalize_transactions


def transactions(*rows, account=None):
    """Build a normalized transaction table from ``(date, recipient, description, value)`` tuples."""
    df = pd.DataFrame(rows, columns=[Col.date, Col.recipient, Col.description, Col.value])
    df = normalize_transactions(df)
    if account is not None:
        df[Col.account] = account
    return df


def categorized(*rows, categories, account="giro", recurring=None):
    """Transactions with explicit categories (one per row), as produced by :func:`apply_rules`."""
    df = apply_rules(transactions(*rows, account=account), [])
    df[Col.category] = list(categories)
    if recurring is not None:
        df[Col.recurring] = [float("nan") if r is None else float(r) for r in recurring]
    return df
