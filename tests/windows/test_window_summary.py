# -*- coding: utf-8 -*-

import datetime

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from .utils import qt_table_to_dataframe


def test_overview(tmp_path, qtbot, config, window_main_account_full, test_input_df):
    window_main, account = window_main_account_full
    summary_table = window_main.summary_window.summary_widget.table

    window_main.summary_window.date_from = datetime.datetime(2018, 5, 1)
    window_main.summary_window.date_upto = datetime.datetime(2019, 5, 1)

    config.taggers.add(tag="tag1")  # TODO two different tags
    config.taggers.save()
    window_main.accounts_window.close()

    qtbot.mouseClick(window_main.summary_button, Qt.MouseButton.LeftButton)

    qt_df_summary = qt_table_to_dataframe(summary_table)

    for col in ["2018-05", "2018-06", "2018-07", "2018-08", "2018-09", "2018-10", "2018-11", "2018-12",
                "2019-01", "2019-02", "2019-03", "2019-04"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(str).str.slice(0, 7) == col, nn.value].sum()
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 1  # tag and no total
    assert abs(qt_df_summary["total"].astype(float).sum() - test_input_df[nn.value].sum()) < 1.

    # move month backward
    qtbot.mouseClick(
        window_main.summary_window.summary_widget.button_before, Qt.MouseButton.LeftButton)
    qt_df_summary = qt_table_to_dataframe(summary_table)
    for col in ["2018-04", "2018-05", "2018-06", "2018-07", "2018-08", "2018-09", "2018-10", "2018-11", "2018-12",
                "2019-01", "2019-02", "2019-03"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(
            str).str.slice(0, 7) == col, nn.value].sum()
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 1
    assert abs(qt_df_summary["total"].astype(
        float).sum() - test_input_df[nn.value].sum()) < 1.

    # move 2 month forward
    qtbot.mouseClick(
        window_main.summary_window.summary_widget.button_after, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(
        window_main.summary_window.summary_widget.button_after, Qt.MouseButton.LeftButton)
    qt_df_summary = qt_table_to_dataframe(summary_table)
    for col in ["2018-06", "2018-07", "2018-08", "2018-09", "2018-10", "2018-11", "2018-12",
                "2019-01", "2019-02", "2019-03", "2019-04", "2019-05"]:
        assert col in qt_df_summary.columns
        expected = test_input_df.loc[test_input_df[nn.date].astype(
            str).str.slice(0, 7) == col, nn.value].sum()
        assert abs(qt_df_summary[col].astype(float).sum() - expected) < 1.
    assert len(qt_df_summary) == 1
    assert abs(qt_df_summary["total"].astype(
        float).sum() - test_input_df[nn.value].sum()) < 1.

    # import sys
    # if "-s" in sys.argv:
    #     with qtbot.waitExposed(window_main, timeout=5000):
    #         window_main.show()
    #     qtbot.stop()
