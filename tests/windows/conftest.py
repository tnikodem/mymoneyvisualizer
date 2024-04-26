import pytest

import os
import sys
import datetime
import pandas as pd
import uuid


from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


from mymoneyvisualizer.naming import Naming as nn

from mymoneyvisualizer.windows.window_main import WindowMain


# run pytests in an environment without display (e.g. ci runner)
if not "DISPLAY" in os.environ and not "-s" in sys.argv:
    app = QApplication(sys.argv+['-platform', 'minimal'])


@pytest.fixture(scope="function")
def window_main_account(tmp_path, qtbot, config):
    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)
    # create new account
    qtbot.mouseClick(window_main.accounts_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window_main.accounts_window.new_acc_button,
                     Qt.MouseButton.LeftButton)
    account = config.accounts.get_by_name("new account 1")
    assert account is not None
    return window_main, account


@pytest.fixture(scope="function")
def window_main_account_full(tmp_path, qtbot, config, test_input_df):
    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)
    # create new account
    qtbot.mouseClick(window_main.accounts_button, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window_main.accounts_window.new_acc_button,
                     Qt.MouseButton.LeftButton)
    account = config.accounts.get_by_name("new account 1")
    assert account is not None
    # add test input df
    account.update(test_input_df)
    return window_main, account


@pytest.fixture(scope="function")
def window_main_two_accounts_tagged(tmp_path, qtbot, config):
    config.taggers.add(name="cash", regex_description="cash", tag="cash")
    config.taggers.add(
        name="grocery", regex_description="grocery", tag="grocery")

    acc_credit = config.accounts.add(name="credit")
    acc_credit.df = pd.DataFrame({nn.transaction_id: [uuid.uuid4()],
                                  nn.date: [datetime.datetime(2019, 1, 1)],
                                  nn.recipient: ["me"],
                                  nn.description: ["cash"],
                                  nn.value: [-50.0],
                                  nn.tag: ["cash"],
                                  nn.tagger_name: ["cash"]})

    acc_cash = config.accounts.add(name="cash")
    acc_cash.df = pd.DataFrame({nn.transaction_id: [uuid.uuid4()],
                                nn.date: [datetime.datetime(2019, 1, 10)],
                                nn.recipient: ["shop"],
                                nn.description: ["grocery"],
                                nn.value: [-10.0],
                                nn.tag: ["grocery"],
                                nn.tagger_name: ["grocery"]})

    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)

    return window_main
