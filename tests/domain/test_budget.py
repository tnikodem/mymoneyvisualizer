import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.budget import (
    SAVED,
    BudgetSeries,
    budget_report,
    budget_series,
    group_totals,
    smooth,
    stacked_curves,
)
from mymoneyvisualizer.domain.models import GroupAssignment

from ..helpers import categorized

SHARES = {"needs": 0.5, "wants": 0.3}
GROUPS = [
    GroupAssignment("income", "income"),
    GroupAssignment("household", "needs"),
    GroupAssignment("car", "needs"),
    GroupAssignment("hobby", "wants"),
    GroupAssignment("depot", "savings"),
    GroupAssignment("unused", "needs"),
]


def test_budget_series_uses_main_categories_and_drops_transfers_and_excluded():
    df = categorized(
        ("2024-01-01", "ACME", "Gehalt", 1200.0),
        ("2024-01-02", "REWE", "x", -120.0),
        ("2024-01-03", "Ich", "Sparen", -500.0),
        ("2024-01-04", "Kiosk", "x", -12.0),
        categories=["income.salary", "household.food", "spar", "misc"],
    )
    series = budget_series(df, own_accounts=["spar"], excluded_categories=["misc"])
    assert list(series.monthly.columns) == ["household", "income"]
    assert series.last_date == pd.Timestamp("2024-01-02")  # of the transactions in the budget


def test_budget_series_ends_with_the_last_transaction():
    """Spread payments reach into the future; that part is not used yet."""
    df = categorized(
        ("2024-01-10", "Möbelhaus", "Sofa", -2400.0),
        ("2024-05-17", "REWE", "x", -10.0),
        categories=["home", "food"],
        spread_months=[120, 0],
    )
    series = budget_series(df)
    assert series.monthly.index[-1] == pd.Period("2024-05", "M")
    assert series.monthly["home"].tolist() == pytest.approx([-20.0] * 5)


def test_budget_series_empty():
    series = budget_series(categorized(("2024-01-01", "a", "b", -1.0), categories=["x"]), excluded_categories=["x"])
    assert series.monthly.empty
    assert series.last_date is None
    assert budget_report(series, [], 2024, 2024, SHARES) is None


def _series(last_date="2024-12-31"):
    index = pd.period_range("2024-01", "2024-12", freq="M")
    monthly = pd.DataFrame(
        {"income": 3000.0, "household": -1200.0, "car": -300.0, "hobby": -600.0, "depot": -400.0, "": -30.0},
        index=index,
    )
    return BudgetSeries(monthly, pd.Timestamp(last_date))


def test_group_totals():
    totals = group_totals(_series().monthly, GROUPS)
    month = totals.iloc[0]
    assert month["income"] == 3000.0
    assert month["needs"] == pytest.approx(1200.0 + 300.0 + 30.0)  # without a group: needs
    assert month["wants"] == 600.0
    assert month["savings"] == 400.0
    assert month[SAVED] == pytest.approx(3000.0 - 1530.0 - 600.0)


def test_budget_report():
    report = budget_report(_series(), GROUPS, 2024, 2024, SHARES)
    assert report.months == report.period_months == 12
    assert report.is_complete
    assert report.income == pytest.approx(36000.0)
    assert report.needs.amount == pytest.approx(12 * 1530.0)
    assert report.needs.categories == [("household", 14400.0), ("car", 3600.0), ("", 360.0)]
    assert report.wants.amount == pytest.approx(7200.0)
    assert report.savings.categories == [("depot", 4800.0)]
    assert report.savings.target == pytest.approx(0.2)
    assert report.saved == pytest.approx(36000.0 - 18360.0 - 7200.0)
    assert report.savings_rate == pytest.approx(10440.0 / 36000.0)
    assert report.share(report.needs.amount) == pytest.approx(0.51)
    # 29 % saved instead of 20 %: 9 % of 3,000 € could be spent per month
    assert report.room_per_month == pytest.approx(0.09 * 3000.0)


def test_too_little_saved_gives_negative_room():
    series = _series()
    series.monthly["hobby"] = -1470.0
    report = budget_report(series, GROUPS, 2024, 2024, SHARES)
    assert report.savings_rate == pytest.approx(0.0)
    assert report.room_per_month == pytest.approx(-0.2 * 3000.0)


def test_budget_report_counts_only_the_months_of_the_period_with_data():
    series = _series()
    series.monthly.index = pd.period_range("2023-07", "2024-06", freq="M")
    report = budget_report(series, GROUPS, 2024, 2025, SHARES)
    assert (report.months, report.period_months) == (6, 24)
    assert not report.is_complete
    assert report.income == pytest.approx(18000.0)
    assert report.per_month(report.income) == pytest.approx(3000.0)


def test_budget_report_without_income():
    series = _series()
    series.monthly["income"] = 0.0
    report = budget_report(series, GROUPS, 2024, 2024, SHARES)
    assert report.savings_rate is None
    assert report.room_per_month is None


def test_budget_report_outside_the_data():
    report = budget_report(_series(), GROUPS, 2030, 2030, SHARES)
    assert report.months == 0
    assert report.room_per_month is None
    assert report.per_month(100.0) == 0.0


def test_stacked_curves_in_reverse_group_order():
    monthly = _series().monthly
    curves = stacked_curves(monthly, GROUPS, "needs")
    assert [name for name, _ in curves] == ["car", "household"]
    np.testing.assert_allclose(curves[-1][1], 1500.0)


def test_smooth_is_a_moving_average_of_twelve_months():
    monthly = pd.DataFrame({"x": [12.0] + [0.0] * 13}, index=pd.period_range("2024-01", periods=14, freq="M"))
    smoothed = smooth(monthly)["x"].tolist()
    assert smoothed[:2] == [12.0, 6.0]
    assert smoothed[11] == pytest.approx(1.0)
    assert smoothed[12] == 0.0
