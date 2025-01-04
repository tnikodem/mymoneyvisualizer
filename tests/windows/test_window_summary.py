# -*- coding: utf-8 -*-

import datetime

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from .utils import qt_table_to_dataframe


def test_overview(tmp_path, qtbot, config, window_main_account_full, test_input_df):
    window_main, account = window_main_account_full
    summary_table = window_main.summary_window.summary_widget.table
    window_main.summary_window.set_date_from("2018-05")
    window_main.summary_window.set_date_upto("2019-04")
    config.taggers.add(tag="tag1")  # TODO two different tags
    config.taggers.save()
    window_main.accounts_window.close()

    qtbot.mouseClick(window_main.summary_button, Qt.MouseButton.LeftButton)

    qt_df_summary = qt_table_to_dataframe(summary_table)

    for col in ["2018-05", "2018-06", "2018-07", "2018-08", "2018-09", "2018-10", "2018-11", "2018-12",
                "2019-01", "2019-02", "2019-03", "2019-04"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(str).str.slice(0, 7) == col, nn.value].sum()
        expected = expected * 2  # as total is included
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 2  # tag and total
    assert abs(qt_df_summary["total"].astype(float).sum() - test_input_df[nn.value].sum()*2) < 1.

    # select different daterange
    window_main.summary_window.set_date_from("2018-04")
    qt_df_summary = qt_table_to_dataframe(summary_table)
    for col in ["2018-04", "2018-05", "2018-06", "2018-07", "2018-08", "2018-09", "2018-10", "2018-11", "2018-12",
                "2019-01", "2019-02", "2019-03", "2019-04"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(str).str.slice(0, 7) == col, nn.value].sum()
        expected = expected * 2  # as total is included
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 2  # tag and total
    assert abs(qt_df_summary["total"].astype(float).sum() - test_input_df[nn.value].sum()*2) < 1.

    # select contradicting date ranges
    window_main.summary_window.set_date_upto("2018-08")
    window_main.summary_window.set_date_upto("2018-11")
    qt_df_summary = qt_table_to_dataframe(summary_table)
    for col in ["2018-11"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(str).str.slice(0, 7) == col, nn.value].sum()
        expected = expected * 2  # as total is included
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 2  # tag and total
    assert abs(qt_df_summary["total"].astype(float).sum() - test_input_df[nn.value].sum()*2) < 1.

    # import sys
    # if "-s" in sys.argv:
    #     with qtbot.waitExposed(window_main, timeout=5000):
    #         window_main.show()
    #     qtbot.stop()
