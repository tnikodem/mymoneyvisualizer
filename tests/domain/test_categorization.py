import logging

from mymoneyvisualizer.domain.categorization import apply_rules, regex_error, rule_errors, rule_mask, rule_matches
from mymoneyvisualizer.domain.columns import CATEGORY_COLUMNS, MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import ManualCategory, Rule

from ..helpers import transactions


def _df():
    return transactions(
        ("2024-01-01", "REWE Markt", "Einkauf", -10.0),
        ("2024-01-02", "EDEKA", "Bio Einkauf", -20.0),
        ("2024-01-03", "Vermieter", "Miete Januar", -900.0),
        ("2024-01-04", "", "", 5.0),
    )


def test_regex_errors():
    assert regex_error("REWE|EDEKA") is None
    assert regex_error("([") is not None
    assert rule_errors(Rule("t", regex_recipient="(", regex_description="ok")).keys() == {"regex_recipient"}
    assert rule_errors(Rule("t")) == {}


def test_empty_regex_matches_everything():
    assert rule_mask(_df(), Rule("all")).all()


def test_regex_is_searched_not_anchored():
    mask = rule_mask(_df(), Rule("t", regex_description="Einkauf"))
    assert list(mask) == [True, True, False, False]


def test_both_regexes_must_match():
    mask = rule_mask(_df(), Rule("t", regex_recipient="EDEKA|REWE", regex_description="^Bio"))
    assert list(mask) == [False, True, False, False]


def test_invalid_regex_matches_nothing_and_logs(caplog):
    with caplog.at_level(logging.ERROR):
        mask = rule_mask(_df(), Rule("broken", regex_recipient="(["))
    assert not mask.any()
    assert "broken" in caplog.text


def test_rule_matches_single_transaction():
    """Regression: the rule window used re.match (anchored) while categorization used re.search."""
    rule = Rule("t", regex_recipient="Markt", regex_description="xyz")
    assert rule_matches(rule, "REWE Markt", "Einkauf") == (True, False)
    assert rule_matches(Rule("t"), "a", "b") == (True, True)


def test_apply_rules_later_rule_wins_and_keeps_input():
    df = _df()
    rules = [
        Rule("groceries", category="household.food", regex_recipient="REWE|EDEKA"),
        Rule("bio", category="household.food.bio", regex_description="Bio", spread_months=12),
    ]
    out = apply_rules(df, rules)
    assert list(out[Col.category]) == ["household.food", "household.food.bio", "", ""]
    assert list(out[Col.rule]) == ["groceries", "bio", "", ""]
    assert list(out[Col.spread_months]) == [0, 12, 0, 0]
    assert list(out[Col.sale_of]) == ["", "", "", ""]
    assert Col.category not in df.columns


def test_manual_categories_win_over_rules():
    df = _df()
    target = df[Col.transaction_id].iloc[0]
    out = apply_rules(
        df,
        [Rule("groceries", category="food", regex_recipient="REWE")],
        {
            target: ManualCategory(target, "gift", spread_months=60, residual_percent=40, sale_of="other"),
            "unknown-id": ManualCategory("unknown-id", "x"),
        },
    )
    assert out[Col.category].iloc[0] == "gift"
    assert out[Col.rule].iloc[0] == MANUAL_RULE
    assert out[[Col.spread_months, Col.residual_percent, Col.sale_of]].iloc[0].tolist() == [60, 40, "other"]


def test_apply_rules_on_empty_table():
    out = apply_rules(transactions(), [Rule("t", category="x")])
    assert out.empty
    assert set(CATEGORY_COLUMNS) <= set(out.columns)
