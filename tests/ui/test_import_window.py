import pandas as pd
import pytest
from PyQt6.QtCore import QDate, Qt

from mymoneyvisualizer.domain.columns import Col

from ..importing.conftest import DKB

LATIN1 = (
    "Kontoauszug;;;\n;;;\n"
    "Datum fää;Empfänger föö;Text;Betrag\n"
    "06-07-2018;rec a;des 1;-13,37\n"
    "24-11-2018;rec b;des 2;-26,74\n"
    "24-11-2018;rec b;des 2;-26,74\n"
    "25-11-2018;rec a;des 3;0,00\n"
)


@pytest.fixture
def export(tmp_path):
    def write(text, encoding="utf-8", name="export.csv"):
        path = tmp_path / name
        path.write_bytes(text.encode(encoding))
        return path

    return write


@pytest.fixture
def window(main):
    return main.import_window


def test_detects_format_and_columns(window, export):
    window.open_file(export(DKB), "giro")
    assert window.isVisible()
    assert window.encoding_combo.currentText() == "utf-8-sig"
    assert (window.separator_edit.text(), window.decimal_edit.text(), window.header_spin.value()) == (";", ",", 4)
    assert window.column_combos["col_recipient"].currentText() == "Zahlungsempfänger*in"
    assert list(window.table_model.frame[Col.value]) == [-3.5, 2500.0, -1050.0]
    assert window.status_text() == "3 new transactions"
    assert window.since_edit.date() == QDate(2024, 1, 13)
    assert window.import_button.isEnabled()


def test_import_latin1_with_duplicates_and_zero(window, model, export):
    window.open_file(export(LATIN1, encoding="latin-1"), "spar")
    assert window.encoding_combo.currentText() == "cp1252"
    assert window.header_spin.value() == 2
    assert window.dayfirst_check.isChecked()
    assert window.column_combos["col_date"].currentText() == "Datum fää"
    assert window.status_text() == "3 new transactions, 1 with value 0"

    before = len(model.account_transactions("spar"))
    assert window.import_transactions() == 3
    assert not window.isVisible()
    spar = model.account_transactions("spar")
    assert len(spar) == before + 3
    assert spar[Col.recipient].str.contains("rec b").sum() == 2  # identical rows are both kept
    assert model.profiles[0].col_date == "Datum fää"
    assert model.profiles[0].name == "importer_1"


def test_reimport_uses_saved_profile_and_skips_known_rows(window, model, export):
    path = export(DKB)
    window.open_file(path, "giro")
    window.name_edit.setText("dkb")
    window.import_transactions()

    window.open_file(path, "giro")
    assert window.original_name == "dkb"
    assert window.name_edit.text() == "dkb"
    assert window.status_text() == "0 new transactions, 3 already imported"
    assert not window.import_button.isEnabled()
    assert window.import_transactions() == 0

    window.duplicates_check.setChecked(False)
    assert window.status_text() == "3 new transactions"
    window.import_transactions()
    assert [p.name for p in model.profiles] == ["dkb"]


def test_since_filter(window, model, export):
    window.open_file(export(DKB), "giro")
    window.since_edit.setDate(QDate(2024, 1, 14))
    assert window.status_text() == "2 new transactions, 1 before the start date"
    window.import_transactions()
    assert model.account_transactions("giro")[Col.date].min() == pd.Timestamp("2023-01-01")
    assert (model.account_transactions("giro")[Col.date] == pd.Timestamp("2024-01-13")).sum() == 0


def test_format_errors_are_shown(window, export, qtbot):
    window.open_file(export(DKB), "giro")
    window.separator_edit.clear()
    assert "separator" in window.error_label.text()
    assert not window.import_button.isEnabled()
    window.separator_edit.setText(";")
    assert window.error_label.text() == ""
    window.column_combos["col_value"].setCurrentText("")
    assert "value" in window.error_label.text()
    window.decimal_edit.setText(".")
    window.column_combos["col_value"].setCurrentText("Betrag (€)")
    window.thousands_edit.setText(".")
    assert "thousands" in window.error_label.text()


def test_changing_header_line_updates_columns(window, export):
    window.open_file(export(DKB), "giro")
    window.header_spin.setValue(0)
    assert window.column_combos["col_date"].currentText() == ""
    assert window.column_combos["col_date"].findText("Girokonto") >= 0
    window.header_spin.setValue(4)
    window.column_combos["col_date"].setCurrentText("Buchungsdatum")
    assert window.column_combos["col_date"].currentText() == "Buchungsdatum"


def test_cancel(window, model, export, qtbot):
    window.open_file(export(DKB), "giro")
    before = len(model.transactions())
    qtbot.mouseClick(window.cancel_button, Qt.MouseButton.LeftButton)
    assert len(model.transactions()) == before
    assert model.profiles == []
