"""Budget graph: stacked expenses per group against a share of the income."""

from __future__ import annotations

import datetime
import html

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSpinBox,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import ACCOUNTS, GROUPS, RULES, SETTINGS, TRANSACTIONS
from mymoneyvisualizer.domain.budget import BudgetReport, BudgetSeries, income_series, stacked_expenses
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.models import EXPENSE_GROUPS, GROUP_NEEDS, GROUP_WANTS
from mymoneyvisualizer.domain.models import GROUPS as GROUP_NAMES
from mymoneyvisualizer.ui.common import GREY, PLOT_COLORS, CategorySelect, Window
from mymoneyvisualizer.ui.table_model import format_money

pg.setConfigOptions(antialias=True)

LIST_TITLES = {"income": "Income", GROUP_NEEDS: "Needs", GROUP_WANTS: "Wants"}


def euro(value: float) -> str:
    return f"{format_money(value, 0)} €"


def budget_html(report: BudgetReport) -> str:
    """Text next to a budget plot."""
    period = (
        str(report.start_year) if report.start_year == report.end_year else f"{report.start_year}-{report.end_year}"
    )
    rows = [(f"<b>{'Total' if report.is_complete else 'Expected budget'}:</b>", euro(report.expected_total))]
    rows += [(f"{html.escape(display_category(category))}:", euro(amount)) for category, amount in report.consumed]
    rows.append(("<b>Consumed total:</b>", f"<b>{euro(report.total_consumed)}</b>"))
    if report.is_complete:
        rows.append(("Difference:", euro(report.balance)))
    else:
        rows.append(("Remaining total:", euro(report.balance)))
        if report.remaining_per_month is not None:
            rows.append(("Remaining per month:", euro(report.remaining_per_month)))
        if report.trend is not None:
            rows.append(("Trend end of period:", euro(report.trend)))
    table = "".join(f"<tr><td>{label}</td><td align='right'>{value}</td></tr>" for label, value in rows)
    return (
        f"<h3>{report.group.title()} budget {period}</h3>"
        f"covered days: {report.covered_days}/{report.total_days} ({round(report.covered_percent)}%)<br/>"
        f"last transaction: {report.last_recorded_date:%d.%m.%Y}<br/>"
        f"remaining: {report.remaining_months:.1f} months<br/><table>{table}</table>"
    )


def _timestamps(index) -> np.ndarray:
    return np.array([p.start_time.timestamp() for p in index], dtype=float)


class BudgetPlot(QWidget):
    def __init__(self, group: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.group = group
        self.share_spin = QSpinBox(self)
        self.share_spin.setRange(0, 100)
        self.share_spin.setSuffix(" % of income")
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.setBackground("w")
        self.plot.addLegend()
        self.report_view = QTextBrowser(self)
        self.report_view.setFixedWidth(280)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{LIST_TITLES[group]}</b> budget:", self))
        header.addWidget(self.share_spin)
        header.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.plot, 1)
        body.addWidget(self.report_view)
        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addLayout(body)

    def draw(
        self,
        series: BudgetSeries,
        groups,
        share: float,
        start_year: int,
        end_year: int,
        report: BudgetReport | None,
    ) -> None:
        self.plot.clear()
        self.report_view.setHtml(budget_html(report) if report is not None else "")
        monthly = series.monthly
        if len(monthly) < 2:
            return
        x = _timestamps(monthly.index)
        pen = pg.mkPen(color=GREY, width=2, style=Qt.PenStyle.DashLine)
        for position in (datetime.datetime(start_year, 1, 1), datetime.datetime(end_year, 12, 31)):
            self.plot.addItem(pg.InfiniteLine(pos=position.timestamp(), angle=90, movable=False, pen=pen))

        budget_line = income_series(monthly, groups).to_numpy() * share
        self.plot.plot(x, budget_line, pen=pg.mkPen(color=(0, 0, 0), width=2), name="budget")

        curves = stacked_expenses(monthly, groups, self.group)
        previous = np.zeros(len(monthly))
        items = []
        for i, (category, level) in enumerate(curves):
            color = PLOT_COLORS[(i + 1) % len(PLOT_COLORS)]
            lower = pg.PlotDataItem(x, previous)
            upper = pg.PlotDataItem(x, level)
            items.append((category, level, color, pg.FillBetweenItem(lower, upper, brush=(*color, 100))))
            previous = level
        for category, level, color, fill in reversed(items):  # legend in stacking order from the top
            self.plot.addItem(fill)
            self.plot.plot(x, level, pen=pg.mkPen(color=color, width=2), name=display_category(category))
        if curves:
            self.plot.addItem(
                pg.FillBetweenItem(pg.PlotDataItem(x, previous), pg.PlotDataItem(x, budget_line), brush=(0, 0, 0, 25))
            )
        top = max([float(budget_line.max()), *[float(level.max()) for _, level in curves], 1.0])
        self.plot.setYRange(0, top * 1.2, padding=0)
        self.plot.setXRange(x[1], x[-1], padding=0)  # the first month is usually incomplete


class BudgetWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS, GROUPS, ACCOUNTS})

    def __init__(self, model, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.setWindowTitle("Budget")
        self.resize(1400, 1000)
        self.series: BudgetSeries | None = None
        self._filling = False

        self.exclude_select = CategorySelect("Exclude:", self)
        self.exclude_select.setMinimumWidth(300)
        self.start_combo, self.end_combo = QComboBox(self), QComboBox(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Budget period:", self))
        controls.addWidget(self.start_combo)
        controls.addWidget(QLabel("-", self))
        controls.addWidget(self.end_combo)
        controls.addStretch(1)
        controls.addWidget(self.exclude_select)

        self.lists: dict[str, QListWidget] = {}
        lists = QVBoxLayout()
        for group in GROUP_NAMES:
            widget = QListWidget(self)
            widget.setFixedWidth(170)
            widget.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            widget.setDefaultDropAction(Qt.DropAction.MoveAction)
            widget.model().rowsInserted.connect(self._lists_changed)
            widget.model().rowsRemoved.connect(self._lists_changed)
            widget.model().rowsMoved.connect(self._lists_changed)
            lists.addWidget(QLabel(LIST_TITLES[group] + ":", self))
            lists.addWidget(widget)
            self.lists[group] = widget

        self.plots = {group: BudgetPlot(group, self) for group in EXPENSE_GROUPS}
        plots = QVBoxLayout()
        for plot in self.plots.values():
            plots.addWidget(plot)
        body = QHBoxLayout()
        body.addLayout(lists)
        body.addLayout(plots, 1)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addLayout(body)
        self.setCentralWidget(central)

        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self.save_groups)
        self.exclude_select.selection_changed.connect(
            lambda categories: model.update_settings(excluded_categories=categories)
        )
        self.start_combo.currentTextChanged.connect(self._period_changed)
        self.end_combo.currentTextChanged.connect(self._period_changed)
        for group, plot in self.plots.items():
            plot.share_spin.valueChanged.connect(lambda percent, g=group: self._share_changed(g, percent))

    # ------------------------------------------------------------------ user input
    def _period_changed(self, _text: str) -> None:
        if not self._filling and self.start_combo.currentText() and self.end_combo.currentText():
            self.model.set_budget_period(int(self.start_combo.currentText()), int(self.end_combo.currentText()))

    def _share_changed(self, group: str, percent: int) -> None:
        if not self._filling:
            self.model.set_budget_share(group, percent / 100)

    def _lists_changed(self, *_args) -> None:
        if not self._filling:
            self._sync_timer.start(0)

    def assignment(self) -> dict[str, list[str]]:
        return {
            group: [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]
            for group, widget in self.lists.items()
        }

    def save_groups(self) -> None:
        self.model.assign_groups(self.assignment())

    # ------------------------------------------------------------------ display
    def refresh(self) -> None:
        super().refresh()
        settings = self.model.settings
        self.series = self.model.budget_series()
        groups = self.model.groups
        shown = set(self.series.monthly.columns)

        self._filling = True
        try:
            self.exclude_select.set_options(self.model.unique_categories(), settings.excluded_categories)
            years = self._years(settings.budget_start, settings.budget_end)
            for combo, value in ((self.start_combo, settings.budget_start), (self.end_combo, settings.budget_end)):
                combo.clear()
                combo.addItems([str(y) for y in years])
                combo.setCurrentText(str(value))
            for group, widget in self.lists.items():
                widget.clear()
                for assignment in groups:
                    if assignment.group == group and assignment.category in shown:
                        item = QListWidgetItem(display_category(assignment.category))
                        item.setData(Qt.ItemDataRole.UserRole, assignment.category)
                        widget.addItem(item)
            for group, plot in self.plots.items():
                plot.share_spin.setValue(round(settings.budget_shares[group] * 100))
        finally:
            self._filling = False

        for group, plot in self.plots.items():
            plot.draw(
                self.series,
                groups,
                settings.budget_shares[group],
                settings.budget_start,
                settings.budget_end,
                self.model.budget_report(group, self.series),
            )

    def _years(self, start: int, end: int) -> list[int]:
        current = datetime.date.today().year
        first = start
        if self.series is not None and not self.series.monthly.empty:
            first = min(first, int(self.series.monthly.index[0].year))
        return list(range(max(current + 1, end), min(first, start, current - 10) - 1, -1))
