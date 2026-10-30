from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.domain.categorization import regex_for
from mymoneyvisualizer.domain.columns import MANUAL_RULE, Col
from mymoneyvisualizer.ui.common import GREEN, GREY, RED
from mymoneyvisualizer.ui.rule_window import Mode


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
    assert not window.mode_button.isEnabled()  # no transaction, no manual category
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
    window.recurring_edit.setText("2")
    assert window.accept()
    assert model.rule("fuel") is None
    assert model.rule("petrol").recurring == 2
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


def test_open_for_uncategorized_transaction_proposes_rule(main, model):
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")
    main.open_rule(transaction_id=kiosk[Col.transaction_id])
    assert window.original_name is None
    assert window.recipient_edit.text() == "Kiosk"
    assert window.description_edit.text() == "Zeitung"
    assert window.mode_button.isEnabled()


def test_manual_category(main, model, qtbot):
    window = main.rule_window
    kiosk = _transaction(model, "Kiosk")[Col.transaction_id]
    main.open_rule(transaction_id=kiosk)
    qtbot.mouseClick(window.mode_button, Qt.MouseButton.LeftButton)
    assert window.mode == Mode.MANUAL
    assert window.definition.isHidden()
    window.category_edit.setText("gift")
    window.recurring_edit.setText("3")
    assert len(window.table_model.frame) == 1
    assert window.table_model.frame[Col.category].iloc[0] == "gift"
    assert _background(window) == GREY
    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    row = model.transaction(kiosk)
    assert (row[Col.category], row[Col.rule], row[Col.recurring]) == ("gift", MANUAL_RULE, 3.0)

    # reopening shows the manual category; an empty category removes it
    main.open_rule(transaction_id=kiosk)
    assert window.mode == Mode.MANUAL
    assert window.category_edit.text() == "gift"
    window.category_edit.clear()
    window.accept()
    assert model.transaction(kiosk)[Col.rule] == ""
    window.toggle_mode()
    assert window.mode == Mode.RULE


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

    window.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
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
