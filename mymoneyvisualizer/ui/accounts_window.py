"""Accounts: one tab per account with its transactions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLineEdit, QTabWidget, QVBoxLayout, QWidget

from mymoneyvisualizer.app import ACCOUNTS, RULES, TRANSACTIONS
from mymoneyvisualizer.domain.columns import UNCATEGORIZED, Col
from mymoneyvisualizer.ui.common import HelpButton, Window, make_button, make_label, set_tone
from mymoneyvisualizer.ui.table_model import (
    CATEGORY,
    DATE,
    MONEY,
    MONTHS,
    PERCENT,
    Column,
    DataFrameModel,
    DataFrameView,
)

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

TRANSACTION_COLUMNS = [
    Column(Col.transaction_id, "id", hidden=True),
    Column(Col.date, "Datum", DATE, 90),
    Column(Col.recipient, "Empfänger", width=280),
    Column(Col.description, "Verwendungszweck", width=500),
    Column(Col.value, "Betrag", MONEY, 100),
    Column(Col.category, "Kategorie", CATEGORY, 170, tooltip="Leer: noch ohne Kategorie. Doppelklick ändert sie."),
    Column(Col.spread_months, "Verteilt über", MONTHS, 90, tooltip="Im Budget über so viele Monate verteilt."),
    Column(Col.residual_percent, "Restwert", PERCENT, 70, tooltip="Erwarteter Wiederverkaufswert, z. B. beim Auto."),
]
EMPTY_HINT = "Noch keine Buchungen: Umsätze im Online-Banking als CSV exportieren und hier importieren."
HELP = (
    "<p>Jedes Konto hat einen eigenen Reiter; Kategorien und Regeln gelten für alle Konten.</p>"
    "<p><b>CSV-Datei importieren:</b> den Export des Online-Bankings einlesen. Format und Spalten werden erkannt,"
    " schon vorhandene Buchungen übersprungen; überlappende Exporte sind also kein Problem.</p>"
    "<p>Doppelklick auf eine Buchung ändert ihre Kategorie.</p>"
)


class AccountTab(QWidget):
    def __init__(self, window: AccountsWindow, account: str):
        super().__init__(window)
        self.window_ = window
        self.account = account
        self.dirty = True

        self.name_edit = QLineEdit(account, self)
        self.name_edit.setFixedWidth(240)
        self.name_edit.setToolTip(
            "Name des Kontos. Umbuchungen auf dieses Konto bekommen seinen Namen als Kategorie und zählen nicht als"
            " Einnahme oder Ausgabe."
        )
        self.import_button = make_button(
            "CSV-Datei importieren …",
            "Den CSV-Export deiner Bank für dieses Konto importieren. Buchungen, die schon da sind, werden erkannt und"
            " übersprungen; überlappende Exporte sind also kein Problem.",
            self,
            primary=True,
        )
        self.summary = make_label("", self, "hint")
        controls = QHBoxLayout()
        controls.addWidget(make_label("Name:", self))
        controls.addWidget(self.name_edit)
        controls.addSpacing(12)
        controls.addWidget(self.summary, 1)
        controls.addWidget(self.import_button)

        self.empty_hint = make_label(EMPTY_HINT, self, wrap=True)
        set_tone(self.empty_hint, "warning")
        self.table_model = DataFrameModel(TRANSACTION_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.addLayout(controls)
        layout.addWidget(self.empty_hint)
        layout.addWidget(self.table)

        self.name_edit.editingFinished.connect(self.rename)
        self.import_button.clicked.connect(self.import_data)
        self.table.doubleClicked.connect(self.open_rule)

    def refresh(self) -> None:
        self.dirty = False
        df = self.window_.model.account_transactions(self.account)
        self.table_model.set_frame(df)
        self.empty_hint.setVisible(df.empty)
        if df.empty:
            self.summary.setText("")
            return
        uncategorized = int((df[Col.category] == UNCATEGORIZED).sum())
        parts = [
            f"{len(df):,} Buchungen".replace(",", "."),
            f"{df[Col.date].min():%d.%m.%Y} – {df[Col.date].max():%d.%m.%Y}",
        ]
        if uncategorized:
            parts.append(f"{uncategorized} ohne Kategorie")
        self.summary.setText(" · ".join(parts))

    def rename(self) -> None:
        new = self.window_.model.rename_account(self.account, self.name_edit.text())
        self.name_edit.setText(new)

    def import_data(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, f"CSV-Datei für {self.account} wählen", "", "CSV-Dateien (*.csv);;Alle Dateien (*)"
            )
        if path:
            self.window_.navigator.open_import(path, self.account)

    def open_rule(self, index) -> None:
        row = self.table.row_at(index.row())
        self.window_.navigator.open_rule(transaction_id=row[Col.transaction_id])


class AccountsWindow(Window):
    topics = frozenset({ACCOUNTS, TRANSACTIONS, RULES})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Konten")
        self.resize(1400, 900)

        self.new_button = make_button(
            "Neues Konto", "Ein weiteres Konto anlegen, z. B. Tagesgeld oder Kreditkarte.", self
        )
        self.delete_button = make_button(
            "Konto löschen", "Das angezeigte Konto mit allen seinen Buchungen löschen.", self
        )
        controls = QHBoxLayout()
        for button in (self.new_button, self.delete_button):
            button.setMinimumWidth(150)
            controls.addWidget(button)
        controls.addStretch(1)
        controls.addWidget(HelpButton(HELP, "Konten", self))

        self.tabs = QTabWidget(self)
        self.tabs.setDocumentMode(False)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addLayout(controls)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.new_button.clicked.connect(self.create_account)
        self.delete_button.clicked.connect(self.delete_account)
        self.tabs.currentChanged.connect(self._tab_shown)

    @property
    def account_tabs(self) -> list[AccountTab]:
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def tab(self, account: str) -> AccountTab | None:
        return next((t for t in self.account_tabs if t.account == account), None)

    def refresh(self) -> None:
        super().refresh()
        current = self.tabs.currentWidget().account if self.tabs.count() else None
        current_index = self.tabs.currentIndex()
        names = self.model.account_names
        if len(names) == self.tabs.count():  # at most a rename: update in place
            for i, (tab, name) in enumerate(zip(self.account_tabs, names, strict=True)):
                if tab.account != name:
                    tab.account = name
                    tab.name_edit.setText(name)
                    self.tabs.setTabText(i, name)
        else:
            while self.tabs.count():
                widget = self.tabs.widget(0)
                self.tabs.removeTab(0)
                widget.deleteLater()
            for name in names:
                self.tabs.addTab(AccountTab(self, name), name)
            if current in names:
                self.tabs.setCurrentIndex(names.index(current))
            elif names:
                self.tabs.setCurrentIndex(min(max(current_index, 0), len(names) - 1))
        self.delete_button.setEnabled(bool(names))
        # large accounts: fill only the visible tab, the others when they are shown
        for tab in self.account_tabs:
            tab.dirty = True
        self._tab_shown(self.tabs.currentIndex())

    def _tab_shown(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if tab is not None and tab.dirty:
            tab.refresh()

    def create_account(self) -> str:
        name = self.model.add_account()
        self.tabs.setCurrentIndex(self.model.account_names.index(name))
        return name

    def delete_account(self) -> None:
        tab = self.tabs.currentWidget()
        if tab is None:
            return
        if self.confirm("Konto löschen", f"Das Konto „{tab.account}“ mit allen seinen Buchungen löschen?"):
            self.model.delete_account(tab.account)
