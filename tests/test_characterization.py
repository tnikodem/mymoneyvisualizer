"""Golden master: the new analysis must reproduce the numbers of the old implementation.

The files in ``tests/data/characterization`` were generated once with the code base before the
restructuring (version 0.1 incl. the "recurring" work in progress). Behaviour that was changed on purpose
(bug fixes) is tested elsewhere, never here.
"""

import json

import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.analysis import summary_table, tagger_overview
from mymoneyvisualizer.domain.budget import budget_report, budget_series, income_series
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import TagCategory

from .characterization import DATA_DIR, load_dataset


@pytest.fixture(scope="module")
def dataset():
    return load_dataset()


def test_tagging_matches_old_implementation(dataset):
    golden = pd.read_csv(DATA_DIR / "golden_tagging.csv", keep_default_na=False, na_values={"recurring": [""]})
    tagged = dataset.tagged.set_index(Col.transaction_id).loc[golden[Col.transaction_id]]
    assert list(tagged[Col.tag]) == list(golden[Col.tag])
    assert list(tagged[Col.tagger_name]) == list(golden[Col.tagger_name])
    np.testing.assert_array_equal(tagged[Col.recurring].to_numpy(), golden[Col.recurring].to_numpy())


@pytest.mark.parametrize("case", json.loads((DATA_DIR / "summary_cases.json").read_text()), ids=lambda c: c["name"])
def test_summary_table_matches_old_implementation(dataset, case):
    golden = pd.read_csv(DATA_DIR / f"golden_summary_{case['name']}.csv", keep_default_na=False)
    table = summary_table(
        dataset.tagged,
        case["date_from"],
        case["date_upto"],
        tag_level=case["tag_level"],
        tag_filter=case["tag_filter"],
        excluded_tags=case["excluded"],
    )
    assert list(table.columns) == list(golden.columns)
    # the old implementation sorted with an unstable sort, so compare per tag
    table = table.set_index(Col.tag)
    golden = golden.set_index(Col.tag)
    assert sorted(table.index) == sorted(golden.index)
    assert table.index[-1] == "total"
    pd.testing.assert_frame_equal(table.loc[golden.index], golden.astype(float), check_exact=False, atol=1e-6)


@pytest.mark.parametrize("case", json.loads((DATA_DIR / "graph_cases.json").read_text()), ids=lambda c: c["name"])
def test_budget_series_matches_old_implementation(dataset, case):
    golden = pd.read_csv(DATA_DIR / f"golden_graph_{case['name']}.csv", keep_default_na=False, index_col="month")
    golden.columns = ["" if c.startswith("Unnamed") else c for c in golden.columns]  # untagged transactions
    golden_income = pd.read_csv(DATA_DIR / f"golden_income_{case['name']}.csv", index_col="month")
    series = budget_series(dataset.tagged, budget_end_year=case["end"], transfer_accounts=dataset.account_names)

    monthly = series.monthly
    assert [p.strftime("%Y-%m") for p in monthly.index] == list(golden.index)
    assert list(monthly.columns) == list(golden.columns)
    np.testing.assert_allclose(monthly.to_numpy(), golden.to_numpy(), rtol=1e-9, atol=1e-6)

    golden_budget = json.loads((DATA_DIR / f"golden_budget_{case['name']}.json").read_text())
    categories = [TagCategory(name, category) for name, category in _categories(golden_budget)]
    income = income_series(monthly, categories)
    np.testing.assert_allclose(income.to_numpy(), golden_income["average_income"].to_numpy(), atol=1e-6)

    for category, expected in golden_budget.items():
        factor = {"basic": 0.3, "optional": 0.5}[category]
        report = budget_report(series, categories, category, case["start"], case["end"], factor)
        assert report.expected_total == pytest.approx(expected["expected_total_budget"])
        assert dict(report.consumed) == pytest.approx(expected["consumed"])
        assert report.total_consumed == pytest.approx(sum(expected["consumed"].values()))


def _categories(golden_budget):
    order = golden_budget["basic"]["category_order"]
    defaults = {"income": "income", "household": "basic", "car": "basic", "carsharing": "optional", "hobby": "optional"}
    return [(name, defaults.get(name, "basic")) for name in order]


def test_tagger_overview_matches_old_implementation(dataset):
    golden = pd.read_csv(DATA_DIR / "golden_tagger_overview.csv")
    overview = tagger_overview(dataset.tagged, dataset.taggers)
    pd.testing.assert_frame_equal(overview, golden, check_dtype=False)
