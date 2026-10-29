"""Building blocks shared by the windows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QMainWindow, QMessageBox, QWidget
from pyqt6_multiselect_combobox import MultiSelectComboBox

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.tags import display_tag

GREY = QColor(123, 123, 123)
GREEN = QColor(203, 255, 179)
RED = QColor(255, 122, 111)
TOTAL_BACKGROUND = QColor(0, 0, 0, 40)
MORE_EXPENSE = QColor(255, 196, 186)
LESS_EXPENSE = QColor(206, 242, 196)

PLOT_COLORS = [
    (246, 112, 136),
    (219, 136, 49),
    (173, 156, 49),
    (119, 170, 49),
    (51, 176, 122),
    (53, 172, 164),
    (56, 168, 197),
    (110, 154, 244),
    (204, 121, 244),
    (245, 101, 204),
]


def line_edit_style(color: QColor | None) -> str:
    return "" if color is None else f"QLineEdit {{ background: {color.name()}; }}"


class ModelBridge(QObject):
    """Re-emits :attr:`AppModel.changed` as a Qt signal; Qt disconnects destroyed receivers itself."""

    changed = pyqtSignal(object)

    def __init__(self, model: AppModel, parent: QObject | None = None):
        super().__init__(parent)
        self.model = model
        self._forward = self.changed.emit  # keep one bound method, a new one compares unequal
        model.changed.connect(self._forward)
        self._attached = True

    def detach(self) -> None:
        if self._attached:
            self.model.changed.disconnect(self._forward)
            self._attached = False


class Window(QMainWindow):
    """Window that refreshes itself when relevant model topics change, but only while it is visible."""

    topics: frozenset[str] = frozenset()

    def __init__(self, model: AppModel, bridge: ModelBridge, parent: QWidget | None = None):
        super().__init__(parent)
        self.model = model
        self._dirty = True
        bridge.changed.connect(self._on_changed)

    def _on_changed(self, topics: frozenset[str]) -> None:
        if not topics & self.topics:
            return
        if self.isVisible():
            self.refresh()
        else:
            self._dirty = True

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt API)
        if self._dirty:
            self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        self._dirty = False

    def confirm(self, title: str, text: str) -> bool:
        answer = QMessageBox.question(self, title, text)
        return answer == QMessageBox.StandardButton.Yes

    def show_error(self, title: str, text: str) -> None:
        QMessageBox.warning(self, title, text)


class TagSelect(QWidget):
    """Labelled multi select of tags; emits ``selection_changed(list[str])`` only for user changes."""

    selection_changed = pyqtSignal(list)

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.combo = MultiSelectComboBox(self)
        self.combo.setPlaceholderText("none")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label, self))
        layout.addWidget(self.combo, 1)
        self._options: list[str] = []
        self.combo.selectionChanged.connect(self._emit)

    def set_options(self, options: Iterable[str], selected: Sequence[str]) -> None:
        self._options = list(options)
        for tag in selected:
            if tag not in self._options:
                self._options.append(tag)
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            for tag in self._options:
                self.combo.addItem(display_tag(tag), tag)
            self.combo.setCurrentIndexes([self._options.index(t) for t in selected])
        finally:
            self.combo.blockSignals(False)

    def selected(self) -> list[str]:
        return list(self.combo.currentData())

    def set_selected(self, tags: Sequence[str]) -> None:
        """Select ``tags`` as if the user did it."""
        self.combo.setCurrentIndexes([self._options.index(t) for t in tags if t in self._options])

    def _emit(self, selected: list) -> None:
        self.selection_changed.emit(list(selected))
