"""Income & expenses as paid (cash basis): monthly sums per category, unusual months highlighted, the transactions
behind a cell."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget

from mymoneyvisualizer.app import ACCOUNTS, RULES, SETTINGS, TRANSACTIONS
from mymoneyvisualizer.domain.analysis import (
    EXPENSES,
    INCOME,
    MONTHLY_AVERAGE,
    NET,
    SAVINGS,
    SUMMARY,
    SUMMARY_LABELS,
    TOTAL,
    last_complete_month,
    month_key,
    ordered_month_range,
    summary_groups,
)
from mymoneyvisualizer.domain.budget import IN_PERIOD, SOLD, SPREAD_AMOUNT, SPREAD_FROM, SPREAD_TO
from mymoneyvisualizer.domain.categories import display_category
from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.ui.budget_window import ACCRUAL_DETAILS
from mymoneyvisualizer.ui.common import (
    LESS_EXPENSE,
    MORE_EXPENSE,
    TOTAL_BACKGROUND,
    CategorySelect,
    HelpButton,
    InfoBanner,
    Window,
    make_label,
)
from mymoneyvisualizer.ui.table_model import (
    CATEGORY,
    DATE,
    MONEY,
    MONEY0,
    MONTHS,
    Column,
    DataFrameModel,
    DataFrameView,
    format_money,
    format_month,
    format_month_range,
    format_months,
)

if TYPE_CHECKING:
    from mymoneyvisualizer.ui.main_window import MainWindow

CATEGORY_LEVELS = ("Hauptkategorien", "Unterkategorien", "3. Ebene", "4. Ebene")
TOTALS = (TOTAL, MONTHLY_AVERAGE)
MONTHS_SHOWN = 12 * 12
#: column with the category as shown (the category column keeps the value for lookups)
LABEL = "label"
LAST_12 = "last 12"
CUSTOM = "custom"
BANNER = (
    "<b>Zahlungssicht:</b> Jede Buchung zählt im Monat der Zahlung. Das <i>Budget</i> rechnet periodengerecht, daher"
    " andere Werte."
)
HELP = (
    "<p>Summen pro Monat und Kategorie in Zahlungssicht. Doppelklick auf eine Zelle zeigt die Buchungen dahinter.</p>"
    "<p><b>Abweichungen:</b> Monate, die deutlich vom Median der 12 Monate davor abweichen, z. B. eine doppelte oder"
    " fehlende Miete. Rot ungünstig (mehr Ausgaben, weniger Einnahmen), grün günstig; die Maus auf der Zelle zeigt den"
    " Vergleich.</p>"
    "<p><b>Saldo:</b> Veränderung des Geldes auf allen Konten zusammen.</p>"
)
DETAIL_HELP = "Doppelklick auf eine Buchung ändert ihre Kategorie."
BUDGET_DETAIL_HELP = (
    "<p>Alle Zahlungen, die periodengerecht in den Zeitraum zählen: auch frühere, die in den Zeitraum hineinverteilt"
    " sind, und von Zahlungen, die über den Zeitraum hinaus verteilt sind, nur ihr Anteil.</p>"
    "<p><b>Betrag im Zeitraum</b> ist dieser Anteil; zusammen ergeben die Zeilen den Wert im Budget."
    " <b>verteilt</b> nennt den ganzen verteilten Betrag und die Dauer; bei Anschaffungen mit Restwert oder Verkauf"
    " ist das nur der Wertverlust.</p>"
    f"<p>{DETAIL_HELP}</p>"
)
#: column of the budget detail: the amount a transaction spreads and over how long, as text
SPREAD = "spread"
SUMMARY_TIPS = {
    INCOME: "Alle Kategorien der Budgetgruppe Einkommen.",
    EXPENSES: "Alle Kategorien der Budgetgruppen Grundbedarf und Wünsche.",
    SAVINGS: "Alle Kategorien der Budgetgruppe Sparen, z. B. ein ETF-Sparplan.",
    NET: "Um so viel hat sich das Geld auf allen Konten zusammen verändert (Umbuchungen zwischen eigenen Konten heben"
    " sich auf).",
}
DETAIL_COLUMNS = [
    Column(Col.transaction_id, "id", hidden=True),
    Column(Col.account, "Konto", width=110),
    Column(Col.date, "Datum", DATE, 90),
    Column(Col.recipient, "Empfänger", width=260),
    Column(Col.description, "Verwendungszweck", width=520),
    Column(Col.value, "Betrag", MONEY, 110),
    Column(Col.category, "Kategorie", CATEGORY, 160),
    Column(Col.spread_months, "Verteilt über", MONTHS, 90, tooltip="Im Budget über so viele Monate verteilt."),
]


BUDGET_DETAIL_COLUMNS = [
    Column(Col.transaction_id, "id", hidden=True),
    Column(Col.date, "bezahlt am", DATE, 90),
    Column(Col.recipient, "Empfänger", width=220),
    Column(Col.description, "Verwendungszweck", width=320),
    Column(IN_PERIOD, "Betrag im Zeitraum", MONEY, 150, tooltip="So viel der Zahlung zählt im Zeitraum"),
    Column(
        SPREAD,
        "verteilt",
        width=220,
        tooltip="Der ganze verteilte Betrag und über wie lange, ab dem Monat der Zahlung; bei Anschaffungen mit"
        " Restwert oder Verkauf nur der Wertverlust",
    ),
    Column(Col.category, "Kategorie", CATEGORY, 160),
    Column(Col.account, "Konto", width=110),
]


def spread_text(row) -> str:
    """``-900,00 € über 1 Jahr``; for a purchase whose sale is included until the sale; ``""`` if not spread."""
    months = (row[SPREAD_TO] - row[SPREAD_FROM]).n + 1
    if months <= 1:
        return ""
    text = f"{format_money(float(row[SPREAD_AMOUNT]))} € über {format_months(months)}"
    return f"{text} (verkauft)" if row[SOLD] else text


def default_months(last_date=None, today: pd.Timestamp | None = None) -> tuple[str, str]:
    """The last twelve complete months up to the last transaction."""
    today = today if today is not None else pd.Timestamp.today()
    end = last_complete_month(last_date if last_date is not None else today, today)
    return month_key(end - 11), month_key(end)


class IncomeExpensesWindow(Window):
    topics = frozenset({TRANSACTIONS, RULES, SETTINGS, ACCOUNTS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.setWindowTitle("Einnahmen & Ausgaben")
        self.resize(1600, 820)
        self.deviation = pd.DataFrame()
        self.baseline = pd.DataFrame()
        self._filling = False

        self.banner = InfoBanner(model, "income expenses", BANNER, ACCRUAL_DETAILS, "Zahlungssicht", self)
        self.help_button = HelpButton(HELP + ACCRUAL_DETAILS, "Einnahmen & Ausgaben", self)
        self.period_combo = QComboBox(self)
        self.period_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToContents)
        self.period_combo.setToolTip("Schnellwahl des Zeitraums; der laufende Monat zählt erst, wenn er vorbei ist.")
        self.start_combo, self.end_combo = QComboBox(self), QComboBox(self)
        self.start_combo.setToolTip("Erster Monat")
        self.end_combo.setToolTip("Letzter Monat")
        self.level_combo = QComboBox(self)
        self.level_combo.addItems(CATEGORY_LEVELS)
        self.level_combo.setToolTip("Hauptkategorien (Wohnen) oder Unterkategorien (Wohnen.Miete)")
        self.filter_edit = QLineEdit(self)
        self.filter_edit.setPlaceholderText("Kategorie filtern")
        self.filter_edit.setClearButtonEnabled(True)
        self.filter_edit.setToolTip("Nur Kategorien, die so beginnen, z. B. Wohnen")
        self.exclude_select = CategorySelect("Ausblenden:", self)
        self.exclude_select.setMinimumWidth(250)
        self.exclude_select.setToolTip(
            "Kategorien, die hier und im Budget nicht mitgezählt werden, z. B. eine einmalige Erbschaft."
        )
        self.internal_transfers_check = QCheckBox("Umbuchungen ausblenden", self)
        self.internal_transfers_check.setToolTip(
            "Umbuchungen zwischen eigenen Konten, z. B. vom Giro- aufs Tagesgeldkonto, sind weder Einnahme noch"
            " Ausgabe. Ihre Kategorie ist der Name des Zielkontos."
        )
        self.deviation_check = QCheckBox("Abweichungen markieren", self)
        self.deviation_check.setChecked(True)
        self.deviation_check.setToolTip(
            "Monate, die deutlich vom Median der 12 Monate davor abweichen, z. B. eine doppelte oder fehlende"
            " Miete. Die Maus auf der Zelle zeigt den Vergleich."
        )
        more = make_label("ungünstig", self, "chip")
        more.setStyleSheet(f"background: {MORE_EXPENSE.name()};")
        more.setToolTip("mehr ausgegeben oder weniger eingenommen als üblich")
        less = make_label("günstig", self, "chip")
        less.setStyleSheet(f"background: {LESS_EXPENSE.name()};")
        less.setToolTip("weniger ausgegeben oder mehr eingenommen als üblich")
        self.legend = (more, less)

        # two rows, so the window also fits on small screens
        selection, display = QHBoxLayout(), QHBoxLayout()
        for widget in (
            make_label("Zeitraum:", self),
            self.period_combo,
            self.start_combo,
            make_label("–", self),
            self.end_combo,
            make_label("   Ebene:", self),
            self.level_combo,
            self.filter_edit,
        ):
            selection.addWidget(widget)
        for widget in (self.exclude_select, self.internal_transfers_check, self.deviation_check, more, less):
            display.addWidget(widget)
        selection.addStretch(1)
        selection.addWidget(self.help_button)
        display.addStretch(1)

        self.table_model = DataFrameModel([], self, background=self._background, tooltip=self._tooltip)
        self.table = DataFrameView(self.table_model, self, pinned=lambda frame: (frame[SUMMARY] != "").to_numpy())
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(self.banner)
        layout.addLayout(selection)
        layout.addLayout(display)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        self._fill_months()
        self.set_months(*default_months(self._last_date()))
        self.period_combo.currentIndexChanged.connect(self._preset_chosen)
        self.start_combo.currentIndexChanged.connect(lambda _: self._months_changed("start"))
        self.end_combo.currentIndexChanged.connect(lambda _: self._months_changed("end"))
        self.exclude_select.selection_changed.connect(
            lambda categories: model.update_settings(excluded_categories=categories)
        )
        self.internal_transfers_check.toggled.connect(lambda hide: model.update_settings(hide_internal_transfers=hide))
        self.level_combo.currentIndexChanged.connect(self.refresh)
        self.filter_edit.textChanged.connect(self.refresh)
        self.deviation_check.toggled.connect(self.refresh)
        self.table.doubleClicked.connect(self.open_detail)

    # ------------------------------------------------------------------ period
    def _last_date(self) -> pd.Timestamp | None:
        df = self.model.transactions()
        return None if df.empty else df[Col.date].max()

    def _fill_months(self) -> None:
        """The month choices: twelve years back and every month with transactions."""
        current = pd.Period(pd.Timestamp.today(), freq="M")
        first = current - (MONTHS_SHOWN - 1)
        df = self.model.transactions()
        if not df.empty:
            first = min(first, pd.Period(df[Col.date].min(), freq="M"))
        months = pd.period_range(first, current, freq="M")[::-1]
        self._filling = True
        try:
            for combo in (self.start_combo, self.end_combo):
                selected = combo.currentData()
                combo.clear()
                for month in months:
                    combo.addItem(format_month(month), month_key(month))
                if selected:
                    combo.setCurrentIndex(max(combo.findData(selected), 0))
        finally:
            self._filling = False

    def _fill_presets(self) -> None:
        """Last twelve months, every year with transactions and a period of your own."""
        last = self._last_date()
        self._presets = {LAST_12: default_months(last)}
        self._filling = True
        try:
            self.period_combo.clear()
            self.period_combo.addItem("Letzte 12 Monate", LAST_12)
            df = self.model.transactions()
            if last is not None:
                end = last_complete_month(last)
                for year in range(end.year, df[Col.date].min().year - 1, -1):
                    self._presets[str(year)] = (f"{year}-01", month_key(min(pd.Period(f"{year}-12", "M"), end)))
                    self.period_combo.addItem(str(year), str(year))
            self.period_combo.addItem("Eigener Zeitraum", CUSTOM)
            self._select_preset()
        finally:
            self._filling = False

    def _select_preset(self) -> None:
        months = self.months
        preset = next((key for key, value in self._presets.items() if value == months), CUSTOM)
        self.period_combo.blockSignals(True)
        self.period_combo.setCurrentIndex(self.period_combo.findData(preset))
        self.period_combo.blockSignals(False)

    def _preset_chosen(self, _index: int) -> None:
        preset = self.period_combo.currentData()
        if not self._filling and preset in self._presets:
            self.set_months(*self._presets[preset])

    @property
    def months(self) -> tuple[str, str]:
        return self.start_combo.currentData(), self.end_combo.currentData()

    def set_months(self, start: str, end: str) -> None:
        self._filling = True
        try:
            self.start_combo.setCurrentIndex(self.start_combo.findData(start))
            self.end_combo.setCurrentIndex(self.end_combo.findData(end))
        finally:
            self._filling = False
        self._months_changed("start")

    def _months_changed(self, changed: str) -> None:
        if self._filling or not all(self.months):
            return
        start, end = ordered_month_range(*self.months, changed)
        for combo, value in ((self.start_combo, start), (self.end_combo, end)):
            combo.blockSignals(True)
            combo.setCurrentIndex(combo.findData(value))
            combo.blockSignals(False)
        if hasattr(self, "_presets"):
            self._select_preset()
        self.refresh()

    @property
    def level(self) -> int:
        return self.level_combo.currentIndex()

    # ------------------------------------------------------------------ table
    def refresh(self, *_args) -> None:
        super().refresh()
        settings = self.model.settings
        self.banner.update_visibility()
        self._fill_months()
        self._fill_presets()
        self.exclude_select.set_options(self.model.unique_categories(), settings.excluded_categories)
        self.internal_transfers_check.blockSignals(True)
        self.internal_transfers_check.setChecked(settings.hide_internal_transfers)
        self.internal_transfers_check.blockSignals(False)
        for chip in self.legend:
            chip.setVisible(self.deviation_check.isChecked())

        start, end = self.months
        options = {"level": self.level, "category_filter": self.filter_edit.text()}
        table = self.model.income_expenses(start, end, **options)
        if table is not None and self.deviation_check.isChecked():
            self.deviation, self.baseline = self.model.income_expenses_deviations(start, end, **options)
        else:
            self.deviation, self.baseline = pd.DataFrame(), pd.DataFrame()
        columns = []
        if table is not None:
            table[LABEL] = [
                category if summary else display_category(category)
                for category, summary in zip(table[Col.category], table[SUMMARY], strict=True)
            ]
            months = [c for c in table.columns if c not in (Col.category, SUMMARY, LABEL, *TOTALS)]
            columns = [
                Column(LABEL, "Kategorie", CATEGORY, 180, tooltip="Doppelklick auf eine Zelle zeigt die Buchungen"),
                *[Column(c, format_month(c), MONEY0, 82) for c in months],
                Column(TOTAL, "Summe", MONEY0, 90, tooltip=f"Summe {format_month_range(start, end)}"),
                Column(MONTHLY_AVERAGE, "Ø Monat", MONEY0, 100, tooltip="Summe geteilt durch die Zahl der Monate"),
                Column(SUMMARY, SUMMARY, hidden=True),
            ]
        self.table_model.set_frame(table, columns)

    # ------------------------------------------------------------------ cell decoration
    def _summary(self, row: int) -> str:
        """Kind of summary row, ``""`` for a category."""
        frame = self.table_model.frame
        return "" if frame.empty else str(frame[SUMMARY].iat[row])

    def _deviation(self, row: int, key: str) -> float | None:
        if self._summary(row):
            return None
        category = self.table_model.frame[Col.category].iat[row]
        if category not in self.deviation.index or key not in self.deviation.columns:
            return None
        value = self.deviation.at[category, key]
        return None if np.isnan(value) else float(value)

    def _background(self, row: int, key: str):
        if self._summary(row) or key in TOTALS:
            return TOTAL_BACKGROUND
        deviation = self._deviation(row, key)
        if deviation is None:
            return None
        return MORE_EXPENSE if deviation < 0 else LESS_EXPENSE

    def _tooltip(self, row: int, key: str) -> str | None:
        summary = self._summary(row)
        if key == LABEL:
            return SUMMARY_TIPS.get(summary)
        deviation = self._deviation(row, key)
        if deviation is None:
            return None
        category = self.table_model.frame[Col.category].iat[row]
        baseline = self.baseline.at[category, key]
        return (
            f"{display_category(category)}, {format_month(key)}: {format_money(deviation, 0)} € Abweichung vom"
            f" Median der 12 Monate davor ({format_money(baseline, 0)} €)"
        )

    # ------------------------------------------------------------------ detail
    def open_detail(self, index) -> None:
        """Transactions behind a cell; for a summary row those of all its categories."""
        key = self.table_model.columns[index.column()].key
        if key in (LABEL, SUMMARY, *TOTALS):
            return
        row = self.table.row_at(index.row())
        summary = row[SUMMARY]
        if not summary:
            self.navigator.open_detail(key, [row[Col.category]], self.filter_edit.text())
            return
        groups = summary_groups(summary)
        categories = None if groups is None else [c for g in groups for c in self.model.categories_in_group(g)]
        title = "alle Kategorien" if summary == NET else SUMMARY_LABELS[summary]
        self.navigator.open_detail(key, categories, self.filter_edit.text(), title)


def count_text(count: int) -> str:
    return f"{count} {'Buchung' if count == 1 else 'Buchungen'}"


class DetailWindow(Window):
    """Transactions of some categories in some months or in all months; a double click categorizes one."""

    topics = frozenset({TRANSACTIONS, RULES, SETTINGS})

    def __init__(self, model, bridge, navigator: MainWindow):
        super().__init__(model, bridge, navigator)
        self.navigator = navigator
        self.resize(1400, 800)
        self.opened = False
        self.month: str | None = None
        #: first month, last month and months with data of a budget detail; None: transactions as paid
        self.budget: tuple[pd.Period, pd.Period, int] | None = None
        self.categories: list[str] | None = None
        self.category_filter = ""
        self.label = make_label("", self, "heading", wrap=True)
        self.summary_label = make_label("", self)
        self.help_button = HelpButton(DETAIL_HELP, "Buchungen", self)
        self.table_model = DataFrameModel(DETAIL_COLUMNS, self)
        self.table = DataFrameView(self.table_model, self)
        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 14, 16, 12)
        header = QHBoxLayout()
        header.addWidget(self.summary_label, 1)
        header.addWidget(self.help_button)
        layout.addWidget(self.label)
        layout.addLayout(header)
        layout.addWidget(self.table)
        self.setCentralWidget(central)
        self.table.doubleClicked.connect(self.open_rule)

    def open_detail(
        self,
        month: str | None,
        categories: Sequence[str] | None,
        category_filter: str = "",
        title: str = "",
    ) -> None:
        """Show the transactions of ``categories`` (``None``: all) as paid in ``month`` (``None``: all months)."""
        self.month, self.budget = month, None
        when = "alle Monate" if month is None else format_month(month)
        self._open(categories, title, when, DETAIL_HELP, category_filter)

    def open_budget_detail(
        self, start: pd.Period, end: pd.Period, categories: Sequence[str] | None, title: str = "", months: int = 0
    ) -> None:
        """Show what counts in the budget of ``start`` to ``end``: also spread payments made before, and only the
        share of payments spread beyond. ``months`` with data give the average per month (default: all)."""
        self.budget = (start, end, months or (end - start).n + 1)
        self._open(categories, title, f"{format_month_range(start, end)}, periodengerecht", BUDGET_DETAIL_HELP)

    def _open(self, categories, title: str, when: str, help_text: str, category_filter: str = "") -> None:
        self.opened = True
        self.categories = None if categories is None else list(categories)
        self.category_filter = category_filter
        what = title or (
            "alle Kategorien" if categories is None else ", ".join(display_category(c) for c in categories)
        )
        self.setWindowTitle(f"{what}: {when}")
        self.label.setText(f"{what} · {when}")
        self.help_button.text_ = help_text
        self.help_button.setToolTip(help_text)
        self.refresh()
        self.show()
        self.raise_()

    def refresh(self) -> None:
        super().refresh()
        if not self.opened:
            return
        if self.budget is None:
            frame = self.model.detail(self.month, self.categories, category_filter=self.category_filter)
            self.table_model.set_frame(frame, DETAIL_COLUMNS)
            total = format_money(frame[Col.value].sum())
            self.summary_label.setText(f"{count_text(len(frame))} · Summe {total} €")
            return
        start, end, months = self.budget
        frame = self.model.budget_contributions(start, end, self.categories)
        frame[SPREAD] = [spread_text(row) for _, row in frame.iterrows()]
        self.table_model.set_frame(frame, BUDGET_DETAIL_COLUMNS)
        total = float(frame[IN_PERIOD].sum())
        self.summary_label.setText(
            f"{count_text(len(frame))} · im Zeitraum {format_money(total)} € · Ø {format_money(total / months)} € pro"
            " Monat"
        )

    def open_rule(self, index) -> None:
        self.navigator.open_rule(transaction_id=self.table.row_at(index.row())[Col.transaction_id])
