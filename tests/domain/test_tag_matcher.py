"""The fast tagging engine must give exactly the same, deterministic result as plain ``re.search`` per row."""

import random
import re

import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import OneTimeTag, Tagger
from mymoneyvisualizer.domain.tagging import (
    TagMatcher,
    _DistinctTexts,
    anchored_literals,
    apply_taggers,
    literal_alternatives,
    recurring_to_float,
    tagger_mask,
)

from ..helpers import transactions


def reference_tagging(df, taggers, one_time_tags=None):
    """The straightforward algorithm: every tagger on every row, in order, then one-time tags."""
    out = df.copy()
    out[Col.tag], out[Col.tagger_name], out[Col.recurring] = "", "", np.nan
    for tagger in taggers:
        mask = tagger_mask(out, tagger)
        out.loc[mask, Col.tag] = tagger.tag
        out.loc[mask, Col.tagger_name] = tagger.name
        out.loc[mask, Col.recurring] = recurring_to_float(tagger.recurring)
    for transaction_id, tag in (one_time_tags or {}).items():
        mask = out[Col.transaction_id] == transaction_id
        out.loc[mask, [Col.tag, Col.tagger_name]] = [tag.tag, "one_time_tag"]
        out.loc[mask, Col.recurring] = recurring_to_float(tag.recurring)
    return out


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("REWE", [("REWE", False, False)]),
        (r"REWE|EDEKA\.de|", [("REWE", False, False), ("EDEKA.de", False, False), ("", False, False)]),
        (r"^Miete|Shell 12$|^x$", [("Miete", True, False), ("Shell 12", False, True), ("x", True, True)]),
        (r"Sch\ r\(1\)", [("Sch r(1)", False, False)]),
        ("a\\\nb", [("a\nb", False, False)]),
        (r"\d+", None),
        ("a.b", None),
        ("a^b", None),
        ("a$b", None),
        ("(a)", None),
        ("^^a", None),
        ("a\\", None),
        ("a$$", None),
    ],
)
def test_anchored_literals(pattern, expected):
    assert anchored_literals(pattern) == expected


def test_literal_alternatives_without_anchors():
    assert literal_alternatives("A|B") == ["A", "B"]
    assert literal_alternatives("^A") is None
    assert literal_alternatives("A.") is None


TEXTS = [
    "REWE Markt 12",
    "REWE",
    "rewe",
    "EDEKA.de",
    "EDEKAxde",
    "Shell 12",
    "Shell 123",
    "Shell 12\n",
    "Shell 12\n\n",
    "x",
    "x\n",
    "",
    "\n",
    "Miete Oktober",
    " Miete",
    "Bäckerei Müller",
    "B�ckerei",
    "BÃ¤ckerei",
    "a\x1fb",
    "Sch r(1)",
    "tab\there",
    "Gehalt Okt",
    "Miete\r\nOktober",
    "a|b",
    "a^b",
    "50$",
    "x\x1f",
    "\x1fx",
]
ATOMS = [
    "REWE",
    "Shell 12",
    "x",
    "",
    "Miete",
    "rewe",
    r"\.",
    r"\(1\)",
    "Bäck",
    "�",
    "Ã¤",
    "\x1f",
    "b",
    "\n",
    "\\\n",
    r"\ ",
    "|",
    "Okt",
    "a",
]


def _random_pattern(rng):
    alternatives = []
    for _ in range(rng.randint(1, 3)):
        text = "".join(rng.choice(ATOMS) for _ in range(rng.randint(0, 2)))
        alternatives.append(("^" if rng.random() < 0.3 else "") + text + ("$" if rng.random() < 0.3 else ""))
    return "|".join(alternatives)


@pytest.mark.parametrize("with_separator", [True, False])
def test_fast_search_equals_re_search(with_separator):
    texts = TEXTS if with_separator else [t for t in TEXTS if "\x1f" not in t]
    distinct = _DistinctTexts(pd.Series(texts))
    rng = random.Random(3)
    for _ in range(3000):
        pattern = _random_pattern(rng)
        try:
            compiled = re.compile(pattern)
        except re.error:
            continue
        expected = [compiled.search(v) is not None for v in distinct.values]
        assert list(distinct.search(pattern)) == expected, pattern


def test_matcher_caches_and_handles_invalid_regex(caplog):
    df = transactions(("2024-01-01", "REWE", "x", -1.0), ("2024-01-02", "EDEKA", "y", -2.0))
    matcher = TagMatcher(df)
    first = matcher.distinct_matches(Col.recipient, "RE")
    assert matcher.distinct_matches(Col.recipient, "RE") is first
    assert not matcher.mask(Tagger("bad", regex_recipient="([")).any()
    assert "invalid regex" in caplog.text
    assert matcher.mask(Tagger("all")).all()
    matcher.CACHE_LIMIT = 1
    matcher.distinct_matches(Col.description, "x")
    assert len(matcher._cache) == 1
    with pytest.raises(ValueError):
        apply_taggers(df.iloc[:1], [], matcher=matcher)


def test_engine_equals_reference_on_large_data():
    from ..perf.dataset import build_state

    state = build_state(accounts=3, years=3, taggers=400, one_time=60)
    df = pd.concat(state.accounts.values(), ignore_index=True)
    fast = apply_taggers(df, state.taggers, state.one_time_tags)
    slow = reference_tagging(df, state.taggers, state.one_time_tags)
    for column in (Col.tag, Col.tagger_name):
        assert list(fast[column]) == list(slow[column])
    np.testing.assert_array_equal(fast[Col.recurring].to_numpy(), slow[Col.recurring].to_numpy())


def test_engine_equals_reference_with_tricky_taggers():
    df = transactions(*[(f"2024-01-{i % 28 + 1:02d}", text, text[::-1], -1.0) for i, text in enumerate(TEXTS)])
    taggers = [
        Tagger(f"t{i}", tag=f"tag{i}", regex_recipient=p, regex_description=q, recurring=i % 3 or None)
        for i, (p, q) in enumerate(
            [
                ("REWE", ""),
                ("^x$", ""),
                ("Shell 12$", ""),
                ("", "r"),
                ("[", ""),
                (r"\w+", "^"),
                ("a|^B", "$"),
                ("", ""),
                ("Ã¤|�", ""),
            ]
        )
    ]
    one_time = {df[Col.transaction_id].iloc[3]: OneTimeTag(df[Col.transaction_id].iloc[3], "once", 2)}
    fast = apply_taggers(df, taggers, one_time)
    slow = reference_tagging(df, taggers, one_time)
    assert list(fast[Col.tag]) == list(slow[Col.tag])
    assert list(fast[Col.tagger_name]) == list(slow[Col.tagger_name])


def test_result_is_identical_after_restart(tmp_path):
    """Cached results while working must equal a fresh start with the stored data."""
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.storage.repository import Repository

    from ..perf.dataset import build_state

    Repository(tmp_path / "data").save_all(build_state(accounts=3, years=3, taggers=300, one_time=40))
    model = AppModel.open(tmp_path / "data")
    model.transactions()  # fill the caches
    first = model.taggers[10]
    model.save_tagger(Tagger("new", tag="x.new", regex_recipient="REWE Markt 1"))
    model.save_tagger(Tagger(first.name, tag="y.changed", regex_description="SAGT DANKE"), original_name=first.name)
    model.delete_taggers([model.taggers[20].name])
    some_id = model.transactions()[Col.transaction_id].iloc[100]
    model.set_one_time_tag(some_id, "z.once", 3)
    model.remove_one_time_tag(next(iter(model.one_time_tags)))
    model.preview_tagger(Tagger("draft", regex_recipient="Shell"), first.name, some_id)
    model.import_transactions("Girokonto", transactions(("2026-10-01", "REWE Markt 1", "Einkauf", -5.0)))

    restarted = AppModel.open(tmp_path / "data")
    columns = [Col.transaction_id, Col.account, Col.tag, Col.tagger_name, Col.recurring]
    pd.testing.assert_frame_equal(model.transactions()[columns], restarted.transactions()[columns])
    fresh = apply_taggers(restarted._combined_raw(), restarted.taggers, restarted.one_time_tags)
    pd.testing.assert_frame_equal(restarted.transactions()[columns], fresh[columns])
