import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.categories import (
    category_at_level,
    display_category,
    main_category,
    matches_category,
    unique_categories,
    unique_main_categories,
)
from mymoneyvisualizer.domain.columns import RAW_COLUMNS, Col, empty_transactions, normalize_transactions


def test_empty_transactions_has_canonical_schema():
    df = empty_transactions()
    assert list(df.columns) == list(RAW_COLUMNS)
    assert len(df) == 0
    assert df[Col.date].dtype == "datetime64[ns]"
    assert df[Col.value].dtype == float


def test_normalize_fills_missing_values_and_ids():
    df = pd.DataFrame(
        {
            Col.transaction_id: ["a", None, ""],
            Col.date: ["2024-01-02", "2024-01-03 00:00:00", "2024-01-04"],
            Col.recipient: ["x", np.nan, None],
            Col.value: ["1.5", 2, "bad"],
            "category": ["derived", "", ""],
        }
    )
    out = normalize_transactions(df)
    assert list(out.columns) == list(RAW_COLUMNS)
    assert out[Col.transaction_id].iloc[0] == "a"
    assert out[Col.transaction_id].iloc[1] != out[Col.transaction_id].iloc[2]
    assert all(len(i) == 36 for i in out[Col.transaction_id].iloc[1:])
    assert list(out[Col.recipient]) == ["x", "", ""]
    assert list(out[Col.description]) == ["", "", ""]
    assert out[Col.value].iloc[0] == 1.5
    assert np.isnan(out[Col.value].iloc[2])
    assert out[Col.date].iloc[1] == pd.Timestamp("2024-01-03")


def test_normalize_does_not_modify_input():
    df = pd.DataFrame({Col.date: ["2024-01-02"], Col.value: [1.0]})
    normalize_transactions(df)
    assert list(df.columns) == [Col.date, Col.value]


def test_main_category_and_levels():
    categories = pd.Series(["household.food.bio", "car", "", "a.b"])
    assert main_category("household.food.bio") == "household"
    assert list(category_at_level(categories, 0)) == ["household", "car", "", "a"]
    assert list(category_at_level(categories, 1)) == ["household.food", "car", "", "a.b"]
    assert list(category_at_level(categories, 5)) == list(categories)
    with pytest.raises(ValueError):
        category_at_level(categories, -1)


def test_matches_category_respects_hierarchy():
    """Regression: the detail view for ``car`` used ``startswith`` and also showed ``carsharing``."""
    categories = pd.Series(["car", "car.fuel", "carsharing", "household", ""])
    assert list(matches_category(categories, "car")) == [True, True, False, False, False]
    assert list(matches_category(categories, "car.fuel")) == [False, True, False, False, False]
    assert list(matches_category(categories, "")) == [False, False, False, False, True]


def test_unique_categories_and_display():
    categories = ["b.x", "a", "b.y", "a"]
    assert unique_categories(categories) == ["a", "b.x", "b.y"]
    assert unique_main_categories(categories) == ["a", "b"]
    assert display_category("") == "(ohne Kategorie)"
    assert display_category("food") == "food"
