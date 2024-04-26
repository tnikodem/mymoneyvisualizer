# -*- coding: utf-8 -*-

import sys
import time
import datetime
import os
import pandas as pd

from PyQt6.QtWidgets import QApplication
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

    # saldo correction
    saldo_textbox = window_main.accounts_window.tab_widget.tab_widgets[0].saldo_textbox
    saldo_textbox.clear()
    qtbot.keyClicks(saldo_textbox, "13.37")
    qtbot.keyClick(saldo_textbox, Qt.Key.Key_Return)

    assert abs(float(saldo_textbox.text()) - 13.37) < 0.0001

    # should saldo correction entry be visible?
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount(
    ) == 1


def test_money_transfer(tmp_path, qtbot, window_main_two_accounts_tagged):
    window_main = window_main_two_accounts_tagged
    table_credit = window_main.accounts_window.tab_widget.tab_widgets[0].table
    table_cash = window_main.accounts_window.tab_widget.tab_widgets[1].table

    qtbot.mouseClick(window_main.accounts_button, Qt.MouseButton.LeftButton)

    qt_df_credit = qt_table_to_dataframe(table_credit)
    assert len(qt_df_credit) == 1
    assert set(qt_df_credit[nn.tag].unique()) == {"cash"}
    assert abs(float(
        window_main.accounts_window.tab_widget.tab_widgets[0].saldo_textbox.text()) + 50.0) < 0.0001

    qt_df_cash = qt_table_to_dataframe(table_cash)
    assert len(qt_df_cash) == 2
    assert set(qt_df_cash[nn.tag].unique()) == {"cash", "grocery"}
    assert abs(float(
        window_main.accounts_window.tab_widget.tab_widgets[1].saldo_textbox.text()) - 40.0) < 0.0001


# TODO test save load project

    # window_main.show()
    # qtbot.wait_for_window_shown(window_main)
    # qtbot.stopForInteraction()
