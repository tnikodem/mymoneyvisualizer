import pandas as pd
import pyqtgraph as pg
import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.domain.budget import BudgetReport
from mymoneyvisualizer.ui.graph_window import budget_html


@pytest.fixture
def window(main):
    main.show_graph()
    return main.graph_window


def _items(widget):
    return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]


def test_renders_plots_and_reports(window):
    """Regression: drawing crashed with pyqtgraph 0.14 / pandas 3 (series with a date index)."""
    basic = window.plots["basic"]
    curves = [item for item in basic.plot.listDataItems() if item.name()]
    assert {c.name() for c in curves} == {"budget", "household", "car"}
    assert any(isinstance(i, pg.FillBetweenItem) for i in basic.plot.getPlotItem().items)
    text = basic.report_view.toPlainText()
    assert "Basic budget 2023" in text
    assert "household:" in text
    assert "covered days: 365/365 (100%)" in text


def test_category_lists(window):
    assert _items(window.lists["income"]) == ["income"]
    assert _items(window.lists["basic"]) == ["household", "car"]
    assert _items(window.lists["optional"]) == ["carsharing", ""]
    assert window.lists["optional"].item(1).text() == "unassigned"


def test_moving_a_tag_changes_its_category(window, model, qtbot):
    item = window.lists["optional"].takeItem(0)
    window.lists["basic"].addItem(item)
    qtbot.waitUntil(lambda: {c.name: c.category for c in model.categories}["carsharing"] == "basic")
    assert _items(window.lists["basic"]) == ["household", "car", "carsharing"]
    names = {item.name() for item in window.plots["basic"].plot.listDataItems() if item.name()}
    assert "carsharing" in names


def test_budget_settings(window, model):
    window.plots["optional"].factor_spin.setValue(40)
    assert model.settings.budget_factors["optional"] == 0.4
    window.end_combo.setCurrentText("2024")
    assert (model.settings.budget_start, model.settings.budget_end) == (2023, 2024)
    assert "Basic budget 2023-2024" in window.plots["basic"].report_view.toPlainText()
    window.start_combo.setCurrentText(str(pd.Timestamp.today().year + 1))
    settings = model.settings
    assert settings.budget_start <= settings.budget_end


def test_empty_data(qtbot, tmp_path):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    main = MainWindow(AppModel.open(tmp_path / "empty"))
    qtbot.addWidget(main)
    main.show_graph()
    assert main.graph_window.plots["basic"].report_view.toPlainText() == ""
    assert main.graph_window.lists["basic"].count() == 0


def _report(**changes):
    values = {
        "category": "basic",
        "start_year": 2024,
        "end_year": 2024,
        "factor": 0.3,
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
    assert "unassigned:" in text
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
