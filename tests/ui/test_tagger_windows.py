from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, Col
from mymoneyvisualizer.ui.common import GREEN, GREY, RED
from mymoneyvisualizer.ui.tagger_window import Mode, regex_for


def _transaction(model, recipient):
    df = model.transactions()
    return df.loc[df[Col.recipient] == recipient].iloc[0]


def _background(window, column=1):
    return window.table_model.data(window.table_model.index(0, column), Qt.ItemDataRole.BackgroundRole)


def test_regex_for():
    assert regex_for("REWE Markt (Nr. 1)") == r"REWE Markt \(Nr\. 1\)"


def test_create_new_tagger(main, model, qtbot):
    window = main.tagger_window
    main.open_tagger()
    assert window.name_edit.text() == "new_tagger"
    assert not window.mode_button.isEnabled()  # no transaction, no one-time tag
    qtbot.keyClicks(window.recipient_edit, "Kiosk")
    qtbot.keyClicks(window.tag_edit, "hobby.news")
    assert list(window.table_model.frame[Col.tag]) == ["hobby.news"]
    assert model.tagger("new_tagger") is None  # only a preview

    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    assert not window.isVisible()
    assert model.tagger("new_tagger").tag == "hobby.news"
    assert _transaction(model, "Kiosk")[Col.tag] == "hobby.news"


def test_cancel_does_not_change_the_tagger(main, model, qtbot):
    """Regression: every key press changed the live tagger, so Cancel kept the edits."""
    window = main.tagger_window
    main.open_tagger(name="groceries")
    window.tag_edit.setText("changed")
    window.recipient_edit.setText("EDEKA")
    window.name_edit.setText("renamed")
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    assert model.tagger("groceries").tag == "household.food"
    assert model.tagger("groceries").regex_recipient == "REWE"
    assert model.tagger("renamed") is None
    assert _transaction(model, "REWE")[Col.tag] == "household.food"


def test_edit_and_rename_existing_tagger(main, model):
    window = main.tagger_window
    main.open_tagger(name="fuel")
    assert window.original_name == "fuel"
    window.name_edit.setText("petrol")
    window.recurring_edit.setText("2")
    assert window.accept()
    assert model.tagger("fuel") is None
    assert model.tagger("petrol").recurring == 2
    assert [t.name for t in model.taggers].index("petrol") == 3


def test_invalid_regex_blocks_ok(main, model):
    window = main.tagger_window
    main.open_tagger()
    window.description_edit.setText("([")
    assert not window.ok_button.isEnabled()
    assert "Invalid regex" in window.message_label.text()
    assert RED.name() in window.description_edit.styleSheet()
    assert window.table_model.frame.empty
    window.description_edit.setText("ok")
    assert window.ok_button.isEnabled()


def test_open_for_transaction_of_existing_tagger(main, model):
    window = main.tagger_window
    rewe = _transaction(model, "REWE")
    main.open_tagger(transaction_id=rewe[Col.transaction_id])
    assert window.original_name == "groceries"
    assert window.table_model.frame[Col.transaction_id].iloc[0] == rewe[Col.transaction_id]
    assert _background(window) == GREEN
    assert GREEN.name() in window.recipient_edit.styleSheet()
    window.recipient_edit.setText("^EWE")  # searched, so "EWE" would match, "^EWE" not
    assert _background(window) == RED
    assert RED.name() in window.recipient_edit.styleSheet()
    window.recipient_edit.setText("EWE")
    assert _background(window) == GREEN  # regression: the old window used re.match and showed red


def test_open_for_untagged_transaction_proposes_tagger(main, model):
    window = main.tagger_window
    kiosk = _transaction(model, "Kiosk")
    main.open_tagger(transaction_id=kiosk[Col.transaction_id])
    assert window.original_name is None
    assert window.recipient_edit.text() == "Kiosk"
    assert window.description_edit.text() == "Zeitung"
    assert window.mode_button.isEnabled()


def test_one_time_tag(main, model, qtbot):
    window = main.tagger_window
    kiosk = _transaction(model, "Kiosk")[Col.transaction_id]
    main.open_tagger(transaction_id=kiosk)
    qtbot.mouseClick(window.mode_button, Qt.MouseButton.LeftButton)
    assert window.mode == Mode.ONE_TIME
    assert window.definition.isHidden()
    window.tag_edit.setText("gift")
    window.recurring_edit.setText("3")
    assert len(window.table_model.frame) == 1
    assert window.table_model.frame[Col.tag].iloc[0] == "gift"
    assert _background(window) == GREY
    qtbot.mouseClick(window.ok_button, Qt.MouseButton.LeftButton)
    row = model.transaction(kiosk)
    assert (row[Col.tag], row[Col.tagger_name], row[Col.recurring]) == ("gift", ONE_TIME_TAGGER, 3.0)

    # reopening shows the one-time tag; an empty tag removes it
    main.open_tagger(transaction_id=kiosk)
    assert window.mode == Mode.ONE_TIME
    assert window.tag_edit.text() == "gift"
    window.tag_edit.clear()
    window.accept()
    assert model.transaction(kiosk)[Col.tagger_name] == ""
    window.toggle_mode()
    assert window.mode == Mode.TAGGER


def test_unknown_names_and_ids_open_new_tagger(main):
    window = main.tagger_window
    main.open_tagger(name="does not exist")
    assert window.original_name is None
    main.open_tagger(transaction_id="does not exist")
    assert window.transaction_id is None


def test_save_error_is_shown(main, model, dialogs, monkeypatch):
    from mymoneyvisualizer.app import InvalidTaggerError

    def fail(*args, **kwargs):
        raise InvalidTaggerError({"regex_recipient": "broken"})

    monkeypatch.setattr(model, "save_tagger", fail)
    main.open_tagger()
    assert not main.tagger_window.accept()
    assert dialogs.shown[-1][0] == "warning"


def test_tagger_overview(main, model, qtbot, dialogs):
    main.show_tagger_overview()
    window = main.tagger_overview_window
    frame = window.table_model.frame.set_index("name")
    assert frame.loc["groceries", "count"] == 13
    assert frame.loc["salary", "sum"] == 36000.0

    window.table.sortByColumn(3, Qt.SortOrder.DescendingOrder)
    assert window.table.displayed_frame()["name"].iloc[0] == "groceries"

    qtbot.mouseClick(window.add_button, Qt.MouseButton.LeftButton)
    assert main.tagger_window.isVisible() and main.tagger_window.original_name is None
    window.table.doubleClicked.emit(window.table.proxy.index(0, 0))
    assert main.tagger_window.original_name == "groceries"

    window.table.selectRow(0)
    dialogs.answer = QMessageBox.StandardButton.No
    window.delete_selected()
    assert model.tagger("groceries") is not None
    dialogs.answer = QMessageBox.StandardButton.Yes
    window.delete_selected()
    assert model.tagger("groceries") is None
    assert "groceries" not in set(window.table_model.frame["name"])
    window.table.clearSelection()
    count = len(dialogs.shown)
    window.delete_selected()
    assert len(dialogs.shown) == count
