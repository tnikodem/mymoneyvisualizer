"""Import a CSV export: detected format, column mapping and a preview of what will be added."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from pyqt6_multiselect_combobox import MultiSelectComboBox

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.importing.profile import MAPPING_FIELDS, ImportProfile
from mymoneyvisualizer.importing.reader import (
    ImportFormatError,
    ImportPreview,
    preview_import,
    propose_profile,
    read_table,
)
from mymoneyvisualizer.importing.sniff import MIXED_ENCODING
from mymoneyvisualizer.ui.common import Window
from mymoneyvisualizer.ui.table_model import DATE, MONEY, Column, DataFrameModel, DataFrameView

ENCODINGS = ("utf-8", "utf-8-sig", MIXED_ENCODING, "cp1252", "latin-1", "utf-16")
PREVIEW_COLUMNS = [
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=280),
    Column(Col.description, "description", width=560),
    Column(Col.value, "value", MONEY, 100),
]
MAPPING_LABELS = {
    "col_date": "Date",
    "col_recipient": "Recipient (optional)",
    "col_description": "Description (optional)",
    "col_value": "Value",
    "col_debit": "Debit amounts (optional)",
    "col_credit": "Credit amounts (optional)",
    "col_sign": "Debit/credit mark, e.g. S/H (optional)",
}


def _qdate(timestamp: pd.Timestamp) -> QDate:
    return QDate(timestamp.year, timestamp.month, timestamp.day)


class ImportWindow(Window):
    def __init__(self, model: AppModel, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.resize(1300, 850)
        self.path: Path | None = None
        self.account: str | None = None
        self.original_name: str | None = None
        self.preview: ImportPreview | None = None
        self._loading = False

        self.name_edit = QLineEdit(self)
        self.encoding_combo = QComboBox(self)
        self.encoding_combo.setEditable(True)
        self.encoding_combo.addItems(ENCODINGS)
        self.separator_edit = QLineEdit(self)
        self.decimal_edit = QLineEdit(self)
        self.thousands_edit = QLineEdit(self)
        for edit in (self.separator_edit, self.decimal_edit, self.thousands_edit):
            edit.setMaxLength(1)
            edit.setFixedWidth(40)
        self.header_spin = QSpinBox(self)
        self.header_spin.setRange(0, 10_000)
        self.dayfirst_check = QCheckBox("Day first", self)
        self.duplicates_check = QCheckBox("Drop duplicates", self)
        self.since_edit = QDateEdit(self)
        self.since_edit.setCalendarPopup(True)
        self.since_edit.setDisplayFormat("dd.MM.yyyy")
        self.column_combos = {f: QComboBox(self) for f in MAPPING_FIELDS}
        self.extra_combo = MultiSelectComboBox(self)
        self.extra_combo.setPlaceholderText("none")
        self.extra_combo.setMinimumWidth(160)

        self.name_edit.setFixedWidth(180)
        format_row, mapping_row, value_row = QHBoxLayout(), QHBoxLayout(), QHBoxLayout()
        for label, widget in (
            ("Profile", self.name_edit),
            ("Encoding", self.encoding_combo),
            ("Separator", self.separator_edit),
            ("Decimal", self.decimal_edit),
            ("Thousands", self.thousands_edit),
            ("Header line", self.header_spin),
            ("Import since", self.since_edit),
            ("", self.dayfirst_check),
            ("", self.duplicates_check),
        ):
            format_row.addLayout(self._labelled(label, widget))
        for field in MAPPING_FIELDS:
            self.column_combos[field].setMinimumWidth(160)
            row = mapping_row if field in ("col_date", "col_recipient", "col_description", "col_value") else value_row
            row.addLayout(self._labelled(MAPPING_LABELS[field], self.column_combos[field]))
        value_row.insertLayout(0, self._labelled("Add to value, e.g. fee/tax (optional)", self.extra_combo))
        for row in (format_row, mapping_row, value_row):
            row.addStretch(1)

        self.status_label = QLabel(self)
        self.error_label = QLabel(self)
        self.error_label.setStyleSheet("color: #b00020;")
        self.import_button = QPushButton("Import", self)
        self.cancel_button = QPushButton("Cancel", self)
        buttons = QHBoxLayout()
        buttons.addWidget(self.status_label, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.import_button)

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(format_row)
        layout.addLayout(mapping_row)
        layout.addLayout(value_row)
        layout.addWidget(self.error_label)
        layout.addLayout(buttons)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        for edit in (self.separator_edit, self.decimal_edit, self.thousands_edit):
            edit.textChanged.connect(self.refresh_preview)
        self.encoding_combo.currentTextChanged.connect(self.refresh_preview)
        self.header_spin.valueChanged.connect(self.refresh_preview)
        self.dayfirst_check.toggled.connect(self.refresh_preview)
        self.duplicates_check.toggled.connect(self.refresh_preview)
        self.since_edit.dateChanged.connect(self.refresh_preview)
        for combo in self.column_combos.values():
            combo.currentTextChanged.connect(self.refresh_preview)
        self.extra_combo.selectionChanged.connect(self.refresh_preview)
        self.import_button.clicked.connect(self.import_transactions)
        self.cancel_button.clicked.connect(self.close)

    def _labelled(self, label: str, widget: QWidget) -> QVBoxLayout:
        box = QVBoxLayout()
        box.addWidget(QLabel(label, self))
        box.addWidget(widget)
        return box

    # ------------------------------------------------------------------ profile <-> widgets
    def open_file(self, path: str | Path, account: str) -> None:
        self.path, self.account = Path(path), account
        self.setWindowTitle(f"Import {self.path.name} into {account}")
        profile, matched = propose_profile(self.path, self.model.profiles)
        self.original_name = matched.name if matched else None
        self.set_profile(profile)
        self._loading = True
        self.since_edit.setDate(QDate(2000, 1, 1))
        self._loading = False
        self.refresh_preview()
        if self.preview is not None and self.preview.first_date is not None:
            self._loading = True
            self.since_edit.setDate(_qdate(self.preview.first_date))
            self._loading = False
        self.show()
        self.raise_()

    def set_profile(self, profile: ImportProfile) -> None:
        self._loading = True
        try:
            self.name_edit.setText(profile.name)
            self.encoding_combo.setCurrentText(profile.encoding)
            self.separator_edit.setText(profile.separator)
            self.decimal_edit.setText(profile.decimal)
            self.thousands_edit.setText(profile.thousands)
            self.header_spin.setValue(profile.skiprows)
            self.dayfirst_check.setChecked(profile.dayfirst)
            self.duplicates_check.setChecked(profile.drop_duplicates)
            for combo in self.column_combos.values():
                combo.clear()
            self.extra_combo.clear()
            self._mapping = profile.mapping
        finally:
            self._loading = False

    def profile(self) -> ImportProfile:
        return ImportProfile(
            name=self.name_edit.text().strip(),
            encoding=self.encoding_combo.currentText().strip() or "utf-8",
            separator=self.separator_edit.text(),
            decimal=self.decimal_edit.text(),
            thousands=self.thousands_edit.text(),
            dayfirst=self.dayfirst_check.isChecked(),
            skiprows=self.header_spin.value(),
            drop_duplicates=self.duplicates_check.isChecked(),
            col_value_extra=[str(c) for c in self.extra_combo.currentData()],
            **{f: self.column_combos[f].currentText() for f in MAPPING_FIELDS},
        )

    def _set_columns(self, columns: list[str]) -> None:
        self._loading = True
        try:
            for field, combo in self.column_combos.items():
                wanted = self._mapping.get(field) or combo.currentText()
                combo.clear()
                combo.addItems(["", *columns])
                combo.setCurrentText(wanted if wanted in columns else "")
            extra = [c for c in self._mapping.get("col_value_extra", []) if c in columns]
            self.extra_combo.clear()
            for column in columns:
                self.extra_combo.addItem(column, column)
            self.extra_combo.setCurrentIndexes([columns.index(c) for c in extra])
        finally:
            self._loading = False

    # ------------------------------------------------------------------ preview / import
    def since(self) -> pd.Timestamp:
        date = self.since_edit.date()
        return pd.Timestamp(date.year(), date.month(), date.day())

    def refresh_preview(self, *_args) -> None:
        if self._loading or self.path is None:
            return
        self.preview = None
        self.error_label.clear()
        if any(c.count() for c in self.column_combos.values()):
            self._mapping = {f: c.currentText() for f, c in self.column_combos.items()}
            self._mapping["col_value_extra"] = [str(c) for c in self.extra_combo.currentData()]
        profile = self.profile()
        try:
            table = read_table(self.path, profile)
            self._set_columns(list(table.columns))
            profile = self.profile()
            existing = self.model.account_transactions(self.account)
            self.preview = preview_import(table, profile, existing=existing, since=self.since())
        except ImportFormatError as e:
            self.error_label.setText(str(e))
        frame = self.preview.transactions if self.preview is not None else None
        self.table_model.set_frame(frame)
        self.status_label.setText(self.status_text())
        self.import_button.setEnabled(self.preview is not None and not self.preview.transactions.empty)

    def status_text(self) -> str:
        preview = self.preview
        if preview is None:
            return ""
        parts = [f"{len(preview.transactions)} new transactions"]
        if len(preview.duplicates):
            parts.append(f"{len(preview.duplicates)} already imported")
        if preview.before_since:
            parts.append(f"{preview.before_since} before the start date")
        if preview.invalid:
            parts.append(f"{preview.invalid} rows without valid date or value")
        if preview.zero:
            parts.append(f"{preview.zero} with value 0")
        return ", ".join(parts)

    def import_transactions(self) -> int:
        if self.preview is None or self.preview.transactions.empty:
            return 0
        count = self.model.import_transactions(self.account, self.preview.transactions)
        self.model.save_profile(self.profile(), original_name=self.original_name)
        self.close()
        return count
