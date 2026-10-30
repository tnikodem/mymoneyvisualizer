"""Categorize transactions: a rule for all matching transactions or a manual category for one. Saved on OK."""

from __future__ import annotations

import enum

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import RULES, TRANSACTIONS, InvalidRuleError
from mymoneyvisualizer.domain.analysis import OVERRIDDEN
from mymoneyvisualizer.domain.categorization import readable_pattern, regex_error, regex_for, rule_matches
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import MAX_SPREAD_MONTHS, ManualCategory, Rule, new_rule_id
from mymoneyvisualizer.ui.common import (
    GREEN,
    GREY,
    RED,
    TOTAL_BACKGROUND,
    Card,
    HelpButton,
    Window,
    category_completer,
    line_edit_style,
    make_button,
    make_label,
    set_tone,
)
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

#: column of the preview: who takes a matched transaction from the rule
TAKEN = "taken"
PREVIEW_COLUMNS = [
    Column(Col.account, "Konto", width=110),
    Column(Col.date, "Datum", DATE, 90),
    Column(Col.recipient, "Empfänger", width=220),
    Column(Col.description, "Verwendungszweck", width=340),
    Column(Col.value, "Betrag", MONEY, 110),
    Column(Col.category, "Kategorie", CATEGORY, 150),
    Column(
        TAKEN,
        "überschrieben von",
        width=130,
        tooltip="Die Regel passt, aber die Buchung bekommt ihre Kategorie von einer späteren Regel oder einer"
        " Einzelzuordnung.",
    ),
    Column(Col.spread_months, "Verteilt über", MONTHS, 90),
    Column(Col.residual_percent, "Restwert", PERCENT, 70),
]
REGEX_HINT = (
    "Text, der vorkommen muss; Groß- und Kleinschreibung zählt. Leer: egal.\n"
    "Für Fortgeschrittene ein regulärer Ausdruck: | trennt Alternativen (REWE|EDEKA), ^ heißt am Anfang."
)


def match_text(rule: Rule) -> str:
    """What a rule matches, in plain words."""
    conditions = [
        f"{label} „{readable_pattern(pattern)}“"
        for label, pattern in (("Empfänger", rule.regex_recipient), ("Verwendungszweck", rule.regex_description))
        if pattern
    ]
    if not conditions:
        return "Ohne Text in beiden Feldern erfasst die Regel alle Buchungen."
    if len(conditions) == 1:
        return f"Erfasst alle Buchungen, deren {conditions[0]} enthält."
    return f"Erfasst alle Buchungen, deren {conditions[0]} und deren {conditions[1]} enthalten."


MODE_HELP = (
    "<p><b>Regel:</b> gibt allen Buchungen die Kategorie, deren Empfänger und Verwendungszweck die Texte enthalten,"
    " auch künftig importierten.</p>"
    "<p><b>Nur diese Buchung</b> gilt vor allen Regeln, z. B. für einen einmaligen Kauf.</p>"
)
SPREAD_HELP = (
    "<p><b>Verteilen über:</b> verteilt jede Zahlung im Budget auf ihre Laufzeit oder Nutzungsdauer, z. B."
    " Jahresversicherung 12 Monate, Sofa 10 Jahre.</p>"
    "<p><b>Restwert:</b> der erwartete Wiederverkaufswert, z. B. beim Auto. Er ist kein Verbrauch; verteilt wird nur"
    " der Wertverlust.</p>"
)
PREVIEW_HELP = (
    "<p>Oben die Buchung, von der du kommst: grün, wenn die Regel sie erfasst, rot, wenn nicht. Ebenso färben sich die"
    " Felder Empfänger und Verwendungszweck.</p>"
    "<p>Grau sind Buchungen, auf die die Regel passt, die ihre Kategorie aber von einer späteren Regel (passen mehrere,"
    " gewinnt die spätere) oder einer Einzelzuordnung bekommen.</p>"
)


class Mode(enum.Enum):
    RULE = "rule"
    MANUAL = "manual"


class SpreadEdit(QWidget):
    """Spread over a number of months or years, and the residual value of a purchase in percent."""

    changed = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.amount_spin = QSpinBox(self)
        self.amount_spin.setRange(0, MAX_SPREAD_MONTHS)
        self.amount_spin.setSpecialValueText("nicht verteilt")
        self.amount_spin.setToolTip(
            "Über wie viele Monate oder Jahre die Zahlung im Budget verteilt wird: die Laufzeit einer"
            " Jahresversicherung (12 Monate) oder die Nutzungsdauer einer Anschaffung (Sofa 10 Jahre, Laptop 4 Jahre)."
        )
        self.unit_combo = QComboBox(self)
        self.unit_combo.addItems(["Monate", "Jahre"])
        self.residual_spin = QSpinBox(self)
        self.residual_spin.setRange(0, 99)
        self.residual_spin.setSuffix(" %")
        self.residual_spin.setToolTip(
            "Was die Sache am Ende noch wert ist, in Prozent des Preises, z. B. beim Auto. Dieser Teil ist kein"
            " Verbrauch, sondern bleibt Vermögen."
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.amount_spin)
        layout.addWidget(self.unit_combo)
        layout.addSpacing(20)
        layout.addWidget(QLabel("Restwert:", self))
        layout.addWidget(self.residual_spin)
        layout.addWidget(HelpButton(SPREAD_HELP, "Verteilen", self))
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
    """Opens with the cursor in the category: type it, Enter saves (like OK), Escape cancels."""

    topics = frozenset({TRANSACTIONS, RULES})

    def __init__(self, model, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.resize(1300, 800)
        self.mode = Mode.RULE
        self.original_id: str | None = None
        self._draft_id = new_rule_id()
        self.transaction_id: str | None = None
        self._loading = False
        self._matches: tuple[bool, bool] | None = None

        self.ok_button = make_button("Speichern", "Speichern und schließen (Enter)", self, primary=True)
        self.ok_button.setDefault(True)
        self.cancel_button = make_button("Abbrechen", "Nichts ändern und schließen (Esc)", self)
        self.cancel_button.setAutoDefault(True)  # Enter on the focused button cancels instead of saving
        self.title = make_label("", self, "heading")
        self.rule_radio = QRadioButton("alle passenden Buchungen (Regel)", self)
        self.rule_radio.setToolTip(
            "Eine Regel gibt allen Buchungen die Kategorie, deren Empfänger und Verwendungszweck die Texte unten"
            " enthalten, auch künftig importierten."
        )
        self.manual_radio = QRadioButton("nur diese Buchung", self)
        self.manual_radio.setToolTip(
            "Nur diese eine Buchung bekommt die Kategorie, z. B. ein einmaliger Kauf; das gilt vor allen Regeln."
        )
        self.rule_radio.setChecked(True)
        self.mode_group = QButtonGroup(self)
        self.mode_group.addButton(self.rule_radio)
        self.mode_group.addButton(self.manual_radio)
        self.category_edit = QLineEdit(self)
        self.category_edit.setPlaceholderText("z. B. Wohnen.Miete oder Lebensmittel")
        self.category_edit.setToolTip(
            "Hauptkategorie und Unterkategorien mit Punkt getrennt, z. B. Wohnen.Miete. Vorschläge erscheinen beim"
            " Tippen. Der Name eines eigenen Kontos als Kategorie macht die Buchung zur Umbuchung."
        )
        self.spread_edit = SpreadEdit(self)
        self.spread_hint = make_label("", self, "hint")
        self.sale_combo = QComboBox(self)
        self.sale_combo.setToolTip(
            "Der Verkauf von etwas, das über seine Nutzungsdauer verteilt wurde: Der echte Wertverlust (Preis minus"
            " Verkaufserlös) wird über die Monate verteilt, die du es hattest."
        )
        self.recipient_edit = QLineEdit(self)
        self.description_edit = QLineEdit(self)
        for edit in (self.recipient_edit, self.description_edit):
            edit.setToolTip(REGEX_HINT)
        self.message_label = make_label("", self, wrap=True)
        set_tone(self.message_label, "bad")
        self.preview_label = make_label("", self, "hint")

        buttons = QHBoxLayout()
        buttons.addWidget(self.title, 1)
        buttons.addWidget(self.cancel_button)
        buttons.addWidget(self.ok_button)
        apply_to = QHBoxLayout()
        apply_to.addWidget(self.rule_radio)
        apply_to.addWidget(self.manual_radio)
        apply_to.addWidget(HelpButton(MODE_HELP, "Regel oder nur diese Buchung", self))
        apply_to.addStretch(1)
        form = QFormLayout()
        form.addRow("Gilt für:", apply_to)
        form.addRow("Kategorie:", self.category_edit)
        form.addRow("Verteilen über:", self.spread_edit)
        form.addRow("", self.spread_hint)
        self.sale_label = QLabel("Verkauf von:", self)
        form.addRow(self.sale_label, self.sale_combo)

        self.definition = QWidget(self)
        definition = QFormLayout(self.definition)
        definition.setContentsMargins(0, 0, 0, 0)
        definition.addRow("Empfänger enthält:", self.recipient_edit)
        definition.addRow("Verwendungszweck enthält:", self.description_edit)
        self.match_hint = make_label("", self, "hint", wrap=True)
        definition.addRow("", self.match_hint)

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self, background=self._background)
        self.table = DataFrameView(self.table_model, self, sortable=False)

        card = Card(self)
        card.content.addLayout(form)
        card.content.addWidget(self.definition)
        card.content.addWidget(self.message_label)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        layout.addLayout(buttons)
        layout.addWidget(card)
        preview = QHBoxLayout()
        preview.addWidget(self.preview_label)
        preview.addWidget(HelpButton(PREVIEW_HELP, "Vorschau", self))
        preview.addStretch(1)
        layout.addLayout(preview)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        for edit in (self.category_edit, self.recipient_edit, self.description_edit):
            edit.textChanged.connect(self._edited)
        self.spread_edit.changed.connect(self._edited)
        self.sale_combo.currentIndexChanged.connect(self._sale_changed)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.close)
        self.manual_radio.toggled.connect(lambda manual: self.set_mode(Mode.MANUAL if manual else Mode.RULE))

    # ------------------------------------------------------------------ opening
    def open_new(self) -> None:
        self._open(Rule(), original_id=None, transaction_id=None)

    def open_rule(self, rule_id: str) -> None:
        rule = self.model.rule(rule_id)
        if rule is None:
            self.open_new()
        else:
            self._open(rule, original_id=rule_id, transaction_id=None)

    def open_for_transaction(self, transaction_id: str) -> None:
        """Edit the rule of a transaction or its manual category, or propose a rule for its recipient."""
        row = self.model.transaction(transaction_id)
        if row is None:
            self.open_new()
            return
        recipient, description = str(row[Col.recipient]), str(row[Col.description])
        # a new rule matches the recipient; the description often contains dates and references of one payment
        draft = Rule(
            regex_recipient=regex_for(recipient),
            regex_description="" if recipient.strip() else regex_for(description),
        )
        rule = self.model.rule(row[Col.rule])
        manual = self.model.manual_categories.get(transaction_id)
        if row[Col.rule] == MANUAL_RULE and manual is not None:
            draft.category = manual.category
            draft.spread_months, draft.residual_percent = manual.spread_months, manual.residual_percent
            self._open(draft, None, transaction_id, Mode.MANUAL, sale_of=manual.sale_of)
        elif rule is not None:
            self._open(rule, rule.id, transaction_id)
        else:
            self._open(draft, None, transaction_id)

    def _open(
        self,
        rule: Rule,
        original_id: str | None,
        transaction_id: str | None,
        mode: Mode = Mode.RULE,
        sale_of: str = "",
    ) -> None:
        self.original_id = original_id
        self._draft_id = original_id or new_rule_id()
        self.transaction_id = transaction_id
        self._loading = True
        try:
            self.category_edit.setText(rule.category)
            self.spread_edit.set_spread(rule.spread_months, rule.residual_percent)
            self.recipient_edit.setText(rule.regex_recipient)
            self.description_edit.setText(rule.regex_description)
            self._fill_sales(sale_of)
        finally:
            self._loading = False
        self.category_edit.setCompleter(category_completer(self.model, self))
        self.set_mode(mode)
        self.show()
        self.raise_()
        self.category_edit.setFocus()

    def _fill_sales(self, selected: str) -> None:
        """Purchases the transaction can be the sale of; only an incoming payment can be a sale."""
        self.sale_combo.clear()
        self.sale_combo.addItem("(kein Verkauf)", "")
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
        draft = Rule(
            category=self.category_edit.text().strip(),
            regex_recipient=self.recipient_edit.text(),
            regex_description=self.description_edit.text(),
            spread_months=self.spread_edit.months(),
            residual_percent=self.spread_edit.residual_percent(),
        )
        draft.id = self._draft_id
        return draft

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
        frame = self.preview()
        self.table_model.set_frame(frame)
        self.preview_label.setText(self.preview_text(frame))

    def preview_text(self, frame: pd.DataFrame) -> str:
        if self.mode == Mode.MANUAL:
            return "Vorschau: nur diese Buchung"
        count = int((frame[Col.rule] == self._draft_id).sum()) if not frame.empty else 0
        text = f"Vorschau: {count} {'Buchung' if count == 1 else 'Buchungen'} erfasst"
        taken = int((frame[TAKEN] != "").sum()) if TAKEN in frame else 0
        if taken:
            text += f" · {taken} weitere überschrieben (grau)"
        return text

    def update_state(self) -> None:
        """Title, regex colors, hints and the OK button; cheap enough for every key press."""
        if self.mode == Mode.MANUAL:
            self.setWindowTitle("Kategorie einer Buchung")
        else:
            self.setWindowTitle("Neue Regel" if self.original_id is None else "Regel bearbeiten")
        self.title.setText(self.windowTitle())
        errors = self.errors()
        self._matches = self.selected_matches(errors)
        for field, edit in (("regex_recipient", self.recipient_edit), ("regex_description", self.description_edit)):
            edit.setStyleSheet(line_edit_style(self._regex_color(field, errors)))
            edit.setToolTip(errors.get(field, REGEX_HINT))
        self.message_label.setText("\n".join(f"Ungültiger regulärer Ausdruck: {e}" for e in errors.values()))
        self.message_label.setVisible(bool(errors))
        self.match_hint.setText("" if errors else match_text(self.draft()))
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
                f"Preis und Verkaufserlös: {format_money(loss)} € über die {format_months(months)}, die du es hattest"
                f" → {format_money(loss / months)} € pro Monat."
            )
        months, residual = self.spread_edit.months(), self.spread_edit.residual_percent()
        if not months:
            return "Zählt im Monat der Zahlung."
        text = f"Gleichmäßig verteilt über {format_months(months)} ab dem Monat der Zahlung"
        if row is None:
            return text + "."
        value = float(row[Col.value])
        text = f"{format_money(value)} € → {format_money(value * (1 - residual / 100) / months)} € pro Monat"
        if residual:
            text += f"; Restwert {format_money(-value * residual / 100, 0)} € bleibt Vermögen"
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
        frame = self.model.preview_rule(self.draft(), self.original_id, self.transaction_id)
        positions = {rule.id: i for i, rule in enumerate(self.model.rules, start=1)}
        frame[TAKEN] = [
            "" if not winner else "Einzelzuordnung" if winner == MANUAL_RULE else f"Regel #{positions.get(winner, '?')}"
            for winner in frame[OVERRIDDEN]
        ]
        return frame

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
        frame = self.table_model.frame
        if row != 0 or self.transaction_id is None or frame[Col.transaction_id].iloc[0] != self.transaction_id:
            # a transaction the rule matches that another rule or a manual category takes
            return TOTAL_BACKGROUND if TAKEN in frame and frame[TAKEN].iat[row] else None
        if self.mode == Mode.MANUAL:
            return GREY
        return GREY if self._matches is None else (GREEN if all(self._matches) else RED)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        """Keys the fields leave alone. While the category completer shows proposals, it takes Enter itself."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if self.ok_button.isEnabled():
                self.accept()
        elif event.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

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
                self.model.save_rule(draft, self.original_id)
            except InvalidRuleError as e:
                self.show_error("Ungültige Regel", str(e))
                return False
            if self.transaction_id is not None:
                # the rule now applies to this transaction as well
                self.model.remove_manual_category(self.transaction_id)
        self.close()
        return True
