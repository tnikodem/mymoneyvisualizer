"""GUI flow with exports of several banks: import window fields and categorization of broken text by double click."""

from pathlib import Path

import pytest

from mymoneyvisualizer.domain.columns import Col

DATA = Path(__file__).parents[1] / "data" / "test_csv"


@pytest.fixture
def window(main, model):
    model.add_account("konto")
    return main.import_window


def test_debit_and_credit_columns_are_proposed(window, model):
    window.open_file(DATA / "deutsche_bank.csv", "konto")
    assert window.column_combos["col_value"].currentText() == ""
    assert window.column_combos["col_debit"].currentText() == "Soll"
    assert window.column_combos["col_credit"].currentText() == "Haben"
    assert window.status_text() == "7 new transactions, 1 rows without valid date or value"
    window.import_transactions()
    assert model.account_transactions("konto")[Col.value].sum() == pytest.approx(4307.33)


def test_fee_and_tax_columns_can_be_switched_off(window, model):
    window.open_file(DATA / "transactions2.csv", "konto")
    assert window.extra_combo.currentData() == ["fee", "tax"]
    assert window.table_model.frame[Col.value].sum() == pytest.approx(1450.90)
    window.extra_combo.setCurrentIndexes([])
    assert window.status_text() == "10 new transactions, 1 with value 0"  # the card fee is lost without "fee"
    window.extra_combo.setCurrentIndexes([window.extra_combo.findText("fee")])
    assert window.table_model.frame[Col.value].sum() == pytest.approx(1450.90 + 4.86 + 12.34)
    assert window.profile().col_value_extra == ["fee"]


def test_debit_credit_mark_is_proposed_and_saved(window, model):
    window.open_file(DATA / "volksbank_alt_soll_haben.csv", "konto")
    assert window.column_combos["col_sign"].currentText() == "column 13"
    window.import_transactions()
    assert model.profiles[0].col_sign == "column 13"
    assert sorted(model.account_transactions("konto")[Col.value]) == [-870.0, -870.0, -31.18, -18.45, 3245.67, 3245.67]
    window.open_file(DATA / "volksbank_alt_soll_haben.csv", "konto")  # stored profile is found again
    assert window.original_name == model.profiles[0].name
    assert window.status_text() == "0 new transactions, 6 already imported, 2 rows without valid date or value"


@pytest.mark.parametrize(
    ("name", "recipient", "description"),
    [
        ("defekt_doppelt_kodiert.csv", "BÃ¤ckerei MÃ¼ller", "VISA Debitkartenumsatz"),
        ("transactions4.csv", "B�ckerei M�ller", "2021-08-14 Debitk.27"),
        ("volksbank_alt_soll_haben.csv", "Apotheke am Markt", "Kartenzahlung"),
    ],
)
def test_categorize_broken_text_by_double_click(main, window, model, name, recipient, description):
    window.open_file(DATA / name, "konto")
    window.import_transactions()

    main.show_accounts()
    tab = main.accounts_window.tab("konto")
    assert tab.table.displayed_frame().empty  # tabs are filled when they are shown
    main.accounts_window.tabs.setCurrentWidget(tab)
    shown = tab.table.displayed_frame()
    row = shown.index[(shown[Col.recipient] == recipient) & shown[Col.description].str.startswith(description)][0]
    tab.table.doubleClicked.emit(tab.table.model().index(int(row), 2))

    rule_window = main.rule_window
    assert rule_window.isVisible()
    assert rule_window.ok_button.isEnabled()
    rule_window.category_edit.setText("kaputt.test")
    assert rule_window.table_model.frame[Col.category].iloc[0] == "kaputt.test"
    rule_window.ok_button.click()

    categorized = model.account_transactions("konto")
    hits = categorized[categorized[Col.category] == "kaputt.test"]
    assert list(hits[Col.recipient]) == [recipient]

    month = hits[Col.date].iloc[0].strftime("%Y-%m")
    main.show_income_expenses()
    main.income_expenses_window.set_months(month, month)
    table = main.income_expenses_window.table_model.frame.set_index(Col.category)
    assert table.at["kaputt", month] == pytest.approx(hits[Col.value].sum())


def test_mixed_encoding_is_offered(window):
    window.open_file(DATA / "defekt_gemischte_kodierung.csv", "konto")
    assert window.encoding_combo.currentText() == "utf-8 + cp1252"
    assert "Stadtwerke Bühl GmbH" in set(window.table_model.frame[Col.recipient])
    window.encoding_combo.setCurrentText("utf-8")  # wrong choice: the cp1252 lines show broken characters
    assert "Stadtwerke B�hl GmbH" in set(window.table_model.frame[Col.recipient])
    assert window.status_text().startswith("8 new transactions")
