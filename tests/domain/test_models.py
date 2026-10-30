import math

import pytest

from mymoneyvisualizer.domain.models import (
    LAST_12_MONTHS,
    GroupAssignment,
    ManualCategory,
    Rule,
    Settings,
    clean_months,
    clean_percent,
    reorder_groups,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, 0), (math.nan, 0), ("", 0), ("x", 0), (-2, 0), (True, 1), (12, 12), (2.7, 2), ("36", 36), (10_000, 600)],
)
def test_clean_months(value, expected):
    assert clean_months(value) == expected


@pytest.mark.parametrize(("value", "expected"), [(None, 0), ("x", 0), (-5, 0), (40, 40), ("12.5", 12), (100, 99)])
def test_clean_percent(value, expected):
    assert clean_percent(value) == expected


def test_rule_roundtrip_and_missing_values():
    rule = Rule(category="car", regex_recipient="Autohaus", spread_months=72, residual_percent=40)
    assert Rule.from_dict(rule.to_dict()) == rule
    assert Rule.from_dict({"category": None}) == Rule()


def test_rule_id_tells_rules_apart_but_is_not_stored_or_compared():
    first, second = Rule(category="food"), Rule(category="food")
    assert first.id != second.id
    assert first == second
    assert "id" not in first.to_dict()
    assert Rule.from_dict(first.to_dict()).id != first.id


def test_unspread_rule_has_no_spread_keys():
    assert Rule("food", "REWE").to_dict() == {
        "category": "food",
        "regex_recipient": "REWE",
        "regex_description": "",
    }
    assert "residual_percent" not in Rule(spread_months=12).to_dict()


def test_manual_category_roundtrip():
    sale = ManualCategory("id-2", "car", sale_of="id-1")
    furniture = ManualCategory("id-3", "home.furniture", spread_months=120)
    for manual in (sale, furniture, ManualCategory("id-4", "hobby")):
        assert ManualCategory.from_dict(manual.to_dict()) == manual
    assert sale.to_dict() == {"transaction_id": "id-2", "category": "car", "sale_of": "id-1"}


def test_group_assignment_unknown_category():
    assert GroupAssignment.from_dict({"category": "", "group": "income"}) == GroupAssignment("", "income")
    assert GroupAssignment.from_dict({"category": "x", "group": "nonsense"}).group == "needs"
    assert GroupAssignment.from_dict({"category": "x"}).to_dict() == {"category": "x", "group": "needs"}


def test_settings_defaults():
    settings = Settings()
    assert settings.budget_period == LAST_12_MONTHS
    assert settings.budget_shares == {"needs": 0.5, "wants": 0.3}
    assert settings.savings_share == pytest.approx(0.2)
    assert settings.hide_internal_transfers is True


def test_savings_share_is_the_rest():
    assert Settings(budget_shares={"needs": 0.6, "wants": 0.3}).savings_share == pytest.approx(0.1)
    assert Settings(budget_shares={"needs": 0.8, "wants": 0.4}).savings_share == 0.0


def test_settings_instances_do_not_share_state():
    """Regression: loading a configuration overwrote the module level DEFAULT_SETTINGS dict."""
    first = Settings.from_dict({"excluded_categories": ["a"], "budget": {"shares": {"needs": 0.9}}})
    first.excluded_categories.append("b")
    first.budget_shares["wants"] = 0.1
    second = Settings()
    assert second.excluded_categories == []
    assert second.budget_shares == {"needs": 0.5, "wants": 0.3}


def test_settings_roundtrip():
    settings = Settings(
        excluded_categories=["x"], budget_period="2022", hide_internal_transfers=False, hidden_hints=["budget"]
    )
    settings.budget_shares["needs"] = 0.4
    assert Settings.from_dict(settings.to_dict()) == settings


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"budget": "garbage"},
        {"budget": {"period": 2020}},
        {"budget": {"period": "last year"}},
        {"budget": {"shares": {"needs": 7}}},
        {"budget": {"shares": "garbage"}},
        {"excluded_categories": "not-a-list"},
        {"hidden_hints": "not-a-list"},
    ],
)
def test_settings_ignore_invalid_values(data):
    assert Settings.from_dict(data) == Settings()


def test_reorder_groups_moves_and_recategorizes():
    current = [GroupAssignment("income", "income"), GroupAssignment("food", "needs"), GroupAssignment("hobby", "wants")]
    result = reorder_groups(current, {"needs": ["food", "hobby"], "wants": [], "income": ["income"]})
    assert [(a.category, a.group) for a in result] == [("food", "needs"), ("hobby", "needs"), ("income", "income")]
    # input is not modified
    assert current[2].group == "wants"


def test_reorder_groups_matches_old_order_algorithm():
    old = [" ", "amazon", "bank", "cash", "food", "hobby", "home", "mobility", "person", "savings", "transfer", "work"]
    new = [" ", "food", "amazon", "bank", "cash", "hobby", "home", "mobility", "person", "savings", "transfer", "work"]
    current = [GroupAssignment(n, "needs") for n in old]
    assert [a.category for a in reorder_groups(current, {"needs": new})] == new


def test_reorder_groups_keeps_categories_missing_in_the_lists():
    """Regression: categories not shown in the lists (e.g. excluded categories) lost their group after drag & drop."""
    current = [
        GroupAssignment("income", "income"),
        GroupAssignment("food", "needs"),
        GroupAssignment("hidden", "wants"),
    ]
    result = reorder_groups(current, {"needs": ["food"], "income": ["income"]})
    assert ("hidden", "wants") in [(a.category, a.group) for a in result]
    assert len(result) == 3


def test_reorder_groups_adds_new_names():
    result = reorder_groups([GroupAssignment("a")], {"wants": ["a", "b"]})
    assert [(a.category, a.group) for a in result] == [("a", "wants"), ("b", "wants")]
