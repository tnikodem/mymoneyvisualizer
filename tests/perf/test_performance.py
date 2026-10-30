"""Time budgets on a large synthetic data set (~58,000 transactions, 700 rules, 400 manual categories).

Measured on a laptop the operations take a tenth of their budget or less; the budgets only catch
regressions like evaluating every rule on every row again (seconds per key press).
"""

import time

import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import ManualCategory, Rule
from mymoneyvisualizer.storage.repository import Repository

from .dataset import build_state


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    path = tmp_path_factory.mktemp("perf") / "data"
    Repository(path).save_all(build_state())
    return path


@pytest.fixture(scope="module")
def model(data_dir):
    return AppModel.open(data_dir)


class Budget:
    def __init__(self, seconds):
        self.seconds = seconds

    def __enter__(self):
        self.start = time.perf_counter()

    def __exit__(self, *exc):
        took = time.perf_counter() - self.start
        assert took < self.seconds, f"took {took:.2f} s, budget {self.seconds} s"


def test_data_set_is_large(model):
    assert len(model.transactions()) > 50_000
    assert len(model.rules) == 700


def test_startup(data_dir):
    with Budget(5.0):
        AppModel.open(data_dir).transactions()


def test_editing_rules(model):
    some = model.transactions().iloc[5000]
    existing = model.rules[100].id
    with Budget(1.5):  # 10 key presses in the rule window, new and existing rule
        for i in range(5):
            model.preview_rule(Rule(regex_recipient="REWE Markt 1"[: 4 + i]), None, some[Col.transaction_id])
            model.preview_rule(Rule(regex_description="SAGT DANKE"[: 3 + i]), existing)
    with Budget(1.5):
        saved = model.save_rule(Rule(category="perf.x", regex_recipient="Shell 12$"))
    with Budget(1.5):  # typed into the rules overview
        model.update_rule(saved.id, spread_months=12)
    with Budget(1.5):
        model.save_manual_category(ManualCategory(some[Col.transaction_id], "perf.once", spread_months=12))
    with Budget(1.5):
        model.delete_rules([saved.id])


def test_analysis(model):
    with Budget(2.0):
        model.income_expenses("2025-11", "2026-10", level=1)
        model.income_expenses_deviations("2025-11", "2026-10", level=1)
        series = model.budget_series()
        model.budget_report(series)
        model.rule_overview()
        model.detail("2026-03", "household")
        for name in model.account_names:
            model.account_transactions(name)


def test_windows(qtbot, model):
    from mymoneyvisualizer.ui.main_window import MainWindow

    main = MainWindow(model)
    qtbot.addWidget(main)
    with Budget(3.0):
        main.show_accounts()
        main.show_income_expenses()
        main.show_budget()
        main.show_rules()
    tab = main.accounts_window.tab("Girokonto")
    assert tab.table_model.rowCount() > 10_000
    with Budget(1.0):
        tab.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)
        tab.table.sortByColumn(2, Qt.SortOrder.AscendingOrder)
    some = model.transactions().iloc[2000]
    with Budget(2.0):
        main.open_rule(transaction_id=some[Col.transaction_id])
        for ch in "abcdefghij":
            main.rule_window.recipient_edit.setText(main.rule_window.recipient_edit.text()[:3] + ch)
            main.rule_window.flush()
    with Budget(2.0):
        main.rule_window.accept()
        for window in (main.accounts_window, main.income_expenses_window, main.budget_window, main.rules_window):
            window.flush()
    main.close()
