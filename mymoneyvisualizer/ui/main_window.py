"""Start window. Creates the other windows on first use and connects them."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from PyQt6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.ui.accounts_window import AccountsWindow
from mymoneyvisualizer.ui.budget_window import BudgetWindow
from mymoneyvisualizer.ui.common import ModelBridge
from mymoneyvisualizer.ui.import_window import ImportWindow
from mymoneyvisualizer.ui.income_expenses_window import DetailWindow, IncomeExpensesWindow
from mymoneyvisualizer.ui.rule_window import RuleWindow
from mymoneyvisualizer.ui.rules_window import RulesWindow


class MainWindow(QMainWindow):
    def __init__(self, model: AppModel):
        super().__init__()
        self.model = model
        self.bridge = ModelBridge(model, self)
        self.setWindowTitle("My Money Visualiser")

        self.accounts_button = QPushButton("Accounts", self)
        self.income_expenses_button = QPushButton("Income && Expenses", self)
        self.budget_button = QPushButton("Budget", self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        for button in (self.accounts_button, self.income_expenses_button, self.budget_button):
            button.setMinimumSize(250, 32)
            layout.addWidget(button)
        location = QLabel(f"Data: {model.repository.data_dir}", self)
        location.setWordWrap(True)
        layout.addWidget(location)
        self.setCentralWidget(central)

        self.accounts_button.clicked.connect(self.show_accounts)
        self.income_expenses_button.clicked.connect(self.show_income_expenses)
        self.budget_button.clicked.connect(self.show_budget)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.bridge.detach()
        super().closeEvent(event)

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

    def open_rule(self, name: str | None = None, transaction_id: str | None = None) -> None:
        if transaction_id is not None:
            self.rule_window.open_for_transaction(transaction_id)
        elif name is not None:
            self.rule_window.open_rule(name)
        else:
            self.rule_window.open_new()

    def open_detail(self, month: str, category: str | None, category_filter: str = "") -> None:
        self.detail_window.open_detail(month, category, category_filter)

    def open_import(self, path: str | Path, account: str) -> None:
        self.import_window.open_file(path, account)
