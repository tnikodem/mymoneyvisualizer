import pandas as pd
import pytest

from mymoneyvisualizer.domain.budget import (
    IN_PERIOD,
    SAVED,
    SOLD,
    SPREAD_FROM,
    SPREAD_TO,
    BudgetSeries,
    budget_report,
    budget_series,
    contributions,
    group_totals,
    period_months,
    previous_months,
    smooth,
)
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import LAST_12_MONTHS, GroupAssignment

from ..helpers import categorized

SHARES = {"needs": 0.5, "wants": 0.3}
YEAR_2024 = (pd.Period("2024-01", "M"), pd.Period("2024-12", "M"))
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
    assert budget_report(series, [], *YEAR_2024, SHARES) is None


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
    report = budget_report(_series(), GROUPS, *YEAR_2024, SHARES)
    assert report.months == report.period_months == 12
    assert report.is_complete
    assert report.income == pytest.approx(36000.0)
    assert report.income_categories == [("income", 36000.0)]
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
    report = budget_report(series, GROUPS, *YEAR_2024, SHARES)
    assert report.savings_rate == pytest.approx(0.0)
    assert report.room_per_month == pytest.approx(-0.2 * 3000.0)


def test_budget_report_counts_only_the_months_of_the_period_with_data():
    series = _series()
    series.monthly.index = pd.period_range("2023-07", "2024-06", freq="M")
    report = budget_report(series, GROUPS, pd.Period("2024-01", "M"), pd.Period("2025-12", "M"), SHARES)
    assert (report.months, report.period_months) == (6, 24)
    assert not report.is_complete
    assert report.income == pytest.approx(18000.0)
    assert report.per_month(report.income) == pytest.approx(3000.0)


def test_budget_report_without_income():
    series = _series()
    series.monthly["income"] = 0.0
    report = budget_report(series, GROUPS, *YEAR_2024, SHARES)
    assert report.savings_rate is None
    assert report.room_per_month is None


def test_budget_report_outside_the_data():
    report = budget_report(_series(), GROUPS, pd.Period("2030-01", "M"), pd.Period("2030-12", "M"), SHARES)
    assert report.months == 0
    assert report.room_per_month is None
    assert report.per_month(100.0) == 0.0


def test_smooth_starts_with_a_full_year():
    """An average of fewer months would show a single large payment (here 12 in January) as a spike."""
    monthly = pd.DataFrame({"x": [12.0] + [0.0] * 13}, index=pd.period_range("2024-01", periods=14, freq="M"))
    smoothed = smooth(monthly)["x"]
    assert smoothed.index[0] == pd.Period("2024-12", "M")
    assert smoothed.tolist() == pytest.approx([1.0, 0.0, 0.0])
    assert smooth(monthly.iloc[:11]).empty


def test_period_months():
    last = pd.Period("2026-09", "M")
    assert period_months(LAST_12_MONTHS, last) == (pd.Period("2025-10", "M"), last)
    assert period_months("2025", last) == (pd.Period("2025-01", "M"), pd.Period("2025-12", "M"))
    assert period_months("2026", last) == (pd.Period("2026-01", "M"), last)  # only complete months
    assert previous_months(*period_months("2026", last)) == (pd.Period("2025-01", "M"), pd.Period("2025-09", "M"))
    assert period_months("2025-03:2025-08", last) == (pd.Period("2025-03", "M"), pd.Period("2025-08", "M"))
    assert period_months("2026-03:2026-12", last) == (pd.Period("2026-03", "M"), last)  # only complete months


def _month(text):
    return pd.Period(text, freq="M")


def test_contributions_of_a_period_include_spread_payments_made_before():
    df = categorized(
        ("2024-01-10", "Möbelhaus", "Sofa", -2400.0),  # 10 years: 20 € per month
        ("2025-03-05", "REWE", "x", -10.0),
        ("2025-06-01", "HUK", "Kfz", -600.0),  # June 2025 to May 2026: 50 € per month
        ("2025-07-01", "Ich", "Sparen", -100.0),  # internal transfer
        categories=["home.sofa", "food", "insurance", "spar"],
        spread_months=[120, 0, 12, 0],
    )
    rows = contributions(df, _month("2025-01"), _month("2025-12"), own_accounts=["spar"])
    assert list(rows[Col.recipient]) == ["Möbelhaus", "REWE", "HUK"]
    assert list(rows[IN_PERIOD]) == [-240.0, -10.0, -350.0]  # the insurance counts 7 of its 12 months
    assert (rows[SPREAD_FROM].iloc[0], rows[SPREAD_TO].iloc[0]) == (_month("2024-01"), _month("2033-12"))
    assert not rows[SOLD].any()
    only = contributions(df, _month("2025-01"), _month("2025-12"), categories=["home"])
    assert list(only[Col.recipient]) == ["Möbelhaus"]  # main categories
    assert contributions(df, _month("2023-01"), _month("2023-12")).empty


def test_contributions_of_a_sold_purchase():
    """A car for 30,000 € sold for 10,000 € after 18 months: 20,000 € over 18 months; the sale has no row."""
    df = categorized(
        ("2024-01-15", "Autohaus", "Auto", -30000.0),
        ("2025-06-20", "Max Mustermann", "Verkauf Auto", 10000.0),
        categories=["car", "car"],
        spread_months=[60, 0],
        residual_percent=[40, 0],
    )
    df.loc[1, Col.sale_of] = df.loc[0, Col.transaction_id]
    rows = contributions(df, _month("2025-01"), _month("2025-12"))
    assert list(rows[Col.recipient]) == ["Autohaus"]
    assert rows[IN_PERIOD].iloc[0] == pytest.approx(-20000 / 18 * 6, abs=0.01)
    assert rows[SPREAD_TO].iloc[0] == _month("2025-06")
    assert rows[SOLD].iloc[0]
