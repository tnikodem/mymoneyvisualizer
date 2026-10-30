"""Accounts: one tab per account with its transactions."""

from __future__ import annotations

import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, TAGGERS, TRANSACTIONS
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.ui.common import Window
from mymoneyvisualizer.ui.table_model import DATE, MONEY, NUMBER, TAG, Column, DataFrameModel, DataFrameView

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

TRANSACTION_COLUMNS = [
    Column(Col.transaction_id, "id", hidden=True),
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=280),
    Column(Col.description, "description", width=520),
    Column(Col.value, "value", MONEY, 100),
    Column(Col.recurring, "recurring", NUMBER, 70),
    Column(Col.tag, "tag", TAG, 160),
]


class AccountTab(QWidget):
    def __init__(self, window: AccountsWindow, account: str):
        super().__init__(window)
        self.window_ = window
        self.account = account
        self.dirty = True

        self.name_edit = QLineEdit(account, self)
        self.name_edit.setFixedWidth(240)
        self.import_button = QPushButton("Import data", self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Name:", self))
        controls.addWidget(self.name_edit)
        controls.addWidget(self.import_button)
        controls.addStretch(1)

        self.table_model = DataFrameModel(TRANSACTION_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)
        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addWidget(self.table)

        self.name_edit.returnPressed.connect(self.rename)
        self.import_button.clicked.connect(self.import_data)
        self.table.doubleClicked.connect(self.open_tagger)

    def refresh(self) -> None:
        self.dirty = False
        self.table_model.set_frame(self.window_.model.account_transactions(self.account))

    def rename(self) -> None:
        new = self.window_.model.rename_account(self.account, self.name_edit.text())
        self.name_edit.setText(new)

    def import_data(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, f"Import into {self.account}", "", "CSV files (*.csv);;All (*)")
        if path:
            self.window_.navigator.open_import(path, self.account)

    def open_tagger(self, index) -> None:
        row = self.table.row_at(index.row())
        self.window_.navigator.open_tagger(transaction_id=row[Col.transaction_id])


class AccountsWindow(Window):
    topics = frozenset({ACCOUNTS, TRANSACTIONS, TAGGERS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Accounts")
        self.resize(1400, 900)

        self.new_button = QPushButton("New Account", self)
        self.delete_button = QPushButton("Delete Account", self)
        self.taggers_button = QPushButton("Taggers", self)
        self.load_button = QPushButton("Load Project", self)
        self.save_button = QPushButton("Save Project", self)
        controls = QHBoxLayout()
        for button in (self.new_button, self.delete_button, self.taggers_button, self.load_button, self.save_button):
            button.setMinimumWidth(150)
            controls.addWidget(button)
        controls.addStretch(1)

        self.tabs = QTabWidget(self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.tabs)
        self.setCentralWidget(central)

        self.new_button.clicked.connect(self.create_account)
        self.delete_button.clicked.connect(self.delete_account)
        self.taggers_button.clicked.connect(navigator.show_tagger_overview)
        self.load_button.clicked.connect(self.load_project)
        self.save_button.clicked.connect(self.save_project)
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
        if self.confirm("Delete account", f"Delete account {tab.account!r} and all its transactions?"):
            self.model.delete_account(tab.account)

    def save_project(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            proposal = f"mmv_backup_{datetime.datetime.now():%Y_%m_%d__%H_%M_%S}.zip"
            path, _ = QFileDialog.getSaveFileName(self, "Save Project", proposal, "Zip files (*.zip)")
        if path:
            self.model.create_backup(path)

    def load_project(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "Zip files (*.zip)")
        if not path:
            return
        if not self.confirm(
            "Load project",
            "Replace all current data by the backup? The current data is kept in a folder next to the data directory.",
        ):
            return
        try:
            previous = self.model.restore_backup(Path(path))
        except StorageError as e:
            self.show_error("Load project", str(e))
            return
        if previous is not None:
            QMessageBox.information(self, "Load project", f"Previous data moved to\n{previous}")
