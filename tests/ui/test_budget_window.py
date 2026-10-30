import pandas as pd
import pyqtgraph as pg
import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.domain.budget import BudgetReport
from mymoneyvisualizer.ui.budget_window import budget_html


@pytest.fixture
def window(main):
    main.show_budget()
    return main.budget_window


def _items(widget):
    return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]


def test_renders_plots_and_reports(window):
    """Regression: drawing crashed with pyqtgraph 0.14 / pandas 3 (series with a date index)."""
    needs = window.plots["needs"]
    curves = [item for item in needs.plot.listDataItems() if item.name()]
    assert {c.name() for c in curves} == {"budget", "household", "car"}
    assert any(isinstance(i, pg.FillBetweenItem) for i in needs.plot.getPlotItem().items)
    text = needs.report_view.toPlainText()
    assert "Needs budget 2023" in text
    assert "household:" in text
    assert "covered days: 365/365 (100%)" in text


def test_category_lists(window):
    assert _items(window.lists["income"]) == ["income"]
    assert _items(window.lists["needs"]) == ["household", "car"]
    assert _items(window.lists["wants"]) == ["carsharing", ""]
    assert window.lists["wants"].item(1).text() == "(uncategorized)"


def test_moving_a_category_changes_its_category(window, model, qtbot):
    item = window.lists["wants"].takeItem(0)
    window.lists["needs"].addItem(item)
    qtbot.waitUntil(lambda: {a.category: a.group for a in model.groups}["carsharing"] == "needs")
    assert _items(window.lists["needs"]) == ["household", "car", "carsharing"]
    names = {item.name() for item in window.plots["needs"].plot.listDataItems() if item.name()}
    assert "carsharing" in names


def test_budget_settings(window, model):
    window.plots["wants"].share_spin.setValue(40)
    assert model.settings.budget_shares["wants"] == 0.4
    window.end_combo.setCurrentText("2024")
    assert (model.settings.budget_start, model.settings.budget_end) == (2023, 2024)
    assert "Needs budget 2023-2024" in window.plots["needs"].report_view.toPlainText()
    window.start_combo.setCurrentText(str(pd.Timestamp.today().year + 1))
    settings = model.settings
    assert settings.budget_start <= settings.budget_end


def test_empty_data(qtbot, tmp_path):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    main = MainWindow(AppModel.open(tmp_path / "empty"))
    qtbot.addWidget(main)
    main.show_budget()
    assert main.budget_window.plots["needs"].report_view.toPlainText() == ""
    assert main.budget_window.lists["needs"].count() == 0


def _report(**changes):
    values = {
        "group": "needs",
        "start_year": 2024,
        "end_year": 2024,
        "share": 0.3,
        "expected_total": 3600.0,
        "consumed": [("household", 2400.0), ("", 60.0)],
        "total_consumed": 2460.0,
        "total_days": 366,
        "covered_days": 183,
        "last_recorded_date": pd.Timestamp("2024-07-01"),
    }
    values.update(changes)
    return BudgetReport(**values)


def test_budget_html_running_period():
    text = budget_html(_report())
    assert "Expected budget" in text
    assert "(uncategorized):" in text
    assert "Remaining per month:" in text
    assert "Trend end of period:" in text
    assert "1.140 €" in text  # balance
    assert "last transaction: 01.07.2024" in text


def test_budget_html_complete_period():
    text = budget_html(_report(start_year=2023, covered_days=731, total_days=731))
    assert "budget 2023-2024" in text
    assert "<b>Total:</b>" in text
    assert "Difference:" in text
    assert "Remaining per month" not in text


def test_budget_html_without_coverage():
    text = budget_html(_report(covered_days=0))
    assert "Trend" not in text
