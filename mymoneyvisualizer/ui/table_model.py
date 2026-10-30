"""Show pandas DataFrames in Qt views."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

from mymoneyvisualizer.domain.tags import display_tag

SORT_ROLE = Qt.ItemDataRole.UserRole + 1

TEXT, TAG, DATE, MONEY, MONEY0, NUMBER = "text", "tag", "date", "money", "money0", "number"


@dataclass(frozen=True)
class Column:
    key: str
    title: str
    kind: str = TEXT
    width: int | None = None
    hidden: bool = False


def _is_missing(value: Any) -> bool:
    return value is None or value is pd.NaT or (isinstance(value, float) and math.isnan(value))


def format_money(value: float, decimals: int = 2) -> str:
    """German number format: ``-1.234,56``."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def format_value(value: Any, kind: str) -> str:
    if _is_missing(value):
        return ""
    if kind == DATE:
        return pd.Timestamp(value).strftime("%d.%m.%Y")
    if kind == MONEY:
        return format_money(float(value))
    if kind == MONEY0:
        return format_money(float(value), 0)
    if kind == NUMBER:
        number = float(value)
        return str(int(number)) if number.is_integer() else str(number)
    if kind == TAG:
        return display_tag(str(value))
    return str(value)


def sort_key(value: Any, kind: str) -> Any:
    if kind in (MONEY, MONEY0, NUMBER):
        return -math.inf if _is_missing(value) else float(value)
    if kind == DATE:
        return 0 if _is_missing(value) else pd.Timestamp(value).value
    return "" if _is_missing(value) else str(value).lower()


class DataFrameModel(QAbstractTableModel):
    """Read-only table model; ``background(row, key)`` and ``tooltip(row, key)`` may decorate cells."""

    def __init__(
        self,
        columns: Sequence[Column],
        parent: QWidget | None = None,
        background: Callable[[int, str], QColor | None] | None = None,
        tooltip: Callable[[int, str], str | None] | None = None,
    ):
        super().__init__(parent)
        self.columns = list(columns)
        self.background = background
        self.tooltip = tooltip
        self._frame = pd.DataFrame(columns=[c.key for c in self.columns])

    @property
    def frame(self) -> pd.DataFrame:
        return self._frame

    def set_frame(self, frame: pd.DataFrame | None, columns: Sequence[Column] | None = None) -> None:
        self.beginResetModel()
        if columns is not None:
            self.columns = list(columns)
        if frame is None:
            frame = pd.DataFrame(columns=[c.key for c in self.columns])
        self._frame = frame.reset_index(drop=True)
        self.endResetModel()

    def row(self, row: int) -> dict[str, Any]:
        return self._frame.iloc[row].to_dict()

    def rowCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        return 0 if parent is not None and parent.isValid() else len(self._frame)

    def columnCount(self, parent: QModelIndex | None = None) -> int:  # noqa: N802 (Qt API)
        return 0 if parent is not None and parent.isValid() else len(self.columns)

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):  # noqa: N802 (Qt API)
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section].title
        return None

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        column = self.columns[index.column()]
        value = (
            self._frame.iat[index.row(), self._frame.columns.get_loc(column.key)] if column.key in self._frame else None
        )
        if role == Qt.ItemDataRole.DisplayRole:
            return format_value(value, column.kind)
        if role == SORT_ROLE:
            return sort_key(value, column.kind)
        if role == Qt.ItemDataRole.TextAlignmentRole and column.kind in (MONEY, MONEY0, NUMBER):
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.BackgroundRole and self.background is not None:
            return self.background(index.row(), column.key)
        if role == Qt.ItemDataRole.ToolTipRole and self.tooltip is not None:
            return self.tooltip(index.row(), column.key)
        return None


class SortProxy(QSortFilterProxyModel):
    """Sorts by :data:`SORT_ROLE`; rows for which ``pinned(source_row)`` is true always stay at the bottom."""

    def __init__(self, parent: QWidget | None = None, pinned: Callable[[int], bool] | None = None):
        super().__init__(parent)
        self.pinned = pinned
        self.setSortRole(SORT_ROLE)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:  # noqa: N802 (Qt API)
        if self.pinned is not None:
            left_pinned, right_pinned = self.pinned(left.row()), self.pinned(right.row())
            if left_pinned != right_pinned:
                # Qt inverts the comparison for descending order
                return right_pinned if self.sortOrder() == Qt.SortOrder.AscendingOrder else left_pinned
        return left.data(SORT_ROLE) < right.data(SORT_ROLE)


class DataFrameView(QTableView):
    """Sortable table view for a :class:`DataFrameModel`."""

    def __init__(self, model: DataFrameModel, parent: QWidget | None = None, pinned=None, sortable: bool = True):
        super().__init__(parent)
        self.source = model
        self.proxy = SortProxy(self, pinned)
        self.proxy.setSourceModel(model)
        self.setModel(self.proxy)
        # keep the order of the data frame until the user clicks a header (default would be column 0)
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(sortable)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        model.modelReset.connect(self.apply_columns)
        self.apply_columns()

    def apply_columns(self) -> None:
        for i, column in enumerate(self.source.columns):
            self.setColumnHidden(i, column.hidden)
            if column.width is not None:
                self.setColumnWidth(i, column.width)

    def source_row(self, index: QModelIndex) -> int:
        return self.proxy.mapToSource(index).row()

    def row_at(self, view_row: int) -> dict[str, Any]:
        return self.source.row(self.proxy.mapToSource(self.proxy.index(view_row, 0)).row())

    def selected_rows(self) -> list[dict[str, Any]]:
        rows = {self.source_row(i) for i in self.selectionModel().selectedRows()}
        return [self.source.row(r) for r in sorted(rows)]

    def displayed_frame(self) -> pd.DataFrame:
        """Rows in the current (sorted) display order; used by tests and exports."""
        rows = [self.proxy.mapToSource(self.proxy.index(r, 0)).row() for r in range(self.proxy.rowCount())]
        return self.source.frame.iloc[rows].reset_index(drop=True)
