import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.analysis import (
    MONTHLY_AVERAGE,
    TOTAL,
    detail_transactions,
    filter_transactions,
    month_key,
    month_range,
    monthly_deviations,
    ordered_month_range,
    summary_deviations,
    summary_table,
    tagger_overview,
)
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Tagger

from ..helpers import tagged


def _sample():
    return tagged(
        ("2024-01-05", "REWE", "Einkauf", -50.0),
        ("2024-01-20", "Shell", "Tanken", -60.0),
        ("2024-03-02", "REWE", "Einkauf", -30.0),
        ("2024-03-03", "ShareNow", "Fahrt", -10.0),
        ("2024-03-31", "ACME", "Gehalt", 2000.0),
        ("2024-03-31", "Ich", "Sparen", -200.0),
        ("2024-04-01", "Kiosk", "Zeitung", -2.0),
        tags=["household.food", "car.fuel", "household.food.bio", "carsharing", "income", "spar", ""],
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
    assert "spar" not in set(filter_transactions(df, transfer_accounts=["spar"])[Col.tag])
    assert set(filter_transactions(df, excluded_tags=["income", ""])[Col.tag]) == {
        "household.food",
        "car.fuel",
        "household.food.bio",
        "carsharing",
        "spar",
    }
    assert set(filter_transactions(df, tag_filter="car")[Col.tag]) == {"car.fuel", "carsharing"}


def test_summary_table_base_level():
    table = summary_table(_sample(), "2024-01", "2024-04", transfer_accounts=["spar"]).set_index(Col.tag)
    assert list(table.columns) == ["2024-01", "2024-02", "2024-03", "2024-04", TOTAL, MONTHLY_AVERAGE]
    assert table.loc["household", "2024-01"] == -50.0
    assert table.loc["household", "2024-02"] == 0.0
    assert table.loc["household", TOTAL] == -80.0
    assert table.loc["household", MONTHLY_AVERAGE] == -20.0
    assert "spar" not in table.index
    assert table.index[-1] == TOTAL
    assert table.loc[TOTAL, TOTAL] == pytest.approx(2000 - 50 - 60 - 30 - 10 - 2)
    # sorted by total, largest expense first
    assert list(table.index[:2]) == ["household", "car"]


def test_summary_table_level_and_filter():
    table = summary_table(_sample(), "2024-01", "2024-04", tag_level=1, tag_filter="household").set_index(Col.tag)
    assert list(table.index) == ["household.food", TOTAL]
    assert table.loc["household.food", TOTAL] == -80.0


def test_summary_table_only_requested_months():
    table = summary_table(_sample(), "2024-03", "2024-03").set_index(Col.tag)
    assert list(table.columns) == ["2024-03", TOTAL, MONTHLY_AVERAGE]
    assert "car" not in table.index  # car.fuel only happened in January


def test_summary_table_empty():
    assert summary_table(_sample(), "2020-01", "2020-12") is None
    assert summary_table(_sample().iloc[0:0], "2024-01", "2024-02") is None


def test_detail_transactions_for_tag_and_month():
    df = _sample()
    detail = detail_transactions(df, "2024-03", "household")
    assert list(detail[Col.tag]) == ["household.food.bio"]
    assert detail_transactions(df, "2024-01", "car")[Col.tag].tolist() == ["car.fuel"]
    assert detail_transactions(df, "2024-03", "car").empty  # carsharing is not car
    assert detail_transactions(df, "2024-04", "")[Col.recipient].tolist() == ["Kiosk"]


def test_detail_transactions_total_row_uses_same_filters():
    detail = detail_transactions(_sample(), "2024-03", None, transfer_accounts=["spar"])
    assert list(detail[Col.recipient]) == ["REWE", "ShareNow", "ACME"]


def _monthly(values, tag="food"):
    months = month_range("2023-01", pd.Period("2023-01", "M") + len(values) - 1)
    return pd.DataFrame([values], index=[tag], columns=months)


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


def test_summary_deviations_uses_history_before_the_range():
    rows = [(f"2023-{m:02d}-15", "REWE", "x", -100.0) for m in range(1, 13)] + [("2024-01-15", "REWE", "x", -500.0)]
    df = tagged(*rows, tags=["food"] * len(rows))
    deviation, baseline = summary_deviations(df, "2024-01", "2024-02")
    assert list(deviation.columns) == ["2024-01", "2024-02"]
    assert deviation.loc["food", "2024-01"] == pytest.approx(-400.0)
    assert baseline.loc["food", "2024-01"] == -100.0


def test_summary_deviations_empty():
    deviation, baseline = summary_deviations(_sample(), "2024-01", "2024-02", tag_filter="nothing")
    assert deviation.empty
    assert list(baseline.columns) == ["2024-01", "2024-02"]


def test_tagger_overview_counts_unused_taggers():
    df = _sample()
    df[Col.tagger_name] = ["groceries", "", "groceries", "", "", "", ""]
    overview = tagger_overview(df, [Tagger("groceries", tag="food", recurring=2), Tagger("unused", tag="x")])
    assert overview.to_dict("records") == [
        {"name": "groceries", "tag": "food", "recurring": 2.0, "count": 2, "sum": -80.0},
        {"name": "unused", "tag": "x", "recurring": pytest.approx(np.nan, nan_ok=True), "count": 0, "sum": 0.0},
    ]
