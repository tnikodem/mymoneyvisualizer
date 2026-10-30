"""Start window: how are my finances, and the four steps to get there. Creates the other windows on first use."""

from __future__ import annotations

import datetime
from collections.abc import Sequence
from functools import cached_property
from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, GROUPS, RULES, SETTINGS, TRANSACTIONS, AppModel
from mymoneyvisualizer.domain.columns import UNCATEGORIZED, Col
from mymoneyvisualizer.storage.files import StorageError
from mymoneyvisualizer.ui.accounts_window import AccountsWindow
from mymoneyvisualizer.ui.budget_window import BudgetWindow, euro, percent
from mymoneyvisualizer.ui.common import Card, HelpButton, ModelBridge, make_button, make_label, set_tone
from mymoneyvisualizer.ui.import_window import ImportWindow
from mymoneyvisualizer.ui.income_expenses_window import DetailWindow, IncomeExpensesWindow
from mymoneyvisualizer.ui.rule_window import RuleWindow
from mymoneyvisualizer.ui.rules_window import RulesWindow
from mymoneyvisualizer.ui.style import set_variant
from mymoneyvisualizer.ui.table_model import format_month_range


def thousands(number: int) -> str:
    return f"{number:,}".replace(",", ".")


HELP = (
    "<p>In vier Schritten von den Kontoauszügen zum Budget; der nächste Schritt ist blau hervorgehoben.</p>"
    "<p>Alle Daten bleiben auf diesem Computer.</p>"
)


class StepCard(Card):
    """One step of the workflow: number, title with its explanation, its state and the buttons that start it."""

    def __init__(self, number: int, title: str, text: str, buttons: Sequence[QPushButton], parent: QWidget):
        super().__init__(parent, horizontal=True)
        badge = make_label(str(number), self, "step")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.help_button = HelpButton(text, title, self)
        heading = QHBoxLayout()
        heading.addWidget(make_label(title, self, "heading"))
        heading.addWidget(self.help_button)
        heading.addStretch(1)
        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addLayout(heading)
        self.status = make_label("", self, wrap=True)
        texts.addWidget(self.status)
        self.content.setSpacing(14)
        self.content.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)
        self.content.addLayout(texts, 1)
        column = QVBoxLayout()
        column.setSpacing(6)
        for button in buttons:
            button.setMinimumWidth(170)
            column.addWidget(button)
        self.content.addLayout(column)


class MainWindow(QMainWindow):
    topics = frozenset({ACCOUNTS, TRANSACTIONS, RULES, GROUPS, SETTINGS})

    def __init__(self, model: AppModel):
        super().__init__()
        self.model = model
        self.bridge = ModelBridge(model, self)
        self.setWindowTitle("MyMoneyVisualizer")
        self.resize(720, 520)

        self.accounts_button = make_button(
            "Öffnen",
            "Konten anlegen und die CSV-Exporte deiner Bank importieren. Bereits importierte Buchungen werden erkannt"
            " und übersprungen.",
            self,
        )
        self.uncategorized_button = make_button(
            "Ohne Kategorie", "Alle Buchungen ohne Kategorie auflisten; ein Doppelklick kategorisiert eine davon.", self
        )
        self.rules_button = make_button(
            "Regeln",
            "Alle Regeln auf einen Blick: was sie erkennen, welche Kategorie sie vergeben und wie viele Buchungen sie"
            " treffen. Dort lassen sie sich auch ändern.",
            self,
        )
        self.income_expenses_button = make_button(
            "Öffnen", "Tabelle der Einnahmen und Ausgaben pro Monat und Kategorie, so wie bezahlt.", self
        )
        self.budget_button = make_button(
            "Öffnen",
            "Sparquote, Konsumausgaben nach Kategorien und ihre Entwicklung, periodengerecht.",
            self,
        )
        self.accounts_card = StepCard(
            1,
            "Konten",
            "CSV-Exporte der Bank importieren, für jedes Konto einzeln. Schon vorhandene Buchungen werden"
            " übersprungen.",
            [self.accounts_button],
            self,
        )
        self.categorize_card = StepCard(
            2,
            "Kategorisieren",
            "Jeder Buchung eine Kategorie geben, z. B. Wohnen.Miete. Eine Regel erledigt das für alle ähnlichen"
            " Buchungen, auch künftige.",
            [self.uncategorized_button, self.rules_button],
            self,
        )
        self.income_expenses_card = StepCard(
            3,
            "Einnahmen & Ausgaben",
            "Zahlungssicht: Monat für Monat und Kategorie für Kategorie. Fällt eine Zahlung aus dem Rahmen?",
            [self.income_expenses_button],
            self,
        )
        self.budget_card = StepCard(
            4,
            "Budget",
            "Periodengerecht: Sparquote, Konsumausgaben nach Kategorien, Entwicklung und Vergleich zum Vorjahr.",
            [self.budget_button],
            self,
        )
        self.accounts_status = self.accounts_card.status
        self.rules_status = self.categorize_card.status
        self.budget_status = self.budget_card.status
        self.income_expenses_card.status.hide()

        self.save_button = make_button(
            "Sicherung speichern …", "Alle Daten (Konten, Regeln, Einstellungen) in eine ZIP-Datei sichern.", self
        )
        self.load_button = make_button(
            "Sicherung laden …",
            "Alle Daten durch eine Sicherung ersetzen; die bisherigen Daten werden aufbewahrt.",
            self,
        )
        backups = QHBoxLayout()
        backups.addWidget(self.save_button)
        backups.addWidget(self.load_button)
        backups.addStretch(1)
        location = make_label(f"Daten: {model.repository.data_dir}", self, "hint", wrap=True)
        location.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        self.help_button = HelpButton(HELP, "MyMoneyVisualizer", self)
        header = QHBoxLayout()
        header.addWidget(make_label("MyMoneyVisualizer", self, "title"))
        header.addWidget(self.help_button)
        header.addStretch(1)
        layout.addLayout(header)
        layout.addSpacing(4)
        for card in (self.accounts_card, self.categorize_card, self.income_expenses_card, self.budget_card):
            layout.addWidget(card)
        layout.addStretch(1)
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
        # the budget is calculated once after a series of changes, not after every single one
        self._budget_timer = QTimer(self)
        self._budget_timer.setSingleShot(True)
        self._budget_timer.timeout.connect(self.refresh_budget_status)
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
        df = self.model.transactions()
        if df.empty:
            self.accounts_status.setText("Noch keine Buchungen." if accounts else "Noch kein Konto.")
        else:
            self.accounts_status.setText(
                f"{accounts} {'Konto' if accounts == 1 else 'Konten'} · {thousands(len(df))} Buchungen"
                f" bis {df[Col.date].max():%d.%m.%Y}"
            )
        set_tone(self.accounts_status, "warning" if df.empty else None)

        uncategorized = self.model.uncategorized_count()
        rules = len(self.model.rules)
        rules_text = f"{rules} {'Regel' if rules == 1 else 'Regeln'}"
        if df.empty:
            self.rules_status.setText(rules_text)
            set_tone(self.rules_status, None)
        elif uncategorized:
            self.rules_status.setText(f"{rules_text} · {thousands(uncategorized)} Buchungen ohne Kategorie")
            set_tone(self.rules_status, "warning")
        else:
            self.rules_status.setText(f"{rules_text} · ✓ alle Buchungen kategorisiert")
            set_tone(self.rules_status, "good")
        count = f" ({thousands(uncategorized)})" if uncategorized else ""
        self.uncategorized_button.setText(f"Ohne Kategorie{count}")
        self.uncategorized_button.setEnabled(uncategorized > 0)

        # the next step stands out
        if df.empty:
            next_step = self.accounts_button
        elif uncategorized:
            next_step = self.uncategorized_button
        else:
            next_step = self.budget_button
        for button in (self.accounts_button, self.uncategorized_button, self.budget_button):
            set_variant(button, "primary", button is next_step)
        self._budget_timer.start(0)

    def refresh_budget_status(self) -> None:
        """The answer of the budget in one line: savings rate and room per month."""
        report = self.model.budget_report()
        if report is None or report.months == 0 or report.savings_rate is None or report.room_per_month is None:
            self.budget_status.setText("Sparquote nach dem ersten abgeschlossenen Monat mit Einkommen")
            set_tone(self.budget_status, None)
            return
        room = report.room_per_month
        verdict = f"{euro(abs(room))} pro Monat {'über' if room >= 0 else 'unter'} dem Ziel"
        self.budget_status.setText(
            f"Sparquote {percent(report.savings_rate)} (Ziel {percent(report.savings.target)}) · {verdict}"
            f" · {format_month_range(report.start, report.end)}"
        )
        set_tone(self.budget_status, "good" if room >= 0 else "bad")

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

    def open_rule(self, rule_id: str | None = None, transaction_id: str | None = None) -> None:
        if transaction_id is not None:
            self.rule_window.open_for_transaction(transaction_id)
        elif rule_id is not None:
            self.rule_window.open_rule(rule_id)
        else:
            self.rule_window.open_new()

    def open_detail(
        self,
        month: str | None,
        categories: Sequence[str] | None,
        category_filter: str = "",
        title: str = "",
    ) -> None:
        self.detail_window.open_detail(month, categories, category_filter, title)

    def open_budget_detail(
        self, start: pd.Period, end: pd.Period, categories: Sequence[str] | None, title: str = "", months: int = 0
    ) -> None:
        self.detail_window.open_budget_detail(start, end, categories, title, months)

    def open_import(self, path: str | Path, account: str) -> None:
        self.import_window.open_file(path, account)

    # ------------------------------------------------------------------ backups
    def save_backup(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            proposal = f"mmv_backup_{datetime.datetime.now():%Y_%m_%d__%H_%M_%S}.zip"
            path, _ = QFileDialog.getSaveFileName(self, "Sicherung speichern", proposal, "ZIP-Dateien (*.zip)")
        if path:
            self.model.create_backup(path)

    def load_backup(self, checked: bool = False, path: str | None = None) -> None:
        if path is None:
            path, _ = QFileDialog.getOpenFileName(self, "Sicherung laden", "", "ZIP-Dateien (*.zip)")
        if not path:
            return
        answer = QMessageBox.question(
            self,
            "Sicherung laden",
            "Alle aktuellen Daten durch die Sicherung ersetzen? Die aktuellen Daten bleiben in einem Ordner neben dem"
            " Datenverzeichnis erhalten.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            previous = self.model.restore_backup(Path(path))
        except StorageError as e:
            QMessageBox.warning(self, "Sicherung laden", str(e))
            return
        if previous is not None:
            QMessageBox.information(self, "Sicherung laden", f"Die bisherigen Daten liegen jetzt in\n{previous}")
