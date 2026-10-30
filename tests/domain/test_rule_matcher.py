"""The fast categorization engine must give exactly the same, deterministic result as plain ``re.search`` per row."""

import random
import re

import pandas as pd
import pytest

from mymoneyvisualizer.domain.categorization import (
    RuleMatcher,
    _DistinctTexts,
    anchored_literals,
    apply_rules,
    literal_alternatives,
    rule_mask,
)
from mymoneyvisualizer.domain.columns import CATEGORY_COLUMNS, MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import ManualCategory, Rule

from ..helpers import transactions


def reference_categorization(df, rules, manual_categories=None):
    """The straightforward algorithm: every rule on every row, in order, then manual categories."""
    out = df.copy()
    out[Col.category], out[Col.rule], out[Col.sale_of] = "", "", ""
    out[Col.spread_months] = out[Col.residual_percent] = 0
    for rule in rules:
        mask = rule_mask(out, rule)
        out.loc[mask, [Col.category, Col.rule]] = [rule.category, rule.id]
        out.loc[mask, [Col.spread_months, Col.residual_percent]] = [rule.spread_months, rule.residual_percent]
    for transaction_id, manual in (manual_categories or {}).items():
        mask = out[Col.transaction_id] == transaction_id
        out.loc[mask, [Col.category, Col.rule, Col.sale_of]] = [manual.category, MANUAL_RULE, manual.sale_of]
        out.loc[mask, [Col.spread_months, Col.residual_percent]] = [manual.spread_months, manual.residual_percent]
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
    matcher = RuleMatcher(df)
    first = matcher.distinct_matches(Col.recipient, "RE")
    assert matcher.distinct_matches(Col.recipient, "RE") is first
    assert not matcher.mask(Rule(regex_recipient="([")).any()
    assert "invalid regex" in caplog.text
    assert matcher.mask(Rule()).all()
    matcher.CACHE_LIMIT = 1
    matcher.distinct_matches(Col.description, "x")
    assert len(matcher._cache) == 1
    with pytest.raises(ValueError):
        apply_rules(df.iloc[:1], [], matcher=matcher)


def test_engine_equals_reference_on_large_data():
    from ..perf.dataset import build_state

    state = build_state(accounts=3, years=3, rules=400, manual=60)
    df = pd.concat(state.accounts.values(), ignore_index=True)
    fast = apply_rules(df, state.rules, state.manual_categories)
    slow = reference_categorization(df, state.rules, state.manual_categories)
    for column in CATEGORY_COLUMNS:
        assert list(fast[column]) == list(slow[column]), column


def test_engine_equals_reference_with_tricky_rules():
    df = transactions(*[(f"2024-01-{i % 28 + 1:02d}", text, text[::-1], -1.0) for i, text in enumerate(TEXTS)])
    rules = [
        Rule(category=f"category{i}", regex_recipient=p, regex_description=q, spread_months=12 * (i % 3))
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
    once = df[Col.transaction_id].iloc[3]
    manual = {once: ManualCategory(once, "once", spread_months=24, residual_percent=10)}
    fast = apply_rules(df, rules, manual)
    slow = reference_categorization(df, rules, manual)
    for column in CATEGORY_COLUMNS:
        assert list(fast[column]) == list(slow[column]), column


def test_result_is_identical_after_restart(tmp_path):
    """Cached results while working must equal a fresh start with the stored data."""
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.storage.repository import Repository

    from ..perf.dataset import build_state

    Repository(tmp_path / "data").save_all(build_state(accounts=3, years=3, rules=300, manual=40))
    model = AppModel.open(tmp_path / "data")
    model.transactions()  # fill the caches
    first = model.rules[10]
    model.save_rule(Rule(category="x.new", regex_recipient="REWE Markt 1"))
    model.save_rule(Rule(category="y.changed", regex_description="SAGT DANKE"), original_id=first.id)
    model.update_rule(model.rules[5].id, spread_months=12, residual_percent=20)
    model.delete_rules([model.rules[20].id])
    some_id = model.transactions()[Col.transaction_id].iloc[100]
    model.save_manual_category(ManualCategory(some_id, "z.once", spread_months=36))
    model.remove_manual_category(next(iter(model.manual_categories)))
    model.preview_rule(Rule(regex_recipient="Shell"), first.id, some_id)
    model.import_transactions("Girokonto", transactions(("2026-10-01", "REWE Markt 1", "Einkauf", -5.0)))

    columns = [Col.transaction_id, Col.account, *CATEGORY_COLUMNS]

    def categories(model, df):
        """Rule ids are new after a restart, so the winning rule is compared by its position."""
        positions = {rule.id: f"#{i}" for i, rule in enumerate(model.rules)}
        return df[columns].assign(**{Col.rule: df[Col.rule].map(lambda r: positions.get(r, r))})

    restarted = AppModel.open(tmp_path / "data")
    pd.testing.assert_frame_equal(
        categories(model, model.transactions()), categories(restarted, restarted.transactions())
    )
    fresh = apply_rules(restarted._combined_raw(), restarted.rules, restarted.manual_categories)
    pd.testing.assert_frame_equal(restarted.transactions()[columns], fresh[columns])
