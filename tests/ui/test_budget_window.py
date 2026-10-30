import pandas as pd
import pyqtgraph as pg
import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.domain.budget import BudgetReport, GroupReport
from mymoneyvisualizer.ui.budget_window import group_html, summary_html


@pytest.fixture
def window(main):
    main.show_budget()
    return main.budget_window


def _items(widget):
    return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]


def _curve(plot, name):
    return next(item for item in plot.plot.listDataItems() if item.name() == name)


def test_renders_plots_and_reports(window):
    """Regression: drawing crashed with pyqtgraph 0.14 / pandas 3 (series with a date index)."""
    needs = window.plots["needs"]
    assert {c.name() for c in needs.plot.listDataItems() if c.name()} == {"target", "household", "car"}
    assert any(isinstance(i, pg.FillBetweenItem) for i in needs.plot.getPlotItem().items)
    text = needs.report_view.toPlainText()
    assert "Needs, per month" in text
    assert "Target:50 % = 1.500 €" in text.replace("\n", "")
    assert "Actual:35 % = 1.060 €" in text.replace("\n", "")  # rent 900, food 100, fuel 60
    assert "household:1.000 €" in text.replace("\n", "")
    savings = window.plots["savings"]
    assert {c.name() for c in savings.plot.listDataItems() if c.name()} == {"target", "saved"}


def test_summary_answers_whether_too_much_or_too_little_is_spent(window):
    """2023: income 36,000 €, needs 12,720 €, wants -20 € (carsharing 180 € minus the uncategorized 200 € that came
    in on the savings account), so 65 % are saved instead of 20 %: (23,300 € - 7,200 €) / 12 more per month."""
    text = window.summary_label.text()
    assert "savings rate <b>65 %</b> (target 20 %)" in text
    assert "1.342 € more per month" in text


def test_category_lists(window):
    assert _items(window.lists["income"]) == ["income"]
    assert _items(window.lists["needs"]) == ["household", "car"]
    assert _items(window.lists["wants"]) == ["carsharing", ""]
    assert _items(window.lists["savings"]) == []
    assert window.lists["wants"].item(1).text() == "(uncategorized)"


def test_moving_a_category_changes_its_group(window, model, qtbot):
    item = window.lists["wants"].takeItem(0)
    window.lists["needs"].addItem(item)
    qtbot.waitUntil(lambda: {a.category: a.group for a in model.groups}["carsharing"] == "needs")
    assert _items(window.lists["needs"]) == ["household", "car", "carsharing"]
    names = {item.name() for item in window.plots["needs"].plot.listDataItems() if item.name()}
    assert "carsharing" in names


def test_budget_settings(window, model):
    window.plots["wants"].share_spin.setValue(40)
    assert model.settings.budget_shares["wants"] == 0.4
    assert window.plots["savings"].share_label.text() == "10 % of income (the rest)"
    window.end_combo.setCurrentText("2024")
    assert (model.settings.budget_start, model.settings.budget_end) == (2023, 2024)
    assert "2023-2024 (13 of 24 months" in window.summary_label.text()
    window.start_combo.setCurrentText(str(pd.Timestamp.today().year + 1))
    settings = model.settings
    assert settings.budget_start <= settings.budget_end


def test_twelve_month_average(window):
    """January 2024 has no income; the moving average still shows 11 of the last 12 salaries."""
    needs = window.plots["needs"]
    assert _curve(needs, "target").yData[-1] == pytest.approx(0.5 * 11 * 3000 / 12)
    window.smooth_check.setChecked(False)
    assert _curve(needs, "target").yData[-1] == 0.0


def test_empty_data(qtbot, tmp_path):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    main = MainWindow(AppModel.open(tmp_path / "empty"))
    qtbot.addWidget(main)
    main.show_budget()
    window = main.budget_window
    assert window.plots["needs"].report_view.toPlainText() == ""
    assert window.summary_label.text() == "No transactions in the budget period."
    assert window.lists["needs"].count() == 0


def _report(**changes):
    values = {
        "start_year": 2024,
        "end_year": 2024,
        "months": 6,
        "period_months": 12,
        "last_date": pd.Timestamp("2024-06-20"),
        "income": 18000.0,
        "needs": GroupReport("needs", 0.5, 9600.0, [("household", 9000.0), ("", 600.0)]),
        "wants": GroupReport("wants", 0.3, 3600.0, [("hobby", 3600.0)]),
        "savings": GroupReport("savings", 0.2, 3000.0, [("depot", 3000.0)]),
    }
    values.update(changes)
    return BudgetReport(**values)


def test_summary_html():
    text = summary_html(_report())
    assert "2024 (6 of 12 months, until 20.06.2024)" in text
    assert "income 3.000 € per month" in text
    assert "savings rate <b>27 %</b> (target 20 %)" in text
    assert "<b>200 € more per month</b>" in text


def test_summary_html_when_too_little_is_saved():
    report = _report(wants=GroupReport("wants", 0.3, 6600.0, []), months=12, period_months=12)
    text = summary_html(report)
    assert "savings rate <b>10 %</b>" in text
    assert "spend <b>150 € less per month</b>" in text
    assert "until" not in text  # complete period


def test_summary_html_without_income_or_data():
    assert "no income" in summary_html(_report(income=0.0))
    assert summary_html(None) == summary_html(_report(months=0)) == "No transactions in the budget period."


def test_group_html():
    needs = group_html(_report(), "needs")
    assert "Target:</td><td align='right'>50 % = 1.500 €" in needs
    assert "Actual:</b></td><td align='right'><b>53 % = 1.600 €" in needs
    assert "(uncategorized):</td><td align='right'>100 €" in needs
    savings = group_html(_report(), "savings")
    assert "Saved:</b></td><td align='right'><b>27 % = 800 €" in savings
    assert "depot:</td><td align='right'>500 €" in savings
    assert "kept on the accounts" in savings
    assert group_html(None, "needs") == ""
