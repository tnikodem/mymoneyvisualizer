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
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QSpinBox,
    QSplitter,
    QToolTip,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, GROUPS, RULES, SETTINGS, TRANSACTIONS
from mymoneyvisualizer.domain.budget import SAVED, BudgetReport, BudgetSeries, group_totals, smooth
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.models import GROUP_INCOME, GROUP_NEEDS, GROUP_SAVINGS, GROUP_WANTS, LAST_12_MONTHS
from mymoneyvisualizer.domain.models import GROUPS as GROUP_NAMES
from mymoneyvisualizer.ui.common import (
    Card,
    CategorySelect,
    HelpButton,
    InfoBanner,
    KeyFigure,
    Window,
    make_label,
    set_tone,
)
from mymoneyvisualizer.ui.style import BAD, BORDER, GOOD, MUTED, OTHER, SERIES, TEXT, rich
from mymoneyvisualizer.ui.table_model import MONTH_NAMES, format_money, format_month, format_month_range

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

pg.setConfigOptions(antialias=True)

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
    GROUP_SAVINGS: "Ersparnis = Nettoeinkommen − Konsumausgaben: Sparpläne und Geldanlagen (z. B. ETF) und der Rest auf"
    " den Konten.",
}
GROUP_COLORS = {GROUP_NEEDS: SERIES[0], GROUP_WANTS: SERIES[1], GROUP_SAVINGS: SERIES[2]}
#: categories drawn one by one in the chart of a group; the rest is added up
MAX_CATEGORIES = 6
#: a change against the year before is highlighted from this many euros per month and percent
NOTABLE_CHANGE = (10.0, 0.10)

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
    "<p><b>Kategorien:</b> Klick auf eine Zeile zeigt ihre Entwicklung im Diagramm, Doppelklick die Buchungen. Rechts"
    " in der Zeile die Budgetgruppe einer Kategorie bzw. das Ziel einer Gruppe nach der 50/30/20-Regel.</p>"
    "<p><b>ggü. Vorjahr:</b> Veränderung gegenüber denselben Monaten ein Jahr davor; rot ungünstig, grün günstig.</p>"
    "<p><b>Diagramm:</b> Blau hinterlegt ist der gewählte Zeitraum; die Maus zeigt die Werte eines Monats.</p>"
    + ACCRUAL_DETAILS
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
    "Hauptkategorien nach Budgetgruppe",
    "Durchschnitt pro Monat im Zeitraum, periodengerecht",
    "Anteil am Nettoeinkommen",
    "Veränderung pro Monat gegenüber denselben Monaten ein Jahr davor; rot ungünstig, grün günstig",
    "Budgetgruppe der Kategorie bzw. Ziel der Gruppe in % des Einkommens (50/30/20-Regel)",
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
    """One series of the chart: an area stacked on the areas below it, or a line."""

    name: str
    color: str
    values: np.ndarray
    area: bool = True
    dashed: bool = False


class BudgetChart(QWidget):
    """The development over time of what is selected in the breakdown, with the budget period shaded."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = make_label("", self, "heading")
        self.smooth_check = QCheckBox("gleitender Ø 12 Monate", self)
        self.smooth_check.setChecked(True)
        self.smooth_check.setToolTip(
            "Gleitender Durchschnitt: Jeder Punkt ist der Durchschnitt der 12 Monate bis dahin und zeigt den Trend ohne"
            " Ausreißer durch einzelne große Zahlungen. Aus: jeder Monat einzeln."
        )
        self.legend = make_label("", self, wrap=True)
        self.legend.setTextFormat(Qt.TextFormat.RichText)
        self.plot = pg.PlotWidget(axisItems={"bottom": GermanDateAxis(orientation="bottom"), "left": EuroAxis("left")})
        self.plot.setBackground("w")
        self.plot.setMenuEnabled(False)
        self.plot.setMouseEnabled(x=False, y=False)
        self.plot.hideButtons()
        self.plot.showGrid(x=False, y=True, alpha=0.15)
        for name in ("left", "bottom"):
            axis = self.plot.getAxis(name)
            axis.setPen(pg.mkPen(BORDER))
            axis.setTextPen(pg.mkPen(MUTED))
        self.plot.setToolTip("Blau hinterlegt: der gewählte Zeitraum")
        header = QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(self.smooth_check)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.legend)
        layout.addWidget(self.plot, 1)
        self.x = np.array([])
        self.months: list[pd.Period] = []
        self.layers: list[Layer] = []
        self.cursor = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen(BORDER, width=1))
        self.plot.scene().sigMouseMoved.connect(self._hover)

    def draw(self, title: str, months: pd.PeriodIndex, layers: list[Layer], period: tuple[pd.Period, pd.Period]):
        self.title.setText(title)
        self.plot.clear()
        self.layers, self.months = layers, list(months)
        self.x = _timestamps(months)
        if len(months) < 2:
            self.legend.setText("Zu wenige Monate für einen Verlauf.")
            return
        start, end = period
        region = pg.LinearRegionItem(
            values=(_timestamps([start])[0], _timestamps([end + 1])[0]),
            movable=False,
            brush=pg.mkBrush(42, 120, 214, 22),
            pen=pg.mkPen(None),
        )
        region.setZValue(-20)
        self.plot.addItem(region)
        level = np.zeros(len(self.x))
        values = [level]
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
                values.append(top)
            else:
                style = Qt.PenStyle.DashLine if layer.dashed else Qt.PenStyle.SolidLine
                self.plot.plot(self.x, layer.values, pen=pg.mkPen(color, width=2, style=style))
                values.append(layer.values)
        self.plot.addItem(self.cursor, ignoreBounds=True)
        self.cursor.hide()
        stacked = np.concatenate(values)
        low, high = min(0.0, float(np.nanmin(stacked))), max(1.0, float(np.nanmax(stacked)))
        self.plot.setYRange(low, high * 1.08, padding=0)
        self.plot.setXRange(self.x[0], self.x[-1], padding=0.01)
        self.legend.setText(
            "&nbsp;&nbsp;&nbsp;".join(
                f"<span style='color:{layer.color}'>{'■' if layer.area else '━' if not layer.dashed else '┅'}</span>"
                f" {html.escape(layer.name)}"
                for layer in reversed(layers)
            )
        )

    def _hover(self, position) -> None:
        if len(self.x) < 2 or not self.plot.sceneBoundingRect().contains(position):
            self.cursor.hide()
            return
        x = self.plot.getPlotItem().vb.mapSceneToView(position).x()
        i = int(np.clip(np.searchsorted(self.x, x), 0, len(self.x) - 1))
        if i > 0 and abs(self.x[i - 1] - x) < abs(self.x[i] - x):
            i -= 1
        self.cursor.setPos(self.x[i])
        self.cursor.show()
        rows = "".join(
            f"<tr><td><span style='color:{layer.color}'>■</span> {html.escape(layer.name)}</td>"
            f"<td align='right'>&nbsp;{euro(float(np.nan_to_num(layer.values[i])))}</td></tr>"
            for layer in reversed(self.layers)
        )
        QToolTip.showText(QCursor.pos(), f"<b>{format_month(self.months[i])}</b><table>{rows}</table>", self.plot)


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
        self._group_by_category: dict[str, str] = {}
        self._filling = False

        self.banner = InfoBanner(model, "budget", BANNER, ACCRUAL_DETAILS, "Periodengerechte Sicht", self)
        self.help_button = HelpButton(HELP, "Budget", self)
        self.period_combo = QComboBox(self)
        self.period_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.period_combo.setToolTip(
            "Welche Monate ausgewertet werden: die letzten 12 abgeschlossenen Monate oder ein Kalenderjahr. Der"
            " laufende Monat zählt erst, wenn er vorbei ist."
        )
        self.period_note = make_label("", self, "hint")
        set_tone(self.period_note, "warning")
        self.exclude_select = CategorySelect("Ausblenden:", self)
        self.exclude_select.setMinimumWidth(260)
        self.exclude_select.setToolTip("Kategorien, die nicht mitgezählt werden, z. B. eine einmalige Erbschaft.")
        controls = QHBoxLayout()
        controls.addWidget(make_label("Zeitraum:", self))
        controls.addWidget(self.period_combo)
        controls.addWidget(self.period_note)
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

        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(5)
        self.tree.setHeaderLabels(["Kategorie", "Ø Monat", "Anteil", "ggü. Vorjahr", "Gruppe / Ziel"])
        for column, tip in enumerate(COLUMN_TIPS):
            self.tree.headerItem().setToolTip(column, tip)
            if column:
                self.tree.headerItem().setTextAlignment(column, Qt.AlignmentFlag.AlignRight)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 80), (2, 56), (3, 88), (4, 172)):
            self.tree.setColumnWidth(column, width)
        self.tree.setRootIsDecorated(True)
        self.tree.setUniformRowHeights(True)
        breakdown = Card(self)
        breakdown.content.addWidget(make_label("Kategorien", breakdown, "heading"))
        breakdown.content.addWidget(self.tree, 1)

        self.chart = BudgetChart(self)
        chart_card = Card(self)
        chart_card.content.addWidget(self.chart)
        splitter = QSplitter(Qt.Orientation.Horizontal, self)
        splitter.addWidget(breakdown)
        splitter.addWidget(chart_card)
        splitter.setChildrenCollapsible(False)
        splitter.setSizes([660, 700])

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
        self.exclude_select.selection_changed.connect(lambda c: model.update_settings(excluded_categories=c))
        self.chart.smooth_check.toggled.connect(self.draw_chart)
        self.tree.currentItemChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(self.open_detail)

    # ------------------------------------------------------------------ user input
    def _period_changed(self, _index: int) -> None:
        period = self.period_combo.currentData()
        if not self._filling and period:
            self.model.set_budget_period(period)

    def _share_changed(self, group: str, value: int) -> None:
        if not self._filling:
            self.model.set_budget_share(group, value / 100)

    def move_category(self, category: str, group: str) -> None:
        """Put a main category into another budget group (at the end of it)."""
        assignment = {
            g: [a.category for a in self.model.groups if a.group == g and a.category != category] for g in GROUP_NAMES
        }
        assignment[group].append(category)
        self.model.assign_groups(assignment)

    def _selection_changed(self, current: QTreeWidgetItem | None, _previous=None) -> None:
        if self._filling:
            return
        self.selected = None if current is None else current.data(0, Qt.ItemDataRole.UserRole)
        self.draw_chart()

    def open_detail(self, item: QTreeWidgetItem, _column: int = 0) -> None:
        """The transactions behind a row, as paid in the budget period."""
        kind, name = item.data(0, Qt.ItemDataRole.UserRole)
        months = self.model.budget_months(self.series)
        if months is None or kind == KEPT:
            return
        categories = [name] if kind == "category" else self.model.categories_in_group(name)
        title = display_category(name) if kind == "category" else TITLES[name]
        self.navigator.open_detail(str(months[0]), categories, title=title, end=str(months[1]))

    # ------------------------------------------------------------------ display
    def refresh(self) -> None:
        super().refresh()
        settings = self.model.settings
        self.banner.update_visibility()
        self.series = self.model.budget_series()
        self.report = self.model.budget_report(self.series)
        self.previous = self.model.budget_report(self.series, previous=True)
        self._filling = True
        try:
            self.exclude_select.set_options(self.model.unique_categories(), settings.excluded_categories)
            self.period_combo.clear()
            for period, start, end in self.model.budget_periods(self.series):
                self.period_combo.addItem(period_label(period, start, end), period)
            index = self.period_combo.findData(settings.budget_period)
            if index < 0 and self.period_combo.count():
                self.period_combo.addItem(settings.budget_period, settings.budget_period)
                index = self.period_combo.count() - 1
            self.period_combo.setCurrentIndex(index)
            self._fill_tree()
        finally:
            self._filling = False
        self.show_figures()
        self.draw_chart()

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
        current = None
        for group, (amount, categories) in rows.items():
            item = QTreeWidgetItem(self.tree)
            item.setData(0, Qt.ItemDataRole.UserRole, ("group", group))
            item.setText(0, TITLES[group])
            item.setToolTip(0, rich(HINTS[group]))
            for column in range(5):
                item.setFont(column, bold)
            self._amounts(item, report, amount, previous.get(("group", group)), group)
            if group in (GROUP_NEEDS, GROUP_WANTS):
                spin = QSpinBox(self.tree)
                spin.setRange(0, 100)
                spin.setPrefix("Ziel ")
                spin.setSuffix(" %")
                spin.setValue(round(settings.budget_shares.get(group, 0.0) * 100))
                spin.setToolTip(f"Ziel für {TITLES[group]} in % des Einkommens; Sparen erhält den Rest.")
                spin.valueChanged.connect(lambda value, g=group: self._share_changed(g, value))
                self.tree.setItemWidget(item, 4, spin)
                share = report.share(amount)
                over = share is not None and share > getattr(report, group).target + 0.005
                set_share_tone(item, over, "Ziel überschritten")
            elif group == GROUP_SAVINGS:
                item.setText(4, f"Ziel {percent(settings.savings_share)}")
                item.setToolTip(4, rich("Der Rest: 100 % minus Grundbedarf und Freizeit & Lebensstil"))
                item.setTextAlignment(4, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                share = report.share(amount)
                below = share is not None and share < settings.savings_share - 0.005
                set_share_tone(item, below, "Ziel verfehlt")
            for category, value in categories:
                child = QTreeWidgetItem(item)
                child.setData(0, Qt.ItemDataRole.UserRole, ("category", category))
                child.setText(0, display_category(category))
                self._amounts(child, report, value, previous.get(("category", category)), group)
                combo = QComboBox(self.tree)
                for name in GROUP_NAMES:
                    combo.addItem(TITLES[name], name)
                combo.setCurrentIndex(GROUP_NAMES.index(group))
                combo.setToolTip(
                    "Budgetgruppe der Kategorie\n" + "\n".join(f"{TITLES[g]}: {HINTS[g]}" for g in GROUP_NAMES)
                )
                combo.currentIndexChanged.connect(
                    lambda _i, c=category, box=combo: self.move_category(c, box.currentData())
                )
                self.tree.setItemWidget(child, 4, combo)
                if self.selected == ("category", category):
                    current = child
            if group == GROUP_SAVINGS:
                kept = QTreeWidgetItem(item)
                kept.setData(0, Qt.ItemDataRole.UserRole, (KEPT, GROUP_SAVINGS))
                kept.setText(0, "Rest auf den Konten")
                kept.setToolTip(
                    0,
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

    def _previous_amounts(self) -> dict[tuple[str, str], float]:
        """Per month in the year before: every group and category."""
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
        """Per month, share of the income and change against the year before of one row."""
        value = report.per_month(total)
        item.setText(1, euro(value))
        item.setText(2, percent(report.share(total)) if group != GROUP_INCOME or item.parent() else "")
        if before is None:
            item.setText(3, "–")
            item.setToolTip(3, "Keine Buchungen in denselben Monaten ein Jahr davor.")
        else:
            change = value - before
            item.setText(3, euro(change, signed=True) if abs(change) >= 0.5 else "±0 €")
            item.setToolTip(3, f"Ein Jahr davor: {euro(before)} pro Monat")
            notable = abs(change) >= max(NOTABLE_CHANGE[0], NOTABLE_CHANGE[1] * abs(before))
            if notable:
                more_is_good = group in (GROUP_INCOME, GROUP_SAVINGS)
                item.setForeground(3, pg.mkColor(GOOD if (change > 0) == more_is_good else BAD))
        for column in (1, 2, 3):
            item.setTextAlignment(column, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    # ------------------------------------------------------------------ chart
    def draw_chart(self, *_args) -> None:
        if self.series is None:
            return
        monthly = self.series.monthly
        months = self.model.budget_months(self.series)
        if monthly.empty or months is None:
            self.chart.draw("Verlauf", monthly.index, [], (pd.Period("2000-01", "M"),) * 2)
            return
        smoothed = self.chart.smooth_check.isChecked() and len(monthly) >= 13
        self.chart.smooth_check.setEnabled(len(monthly) >= 13)
        data = smooth(monthly) if smoothed else monthly
        groups = self.model.groups
        self._group_by_category = {a.category: a.group for a in groups}
        totals = group_totals(data, groups)
        income = totals[GROUP_INCOME].to_numpy()
        settings = self.model.settings
        kind, name = self.selected or ("all", "")
        if kind == KEPT:
            kind = "group"
        if kind == "group":
            title, layers = self._group_layers(data, totals, name, settings)
        elif kind == "category":
            sign = 1 if self._group_of(name) == GROUP_INCOME else -1
            values = sign * data[name].to_numpy() if name in data else np.zeros(len(data))
            title = display_category(name)
            layers = [Layer(title, GROUP_COLORS.get(self._group_of(name), SERIES[0]), values)]
        else:
            title = "Einkommen und Konsum"
            layers = [
                Layer(TITLES[GROUP_NEEDS], GROUP_COLORS[GROUP_NEEDS], totals[GROUP_NEEDS].to_numpy()),
                Layer(TITLES[GROUP_WANTS], GROUP_COLORS[GROUP_WANTS], totals[GROUP_WANTS].to_numpy()),
                Layer(
                    f"Konsumgrenze für {percent(settings.savings_share)} Sparquote",
                    MUTED,
                    income * (1 - settings.savings_share),
                    area=False,
                    dashed=True,
                ),
                Layer("Nettoeinkommen", TEXT, income, area=False),
            ]
        self.chart.draw(title, data.index, layers, months)

    def _group_of(self, category: str) -> str:
        return self._group_by_category.get(category, GROUP_NEEDS)

    def _group_layers(self, data: pd.DataFrame, totals: pd.DataFrame, group: str, settings):
        """The categories of a group stacked, largest at the bottom, with the target of the group."""
        sign = 1 if group == GROUP_INCOME else -1
        members = [c for c in data.columns if self._group_of(c) == group]
        # the color follows the category: ordered by the whole history, not by the shown period
        overall = self.series.monthly
        members.sort(key=lambda c: sign * float(overall[c].sum()) if c in overall else 0.0, reverse=True)
        shown, rest = members[:MAX_CATEGORIES], members[MAX_CATEGORIES:]
        if len(rest) == 1:
            shown, rest = members, []
        layers = [Layer(display_category(c), SERIES[i], sign * data[c].to_numpy()) for i, c in enumerate(shown)]
        if rest:
            layers.append(Layer("Sonstige", OTHER, sign * data[rest].sum(axis=1).to_numpy()))
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
        return TITLES[group], layers


def set_share_tone(item: QTreeWidgetItem, off_target: bool, message: str) -> None:
    """The share of a group in red when it misses its target."""
    if off_target:
        item.setForeground(2, pg.mkColor(BAD))
        item.setToolTip(2, message)
    else:
        item.setToolTip(2, "im Rahmen des Ziels")
