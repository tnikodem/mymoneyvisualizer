import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.domain.analysis import SUMMARY, TOTAL
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.ui.common import LESS_EXPENSE, MORE_EXPENSE, TOTAL_BACKGROUND
from mymoneyvisualizer.ui.income_expenses_window import default_months


@pytest.fixture
def window(main):
    main.show_income_expenses()
    window = main.income_expenses_window
    window.set_months("2023-07", "2024-01")
    return window


def _categories(window):
    frame = window.table_model.frame
    return set(frame.loc[frame[SUMMARY] == "", Col.category])


def _cell(window, category, month, role=Qt.ItemDataRole.DisplayRole):
    frame = window.table_model.frame
    row = frame.index[frame[Col.category] == category][0]
    column = [c.key for c in window.table_model.columns].index(month)
    return window.table_model.data(window.table_model.index(row, column), role)


def test_default_months():
    """The last twelve complete months up to the last transaction: the current month is not over yet."""
    today = pd.Timestamp("2024-03-15")
    assert default_months(pd.Timestamp("2024-03-10"), today) == ("2023-03", "2024-02")
    assert default_months(pd.Timestamp("2023-06-30"), today) == ("2022-07", "2023-06")
    assert default_months(None, today) == ("2023-03", "2024-02")


def test_period_presets(window):
    """The data ends in January 2024."""
    combo = window.period_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Letzte 12 Monate",
        "2024",
        "2023",
        "Eigener Zeitraum",
    ]
    assert combo.currentData() == "custom"  # the fixture chose July 2023 to January 2024
    combo.setCurrentIndex(combo.findData("2023"))
    assert window.months == ("2023-01", "2023-12")
    combo.setCurrentIndex(combo.findData("last 12"))
    assert window.months == ("2023-02", "2024-01")
    assert window.start_combo.currentText() == "Feb 2023"
    window.set_months("2023-05", "2023-06")
    assert combo.currentData() == "custom"


def test_table_shows_monthly_sums(window, model):
    frame = window.table_model.frame.set_index(Col.category)
    assert list(frame.columns[:2]) == ["2023-07", "2023-08"]
    assert frame.loc["household", "2023-07"] == -1000.0
    assert frame.loc["household", "2024-01"] == -450.0
    assert "spar" not in frame.index  # internal transfers hidden
    assert list(frame.index[-3:]) == ["Einnahmen", "Ausgaben", "Saldo"]
    assert frame.loc["Einnahmen", "2023-07"] == 3000.0
    assert frame.loc["Ausgaben", "2023-07"] == -1075.0
    assert frame.loc["Saldo", "2023-07"] == 1925.0
    assert window.table_model.headerData(1, Qt.Orientation.Horizontal) == "Jul 2023"
    assert set(window.table_model.frame["label"]) >= {"(ohne Kategorie)", "Saldo"}
    assert _cell(window, "household", "2023-07") == "-1.000"


def test_start_after_end_moves_end(window):
    """Regression: choosing a start month after the end month produced an empty table."""
    window.start_combo.setCurrentIndex(window.start_combo.findData("2024-01"))
    assert window.months == ("2024-01", "2024-01")
    assert not window.table_model.frame.empty
    window.end_combo.setCurrentIndex(window.end_combo.findData("2023-11"))
    assert window.months == ("2023-11", "2023-11")
    assert list(window.table_model.frame.columns[1:2]) == ["2023-11"]


def test_controls_change_settings_and_table(window, model):
    window.internal_transfers_check.setChecked(False)
    assert model.settings.hide_internal_transfers is False
    assert "spar" in _categories(window)

    window.exclude_select.set_selected(["household.rent"])
    assert model.settings.excluded_categories == ["household.rent"]
    assert _cell(window, "household", "2023-07") == "-100"

    window.level_combo.setCurrentIndex(1)
    assert "household.food" in _categories(window)
    window.filter_edit.setText("car")
    assert _categories(window) == {"car.fuel", "carsharing"}


def test_excluded_categories_shared_with_budget(main, window, model):
    main.show_budget()
    main.budget_window.exclude_select.set_selected(["car.fuel"])
    assert window.exclude_select.selected() == ["car.fuel"]


def test_unusual_month_is_highlighted(window):
    assert _cell(window, "household", "2024-01", Qt.ItemDataRole.BackgroundRole) == LESS_EXPENSE
    assert "-450" not in _cell(window, "household", "2024-01", Qt.ItemDataRole.ToolTipRole)
    assert _cell(window, "household", "2023-08", Qt.ItemDataRole.BackgroundRole) is None
    assert _cell(window, "Saldo", "2023-08", Qt.ItemDataRole.BackgroundRole) == TOTAL_BACKGROUND
    assert _cell(window, "household", TOTAL, Qt.ItemDataRole.BackgroundRole) == TOTAL_BACKGROUND
    window.level_combo.setCurrentIndex(1)
    assert _cell(window, "household.food", "2024-01", Qt.ItemDataRole.BackgroundRole) == MORE_EXPENSE
    tooltip = _cell(window, "household.food", "2024-01", Qt.ItemDataRole.ToolTipRole)
    assert "-350 €" in tooltip and "-100 €" in tooltip
    window.deviation_check.setChecked(False)
    assert _cell(window, "household.food", "2024-01", Qt.ItemDataRole.BackgroundRole) is None
    # explained next to the check box, not in the help of the window
    assert "Median" in window.deviation_help.toolTip() and "Median" not in window.help_button.toolTip()


def test_summary_rows_stay_last_when_sorting(window):
    for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
        window.table.sortByColumn(1, order)
        assert list(window.table.displayed_frame()[SUMMARY].iloc[-3:]) == ["income", "expenses", "net"]


def test_empty_range(window):
    window.set_months("2020-01", "2020-02")
    assert window.table_model.frame.empty
    assert window.table_model.columnCount() == 0


def test_double_click_opens_detail(main, window):
    columns = [c.key for c in window.table_model.columns]
    frame = window.table.displayed_frame()
    car_row = frame.index[frame[Col.category] == "car"][0]
    window.table.doubleClicked.emit(window.table.model().index(car_row, columns.index("2023-07")))
    detail = main.detail_window
    assert detail.isVisible()
    # regression: carsharing was listed under car
    assert list(detail.table_model.frame[Col.category]) == ["car.fuel"]
    assert detail.windowTitle() == "car: Jul 2023"

    net_row = len(frame) - 1
    window.table.doubleClicked.emit(window.table.model().index(net_row, columns.index("2024-01")))
    assert list(detail.table_model.frame[Col.recipient]) == ["REWE", "Kiosk"]
    assert detail.label.text() == "alle Kategorien · Jan 2024"
    assert detail.summary_label.text() == "2 Buchungen · Summe -452,50 €"

    income_row = net_row - 2
    window.table.doubleClicked.emit(window.table.model().index(income_row, columns.index("2023-07")))
    assert list(detail.table_model.frame[Col.recipient]) == ["ACME GmbH"]
    assert detail.windowTitle() == "Einnahmen: Jul 2023"

    window.table.doubleClicked.emit(window.table.model().index(0, columns.index(TOTAL)))
    assert detail.month == "2023-07"  # unchanged


def test_detail_follows_changes_and_opens_rule(main, model, window):
    main.open_detail("2024-01", [""])
    detail = main.detail_window
    assert list(detail.table_model.frame[Col.recipient]) == ["Kiosk"]
    assert "(ohne Kategorie)" in detail.windowTitle()
    detail.table.doubleClicked.emit(detail.table.model().index(0, 2))
    assert main.rule_window.recipient_edit.text() == "Kiosk"
    main.rule_window.category_edit.setText("hobby")
    main.rule_window.accept()
    assert detail.table_model.frame.empty
