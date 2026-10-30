import pandas as pd
import pytest
from PyQt6.QtCore import Qt

from mymoneyvisualizer.domain.analysis import TOTAL
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.ui.common import LESS_EXPENSE, MORE_EXPENSE, TOTAL_BACKGROUND
from mymoneyvisualizer.ui.income_expenses_window import default_months


@pytest.fixture
def window(main):
    main.show_income_expenses()
    window = main.income_expenses_window
    window.set_months("2023-07", "2024-01")
    return window


def _cell(window, category, month, role=Qt.ItemDataRole.DisplayRole):
    frame = window.table_model.frame
    row = frame.index[frame[Col.category] == category][0]
    column = [c.key for c in window.table_model.columns].index(month)
    return window.table_model.data(window.table_model.index(row, column), role)


def test_default_months():
    assert default_months(pd.Timestamp("2024-03-15")) == ("2023-03", "2024-02")


def test_table_shows_monthly_sums(window, model):
    frame = window.table_model.frame.set_index(Col.category)
    assert list(frame.columns[:2]) == ["2023-07", "2023-08"]
    assert frame.loc["household", "2023-07"] == -1000.0
    assert frame.loc["household", "2024-01"] == -450.0
    assert "spar" not in frame.index  # transfers hidden
    assert frame.index[-1] == TOTAL
    assert _cell(window, "household", "2023-07") == "-1.000"


def test_start_after_end_moves_end(window):
    """Regression: choosing a start month after the end month produced an empty table."""
    window.start_combo.setCurrentText("2024-01")
    assert window.months == ("2024-01", "2024-01")
    assert not window.table_model.frame.empty
    window.end_combo.setCurrentText("2023-11")
    assert window.months == ("2023-11", "2023-11")
    assert list(window.table_model.frame.columns[1:2]) == ["2023-11"]


def test_controls_change_settings_and_table(window, model):
    window.internal_transfers_check.setChecked(False)
    assert model.settings.hide_internal_transfers is False
    assert "spar" in set(window.table_model.frame[Col.category])

    window.exclude_select.set_selected(["household.rent"])
    assert model.settings.excluded_categories == ["household.rent"]
    assert _cell(window, "household", "2023-07") == "-100"

    window.level_combo.setCurrentIndex(1)
    assert "household.food" in set(window.table_model.frame[Col.category])
    window.filter_edit.setText("car")
    assert set(window.table_model.frame[Col.category]) == {"car.fuel", "carsharing", TOTAL}


def test_excluded_categories_shared_with_budget(main, window, model):
    main.show_budget()
    main.budget_window.exclude_select.set_selected(["car.fuel"])
    assert window.exclude_select.selected() == ["car.fuel"]


def test_unusual_month_is_highlighted(window):
    assert _cell(window, "household", "2024-01", Qt.ItemDataRole.BackgroundRole) == LESS_EXPENSE
    assert "-450" not in _cell(window, "household", "2024-01", Qt.ItemDataRole.ToolTipRole)
    assert _cell(window, "household", "2023-08", Qt.ItemDataRole.BackgroundRole) is None
    assert _cell(window, TOTAL, "2023-08", Qt.ItemDataRole.BackgroundRole) == TOTAL_BACKGROUND
    assert _cell(window, "household", TOTAL, Qt.ItemDataRole.BackgroundRole) == TOTAL_BACKGROUND
    window.level_combo.setCurrentIndex(1)
    assert _cell(window, "household.food", "2024-01", Qt.ItemDataRole.BackgroundRole) == MORE_EXPENSE
    tooltip = _cell(window, "household.food", "2024-01", Qt.ItemDataRole.ToolTipRole)
    assert "-350 €" in tooltip and "-100 €" in tooltip
    window.deviation_check.setChecked(False)
    assert _cell(window, "household.food", "2024-01", Qt.ItemDataRole.BackgroundRole) is None


def test_total_row_stays_last_when_sorting(window):
    for order in (Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder):
        window.table.sortByColumn(1, order)
        assert window.table.displayed_frame()[Col.category].iloc[-1] == TOTAL


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
    assert "car in 2023-07" in detail.windowTitle()

    total_row = len(frame) - 1
    window.table.doubleClicked.emit(window.table.model().index(total_row, columns.index("2024-01")))
    assert list(detail.table_model.frame[Col.recipient]) == ["REWE", "Kiosk"]
    assert detail.label.text().startswith("All transactions in 2024-01 for all categories")

    window.table.doubleClicked.emit(window.table.model().index(0, columns.index(TOTAL)))
    assert detail.month == "2024-01"  # unchanged


def test_detail_follows_changes_and_opens_rule(main, model, window):
    main.open_detail("2024-01", "")
    detail = main.detail_window
    assert list(detail.table_model.frame[Col.recipient]) == ["Kiosk"]
    assert "(uncategorized)" in detail.windowTitle()
    detail.table.doubleClicked.emit(detail.table.model().index(0, 2))
    assert main.rule_window.recipient_edit.text() == "Kiosk"
    main.rule_window.category_edit.setText("hobby")
    main.rule_window.accept()
    assert detail.table_model.frame.empty
