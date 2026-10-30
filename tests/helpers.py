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


def categorized(*rows, categories, account="giro", spread_months=None, residual_percent=None, sale_of=None):
    """Transactions with explicit categories and spreads (one per row), as produced by :func:`apply_rules`."""
    df = apply_rules(transactions(*rows, account=account), [])
    df[Col.category] = list(categories)
    for column, values in (
        (Col.spread_months, spread_months),
        (Col.residual_percent, residual_percent),
        (Col.sale_of, sale_of),
    ):
        if values is not None:
            df[column] = list(values)
    return df
