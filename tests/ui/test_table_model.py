import math

import pandas as pd
import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from mymoneyvisualizer.ui.table_model import (
    DATE,
    MONEY,
    MONEY0,
    NUMBER,
    SORT_ROLE,
    TAG,
    TEXT,
    Column,
    DataFrameModel,
    DataFrameView,
    format_money,
    format_value,
    sort_key,
)


@pytest.mark.parametrize(
    ("value", "kind", "expected"),
    [
        (-1234.567, MONEY, "-1.234,57"),
        (1234.5, MONEY0, "1.234"),
        (2.0, NUMBER, "2"),
        (2.5, NUMBER, "2.5"),
        (math.nan, NUMBER, ""),
        (None, TEXT, ""),
        (pd.NaT, DATE, ""),
        (pd.Timestamp("2024-03-01"), DATE, "01.03.2024"),
        ("", TAG, "unassigned"),
        ("food", TAG, "food"),
        (5, TEXT, "5"),
    ],
)
def test_format_value(value, kind, expected):
    assert format_value(value, kind) == expected


def test_format_money_decimals():
    assert format_money(1000000, 0) == "1.000.000"


def test_sort_keys():
    assert sort_key(math.nan, MONEY) == -math.inf
    assert sort_key(3, NUMBER) == 3.0
    assert sort_key(pd.Timestamp("2024-01-01"), DATE) > sort_key(pd.Timestamp("2023-01-01"), DATE)
    assert sort_key(None, DATE) == 0
    assert sort_key("B", TEXT) == "b"
    assert sort_key(None, TEXT) == ""


COLUMNS = [Column("name", "Name", width=50), Column("value", "Value", MONEY), Column("hidden", "h", hidden=True)]


def _frame():
    return pd.DataFrame({"name": ["b", "a", "total", "c"], "value": [2.0, 10.0, 0.0, -5.0], "hidden": [1, 2, 3, 4]})


def test_model_roles(qtbot):
    model = DataFrameModel(
        COLUMNS,
        background=lambda row, key: QColor("red") if key == "value" else None,
        tooltip=lambda row, key: f"{row}:{key}",
    )
    model.set_frame(_frame())
    assert (model.rowCount(), model.columnCount()) == (4, 3)
    index = model.index(1, 1)
    assert model.data(index) == "10,00"
    assert model.data(index, SORT_ROLE) == 10.0
    assert model.data(index, Qt.ItemDataRole.TextAlignmentRole) & Qt.AlignmentFlag.AlignRight
    assert model.data(index, Qt.ItemDataRole.BackgroundRole) == QColor("red")
    assert model.data(index, Qt.ItemDataRole.ToolTipRole) == "1:value"
    assert model.data(model.index(0, 0), Qt.ItemDataRole.TextAlignmentRole) is None
    assert model.data(model.index(0, 0), Qt.ItemDataRole.DecorationRole) is None
    assert model.data(model.index(9, 9)) is None
    assert model.headerData(1, Qt.Orientation.Horizontal) == "Value"
    assert model.headerData(1, Qt.Orientation.Vertical) is None
    assert model.row(3) == {"name": "c", "value": -5.0, "hidden": 4}
    assert model.rowCount(model.index(0, 0)) == 0 and model.columnCount(model.index(0, 0)) == 0


def test_model_missing_column_and_reset():
    model = DataFrameModel([Column("absent", "x")])
    model.set_frame(pd.DataFrame({"other": [1]}))
    assert model.data(model.index(0, 0)) == ""
    model.set_frame(None, columns=[Column("y", "y")])
    assert model.rowCount() == 0
    assert model.columns[0].key == "y"


@pytest.mark.parametrize("order", [Qt.SortOrder.AscendingOrder, Qt.SortOrder.DescendingOrder])
def test_view_sorting_keeps_pinned_rows_last(qtbot, order):
    model = DataFrameModel(COLUMNS)
    model.set_frame(_frame())
    view = DataFrameView(model, pinned=lambda row: model.frame["name"].iat[row] == "total")
    qtbot.addWidget(view)
    view.sortByColumn(1, order)
    names = list(view.displayed_frame()["name"])
    assert names[-1] == "total"
    expected = ["c", "b", "a"] if order == Qt.SortOrder.AscendingOrder else ["a", "b", "c"]
    assert names[:-1] == expected
    assert view.isColumnHidden(2)
    assert view.columnWidth(0) == 50
    assert view.row_at(0)["name"] == expected[0]


def test_view_keeps_frame_order_until_user_sorts(qtbot):
    """Regression: enabling sorting sorted by the (hidden) first column, e.g. random transaction ids."""
    model = DataFrameModel([Column("id", "id", hidden=True), Column("value", "Value", MONEY)])
    view = DataFrameView(model)
    qtbot.addWidget(view)
    model.set_frame(pd.DataFrame({"id": ["c", "a", "b"], "value": [3.0, 2.0, 1.0]}))
    assert list(view.displayed_frame()["id"]) == ["c", "a", "b"]


def test_view_selection(qtbot):
    model = DataFrameModel(COLUMNS)
    model.set_frame(_frame())
    view = DataFrameView(model, sortable=False)
    qtbot.addWidget(view)
    view.selectRow(1)
    assert [r["name"] for r in view.selected_rows()] == ["a"]
    assert view.source_row(view.proxy.index(3, 0)) == 3
