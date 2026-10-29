import datetime
import math

import pytest

from mymoneyvisualizer.domain.models import (
    OneTimeTag,
    Settings,
    TagCategory,
    Tagger,
    clean_recurring,
    recurring_to_float,
    reorder_categories,
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


def test_tagger_roundtrip_and_legacy_values():
    tagger = Tagger(name="t", tag="food", regex_recipient="REWE", regex_description="", recurring=2)
    assert Tagger.from_dict(tagger.to_dict()) == tagger
    legacy = Tagger.from_dict({"name": "t", "tag": None, "regex_recipient": math.nan, "recurring": math.nan})
    assert legacy == Tagger(name="t")


def test_one_time_tag_roundtrip():
    tag = OneTimeTag("id-1", "hobby", 3)
    assert OneTimeTag.from_dict(tag.to_dict()) == tag


def test_tag_category_legacy_blank_name_and_unknown_category():
    assert TagCategory.from_dict({"name": " ", "category": "income"}) == TagCategory("", "income")
    assert TagCategory.from_dict({"name": "x", "category": "nonsense"}).category == "basic"
    assert TagCategory.from_dict({"name": "x"}).to_dict() == {"name": "x", "category": "basic"}


def test_settings_defaults_use_current_year():
    settings = Settings()
    assert settings.budget_start == settings.budget_end == datetime.date.today().year
    assert settings.budget_factors == {"basic": 0.3, "optional": 0.5}
    assert settings.hide_transfers is True


def test_settings_instances_do_not_share_state():
    """Regression: loading a configuration overwrote the module level DEFAULT_SETTINGS dict."""
    first = Settings.from_dict({"exclude_tags": ["a"], "budget": {"factors": {"basic": 0.9}}})
    first.excluded_tags.append("b")
    first.budget_factors["optional"] = 0.1
    second = Settings()
    assert second.excluded_tags == []
    assert second.budget_factors == {"basic": 0.3, "optional": 0.5}


def test_settings_roundtrip():
    settings = Settings(excluded_tags=["x"], budget_start=2020, budget_end=2022, hide_transfers=False)
    settings.budget_factors["basic"] = 0.4
    assert Settings.from_dict(settings.to_dict()) == settings


def test_settings_reads_legacy_format():
    legacy = {
        "exclude_tags": ["giro"],
        "budget": {"basic": {"factor": 0.25, "start": 2019, "end": 2021}, "optional": {"factor": 0.6}},
        "plot_aggregation_month": 3,
    }
    settings = Settings.from_dict(legacy)
    assert settings.excluded_tags == ["giro"]
    assert (settings.budget_start, settings.budget_end) == (2019, 2021)
    assert settings.budget_factors == {"basic": 0.25, "optional": 0.6}


@pytest.mark.parametrize(
    "data",
    [
        None,
        {},
        {"budget": "garbage"},
        {"budget": {"start": 2020}},
        {"budget": {"factors": {"basic": 7}}},
        {"exclude_tags": "not-a-list"},
    ],
)
def test_settings_ignore_invalid_values(data):
    assert Settings.from_dict(data) == Settings()


def test_settings_swap_inverted_period():
    settings = Settings.from_dict({"budget": {"start": 2024, "end": 2020}})
    assert (settings.budget_start, settings.budget_end) == (2020, 2024)


def test_reorder_categories_moves_and_recategorizes():
    current = [TagCategory("income", "income"), TagCategory("food", "basic"), TagCategory("hobby", "optional")]
    result = reorder_categories(current, {"basic": ["food", "hobby"], "optional": [], "income": ["income"]})
    assert [(c.name, c.category) for c in result] == [("food", "basic"), ("hobby", "basic"), ("income", "income")]
    # input is not modified
    assert current[2].category == "optional"


def test_reorder_categories_matches_old_order_algorithm():
    old = [" ", "amazon", "bank", "cash", "food", "hobby", "home", "mobility", "person", "savings", "transfer", "work"]
    new = [" ", "food", "amazon", "bank", "cash", "hobby", "home", "mobility", "person", "savings", "transfer", "work"]
    current = [TagCategory(n, "basic") for n in old]
    assert [c.name for c in reorder_categories(current, {"basic": new})] == new


def test_reorder_categories_keeps_tags_missing_in_the_lists():
    """Regression: tags not shown in the lists (e.g. excluded tags) lost their category after drag & drop."""
    current = [TagCategory("income", "income"), TagCategory("food", "basic"), TagCategory("hidden", "optional")]
    result = reorder_categories(current, {"basic": ["food"], "income": ["income"]})
    assert ("hidden", "optional") in [(c.name, c.category) for c in result]
    assert len(result) == 3


def test_reorder_categories_adds_new_names():
    result = reorder_categories([TagCategory("a")], {"optional": ["a", "b"]})
    assert [(c.name, c.category) for c in result] == [("a", "optional"), ("b", "optional")]
