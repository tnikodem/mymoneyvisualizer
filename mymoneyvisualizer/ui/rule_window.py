"""Create or edit a rule, or categorize a single transaction. Nothing is saved before OK."""

from __future__ import annotations

import enum

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCompleter,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import RULES, TRANSACTIONS, InvalidRuleError
from mymoneyvisualizer.domain.categorization import regex_error, regex_for, rule_matches
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import Rule, clean_recurring
from mymoneyvisualizer.ui.common import GREEN, GREY, RED, Window, line_edit_style
from mymoneyvisualizer.ui.table_model import CATEGORY, DATE, MONEY, NUMBER, Column, DataFrameModel, DataFrameView

PREVIEW_COLUMNS = [
    Column(Col.account, "account", width=110),
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=260),
    Column(Col.description, "description", width=520),
    Column(Col.value, "value", MONEY, 90),
    Column(Col.recurring, "recurring", NUMBER, 70),
    Column(Col.category, "category", CATEGORY, 150),
]


class Mode(enum.Enum):
    RULE = "rule"
    MANUAL = "manual"


class RuleWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES})

    def __init__(self, model, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.resize(1300, 800)
        self.mode = Mode.RULE
        self.original_name: str | None = None
        self.transaction_id: str | None = None
        self._loading = False
        self._matches: tuple[bool, bool] | None = None

        self.ok_button = QPushButton("OK", self)
        self.ok_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel", self)
        self.mode_button = QPushButton("Manual category", self)
        self.category_edit = QLineEdit(self)
        self.recurring_edit = QLineEdit(self)
        self.recurring_edit.setValidator(QIntValidator(1, 100, self))
        self.recurring_edit.setPlaceholderText("every year")
        self.name_edit = QLineEdit(self)
        self.recipient_edit = QLineEdit(self)
        self.description_edit = QLineEdit(self)
        self.message_label = QLabel(self)
        self.message_label.setStyleSheet("color: #b00020;")

        controls = QHBoxLayout()
        controls.addWidget(self.ok_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(QLabel("Category:", self))
        controls.addWidget(self.category_edit, 1)
        controls.addWidget(QLabel("Recurring [years]:", self))
        controls.addWidget(self.recurring_edit)
        controls.addStretch(1)
        controls.addWidget(self.mode_button)

        self.definition = QWidget(self)
        form = QFormLayout(self.definition)
        form.addRow("Name:", self.name_edit)
        form.addRow("Recipient regex:", self.recipient_edit)
        form.addRow("Description regex:", self.description_edit)

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self, background=self._background)
        self.table = DataFrameView(self.table_model, self, sortable=False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.definition)
        layout.addWidget(self.message_label)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        for edit in (
            self.category_edit,
            self.recurring_edit,
            self.name_edit,
            self.recipient_edit,
            self.description_edit,
        ):
            edit.textChanged.connect(self._edited)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.close)
        self.mode_button.clicked.connect(self.toggle_mode)

    # ------------------------------------------------------------------ opening
    def open_new(self) -> None:
        self._open(Rule(self.model.free_rule_name()), original_name=None, transaction_id=None)

    def open_rule(self, name: str) -> None:
        rule = self.model.rule(name)
        if rule is None:
            self.open_new()
        else:
            self._open(rule, original_name=name, transaction_id=None)

    def open_for_transaction(self, transaction_id: str) -> None:
        """Edit the rule of a transaction, its manual category, or propose a new rule matching it."""
        row = self.model.transaction(transaction_id)
        if row is None:
            self.open_new()
            return
        rule_name = row[Col.rule]
        if rule_name == MANUAL_RULE:
            draft = Rule(
                self.model.free_rule_name(),
                category=row[Col.category],
                recurring=clean_recurring(row[Col.recurring]),
                regex_recipient=regex_for(row[Col.recipient]),
                regex_description=regex_for(row[Col.description]),
            )
            self._open(draft, original_name=None, transaction_id=transaction_id, mode=Mode.MANUAL)
        elif self.model.rule(rule_name) is not None:
            self._open(self.model.rule(rule_name), original_name=rule_name, transaction_id=transaction_id)
        else:
            draft = Rule(
                self.model.free_rule_name(),
                regex_recipient=regex_for(row[Col.recipient]),
                regex_description=regex_for(row[Col.description]),
            )
            self._open(draft, original_name=None, transaction_id=transaction_id)

    def _open(self, rule: Rule, original_name: str | None, transaction_id: str | None, mode: Mode = Mode.RULE) -> None:
        self.original_name = original_name
        self.transaction_id = transaction_id
        self._loading = True
        try:
            self.name_edit.setText(rule.name)
            self.category_edit.setText(rule.category)
            self.recurring_edit.setText("" if rule.recurring is None else str(rule.recurring))
            self.recipient_edit.setText(rule.regex_recipient)
            self.description_edit.setText(rule.regex_description)
        finally:
            self._loading = False
        completer = QCompleter(self.model.unique_categories(), self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.category_edit.setCompleter(completer)
        self.set_mode(mode)
        self.show()
        self.raise_()

    # ------------------------------------------------------------------ editing
    def draft(self) -> Rule:
        return Rule(
            name=self.name_edit.text().strip(),
            category=self.category_edit.text().strip(),
            regex_recipient=self.recipient_edit.text(),
            regex_description=self.description_edit.text(),
            recurring=clean_recurring(self.recurring_edit.text()),
        )

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.MANUAL and self.transaction_id is None:
            mode = Mode.RULE
        self.mode = mode
        self.definition.setHidden(mode == Mode.MANUAL)
        self.mode_button.setText("Rule" if mode == Mode.MANUAL else "Manual category")
        self.mode_button.setEnabled(self.transaction_id is not None)
        self.refresh()

    def toggle_mode(self) -> None:
        self.set_mode(Mode.RULE if self.mode == Mode.MANUAL else Mode.MANUAL)

    def errors(self) -> dict[str, str]:
        if self.mode == Mode.MANUAL:
            return {}
        draft = self.draft()
        errors = {}
        for field, pattern in (
            ("regex_recipient", draft.regex_recipient),
            ("regex_description", draft.regex_description),
        ):
            error = regex_error(pattern)
            if error is not None:
                errors[field] = error
        return errors

    def _edited(self, *_args) -> None:
        """Validate at once, update the (possibly large) preview when typing pauses."""
        if self._loading:
            return
        self.update_state()
        self.schedule_refresh()

    def refresh(self, *_args) -> None:
        if self._loading:
            return
        super().refresh()
        self.update_state()
        self.table_model.set_frame(self.preview())

    def update_state(self) -> None:
        """Title, regex colors and the OK button; cheap enough for every key press."""
        self.setWindowTitle("Manual category" if self.mode == Mode.MANUAL else self.draft().name or "Rule")
        errors = self.errors()
        self._matches = self.selected_matches(errors)
        for field, edit in (("regex_recipient", self.recipient_edit), ("regex_description", self.description_edit)):
            edit.setStyleSheet(line_edit_style(self._regex_color(field, errors)))
            edit.setToolTip(errors.get(field, ""))
        self.message_label.setText("\n".join(f"Invalid regex: {e}" for e in errors.values()))
        self.ok_button.setEnabled(not errors)
        self.table_model.layoutChanged.emit()  # colors of the first row

    def preview(self):
        draft = self.draft()
        if self.mode == Mode.MANUAL:
            row = self.model.transaction(self.transaction_id)
            df = row.to_frame().T if row is not None else self.model.transactions().iloc[0:0].copy()
            df[Col.category] = draft.category
            df[Col.recurring] = float("nan") if draft.recurring is None else float(draft.recurring)
            return df
        return self.model.preview_rule(draft, self.original_name, self.transaction_id)

    def selected_matches(self, errors: dict[str, str] | None = None) -> tuple[bool, bool] | None:
        """Whether the regexes match the transaction the window was opened for."""
        if self.transaction_id is None or (errors if errors is not None else self.errors()):
            return None
        row = self.model.transaction(self.transaction_id)
        if row is None:
            return None
        return rule_matches(self.draft(), row[Col.recipient], row[Col.description])

    def _regex_color(self, field: str, errors: dict[str, str]):
        if field in errors:
            return RED
        if self._matches is None:
            return None
        return GREEN if self._matches[0 if field == "regex_recipient" else 1] else RED

    def _background(self, row: int, key: str):
        if row != 0 or self.transaction_id is None:
            return None
        frame = self.table_model.frame
        if frame.empty or frame[Col.transaction_id].iloc[0] != self.transaction_id:
            return None
        if self.mode == Mode.MANUAL:
            return GREY
        return GREY if self._matches is None else (GREEN if all(self._matches) else RED)

    # ------------------------------------------------------------------ saving
    def accept(self) -> bool:
        draft = self.draft()
        if self.mode == Mode.MANUAL:
            if draft.category:
                self.model.set_manual_category(self.transaction_id, draft.category, draft.recurring)
            else:
                self.model.remove_manual_category(self.transaction_id)
        else:
            try:
                self.model.save_rule(draft, self.original_name)
            except InvalidRuleError as e:
                self.show_error("Invalid rule", str(e))
                return False
        self.close()
        return True
