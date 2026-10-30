"""Categorize transactions: a rule for all matching transactions or a manual category for one. Saved on OK."""

from __future__ import annotations

import enum

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QCompleter,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import RULES, TRANSACTIONS, InvalidRuleError
from mymoneyvisualizer.domain.categorization import regex_error, regex_for, rule_matches
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import MAX_SPREAD_MONTHS, ManualCategory, Rule
from mymoneyvisualizer.ui.common import GREEN, GREY, RED, Window, line_edit_style
from mymoneyvisualizer.ui.table_model import (
    CATEGORY,
    DATE,
    MONEY,
    MONTHS,
    PERCENT,
    Column,
    DataFrameModel,
    DataFrameView,
    format_money,
    format_months,
)

PREVIEW_COLUMNS = [
    Column(Col.account, "account", width=110),
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=260),
    Column(Col.description, "description", width=460),
    Column(Col.value, "value", MONEY, 90),
    Column(Col.category, "category", CATEGORY, 150),
    Column(Col.spread_months, "spread", MONTHS, 80),
    Column(Col.residual_percent, "residual", PERCENT, 60),
]
#: longest proposed rule name taken from the recipient
NAME_LENGTH = 40
REGEX_HINT = "Regular expression searched in the text; | separates alternatives, empty matches everything."


class Mode(enum.Enum):
    RULE = "rule"
    MANUAL = "manual"


def proposed_name(recipient: str, description: str) -> str:
    text = " ".join((recipient.strip() or description.strip()).split())
    return text[:NAME_LENGTH].strip()


class SpreadEdit(QWidget):
    """Spread over a number of months or years, and the residual value of a purchase in percent."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.amount_spin = QSpinBox(self)
        self.amount_spin.setRange(0, MAX_SPREAD_MONTHS)
        self.amount_spin.setSpecialValueText("not spread")
        self.unit_combo = QComboBox(self)
        self.unit_combo.addItems(["months", "years"])
        self.residual_spin = QSpinBox(self)
        self.residual_spin.setRange(0, 99)
        self.residual_spin.setSuffix(" %")
        self.residual_spin.setToolTip("Expected value when you sell it, e.g. a car; it is not consumed.")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.amount_spin)
        layout.addWidget(self.unit_combo)
        layout.addSpacing(20)
        layout.addWidget(QLabel("Residual value:", self))
        layout.addWidget(self.residual_spin)
        layout.addStretch(1)
        self.residual_spin.setEnabled(False)
        for signal in (
            self.amount_spin.valueChanged,
            self.unit_combo.currentIndexChanged,
            self.residual_spin.valueChanged,
        ):
            signal.connect(self._changed)

    def months(self) -> int:
        return min(self.amount_spin.value() * (12 if self.unit_combo.currentIndex() == 1 else 1), MAX_SPREAD_MONTHS)

    def residual_percent(self) -> int:
        return self.residual_spin.value() if self.months() else 0

    def set_spread(self, months: int, residual_percent: int) -> None:
        in_years = months >= 12 and months % 12 == 0
        self.unit_combo.setCurrentIndex(1 if in_years else 0)
        self.amount_spin.setValue(months // 12 if in_years else months)
        self.residual_spin.setValue(residual_percent)

    def _changed(self, *_args) -> None:
        self.residual_spin.setEnabled(self.amount_spin.value() > 0)
        self.changed.emit()


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
        self.rule_radio = QRadioButton("all matching transactions (rule)", self)
        self.manual_radio = QRadioButton("only this transaction", self)
        self.rule_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rule_radio)
        self.mode_group.addButton(self.manual_radio)
        self.category_edit = QLineEdit(self)
        self.category_edit.setPlaceholderText("e.g. household.food; an account name marks an internal transfer")
        self.spread_edit = SpreadEdit(self)
        self.spread_hint = QLabel(self)
        self.sale_combo = QComboBox(self)
        self.sale_combo.setToolTip(
            "Selling something you spread over its useful life: its real loss of value (price minus sale proceeds)"
            " is spread over the months you owned it."
        )
        self.name_edit = QLineEdit(self)
        self.recipient_edit = QLineEdit(self)
        self.description_edit = QLineEdit(self)
        for edit in (self.recipient_edit, self.description_edit):
            edit.setToolTip(REGEX_HINT)
        self.message_label = QLabel(self)
        self.message_label.setStyleSheet("color: #b00020;")

        buttons = QHBoxLayout()
        buttons.addWidget(self.ok_button)
        buttons.addWidget(self.cancel_button)
        buttons.addStretch(1)
        apply_to = QHBoxLayout()
        apply_to.addWidget(self.rule_radio)
        apply_to.addWidget(self.manual_radio)
        apply_to.addStretch(1)
        form = QFormLayout()
        form.addRow("Apply to:", apply_to)
        form.addRow("Category:", self.category_edit)
        form.addRow("Spread over:", self.spread_edit)
        form.addRow("", self.spread_hint)
        self.sale_label = QLabel("Sale of:", self)
        form.addRow(self.sale_label, self.sale_combo)

        self.definition = QWidget(self)
        definition = QFormLayout(self.definition)
        definition.setContentsMargins(0, 0, 0, 0)
        definition.addRow("Rule name:", self.name_edit)
        definition.addRow("Recipient regex:", self.recipient_edit)
        definition.addRow("Description regex:", self.description_edit)

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self, background=self._background)
        self.table = DataFrameView(self.table_model, self, sortable=False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(buttons)
        layout.addLayout(form)
        layout.addWidget(self.definition)
        layout.addWidget(self.message_label)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        for edit in (self.category_edit, self.name_edit, self.recipient_edit, self.description_edit):
            edit.textChanged.connect(self._edited)
        self.spread_edit.changed.connect(self._edited)
        self.sale_combo.currentIndexChanged.connect(self._sale_changed)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.close)
        self.manual_radio.toggled.connect(lambda manual: self.set_mode(Mode.MANUAL if manual else Mode.RULE))

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
        """Edit the rule of a transaction or its manual category, or propose a rule for its recipient."""
        row = self.model.transaction(transaction_id)
        if row is None:
            self.open_new()
            return
        recipient, description = str(row[Col.recipient]), str(row[Col.description])
        # a new rule matches the recipient; the description often contains dates and references of one payment
        draft = Rule(
            self.model.free_rule_name(proposed_name(recipient, description)),
            regex_recipient=regex_for(recipient),
            regex_description="" if recipient.strip() else regex_for(description),
        )
        rule_name = row[Col.rule]
        manual = self.model.manual_categories.get(transaction_id)
        if rule_name == MANUAL_RULE and manual is not None:
            draft.category = manual.category
            draft.spread_months, draft.residual_percent = manual.spread_months, manual.residual_percent
            self._open(draft, None, transaction_id, Mode.MANUAL, sale_of=manual.sale_of)
        elif self.model.rule(rule_name) is not None:
            self._open(self.model.rule(rule_name), rule_name, transaction_id)
        else:
            self._open(draft, None, transaction_id)

    def _open(
        self,
        rule: Rule,
        original_name: str | None,
        transaction_id: str | None,
        mode: Mode = Mode.RULE,
        sale_of: str = "",
    ) -> None:
        self.original_name = original_name
        self.transaction_id = transaction_id
        self._loading = True
        try:
            self.name_edit.setText(rule.name)
            self.category_edit.setText(rule.category)
            self.spread_edit.set_spread(rule.spread_months, rule.residual_percent)
            self.recipient_edit.setText(rule.regex_recipient)
            self.description_edit.setText(rule.regex_description)
            self._fill_sales(sale_of)
        finally:
            self._loading = False
        completer = QCompleter(self.model.unique_categories() + self.model.account_names, self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.category_edit.setCompleter(completer)
        self.set_mode(mode)
        self.show()
        self.raise_()

    def _fill_sales(self, selected: str) -> None:
        """Purchases the transaction can be the sale of; only an incoming payment can be a sale."""
        self.sale_combo.clear()
        self.sale_combo.addItem("(no sale)", "")
        row = self.transaction()
        if row is not None and float(row[Col.value]) > 0:
            for _, purchase in self.model.sale_candidates(self.transaction_id).iterrows():
                text = (
                    f"{purchase[Col.date]:%d.%m.%Y}  {purchase[Col.recipient]}  "
                    f"{format_money(float(purchase[Col.value]))} €  ({purchase[Col.category]})"
                )
                self.sale_combo.addItem(text, purchase[Col.transaction_id])
        index = self.sale_combo.findData(selected)
        self.sale_combo.setCurrentIndex(max(index, 0))

    # ------------------------------------------------------------------ editing
    def transaction(self) -> pd.Series | None:
        return None if self.transaction_id is None else self.model.transaction(self.transaction_id)

    def sale_of(self) -> str:
        """The purchase this transaction is the sale of (only for a manual category)."""
        if self.mode != Mode.MANUAL:
            return ""
        return self.sale_combo.currentData() or ""

    def draft(self) -> Rule:
        return Rule(
            name=self.name_edit.text().strip(),
            category=self.category_edit.text().strip(),
            regex_recipient=self.recipient_edit.text(),
            regex_description=self.description_edit.text(),
            spread_months=self.spread_edit.months(),
            residual_percent=self.spread_edit.residual_percent(),
        )

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.MANUAL and self.transaction_id is None:
            mode = Mode.RULE
        self.mode = mode
        for radio, checked in ((self.manual_radio, mode == Mode.MANUAL), (self.rule_radio, mode == Mode.RULE)):
            radio.blockSignals(True)
            radio.setChecked(checked)
            radio.blockSignals(False)
        self.manual_radio.setEnabled(self.transaction_id is not None)
        self.definition.setHidden(mode == Mode.MANUAL)
        self.refresh()

    def _sale_changed(self, *_args) -> None:
        if self._loading:
            return
        purchase = self.model.transaction(self.sale_of()) if self.sale_of() else None
        if purchase is not None and not self.category_edit.text().strip():
            self.category_edit.setText(str(purchase[Col.category]))
        self._edited()

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
        """Title, regex colors, hints and the OK button; cheap enough for every key press."""
        self.setWindowTitle("Category of one transaction" if self.mode == Mode.MANUAL else self.draft().name or "Rule")
        errors = self.errors()
        self._matches = self.selected_matches(errors)
        for field, edit in (("regex_recipient", self.recipient_edit), ("regex_description", self.description_edit)):
            edit.setStyleSheet(line_edit_style(self._regex_color(field, errors)))
            edit.setToolTip(errors.get(field, REGEX_HINT))
        self.message_label.setText("\n".join(f"Invalid regex: {e}" for e in errors.values()))
        self.ok_button.setEnabled(not errors)
        selling = self.mode == Mode.MANUAL and self.sale_combo.count() > 1
        self.sale_label.setVisible(selling)
        self.sale_combo.setVisible(selling)
        self.spread_edit.setEnabled(not self.sale_of())
        self.spread_hint.setText(self.spread_text())
        self.table_model.layoutChanged.emit()  # colors of the first row

    def spread_text(self) -> str:
        """What the spread means for the transaction the window was opened for."""
        row = self.transaction()
        purchase = self.model.transaction(self.sale_of()) if self.sale_of() else None
        if row is not None and purchase is not None:
            first = pd.Period(purchase[Col.date], freq="M")
            months = (pd.Period(row[Col.date], freq="M") - first).n + 1
            loss = float(purchase[Col.value]) + float(row[Col.value])
            return (
                f"Price and sale proceeds: {format_money(loss)} € over the {format_months(months)} you owned it"
                f" → {format_money(loss / months)} € per month."
            )
        months, residual = self.spread_edit.months(), self.spread_edit.residual_percent()
        if not months:
            return "Counted in the month of payment."
        text = f"Spread evenly over {format_months(months)} from the month of payment"
        if row is None:
            return text + "."
        value = float(row[Col.value])
        text = f"{format_money(value)} € → {format_money(value * (1 - residual / 100) / months)} € per month"
        if residual:
            text += f"; residual value {format_money(-value * residual / 100, 0)} € stays an asset"
        return text + "."

    def preview(self):
        if self.mode == Mode.MANUAL:
            row = self.transaction()
            df = row.to_frame().T if row is not None else self.model.transactions().iloc[0:0].copy()
            draft = self.draft()
            df[Col.category] = draft.category
            df[Col.spread_months] = draft.spread_months
            df[Col.residual_percent] = draft.residual_percent
            return df
        return self.model.preview_rule(self.draft(), self.original_name, self.transaction_id)

    def selected_matches(self, errors: dict[str, str] | None = None) -> tuple[bool, bool] | None:
        """Whether the regexes match the transaction the window was opened for."""
        if self.transaction_id is None or (errors if errors is not None else self.errors()):
            return None
        row = self.transaction()
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
            if draft.category or self.sale_of():
                self.model.save_manual_category(
                    ManualCategory(
                        self.transaction_id,
                        draft.category,
                        spread_months=draft.spread_months,
                        residual_percent=draft.residual_percent,
                        sale_of=self.sale_of(),
                    )
                )
            else:
                self.model.remove_manual_category(self.transaction_id)
        else:
            try:
                self.model.save_rule(draft, self.original_name)
            except InvalidRuleError as e:
                self.show_error("Invalid rule", str(e))
                return False
            if self.transaction_id is not None:
                # the rule now applies to this transaction as well
                self.model.remove_manual_category(self.transaction_id)
        self.close()
        return True
