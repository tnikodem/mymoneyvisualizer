"""Start window: the four steps of the workflow and backups. Creates the other windows on first use."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

from PyQt6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, RULES, TRANSACTIONS, AppModel
from mymoneyvisualizer.domain.columns import UNCATEGORIZED
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.ui.accounts_window import AccountsWindow
from mymoneyvisualizer.ui.budget_window import BudgetWindow
from mymoneyvisualizer.ui.common import ModelBridge
from mymoneyvisualizer.ui.import_window import ImportWindow
from mymoneyvisualizer.ui.income_expenses_window import DetailWindow, IncomeExpensesWindow
from mymoneyvisualizer.ui.rule_window import RuleWindow
from mymoneyvisualizer.ui.rules_window import RulesWindow


class MainWindow(QMainWindow):
    topics = frozenset({ACCOUNTS, TRANSACTIONS, RULES})

    def __init__(self, model: AppModel):
        super().__init__()
        self.model = model
        self.bridge = ModelBridge(model, self)
        self.setWindowTitle("My Money Visualizer")

        self.accounts_button = QPushButton("1. Accounts", self)
        self.rules_button = QPushButton("2. Rules", self)
        self.income_expenses_button = QPushButton("3. Income && Expenses", self)
        self.budget_button = QPushButton("4. Budget", self)
        self.accounts_status = QLabel(self)
        self.rules_status = QLabel(self)
        self.uncategorized_button = QPushButton("Categorize", self)
        steps = QGridLayout()
        explanations = (
            (self.accounts_button, self.accounts_status),
            (self.rules_button, self.rules_status),
            (self.income_expenses_button, QLabel("When was how much paid? Check every month at a glance.", self)),
            (self.budget_button, QLabel("Spending spread over time, compared with the 50/30/20 rule.", self)),
        )
        for row, (button, label) in enumerate(explanations):
            button.setMinimumSize(220, 32)
            steps.addWidget(button, row, 0)
            steps.addWidget(label, row, 1)
        steps.addWidget(self.uncategorized_button, 1, 2)
        steps.setColumnStretch(1, 1)

        self.save_button = QPushButton("Save backup…", self)
        self.load_button = QPushButton("Load backup…", self)
        backups = QHBoxLayout()
        backups.addWidget(self.save_button)
        backups.addWidget(self.load_button)
        backups.addStretch(1)
        location = QLabel(f"Data: {model.repository.data_dir}", self)
        location.setWordWrap(True)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(steps)
        layout.addSpacing(12)
        layout.addLayout(backups)
        layout.addWidget(location)
        self.setCentralWidget(central)

        self.accounts_button.clicked.connect(self.show_accounts)
        self.rules_button.clicked.connect(self.show_rules)
        self.income_expenses_button.clicked.connect(self.show_income_expenses)
        self.budget_button.clicked.connect(self.show_budget)
        self.uncategorized_button.clicked.connect(self.show_uncategorized)
        self.save_button.clicked.connect(self.save_backup)
        self.load_button.clicked.connect(self.load_backup)
        self.bridge.changed.connect(self._on_changed)
        self.refresh_status()

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.bridge.detach()
        super().closeEvent(event)

    def _on_changed(self, topics: frozenset[str]) -> None:
        if topics & self.topics:
            self.refresh_status()

    def refresh_status(self) -> None:
        accounts = len(self.model.account_names)
        transactions = len(self.model.transactions())
        self.accounts_status.setText(
            f"{accounts} account{'' if accounts == 1 else 's'} with {transactions} transactions."
            " Import the CSV exports of your bank."
        )
        uncategorized = self.model.uncategorized_count()
        rules = len(self.model.rules)
        self.rules_status.setText(
            f"{rules} rule{'' if rules == 1 else 's'}; "
            + (f"{uncategorized} transactions without category." if uncategorized else "everything is categorized.")
        )
        self.uncategorized_button.setEnabled(uncategorized > 0)

    # ------------------------------------------------------------------ windows (created lazily)
    @cached_property
    def accounts_window(self) -> AccountsWindow:
        return AccountsWindow(self.model, self.bridge, self)

    @cached_property
    def income_expenses_window(self) -> IncomeExpensesWindow:
        return IncomeExpensesWindow(self.model, self.bridge, self)

    @cached_property
    def budget_window(self) -> BudgetWindow:
        return BudgetWindow(self.model, self.bridge, self)

    @cached_property
    def rule_window(self) -> RuleWindow:
        return RuleWindow(self.model, self.bridge, self)

    @cached_property
    def rules_window(self) -> RulesWindow:
        return RulesWindow(self.model, self.bridge, self)

    @cached_property
    def detail_window(self) -> DetailWindow:
        return DetailWindow(self.model, self.bridge, self)

    @cached_property
    def import_window(self) -> ImportWindow:
        return ImportWindow(self.model, self.bridge, self)

    # ------------------------------------------------------------------ navigation
    @staticmethod
    def _show(window: QMainWindow) -> None:
        window.show()
        window.raise_()
        window.activateWindow()

    def show_accounts(self) -> None:
        self._show(self.accounts_window)

    def show_income_expenses(self) -> None:
        self._show(self.income_expenses_window)

    def show_budget(self) -> None:
        self._show(self.budget_window)

    def show_rules(self) -> None:
        self._show(self.rules_window)

    def show_uncategorized(self) -> None:
        """All transactions without category; a double click categorizes one."""
        self.open_detail(None, [UNCATEGORIZED])

    def open_rule(self, name: str | None = None, transaction_id: str | None = None) -> None:
        if transaction_id is not None:
            self.rule_window.open_for_transaction(transaction_id)
        elif name is not None:
            self.rule_window.open_rule(name)
        else:
            self.rule_window.open_new()

    def open_detail(
        self, month: str | None, categories: Sequence[str] | None, category_filter: str = "", title: str = ""
    ) -> None:
        self.detail_window.open_detail(month, categories, category_filter, title)

    def open_import(self, path: str | Path, account: str) -> None:
        self.import_window.open_file(path, account)

    # ------------------------------------------------------------------ backups
    def save_backup(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            proposal = f"mmv_backup_{datetime.datetime.now():%Y_%m_%d__%H_%M_%S}.zip"
            path, _ = QFileDialog.getSaveFileName(self, "Save backup", proposal, "Zip files (*.zip)")
        if path:
            self.model.create_backup(path)

    def load_backup(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Load backup", "", "Zip files (*.zip)")
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Load backup",
            "Replace all current data by the backup? The current data is kept in a folder next to the data directory.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            previous = self.model.restore_backup(Path(path))
        except StorageError as e:
            QMessageBox.warning(self, "Load backup", str(e))
            return
        if previous is not None:
            QMessageBox.information(self, "Load backup", f"Previous data moved to\n{previous}")
