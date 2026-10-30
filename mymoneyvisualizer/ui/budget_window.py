"""Budget as used (accrual basis): is the savings rate right, where does the money go, what changed?

Payments are spread over the months in which they are used and internal transfers are left out, so the numbers
differ from the income & expenses table, which shows the payments as they were made. Needs, wants and savings are
compared with shares of the income (50/30/20 rule).
"""

from __future__ import annotations

import datetime
import html
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QCursor, QDropEvent, QFont, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QSplitter,
    QToolButton,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, GROUPS, RULES, SETTINGS, TRANSACTIONS
from mymoneyvisualizer.domain.analysis import month_key, ordered_month_range
from mymoneyvisualizer.domain.budget import SAVED, BudgetReport, BudgetSeries, group_totals, smooth
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.models import (
    GROUP_INCOME,
    GROUP_NEEDS,
    GROUP_SAVINGS,
    GROUP_WANTS,
    LAST_12_MONTHS,
    custom_period,
)
from mymoneyvisualizer.ui.common import (
    Card,
    CategorySelect,
    HelpButton,
    InfoBanner,
    KeyFigure,
    Window,
    make_button,
    make_label,
    set_tone,
)
from mymoneyvisualizer.ui.groups_dialog import GROUP_COLORS, HINTS, TITLES, GroupsDialog, dot_icon
from mymoneyvisualizer.ui.style import ACCENT, BAD, BORDER, GOOD, MUTED, OTHER, SERIES, TEXT, rich
from mymoneyvisualizer.ui.table_model import MONTH_NAMES, format_money, format_month, format_month_range

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

pg.setConfigOptions(antialias=True)

SAVINGS_HINT = (
    "Ersparnis = Nettoeinkommen − Konsumausgaben: Sparpläne und Geldanlagen (z. B. ETF) und der Rest auf den Konten."
)
#: categories drawn one by one in the chart of a group; the rest is added up
MAX_CATEGORIES = 6
#: a change against the year before is highlighted from this many euros per month and percent
NOTABLE_CHANGE = (10.0, 0.10)
#: the comparison with the year before needs a period of a year
COMPARED_MONTHS = 12
#: the mouse is on a line of the chart up to this many pixels away
LINE_DISTANCE = 5
CUSTOM = "custom"
#: a category is dragged to another place, a group takes it
CATEGORY_FLAGS = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDragEnabled
GROUP_FLAGS = Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsDropEnabled
#: columns of the breakdown
NAME, AVERAGE, SHARE, TARGET, CHANGE = range(5)

BANNER = (
    "<b>Periodengerecht:</b> Zahlungen sind auf ihre Nutzungsdauer verteilt, Umbuchungen zählen nicht. Daher andere"
    " Werte als in <i>Einnahmen &amp; Ausgaben</i>."
)
ACCRUAL_DETAILS = (
    "<p><b>Zahlungssicht</b> (Einnahmen &amp; Ausgaben): Jede Buchung zählt im Monat der Zahlung, wie auf dem"
    " Kontoauszug. Richtig, um Zahlungen zu prüfen.</p>"
    "<p><b>Periodengerechte Sicht</b> (Budget): Eine Zahlung zählt in den Monaten, in denen sie genutzt wird."
    " Beispiel Kfz-Versicherung, 684 € im Januar: in der Zahlungssicht −684 € im Januar, periodengerecht −57 € in"
    " jedem Monat. Über das Jahr ist die Summe gleich.</p>"
    "<p>Die Verteilung legst du in der Regel oder für eine einzelne Buchung unter <i>Verteilen über</i> fest. Bei"
    " Anschaffungen mit <i>Restwert</i> (z. B. Auto) zählt nur der Wertverlust.</p>"
    "<p>Außerdem zählen Umbuchungen zwischen eigenen Konten nicht, und der laufende Monat zählt erst, wenn er vorbei"
    " ist.</p>"
)
HELP = (
    "<p><b>Kennzahlen</b> für den gewählten Zeitraum, als Durchschnitt pro Monat.</p>"
    "<p><b>Kategorien:</b> Klick auf eine Zeile zeigt ihre Entwicklung im Diagramm, noch ein Klick (oder Esc) wieder"
    " das Ganze; Doppelklick zeigt alle Buchungen, die in den Zeitraum zählen. Eine Kategorie mit der Maus ziehen"
    " ändert ihre Reihenfolge, in einer anderen Gruppe fallen gelassen ihre Gruppe; das Diagramm bleibt dabei, wie es"
    " ist. Die Ziele änderst du unter <i>Gruppen &amp; Ziele</i>.</p>"
    "<p><b>ggü. Vorjahr</b> (bei 12 Monaten): Veränderung gegenüber den 12 Monaten davor; rot ungünstig, grün"
    " günstig.</p>"
    "<p><b>Diagramm:</b> Mausrad oder + und − zoomen, Ziehen verschiebt. Die blauen Linien begrenzen den Zeitraum,"
    " die Linie Ø ist der Durchschnitt darin. Die Maus auf einer Fläche zeigt ihren Wert im Monat, ein Klick ihre"
    " Buchungen (beim gleitenden Ø die der 12 Monate bis dahin).</p>" + ACCRUAL_DETAILS
)
FIGURE_TIPS = {
    "income": "Alle Kategorien der Gruppe Einkommen, Durchschnitt pro Monat im Zeitraum.",
    "spending": "Konsumausgaben = Grundbedarf + Freizeit & Lebensstil, Durchschnitt pro Monat, periodengerecht."
    " Sparen ist keine Ausgabe.",
    "rate": "Sparquote = (Nettoeinkommen − Konsumausgaben) ÷ Nettoeinkommen.",
    "room": "So viel liegt die Ersparnis pro Monat über dem Sparziel (negativ: darunter). So viel könntest du mehr"
    " ausgeben bzw. müsstest du weniger ausgeben.\nViel mehr zu sparen als nötig ist kein Ziel an sich: Geld verliert"
    " durch Inflation an Wert, Lebensqualität lässt sich nicht nachholen.",
}
COLUMN_TIPS = (
    "Hauptkategorien nach Budgetgruppe. Klick: Entwicklung im Diagramm, Doppelklick: die Buchungen. Ziehen ändert"
    " die Reihenfolge oder die Gruppe",
    "Durchschnitt pro Monat im Zeitraum, periodengerecht",
    "Anteil am Nettoeinkommen",
    "Ziel der Gruppe in % des Einkommens (50/30/20-Regel); ändern unter Gruppen & Ziele",
    "Veränderung pro Monat gegenüber den 12 Monaten davor; rot ungünstig, grün günstig",
)
KEPT = "kept"


def euro(value: float, signed: bool = False) -> str:
    sign = ("+" if value >= 0.5 else "−" if value <= -0.5 else "") if signed else ("−" if value <= -0.5 else "")
    return f"{sign}{format_money(abs(value), 0)} €"


def percent(value: float | None) -> str:
    if value is None:
        return "–"
    number = round(100 * value)
    return f"{'−' if number < 0 else ''}{abs(number)} %"


def period_label(period: str, start: pd.Period, end: pd.Period) -> str:
    """``Letzte 12 Monate (Okt 2025 – Sep 2026)``, ``2025`` or ``2026 (Jan – Sep)``."""
    if period == LAST_12_MONTHS:
        return f"Letzte 12 Monate ({format_month_range(start, end)})"
    months = format_month_range(start, end)
    return period if months == period else f"{period} ({months.replace(f' {period}', '')})"


def _timestamps(index) -> np.ndarray:
    """Month starts in local time, as the date axis expects."""
    return np.array([datetime.datetime(p.year, p.month, 1).timestamp() for p in index], dtype=float)


def encode(key: tuple[str, str] | None) -> str:
    return "all" if key is None else f"{key[0]}:{key[1]}"


def decode(link: str) -> tuple[str, str] | None:
    if link == "all":
        return None
    kind, name = link.split(":", 1)
    return kind, name


class EuroAxis(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):  # noqa: N802 (pyqtgraph API)
        return [format_money(v * scale, 0) for v in values]


class GermanDateAxis(pg.DateAxisItem):
    """Years, or German month names when the ticks are months apart."""

    def tickStrings(self, values, scale, spacing):  # noqa: N802 (pyqtgraph API)
        days = spacing / 86400
        if days < 27:
            return super().tickStrings(values, scale, spacing)
        dates = [datetime.datetime.fromtimestamp(v) for v in values]
        if days > 300:
            return [str(d.year) for d in dates]
        return [f"{MONTH_NAMES[d.month - 1]} {d:%y}" for d in dates]


@dataclass
class Layer:
    """One series of the chart: an area stacked on the areas before it in the list, or a line.

    The legend lists the layers backwards: the lines and then the areas from the top of the stack. A click on the layer
    lists the transactions of its main ``categories`` (``None``: nothing to list).
    """

    name: str
    color: str
    values: np.ndarray
    area: bool = True
    dashed: bool = False
    categories: list[str] | None = None

    @property
    def symbol(self) -> str:
        return "■" if self.area else "┅" if self.dashed else "━"


def round_button(text: str, tooltip: str, parent: QWidget) -> QToolButton:
    button = QToolButton(parent)
    button.setText(text)
    button.setToolTip(tooltip)
    button.setProperty("help", True)  # the round look of the help button
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


class BudgetChart(QWidget):
    """The development over time of what is selected in the breakdown; zoom with the wheel or the buttons.

    Two lines mark the budget period, another one shows the average in it. The mouse on an area or line shows its
    value in that month, a click on it emits ``layer_clicked(month, layer)``.
    """

    layer_clicked = pyqtSignal(object, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = make_label("", self, "heading")
        self.title.setTextFormat(Qt.TextFormat.RichText)
        self.title.setToolTip("Klick auf „Gesamt“ oder die Gruppe zeigt wieder die übergeordnete Ansicht")
        self.smooth_check = QCheckBox("gleitender Ø 12 Monate", self)
        self.smooth_check.setChecked(True)
        self.smooth_check.setToolTip(
            "Gleitender Durchschnitt: Jeder Punkt ist der Durchschnitt der 12 Monate bis dahin und zeigt den Trend ohne"
            " Ausreißer durch einzelne große Zahlungen. Aus: jeder Monat einzeln."
        )
        self.zoom_in = round_button("+", "Hineinzoomen (auch mit dem Mausrad)", self)
        self.zoom_out = round_button("−", "Herauszoomen", self)
        self.zoom_reset = round_button("↺", "Alles zeigen", self)
        self.legend = make_label("", self, wrap=True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.plot = pg.PlotWidget(axisItems={"bottom": GermanDateAxis(orientation="bottom"), "left": EuroAxis("left")})
        self.plot.setBackground("w")
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=True, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=False, y=True, alpha=0.15)
        self.view = self.plot.getPlotItem().vb
        self.view.setAutoVisible(y=True)
        for name in ("left", "bottom"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen(BORDER))
            axis.setTextPen(pg.mkPen(MUTED))
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(self.smooth_check)
        header.addSpacing(8)
        for button in (self.zoom_in, self.zoom_out, self.zoom_reset):
            header.addWidget(button)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.legend)
        layout.addWidget(self.plot, 1)
        self.x = np.array([])
        self.months: list[pd.Period] = []
        self.layers: list[Layer] = []
        #: every point is the moving average of the 12 months up to it
        self.smoothed = False
        #: the visible time range when the user zoomed, kept when the chart is drawn again
        self.zoomed: tuple[float, float] | None = None
        self._drawing = False
        self.cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(BORDER, width=1))
        self.plot.scene().sigMouseMoved.connect(self._hover)
        self.plot.scene().sigMouseClicked.connect(self._clicked)
        self.view.sigXRangeChanged.connect(self._range_changed)
        self.zoom_in.clicked.connect(lambda: self.zoom(0.5))
        self.zoom_out.clicked.connect(lambda: self.zoom(2.0))
        self.zoom_reset.clicked.connect(self.reset_zoom)

    # ------------------------------------------------------------------ zoom
    def zoom(self, factor: float) -> None:
        """Show ``factor`` times the visible time range around its center (< 1 zooms in)."""
        if len(self.x) < 2:
            return
        left, right = self.view.viewRange()[0]
        center, half = (left + right) / 2, (right - left) / 2 * factor
        self.view.setXRange(center - half, center + half, padding=0)

    def reset_zoom(self) -> None:
        self.zoomed = None
        if len(self.x) >= 2:
            self._drawing = True
            self.view.setXRange(self.x[0], self.x[-1], padding=0.01)
            self._drawing = False

    def _range_changed(self, _view, x_range) -> None:
        if not self._drawing and len(self.x) >= 2:
            self.zoomed = (float(x_range[0]), float(x_range[1]))

    # ------------------------------------------------------------------ drawing
    def draw(
        self,
        title: str,
        months: pd.PeriodIndex,
        layers: list[Layer],
        period: tuple[pd.Period, pd.Period],
        average: float | None = None,
        smoothed: bool = False,
    ):
        self._drawing = True
        self.smoothed = smoothed
        try:
            self._draw(title, months, layers, period, average)
        finally:
            self._drawing = False

    def _draw(self, title, months, layers, period, average) -> None:
        self.title.setText(title)
        self.plot.clear()
        self.layers, self.months = layers, list(months)
        self.x = _timestamps(months)
        if len(months) < 2:
            self.legend.setText("Zu wenige Monate für einen Verlauf.")
            return
        level = np.zeros(len(self.x))
        self.plot.plot(self.x, level, pen=None)  # keeps 0 in view when the height follows the visible data
        for layer in layers:
            color = pg.mkColor(layer.color)
            if layer.area:
                top = level + np.nan_to_num(layer.values)
                fill = pg.mkColor(layer.color)
                fill.setAlpha(140)
                self.plot.addItem(
                    pg.FillBetweenItem(pg.PlotDataItem(self.x, level), pg.PlotDataItem(self.x, top), fill)
                )
                self.plot.plot(self.x, top, pen=pg.mkPen(color, width=1.5))
                level = top
            else:
                style = Qt.PenStyle.DashLine if layer.dashed else Qt.PenStyle.SolidLine
                self.plot.plot(self.x, layer.values, pen=pg.mkPen(color, width=2, style=style))
        self._draw_period(period, average)
        self.plot.addItem(self.cursor, ignoreBounds=True)
        self.cursor.hide()
        margin = 45 * 86400
        self.view.setLimits(xMin=self.x[0] - margin, xMax=self.x[-1] + margin, minXRange=100 * 86400)
        self.view.enableAutoRange(axis=pg.ViewBox.YAxis)
        if self.zoomed is not None:
            self.view.setXRange(*self.zoomed, padding=0)
        else:
            self.view.setXRange(self.x[0], self.x[-1], padding=0.01)
        entries = [
            f"<span style='color:{layer.color}'>{layer.symbol}</span> {html.escape(layer.name)}"
            for layer in reversed(layers)
        ]
        if average is not None:
            entries.append(f"<span style='color:{ACCENT}'>━</span> Ø im Zeitraum")
        self.legend.setText("&nbsp;&nbsp;&nbsp;".join(entries))

    def _draw_period(self, period: tuple[pd.Period, pd.Period], average: float | None) -> None:
        """The limits of the period as labelled lines and its average."""
        start, end = period
        left, right = _timestamps([start, end + 1])
        for position, text, anchor in ((left, format_month(start), 0.0), (right, format_month(end), 1.0)):
            line = pg.InfiniteLine(
                pos=position,
                angle=90,
                movable=False,
                pen=pg.mkPen(ACCENT, width=1.5),
                label=text,
                labelOpts={
                    "position": 0.04,
                    "color": ACCENT,
                    "anchors": [(anchor, 0), (anchor, 0)],
                    "fill": (255, 255, 255, 220),
                },
            )
            line.setZValue(11)
            self.plot.addItem(line, ignoreBounds=True)
        if average is not None:
            mean = pg.PlotDataItem([left, right], [average, average], pen=pg.mkPen(ACCENT, width=2))
            mean.setZValue(12)
            self.plot.addItem(mean)
            label = pg.TextItem(f"Ø {euro(average)}", color=ACCENT, anchor=(1, 1))
            label.setPos(right, average)
            label.setZValue(12)
            self.plot.addItem(label, ignoreBounds=True)

    # ------------------------------------------------------------------ mouse
    def _month_at(self, position) -> int | None:
        if len(self.x) < 2 or not self.view.sceneBoundingRect().contains(position):
            return None
        x = self.view.mapSceneToView(position).x()
        i = int(np.clip(np.searchsorted(self.x, x), 0, len(self.x) - 1))
        if i > 0 and abs(self.x[i - 1] - x) < abs(self.x[i] - x):
            i -= 1
        return i

    def _layer_at(self, position) -> Layer | None:
        """The line near the mouse, else the area under it."""
        point = self.view.mapSceneToView(position)
        x, y = point.x(), point.y()
        distance = LINE_DISTANCE * self.view.viewPixelSize()[1]
        for layer in reversed(self.layers):
            if not layer.area and abs(np.interp(x, self.x, layer.values) - y) <= distance:
                return layer
        level, hit = 0.0, None
        for layer in self.layers:
            if layer.area:
                top = level + float(np.interp(x, self.x, np.nan_to_num(layer.values)))
                if min(level, top) <= y <= max(level, top):
                    hit = layer
                level = top
        return hit

    def _hover(self, position) -> None:
        i = self._month_at(position)
        layer = None if i is None else self._layer_at(position)
        clickable = layer is not None and layer.categories is not None
        if clickable:
            self.plot.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.plot.viewport().unsetCursor()
        if i is None:
            self.cursor.hide()
            return
        self.cursor.setPos(self.x[i])
        self.cursor.show()
        if layer is None:
            QToolTip.hideText()
            return
        month = self.months[i]
        when = f"Ø {format_month_range(month - 11, month)}" if self.smoothed else format_month(month)
        QToolTip.showText(
            QCursor.pos(),
            f"{when}<br><span style='color:{layer.color}'>{layer.symbol}</span>"
            f" <b>{html.escape(layer.name)}</b>&nbsp; {euro(float(np.nan_to_num(layer.values[i])))}"
            + ("<br><i>Klick: die Buchungen</i>" if clickable else ""),
            self.plot,
        )

    def _clicked(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or event.double():
            return
        position = event.scenePos()
        i = self._month_at(position)
        layer = None if i is None else self._layer_at(position)
        if layer is not None and layer.categories is not None:
            self.layer_clicked.emit(self.months[i], layer)


class BreakdownTree(QTreeWidget):
    """The breakdown: a click on a row selects it, a drag moves a category to another place or group.

    A row is selected when the mouse is released without a drag (``row_clicked``), so dragging changes nothing but the
    order, also in the overall view. A click into the empty area or Esc emits ``row_clicked(None)``. ``reordered``
    follows a drop, ``drag_finished`` every drag, whether dropped or not.
    """

    row_clicked = pyqtSignal(object)
    reordered = pyqtSignal()
    drag_finished = pyqtSignal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setDropIndicatorShown(True)
        # a category goes into a group, never next to the groups
        self.invisibleRootItem().setFlags(self.invisibleRootItem().flags() & ~Qt.ItemFlag.ItemIsDropEnabled)
        #: the mouse button is down: Qt marks the row it was pressed on (a drag needs that), but nothing is selected yet
        self.pressing = False
        self._pressed: tuple[QTreeWidgetItem, QPoint] | None = None

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        position = event.position().toPoint()
        item = self.itemAt(position)
        if event.button() == Qt.MouseButton.LeftButton:
            if item is None:
                self.row_clicked.emit(None)
                return
            # not the arrow that expands and collapses a group
            on_row = self.visualItemRect(item).left() <= position.x()
            self._pressed = (item, position) if on_row else None
            self.pressing = on_row
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        super().mouseReleaseEvent(event)
        pressed, self._pressed = self._pressed, None
        self.pressing = False
        if pressed is None or event.button() != Qt.MouseButton.LeftButton:
            return
        position = event.position().toPoint()
        moved = (position - pressed[1]).manhattanLength() >= QApplication.startDragDistance()
        if moved or self.itemAt(position) is not pressed[0]:
            self.drag_finished.emit()
        else:
            self.row_clicked.emit(pressed[0])

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802 (Qt API)
        self._pressed = None  # the first click selected the row; the second one must not clear it again
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 (Qt API)
        if event.key() == Qt.Key.Key_Escape:
            self.row_clicked.emit(None)
        else:
            super().keyPressEvent(event)

    def startDrag(self, actions) -> None:  # noqa: N802 (Qt API)
        super().startDrag(actions)  # returns when the drag is over
        self._pressed, self.pressing = None, False
        self.drag_finished.emit()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802 (Qt API)
        super().dropEvent(event)
        QTimer.singleShot(0, self.reordered.emit)  # the tree is rebuilt after saving: not inside the drop


class BudgetWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS, GROUPS, ACCOUNTS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Budget")
        self.resize(1400, 950)
        self.series: BudgetSeries | None = None
        self.report: BudgetReport | None = None
        self.previous: BudgetReport | None = None
        self.selected: tuple[str, str] | None = None
        self.groups_dialog: GroupsDialog | None = None
        self._group_by_category: dict[str, str] = {}
        self._filling = False

        self.banner = InfoBanner(model, "budget", BANNER, ACCRUAL_DETAILS, "Periodengerechte Sicht", self)
        self.help_button = HelpButton(HELP, "Budget", self)
        self.period_combo = QComboBox(self)
        self.period_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.period_combo.setToolTip(
            "Welche Monate ausgewertet werden: die letzten 12 abgeschlossenen Monate, ein Kalenderjahr oder ein eigener"
            " Zeitraum. Der laufende Monat zählt erst, wenn er vorbei ist."
        )
        self.start_combo, self.end_combo = QComboBox(self), QComboBox(self)
        for combo in (self.start_combo, self.end_combo):
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.start_combo.setToolTip("Erster Monat des Zeitraums")
        self.end_combo.setToolTip("Letzter Monat des Zeitraums")
        self.dash = make_label("–", self)
        self.period_note = make_label("", self, "hint")
        set_tone(self.period_note, "warning")
        self.exclude_select = CategorySelect("Ausblenden:", self)
        self.exclude_select.setMinimumWidth(260)
        self.exclude_select.setToolTip("Kategorien, die nicht mitgezählt werden, z. B. eine einmalige Erbschaft.")
        controls = QHBoxLayout()
        for widget in (
            make_label("Zeitraum:", self),
            self.period_combo,
            self.start_combo,
            self.dash,
            self.end_combo,
            self.period_note,
        ):
            controls.addWidget(widget)
        controls.addStretch(1)
        controls.addWidget(self.exclude_select)
        controls.addWidget(self.help_button)

        self.figures = {
            "income": KeyFigure("Nettoeinkommen", FIGURE_TIPS["income"], self),
            "spending": KeyFigure("Konsumausgaben", FIGURE_TIPS["spending"], self),
            "rate": KeyFigure("Sparquote", FIGURE_TIPS["rate"], self),
            "room": KeyFigure("Abstand zum Sparziel", FIGURE_TIPS["room"], self),
        }
        figures = QHBoxLayout()
        figures.setSpacing(12)
        for figure in self.figures.values():
            figures.addWidget(figure, 1)

        self.tree = BreakdownTree(self)
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Kategorie", "Ø Monat", "Anteil", "Ziel", "ggü. Vorjahr"])
        for column, tip in enumerate(COLUMN_TIPS):
            self.tree.headerItem().setToolTip(column, rich(tip))
            if column:
                self.tree.headerItem().setTextAlignment(column, Qt.AlignmentFlag.AlignRight)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(NAME, QHeaderView.ResizeMode.Stretch)
        for column, width in ((AVERAGE, 84), (SHARE, 60), (TARGET, 56), (CHANGE, 96)):
            self.tree.setColumnWidth(column, width)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        self.groups_button = make_button(
            "Gruppen && Ziele …",
            "Kategorien den Budgetgruppen zuordnen und die Ziele der 50/30/20-Regel ändern",
            self,
        )
        breakdown = Card(self)
        header = QHBoxLayout()
        header.addWidget(make_label("Kategorien", breakdown, "heading"), 1)
        header.addWidget(self.groups_button)
        breakdown.content.addLayout(header)
        breakdown.content.addWidget(self.tree, 1)

        self.chart = BudgetChart(self)
        chart_card = Card(self)
        chart_card.content.addWidget(self.chart)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(breakdown)
        splitter.addWidget(chart_card)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([580, 780])

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)
        layout.addWidget(self.banner)
        layout.addLayout(controls)
        layout.addLayout(figures)
        layout.addWidget(splitter, 1)
        self.setCentralWidget(central)

        self.period_combo.currentIndexChanged.connect(self._period_changed)
        self.start_combo.currentIndexChanged.connect(lambda _: self._custom_changed("start"))
        self.end_combo.currentIndexChanged.connect(lambda _: self._custom_changed("end"))
        self.exclude_select.selection_changed.connect(lambda c: model.update_settings(excluded_categories=c))
        self.groups_button.clicked.connect(self.open_groups)
        self.chart.smooth_check.toggled.connect(self.draw_chart)
        self.chart.title.linkActivated.connect(lambda link: self.select(decode(link)))
        self.chart.layer_clicked.connect(self.open_layer)
        self.tree.currentItemChanged.connect(self._current_changed)
        self.tree.row_clicked.connect(self._row_clicked)
        self.tree.drag_finished.connect(self._mark_selected)
        self.tree.itemDoubleClicked.connect(self.open_detail)
        self.tree.reordered.connect(self.save_order)

    # ------------------------------------------------------------------ user input
    def _period_changed(self, _index: int) -> None:
        period = self.period_combo.currentData()
        if self._filling or not period:
            return
        if period == CUSTOM:  # starts with the months shown so far
            months = self.model.budget_months(self.series)
            if months is not None:
                self.model.set_budget_period(custom_period(month_key(months[0]), month_key(months[1])))
        else:
            self.model.set_budget_period(period)

    def _custom_changed(self, changed: str) -> None:
        if self._filling or not self.start_combo.currentData() or not self.end_combo.currentData():
            return
        start, end = ordered_month_range(self.start_combo.currentData(), self.end_combo.currentData(), changed)
        self.model.set_budget_period(custom_period(start, end))

    def open_groups(self) -> GroupsDialog:
        if self.groups_dialog is None:
            self.groups_dialog = GroupsDialog(self.model, self)
        self.groups_dialog.refresh()
        self.groups_dialog.show()
        self.groups_dialog.raise_()
        return self.groups_dialog

    def select(self, key: tuple[str, str] | None) -> None:
        """Show ``key`` (a group or category; ``None``: the whole) in the chart and mark it in the breakdown."""
        self.selected = key if self._item(key) is not None else None
        self._mark_selected()
        self.draw_chart()

    def _mark_selected(self) -> None:
        """Mark the selected row in the breakdown again, e.g. after a drag marked the dragged one."""
        item = self._item(self.selected)
        self.tree.blockSignals(True)
        try:
            self.tree.clearSelection()
            self.tree.setCurrentItem(item)
            if item is None:
                self.tree.clearSelection()
        finally:
            self.tree.blockSignals(False)

    def _row_clicked(self, item: QTreeWidgetItem | None) -> None:
        """A click selects a row; a second click on it, into the empty area or Esc shows the whole again."""
        key = None if item is None else item.data(NAME, Qt.ItemDataRole.UserRole)
        self.select(None if key == self.selected else key)

    def _current_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        """The keyboard moved the current row; a mouse press waits for the release."""
        if not self._filling and not self.tree.pressing:
            self.selected = None if current is None else current.data(NAME, Qt.ItemDataRole.UserRole)
            self.draw_chart()

    def _item(self, key: tuple[str, str] | None) -> QTreeWidgetItem | None:
        if key is None:
            return None
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            for item in (group, *(group.child(j) for j in range(group.childCount()))):
                if item.data(NAME, Qt.ItemDataRole.UserRole) == key:
                    return item
        return None

    def save_order(self) -> None:
        """The categories in the order and groups of the tree, after one was dragged."""
        assignment = {}
        for i in range(self.tree.topLevelItemCount()):
            group = self.tree.topLevelItem(i)
            keys = [group.child(j).data(NAME, Qt.ItemDataRole.UserRole) for j in range(group.childCount())]
            assignment[group.data(NAME, Qt.ItemDataRole.UserRole)[1]] = [
                name for kind, name in keys if kind == "category"
            ]
        self.model.assign_groups(assignment)

    def open_detail(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        """Everything that counts in the budget period for a row, also spread payments made before."""
        kind, name = item.data(NAME, Qt.ItemDataRole.UserRole)
        months = self.model.budget_months(self.series)
        if months is None or kind == KEPT:
            return
        if kind == "category":
            categories, title = [name], display_category(name)
        else:
            categories, title = self.model.categories_in_group(name), TITLES[name]
        self.navigator.open_budget_detail(*months, categories, title, self.report.months if self.report else 0)

    def open_layer(self, month: pd.Period, layer: Layer) -> None:
        """The transactions behind an area of the chart in a month, or in the 12 months of the moving average."""
        months = 12 if self._smoothed() else 1
        self.navigator.open_budget_detail(month - (months - 1), month, layer.categories, layer.name, months)

    # ------------------------------------------------------------------ display
    def refresh(self) -> None:
        super().refresh()
        settings = self.model.settings
        self.banner.update_visibility()
        self.series = self.model.budget_series()
        self.report = self.model.budget_report(self.series)
        compared = self.report is not None and self.report.period_months == COMPARED_MONTHS
        self.previous = self.model.budget_report(self.series, previous=True) if compared else None
        self._filling = True
        try:
            self.exclude_select.set_options(self.model.unique_categories(), settings.excluded_categories)
            self._fill_periods(settings.budget_period)
            self.tree.setColumnHidden(CHANGE, not compared)
            self._fill_tree()
        finally:
            self._filling = False
        self.show_figures()
        self.draw_chart()

    def _fill_periods(self, period: str) -> None:
        self.period_combo.clear()
        presets = self.model.budget_periods(self.series)
        for preset, start, end in presets:
            self.period_combo.addItem(period_label(preset, start, end), preset)
        custom = ":" in period
        if self.period_combo.count():
            self.period_combo.addItem("Eigener Zeitraum", CUSTOM)
            index = self.period_combo.findData(CUSTOM if custom else period)
            if index < 0:  # a year without data
                self.period_combo.insertItem(self.period_combo.count() - 1, period, period)
                index = self.period_combo.findData(period)
            self.period_combo.setCurrentIndex(index)
        for widget in (self.start_combo, self.dash, self.end_combo):
            widget.setVisible(custom)
        months = self.model.budget_months(self.series)
        if not custom or months is None or not presets:
            return
        first, last = self.series.monthly.index[0], presets[0][2]  # the last complete month
        choices = pd.period_range(min(first, months[0]), max(last, months[0]), freq="M")[::-1]
        for combo, value in ((self.start_combo, months[0]), (self.end_combo, months[1])):
            combo.clear()
            for month in choices:
                combo.addItem(format_month(month), month_key(month))
            combo.setCurrentIndex(max(combo.findData(month_key(value)), 0))

    def show_figures(self) -> None:
        report = self.report
        note = ""
        if report is not None and 0 < report.months < report.period_months:
            note = f"Nur {report.months} von {report.period_months} Monaten haben Buchungen."
        self.period_note.setText(note)
        if report is None or report.months == 0:
            for figure in self.figures.values():
                figure.set("–", "Keine Buchungen im Zeitraum.")
            return
        income = report.per_month(report.income)
        spending = report.per_month(report.needs.amount + report.wants.amount)
        self.figures["income"].set(euro(income), "pro Monat")
        share = report.share(report.needs.amount + report.wants.amount)
        self.figures["spending"].set(euro(spending), f"pro Monat · {percent(share)} des Einkommens")
        rate, target, room = report.savings_rate, report.savings.target, report.room_per_month
        if rate is None or room is None:
            self.figures["rate"].set("–", "Kein Einkommen im Zeitraum.")
            self.figures["room"].set("–", "")
            return
        reached = rate >= target
        self.figures["rate"].set(
            percent(rate),
            f"Ziel {percent(target)} · {'✓ erreicht' if reached else '✗ verfehlt'}",
            "good" if reached else "bad",
        )
        above = room >= 0
        self.figures["room"].set(
            euro(room, signed=True),
            f"pro Monat {'über' if above else 'unter'} dem Ziel",
            "good" if above else "bad",
        )

    # ------------------------------------------------------------------ breakdown
    def _fill_tree(self) -> None:
        self.tree.clear()
        report = self.report
        if report is None or report.months == 0:
            return
        previous = self._previous_amounts()
        bold = QFont(self.tree.font())
        bold.setBold(True)
        settings = self.model.settings
        rows = {
            GROUP_INCOME: (report.income, report.income_categories),
            GROUP_NEEDS: (report.needs.amount, report.needs.categories),
            GROUP_WANTS: (report.wants.amount, report.wants.categories),
            GROUP_SAVINGS: (report.saved, report.savings.categories),
        }
        targets = {**settings.budget_shares, GROUP_SAVINGS: settings.savings_share}
        # the order of the user, as dragged in the tree
        order = {assignment.category: i for i, assignment in enumerate(self.model.groups)}
        current = None
        for group, (amount, categories) in rows.items():
            item = QTreeWidgetItem(self.tree)
            item.setFlags(GROUP_FLAGS)
            item.setData(NAME, Qt.ItemDataRole.UserRole, ("group", group))
            item.setText(NAME, TITLES[group])
            item.setIcon(NAME, dot_icon(GROUP_COLORS[group]))
            item.setToolTip(NAME, rich(SAVINGS_HINT if group == GROUP_SAVINGS else HINTS[group]))
            for column in range(5):
                item.setFont(column, bold)
            self._amounts(item, report, amount, previous.get(("group", group)), group)
            if group in targets:
                item.setText(TARGET, percent(targets[group]))
                share = report.share(amount)
                if group == GROUP_SAVINGS:
                    missed = share is not None and share < targets[group] - 0.005
                    set_share_tone(item, missed, "Ziel verfehlt")
                else:
                    missed = share is not None and share > targets[group] + 0.005
                    set_share_tone(item, missed, "Ziel überschritten")
            for category, value in sorted(categories, key=lambda entry: order.get(entry[0], len(order))):
                child = QTreeWidgetItem(item)
                child.setFlags(CATEGORY_FLAGS)
                child.setData(NAME, Qt.ItemDataRole.UserRole, ("category", category))
                child.setText(NAME, display_category(category))
                self._amounts(child, report, value, previous.get(("category", category)), group)
                if self.selected == ("category", category):
                    current = child
            if group == GROUP_SAVINGS:
                kept = QTreeWidgetItem(item)
                kept.setFlags(Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled)
                kept.setData(NAME, Qt.ItemDataRole.UserRole, (KEPT, GROUP_SAVINGS))
                kept.setText(NAME, "Rest auf den Konten")
                kept.setToolTip(
                    NAME,
                    rich(
                        "Ersparnis, die nicht in Sparpläne geflossen ist: bleibt auf Giro- und Tagesgeldkonten, auch"
                        " Umbuchungen aufs Tagesgeld. Negativ: Rücklagen aufgebraucht."
                    ),
                )
                rest = report.saved - report.savings.amount
                self._amounts(kept, report, rest, previous.get((KEPT, GROUP_SAVINGS)), GROUP_SAVINGS)
            item.setExpanded(True)
            if self.selected == ("group", group):
                current = item
        if current is not None:
            self.tree.setCurrentItem(current)
        elif self.selected is not None and self.selected[0] != KEPT:
            self.selected = None  # the category is gone

    def _previous_amounts(self) -> dict[tuple[str, str], float]:
        """Per month in the 12 months before: every group and category."""
        before = self.previous
        if before is None or before.months == 0:
            return {}
        amounts = {
            ("group", GROUP_INCOME): before.per_month(before.income),
            ("group", GROUP_NEEDS): before.per_month(before.needs.amount),
            ("group", GROUP_WANTS): before.per_month(before.wants.amount),
            ("group", GROUP_SAVINGS): before.per_month(before.saved),
            (KEPT, GROUP_SAVINGS): before.per_month(before.saved - before.savings.amount),
        }
        for categories in (
            before.income_categories,
            before.needs.categories,
            before.wants.categories,
            before.savings.categories,
        ):
            for category, value in categories:
                amounts[("category", category)] = before.per_month(value)
        return amounts

    def _amounts(self, item, report: BudgetReport, total: float, before: float | None, group: str) -> None:
        """Per month, share of the income and change against the 12 months before of one row."""
        value = report.per_month(total)
        item.setText(AVERAGE, euro(value))
        item.setText(SHARE, percent(report.share(total)) if group != GROUP_INCOME or item.parent() else "")
        if before is None:
            item.setText(CHANGE, "–")
            item.setToolTip(CHANGE, "Keine Buchungen in den 12 Monaten davor")
        else:
            change = value - before
            item.setText(CHANGE, euro(change, signed=True) if abs(change) >= 0.5 else "±0 €")
            item.setToolTip(CHANGE, f"12 Monate davor: {euro(before)} pro Monat")
            notable = abs(change) >= max(NOTABLE_CHANGE[0], NOTABLE_CHANGE[1] * abs(before))
            if notable:
                more_is_good = group in (GROUP_INCOME, GROUP_SAVINGS)
                item.setForeground(CHANGE, pg.mkColor(GOOD if (change > 0) == more_is_good else BAD))
        for column in (AVERAGE, SHARE, TARGET, CHANGE):
            item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------ chart
    def _smoothed(self) -> bool:
        return self.chart.smooth_check.isChecked() and self.series is not None and len(self.series.monthly) >= 13

    def _breadcrumb(self, key: tuple[str, str] | None) -> str:
        """``Gesamt › Grundbedarf › Wohnen``; every part but the last is a link."""
        if key is None:
            return "Gesamt: Einkommen und Konsum"
        kind, name = key
        group = self._group_of(name) if kind == "category" else name
        parts = [("Gesamt", None), (TITLES[group], ("group", group))]
        if kind == "category":
            parts.append((display_category(name), key))
        links = [
            f"<a href='{encode(k)}' style='color:{ACCENT}; text-decoration:none'>{html.escape(t)}</a>"
            for t, k in parts[:-1]
        ]
        return " › ".join([*links, html.escape(parts[-1][0])])

    def _average(self, key: tuple[str, str] | None) -> float | None:
        """The value of the breakdown for ``key``: the average per month in the period."""
        report = self.report
        if report is None or report.months == 0:
            return None
        if key is None:
            return report.per_month(report.needs.amount + report.wants.amount)
        kind, name = key
        if kind != "category":
            amounts = {
                GROUP_INCOME: report.income,
                GROUP_NEEDS: report.needs.amount,
                GROUP_WANTS: report.wants.amount,
                GROUP_SAVINGS: report.saved,
            }
            return report.per_month(amounts[name])
        for categories in (
            report.income_categories,
            report.needs.categories,
            report.wants.categories,
            report.savings.categories,
        ):
            for category, value in categories:
                if category == name:
                    return report.per_month(value)
        return None

    def draw_chart(self, *_args) -> None:
        if self.series is None:
            return
        monthly = self.series.monthly
        months = self.model.budget_months(self.series)
        if monthly.empty or months is None:
            self.chart.draw("Gesamt", monthly.index, [], (pd.Period("2000-01", "M"),) * 2)
            return
        smoothed = self._smoothed()
        self.chart.smooth_check.setEnabled(len(monthly) >= 13)
        data = smooth(monthly) if smoothed else monthly
        groups = self.model.groups
        self._group_by_category = {a.category: a.group for a in groups}
        totals = group_totals(data, groups)
        income = totals[GROUP_INCOME].to_numpy()
        settings = self.model.settings
        key = ("group", GROUP_SAVINGS) if self.selected is not None and self.selected[0] == KEPT else self.selected
        if key is not None and key[0] == "group":
            layers = self._group_layers(data, totals, key[1], settings)
        elif key is not None:
            name = key[1]
            sign = 1 if self._group_of(name) == GROUP_INCOME else -1
            values = sign * data[name].to_numpy() if name in data else np.zeros(len(data))
            color = GROUP_COLORS.get(self._group_of(name), SERIES[0])
            layers = [Layer(display_category(name), color, values, categories=[name])]
        else:
            layers = [  # needs above wants, as in the breakdown
                *(
                    Layer(TITLES[g], GROUP_COLORS[g], totals[g].to_numpy(), categories=self._members(data, g))
                    for g in (GROUP_WANTS, GROUP_NEEDS)
                ),
                Layer(
                    f"Konsumgrenze für {percent(settings.savings_share)} Sparquote",
                    MUTED,
                    income * (1 - settings.savings_share),
                    area=False,
                    dashed=True,
                ),
                Layer("Nettoeinkommen", TEXT, income, area=False, categories=self._members(data, GROUP_INCOME)),
            ]
        self.chart.draw(self._breadcrumb(key), data.index, layers, months, self._average(key), smoothed)

    def _group_of(self, category: str) -> str:
        return self._group_by_category.get(category, GROUP_NEEDS)

    def _members(self, data: pd.DataFrame, group: str) -> list[str]:
        """The main categories of ``group`` in the order of the breakdown."""
        order = {assignment.category: i for i, assignment in enumerate(self.model.groups)}
        return sorted((c for c in data.columns if self._group_of(c) == group), key=lambda c: order.get(c, len(order)))

    def _group_layers(self, data: pd.DataFrame, totals: pd.DataFrame, group: str, settings) -> list[Layer]:
        """The categories of a group stacked in the order of the breakdown, with the target of the group."""
        sign = 1 if group == GROUP_INCOME else -1
        members = self._members(data, group)  # the color follows the place in this order
        # the largest of the whole history one by one, the others added up
        overall = self.series.monthly
        largest = sorted(members, key=lambda c: sign * float(overall[c].sum()) if c in overall else 0.0, reverse=True)
        if len(largest) > MAX_CATEGORIES + 1:
            largest = largest[:MAX_CATEGORIES]
        shown = [c for c in members if c in largest]
        rest = [c for c in members if c not in largest]
        areas = [
            Layer(display_category(c), SERIES[i], sign * data[c].to_numpy(), categories=[c])
            for i, c in enumerate(shown)
        ]
        if rest:
            areas.append(Layer("Sonstige", OTHER, sign * data[rest].sum(axis=1).to_numpy(), categories=rest))
        layers = areas[::-1]  # the first row of the breakdown on top of the stack, as in the legend
        income = totals[GROUP_INCOME].to_numpy()
        if group in (GROUP_NEEDS, GROUP_WANTS):
            share = settings.budget_shares.get(group, 0.0)
            layers.append(Layer(f"Ziel {percent(share)} des Einkommens", TEXT, income * share, area=False, dashed=True))
        elif group == GROUP_SAVINGS:
            layers.append(Layer("Ersparnis gesamt", TEXT, totals[SAVED].to_numpy(), area=False))
            target = settings.savings_share
            layers.append(
                Layer(f"Ziel {percent(target)} des Einkommens", MUTED, income * target, area=False, dashed=True)
            )
        return layers


def set_share_tone(item: QTreeWidgetItem, off_target: bool, message: str) -> None:
    """The share of a group in red when it misses its target."""
    if off_target:
        item.setForeground(SHARE, pg.mkColor(BAD))
        item.setToolTip(SHARE, message)
    else:
        item.setToolTip(SHARE, "im Rahmen des Ziels")
