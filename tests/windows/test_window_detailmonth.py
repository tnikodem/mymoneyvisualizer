import datetime

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from .utils import qt_table_to_dataframe


def test_overview(tmp_path, qtbot, config, window_main_account_full):
    window_main, _ = window_main_account_full
    dm_table = window_main.detail_month_window.detailmonth_widget.multi_account_table

    window_main.summary_window.date_from = datetime.datetime(2018, 5, 1)
    window_main.summary_window.date_upto = datetime.datetime(2019, 5, 1)

    config.taggers.add(tag="taga",  regex_recipient="rec a")
    config.taggers.add(tag="tagb",  regex_recipient="rec b")
    config.taggers.save()
    window_main.accounts_window.close()

    qtbot.mouseClick(window_main.summary_button, Qt.MouseButton.LeftButton)

    # test if transactio is doen correctly..
    df = config.accounts.get_by_index(0).df
    assert len(df) == df["transaction_id"].nunique()

    class TestItem:
        def __init__(self, row, column):
            self._row = row
            self._column = column

        def row(self):
            return self._row

        def column(self):
            return self._column

    test_item = TestItem(0, 2)
    window_main.summary_window.summary_widget.table.open_window_detail(
        test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 0

    test_item = TestItem(1, 3)
    window_main.summary_window.summary_widget.table.open_window_detail(
        test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 10
    assert all(qt_df_dm[nn.date].astype(str).str.slice(3, 10) == '07.2018')

    test_item = TestItem(0, 7)
    window_main.summary_window.summary_widget.table.open_window_detail(
        test_item)
    qt_df_dm = qt_table_to_dataframe(dm_table)
    assert len(qt_df_dm) == 10
    assert all(qt_df_dm["date"].astype(str).str.slice(3, 10) == '11.2018')

    # Test open Tagger window
    df_account = config.accounts.get_by_index(0).df
    row_dict = {
        nn.tagger_name: df_account[nn.tagger_name].values[1],
        nn.transaction_id: df_account[nn.transaction_id].values[1],
    }
    window_main.detail_month_window.open_tagger_window(row_dict)
    tagger_table = window_main.tagger_window.tagger_widget.multi_account_table
    df_tagger = qt_table_to_dataframe(tagger_table)
    assert df_tagger[nn.transaction_id].values[0] == df_account[nn.transaction_id].values[1]
    assert df_tagger[nn.tag].unique() == ["taga"]

    # import sys
    # if "-s" in sys.argv:
    #     with qtbot.waitExposed(window_main, timeout=5000):
    #         window_main.show()
    #     qtbot.stop()
