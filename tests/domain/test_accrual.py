"""Spreading payments over the months they are used in (accrual basis)."""

import pandas as pd
import pytest

from mymoneyvisualizer.domain.accrual import accrue, linked_sales, month_numbers, schedule, to_period
from mymoneyvisualizer.domain.columns import Col

from ..helpers import categorized


def _accrue(*rows, categories, **spreads):
    return accrue(categorized(*rows, categories=categories, **spreads))


def _month(monthly, month, category):
    return monthly.loc[pd.Period(month, "M"), category]


def test_month_numbers_are_consecutive():
    numbers = month_numbers(pd.Series(pd.to_datetime(["2023-12-31", "2024-01-01", "2024-02-29"])))
    assert list(numbers - numbers[0]) == [0, 1, 2]
    assert to_period(int(numbers[1])) == pd.Period("2024-01", "M")


def test_unspread_payments_count_in_their_month():
    monthly = _accrue(
        ("2024-01-15", "REWE", "x", -50.0),
        ("2024-03-02", "REWE", "x", -20.0),
        ("2024-03-20", "ACME", "Gehalt", 3000.0),
        categories=["food", "food", "income"],
    )
    assert [str(p) for p in monthly.index] == ["2024-01", "2024-02", "2024-03"]
    assert list(monthly["food"]) == [-50.0, 0.0, -20.0]
    assert list(monthly["income"]) == [0.0, 0.0, 3000.0]


def test_prepaid_insurance_is_spread_over_its_service_period():
    """Rechnungsabgrenzung: a yearly premium of 600 € costs 50 € in each month it covers."""
    monthly = _accrue(("2024-03-10", "HUK", "Kfz", -600.0), categories=["car"], spread_months=[12])
    assert monthly.index[0] == pd.Period("2024-03", "M")
    assert monthly.index[-1] == pd.Period("2025-02", "M")
    assert monthly["car"].tolist() == [-50.0] * 12


def test_furniture_is_depreciated_over_its_useful_life():
    """Abschreibung: a sofa for 2,400 € used for ten years costs 20 € per month."""
    monthly = _accrue(("2024-02-01", "Möbelhaus", "Sofa", -2400.0), categories=["home"], spread_months=[120])
    assert len(monthly) == 120
    assert monthly["home"].tolist() == pytest.approx([-20.0] * 120)


def test_only_the_loss_of_value_is_spread_the_residual_value_is_kept():
    """A car for 30,000 €, used five years, still worth 40 %: 18,000 € loss of value, 300 € per month."""
    monthly = _accrue(
        ("2020-03-15", "Autohaus", "Golf", -30000.0),
        categories=["car"],
        spread_months=[60],
        residual_percent=[40],
    )
    assert monthly.index[[0, -1]].tolist() == [pd.Period("2020-03", "M"), pd.Period("2025-02", "M")]
    assert monthly["car"].tolist() == pytest.approx([-300.0] * 60)
    assert monthly["car"].sum() == pytest.approx(-18000.0)


def test_a_linked_sale_spreads_the_real_loss_over_the_months_owned():
    """Sold for 10,000 € in June 2026: 20,000 € loss over 76 months, the proceeds are no income."""
    df = categorized(
        ("2020-03-15", "Autohaus", "Golf", -30000.0),
        ("2026-06-10", "Max Mustermann", "Verkauf Golf", 10000.0),
        categories=["car", "car"],
        spread_months=[60, 0],
        residual_percent=[40, 0],
    )
    df[Col.sale_of] = ["", df[Col.transaction_id].iloc[0]]
    monthly = accrue(df)
    assert monthly.index[[0, -1]].tolist() == [pd.Period("2020-03", "M"), pd.Period("2026-06", "M")]
    assert len(monthly) == 76
    assert monthly["car"].tolist() == pytest.approx([-20000.0 / 76] * 76)
    assert monthly["car"].sum() == pytest.approx(-30000.0 + 10000.0)


def test_a_sale_also_ends_an_unspread_purchase():
    df = categorized(
        ("2024-01-10", "Shop", "E-Bike", -3000.0),
        ("2024-12-20", "Kleinanzeigen", "E-Bike", 1800.0),
        categories=["mobility", "mobility"],
    )
    df[Col.sale_of] = ["", df[Col.transaction_id].iloc[0]]
    assert accrue(df)["mobility"].tolist() == pytest.approx([-100.0] * 12)


def test_several_sales_of_one_purchase_add_up():
    df = categorized(
        ("2024-01-10", "Shop", "Set", -1000.0),
        ("2024-02-10", "A", "part 1", 300.0),
        ("2024-04-10", "B", "part 2", 300.0),
        categories=["hobby"] * 3,
        spread_months=[120, 0, 0],
    )
    df[Col.sale_of] = ["", df[Col.transaction_id].iloc[0], df[Col.transaction_id].iloc[0]]
    monthly = accrue(df)
    assert monthly["hobby"].tolist() == pytest.approx([-100.0] * 4)


@pytest.mark.parametrize("link", ["unknown-id", "SELF", "LATER"])
def test_invalid_sale_links_are_ordinary_payments(link):
    df = categorized(
        ("2024-01-10", "Shop", "x", -1200.0),
        ("2024-03-10", "Buyer", "y", 500.0),
        ("2024-05-10", "Shop", "later purchase", -100.0),
        categories=["hobby"] * 3,
        spread_months=[12, 0, 0],
    )
    ids = df[Col.transaction_id].tolist()
    df[Col.sale_of] = ["", {"SELF": ids[1], "LATER": ids[2]}.get(link, link), ""]
    assert linked_sales(df) == {}
    monthly = accrue(df)
    assert _month(monthly, "2024-03", "hobby") == pytest.approx(-100.0 + 500.0)
    assert _month(monthly, "2024-05", "hobby") == pytest.approx(-100.0 - 100.0)


def test_schedule_keeps_the_index_and_leaves_out_linked_sales():
    df = categorized(
        ("2024-01-10", "Shop", "x", -1200.0),
        ("2024-03-10", "Buyer", "y", 600.0),
        categories=["hobby", "hobby"],
        spread_months=[24, 0],
    )
    df.index = [10, 11]
    df[Col.sale_of] = ["", df[Col.transaction_id].iloc[0]]
    plan = schedule(df)
    assert plan.index.tolist() == [10]
    assert plan["amount"].iloc[0] == pytest.approx(-200.0)


def test_nothing_is_projected():
    """Only real payments: after the last spread month there is nothing, even for a yearly payment."""
    monthly = _accrue(("2024-01-01", "HUK", "Kfz", -600.0), categories=["car"], spread_months=[12])
    assert monthly.index[-1] == pd.Period("2024-12", "M")


def test_accrue_empty():
    assert accrue(categorized(categories=[])).empty
