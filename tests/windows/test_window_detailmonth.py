# -*- coding: utf-8 -*-

import datetime
import os
import pandas as pd

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from .utils import qt_table_to_dataframe


def test_overview(tmp_path, qtbot, config, window_main_account_full, test_input_df):
    window_main, account = window_main_account_full
    dm_table = window_main.detail_month_window.detailmonth_widget.table

    window_main.summary_window.date_from = datetime.datetime(2018, 5, 1)
    window_main.summary_window.date_upto = datetime.datetime(2019, 5, 1)

    config.taggers.add(tag="tag1")  #TODO two different tags
    config.taggers.save()
    window_main.accounts_window.close()

    qtbot.mouseClick(window_main.summary_button, Qt.MouseButton.LeftButton)

    class TestItem:
        def __init__(self, row, column):
            self._row = row
            self._column = column

        def row(self):
            return self._row

        def column(self):
            return self._column

    test_item = TestItem(0, 2)
    window_main.summary_window.summary_widget.table.open_window_detail(test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 0

    test_item = TestItem(0, 3)
    window_main.summary_window.summary_widget.table.open_window_detail(test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 10
    assert all(qt_df_dm["date"].astype(str).str.slice(0, 7) == '2018-07')

    test_item = TestItem(0, 7)
    window_main.summary_window.summary_widget.table.open_window_detail(test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 30
    assert all(qt_df_dm["date"].astype(str).str.slice(0, 7) == '2018-11')

    # window_main.show()
    # qtbot.wait_for_window_shown(window_main)
    # qtbot.stopForInteraction()
