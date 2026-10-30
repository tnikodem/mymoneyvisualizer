import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.analysis import (
    MONTHLY_AVERAGE,
    SUMMARY,
    TOTAL,
    detail_transactions,
    filter_transactions,
    income_expenses_deviations,
    income_expenses_table,
    month_key,
    month_range,
    monthly_deviations,
    ordered_month_range,
    rule_overview,
)
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Rule

from ..helpers import categorized


def _sample():
    return categorized(
        ("2024-01-05", "REWE", "Einkauf", -50.0),
        ("2024-01-20", "Shell", "Tanken", -60.0),
        ("2024-03-02", "REWE", "Einkauf", -30.0),
        ("2024-03-03", "ShareNow", "Fahrt", -10.0),
        ("2024-03-31", "ACME", "Gehalt", 2000.0),
        ("2024-03-31", "Ich", "Sparen", -200.0),
        ("2024-04-01", "Kiosk", "Zeitung", -2.0),
        categories=["household.food", "car.fuel", "household.food.bio", "carsharing", "income", "spar", ""],
    )


def test_month_helpers():
    assert month_key(pd.Timestamp("2024-03-31")) == "2024-03"
    assert month_range("2023-11", "2024-02") == ["2023-11", "2023-12", "2024-01", "2024-02"]
    assert month_range("2024-02", "2024-01") == []


@pytest.mark.parametrize(
    ("start", "end", "changed", "expected"),
    [
        ("2024-01", "2024-05", "start", ("2024-01", "2024-05")),
        ("2024-05", "2024-01", "start", ("2024-05", "2024-05")),
        ("2024-05", "2024-01", "end", ("2024-01", "2024-01")),
        ("2024-05", "2024-05", "end", ("2024-05", "2024-05")),
    ],
)
def test_ordered_month_range(start, end, changed, expected):
    """Regression: moving the start month behind the end month produced an empty range."""
    assert ordered_month_range(start, end, changed) == expected


def test_filter_transactions():
    df = _sample()
    assert len(filter_transactions(df)) == len(df)
    assert "spar" not in set(filter_transactions(df, own_accounts=["spar"])[Col.category])
    assert set(filter_transactions(df, excluded_categories=["income", ""])[Col.category]) == {
        "household.food",
        "car.fuel",
        "household.food.bio",
        "carsharing",
        "spar",
    }
    assert set(filter_transactions(df, category_filter="car")[Col.category]) == {"car.fuel", "carsharing"}


GROUPS = {"income": "income", "household": "needs", "car": "needs", "carsharing": "wants", "": "needs"}


def _categories(table):
    return table.loc[table[SUMMARY] == ""].set_index(Col.category)


def _summaries(table):
    return table.loc[table[SUMMARY] != ""].set_index(SUMMARY)


def test_income_expenses_table_base_level():
    table = income_expenses_table(_sample(), "2024-01", "2024-04", own_accounts=["spar"], groups=GROUPS)
    assert list(table.columns) == [
        Col.category,
        "2024-01",
        "2024-02",
        "2024-03",
        "2024-04",
        TOTAL,
        MONTHLY_AVERAGE,
        SUMMARY,
    ]
    categories = _categories(table)
    assert categories.loc["household", "2024-01"] == -50.0
    assert categories.loc["household", "2024-02"] == 0.0
    assert categories.loc["household", TOTAL] == -80.0
    assert categories.loc["household", MONTHLY_AVERAGE] == -20.0
    assert "spar" not in categories.index
    # sorted by total, largest expense first
    assert list(categories.index[:2]) == ["household", "car"]


def test_income_expenses_table_summary_rows():
    table = income_expenses_table(_sample(), "2024-01", "2024-04", groups={**GROUPS, "spar": "savings"})
    summaries = _summaries(table)
    assert list(summaries.index) == ["income", "expenses", "savings", "net"]
    assert list(summaries[Col.category]) == ["Einnahmen", "Ausgaben", "Sparen", "Saldo"]
    assert summaries.loc["income", TOTAL] == 2000.0
    assert summaries.loc["expenses", TOTAL] == pytest.approx(-50 - 60 - 30 - 10 - 2)
    assert summaries.loc["savings", "2024-03"] == -200.0
    assert summaries.loc["net", TOTAL] == pytest.approx(2000 - 50 - 60 - 30 - 10 - 2 - 200)
    assert table.index[-1] == len(table) - 1 and table[SUMMARY].iloc[-1] == "net"


def test_income_expenses_table_without_groups_only_has_the_net_row():
    """Categories without a group (e.g. internal transfers when shown) only count in the net row."""
    table = income_expenses_table(_sample(), "2024-01", "2024-04")
    summaries = _summaries(table)
    assert list(summaries.index) == ["income", "expenses", "net"]
    assert summaries.loc["income", TOTAL] == 0.0
    assert summaries.loc["net", TOTAL] == pytest.approx(2000 - 50 - 60 - 30 - 10 - 200 - 2)


def test_income_expenses_table_level_and_filter():
    table = income_expenses_table(_sample(), "2024-01", "2024-04", level=1, category_filter="household", groups=GROUPS)
    assert list(_categories(table).index) == ["household.food"]
    assert _categories(table).loc["household.food", TOTAL] == -80.0
    assert _summaries(table).loc["expenses", TOTAL] == -80.0


def test_income_expenses_table_only_requested_months():
    table = income_expenses_table(_sample(), "2024-03", "2024-03")
    assert list(table.columns) == [Col.category, "2024-03", TOTAL, MONTHLY_AVERAGE, SUMMARY]
    assert "car" not in _categories(table).index  # car.fuel only happened in January


def test_income_expenses_table_empty():
    assert income_expenses_table(_sample(), "2020-01", "2020-12") is None
    assert income_expenses_table(_sample().iloc[0:0], "2024-01", "2024-02") is None


def test_detail_transactions_for_category_and_month():
    df = _sample()
    detail = detail_transactions(df, "2024-03", ["household"])
    assert list(detail[Col.category]) == ["household.food.bio"]
    assert detail_transactions(df, "2024-01", ["car"])[Col.category].tolist() == ["car.fuel"]
    assert detail_transactions(df, "2024-03", ["car"]).empty  # carsharing is not car
    assert detail_transactions(df, "2024-04", [""])[Col.recipient].tolist() == ["Kiosk"]


def test_detail_transactions_of_several_categories_and_all_months():
    df = _sample()
    detail = detail_transactions(df, None, ["car", "carsharing"])
    assert list(detail[Col.recipient]) == ["Shell", "ShareNow"]
    assert detail_transactions(df, None, [""])[Col.recipient].tolist() == ["Kiosk"]


def test_detail_transactions_of_all_categories_use_same_filters():
    detail = detail_transactions(_sample(), "2024-03", None, own_accounts=["spar"])
    assert list(detail[Col.recipient]) == ["REWE", "ShareNow", "ACME"]


def _monthly(values, category="food"):
    months = month_range("2023-01", pd.Period("2023-01", "M") + len(values) - 1)
    return pd.DataFrame([values], index=[category], columns=months)


def test_monthly_deviations_flags_outlier():
    values = [-100.0] * 12 + [-400.0, -110.0]
    deviation, baseline = monthly_deviations(_monthly(values))
    assert deviation.loc["food", "2024-01"] == pytest.approx(-300.0)
    assert np.isnan(deviation.loc["food", "2024-02"])  # within min_abs
    assert baseline.loc["food", "2024-01"] == -100.0


def test_monthly_deviations_needs_history():
    deviation, baseline = monthly_deviations(_monthly([-100.0] * 3 + [-1000.0]))
    assert deviation.isna().all().all()
    assert baseline.isna().all().all()


def test_monthly_deviations_respects_spread():
    noisy = [-100.0, -300.0] * 6 + [-450.0]
    deviation, _ = monthly_deviations(_monthly(noisy))
    assert np.isnan(deviation.iloc[0, -1])  # 3 * scaled MAD of a noisy series is larger than the difference


def test_income_expenses_deviations_uses_history_before_the_range():
    rows = [(f"2023-{m:02d}-15", "REWE", "x", -100.0) for m in range(1, 13)] + [("2024-01-15", "REWE", "x", -500.0)]
    df = categorized(*rows, categories=["food"] * len(rows))
    deviation, baseline = income_expenses_deviations(df, "2024-01", "2024-02")
    assert list(deviation.columns) == ["2024-01", "2024-02"]
    assert deviation.loc["food", "2024-01"] == pytest.approx(-400.0)
    assert baseline.loc["food", "2024-01"] == -100.0


def test_income_expenses_deviations_empty():
    deviation, baseline = income_expenses_deviations(_sample(), "2024-01", "2024-02", category_filter="nothing")
    assert deviation.empty
    assert list(baseline.columns) == ["2024-01", "2024-02"]


def test_rule_overview_says_what_each_rule_does():
    df = _sample()
    groceries = Rule(category="food", regex_recipient=r"REWE|EDEKA\.de", spread_months=12)
    unused = Rule(category="x", regex_recipient="^Shell", regex_description="Tanken")
    df[Col.rule] = [groceries.id, "", groceries.id, "", "", "", ""]
    assert rule_overview(df, [groceries, unused]).to_dict("records") == [
        {
            "id": groceries.id,
            "position": 1,
            "recipient": "REWE | EDEKA.de",
            "description": "",
            "category": "food",
            "spread_months": 12,
            "residual_percent": 0,
            "count": 2,
            "overridden": 0,
            "sum": -80.0,
        },
        {
            "id": unused.id,
            "position": 2,
            "recipient": "^Shell",
            "description": "Tanken",
            "category": "x",
            "spread_months": 0,
            "residual_percent": 0,
            "count": 0,
            "overridden": 1,  # Shell matches, but no rule id says so
            "sum": 0.0,
        },
    ]
