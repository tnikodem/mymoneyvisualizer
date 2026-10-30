from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLineEdit, QMessageBox, QSpinBox

from mymoneyvisualizer.domain.categorization import regex_for
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.domain.models import ManualCategory
from mymoneyvisualizer.ui.common import GREEN, GREY, RED
from mymoneyvisualizer.ui.rule_window import Mode
from mymoneyvisualizer.ui.rules_window import OVERVIEW_COLUMNS

from ..helpers import rule_of, transactions


def _transaction(model, recipient):
    df = model.transactions()
    return df.loc[df[Col.recipient] == recipient].iloc[0]


def _background(window, column=1):
    return window.table_model.data(window.table_model.index(0, column), Qt.ItemDataRole.BackgroundRole)


def _column(key):
    return next(i for i, column in enumerate(OVERVIEW_COLUMNS) if column.key == key)


def test_regex_for():
    assert regex_for("REWE Markt (Nr. 1)") == r"REWE Markt \(Nr\. 1\)"


def test_create_new_rule(main, model, qtbot):
    window = main.rule_window
    main.open_rule()
    assert window.windowTitle() == "New rule"
    assert not window.manual_radio.isEnabled()  # no transaction, no manual category
    qtbot.keyClicks(window.recipient_edit, "Kiosk")
    qtbot.keyClicks(window.category_edit, "hobby.news")
    assert list(window.table_model.frame[Col.category]) == ["hobby.news"]
    assert len(model.rules) == 6  # only a preview

    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    assert not window.isVisible()
    assert (model.rules[-1].category, model.rules[-1].regex_recipient) == ("hobby.news", "Kiosk")
    assert _transaction(model, "Kiosk")[Col.category] == "hobby.news"


def test_double_click_type_the_category_enter(main, model, qtbot):
    """Fewest steps: the cursor is in the category, Enter saves, Escape cancels."""
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")[Col.transaction_id]
    main.open_rule(transaction_id=kiosk)
    assert window.focusWidget() is window.category_edit
    qtbot.keyClicks(window.category_edit, "hobby.news")
    qtbot.keyClick(window.category_edit, Qt.Key.Key_Escape)
    assert not window.isVisible()
    assert model.transaction(kiosk)[Col.category] == ""

    main.open_rule(transaction_id=kiosk)
    qtbot.keyClicks(window.category_edit, "hobby.news")
    qtbot.keyClick(window.category_edit, Qt.Key.Key_Return)
    assert not window.isVisible()
    assert model.transaction(kiosk)[Col.category] == "hobby.news"


def test_enter_takes_a_proposal_of_the_completer_first(main, model, qtbot):
    window = main.rule_window
    main.open_rule(transaction_id=_transaction(model, "Kiosk")[Col.transaction_id])
    window.activateWindow()  # the completer needs the focus
    qtbot.waitUntil(window.isActiveWindow)
    qtbot.keyClicks(window.category_edit, "fue")
    popup = window.category_edit.completer().popup()
    qtbot.waitUntil(popup.isVisible)
    popup.setCurrentIndex(popup.model().index(0, 0))
    qtbot.keyClick(popup, Qt.Key.Key_Return)
    assert window.isVisible()
    assert window.category_edit.text() == "car.fuel"
    qtbot.keyClick(window.category_edit, Qt.Key.Key_Return)
    assert not window.isVisible()
    assert _transaction(model, "Kiosk")[Col.category] == "car.fuel"


def test_enter_on_cancel_saves_nothing(main, model, qtbot):
    window = main.rule_window
    main.open_rule()
    window.category_edit.setText("x")
    qtbot.keyClick(window.cancel_button, Qt.Key.Key_Return)
    assert not window.isVisible()
    assert len(model.rules) == 6


def test_cancel_does_not_change_the_rule(main, model, qtbot):
    """Regression: every key press changed the live rule, so Cancel kept the edits."""
    window = main.rule_window
    groceries = rule_of(model, "household.food")
    main.open_rule(rule_id=groceries.id)
    assert window.windowTitle() == "Rule"
    window.category_edit.setText("changed")
    window.recipient_edit.setText("EDEKA")
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    assert model.rule(groceries.id).category == "household.food"
    assert model.rule(groceries.id).regex_recipient == "REWE"
    assert _transaction(model, "REWE")[Col.category] == "household.food"


def test_edit_existing_rule(main, model):
    window = main.rule_window
    fuel = rule_of(model, "car.fuel")
    main.open_rule(rule_id=fuel.id)
    assert window.original_id == fuel.id
    window.spread_edit.set_spread(24, 30)
    assert window.spread_edit.unit_combo.currentText() == "years"
    assert window.accept()
    assert (model.rule(fuel.id).spread_months, model.rule(fuel.id).residual_percent) == (24, 30)
    assert [r.id for r in model.rules].index(fuel.id) == 3  # same position


def test_invalid_regex_blocks_ok(main, model, qtbot):
    window = main.rule_window
    main.open_rule()
    window.description_edit.setText("([")
    assert not window.ok_button.isEnabled()
    assert "Invalid regex" in window.message_label.text()
    assert RED.name() in window.description_edit.styleSheet()
    assert window.table_model.frame.empty
    qtbot.keyClick(window.description_edit, Qt.Key.Key_Return)
    assert window.isVisible()  # Enter does not save an invalid rule
    window.description_edit.setText("ok")
    assert window.ok_button.isEnabled()


def test_open_for_transaction_of_existing_rule(main, model):
    window = main.rule_window
    rewe = _transaction(model, "REWE")
    main.open_rule(transaction_id=rewe[Col.transaction_id])
    assert window.original_id == rule_of(model, "household.food").id
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
    assert window.original_id is None
    assert window.recipient_edit.text() == "Kiosk"
    assert window.description_edit.text() == ""
    assert window.manual_radio.isEnabled()
    assert window.rule_radio.isChecked()


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
    assert (row[Col.category], row[Col.rule]) == ("hobby.news", model.rules[-1].id)


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


def test_unknown_ids_open_new_rule(main):
    window = main.rule_window
    main.open_rule(rule_id="does not exist")
    assert window.original_id is None
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


def test_rule_overview_shows_what_the_rules_do(main, model, qtbot, dialogs):
    main.show_rules()
    window = main.rules_window
    frame = window.table_model.frame
    assert list(frame["position"]) == [1, 2, 3, 4, 5, 6]
    assert list(frame["recipient"]) == ["ACME", "", "REWE", "Shell", "ShareNow", ""]
    assert list(frame["description"]) == ["", "Miete", "", "", "", "^Sparen$"]
    frame = frame.set_index(Col.category)
    assert frame.loc["household.food", "count"] == 13
    assert frame.loc["income.salary", "sum"] == 36000.0

    window.table.sortByColumn(_column("count"), Qt.SortOrder.DescendingOrder)
    assert window.table.displayed_frame()[Col.category].iloc[0] == "household.food"

    groceries = rule_of(model, "household.food")
    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert main.rule_window.isVisible() and main.rule_window.original_id is None
    window.table.doubleClicked.emit(window.table.model().index(0, 0))
    assert main.rule_window.original_id == groceries.id

    window.table.selectRow(0)
    dialogs.answer = QMessageBox.StandardButton.No
    window.delete_selected()
    assert dialogs.shown[-1][2] == "Delete the selected rule?"
    assert model.rule(groceries.id) is not None
    dialogs.answer = QMessageBox.StandardButton.Yes
    window.delete_selected()
    assert model.rule(groceries.id) is None
    assert groceries.id not in set(window.table_model.frame["id"])
    window.table.clearSelection()
    count = len(dialogs.shown)
    window.delete_selected()
    assert len(dialogs.shown) == count


def test_filter_rules(main, qtbot):
    main.show_rules()
    window = main.rules_window
    qtbot.keyClicks(window.filter_edit, "household")
    assert list(window.table_model.frame["position"]) == [2, 3]
    qtbot.keyClicks(window.filter_edit, " rew")  # every word must be found
    assert list(window.table_model.frame["recipient"]) == ["REWE"]
    window.filter_edit.setText("SPAREN")
    assert list(window.table_model.frame[Col.category]) == ["spar"]
    window.filter_edit.clear()
    assert len(window.table_model.frame) == 6


def test_change_spread_and_category_in_the_table(main, model):
    main.show_rules()
    window = main.rules_window
    table = window.table_model
    fuel = rule_of(model, "car.fuel")
    row = list(table.frame["id"]).index(fuel.id)
    spread, residual = table.index(row, _column(Col.spread_months)), table.index(row, _column(Col.residual_percent))
    assert table.flags(spread) & Qt.ItemFlag.ItemIsEditable
    assert not table.flags(residual) & Qt.ItemFlag.ItemIsEditable  # not spread, no residual value
    assert not table.flags(table.index(row, _column("recipient"))) & Qt.ItemFlag.ItemIsEditable
    assert table.data(spread, Qt.ItemDataRole.EditRole) == 0

    window.table.setCurrentIndex(spread)
    assert table.setData(spread, 24)
    assert model.rule(fuel.id).spread_months == 24
    assert window.table.currentIndex().row() == row  # still on the rule after the refresh
    assert table.data(spread) == "2 years"
    assert table.flags(residual) & Qt.ItemFlag.ItemIsEditable
    assert table.setData(residual, 40)
    assert table.setData(table.index(row, _column(Col.category)), " car.petrol ")
    assert (model.rule(fuel.id).category, model.rule(fuel.id).residual_percent) == ("car.petrol", 40)
    assert _transaction(model, "Shell")[Col.spread_months] == 24
    assert not table.setData(table.index(row, _column("recipient")), "x")


def test_edit_in_the_table_with_the_keyboard(main, model, qtbot):
    """Select the cell and type: the editor opens; Enter saves, the overview follows once the editor is closed."""
    main.show_rules()
    window = main.rules_window
    window.activateWindow()  # editors need the focus
    qtbot.waitUntil(window.isActiveWindow)
    fuel = rule_of(model, "car.fuel")
    row = list(window.table_model.frame["id"]).index(fuel.id)
    spread = window.table_model.index(row, _column(Col.spread_months))
    window.table.setCurrentIndex(spread)
    qtbot.keyClicks(window.table, "1")
    editor = window.table.indexWidget(spread)
    assert isinstance(editor, QSpinBox)
    assert (editor.maximum(), editor.suffix()) == (600, " months")
    qtbot.keyClicks(editor, "2")
    qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.waitUntil(lambda: model.rule(fuel.id).spread_months == 12)  # Qt commits the editor later
    qtbot.waitUntil(lambda: window.table_model.frame.loc[row, Col.spread_months] == 12)
    assert window.table.state() != window.table.State.EditingState

    residual = window.table_model.index(row, _column(Col.residual_percent))
    window.table.setCurrentIndex(residual)
    qtbot.keyClick(window.table, Qt.Key.Key_F2)
    assert window.table.indexWidget(residual).suffix() == " %"
    qtbot.keyClick(window.table.indexWidget(residual), Qt.Key.Key_Escape)

    category = window.table_model.index(row, _column(Col.category))
    window.table.setCurrentIndex(category)
    qtbot.keyClick(window.table, Qt.Key.Key_F2)
    editor = window.table.indexWidget(category)
    assert isinstance(editor, QLineEdit)
    assert editor.text() == "car.fuel"
    assert "household.food" in editor.completer().model().stringList()
