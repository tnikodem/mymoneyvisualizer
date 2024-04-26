# -*- coding: utf-8 -*-
import pandas as pd

from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn

# from mymoneyvisualizer.windows.window_tagger import WindowTagger
from mymoneyvisualizer.windows.window_taggeroverview import WindowTaggerOverview

from .utils import CallbackCounter, qt_table_to_dataframe


# TODO tagger overview does not get updated by change of tagger


def test_add_single_tagger(tmp_path, qtbot, config, window_main_account_full, test_input_df):
    window_main, account = window_main_account_full
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)
    tagger_table = window_main.tagger_window.tagger_widget.multi_account_table
    taggeroverview_table = window_main.tagger_overview_window.table
    account_table = window_main.accounts_window.tab_widget.tab_widgets[0].table

    qtbot.mouseClick(window_main.accounts_window.taggers_button,
                     Qt.MouseButton.LeftButton)
    qtbot.mouseClick(
        window_main.tagger_overview_window.button_add, Qt.MouseButton.LeftButton)
    assert len(qt_table_to_dataframe(tagger_table)) == len(test_input_df)

    window_main.tagger_window.tagger_widget.tagger_definition_widget.name_textbox.clear()
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tagger_definition_widget.name_textbox, "tagger1")
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tagger_definition_widget.recipient_regex_textbox, "rec b")
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tagger_definition_widget.description_regex_textbox, "des 7")
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tag_textbox, "tag1")

    qtbot.keyClick(window_main.tagger_window, Qt.Key.Key_Return)
    assert len(qt_table_to_dataframe(tagger_table)) == 1

    qtbot.mouseClick(
        window_main.tagger_window.tagger_widget.button_ok, Qt.MouseButton.LeftButton)
    qt_df_taggerviewview = qt_table_to_dataframe(taggeroverview_table)
    assert len(qt_df_taggerviewview) == 1
    sum1 = float(qt_df_taggerviewview["sum"].sum())
    sum2 = float(test_input_df.query(
        f"{nn.recipient} == 'rec b' and {nn.description} == 'des 7'")[nn.value].sum())
    assert abs(sum1 - sum2) < 0.0001
    assert counter.counter == 1

    window_main.tagger_overview_window.close()
    qt_df_account = qt_table_to_dataframe(account_table)
    assert len(qt_df_account.query("tag == 'tag1'")) == 1


def test_add_and_delete(tmp_path, qtbot, config, window_main_account_full, test_input_df):
    window_main, account = window_main_account_full
    counter = CallbackCounter()
    config.accounts.add_update_callback(counter.count)
    taggeroverview_table = window_main.tagger_overview_window.table

    qtbot.mouseClick(window_main.accounts_window.taggers_button,
                     Qt.MouseButton.LeftButton)

    # add 3
    for i in range(3):
        tag = "tag"+str(i)
        qtbot.mouseClick(
            window_main.tagger_overview_window.button_add, Qt.MouseButton.LeftButton)

        qtbot.keyClicks(
            window_main.tagger_window.tagger_widget.tagger_definition_widget.recipient_regex_textbox, "rec b")
        qtbot.keyClicks(
            window_main.tagger_window.tagger_widget.tagger_definition_widget.description_regex_textbox, "des "+str(i+1))
        qtbot.keyClicks(
            window_main.tagger_window.tagger_widget.tag_textbox, tag)
        qtbot.mouseClick(
            window_main.tagger_window.tagger_widget.button_ok, Qt.MouseButton.LeftButton)

        qt_df_taggeroverview = qt_table_to_dataframe(taggeroverview_table)
        assert len(qt_df_taggeroverview) == i+1
        assert len(qt_df_taggeroverview.query(f"tag == '{tag}'")) == 1
        assert counter.counter == i+1

    # delete 1 tagger
    config.taggers.delete(name="new_tagger_1")
    assert len(qt_table_to_dataframe(taggeroverview_table)) == 2
    assert counter.counter == 4

    # rename 1 tagger
    window_main.tagger_overview_window.open_tagger("new_tagger_2")
    window_main.tagger_window.tagger_widget.tagger_definition_widget.name_textbox.clear()
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tagger_definition_widget.name_textbox, "tagger42")
    window_main.tagger_window.tagger_widget.tag_textbox.clear()
    qtbot.keyClicks(
        window_main.tagger_window.tagger_widget.tag_textbox, "tag42")
    qtbot.mouseClick(
        window_main.tagger_window.tagger_widget.button_ok, Qt.MouseButton.LeftButton)
    qt_df_taggeroverview = qt_table_to_dataframe(taggeroverview_table)
    assert len(qt_df_taggeroverview) == 2
    assert len(qt_df_taggeroverview.query("tag == 'tag42'")) == 1
    assert counter.counter == 5


def test_sort_overview(tmp_path, qtbot, config_full):
    config = config_full
    tagger_overview_window = WindowTaggerOverview(
        parent=None, config=config, tagger_window=None)
    qtbot.add_widget(tagger_overview_window)

    tagger_overview_window.table.table_widget.sortByColumn(
        2, Qt.SortOrder.DescendingOrder)
    dfs = []
    for acc in config.accounts.get():
        dfs += [acc.df]
    df = pd.concat(dfs, sort=False).sort_values(
        nn.date, ascending=False).reset_index(drop=True)
    dfg = df.groupby(nn.tag).agg(
        {nn.date: "count", nn.value: "sum"}).sort_values(nn.date, ascending=False)
    qt_df_taggeroverview = qt_table_to_dataframe(tagger_overview_window.table)
    assert list(dfg[nn.date]) == list(
        qt_df_taggeroverview["count"].astype(int))
    for i, j in zip(list(dfg[nn.value]), list(qt_df_taggeroverview[nn.sum].astype(float))):
        assert abs(i-j) < 1e5

    # change tagger
    tagger1 = config.taggers.get_by_index(0)
    tagger1.name = "tagger1_new"
    tagger1.tag = "tag1_new"
    tagger1.save()
    qt_df_taggeroverview = qt_table_to_dataframe(tagger_overview_window.table)
    assert "tag1_new" in qt_df_taggeroverview[nn.tag].values
