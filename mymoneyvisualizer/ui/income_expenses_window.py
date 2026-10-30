"""Income & expenses: monthly sums per category, unusual months highlighted, and the transactions behind a cell."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from mymoneyvisualizer.app import ACCOUNTS, RULES, SETTINGS, TRANSACTIONS
from mymoneyvisualizer.domain.analysis import MONTHLY_AVERAGE, TOTAL, month_key, ordered_month_range
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.ui.common import LESS_EXPENSE, MORE_EXPENSE, TOTAL_BACKGROUND, CategorySelect, Window
from mymoneyvisualizer.ui.table_model import (
    CATEGORY,
    DATE,
    MONEY,
    MONEY0,
    Column,
    DataFrameModel,
    DataFrameView,
    format_money,
)

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

CATEGORY_LEVELS = ("Main category", "Subcategory", "Level 3", "Level 4")
MONTHS_SHOWN = 12 * 12
DETAIL_COLUMNS = [
    Column(Col.transaction_id, "id", hidden=True),
    Column(Col.account, "account", width=110),
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=260),
    Column(Col.description, "description", width=560),
    Column(Col.value, "value", MONEY, 90),
    Column(Col.category, "category", CATEGORY, 160),
]


def default_months(today: pd.Timestamp | None = None) -> tuple[str, str]:
    """The last twelve complete months."""
    current = pd.Period(today or pd.Timestamp.today(), freq="M")
    return month_key(current - 12), month_key(current - 1)


class IncomeExpensesWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS, ACCOUNTS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Income & Expenses")
        self.resize(1700, 800)
        self.deviation = pd.DataFrame()
        self.baseline = pd.DataFrame()

        current = pd.Period(pd.Timestamp.today(), freq="M")
        months = [month_key(current - i) for i in range(MONTHS_SHOWN)]
        self.start_combo, self.end_combo = QComboBox(self), QComboBox(self)
        for combo in (self.start_combo, self.end_combo):
            combo.addItems(months)
        start, end = default_months()
        self.start_combo.setCurrentText(start)
        self.end_combo.setCurrentText(end)
        self.exclude_select = CategorySelect("Exclude:", self)
        self.exclude_select.setMinimumWidth(250)
        self.internal_transfers_check = QCheckBox("Hide internal transfers", self)
        self.level_combo = QComboBox(self)
        self.level_combo.addItems(CATEGORY_LEVELS)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("category prefix")
        self.deviation_check = QCheckBox("Highlight unusual months", self)
        self.deviation_check.setChecked(True)

        # two rows, so the window also fits on small screens
        selection, display = QHBoxLayout(), QHBoxLayout()
        for widget in (
            QLabel("From:", self),
            self.start_combo,
            QLabel("to:", self),
            self.end_combo,
            QLabel("Level:", self),
            self.level_combo,
            QLabel("Filter:", self),
            self.filter_edit,
        ):
            selection.addWidget(widget)
        for widget in (self.exclude_select, self.internal_transfers_check, self.deviation_check):
            display.addWidget(widget)
        selection.addStretch(1)
        display.addStretch(1)

        self.table_model = DataFrameModel([], self, background=self._background, tooltip=self._tooltip)
        self.table = DataFrameView(
            self.table_model, self, pinned=lambda frame: (frame[Col.category] == TOTAL).to_numpy()
        )
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(selection)
        layout.addLayout(display)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self.start_combo.currentTextChanged.connect(lambda _: self._months_changed("start"))
        self.end_combo.currentTextChanged.connect(lambda _: self._months_changed("end"))
        self.exclude_select.selection_changed.connect(
            lambda categories: model.update_settings(excluded_categories=categories)
        )
        self.internal_transfers_check.toggled.connect(lambda hide: model.update_settings(hide_internal_transfers=hide))
        self.level_combo.currentIndexChanged.connect(self.refresh)
        self.filter_edit.textChanged.connect(self.refresh)
        self.deviation_check.toggled.connect(self.refresh)
        self.table.doubleClicked.connect(self.open_detail)

    @property
    def months(self) -> tuple[str, str]:
        return self.start_combo.currentText(), self.end_combo.currentText()

    def set_months(self, start: str, end: str) -> None:
        self.start_combo.setCurrentText(start)
        self.end_combo.setCurrentText(end)

    def _months_changed(self, changed: str) -> None:
        start, end = ordered_month_range(*self.months, changed)
        for combo, value in ((self.start_combo, start), (self.end_combo, end)):
            combo.blockSignals(True)
            combo.setCurrentText(value)
            combo.blockSignals(False)
        self.refresh()

    @property
    def level(self) -> int:
        return self.level_combo.currentIndex()

    def refresh(self, *_args) -> None:
        super().refresh()
        settings = self.model.settings
        self.exclude_select.set_options(self.model.unique_categories(), settings.excluded_categories)
        self.internal_transfers_check.blockSignals(True)
        self.internal_transfers_check.setChecked(settings.hide_internal_transfers)
        self.internal_transfers_check.blockSignals(False)

        start, end = self.months
        options = {"level": self.level, "category_filter": self.filter_edit.text()}
        table = self.model.income_expenses(start, end, **options)
        if table is not None and self.deviation_check.isChecked():
            self.deviation, self.baseline = self.model.income_expenses_deviations(start, end, **options)
        else:
            self.deviation, self.baseline = pd.DataFrame(), pd.DataFrame()
        columns = (
            []
            if table is None
            else [
                Column(Col.category, "category", CATEGORY, 180),
                *[Column(c, c, MONEY0, 80) for c in table.columns if c not in (Col.category, TOTAL, MONTHLY_AVERAGE)],
                Column(TOTAL, TOTAL, MONEY0, 90),
                Column(MONTHLY_AVERAGE, MONTHLY_AVERAGE, MONEY0, 110),
            ]
        )
        self.table_model.set_frame(table, columns)

    # ------------------------------------------------------------------ cell decoration
    def _is_total_row(self, row: int) -> bool:
        frame = self.table_model.frame
        return not frame.empty and frame[Col.category].iat[row] == TOTAL

    def _deviation(self, row: int, key: str) -> float | None:
        category = self.table_model.frame[Col.category].iat[row]
        if category not in self.deviation.index or key not in self.deviation.columns:
            return None
        value = self.deviation.at[category, key]
        return None if np.isnan(value) else float(value)

    def _background(self, row: int, key: str):
        if self._is_total_row(row) or key in (TOTAL, MONTHLY_AVERAGE):
            return TOTAL_BACKGROUND
        deviation = self._deviation(row, key)
        if deviation is None:
            return None
        return MORE_EXPENSE if deviation < 0 else LESS_EXPENSE

    def _tooltip(self, row: int, key: str) -> str | None:
        deviation = self._deviation(row, key)
        if deviation is None:
            return None
        category = self.table_model.frame[Col.category].iat[row]
        baseline = self.baseline.at[category, key]
        return (
            f"{display_category(category)} {key}: {format_money(deviation, 0)} € compared to the median of the "
            f"previous 12 months ({format_money(baseline, 0)} €)"
        )

    # ------------------------------------------------------------------ detail
    def open_detail(self, index) -> None:
        key = self.table_model.columns[index.column()].key
        if key in (Col.category, TOTAL, MONTHLY_AVERAGE):
            return
        category = self.table.row_at(index.row())[Col.category]
        self.navigator.open_detail(key, None if category == TOTAL else category, self.filter_edit.text())


class DetailWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.resize(1400, 800)
        self.month: str | None = None
        self.category: str | None = None
        self.category_filter = ""
        self.label = QLabel(self)
        self.table_model = DataFrameModel(DETAIL_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addWidget(self.label)
        layout.addWidget(self.table)
        self.setCentralWidget(central)
        self.table.doubleClicked.connect(self.open_rule)

    def open_detail(self, month: str, category: str | None, category_filter: str = "") -> None:
        self.month, self.category, self.category_filter = month, category, category_filter
        what = "all categories" if category is None else display_category(category)
        self.setWindowTitle(f"{what} in {month}")
        self.label.setText(f"All transactions in {month} for {what}:")
        self.refresh()
        self.show()
        self.raise_()

    def refresh(self) -> None:
        super().refresh()
        if self.month is not None:
            self.table_model.set_frame(
                self.model.detail(self.month, self.category, category_filter=self.category_filter)
            )

    def open_rule(self, index) -> None:
        self.navigator.open_rule(transaction_id=self.table.row_at(index.row())[Col.transaction_id])
