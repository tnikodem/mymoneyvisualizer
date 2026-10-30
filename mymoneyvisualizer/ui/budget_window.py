"""Budget by the 50/30/20 rule on the accrual basis: needs, wants and savings against shares of the income."""

from __future__ import annotations

import datetime
import html

import numpy as np
import pyqtgraph as pg
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
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
from mymoneyvisualizer.domain.budget import (
    SAVED,
    BudgetReport,
    BudgetSeries,
    GroupReport,
    group_totals,
    smooth,
    stacked_curves,
)
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.models import GROUP_INCOME, GROUP_NEEDS, GROUP_SAVINGS, GROUP_WANTS
from mymoneyvisualizer.domain.models import GROUPS as GROUP_NAMES
from mymoneyvisualizer.ui.common import GREY, PLOT_COLORS, CategorySelect, Window
from mymoneyvisualizer.ui.table_model import format_money

pg.setConfigOptions(antialias=True)

TITLES = {GROUP_INCOME: "Income", GROUP_NEEDS: "Needs", GROUP_WANTS: "Wants", GROUP_SAVINGS: "Savings"}
HINTS = {
    GROUP_INCOME: "Net income: salary, child benefit, interest, refunds.",
    GROUP_NEEDS: "What you need to live: rent, utilities, groceries, insurance, the way to work.",
    GROUP_WANTS: "What makes life nice: leisure, restaurants, travel, hobbies, subscriptions.",
    GROUP_SAVINGS: "Transfers to savings and investments that are not an account here, e.g. an ETF savings plan.",
}
PLOTTED_GROUPS = (GROUP_NEEDS, GROUP_WANTS, GROUP_SAVINGS)
GOOD, BAD = "#1b7f3b", "#b00020"


def euro(value: float) -> str:
    return f"{format_money(value, 0)} €"


def percent(value: float | None) -> str:
    return "–" if value is None else f"{round(100 * value)} %"


def period_text(report: BudgetReport) -> str:
    years = str(report.start_year) if report.start_year == report.end_year else f"{report.start_year}-{report.end_year}"
    if report.is_complete:
        return years
    return f"{years} ({report.months} of {report.period_months} months, until {report.last_date:%d.%m.%Y})"


def summary_html(report: BudgetReport | None) -> str:
    """The answer to "do I spend too much or too little?" for the budget period."""
    if report is None or report.months == 0:
        return "No transactions in the budget period."
    if report.savings_rate is None:
        return f"<b>{period_text(report)}</b>: no income in the budget period."
    room = report.room_per_month
    target = percent(report.savings.target)
    if room >= 0:
        verdict = f"You could spend <b>{euro(room)} more per month</b> and still save {target}."
        color = GOOD
    else:
        verdict = f"To save {target}, spend <b>{euro(-room)} less per month</b>."
        color = BAD
    return (
        f"<b>{html.escape(period_text(report))}</b>: income {euro(report.per_month(report.income))} per month,"
        f" savings rate <b>{percent(report.savings_rate)}</b> (target {target}). "
        f"<span style='color: {color}'>{verdict}</span>"
    )


def group_html(report: BudgetReport | None, group: str) -> str:
    """Target and actual per month of one group, with its categories."""
    if report is None or report.months == 0:
        return ""
    part: GroupReport = getattr(report, group)
    rows = [("Target:", f"{percent(part.target)} = {euro(report.per_month(part.target * report.income))}")]
    if group == GROUP_SAVINGS:
        saved = report.saved
        rows.append(("<b>Saved:</b>", f"<b>{percent(report.share(saved))} = {euro(report.per_month(saved))}</b>"))
        rows += [(f"{html.escape(display_category(c))}:", euro(report.per_month(a))) for c, a in part.categories]
        if part.categories:
            rows.append(("kept on the accounts:", euro(report.per_month(saved - part.amount))))
    else:
        amount = part.amount
        rows.append(("<b>Actual:</b>", f"<b>{percent(report.share(amount))} = {euro(report.per_month(amount))}</b>"))
        rows += [(f"{html.escape(display_category(c))}:", euro(report.per_month(a))) for c, a in part.categories]
    table = "".join(f"<tr><td>{label}</td><td align='right'>{value}</td></tr>" for label, value in rows)
    return f"<b>{TITLES[group]}</b>, per month<table>{table}</table>"


def _timestamps(index) -> np.ndarray:
    return np.array([p.start_time.timestamp() for p in index], dtype=float)


class BudgetPlot(QWidget):
    """Stacked categories of one budget group against its target share of the income."""

    def __init__(self, group: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.group = group
        self.share_spin = QSpinBox(self)
        self.share_spin.setRange(0, 100)
        self.share_spin.setSuffix(" % of income")
        self.share_label = QLabel(self)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem(orientation="bottom")})
        self.plot.setBackground("w")
        self.plot.addLegend()
        self.report_view = QTextBrowser(self)
        self.report_view.setFixedWidth(300)

        header = QHBoxLayout()
        header.addWidget(QLabel(f"<b>{TITLES[group]}</b> target:", self))
        if group == GROUP_SAVINGS:
            self.share_spin.hide()
            header.addWidget(self.share_label)
        else:
            header.addWidget(self.share_spin)
        header.addStretch(1)
        body = QHBoxLayout()
        body.addWidget(self.plot, 1)
        body.addWidget(self.report_view)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(header)
        layout.addLayout(body)

    def draw(self, monthly, groups, target: float, start_year: int, end_year: int) -> None:
        """Draw ``monthly`` (accrued, maybe smoothed) amounts; ``target`` is the share of the income."""
        self.plot.clear()
        if len(monthly) < 2:
            return
        x = _timestamps(monthly.index)
        pen = pg.mkPen(color=GREY, width=2, style=Qt.PenStyle.DashLine)
        for position in (datetime.datetime(start_year, 1, 1), datetime.datetime(end_year, 12, 31)):
            self.plot.addItem(pg.InfiniteLine(pos=position.timestamp(), angle=90, movable=False, pen=pen))

        totals = group_totals(monthly, groups)
        target_line = totals[GROUP_INCOME].to_numpy() * target
        self.plot.plot(x, target_line, pen=pg.mkPen(color=(0, 0, 0), width=2), name="target")
        if self.group == GROUP_SAVINGS:
            saved = totals[SAVED].to_numpy()
            self.plot.plot(x, saved, pen=pg.mkPen(color=GOOD, width=3), name="saved")
            levels = [saved]
        else:
            levels = []
        curves = stacked_curves(monthly, groups, self.group)
        previous = np.zeros(len(monthly))
        items = []
        for i, (category, level) in enumerate(curves):
            color = PLOT_COLORS[(i + 1) % len(PLOT_COLORS)]
            fill = pg.FillBetweenItem(pg.PlotDataItem(x, previous), pg.PlotDataItem(x, level), brush=(*color, 100))
            items.append((category, level, color, fill))
            previous = level
        for category, level, color, fill in reversed(items):  # legend in stacking order from the top
            self.plot.addItem(fill)
            self.plot.plot(x, level, pen=pg.mkPen(color=color, width=2), name=display_category(category))
        if curves and self.group != GROUP_SAVINGS:
            self.plot.addItem(
                pg.FillBetweenItem(pg.PlotDataItem(x, previous), pg.PlotDataItem(x, target_line), brush=(0, 0, 0, 25))
            )
        values = [target_line, *levels, *[level for _, level in curves]]
        top = max([float(np.nanmax(v)) for v in values] + [1.0])
        bottom = min([float(np.nanmin(v)) for v in values] + [0.0])
        self.plot.setYRange(bottom * 1.2, top * 1.2, padding=0)
        self.plot.setXRange(x[0], x[-1], padding=0)


class BudgetWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS, GROUPS, ACCOUNTS})

    def __init__(self, model, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.setWindowTitle("Budget")
        self.resize(1400, 1000)
        self.series: BudgetSeries | None = None
        self.report: BudgetReport | None = None
        self._filling = False

        self.start_combo, self.end_combo = QComboBox(self), QComboBox(self)
        self.smooth_check = QCheckBox("12-month average", self)
        self.smooth_check.setChecked(True)
        self.smooth_check.setToolTip("Every point shows the average of the last 12 months: the long-term view.")
        self.exclude_select = CategorySelect("Exclude:", self)
        self.exclude_select.setMinimumWidth(300)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Budget period:", self))
        controls.addWidget(self.start_combo)
        controls.addWidget(QLabel("-", self))
        controls.addWidget(self.end_combo)
        controls.addWidget(self.smooth_check)
        controls.addStretch(1)
        controls.addWidget(self.exclude_select)
        self.summary_label = QLabel(self)
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.TextFormat.RichText)

        self.lists: dict[str, QListWidget] = {}
        lists = QVBoxLayout()
        hint = QLabel("Drag the categories into their budget group.", self)
        hint.setWordWrap(True)
        hint.setFixedWidth(170)
        lists.addWidget(hint)
        for group in GROUP_NAMES:
            widget = QListWidget(self)
            widget.setFixedWidth(170)
            widget.setToolTip(HINTS[group])
            widget.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
            widget.setDefaultDropAction(Qt.DropAction.MoveAction)
            widget.model().rowsInserted.connect(self._lists_changed)
            widget.model().rowsRemoved.connect(self._lists_changed)
            widget.model().rowsMoved.connect(self._lists_changed)
            title = QLabel(TITLES[group] + ":", self)
            title.setToolTip(HINTS[group])
            lists.addWidget(title)
            lists.addWidget(widget)
            self.lists[group] = widget

        self.plots = {group: BudgetPlot(group, self) for group in PLOTTED_GROUPS}
        plots = QVBoxLayout()
        for plot in self.plots.values():
            plots.addWidget(plot)
        body = QHBoxLayout()
        body.addLayout(lists)
        body.addLayout(plots, 1)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.summary_label)
        layout.addLayout(body)
        self.setCentralWidget(central)

        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self.save_groups)
        self.exclude_select.selection_changed.connect(lambda c: model.update_settings(excluded_categories=c))
        self.start_combo.currentTextChanged.connect(self._period_changed)
        self.end_combo.currentTextChanged.connect(self._period_changed)
        self.smooth_check.toggled.connect(self.draw)
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
        self.report = self.model.budget_report(self.series)
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
                for assignment in self.model.groups:
                    if assignment.group == group and assignment.category in shown:
                        item = QListWidgetItem(display_category(assignment.category))
                        item.setData(Qt.ItemDataRole.UserRole, assignment.category)
                        widget.addItem(item)
            for group, plot in self.plots.items():
                if group in settings.budget_shares:
                    plot.share_spin.setValue(round(settings.budget_shares[group] * 100))
            self.plots[GROUP_SAVINGS].share_label.setText(f"{percent(settings.savings_share)} of income (the rest)")
        finally:
            self._filling = False
        self.draw()

    def draw(self, *_args) -> None:
        if self.series is None:
            return
        settings = self.model.settings
        monthly = smooth(self.series.monthly) if self.smooth_check.isChecked() else self.series.monthly
        self.summary_label.setText(summary_html(self.report))
        targets = {**settings.budget_shares, GROUP_SAVINGS: settings.savings_share}
        for group, plot in self.plots.items():
            plot.report_view.setHtml(group_html(self.report, group))
            plot.draw(monthly, self.model.groups, targets[group], settings.budget_start, settings.budget_end)

    def _years(self, start: int, end: int) -> list[int]:
        current = datetime.date.today().year
        first = start
        if self.series is not None and not self.series.monthly.empty:
            first = min(first, int(self.series.monthly.index[0].year))
        return list(range(max(current + 1, end), min(first, start, current - 10) - 1, -1))
