from mymoneyvisualizer.windows.window_main import WindowMain



def test_create_account(qtbot, config):
    window_main = WindowMain(config=config)
    qtbot.add_widget(window_main)
