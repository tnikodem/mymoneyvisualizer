# -*- coding: utf-8 -*-

from PyQt6.QtCore import Qt


from .utils import CallbackCounter, qt_table_to_dataframe

# TODO adding tagger with existing name


def test_add_taggers(tmp_path, qtbot, config, window_main_account_full):
    window_main, account = window_main_account_full
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)

    tagger_table = window_main.tagger_window.tagger_widget.multi_account_table
    account_table = window_main.accounts_window.tab_widget.tab_widgets[0].table

    # add tagger
    window_main.tagger_window.open_or_create_tagger(
        tagger_name="", recipient="rec a", description="des 5")
    assert tagger_table.table_widget.rowCount() == 2

    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tag_textbox, "tag1")
    qtbot.keyClick(window_main.tagger_window, Qt.Key.Key_Return)
    # with 'update' only in current view
    assert len(account.df.query("tag == 'tag1'")) == 0
    qt_df_tagger = qt_table_to_dataframe(tagger_table)
    assert len(qt_df_tagger.query("tag == 'tag1'")) == 2
    assert counter.counter == 0

    qtbot.mouseClick(
        window_main.tagger_window.tagger_widget.button_ok, Qt.MouseButton.LeftButton)
    assert len(account.df.query("tag == 'tag1'")) == 2
    qt_df_accounts = qt_table_to_dataframe(account_table)
    assert len(qt_df_accounts.query("tag == 'tag1'")) == 2
    assert counter.counter == 1

    # window_main.show()
    # qtbot.wait_for_window_shown(window_main)
    # qtbot.stopForInteraction()
