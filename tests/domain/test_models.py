import datetime
import math

import pytest

from mymoneyvisualizer.domain.models import (
    GroupAssignment,
    ManualCategory,
    Rule,
    Settings,
    clean_recurring,
    recurring_to_float,
    reorder_groups,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        (math.nan, None),
        ("", None),
        ("x", None),
        (0, None),
        (-2, None),
        (True, None),
        (1, 1),
        (2.0, 2),
        ("3", 3),
    ],
)
def test_clean_recurring(value, expected):
    assert clean_recurring(value) == expected


def test_recurring_to_float():
    assert math.isnan(recurring_to_float(None))
    assert recurring_to_float(2) == 2.0


def test_rule_roundtrip_and_missing_values():
    rule = Rule(name="t", category="food", regex_recipient="REWE", regex_description="", recurring=2)
    assert Rule.from_dict(rule.to_dict()) == rule
    assert Rule.from_dict({"name": "t", "category": None, "recurring": None}) == Rule(name="t")


def test_manual_category_roundtrip():
    category = ManualCategory("id-1", "hobby", 3)
    assert ManualCategory.from_dict(category.to_dict()) == category


def test_group_assignment_unknown_category():
    assert GroupAssignment.from_dict({"category": "", "group": "income"}) == GroupAssignment("", "income")
    assert GroupAssignment.from_dict({"category": "x", "group": "nonsense"}).group == "needs"
    assert GroupAssignment.from_dict({"category": "x"}).to_dict() == {"category": "x", "group": "needs"}


def test_settings_defaults_use_current_year():
    settings = Settings()
    assert settings.budget_start == settings.budget_end == datetime.date.today().year
    assert settings.budget_shares == {"needs": 0.3, "wants": 0.5}
    assert settings.hide_internal_transfers is True


def test_settings_instances_do_not_share_state():
    """Regression: loading a configuration overwrote the module level DEFAULT_SETTINGS dict."""
    first = Settings.from_dict({"excluded_categories": ["a"], "budget": {"factors": {"needs": 0.9}}})
    first.excluded_categories.append("b")
    first.budget_shares["wants"] = 0.1
    second = Settings()
    assert second.excluded_categories == []
    assert second.budget_shares == {"needs": 0.3, "wants": 0.5}


def test_settings_roundtrip():
    settings = Settings(excluded_categories=["x"], budget_start=2020, budget_end=2022, hide_internal_transfers=False)
    settings.budget_shares["needs"] = 0.4
    assert Settings.from_dict(settings.to_dict()) == settings


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"budget": "garbage"},
        {"budget": {"start": 2020}},
        {"budget": {"factors": {"needs": 7}}},
        {"budget": {"factors": "garbage"}},
        {"excluded_categories": "not-a-list"},
    ],
)
def test_settings_ignore_invalid_values(data):
    assert Settings.from_dict(data) == Settings()


def test_settings_swap_inverted_period():
    settings = Settings.from_dict({"budget": {"start": 2024, "end": 2020}})
    assert (settings.budget_start, settings.budget_end) == (2020, 2024)


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
