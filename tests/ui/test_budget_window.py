"""The budget window with the fixture data: 2023 complete, January 2024 without income."""

import pandas as pd
import pytest
from PyQt6.QtCore import QPointF
from PyQt6.QtWidgets import QComboBox, QSpinBox

from mymoneyvisualizer.domain.models import LAST_12_MONTHS
from mymoneyvisualizer.ui.budget_window import euro, percent, period_label

from ..helpers import transactions


@pytest.fixture
def window(main):
    main.show_budget()
    return main.budget_window


def _top(window, title):
    tree = window.tree
    return next(tree.topLevelItem(i) for i in range(tree.topLevelItemCount()) if tree.topLevelItem(i).text(0) == title)


def _child(window, group_title, text):
    item = _top(window, group_title)
    return next(item.child(i) for i in range(item.childCount()) if item.child(i).text(0) == text)


def _layer(window, name):
    return next(layer for layer in window.chart.layers if layer.name == name)


def test_key_figures_answer_whether_too_much_or_too_little_is_spent(window):
    """2023: income 36,000 €, needs 12,720 €, wants -20 € (carsharing 180 € minus the uncategorized 200 € that came
    in on the savings account), so 65 % are saved instead of 20 %: (23,300 € - 7,200 €) / 12 more per month."""
    figures = window.figures
    assert (figures["income"].value.text(), figures["income"].detail.text()) == ("3.000 €", "pro Monat")
    assert figures["spending"].value.text() == "1.058 €"
    assert figures["spending"].detail.text() == "pro Monat · 35 % des Einkommens"
    assert figures["rate"].value.text() == "65 %"
    assert figures["rate"].detail.text() == "Ziel 20 % · ✓ erreicht"
    assert figures["rate"].property("tone") == "good"
    assert figures["room"].value.text() == "+1.342 €"
    assert window.period_note.text() == ""


def test_too_little_saved(window, model):
    """A car for 30,000 € without category (wants) eats up all savings: (36,000 - 12,720 - 29,980) € = -6,700 €."""
    model.import_transactions("giro", transactions(("2023-05-01", "Autohaus", "Auto", -30000.0)))
    assert window.figures["rate"].value.text() == "−19 %"
    assert window.figures["rate"].detail.text() == "Ziel 20 % · ✗ verfehlt"
    room = window.figures["room"]
    assert room.value.text() == "−1.158 €"  # (-6,700 € - 7,200 €) / 12
    assert room.detail.text() == "pro Monat unter dem Ziel"
    assert room.property("tone") == "bad"
    assert (
        _top(window, "Freizeit & Lebensstil").foreground(2).color().name() == "#c5221f"
    )  # 83 % instead of at most 30 %
    assert _top(window, "Sparen").foreground(2).color().name() == "#c5221f"


def test_breakdown_per_group_and_category(window):
    assert [window.tree.topLevelItem(i).text(0) for i in range(4)] == [
        "Einkommen",
        "Grundbedarf",
        "Freizeit & Lebensstil",
        "Sparen",
    ]
    needs = _top(window, "Grundbedarf")
    assert [needs.text(c) for c in range(1, 4)] == ["1.060 €", "35 %", "–"]  # no data a year before
    assert [needs.child(i).text(0) for i in range(needs.childCount())] == ["household", "car"]
    assert _child(window, "Grundbedarf", "household").text(1) == "1.000 €"
    assert _child(window, "Freizeit & Lebensstil", "(ohne Kategorie)").text(1) == "−17 €"
    savings = _top(window, "Sparen")
    assert [savings.text(c) for c in (1, 2, 4)] == ["1.942 €", "65 %", "Ziel 20 %"]
    assert _child(window, "Sparen", "Rest auf den Konten").text(1) == "1.942 €"
    spin = window.tree.itemWidget(needs, 4)
    assert isinstance(spin, QSpinBox) and spin.value() == 50


def test_change_against_the_year_before(window, model):
    """2024 against January 2023: the food bill went up from 100 € to 450 €, the salary is missing."""
    model.set_budget_period("2024")
    food = _child(window, "Grundbedarf", "household")
    assert food.text(3) == "−550 €"  # rent and food 1,000 € in January 2023, only food 450 € now
    assert food.foreground(3).color().name() == "#1e7d3a"  # less spent: good
    assert _top(window, "Einkommen").text(3) == "−3.000 €"
    assert _top(window, "Einkommen").foreground(3).color().name() == "#c5221f"
    assert "Ein Jahr davor: 1.000 € pro Monat" in food.toolTip(3)


def test_moving_a_category_to_another_group(window, model, qtbot):
    combo = window.tree.itemWidget(_child(window, "Freizeit & Lebensstil", "carsharing"), 4)
    assert isinstance(combo, QComboBox) and combo.currentData() == "wants"
    combo.setCurrentIndex(combo.findData("needs"))
    qtbot.waitUntil(lambda: {a.category: a.group for a in model.groups}["carsharing"] == "needs")
    assert _child(window, "Grundbedarf", "carsharing").text(1) == "15 €"


def test_targets(window, model):
    window.tree.itemWidget(_top(window, "Grundbedarf"), 4).setValue(40)
    assert model.settings.budget_shares["needs"] == 0.4
    assert _top(window, "Sparen").text(4) == "Ziel 30 %"
    assert window.figures["rate"].detail.text() == "Ziel 30 % · ✓ erreicht"


def test_periods(window, model):
    combo = window.period_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Letzte 12 Monate (Feb 2023 – Jan 2024)",
        "2024 (Jan)",
        "2023",
    ]
    assert combo.currentData() == "2023"
    combo.setCurrentIndex(0)
    assert model.settings.budget_period == LAST_12_MONTHS
    assert window.figures["income"].value.text() == "2.750 €"  # 11 salaries in 12 months


def test_chart_shows_the_development_of_the_selection(window):
    chart = window.chart
    assert [layer.name for layer in chart.layers] == [
        "Grundbedarf",
        "Freizeit & Lebensstil",
        "Konsumgrenze für 20 % Sparquote",
        "Nettoeinkommen",
    ]
    assert chart.title.text() == "Einkommen und Konsum"
    # January 2024 has no income; the average of the last 12 months still holds 11 salaries
    assert _layer(window, "Nettoeinkommen").values[-1] == pytest.approx(11 * 3000 / 12)
    assert len(chart.months) == 2  # a full year is needed for the first average

    window.tree.setCurrentItem(_top(window, "Grundbedarf"))
    assert [layer.name for layer in chart.layers] == ["household", "car", "Ziel 50 % des Einkommens"]
    window.tree.setCurrentItem(_child(window, "Grundbedarf", "household"))
    assert _layer(window, "household").values[-1] == pytest.approx((11 * 1000 + 450) / 12)
    window.tree.setCurrentItem(_top(window, "Sparen"))
    assert "Ersparnis gesamt" in [layer.name for layer in chart.layers]
    window.tree.setCurrentItem(_top(window, "Einkommen"))
    assert [layer.name for layer in chart.layers] == ["income"]

    chart.smooth_check.setChecked(False)
    assert chart.title.text() == "Einkommen"
    assert _layer(window, "income").values[-1] == 0.0
    assert len(chart.months) == 13


def test_hovering_the_chart_shows_the_values_of_a_month(window):
    chart = window.chart
    view = chart.plot.getPlotItem().vb
    chart._hover(view.mapViewToScene(QPointF(chart.x[-1], 100)))
    assert chart.cursor.isVisible()
    assert chart.cursor.value() == chart.x[-1]
    chart._hover(QPointF(-1000, -1000))
    assert not chart.cursor.isVisible()


def test_double_click_lists_the_transactions_as_paid(main, window):
    window.open_detail(_child(window, "Grundbedarf", "household"))
    detail = main.detail_window
    assert detail.isVisible()
    assert detail.label.text() == "household · 2023"
    assert "Im Budget sind verteilte Zahlungen anteilig" in detail.help_button.toolTip()
    assert detail.summary_label.text() == "24 Buchungen · Summe -12.000,00 €"
    window.open_detail(_top(window, "Grundbedarf"))
    assert detail.label.text() == "Grundbedarf · 2023"
    assert len(detail.table_model.frame) == 36
    window.open_detail(_child(window, "Sparen", "Rest auf den Konten"))
    assert detail.label.text() == "Grundbedarf · 2023"  # nothing to list


def test_banner_explains_why_the_numbers_differ_until_it_is_closed(window, model, dialogs):
    window.banner.more_button.click()
    kind, title, text = dialogs.shown[-1]
    assert (kind, title) == ("information", "Periodengerechte Sicht")
    assert "Kfz-Versicherung, 684 € im Januar" in text
    window.banner.close_button.click()
    assert window.banner.isHidden()
    assert model.settings.hidden_hints == ["budget"]
    window.refresh()
    assert window.banner.isHidden()  # read once is enough
    window.help_button.click()  # the explanation stays available
    assert "Kfz-Versicherung, 684 € im Januar" in dialogs.shown[-1][2]


def test_partial_and_empty_data(qtbot, tmp_path):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    model = AppModel.open(tmp_path / "data")
    main = MainWindow(model)
    qtbot.addWidget(main)
    main.show_budget()
    window = main.budget_window
    assert window.figures["rate"].value.text() == "–"
    assert window.tree.topLevelItemCount() == 0
    assert window.chart.legend.text() == "Zu wenige Monate für einen Verlauf."

    model.add_account("giro")
    model.import_transactions("giro", transactions(("2024-01-05", "a", "b", 100.0), ("2024-02-05", "c", "d", -10.0)))
    assert window.period_note.text() == "Nur 2 von 12 Monaten haben Buchungen."
    assert window.figures["rate"].value.text() == "–"  # without income
    assert window.figures["rate"].detail.text() == "Kein Einkommen im Zeitraum."


def test_formatting():
    assert (euro(1234.4), euro(-0.4), euro(-12.6), euro(12.6, signed=True), euro(0.2, signed=True)) == (
        "1.234 €",
        "0 €",
        "−13 €",
        "+13 €",
        "0 €",
    )
    assert (percent(0.254), percent(-0.19), percent(None)) == ("25 %", "−19 %", "–")
    month = pd.Period
    assert period_label(LAST_12_MONTHS, month("2025-10", "M"), month("2026-09", "M")) == (
        "Letzte 12 Monate (Okt 2025 – Sep 2026)"
    )
    assert period_label("2026", month("2026-01", "M"), month("2026-09", "M")) == "2026 (Jan – Sep)"
    assert period_label("2025", month("2025-01", "M"), month("2025-12", "M")) == "2025"
    assert period_label("2023", month("2023-11", "M"), month("2023-12", "M")) == "2023 (Nov – Dez)"
