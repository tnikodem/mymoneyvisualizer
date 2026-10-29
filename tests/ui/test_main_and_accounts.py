from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.domain.columns import Col


def test_windows_are_created_on_first_use(main, qtbot):
    assert "summary_window" not in main.__dict__
    qtbot.mouseClick(main.summary_button, Qt.MouseButton.LeftButton)
    assert main.summary_window.isVisible()
    qtbot.mouseClick(main.graph_button, Qt.MouseButton.LeftButton)
    assert main.graph_window.isVisible()
    qtbot.mouseClick(main.accounts_button, Qt.MouseButton.LeftButton)
    assert main.accounts_window.isVisible()
    assert "tagger_window" not in main.__dict__


def test_hidden_windows_refresh_when_shown(main, model):
    window = main.accounts_window  # created, not shown
    model.add_account("later")
    assert window.tab("later") is None
    main.show_accounts()
    assert window.tab("later") is not None


def test_accounts_tabs_show_transactions(main, model):
    main.show_accounts()
    window = main.accounts_window
    assert [t.account for t in window.account_tabs] == ["giro", "spar"]
    shown = window.tab("giro").table.displayed_frame()
    assert len(shown) == len(model.account_transactions("giro"))
    assert list(shown[Col.date]) == sorted(shown[Col.date], reverse=True)  # newest first
    assert shown[Col.tag].iloc[-1] == "income.salary"


def test_new_rename_and_delete_account(main, model, qtbot, dialogs):
    main.show_accounts()
    window = main.accounts_window
    qtbot.mouseClick(window.new_button, Qt.MouseButton.LeftButton)
    assert model.account_names[-1] == "new account 1"
    tab = window.tabs.currentWidget()
    assert tab.account == "new account 1"

    tab.name_edit.clear()
    qtbot.keyClicks(tab.name_edit, "Bargeld")
    qtbot.keyClick(tab.name_edit, Qt.Key.Key_Return)
    assert "Bargeld" in model.account_names
    assert window.tabs.tabText(window.tabs.currentIndex()) == "Bargeld"
    assert (model.repository.data_dir / "accounts" / "Bargeld.csv").is_file()

    dialogs.answer = QMessageBox.StandardButton.No
    qtbot.mouseClick(window.delete_button, Qt.MouseButton.LeftButton)
    assert "Bargeld" in model.account_names
    dialogs.answer = QMessageBox.StandardButton.Yes
    qtbot.mouseClick(window.delete_button, Qt.MouseButton.LeftButton)
    assert model.account_names == ["giro", "spar"]


def test_rename_to_existing_name_is_made_unique(main, model, qtbot):
    main.show_accounts()
    tab = main.accounts_window.tab("spar")
    tab.name_edit.setText("giro")
    tab.rename()
    assert model.account_names == ["giro", "giro_1"]
    assert main.accounts_window.tab("giro_1").name_edit.text() == "giro_1"


def test_import_button_and_double_click(main, monkeypatch, tmp_path):
    main.show_accounts()
    tab = main.accounts_window.tab("giro")
    opened = []
    monkeypatch.setattr(main, "open_import", lambda path, account: opened.append((path, account)))
    tab.import_data(path=str(tmp_path / "x.csv"))
    tab.import_data(path="")
    assert opened == [(str(tmp_path / "x.csv"), "giro")]

    tab.table.doubleClicked.emit(tab.table.proxy.index(0, 2))
    assert main.tagger_window.isVisible()
    assert main.tagger_window.transaction_id == tab.table.row_at(0)[Col.transaction_id]


def test_save_and_load_project(main, model, tmp_path, dialogs):
    main.show_accounts()
    window = main.accounts_window
    backup = tmp_path / "backup.zip"
    window.save_project(path=str(backup))
    assert backup.is_file()

    model.delete_account("spar")
    window.load_project(path=str(backup))
    assert model.account_names == ["giro", "spar"]
    assert [t.account for t in window.account_tabs] == ["giro", "spar"]
    assert dialogs.shown[-1][0] == "information"


def test_load_project_errors_and_cancel(main, model, tmp_path, dialogs):
    main.show_accounts()
    window = main.accounts_window
    broken = tmp_path / "broken.zip"
    broken.write_text("no zip")
    window.load_project(path=str(broken))
    assert dialogs.shown[-1][0] == "warning"
    window.load_project(path="")
    dialogs.answer = QMessageBox.StandardButton.No
    window.load_project(path=str(broken))
    assert dialogs.shown[-1][0] == "question"
    window.save_project(path="")


def test_delete_without_accounts(qtbot, tmp_path, dialogs):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    window = MainWindow(AppModel.open(tmp_path / "empty"))
    qtbot.addWidget(window)
    window.show_accounts()
    window.accounts_window.delete_account()
    assert dialogs.shown == []
    window.close()
