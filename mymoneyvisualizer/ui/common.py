"""Building blocks shared by the windows."""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from PyQt6.QtCore import QMargins, QObject, QPoint, QRect, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QCompleter,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from pyqt6_multiselect_combobox import MultiSelectComboBox

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.ui.style import set_variant

GREY = QColor("#e6e9ee")
GREEN = QColor("#d9f0df")
RED = QColor("#fbdcd8")
TOTAL_BACKGROUND = QColor("#eef1f5")
MORE_EXPENSE = QColor("#f8cfca")
LESS_EXPENSE = QColor("#cdebd5")


def line_edit_style(color: QColor | None) -> str:
    return "" if color is None else f"QLineEdit {{ background: {color.name()}; }}"


def make_button(
    text: str, tooltip: str = "", parent: QWidget | None = None, *, primary: bool = False, link: bool = False
) -> QPushButton:
    """A button with an explanation; ``primary`` for the main action of a window, ``link`` for a text link."""
    button = QPushButton(text, parent)
    button.setToolTip(tooltip)
    if primary:
        button.setProperty("primary", True)
    if link:
        button.setProperty("link", True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


def make_label(text: str = "", parent: QWidget | None = None, role: str | None = None, wrap: bool = False) -> QLabel:
    """A label; ``role`` is one of title, heading, hint (secondary text) and kpi (a big number)."""
    label = QLabel(text, parent)
    if role is not None:
        label.setProperty("role", role)
    label.setWordWrap(wrap)
    return label


def set_tone(widget: QWidget, tone: str | None) -> None:
    """Color a label or card by what it means: good, bad, warning or neutral (``None``)."""
    set_variant(widget, "tone", tone or "")


class Card(QFrame):
    """A white panel with rounded corners; ``layout`` takes its content."""

    def __init__(self, parent: QWidget | None = None, horizontal: bool = False, margins: int = 14):
        super().__init__(parent)
        self.setProperty("card", True)
        self.content = QHBoxLayout(self) if horizontal else QVBoxLayout(self)
        self.content.setContentsMargins(margins, margins - 2, margins, margins - 2)


class HelpButton(QToolButton):
    """The "?" of a window: its explanation as tooltip, a click shows it in a dialog."""

    def __init__(self, text: str, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setText("?")
        self.setProperty("help", True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.text_, self.title = text, title
        self.setToolTip(text)
        self.clicked.connect(self.show_help)

    def show_help(self) -> None:
        QMessageBox.information(self, self.title, self.text_)


class InfoBanner(QFrame):
    """A short explanation at the top of a window until it is closed; the help button of the window keeps it.

    ``name`` remembers the closing in the settings, so a banner is read once, not every day.
    """

    def __init__(self, model: AppModel, name: str, text: str, details: str = "", title: str = "", parent=None):
        super().__init__(parent)
        self.setProperty("banner", True)
        self.model, self.name = model, name
        self.details, self.title = details, title
        icon = make_label("ⓘ", self)
        icon.setStyleSheet("font-size: 13pt; color: #2a78d6;")
        self.label = make_label(text, self, wrap=True)
        self.label.setTextFormat(Qt.TextFormat.RichText)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 6, 6)
        layout.addWidget(icon, 0, Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self.label, 1)
        self.more_button = None
        if details:
            self.more_button = make_button("Mehr", "Ausführliche Erklärung anzeigen", self, link=True)
            self.more_button.clicked.connect(self.show_details)
            layout.addWidget(self.more_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.close_button = QToolButton(self)
        self.close_button.setText("✕")
        self.close_button.setProperty("close", True)
        self.close_button.setToolTip("Hinweis ausblenden; die Erklärung bleibt über das „?“ des Fensters erreichbar.")
        self.close_button.clicked.connect(self.dismiss)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignVCenter)
        self.update_visibility()

    def update_visibility(self) -> None:
        self.setHidden(self.name in self.model.settings.hidden_hints)

    def dismiss(self) -> None:
        self.hide()
        self.model.hide_hint(self.name)

    def show_details(self) -> None:
        QMessageBox.information(self, self.title or "Erklärung", self.details)


class KeyFigure(QFrame):
    """A key figure as a card: what it is, the big number and one line that says what it means."""

    def __init__(self, title: str, tooltip: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.setProperty("card", True)
        self.setToolTip(tooltip)
        self.title = make_label(title, self, "hint")
        self.value = make_label("–", self, "kpi")
        self.detail = make_label("", self, "hint", wrap=True)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(2)
        layout.addWidget(self.title)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addStretch(1)

    def set(self, value: str, detail: str = "", tone: str | None = None) -> None:
        self.value.setText(value)
        self.detail.setText(detail)
        set_tone(self, tone)
        set_tone(self.value, tone)


def category_completer(model: AppModel, parent: QObject) -> QCompleter:
    """Proposes the known categories and the account names (internal transfers) while a category is typed."""
    completer = QCompleter(model.unique_categories() + model.account_names, parent)
    completer.setFilterMode(Qt.MatchFlag.MatchContains)
    completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
    return completer


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


class CategorySelect(QWidget):
    """Labelled multi select of categories; emits ``selection_changed(list[str])`` only for user changes."""

    selection_changed = pyqtSignal(list)

    def __init__(self, label: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.combo = MultiSelectComboBox(self)
        self.combo.setPlaceholderText("keine")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(label, self))
        layout.addWidget(self.combo, 1)
        self._options: list[str] = []
        self.combo.selectionChanged.connect(self._emit)

    def set_options(self, options: Iterable[str], selected: Sequence[str]) -> None:
        self._options = list(options)
        for category in selected:
            if category not in self._options:
                self._options.append(category)
        self.combo.blockSignals(True)
        try:
            self.combo.clear()
            for category in self._options:
                self.combo.addItem(display_category(category), category)
            self.combo.setCurrentIndexes([self._options.index(t) for t in selected])
        finally:
            self.combo.blockSignals(False)

    def selected(self) -> list[str]:
        return list(self.combo.currentData())

    def set_selected(self, categories: Sequence[str]) -> None:
        """Select ``categories`` as if the user did it."""
        self.combo.setCurrentIndexes([self._options.index(t) for t in categories if t in self._options])

    def _emit(self, selected: list) -> None:
        self.selection_changed.emit(list(selected))
