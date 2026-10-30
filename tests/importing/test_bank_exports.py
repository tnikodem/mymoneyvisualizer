"""End-to-end checks with exports in the layout of many banks, including broken ones (``tests/data/test_csv``).

The expected rows come from the generator of the test files, not from the importer. For every file:
auto detection -> import -> a rule per transaction created like a double click -> income & expenses per category.
"""

from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest
import yaml

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.analysis import NET, SUMMARY, TOTAL, income_expenses_table, month_key
from mymoneyvisualizer.domain.categorization import regex_for, rule_matches
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Rule
from mymoneyvisualizer.importing.reader import preview_import, propose_profile, read_table, to_transactions

DATA = Path(__file__).parents[1] / "data" / "test_csv"
EXPECTED = yaml.safe_load((DATA / "expected.yaml").read_text(encoding="utf-8"))
FILES = list(EXPECTED)


def _import(name):
    profile, _ = propose_profile(DATA / name)
    table = read_table(DATA / name, profile)
    transactions, invalid, zero = to_transactions(table, profile)
    return transactions, invalid, zero, profile, table


def _rows(df):
    return [
        (date.date().isoformat(), recipient, description, round(value, 2))
        for date, recipient, description, value in zip(
            df[Col.date], df[Col.recipient], df[Col.description], df[Col.value], strict=True
        )
    ]


@pytest.mark.parametrize("name", FILES)
def test_import_matches_ground_truth(name):
    transactions, invalid, zero, _, _ = _import(name)
    expected = EXPECTED[name]
    assert _rows(transactions) == [
        (t["date"], t["recipient"], t["description"], t["value"]) for t in expected["transactions"]
    ]
    assert (invalid, zero) == (expected["skipped"], 0)


@pytest.mark.parametrize("name", FILES)
def test_reimport_adds_nothing(name):
    transactions, _, _, profile, table = _import(name)
    assert preview_import(table, profile, existing=transactions).transactions.empty


@pytest.mark.parametrize("name", FILES)
def test_double_click_rules_and_income_expenses(name, tmp_path):
    """Rules created from the (possibly broken) text categorize their transaction; the table adds up per category."""
    transactions, _, _, _, _ = _import(name)
    truth = EXPECTED[name]["transactions"]
    model = AppModel.open(tmp_path / "data")
    model.add_account("konto")
    model.import_transactions("konto", transactions)

    categories = dict(zip(transactions[Col.transaction_id], (t["category"] for t in truth), strict=True))
    for transaction_id, category in categories.items():
        row = model.transaction(transaction_id)
        rule = Rule(
            category=category,
            regex_recipient=regex_for(row[Col.recipient]),
            regex_description=regex_for(row[Col.description]),
        )
        assert rule_matches(rule, row[Col.recipient], row[Col.description]) == (True, True)
        model.save_rule(rule)

    categorized = model.transactions().set_index(Col.transaction_id)
    assert {tid: categorized.at[tid, Col.category] for tid in categories} == categories

    expected_sums = defaultdict(float)
    for t in truth:
        expected_sums[t["category"]] += t["value"]
    first, last = min(t["date"] for t in truth), max(t["date"] for t in truth)
    table = income_expenses_table(model.transactions(), month_key(first), month_key(last))
    categories = table.loc[table[SUMMARY] == ""].set_index(Col.category)
    assert set(categories.index) == set(expected_sums)
    for category, total in expected_sums.items():
        assert categories.at[category, TOTAL] == pytest.approx(total, abs=0.005), category
    net = table.loc[table[SUMMARY] == NET, TOTAL].item()
    assert net == pytest.approx(sum(t["value"] for t in truth), abs=0.005)


def test_all_files_are_covered():
    files = {p.name for p in DATA.iterdir() if p.suffix in (".csv", ".txt")}
    assert files == set(FILES)


def test_expected_data_is_consistent():
    for name, data in EXPECTED.items():
        dates = [pd.Timestamp(t["date"]) for t in data["transactions"]]
        assert dates, name
        assert all(isinstance(t["value"], float | int) for t in data["transactions"]), name
