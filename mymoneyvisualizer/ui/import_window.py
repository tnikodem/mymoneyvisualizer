"""Import a CSV export: what will be added, the column mapping and, if detection failed, the file format."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QGridLayout,
    QHBoxLayout,
    QLineEdit,
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
from mymoneyvisualizer.ui.common import Card, HelpButton, Window, make_button, make_label, set_tone
from mymoneyvisualizer.ui.table_model import DATE, MONEY, Column, DataFrameModel, DataFrameView

ENCODINGS = ("utf-8", "utf-8-sig", MIXED_ENCODING, "cp1252", "latin-1", "utf-16")
PREVIEW_COLUMNS = [
    Column(Col.date, "Datum", DATE, 90),
    Column(Col.recipient, "Empfänger", width=280),
    Column(Col.description, "Verwendungszweck", width=560),
    Column(Col.value, "Betrag", MONEY, 110),
]
MAPPING_LABELS = {
    "col_date": "Datum",
    "col_recipient": "Empfänger (optional)",
    "col_description": "Verwendungszweck (optional)",
    "col_value": "Betrag",
    "col_debit": "Soll-Beträge (optional)",
    "col_credit": "Haben-Beträge (optional)",
    "col_sign": "Soll/Haben-Kennzeichen, z. B. S/H (optional)",
}
MAPPING_TIPS = {
    "col_date": "Die Spalte mit dem Buchungsdatum.",
    "col_recipient": "Wer das Geld bekommt oder schickt; damit werden Regeln vorgeschlagen.",
    "col_description": "Der Verwendungszweck bzw. Buchungstext.",
    "col_value": "Der Betrag mit Vorzeichen: Ausgaben negativ, Eingänge positiv.",
    "col_debit": "Nur nötig, wenn die Datei Ausgaben in einer eigenen Spalte hat.",
    "col_credit": "Nur nötig, wenn die Datei Eingänge in einer eigenen Spalte hat.",
    "col_sign": "Nur nötig, wenn die Beträge kein Vorzeichen haben und eine Spalte S (Soll) oder H (Haben) angibt.",
}
MAIN_FIELDS = ("col_date", "col_value", "col_recipient", "col_description")
MAPPING_HELP = (
    "<p>Die Spalten sind vorgeschlagen; prüfe sie an der Vorschau. Die Zuordnung wird für die nächste Datei derselben"
    " Bank gespeichert.</p>"
    "<p>Buchungen, die schon im Konto sind, werden übersprungen.</p>"
)
ADVANCED_HELP = (
    "Sehen Umlaute oder Beträge in der Vorschau falsch aus, helfen Zeichensatz, Trennzeichen und Dezimalzeichen."
)


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
        self.name_edit.setToolTip(
            "Unter diesem Namen werden die Einstellungen gespeichert und beim nächsten Import einer Datei mit denselben"
            " Spalten automatisch verwendet."
        )
        self.encoding_combo = QComboBox(self)
        self.encoding_combo.setEditable(True)
        self.encoding_combo.addItems(ENCODINGS)
        self.encoding_combo.setToolTip(
            "Wie die Datei kodiert ist. Kaputte Umlaute (Ã¤ statt ä) deuten auf den falschen."
        )
        self.separator_edit = QLineEdit(self)
        self.separator_edit.setToolTip("Zeichen zwischen den Spalten, meist ; oder ,")
        self.decimal_edit = QLineEdit(self)
        self.decimal_edit.setToolTip("Zeichen vor den Cent, in deutschen Dateien meist ein Komma: 1,99")
        self.thousands_edit = QLineEdit(self)
        self.thousands_edit.setToolTip("Zeichen zwischen den Tausendern, z. B. der Punkt in 1.000,00; darf leer sein.")
        for edit in (self.separator_edit, self.decimal_edit, self.thousands_edit):
            edit.setMaxLength(1)
            edit.setFixedWidth(48)
        self.header_spin = QSpinBox(self)
        self.header_spin.setRange(0, 10_000)
        self.header_spin.setToolTip("So viele Zeilen stehen vor der Zeile mit den Spaltennamen.")
        self.dayfirst_check = QCheckBox("Tag vor Monat", self)
        self.dayfirst_check.setToolTip("Datum als Tag.Monat.Jahr wie in Deutschland, nicht Monat/Tag/Jahr.")
        self.duplicates_check = QCheckBox("Schon vorhandene überspringen", self)
        self.duplicates_check.setToolTip(
            "Buchungen, die schon im Konto sind (gleiches Datum, gleicher Betrag, gleicher Text), nicht noch einmal"
            " importieren. So schaden überlappende Exporte nicht."
        )
        self.since_edit = QDateEdit(self)
        self.since_edit.setCalendarPopup(True)
        self.since_edit.setDisplayFormat("dd.MM.yyyy")
        self.since_edit.setToolTip("Ältere Buchungen der Datei werden nicht importiert.")
        self.column_combos = {f: QComboBox(self) for f in MAPPING_FIELDS}
        for field, combo in self.column_combos.items():
            combo.setToolTip(MAPPING_TIPS[field])
            combo.setMinimumWidth(200)
        self.extra_combo = MultiSelectComboBox(self)
        self.extra_combo.setPlaceholderText("keine")
        self.extra_combo.setMinimumWidth(200)
        self.extra_combo.setToolTip("Spalten, die zum Betrag addiert werden, z. B. Gebühren oder Steuern eines Depots.")
        self.name_edit.setFixedWidth(200)

        self.title = make_label("", self, "heading")
        self.status_label = make_label("", self, wrap=True)
        self.error_label = make_label("", self, wrap=True)
        set_tone(self.error_label, "bad")
        self.import_button = make_button(
            "Importieren", "Die Buchungen der Vorschau in das Konto übernehmen.", self, primary=True
        )
        self.cancel_button = make_button("Abbrechen", "Nichts importieren und das Fenster schließen.", self)
        header = QHBoxLayout()
        texts = QVBoxLayout()
        texts.addWidget(self.title)
        texts.addWidget(self.status_label)
        header.addLayout(texts, 1)
        header.addWidget(self.cancel_button)
        header.addWidget(self.import_button)

        mapping = Card(self)
        heading = QHBoxLayout()
        heading.addWidget(make_label("Spaltenzuordnung", mapping, "heading"))
        heading.addWidget(HelpButton(MAPPING_HELP, "Spaltenzuordnung", mapping))
        heading.addStretch(1)
        mapping.content.addLayout(heading)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        for column, field in enumerate(MAIN_FIELDS):
            grid.addWidget(make_label(MAPPING_LABELS[field], mapping), 0, column)
            grid.addWidget(self.column_combos[field], 1, column)
        grid.addWidget(make_label("Importieren ab", mapping), 0, len(MAIN_FIELDS))
        grid.addWidget(self.since_edit, 1, len(MAIN_FIELDS))
        grid.setColumnStretch(len(MAIN_FIELDS) + 1, 1)
        mapping.content.addLayout(grid)

        self.advanced_button = make_button(
            "▸ Erweiterte Einstellungen",
            "Dateiformat und besondere Betragsspalten. Nur nötig, wenn die Vorschau falsch aussieht.",
            self,
            link=True,
        )
        self.advanced_button.setCheckable(True)
        self.advanced = QWidget(self)
        advanced = QGridLayout(self.advanced)
        advanced.setContentsMargins(0, 0, 0, 0)
        advanced.setHorizontalSpacing(16)
        format_fields = (
            ("Profilname", self.name_edit),
            ("Zeichensatz", self.encoding_combo),
            ("Trennzeichen", self.separator_edit),
            ("Dezimalzeichen", self.decimal_edit),
            ("Tausender", self.thousands_edit),
            ("Zeilen vor der Kopfzeile", self.header_spin),
        )
        for column, (label, widget) in enumerate(format_fields):
            advanced.addWidget(make_label(label, self.advanced), 0, column)
            advanced.addWidget(widget, 1, column)
        advanced.addWidget(self.dayfirst_check, 1, len(format_fields))
        advanced.addWidget(self.duplicates_check, 1, len(format_fields) + 1)
        values = (*[f for f in MAPPING_FIELDS if f not in MAIN_FIELDS],)
        advanced.addWidget(make_label("Zum Betrag addieren (optional)", self.advanced), 2, 0, 1, 2)
        advanced.addWidget(self.extra_combo, 3, 0, 1, 2)
        for column, field in enumerate(values, start=2):
            advanced.addWidget(make_label(MAPPING_LABELS[field], self.advanced), 2, 2 * column - 2, 1, 2)
            advanced.addWidget(self.column_combos[field], 3, 2 * column - 2, 1, 2)
        advanced.setColumnStretch(len(format_fields) + 2, 1)
        advanced_row = QHBoxLayout()
        advanced_row.addWidget(self.advanced_button)
        advanced_row.addWidget(HelpButton(ADVANCED_HELP, "Erweiterte Einstellungen", mapping))
        advanced_row.addStretch(1)
        mapping.content.addLayout(advanced_row)
        mapping.content.addWidget(self.advanced)
        self.advanced.hide()

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.error_label)
        layout.addWidget(mapping)
        layout.addWidget(make_label("Vorschau", self, "heading"))
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
        self.advanced_button.toggled.connect(self.show_advanced)

    def show_advanced(self, shown: bool) -> None:
        self.advanced.setVisible(shown)
        self.advanced_button.setText(("▾" if shown else "▸") + " Erweiterte Einstellungen")

    # ------------------------------------------------------------------ profile <-> widgets
    def open_file(self, path: str | Path, account: str) -> None:
        self.path, self.account = Path(path), account
        self.setWindowTitle(f"Import: {self.path.name} → {account}")
        self.title.setText(f"{self.path.name} → Konto {account}")
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
            message = str(e)
            if not message.startswith("Bitte eine Spalte"):  # the file format is not right
                message += " Prüfe die erweiterten Einstellungen."
                self.advanced_button.setChecked(True)
            self.error_label.setText(message)
        self.error_label.setVisible(bool(self.error_label.text()))
        frame = self.preview.transactions if self.preview is not None else None
        self.table_model.set_frame(frame)
        self.status_label.setText(self.status_text())
        self.import_button.setEnabled(self.preview is not None and not self.preview.transactions.empty)

    def status_text(self) -> str:
        preview = self.preview
        if preview is None:
            return ""
        new = len(preview.transactions)
        parts = [f"<b>{new} neue {'Buchung' if new == 1 else 'Buchungen'}</b>"]
        if len(preview.duplicates):
            parts.append(f"{len(preview.duplicates)} schon vorhanden")
        if preview.before_since:
            parts.append(f"{preview.before_since} vor dem Startdatum")
        if preview.invalid:
            rows = "Zeile" if preview.invalid == 1 else "Zeilen"
            parts.append(f"{preview.invalid} {rows} ohne gültiges Datum oder gültigen Betrag")
        if preview.zero:
            parts.append(f"{preview.zero} mit Betrag 0")
        return " · ".join(parts)

    def import_transactions(self) -> int:
        if self.preview is None or self.preview.transactions.empty:
            return 0
        count = self.model.import_transactions(self.account, self.preview.transactions)
        self.model.save_profile(self.profile(), original_name=self.original_name)
        self.close()
        return count
