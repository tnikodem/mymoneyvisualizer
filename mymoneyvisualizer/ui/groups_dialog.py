"""Budget groups of the main categories and the targets of the 50/30/20 rule, in a window of its own."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import GROUPS, SETTINGS, TRANSACTIONS, AppModel
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.models import GROUP_INCOME, GROUP_NEEDS, GROUP_SAVINGS, GROUP_WANTS
from mymoneyvisualizer.domain.models import GROUPS as GROUP_NAMES
from mymoneyvisualizer.ui.common import ModelBridge, make_button, make_label
from mymoneyvisualizer.ui.style import SERIES, TEXT

TITLES = {
    GROUP_INCOME: "Einkommen",
    GROUP_NEEDS: "Grundbedarf",
    GROUP_WANTS: "Freizeit & Lebensstil",
    GROUP_SAVINGS: "Sparen",
}
HINTS = {
    GROUP_INCOME: "Nettoeinkommen: Gehalt, Kindergeld, Zinsen, Erstattungen.",
    GROUP_NEEDS: "Notwendige Ausgaben: Miete, Energie, Lebensmittel, Versicherungen, Mobilität, Kinderbetreuung.",
    GROUP_WANTS: "Verzichtbare Ausgaben: Freizeit, Restaurant, Urlaub, Hobbys, Abos, Anschaffungen.",
    GROUP_SAVINGS: "Sparpläne und Geldanlagen, die hier kein eigenes Konto sind, z. B. ein ETF-Sparplan.",
}
GROUP_COLORS = {GROUP_INCOME: TEXT, GROUP_NEEDS: SERIES[0], GROUP_WANTS: SERIES[1], GROUP_SAVINGS: SERIES[2]}


def dot_icon(color: str) -> QIcon:
    """A colored dot, the color of the group in the chart."""
    pixmap = QPixmap(12, 12)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(1, 1, 10, 10)
    painter.end()
    return QIcon(pixmap)


class GroupsDialog(QDialog):
    """Four lists, one per budget group: drag a category into another list or use its context menu.

    Every change is saved at once; the target shares of needs and wants are set below their lists.
    """

    def __init__(self, model: AppModel, parent: QWidget | None = None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("Gruppen & Ziele")
        self.resize(900, 520)
        self._filling = False
        self.lists: dict[str, QListWidget] = {}
        self.spins: dict[str, QSpinBox] = {}
        self.savings_label = make_label("", self, "hint")

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        for column, group in enumerate(GROUP_NAMES):
            title = make_label(TITLES[group], self, "heading")
            header = QHBoxLayout()
            header.setSpacing(6)
            dot = make_label("", self)
            dot.setPixmap(dot_icon(GROUP_COLORS[group]).pixmap(12, 12))
            header.addWidget(dot)
            header.addWidget(title, 1)
            grid.addLayout(header, 0, column)
            grid.addWidget(make_label(HINTS[group], self, "hint", wrap=True), 1, column, Qt.AlignmentFlag.AlignTop)
            widget = QListWidget(self)
            widget.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            widget.setDefaultDropAction(Qt.DropAction.MoveAction)
            widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            widget.customContextMenuRequested.connect(lambda pos, g=group: self._context_menu(g, pos))
            for signal in (widget.model().rowsInserted, widget.model().rowsRemoved, widget.model().rowsMoved):
                signal.connect(self._lists_changed)
            grid.addWidget(widget, 2, column)
            self.lists[group] = widget
            if group in (GROUP_NEEDS, GROUP_WANTS):
                spin = QSpinBox(self)
                spin.setRange(0, 100)
                spin.setPrefix("Ziel ")
                spin.setSuffix(" % des Einkommens")
                spin.setToolTip(f"Höchstens so viel des Einkommens für {TITLES[group]}; Sparen erhält den Rest.")
                spin.valueChanged.connect(lambda value, g=group: self._share_changed(g, value))
                grid.addWidget(spin, 3, column)
                self.spins[group] = spin
            elif group == GROUP_SAVINGS:
                grid.addWidget(self.savings_label, 3, column)
        grid.setRowStretch(2, 1)

        self.close_button = make_button("Schließen", "Änderungen sind schon gespeichert.", self)
        self.close_button.clicked.connect(self.close)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.close_button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.addWidget(
            make_label(
                "Ziehe eine Kategorie mit der Maus in die passende Gruppe, oder Rechtsklick › Verschieben nach."
                " Änderungen gelten sofort.",
                self,
                wrap=True,
            )
        )
        layout.addLayout(grid, 1)
        layout.addLayout(buttons)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.timeout.connect(self.save)
        self.bridge = ModelBridge(model, self)
        self.bridge.changed.connect(self._on_changed)
        self.refresh()

    def _on_changed(self, topics: frozenset[str]) -> None:
        if topics & {GROUPS, SETTINGS, TRANSACTIONS} and not self._save_timer.isActive():
            self.refresh()

    def refresh(self) -> None:
        settings = self.model.settings
        self._filling = True
        try:
            for group, widget in self.lists.items():
                widget.clear()
                for assignment in self.model.groups:
                    if assignment.group == group:
                        item = QListWidgetItem(display_category(assignment.category))
                        item.setData(Qt.ItemDataRole.UserRole, assignment.category)
                        widget.addItem(item)
            for group, spin in self.spins.items():
                spin.setValue(round(settings.budget_shares.get(group, 0.0) * 100))
            self.savings_label.setText(f"Ziel {round(settings.savings_share * 100)} % des Einkommens (der Rest)")
        finally:
            self._filling = False

    def assignment(self) -> dict[str, list[str]]:
        return {
            group: [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]
            for group, widget in self.lists.items()
        }

    def save(self) -> None:
        self.model.assign_groups(self.assignment())

    def _lists_changed(self, *_args) -> None:
        if not self._filling:
            self._save_timer.start(0)  # after the drop is complete

    def _share_changed(self, group: str, value: int) -> None:
        if not self._filling:
            self.model.set_budget_share(group, value / 100)

    def move(self, categories: list[str], group: str) -> None:
        """Put main categories into ``group`` (at its end)."""
        assignment = {g: [c for c in members if c not in categories] for g, members in self.assignment().items()}
        assignment[group] += categories
        self.model.assign_groups(assignment)

    def _context_menu(self, group: str, position) -> None:
        widget = self.lists[group]
        categories = [item.data(Qt.ItemDataRole.UserRole) for item in widget.selectedItems()]
        if not categories:
            return
        menu = QMenu(self)
        target = menu.addMenu("Verschieben nach")
        for other in GROUP_NAMES:
            if other != group:
                action = QAction(dot_icon(GROUP_COLORS[other]), TITLES[other], target)
                action.triggered.connect(lambda _checked=False, g=other: self.move(categories, g))
                target.addAction(action)
        menu.exec(widget.viewport().mapToGlobal(position))
