from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.domain.categorization import regex_for
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import ManualCategory
from mymoneyvisualizer.ui.common import GREEN, GREY, RED
from mymoneyvisualizer.ui.rule_window import Mode, proposed_name

from ..helpers import transactions


def _transaction(model, recipient):
    df = model.transactions()
    return df.loc[df[Col.recipient] == recipient].iloc[0]


def _background(window, column=1):
    return window.table_model.data(window.table_model.index(0, column), Qt.ItemDataRole.BackgroundRole)


def test_regex_for():
    assert regex_for("REWE Markt (Nr. 1)") == r"REWE Markt \(Nr\. 1\)"


def test_create_new_rule(main, model, qtbot):
    window = main.rule_window
    main.open_rule()
    assert window.name_edit.text() == "new_rule"
    assert not window.manual_radio.isEnabled()  # no transaction, no manual category
    qtbot.keyClicks(window.recipient_edit, "Kiosk")
    qtbot.keyClicks(window.category_edit, "hobby.news")
    assert list(window.table_model.frame[Col.category]) == ["hobby.news"]
    assert model.rule("new_rule") is None  # only a preview

    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    assert not window.isVisible()
    assert model.rule("new_rule").category == "hobby.news"
    assert _transaction(model, "Kiosk")[Col.category] == "hobby.news"


def test_cancel_does_not_change_the_rule(main, model, qtbot):
    """Regression: every key press changed the live rule, so Cancel kept the edits."""
    window = main.rule_window
    main.open_rule(name="groceries")
    window.category_edit.setText("changed")
    window.recipient_edit.setText("EDEKA")
    window.name_edit.setText("renamed")
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    assert model.rule("groceries").category == "household.food"
    assert model.rule("groceries").regex_recipient == "REWE"
    assert model.rule("renamed") is None
    assert _transaction(model, "REWE")[Col.category] == "household.food"


def test_edit_and_rename_existing_rule(main, model):
    window = main.rule_window
    main.open_rule(name="fuel")
    assert window.original_name == "fuel"
    window.name_edit.setText("petrol")
    window.spread_edit.set_spread(24, 30)
    assert window.spread_edit.unit_combo.currentText() == "years"
    assert window.accept()
    assert model.rule("fuel") is None
    assert (model.rule("petrol").spread_months, model.rule("petrol").residual_percent) == (24, 30)
    assert [t.name for t in model.rules].index("petrol") == 3


def test_invalid_regex_blocks_ok(main, model):
    window = main.rule_window
    main.open_rule()
    window.description_edit.setText("([")
    assert not window.ok_button.isEnabled()
    assert "Invalid regex" in window.message_label.text()
    assert RED.name() in window.description_edit.styleSheet()
    assert window.table_model.frame.empty
    window.description_edit.setText("ok")
    assert window.ok_button.isEnabled()


def test_open_for_transaction_of_existing_rule(main, model):
    window = main.rule_window
    rewe = _transaction(model, "REWE")
    main.open_rule(transaction_id=rewe[Col.transaction_id])
    assert window.original_name == "groceries"
    assert window.table_model.frame[Col.transaction_id].iloc[0] == rewe[Col.transaction_id]
    assert _background(window) == GREEN
    assert GREEN.name() in window.recipient_edit.styleSheet()
    window.recipient_edit.setText("^EWE")  # searched, so "EWE" would match, "^EWE" not
    assert _background(window) == RED
    assert RED.name() in window.recipient_edit.styleSheet()
    window.recipient_edit.setText("EWE")
    assert _background(window) == GREEN  # regression: the old window used re.match and showed red


def test_open_for_uncategorized_transaction_proposes_rule_for_the_recipient(main, model):
    """The description often holds dates and references of one payment, so the rule matches the recipient."""
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")
    main.open_rule(transaction_id=kiosk[Col.transaction_id])
    assert window.original_name is None
    assert window.name_edit.text() == "Kiosk"
    assert window.recipient_edit.text() == "Kiosk"
    assert window.description_edit.text() == ""
    assert window.manual_radio.isEnabled()
    assert window.rule_radio.isChecked()


def test_proposed_name():
    assert proposed_name("  REWE   Markt GmbH ", "x") == "REWE Markt GmbH"
    assert proposed_name("", "Kontoführung 09/2026") == "Kontoführung 09/2026"
    assert len(proposed_name("x" * 100, "")) == 40


def test_manual_category(main, model, qtbot):
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")[Col.transaction_id]
    main.open_rule(transaction_id=kiosk)
    window.manual_radio.setChecked(True)
    assert window.mode == Mode.MANUAL
    assert window.definition.isHidden()
    assert window.sale_combo.isHidden()  # an outgoing payment is no sale
    window.category_edit.setText("gift")
    window.spread_edit.set_spread(3, 0)
    assert len(window.table_model.frame) == 1
    assert window.table_model.frame[Col.category].iloc[0] == "gift"
    assert window.spread_hint.text() == "-2,50 € → -0,83 € per month."
    assert _background(window) == GREY
    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    row = model.transaction(kiosk)
    assert (row[Col.category], row[Col.rule], row[Col.spread_months]) == ("gift", MANUAL_RULE, 3)

    # reopening shows the manual category; an empty category removes it
    main.open_rule(transaction_id=kiosk)
    assert window.mode == Mode.MANUAL
    assert window.category_edit.text() == "gift"
    window.category_edit.clear()
    window.accept()
    assert model.transaction(kiosk)[Col.rule] == ""
    window.rule_radio.setChecked(True)
    assert window.mode == Mode.RULE


def test_spread_hint(main, model):
    window = main.rule_window
    main.open_rule(transaction_id=_transaction(model, "Kiosk")[Col.transaction_id])
    assert window.spread_hint.text() == "Counted in the month of payment."
    window.spread_edit.set_spread(2, 40)
    assert window.spread_hint.text() == "-2,50 € → -0,75 € per month; residual value 1 € stays an asset."
    main.open_rule()
    window.spread_edit.set_spread(60, 0)
    assert window.spread_hint.text() == "Spread evenly over 5 years from the month of payment."


def test_a_rule_replaces_the_manual_category_of_its_transaction(main, model):
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")[Col.transaction_id]
    model.save_manual_category(ManualCategory(kiosk, "gift"))
    main.open_rule(transaction_id=kiosk)
    assert window.mode == Mode.MANUAL
    window.rule_radio.setChecked(True)
    window.category_edit.setText("hobby.news")
    assert window.accept()
    row = model.transaction(kiosk)
    assert (row[Col.category], row[Col.rule]) == ("hobby.news", "Kiosk")


def test_sale_of_a_spread_purchase(main, model):
    """A bike bought for 450 € and sold for 300 €: 150 € loss of value over the months it was owned."""
    window = main.rule_window
    bike = model.transactions().loc[lambda df: df[Col.value] == -450.0, Col.transaction_id].item()
    model.save_manual_category(ManualCategory(bike, "hobby.bike", spread_months=60, residual_percent=40))
    model.import_transactions("giro", transactions(("2024-06-01", "Max Mustermann", "Verkauf Fahrrad", 300.0)))
    sale = _transaction(model, "Max Mustermann")[Col.transaction_id]

    main.open_rule(transaction_id=sale)
    window.manual_radio.setChecked(True)
    assert not window.sale_combo.isHidden()
    assert window.sale_combo.count() == 2
    assert window.sale_combo.itemData(1) == bike
    window.sale_combo.setCurrentIndex(1)
    assert window.category_edit.text() == "hobby.bike"
    assert not window.spread_edit.isEnabled()
    assert window.spread_hint.text() == (
        "Price and sale proceeds: -150,00 € over the 6 months you owned it → -25,00 € per month."
    )
    assert window.accept()
    assert model.manual_categories[sale].sale_of == bike

    main.open_rule(transaction_id=sale)
    assert window.sale_combo.currentData() == bike


def test_unknown_names_and_ids_open_new_rule(main):
    window = main.rule_window
    main.open_rule(name="does not exist")
    assert window.original_name is None
    main.open_rule(transaction_id="does not exist")
    assert window.transaction_id is None


def test_save_error_is_shown(main, model, dialogs, monkeypatch):
    from mymoneyvisualizer.app import InvalidRuleError

    def fail(*args, **kwargs):
        raise InvalidRuleError({"regex_recipient": "broken"})

    monkeypatch.setattr(model, "save_rule", fail)
    main.open_rule()
    assert not main.rule_window.accept()
    assert dialogs.shown[-1][0] == "warning"


def test_rule_overview(main, model, qtbot, dialogs):
    main.show_rules()
    window = main.rules_window
    frame = window.table_model.frame.set_index("name")
    assert frame.loc["groceries", "count"] == 13
    assert frame.loc["salary", "sum"] == 36000.0

    window.table.sortByColumn(4, Qt.SortOrder.DescendingOrder)  # count
    assert window.table.displayed_frame()["name"].iloc[0] == "groceries"

    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert main.rule_window.isVisible() and main.rule_window.original_name is None
    window.table.doubleClicked.emit(window.table.model().index(0, 0))
    assert main.rule_window.original_name == "groceries"

    window.table.selectRow(0)
    dialogs.answer = QMessageBox.StandardButton.No
    window.delete_selected()
    assert model.rule("groceries") is not None
    dialogs.answer = QMessageBox.StandardButton.Yes
    window.delete_selected()
    assert model.rule("groceries") is None
    assert "groceries" not in set(window.table_model.frame["name"])
    window.table.clearSelection()
    count = len(dialogs.shown)
    window.delete_selected()
    assert len(dialogs.shown) == count
