"""List of all taggers with the number and sum of the transactions they tag."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from mymoneyvisualizer.app import TAGGERS, TRANSACTIONS
from mymoneyvisualizer.ui.common import Window
from mymoneyvisualizer.ui.table_model import MONEY, NUMBER, TAG, Column, DataFrameModel, DataFrameView

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

OVERVIEW_COLUMNS = [
    Column("name", "name", width=220),
    Column("tag", "tag", TAG, 220),
    Column("recurring", "recurring", NUMBER, 80),
    Column("count", "count", NUMBER, 80),
    Column("sum", "sum", MONEY, 110),
]


class TaggerOverviewWindow(Window):
    topics = frozenset({TAGGERS, TRANSACTIONS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Taggers")
        self.resize(800, 800)

        self.ok_button = QPushButton("OK", self)
        self.add_button = QPushButton("Add Tagger", self)
        self.delete_button = QPushButton("Delete Tagger", self)
        controls = QHBoxLayout()
        for button in (self.ok_button, self.add_button, self.delete_button):
            controls.addWidget(button)
        controls.addStretch(1)

        self.table_model = DataFrameModel(OVERVIEW_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(QLabel("Taggers are applied from top to bottom (unsorted); later ones win.", self))
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self.ok_button.clicked.connect(self.close)
        self.add_button.clicked.connect(lambda: navigator.open_tagger())
        self.delete_button.clicked.connect(self.delete_selected)
        self.table.doubleClicked.connect(self.open_tagger)

    def refresh(self) -> None:
        super().refresh()
        self.table_model.set_frame(self.model.tagger_overview())

    def open_tagger(self, index) -> None:
        self.navigator.open_tagger(name=self.table.row_at(index.row())["name"])

    def delete_selected(self) -> None:
        names = [row["name"] for row in self.table.selected_rows()]
        if names and self.confirm("Delete taggers", "Delete " + ", ".join(names) + "?"):
            self.model.delete_taggers(names)
