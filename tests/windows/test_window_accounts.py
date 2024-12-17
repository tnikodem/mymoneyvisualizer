import os
from PyQt6.QtCore import Qt
from mymoneyvisualizer.windows.window_main import WindowMain


def test_create_account(tmp_path, qtbot, config):
    default_db_filepath = config.dir_path + "/accounts/"

    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)

    # create new account
    default_account_name = "new account 1"
    qtbot.mouseClick(window_main.accounts_button, Qt.MouseButton.LeftButton)

    qtbot.mouseClick(window_main.accounts_window.new_acc_button, Qt.MouseButton.LeftButton)
    account = config.accounts.get_by_name(default_account_name)
    assert account is not None

    # rename account
    test_account_name = 'test1'
    tab1_name = window_main.accounts_window.tab_widget.tab_widgets[0].name_textbox
    tab1_name.clear()
    qtbot.keyClicks(tab1_name, test_account_name)
    qtbot.keyClick(tab1_name, Qt.Key.Key_Return)
    account = config.accounts.get_by_name(test_account_name)
    assert account is not None
    expected_filepath2 = default_db_filepath+test_account_name + ".csv"
    assert os.path.isfile(expected_filepath2)

    # import sys
    # if "-s" in sys.argv:
    #     with qtbot.waitExposed(window_main, timeout=5000):
    #         window_main.show()
    #     qtbot.stop()
