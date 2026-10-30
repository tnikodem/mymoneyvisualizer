"""Show pandas DataFrames in Qt views, fast enough for tens of thousands of rows."""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QWidget

SORT_ROLE = Qt.ItemDataRole.UserRole + 1

TEXT, TAG, DATE, MONEY, MONEY0, NUMBER = "text", "tag", "date", "money", "money0", "number"
NUMERIC = (MONEY, MONEY0, NUMBER)


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
    return str(value)  # an empty tag stays empty, so missing tags stand out


def sort_key(value: Any, kind: str) -> Any:
    if kind in NUMERIC:
        return -math.inf if _is_missing(value) else float(value)
    if kind == DATE:
        return 0 if _is_missing(value) else pd.Timestamp(value).value
    return "" if _is_missing(value) else str(value).lower()


def _sort_values(values: pd.Series, kind: str) -> pd.Series:
    """Vectorized sort keys of a column (same order as :func:`sort_key`)."""
    if kind in NUMERIC:
        return pd.to_numeric(values, errors="coerce").fillna(-math.inf)
    if kind == DATE:  # nanoseconds; a missing date (NaT) is the smallest integer
        dates = pd.to_datetime(values, errors="coerce").astype("datetime64[ns]").to_numpy()
        return pd.Series(dates.view("int64"), index=values.index)
    return values.astype(str).str.lower()


class DataFrameModel(QAbstractTableModel):
    """Read-only table model; ``background(row, key)`` and ``tooltip(row, key)`` may decorate cells.

    Sorting happens in the model with pandas (a sort proxy compares rows one by one in Python, which takes
    seconds for large tables) and is kept when the frame is replaced. Rows for which ``pinned(frame)`` is
    true stay at the bottom, e.g. a total row.
    """

    def __init__(
        self,
        columns: Sequence[Column],
        parent: QWidget | None = None,
        background: Callable[[int, str], QColor | None] | None = None,
        tooltip: Callable[[int, str], str | None] | None = None,
        pinned: Callable[[pd.DataFrame], np.ndarray] | None = None,
    ):
        super().__init__(parent)
        self.columns = list(columns)
        self.background = background
        self.tooltip = tooltip
        self.pinned = pinned
        self.sorting: tuple[str, Qt.SortOrder] | None = None
        self._frame = pd.DataFrame(columns=[c.key for c in self.columns])
        self._arrays: list[np.ndarray | None] = []

    @property
    def frame(self) -> pd.DataFrame:
        """The rows in display order."""
        return self._frame

    def set_frame(self, frame: pd.DataFrame | None, columns: Sequence[Column] | None = None) -> None:
        self.beginResetModel()
        if columns is not None:
            self.columns = list(columns)
        if frame is None:
            frame = pd.DataFrame(columns=[c.key for c in self.columns])
        self._set(frame.reset_index(drop=True))
        self.endResetModel()

    def _set(self, frame: pd.DataFrame) -> None:
        self._frame = self._sorted(frame)
        self._arrays = [self._frame[c.key].to_numpy() if c.key in self._frame else None for c in self.columns]

    def _sorted(self, frame: pd.DataFrame) -> pd.DataFrame:
        if self.sorting is not None and not frame.empty:
            key, order = self.sorting
            column = next((c for c in self.columns if c.key == key), None)
            if column is not None and key in frame:
                keys = _sort_values(frame[key], column.kind)
                frame = frame.iloc[np.argsort(keys.to_numpy(), kind="stable")]
                if order == Qt.SortOrder.DescendingOrder:
                    frame = frame.iloc[::-1]
        if self.pinned is not None and not frame.empty:
            pinned = np.asarray(self.pinned(frame), dtype=bool)
            if pinned.any():
                frame = pd.concat([frame.loc[~pinned], frame.loc[pinned]])
        return frame.reset_index(drop=True)

    def sort(self, column: int, order: Qt.SortOrder = Qt.SortOrder.AscendingOrder) -> None:
        if not 0 <= column < len(self.columns):
            return
        self.beginResetModel()
        self.sorting = (self.columns[column].key, order)
        self._set(self._frame)
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
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter) if column.kind in NUMERIC else None
        if role == Qt.ItemDataRole.BackgroundRole:
            return self.background(index.row(), column.key) if self.background is not None else None
        if role == Qt.ItemDataRole.ToolTipRole:
            return self.tooltip(index.row(), column.key) if self.tooltip is not None else None
        if role not in (Qt.ItemDataRole.DisplayRole, SORT_ROLE):
            return None
        array = self._arrays[index.column()]
        value = None if array is None else array[index.row()]
        return format_value(value, column.kind) if role == Qt.ItemDataRole.DisplayRole else sort_key(value, column.kind)


class DataFrameView(QTableView):
    """Sortable table view for a :class:`DataFrameModel`; view rows are model rows."""

    def __init__(self, model: DataFrameModel, parent: QWidget | None = None, pinned=None, sortable: bool = True):
        super().__init__(parent)
        self.source = model
        if pinned is not None:
            model.pinned = pinned
        self.setModel(model)
        # keep the order of the data frame until the user clicks a header (default would be column 0)
        self.horizontalHeader().setSortIndicator(-1, Qt.SortOrder.AscendingOrder)
        self.setSortingEnabled(sortable)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        model.modelReset.connect(self.apply_columns)
        self.apply_columns()

    def apply_columns(self) -> None:
        for i, column in enumerate(self.source.columns):
            self.setColumnHidden(i, column.hidden)
            if column.width is not None:
                self.setColumnWidth(i, column.width)

    def row_at(self, view_row: int) -> dict[str, Any]:
        return self.source.row(view_row)

    def selected_rows(self) -> list[dict[str, Any]]:
        rows = {i.row() for i in self.selectionModel().selectedRows()}
        return [self.source.row(r) for r in sorted(rows)]

    def displayed_frame(self) -> pd.DataFrame:
        """Rows in the current (sorted) display order; used by tests and exports."""
        return self.source.frame
