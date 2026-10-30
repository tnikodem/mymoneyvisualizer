import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.budget import (
    BudgetReport,
    BudgetSeries,
    amortize_recurring,
    budget_report,
    budget_series,
    covered_days,
    income_series,
    stacked_expenses,
)
from mymoneyvisualizer.domain.models import GroupAssignment

from ..helpers import categorized


def _amortize(rows, categories, recurring, horizon="2025-12"):
    return amortize_recurring(categorized(*rows, categories=categories, recurring=recurring), pd.Period(horizon, "M"))


def test_amortize_empty():
    assert amortize_recurring(categorized(categories=[]), pd.Period("2025-12", "M")).empty


def test_current_yearly_event_is_continued_until_horizon():
    monthly = _amortize([("2024-03-10", "Allianz", "KFZ", -1200.0)], ["car"], [1], horizon="2024-12")
    assert [p.strftime("%Y-%m") for p in monthly.index] == [f"2024-{m:02d}" for m in range(3, 13)]
    np.testing.assert_allclose(monthly["car"], -100.0)


def test_historical_event_only_covers_its_own_period():
    rows = [("2022-01-15", "Allianz", "KFZ", -1200.0), ("2024-06-01", "x", "y", -1.0)]
    monthly = _amortize(rows, ["car", "other"], [1, None])
    car = monthly["car"]
    assert car.loc[pd.Period("2022-01", "M")] == pytest.approx(-100.0)
    assert car.loc[pd.Period("2022-12", "M")] == pytest.approx(-100.0)
    assert car.loc[pd.Period("2023-01", "M")] == pytest.approx(0.0)


def test_multi_year_recurrence():
    rows = [("2020-05-20", "Elektro", "Laptop", -3600.0), ("2024-06-01", "x", "y", -1.0)]
    monthly = _amortize(rows, ["tech", "other"], [3, None])
    tech = monthly["tech"]
    assert (tech.round(9) == -100.0).sum() == 36
    assert tech.loc[pd.Period("2023-05", "M")] == pytest.approx(0.0)


def test_recurrence_of_ten_years_or_more_is_never_projected():
    rows = [("2024-01-01", "Haus", "Dach", -12000.0)]
    monthly = _amortize(rows, ["house"], [10], horizon="2040-12")
    assert monthly.index[-1] == pd.Period("2033-12", "M")
    np.testing.assert_allclose(monthly["house"], -100.0)


def test_transactions_after_horizon_are_ignored():
    rows = [("2026-01-01", "x", "y", -10.0), ("2024-01-01", "a", "b", -12.0)]
    monthly = _amortize(rows, ["late", "early"], [None, None], horizon="2025-12")
    assert "late" not in monthly.columns
    assert _amortize([rows[0]], ["late"], [None], horizon="2025-12").empty


def test_budget_series_filters_and_uses_main_categories():
    df = categorized(
        ("2024-01-01", "ACME", "Gehalt", 1200.0),
        ("2024-01-02", "REWE", "x", -120.0),
        ("2024-01-03", "Ich", "Sparen", -500.0),
        ("2024-01-04", "Kiosk", "x", -12.0),
        categories=["income.salary", "household.food", "spar", "misc"],
    )
    series = budget_series(df, budget_end_year=2024, own_accounts=["spar"], excluded_categories=["misc"])
    assert list(series.monthly.columns) == ["household", "income"]
    assert series.monthly.index[-1] == pd.Period("2029-12", "M")


def test_budget_series_last_recorded_date_is_last_transaction():
    """Regression: the projection moved ``last_date`` to the horizon, so every budget period looked complete."""
    df = categorized(("2024-01-01", "a", "b", -1.0), ("2024-05-17", "a", "b", -1.0), categories=["x", "x"])
    series = budget_series(df, budget_end_year=2024)
    assert series.last_recorded_date == pd.Timestamp("2024-05-17")


def test_budget_series_empty():
    series = budget_series(
        categorized(("2024-01-01", "a", "b", -1.0), categories=["x"]), budget_end_year=2024, excluded_categories=["x"]
    )
    assert series.monthly.empty
    assert series.last_recorded_date is None
    assert budget_report(series, [], "needs", 2024, 2024, 0.3) is None


@pytest.mark.parametrize(
    ("start", "end", "last", "expected"),
    [
        (2024, 2024, "2024-01-01", (1, 366)),
        (2024, 2024, "2024-12-31", (366, 366)),
        (2023, 2024, "2023-12-31", (365, 731)),
        (2025, 2026, "2025-06-30", (181, 730)),
        (2027, 2027, "2026-06-30", (0, 365)),
        (2020, 2020, "2024-06-30", (366, 366)),
    ],
)
def test_covered_days(start, end, last, expected):
    """Regression: years after the last transaction were counted as covered (e.g. 2025-2026 → 362 days)."""
    assert covered_days(start, end, pd.Timestamp(last)) == expected


def _series():
    index = pd.period_range("2024-01", "2024-12", freq="M")
    monthly = pd.DataFrame(
        {"income": 1000.0, "household": -200.0, "car": -50.0, "hobby": -30.0, "": -5.0},
        index=index,
    )
    return BudgetSeries(monthly, pd.Timestamp("2024-06-30"))


GROUPS = [
    GroupAssignment("income", "income"),
    GroupAssignment("household", "needs"),
    GroupAssignment("car", "needs"),
    GroupAssignment("hobby", "wants"),
    GroupAssignment("", "needs"),
    GroupAssignment("unknown", "needs"),
]


def test_income_series_and_stacking():
    monthly = _series().monthly
    np.testing.assert_allclose(income_series(monthly, GROUPS), 1000.0)
    curves = stacked_expenses(monthly, GROUPS, "needs")
    assert [name for name, _ in curves] == ["", "car", "household"]
    np.testing.assert_allclose(curves[-1][1], 255.0)


def test_budget_report():
    report = budget_report(_series(), GROUPS, "needs", 2024, 2024, 0.3)
    assert report.expected_total == pytest.approx(3600.0)
    assert report.consumed == [("household", 2400.0), ("car", 600.0), ("", 60.0)]
    assert report.total_consumed == pytest.approx(3060.0)
    assert (report.covered_days, report.total_days) == (182, 366)
    assert not report.is_complete
    assert report.covered_percent == pytest.approx(49.73, abs=0.01)
    assert report.balance == pytest.approx(540.0)
    assert report.remaining_months == pytest.approx(184 / 30)
    assert report.remaining_per_month == pytest.approx(540.0 / (184 / 30))
    assert report.trend == pytest.approx(3600.0 - 3060.0 * 366 / 182)


def test_budget_report_complete_and_empty_coverage():
    complete = BudgetReport("needs", 2024, 2024, 0.3, 100.0, [], 0.0, 366, 366, pd.Timestamp("2024-12-31"))
    assert complete.is_complete
    assert complete.remaining_per_month is None
    nothing = BudgetReport("needs", 2024, 2024, 0.3, 100.0, [], 0.0, 366, 0, pd.Timestamp("2023-12-31"))
    assert nothing.trend is None


def test_budget_report_period_selects_months():
    series = _series()
    series.monthly.index = pd.period_range("2023-07", "2024-06", freq="M")
    report = budget_report(series, GROUPS, "wants", 2024, 2024, 0.5)
    assert report.expected_total == pytest.approx(3000.0)
    assert report.consumed == [("hobby", 180.0)]
