"""Start window. Creates the other windows on first use and connects them."""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from PyQt6.QtWidgets import QLabel, QMainWindow, QPushButton, QVBoxLayout, QWidget

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.ui.accounts_window import AccountsWindow
from mymoneyvisualizer.ui.common import ModelBridge
from mymoneyvisualizer.ui.graph_window import GraphWindow
from mymoneyvisualizer.ui.import_window import ImportWindow
from mymoneyvisualizer.ui.summary_window import DetailWindow, SummaryWindow
from mymoneyvisualizer.ui.tagger_overview_window import TaggerOverviewWindow
from mymoneyvisualizer.ui.tagger_window import TaggerWindow


class MainWindow(QMainWindow):
    def __init__(self, model: AppModel):
        super().__init__()
        self.model = model
        self.bridge = ModelBridge(model, self)
        self.setWindowTitle("My Money Visualiser")

        self.accounts_button = QPushButton("Accounts", self)
        self.summary_button = QPushButton("Summary Table", self)
        self.graph_button = QPushButton("Summary Graph", self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        for button in (self.accounts_button, self.summary_button, self.graph_button):
            button.setMinimumSize(250, 32)
            layout.addWidget(button)
        location = QLabel(f"Data: {model.repository.data_dir}", self)
        location.setWordWrap(True)
        layout.addWidget(location)
        self.setCentralWidget(central)

        self.accounts_button.clicked.connect(self.show_accounts)
        self.summary_button.clicked.connect(self.show_summary)
        self.graph_button.clicked.connect(self.show_graph)

    def closeEvent(self, event) -> None:  # noqa: N802 (Qt API)
        self.bridge.detach()
        super().closeEvent(event)

    # ------------------------------------------------------------------ windows (created lazily)
    @cached_property
    def accounts_window(self) -> AccountsWindow:
        return AccountsWindow(self.model, self.bridge, self)

    @cached_property
    def summary_window(self) -> SummaryWindow:
        return SummaryWindow(self.model, self.bridge, self)

    @cached_property
    def graph_window(self) -> GraphWindow:
        return GraphWindow(self.model, self.bridge, self)

    @cached_property
    def tagger_window(self) -> TaggerWindow:
        return TaggerWindow(self.model, self.bridge, self)

    @cached_property
    def tagger_overview_window(self) -> TaggerOverviewWindow:
        return TaggerOverviewWindow(self.model, self.bridge, self)

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

    def show_summary(self) -> None:
        self._show(self.summary_window)

    def show_graph(self) -> None:
        self._show(self.graph_window)

    def show_tagger_overview(self) -> None:
        self._show(self.tagger_overview_window)

    def open_tagger(self, name: str | None = None, transaction_id: str | None = None) -> None:
        if transaction_id is not None:
            self.tagger_window.open_for_transaction(transaction_id)
        elif name is not None:
            self.tagger_window.open_tagger(name)
        else:
            self.tagger_window.open_new()

    def open_detail(self, month: str, tag: str | None, tag_filter: str = "") -> None:
        self.detail_window.open_detail(month, tag, tag_filter)

    def open_import(self, path: str | Path, account: str) -> None:
        self.import_window.open_file(path, account)
