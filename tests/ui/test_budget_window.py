"""The budget window with the fixture data: 2023 complete, January 2024 without income."""

import pandas as pd
import pyqtgraph as pg
import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtWidgets import QMenu

from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import LAST_12_MONTHS
from mymoneyvisualizer.ui.budget_window import AVERAGE, CHANGE, SHARE, TARGET, euro, percent, period_label

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


def _legend(window):
    """The names of the legend, which lists the lines and then the stacked areas from the top."""
    names = [layer.name for layer in reversed(window.chart.layers)]
    text = window.chart.legend.text()
    assert [text.index(name.replace("&", "&amp;")) for name in names] == sorted(
        text.index(name.replace("&", "&amp;")) for name in names
    )
    return names


def _stack_from_the_top(window):
    """The areas of the chart from the top of the stack down."""
    return [layer.name for layer in reversed(window.chart.layers) if layer.area]


def _items(widget):
    return [widget.item(i).data(Qt.ItemDataRole.UserRole) for i in range(widget.count())]


def _width(view_range):
    return view_range[1] - view_range[0]


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
    # no transactions in the 12 months before 2023
    assert [needs.text(c) for c in (AVERAGE, SHARE, TARGET, CHANGE)] == ["1.060 €", "35 %", "50 %", "–"]
    assert not needs.icon(0).isNull()  # the color of the group in the chart
    assert [needs.child(i).text(0) for i in range(needs.childCount())] == ["household", "car"]
    household = _child(window, "Grundbedarf", "household")
    assert (household.text(AVERAGE), household.text(TARGET)) == ("1.000 €", "")
    assert window.tree.itemWidget(household, TARGET) is None  # no selection in every row
    assert _child(window, "Freizeit & Lebensstil", "(ohne Kategorie)").text(AVERAGE) == "−17 €"
    savings = _top(window, "Sparen")
    assert [savings.text(c) for c in (AVERAGE, SHARE, TARGET)] == ["1.942 €", "65 %", "20 %"]
    assert _child(window, "Sparen", "Rest auf den Konten").text(AVERAGE) == "1.942 €"


def test_change_against_the_12_months_before(window, model):
    """Only for a period of 12 months. The last 12 months (Feb 2023 - Jan 2024) against the 12 before, of which only
    January 2023 has transactions."""
    assert not window.tree.isColumnHidden(CHANGE)  # 2023
    model.set_budget_period("2024")  # January only
    assert window.tree.isColumnHidden(CHANGE)
    model.import_transactions("giro", transactions(("2024-01-15", "Shell", "Reparatur", -3000.0)))
    model.set_budget_period(LAST_12_MONTHS)
    assert not window.tree.isColumnHidden(CHANGE)
    car = _child(window, "Grundbedarf", "car")
    assert car.text(CHANGE) == "+245 €"  # (11 * 60 € + 3,000 €) / 12 = 305 € against 60 €
    assert car.foreground(CHANGE).color().name() == "#c5221f"  # more spent: bad
    assert "12 Monate davor: 60 € pro Monat" in car.toolTip(CHANGE)
    income = _top(window, "Einkommen")
    assert income.text(CHANGE) == "−250 €"  # 11 salaries in 12 months against one in one month
    assert income.foreground(CHANGE).color().name() == "#000000"  # less than 10 %: not highlighted


def test_groups_and_targets_in_their_own_window(window, model, qtbot, monkeypatch):
    dialog = window.open_groups()
    assert dialog.isVisible()
    assert _items(dialog.lists["wants"]) == ["carsharing", ""]
    assert dialog.lists["wants"].item(1).text() == "(ohne Kategorie)"
    dialog.move(["carsharing"], "needs")
    assert {a.category: a.group for a in model.groups}["carsharing"] == "needs"
    assert _items(dialog.lists["needs"]) == ["household", "car", "carsharing"]
    assert _child(window, "Grundbedarf", "carsharing").text(AVERAGE) == "15 €"

    # drag and drop: an item that lands in another list is saved
    dialog.lists["savings"].addItem(dialog.lists["needs"].takeItem(0))
    qtbot.waitUntil(lambda: {a.category: a.group for a in model.groups}["household"] == "savings")

    # the context menu moves the selected categories
    dialog.lists["wants"].item(0).setSelected(True)
    monkeypatch.setattr(QMenu, "exec", lambda menu, *args: menu.actions()[0].menu().actions()[0].trigger())
    dialog._context_menu("wants", dialog.lists["wants"].visualItemRect(dialog.lists["wants"].item(0)).center())
    assert {a.category: a.group for a in model.groups}[""] == "income"

    dialog.spins["needs"].setValue(40)
    assert model.settings.budget_shares["needs"] == 0.4
    assert dialog.savings_label.text() == "Ziel 30 % des Einkommens (der Rest)"
    assert _top(window, "Sparen").text(TARGET) == "30 %"
    assert window.figures["rate"].detail.text() == "Ziel 30 % · ✓ erreicht"
    assert window.open_groups() is dialog


def test_periods(window, model):
    combo = window.period_combo
    assert [combo.itemText(i) for i in range(combo.count())] == [
        "Letzte 12 Monate (Feb 2023 – Jan 2024)",
        "2024 (Jan)",
        "2023",
        "Eigener Zeitraum",
    ]
    assert combo.currentData() == "2023"
    assert window.start_combo.isHidden()
    combo.setCurrentIndex(0)
    assert model.settings.budget_period == LAST_12_MONTHS
    assert window.figures["income"].value.text() == "2.750 €"  # 11 salaries in 12 months


def test_custom_period(window, model):
    combo = window.period_combo
    combo.setCurrentIndex(combo.findData("custom"))  # starts with the months shown so far
    assert model.settings.budget_period == "2023-01:2023-12"
    assert not window.start_combo.isHidden()
    assert (window.start_combo.currentText(), window.end_combo.currentText()) == ("Jan 2023", "Dez 2023")
    window.end_combo.setCurrentIndex(window.end_combo.findData("2023-06"))
    assert model.settings.budget_period == "2023-01:2023-06"
    assert window.figures["income"].value.text() == "3.000 €"
    assert window.tree.isColumnHidden(CHANGE)  # no comparison for 6 months
    window.start_combo.setCurrentIndex(window.start_combo.findData("2023-09"))  # after the end: moves it
    assert model.settings.budget_period == "2023-09:2023-09"
    assert combo.currentText() == "Eigener Zeitraum"


def test_chart_shows_the_development_of_the_selection(window):
    chart = window.chart
    # the legend and the stack in the order of the breakdown: needs above wants
    assert _legend(window) == [
        "Nettoeinkommen",
        "Konsumgrenze für 20 % Sparquote",
        "Grundbedarf",
        "Freizeit & Lebensstil",
    ]
    assert _stack_from_the_top(window) == ["Grundbedarf", "Freizeit & Lebensstil"]
    assert chart.title.text() == "Gesamt: Einkommen und Konsum"
    # January 2024 has no income; the average of the last 12 months still holds 11 salaries
    assert _layer(window, "Nettoeinkommen").values[-1] == pytest.approx(11 * 3000 / 12)
    assert len(chart.months) == 2  # a full year is needed for the first average

    window.tree.setCurrentItem(_top(window, "Grundbedarf"))
    assert _legend(window) == ["Ziel 50 % des Einkommens", "household", "car"]
    assert _stack_from_the_top(window) == ["household", "car"]  # as in the tree
    window.tree.setCurrentItem(_child(window, "Grundbedarf", "household"))
    assert _layer(window, "household").values[-1] == pytest.approx((11 * 1000 + 450) / 12)
    window.tree.setCurrentItem(_top(window, "Sparen"))
    assert "Ersparnis gesamt" in [layer.name for layer in chart.layers]
    window.tree.setCurrentItem(_top(window, "Einkommen"))
    assert [layer.name for layer in chart.layers] == ["income"]

    chart.smooth_check.setChecked(False)
    assert chart.title.text().endswith(" › Einkommen")
    assert _layer(window, "income").values[-1] == 0.0
    assert len(chart.months) == 13


def test_hovering_the_chart_shows_the_area_under_the_mouse(window):
    """The overview at the last month: needs from 0 (wants are about 0) up to about 1,000 €, the limit of consumption
    at 2,200 € and the income at 2,750 €."""
    chart = window.chart

    def at(y):
        return chart.view.mapViewToScene(QPointF(chart.x[-1], y))

    chart._hover(at(500))
    assert chart.cursor.isVisible()
    assert chart.cursor.value() == chart.x[-1]
    assert chart._layer_at(at(500)).name == "Grundbedarf"
    assert chart._layer_at(at(500)).categories == ["household", "car"]
    assert chart._layer_at(at(11 * 3000 / 12)).name == "Nettoeinkommen"  # a line
    assert chart._layer_at(at(1600)) is None  # above the stack, away from the lines
    assert chart._layer_at(at(2200)).categories is None  # the limit: nothing to list

    window.tree.setCurrentItem(_top(window, "Grundbedarf"))  # household on top of car
    car = _layer(window, "car").values[-1]
    assert chart._layer_at(at(car / 2)).name == "car"
    assert chart._layer_at(at(car + 10)).name == "household"

    chart._hover(QPointF(-1000, -1000))
    assert not chart.cursor.isVisible()


def test_categories_are_dragged_into_another_order_or_group(window, model, qtbot):
    tree = window.tree
    needs = _top(window, "Grundbedarf")
    household = _child(window, "Grundbedarf", "household")
    assert household.flags() & Qt.ItemFlag.ItemIsDragEnabled and not household.flags() & Qt.ItemFlag.ItemIsDropEnabled
    assert needs.flags() & Qt.ItemFlag.ItemIsDropEnabled and not needs.flags() & Qt.ItemFlag.ItemIsDragEnabled
    assert not tree.invisibleRootItem().flags() & Qt.ItemFlag.ItemIsDropEnabled  # nothing beside the groups

    # what a drop does to the tree: household below car, carsharing into the needs
    needs.addChild(needs.takeChild(0))
    wants = _top(window, "Freizeit & Lebensstil")
    needs.insertChild(0, wants.takeChild(0))
    tree.reordered.emit()
    groups = model.groups
    assert [a.category for a in groups if a.group == "needs"] == ["carsharing", "car", "household"]
    needs = _top(window, "Grundbedarf")  # the tree is built again from the saved order
    assert [needs.child(i).text(0) for i in range(needs.childCount())] == ["carsharing", "car", "household"]

    tree.setCurrentItem(_top(window, "Grundbedarf"))  # the chart stacks in the same order
    # the legend and the stack follow: the first row on top
    assert _stack_from_the_top(window) == ["carsharing", "car", "household"]
    assert _legend(window)[1:] == ["carsharing", "car", "household"]


def test_a_selected_row_can_still_be_dragged(window, qtbot):
    tree = window.tree
    needs = _top(window, "Grundbedarf")
    tree.setCurrentItem(needs)
    start = tree.visualItemRect(needs).center()
    qtbot.mousePress(tree.viewport(), Qt.MouseButton.LeftButton, pos=start)
    qtbot.mouseRelease(tree.viewport(), Qt.MouseButton.LeftButton, pos=start + QPoint(0, 40))
    assert window.selected == ("group", "needs")  # a drag, not a click


def test_dragging_in_the_overview_keeps_the_overview(main, window, qtbot):
    """The chart follows a row when the mouse is released on it without a drag."""
    tree, viewport = window.tree, window.tree.viewport()
    household = tree.visualItemRect(_child(window, "Grundbedarf", "household")).center()
    qtbot.mousePress(viewport, Qt.MouseButton.LeftButton, pos=household)
    assert window.selected is None  # pressed: Qt marks the row, the chart waits
    qtbot.mouseRelease(viewport, Qt.MouseButton.LeftButton, pos=household + QPoint(0, 40))
    assert window.selected is None and tree.currentItem() is None  # dragged: nothing selected
    assert window.chart.title.text() == "Gesamt: Einkommen und Konsum"

    qtbot.mouseClick(viewport, Qt.MouseButton.LeftButton, pos=household)
    assert window.selected == ("category", "household")
    assert window.chart.title.text().endswith(" › household")
    qtbot.mouseDClick(viewport, Qt.MouseButton.LeftButton, pos=household)
    assert window.selected == ("category", "household")  # a double click does not clear it
    assert main.detail_window.isVisible()


def test_selection_can_be_cleared(window, qtbot):
    tree, chart = window.tree, window.chart
    needs = _top(window, "Grundbedarf")
    tree.setCurrentItem(needs)
    assert window.selected == ("group", "needs")
    qtbot.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(needs).center())
    assert window.selected is None  # a second click on the row: the whole again
    assert chart.title.text() == "Gesamt: Einkommen und Konsum"

    tree.setCurrentItem(_child(window, "Grundbedarf", "household"))
    title = chart.title.text()
    assert "Gesamt</a> › <a href='group:needs'" in title and title.endswith(" › household")
    chart.title.linkActivated.emit("group:needs")  # the breadcrumb
    assert window.selected == ("group", "needs")
    chart.title.linkActivated.emit("all")
    assert window.selected is None and tree.currentItem() is None

    tree.setCurrentItem(needs)
    qtbot.keyClick(tree, Qt.Key.Key_Escape)
    assert window.selected is None
    tree.setCurrentItem(needs)
    qtbot.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.viewport().rect().bottomLeft())
    assert window.selected is None  # a click into the empty area


def test_chart_zoom_is_kept_until_reset(window):
    chart = window.chart
    chart.smooth_check.setChecked(False)  # 13 months
    full = chart.view.viewRange()[0]
    chart.zoom_in.click()
    zoomed = chart.view.viewRange()[0]
    assert _width(zoomed) == pytest.approx(_width(full) / 2)
    window.tree.setCurrentItem(_top(window, "Grundbedarf"))
    assert chart.view.viewRange()[0] == pytest.approx(zoomed)  # drawn again, still zoomed
    chart.zoom_out.click()
    assert _width(chart.view.viewRange()[0]) == pytest.approx(_width(full))
    chart.zoom_in.click()
    chart.zoom_reset.click()
    assert chart.zoomed is None
    assert chart.view.viewRange()[0] == pytest.approx(full)


def test_chart_shows_the_period_and_its_average(window):
    chart = window.chart
    labels = [item.textItem.toPlainText() for item in chart.plot.getPlotItem().items if isinstance(item, pg.TextItem)]
    assert labels == ["Ø 1.058 €"]  # the consumption per month, as in the key figure
    lines = [
        item
        for item in chart.plot.getPlotItem().items
        if isinstance(item, pg.InfiniteLine) and getattr(item, "label", None)
    ]
    assert [line.label.toPlainText() for line in lines] == ["Jan 2023", "Dez 2023"]
    window.tree.setCurrentItem(_child(window, "Grundbedarf", "household"))
    labels = [item.textItem.toPlainText() for item in chart.plot.getPlotItem().items if isinstance(item, pg.TextItem)]
    assert labels == ["Ø 1.000 €"]
    assert "Ø im Zeitraum" in chart.legend.text()


def test_click_on_an_area_lists_its_transactions_of_the_month(main, window):
    chart = window.chart
    chart.smooth_check.setChecked(False)
    window.tree.setCurrentItem(_top(window, "Grundbedarf"))

    class Click:
        def __init__(self, x, y):
            self.x, self.y = x, y

        def button(self):
            return Qt.MouseButton.LeftButton

        def double(self):
            return False

        def scenePos(self):  # noqa: N802 (pyqtgraph API)
            return chart.view.mapViewToScene(QPointF(self.x, self.y))

    chart._clicked(Click(chart.x[-1], 100))  # household, on top of car, which has no payment in January
    detail = main.detail_window
    assert detail.label.text() == "household · Jan 2024, periodengerecht"
    assert list(detail.table_model.frame[Col.recipient]) == ["REWE"]
    assert detail.summary_label.text() == "1 Buchung · im Zeitraum -450,00 € · Ø -450,00 € pro Monat"
    chart._clicked(Click(chart.x[-2], 30))  # car in December
    assert detail.label.text() == "car · Dez 2023, periodengerecht"
    chart._clicked(Click(chart.x[-2], 5000))  # beside the areas: nothing
    assert detail.label.text() == "car · Dez 2023, periodengerecht"

    chart.smooth_check.setChecked(True)  # a point of the moving average: its 12 months
    window.open_layer(pd.Period("2024-01", "M"), _layer(window, "household"))
    assert detail.label.text() == "household · Feb 2023 – Jan 2024, periodengerecht"
    assert detail.summary_label.text().endswith("Ø -954,17 € pro Monat")
    window.select(None)
    window.open_layer(pd.Period("2024-01", "M"), _layer(window, "Grundbedarf"))
    assert detail.label.text() == "Grundbedarf · Feb 2023 – Jan 2024, periodengerecht"


def test_double_click_lists_what_counts_in_the_period(main, window, model):
    """Also payments made before the period: the rent spread over 12 months reaches into 2023 from 2022."""
    rent = next(r for r in model.rules if r.category == "household.rent")
    model.update_rule(rent.id, spread_months=12)
    window.open_detail(_child(window, "Grundbedarf", "household"))
    detail = main.detail_window
    assert detail.isVisible()
    assert detail.label.text() == "household · 2023, periodengerecht"
    assert "auch frühere" in detail.help_button.toolTip()
    frame = detail.table_model.frame
    december = frame.loc[frame[Col.date] == pd.Timestamp("2023-12-03")].iloc[0]
    assert (december["in_period"], december["spread"]) == (-75.0, "1 Jahr")
    assert december["amount_in_period"] == "-75,00 € (von insg. -900,00 €)"  # one month of twelve in 2023
    assert detail.table_model.headerData(4, Qt.Orientation.Horizontal) == "Betrag im Zeitraum"
    food = frame.loc[frame[Col.recipient] == "REWE"].iloc[0]
    assert (food["amount_in_period"], food["spread"]) == ("-100,00 €", "")  # paid and used in the period
    assert frame["in_period"].sum() == pytest.approx(-(900 * 78 / 12 + 1200))  # 1+2+...+12 rents of 75 €
    window.open_detail(_top(window, "Grundbedarf"))
    assert detail.label.text() == "Grundbedarf · 2023, periodengerecht"
    window.open_detail(_child(window, "Sparen", "Rest auf den Konten"))
    assert detail.label.text() == "Grundbedarf · 2023, periodengerecht"  # nothing to list


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
