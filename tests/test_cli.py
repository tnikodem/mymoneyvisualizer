import runpy

import pytest
from PyQt6.QtWidgets import QApplication, QMessageBox

from mymoneyvisualizer import __version__, cli
from mymoneyvisualizer.ui.main_window import MainWindow


def test_parse_args():
    args = cli.parse_args(["--data-dir", "x", "--debug"])
    assert (args.data_dir, args.debug) == ("x", True)
    assert cli.parse_args([]).data_dir is None


def test_version(capsys):
    with pytest.raises(SystemExit):
        cli.parse_args(["--version"])
    assert __version__ in capsys.readouterr().out


def test_main_starts_window(qtbot, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(QApplication, "exec", lambda self: 0)
    monkeypatch.setattr(MainWindow, "show", lambda self: shown.append(self))
    assert cli.main(["--data-dir", str(tmp_path / "data")]) == 0
    assert shown[0].model.repository.data_dir == tmp_path / "data"
    shown[0].close()


def test_main_reports_unreadable_data(qtbot, tmp_path, monkeypatch):
    (tmp_path / "rules.yaml").write_text("{not: [valid")
    messages = []
    monkeypatch.setattr(QMessageBox, "critical", lambda *args: messages.append(args[2]))
    assert cli.main(["--data-dir", str(tmp_path)]) == 1
    assert "rules.yaml" in messages[0]


def test_python_dash_m(monkeypatch):
    monkeypatch.setattr(cli, "main", lambda: 7)
    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("mymoneyvisualizer", run_name="__main__")
    assert exit_info.value.code == 7
