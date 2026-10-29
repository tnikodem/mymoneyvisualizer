import logging

import numpy as np

from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, Col
from mymoneyvisualizer.domain.models import OneTimeTag, Tagger
from mymoneyvisualizer.domain.tagging import apply_taggers, regex_error, tagger_errors, tagger_mask, tagger_matches

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
    assert tagger_errors(Tagger("t", regex_recipient="(", regex_description="ok")).keys() == {"regex_recipient"}
    assert tagger_errors(Tagger("t")) == {}


def test_empty_regex_matches_everything():
    assert tagger_mask(_df(), Tagger("all")).all()


def test_regex_is_searched_not_anchored():
    mask = tagger_mask(_df(), Tagger("t", regex_description="Einkauf"))
    assert list(mask) == [True, True, False, False]


def test_both_regexes_must_match():
    mask = tagger_mask(_df(), Tagger("t", regex_recipient="EDEKA|REWE", regex_description="^Bio"))
    assert list(mask) == [False, True, False, False]


def test_invalid_regex_matches_nothing_and_logs(caplog):
    with caplog.at_level(logging.ERROR):
        mask = tagger_mask(_df(), Tagger("broken", regex_recipient="(["))
    assert not mask.any()
    assert "broken" in caplog.text


def test_tagger_matches_single_transaction():
    """Regression: the tagger window used re.match (anchored) while tagging used re.search."""
    tagger = Tagger("t", regex_recipient="Markt", regex_description="xyz")
    assert tagger_matches(tagger, "REWE Markt", "Einkauf") == (True, False)
    assert tagger_matches(Tagger("t"), "a", "b") == (True, True)


def test_apply_taggers_later_tagger_wins_and_keeps_input():
    df = _df()
    taggers = [
        Tagger("groceries", tag="household.food", regex_recipient="REWE|EDEKA", recurring=None),
        Tagger("bio", tag="household.food.bio", regex_description="Bio", recurring=2),
    ]
    out = apply_taggers(df, taggers)
    assert list(out[Col.tag]) == ["household.food", "household.food.bio", "", ""]
    assert list(out[Col.tagger_name]) == ["groceries", "bio", "", ""]
    assert np.isnan(out[Col.recurring].iloc[0])
    assert out[Col.recurring].iloc[1] == 2.0
    assert Col.tag not in df.columns


def test_one_time_tags_win_over_taggers():
    df = _df()
    target = df[Col.transaction_id].iloc[0]
    out = apply_taggers(
        df,
        [Tagger("groceries", tag="food", regex_recipient="REWE")],
        {target: OneTimeTag(target, "gift", 3), "unknown-id": OneTimeTag("unknown-id", "x")},
    )
    assert out[Col.tag].iloc[0] == "gift"
    assert out[Col.tagger_name].iloc[0] == ONE_TIME_TAGGER
    assert out[Col.recurring].iloc[0] == 3.0


def test_apply_taggers_on_empty_table():
    out = apply_taggers(transactions(), [Tagger("t", tag="x")])
    assert out.empty
    assert {Col.tag, Col.tagger_name, Col.recurring} <= set(out.columns)
