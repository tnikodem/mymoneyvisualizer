"""All rules in the order they are applied: what they match, what they set and what they categorize.

Category, spread and residual value are changed right in the table: select the cell and type. A double click opens
the rule with all its transactions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from PyQt6.QtCore import QModelIndex, Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLineEdit,
    QSpinBox,
    QStyledItemDelegate,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import RULES, TRANSACTIONS
from mymoneyvisualizer.domain.analysis import OVERRIDDEN
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import MAX_SPREAD_MONTHS
from mymoneyvisualizer.ui.common import HelpButton, Window, category_completer, make_button
from mymoneyvisualizer.ui.style import WARNING
from mymoneyvisualizer.ui.table_model import (
    CATEGORY,
    MONEY,
    MONTHS,
    NUMBER,
    PERCENT,
    Column,
    DataFrameModel,
    DataFrameView,
)

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

OVERVIEW_COLUMNS = [
    Column("position", "#", NUMBER, 40, tooltip="Reihenfolge: Passen mehrere Regeln, gewinnt die spätere."),
    Column("recipient", "Empfänger enthält", width=220, tooltip="Was im Empfänger stehen muss (leer: egal)."),
    Column(
        "description",
        "Verwendungszweck enthält",
        width=220,
        tooltip="Was im Verwendungszweck stehen muss (leer: egal).",
    ),
    Column(
        Col.category, "Kategorie", CATEGORY, 180, tooltip="Diese Kategorie bekommen die Buchungen. Tippen ändert sie."
    ),
    Column(
        Col.spread_months,
        "Verteilt über",
        MONTHS,
        100,
        tooltip="Im Budget wird jede Zahlung über so viele Monate verteilt, z. B. 12 für eine Jahresversicherung.",
    ),
    Column(
        Col.residual_percent,
        "Restwert",
        PERCENT,
        70,
        tooltip="Erwarteter Wiederverkaufswert in Prozent des Preises, z. B. beim Auto; zählt nicht als Verbrauch.",
    ),
    Column("count", "Buchungen", NUMBER, 95, tooltip="So viele Buchungen bekommen ihre Kategorie von dieser Regel."),
    Column(
        OVERRIDDEN,
        "überschrieben",
        NUMBER,
        115,
        tooltip="So viele Buchungen passen zwar auf die Regel, bekommen ihre Kategorie aber von einer späteren Regel"
        " oder einer Einzelzuordnung. Viele überschriebene und 0 Buchungen: Die Regel ist überflüssig oder steht an der"
        " falschen Stelle.",
    ),
    Column("sum", "Summe", MONEY, 100, tooltip="Summe dieser Buchungen."),
]
#: columns that are changed in the table; their keys are the names of the rule fields
EDITABLE = (Col.category, Col.spread_months, Col.residual_percent)
#: columns searched by the filter
FILTERED = ("recipient", "description", Col.category)
HELP = (
    "<p>Regeln werden in der Reihenfolge <b>#</b> angewendet; passen mehrere, gewinnt die spätere.</p>"
    "<p><b>Buchungen:</b> so viele bekommen ihre Kategorie von der Regel. <b>überschrieben:</b> so viele passen auch,"
    " bekommen ihre Kategorie aber von einer späteren Regel oder einer Einzelzuordnung.</p>"
    "<p>Kategorie, Verteilung und Restwert änderst du direkt in der Tabelle: Zelle anklicken und lostippen.</p>"
    "<p>Doppelklick öffnet die Regel mit allen ihren Buchungen. Eine neue Regel entsteht am schnellsten mit"
    " Doppelklick auf eine Buchung.</p>"
)


class RuleTableModel(DataFrameModel):
    """The overview; category, spread and residual value (of a spread rule) can be edited in place."""

    def __init__(self, window: RulesWindow):
        super().__init__(OVERVIEW_COLUMNS, window)
        self.window_ = window

    def key(self, index: QModelIndex) -> str:
        return self.columns[index.column()].key

    def editable(self, index: QModelIndex) -> bool:
        key = self.key(index)
        if key == Col.residual_percent:  # only a spread payment has a residual value
            return bool(self.frame[Col.spread_months].iloc[index.row()] > 0)
        return key in EDITABLE

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        flags = super().flags(index)
        if index.isValid() and self.editable(index):
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def data(self, index: QModelIndex, role=Qt.ItemDataRole.DisplayRole):
        if (
            index.isValid()
            and self.key(index) == OVERRIDDEN
            and role
            in (
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.ForegroundRole,
            )
        ):
            count = int(self.frame[OVERRIDDEN].iat[index.row()])
            if role == Qt.ItemDataRole.ForegroundRole:
                return QColor(WARNING) if count else None
            return str(count) if count else ""
        if role == Qt.ItemDataRole.EditRole and index.isValid() and self.editable(index):
            value = self.frame[self.key(index)].iloc[index.row()]
            return str(value) if self.key(index) == Col.category else int(value)
        return super().data(index, role)

    def setData(self, index: QModelIndex, value: Any, role=Qt.ItemDataRole.EditRole) -> bool:  # noqa: N802 (Qt API)
        if role != Qt.ItemDataRole.EditRole or not index.isValid() or not self.editable(index):
            return False
        self.window_.update_rule(self.row(index.row())["id"], self.key(index), value)
        return True


class RuleEditorDelegate(QStyledItemDelegate):
    """Editors in the table: the category with the known categories as proposals, spread and residual as spin boxes."""

    def __init__(self, window: RulesWindow):
        super().__init__(window)
        self.window_ = window

    def createEditor(self, parent: QWidget, option, index: QModelIndex) -> QWidget:  # noqa: N802 (Qt API)
        key = self.window_.table_model.key(index)
        if key == Col.category:
            editor = QLineEdit(parent)
            editor.setCompleter(category_completer(self.window_.model, editor))
            return editor
        spin = QSpinBox(parent)
        if key == Col.spread_months:
            spin.setRange(0, MAX_SPREAD_MONTHS)
            spin.setSuffix(" Monate")
            spin.setSpecialValueText("nicht verteilt")
        else:
            spin.setRange(0, 99)
            spin.setSuffix(" %")
        return spin


class RulesWindow(Window):
    topics = frozenset({RULES, TRANSACTIONS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Regeln")
        self.resize(1000, 800)
        self._overview = pd.DataFrame(columns=["id", *(c.key for c in OVERVIEW_COLUMNS)])

        self.ok_button = make_button("Schließen", "Das Fenster schließen; Änderungen sind schon gespeichert.", self)
        self.add_button = make_button(
            "Neue Regel",
            "Eine Regel von Hand anlegen. Schneller: Doppelklick auf eine Buchung, dann ist der Empfänger schon"
            " eingetragen.",
            self,
        )
        self.delete_button = make_button("Löschen", "Die markierten Regeln löschen.", self)
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Suchen …")
        self.filter_edit.setToolTip(
            "Nur Regeln, deren Empfänger, Verwendungszweck oder Kategorie alle eingegebenen Wörter enthalten"
        )
        self.filter_edit.setClearButtonEnabled(True)
        controls = QHBoxLayout()
        for button in (self.ok_button, self.add_button, self.delete_button):
            controls.addWidget(button)
        controls.addSpacing(20)
        controls.addWidget(self.filter_edit, 1)
        controls.addWidget(HelpButton(HELP, "Regeln", self))

        self.table_model = RuleTableModel(self)
        self.table = DataFrameView(self.table_model, self)
        self.delegate = RuleEditorDelegate(self)
        self.table.setItemDelegate(self.delegate)
        self.table.setEditTriggers(
            QAbstractItemView.EditTrigger.AnyKeyPressed | QAbstractItemView.EditTrigger.EditKeyPressed
        )
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addLayout(controls)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self.ok_button.clicked.connect(self.close)
        self.add_button.clicked.connect(lambda: navigator.open_rule())
        self.delete_button.clicked.connect(self.delete_selected)
        self.filter_edit.textChanged.connect(self.show_rules)
        self.table.doubleClicked.connect(self.open_rule)
        # connected after the view: the editor is closed when this runs
        self.delegate.closeEditor.connect(self._editor_closed)

    def refresh(self) -> None:
        if self.table.state() == QAbstractItemView.State.EditingState:
            self._dirty = True  # a refresh would close the open editor; it follows when the editor is closed
            return
        super().refresh()
        self._overview = self.model.rule_overview()
        self.show_rules()

    def _editor_closed(self, *_args) -> None:
        if self._dirty and self.isVisible():
            self.schedule_refresh()

    def show_rules(self) -> None:
        """Show the rules that match the filter; the current cell stays on its rule."""
        overview = self._overview
        words = self.filter_edit.text().lower().split()
        if words:
            text = overview[FILTERED[0]].str.cat([overview[key] for key in FILTERED[1:]], sep="\n").str.lower()
            mask = np.ones(len(overview), dtype=bool)
            for word in words:
                mask &= text.str.contains(word, regex=False).to_numpy(dtype=bool)
            overview = overview.loc[mask]

        current = self.table.currentIndex()
        current_id = self.table_model.row(current.row())["id"] if current.isValid() else None
        self.table_model.set_frame(overview)
        if current_id is not None:
            rows = np.flatnonzero(self.table_model.frame["id"].to_numpy() == current_id)
            if len(rows):
                self.table.setCurrentIndex(self.table_model.index(int(rows[0]), current.column()))

    def update_rule(self, rule_id: str, key: str, value: Any) -> None:
        """Change one field of a rule from the table."""
        self.model.update_rule(rule_id, **{key: str(value).strip() if key == Col.category else int(value)})

    def open_rule(self, index) -> None:
        self.navigator.open_rule(rule_id=self.table.row_at(index.row())["id"])

    def delete_selected(self) -> None:
        ids = [row["id"] for row in self.table.selected_rows()]
        text = "Die markierte Regel löschen?" if len(ids) == 1 else f"Die {len(ids)} markierten Regeln löschen?"
        if ids and self.confirm("Regeln löschen", text):
            self.model.delete_rules(ids)
