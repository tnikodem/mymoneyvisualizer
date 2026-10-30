from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Rule


def test_windows_are_created_on_first_use(main, qtbot):
    assert "income_expenses_window" not in main.__dict__
    qtbot.mouseClick(main.income_expenses_button, Qt.MouseButton.LeftButton)
    assert main.income_expenses_window.isVisible()
    qtbot.mouseClick(main.budget_button, Qt.MouseButton.LeftButton)
    assert main.budget_window.isVisible()
    qtbot.mouseClick(main.accounts_button, Qt.MouseButton.LeftButton)
    assert main.accounts_window.isVisible()
    qtbot.mouseClick(main.rules_button, Qt.MouseButton.LeftButton)
    assert main.rules_window.isVisible()
    assert "rule_window" not in main.__dict__


def test_status_shows_what_is_left_to_do(main, model, qtbot):
    assert main.accounts_status.text().startswith("2 accounts with 75 transactions.")
    assert main.rules_status.text() == "6 rules; 2 transactions without category."
    qtbot.mouseClick(main.uncategorized_button, Qt.MouseButton.LeftButton)
    detail = main.detail_window
    assert detail.isVisible()
    assert detail.windowTitle() == "(uncategorized): all months"
    assert list(detail.table_model.frame[Col.recipient]) == ["Ich", "Kiosk"]

    model.save_rule(Rule("rest", category="misc", regex_recipient="Kiosk|Ich"))
    assert main.rules_status.text() == "7 rules; everything is categorized."
    assert not main.uncategorized_button.isEnabled()
    assert detail.table_model.frame.empty


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
    assert shown[Col.category].iloc[-1] == "income.salary"


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

    tab.table.doubleClicked.emit(tab.table.model().index(0, 2))
    assert main.rule_window.isVisible()
    assert main.rule_window.transaction_id == tab.table.row_at(0)[Col.transaction_id]


def test_save_and_load_backup(main, model, tmp_path, dialogs):
    main.show_accounts()
    window = main.accounts_window
    backup = tmp_path / "backup.zip"
    main.save_backup(path=str(backup))
    assert backup.is_file()

    model.delete_account("spar")
    main.load_backup(path=str(backup))
    assert model.account_names == ["giro", "spar"]
    assert [t.account for t in window.account_tabs] == ["giro", "spar"]
    assert dialogs.shown[-1][0] == "information"


def test_load_backup_errors_and_cancel(main, model, tmp_path, dialogs):
    broken = tmp_path / "broken.zip"
    broken.write_text("no zip")
    main.load_backup(path=str(broken))
    assert dialogs.shown[-1][0] == "warning"
    main.load_backup(path="")
    dialogs.answer = QMessageBox.StandardButton.No
    main.load_backup(path=str(broken))
    assert dialogs.shown[-1][0] == "question"
    main.save_backup(path="")


def test_delete_without_accounts(qtbot, tmp_path, dialogs):
    from mymoneyvisualizer.app import AppModel
    from mymoneyvisualizer.ui.main_window import MainWindow

    window = MainWindow(AppModel.open(tmp_path / "empty"))
    qtbot.addWidget(window)
    window.show_accounts()
    window.accounts_window.delete_account()
    assert dialogs.shown == []
    window.close()
