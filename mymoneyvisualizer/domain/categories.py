"""Helpers for hierarchical categories such as ``household.food.grocery``."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from mymoneyvisualizer.domain.columns import UNCATEGORIZED

SEPARATOR = "."
UNCATEGORIZED_LABEL = "(ohne Kategorie)"


def main_category(category: str) -> str:
    return str(category).split(SEPARATOR, 1)[0]


def category_at_level(categories: pd.Series, level: int) -> pd.Series:
    """Cut categories to ``level + 1`` parts; level 0 is the main category."""
    if level < 0:
        raise ValueError("level must be >= 0")
    parts = categories.astype(str).str.split(SEPARATOR, n=level + 1)
    return parts.str[: level + 1].str.join(SEPARATOR)


def matches_category(categories: pd.Series, category: str) -> pd.Series:
    """True for ``category`` itself and all of its subcategories, but not for categories that merely share a prefix.

    ``car`` matches ``car`` and ``car.fuel`` but not ``carsharing``.
    """
    categories = categories.astype(str)
    if category == UNCATEGORIZED:
        return categories == UNCATEGORIZED
    return (categories == category) | categories.str.startswith(category + SEPARATOR)


def unique_categories(categories: Iterable[str]) -> list[str]:
    return sorted({str(t) for t in categories})


def unique_main_categories(categories: Iterable[str]) -> list[str]:
    return sorted({main_category(t) for t in categories})


def display_category(category: str) -> str:
    return UNCATEGORIZED_LABEL if category == UNCATEGORIZED else category
