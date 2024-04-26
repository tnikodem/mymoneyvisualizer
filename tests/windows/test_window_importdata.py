# -*- coding: utf-8 -*-

from PyQt6.QtCore import Qt, QDate
from mymoneyvisualizer.naming import Naming as nn

from .utils import CallbackCounter


def test_import_utf8(tmp_path, qtbot, config, window_main_account, test_input_utf8, test_input_df):
    window_main, account = window_main_account
    filepath, _ = test_input_utf8
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)

    window_main.importdata_window.open_new_data(
        filepath=filepath, account_name="new account 1")

    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_datecol, "date")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_reccol, "recipient")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_descol, "description")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_valuecol, "value")
    qtbot.keyClick(
        window_main.importdata_window.import_data_widget.textbox_dec, Qt.Key.Key_Return)

    qtbot.mouseClick(
        window_main.importdata_window.import_data_widget.import_button, Qt.MouseButton.LeftButton)

    assert len(account) == 40
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount(
    ) == 40
    assert abs(test_input_df[nn.value].sum() -
               account.df[nn.value].sum()) < 0.0001
    assert counter.counter == 1


def test_import_since(tmp_path, qtbot, config, window_main_account, test_input_utf8, test_input_df):
    window_main, account = window_main_account
    filepath, _ = test_input_utf8
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)

    window_main.importdata_window.open_new_data(
        filepath=filepath, account_name="new account 1")

    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_datecol, "date")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_reccol, "recipient")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_descol, "description")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_valuecol, "value")
    qtbot.keyClick(
        window_main.importdata_window.import_data_widget.textbox_dec, Qt.Key.Key_Return)

    assert window_main.importdata_window.import_data_widget.dateedit.date(
    ).toString() == 'Fri Jul 6 2018'
    window_main.importdata_window.import_data_widget.dateedit.setDate(
        QDate.fromString('18.08.2018', 'dd.MM.yyyy'))

    qtbot.mouseClick(
        window_main.importdata_window.import_data_widget.import_button, Qt.MouseButton.LeftButton)

    assert len(account) == 30
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount(
    ) == 30
    assert abs(test_input_df.query(
        f"{nn.date} > '2018-08-18'")[nn.value].sum() - account.df[nn.value].sum()) < 0.0001
    assert counter.counter == 1


def test_import_latin1(tmp_path, qtbot, config, window_main_account, test_input_latin1, test_input_df):
    window_main, account = window_main_account
    filepath, _ = test_input_latin1
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)

    window_main.importdata_window.open_new_data(
        filepath=filepath, account_name="new account 1")

    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_datecol, "date")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_reccol, "recipient")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_descol, "description")
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.combobox_valuecol, "value")

    # European style, dayfirst, decimal=,
    window_main.importdata_window.import_data_widget.checkbox_dayfirst.setChecked(
        True)
    window_main.importdata_window.import_data_widget.textbox_dec.clear()
    qtbot.keyClicks(
        window_main.importdata_window.import_data_widget.textbox_dec, ",")
    qtbot.keyClick(
        window_main.importdata_window.import_data_widget.textbox_dec, Qt.Key.Key_Return)

    qtbot.mouseClick(
        window_main.importdata_window.import_data_widget.import_button, Qt.MouseButton.LeftButton)

    assert len(account) == 40
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount(
    ) == 40
    assert abs(test_input_df[nn.value].sum() -
               account.df[nn.value].sum()) < 0.0001
    assert counter.counter == 1
