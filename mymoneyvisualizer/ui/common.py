"""Building blocks shared by the windows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QMargins, QObject, QPoint, QRect, QSize, QTimer, pyqtSignal
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


#: Assumed height of the native title bar as long as the real frame is unknown (before the first show).
TITLE_BAR_ESTIMATE = 40


def fit_into(frame: QRect, available: QRect, minimum: QSize | None = None) -> QRect:
    """Shrink and move ``frame`` so that it lies inside ``available``.

    A frame that cannot shrink below ``minimum`` sticks out at the right/bottom, never at the top/left,
    so the title bar stays reachable.
    """
    minimum = minimum or QSize(0, 0)
    width = max(min(frame.width(), available.width()), minimum.width())
    height = max(min(frame.height(), available.height()), minimum.height())
    left = max(min(frame.left(), available.left() + available.width() - width), available.left())
    top = max(min(frame.top(), available.top() + available.height() - height), available.top())
    return QRect(left, top, width, height)


class Window(QMainWindow):
    """Window that refreshes itself when relevant model topics change, but only while it is visible.

    On its first show it is centered over its parent and kept completely on the screen. Qt centers windows
    over their parent without looking at the screen, so tall windows opened from the small main window had
    their title bar above the top of the screen.
    """

    topics: frozenset[str] = frozenset()
    #: Changes are collected this long and then shown with one refresh (``None``: refresh at once).
    REFRESH_DELAY_MS: int | None = 150

    def __init__(self, model: AppModel, bridge: ModelBridge, parent: QWidget | None = None):
        super().__init__(parent)
        self.model = model
        self._dirty = True
        self._placed = False
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.timeout.connect(self.refresh)
        bridge.changed.connect(self._on_changed)

    def schedule_refresh(self, *_args) -> None:
        """Refresh soon; several changes in a row (e.g. typing) cause only one refresh."""
        if self.REFRESH_DELAY_MS is None:
            self.refresh()
        else:
            self._refresh_timer.start(self.REFRESH_DELAY_MS)

    def flush(self) -> None:
        """Run a scheduled refresh now."""
        if self._refresh_timer.isActive():
            self._refresh_timer.stop()
            self.refresh()

    def place_on_screen(self) -> None:
        parent = self.parentWidget()
        screen = (parent or self).screen()
        available = screen.availableGeometry()
        handle = self.windowHandle()
        margins = handle.frameMargins() if handle is not None else QMargins()
        if margins.isNull():
            margins = QMargins(0, TITLE_BAR_ESTIMATE, 0, 0)
        frame = QRect(QPoint(0, 0), self.size().grownBy(margins))
        if parent is not None and parent.isVisible():
            frame.moveCenter(parent.frameGeometry().center())
        else:
            frame.moveCenter(available.center())
        minimum = self.minimumSizeHint().expandedTo(self.minimumSize()).grownBy(margins)
        self.setGeometry(fit_into(frame, available, minimum).marginsRemoved(margins))

    def _on_changed(self, topics: frozenset[str]) -> None:
        if not topics & self.topics:
            return
        if self.isVisible():
            self.schedule_refresh()
        else:
            self._dirty = True

    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802 (Qt API)
        if not self._placed:
            self._placed = True  # later the user decides where the window is
            self.place_on_screen()
        if self._dirty:
            self.refresh()
        super().showEvent(event)

    def refresh(self) -> None:
        self._dirty = False
        self._refresh_timer.stop()

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
