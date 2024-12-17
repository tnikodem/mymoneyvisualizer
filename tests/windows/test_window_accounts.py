# -*- coding: utf-8 -*-

import os

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.window_main import WindowMain

from .utils import qt_table_to_dataframe


def test_create_account(tmp_path, qtbot, config):
    default_db_filepath = config.dir_path + "/accounts/"

    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)

    # create new account
    default_account_name = "new account 1"
    qtbot.mouseClick(window_main.accounts_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window_main.accounts_window.new_acc_button,
                     Qt.MouseButton.LeftButton)
    account = config.accounts.get_by_name(default_account_name)
    assert account is not None

    # save account
    qtbot.mouseClick(
        window_main.accounts_window.tab_widget.tab_widgets[0].savebutton, Qt.MouseButton.LeftButton)
    expected_filepath = default_db_filepath + \
        default_account_name.replace(" ", "_") + ".csv"
    assert os.path.isfile(expected_filepath)

    # rename account
    test_account_name = 'test1'
    tab1_name = window_main.accounts_window.tab_widget.tab_widgets[0].name_textbox
    tab1_name.clear()
    qtbot.keyClicks(tab1_name, test_account_name)
    qtbot.mouseClick(
        window_main.accounts_window.tab_widget.tab_widgets[0].savebutton, Qt.MouseButton.LeftButton)
    account = config.accounts.get_by_name(test_account_name)
    assert account is not None
    expected_filepath2 = default_db_filepath+test_account_name + ".csv"
    assert os.path.isfile(expected_filepath2)
    assert not os.path.isfile(expected_filepath)
