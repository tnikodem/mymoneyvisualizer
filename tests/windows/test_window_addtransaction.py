# -*- coding: utf-8 -*-

import time
import datetime
import os
import pandas as pd

from PyQt6.QtCore import Qt, QDate

from mymoneyvisualizer.windows.window_main import WindowMain

from .utils import CallbackCounter


def test_adddeltransactions(tmp_path, qtbot, window_main_account):
    window_main, account = window_main_account

    counter = CallbackCounter()
    window_main.config.accounts.add_update_callback(counter.count)

    # add transaction
    qtbot.mouseClick(window_main.accounts_window.tab_widget.tab_widgets[0].addtransbutton, Qt.MouseButton.LeftButton)
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.rec_textbox, "foo")
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.des_textbox, "bar")
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.value_textbox, "12.34")
    window_main.addtrans_window.addtrans_widget.calendar_widget.setSelectedDate(QDate(2018, 1, 1))
    qtbot.mouseClick(window_main.addtrans_window.addtrans_widget.add_button, Qt.MouseButton.LeftButton)
    assert len(account) == 1
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount() == 1
    assert counter.counter == 1
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.rec_textbox, "foo")
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.des_textbox, "bar2")
    qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.value_textbox, "12.34")
    qtbot.mouseClick(window_main.addtrans_window.addtrans_widget.add_button, Qt.MouseButton.LeftButton)
    assert len(account) == 2
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount() == 2
    assert counter.counter == 2
    qtbot.keyClick(window_main.addtrans_window, Qt.Key.Key_Escape)
    # window_main.addtrans_window.close()

    # FIXME return key test (test only) does not work
    # window_main.addtrans_window.addtrans_widget.value_textbox.setFocus()
    # qtbot.keyClicks(window_main.addtrans_window.addtrans_widget.des_textbox, "\n")

    # delete entry
    # FIXME table interaction does not work??!!
    window_main.accounts_window.delete_entry(account_index=0, date=datetime.datetime(2018, 1, 1),
                                             recipient="foo", description="bar", force=True)
    assert len(account) == 1
    assert window_main.accounts_window.tab_widget.tab_widgets[0].table.table_widget.rowCount() == 1
    assert counter.counter == 3
