"""Unit tests for the handling of unusual and broken exports."""

import codecs

import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.categorization import regex_for
from mymoneyvisualizer.importing.profile import ImportProfile, column_candidates, fold, guess_mapping
from mymoneyvisualizer.importing.reader import (
    parse_amounts,
    parse_dates,
    propose_mapping,
    propose_profile,
    read_table,
    to_transactions,
    transaction_values,
)
from mymoneyvisualizer.importing.sniff import MIXED_ENCODING, decode, detect_encoding, lines


# ------------------------------------------------------------------ encodings
def test_detect_utf16_with_and_without_bom():
    text = "Datum\tBetrag\n01.02.2024\t-1,00\n"
    assert detect_encoding(codecs.BOM_UTF16_LE + text.encode("utf-16-le")) == "utf-16"
    assert detect_encoding(text.encode("utf-16-le")) == "utf-16-le"
    assert detect_encoding(text.encode("utf-16-be")) == "utf-16-be"
    assert decode(codecs.BOM_UTF16_LE + text.encode("utf-16-le"), "utf-16") == text


def test_mixed_utf8_and_cp1252_lines_are_decoded_line_by_line():
    raw = "Bäcker;1\n".encode() + "Müller;2\r\n".encode("cp1252") + "Größe;3\n".encode()
    assert detect_encoding(raw) == MIXED_ENCODING
    assert decode(raw, MIXED_ENCODING) == "Bäcker;1\nMüller;2\r\nGröße;3\n"
    assert detect_encoding("Müller".encode("cp1252")) == "cp1252"  # no UTF-8 at all


def test_decode_removes_nul_and_bom_but_keeps_broken_characters():
    assert decode(b"\xef\xbb\xbfA\x00B", "utf-8") == "AB"
    assert decode("Beg�nstigter".encode(), "utf-8") == "Beg�nstigter"
    assert decode(b"M\x81ller", MIXED_ENCODING) == "M�ller"


def test_lines_only_break_at_cr_lf():
    assert lines("a b\x0cc\r\nd\re\nf") == ["a b\x0cc\r\n", "d\r", "e\n", "f"]


# ------------------------------------------------------------------ amounts and dates
@pytest.mark.parametrize(
    ("values", "decimal", "thousands", "expected"),
    [
        (["−4,20", "–1.000,00"], ",", ".", [-4.2, -1000.0]),
        (["23,45 S", "23,45 H", "1.234,56S", "7,00"], ",", ".", [-23.45, 23.45, -1234.56, 7.0]),
        (["28.10.2026", "1.2.24", "12.10.26"], ",", ".", [np.nan, np.nan, np.nan]),
        (["1.234.567,89", "-1.000", "1.0000"], ",", ".", [1234567.89, -1000.0, np.nan]),
        (["3,100.00", "31,00.00"], ".", ",", [3100.0, np.nan]),
        (["1 234,50 €"], ",", ".", [1234.5]),
    ],
)
def test_parse_amounts_edge_cases(values, decimal, thousands, expected):
    np.testing.assert_array_equal(parse_amounts(pd.Series(values), decimal, thousands).to_numpy(), expected)


def test_parse_dates_with_time_and_iso_timestamps():
    parsed = parse_dates(pd.Series(["2025-08-02T21:19:49.402Z", "2025-08-05T06:30:44.763272Z", "kaputt"]))
    assert list(parsed[:2]) == [pd.Timestamp("2025-08-02"), pd.Timestamp("2025-08-05")]
    assert pd.isna(parsed.iloc[2])
    assert list(parse_dates(pd.Series(["01.02.2024 10:15", "03.02.2024 23:59"]))) == [
        pd.Timestamp("2024-02-01"),
        pd.Timestamp("2024-02-03"),
    ]


# ------------------------------------------------------------------ values from several columns
def _table(**columns):
    return pd.DataFrame({k: list(v) for k, v in columns.items()}, dtype=str)


def test_value_with_fees_and_taxes():
    table = _table(amount=["-78.10", "0.00", "18.42", ""], fee=["-1.00", "-5.00", "", ""], tax=["", "", "-4.86", ""])
    profile = ImportProfile(col_value="amount", col_value_extra=["fee", "tax"], decimal=".", thousands=",")
    values = transaction_values(table, profile)
    np.testing.assert_allclose(values[:3], [-79.10, -5.00, 13.56])
    assert np.isnan(values.iloc[3])


def test_value_from_debit_and_credit_columns():
    table = _table(Soll=["-85,00", "", "12,00", ""], Haben=["", "3.245,67", "", ""])
    profile = ImportProfile(col_debit="Soll", col_credit="Haben")
    values = transaction_values(table, profile)
    np.testing.assert_array_equal(values[:3], [-85.0, 3245.67, -12.0])  # positive debit amounts are spent too
    assert np.isnan(values.iloc[3])


def test_value_with_debit_credit_mark():
    table = _table(Umsatz=["31,18", "3.245,67", "5,00", "2,00"], mark=["S", "H", "", "soll"])
    values = transaction_values(table, ImportProfile(col_value="Umsatz", col_sign="mark"))
    np.testing.assert_array_equal(values, [-31.18, 3245.67, 5.0, -2.0])


def test_balance_rows_are_skipped():
    table = _table(
        Datum=["01.02.2024", "02.02.2024", "03.02.2024"],
        Text=["a", "Endsaldo", "b"],
        Betrag=["-1,00", "100,00", "-2,00"],
    )
    profile = ImportProfile(col_date="Datum", col_description="Text", col_value="Betrag")
    df, invalid, _ = to_transactions(table, profile)
    assert list(df["description"]) == ["a", "b"]
    assert invalid == 1


# ------------------------------------------------------------------ reading rows
def test_overflow_cells_are_joined_into_the_description(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text(
        "Datum;Name;Verwendungszweck;Betrag\n01.02.2024;A;Miete; Oktober; Whg 3;-1,00\n02.02.2024;B;Einkauf;-2,00;;\n",
        encoding="utf-8",
    )
    table = read_table(path, ImportProfile())
    assert table.values.tolist() == [
        ["01.02.2024", "A", "Miete; Oktober; Whg 3", "-1,00"],
        ["02.02.2024", "B", "Einkauf", "-2,00"],
    ]


def test_overflow_without_description_column_is_cut(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Datum;Betrag\n01.02.2024;-1,00;x\n", encoding="utf-8")
    assert read_table(path, ImportProfile()).values.tolist() == [["01.02.2024", "-1,00"]]


# ------------------------------------------------------------------ proposing a mapping
def test_propose_mapping_uses_debit_and_credit_if_value_column_is_empty():
    table = _table(
        Buchungstag=["28.10.2026", "15.10.2026"],
        Wert=["28.10.2026", "15.10.2026"],
        **{
            "Begünstigter / Auftraggeber": ["REWE", "Musterfirma"],
            "Betrag": ["", ""],
            "Abweichender Empfänger": ["", ""],
            "Soll": ["-35,12", ""],
            "Haben": ["", "3.245,67"],
        },
    )
    mapping = propose_mapping(table)
    assert mapping == {
        "col_date": "Buchungstag",
        "col_recipient": "Begünstigter / Auftraggeber",
        "col_debit": "Soll",
        "col_credit": "Haben",
    }


def test_propose_mapping_adds_fees_unless_value_is_net():
    table = _table(date=["2026-10-01"], name=["x"], amount=["-1.00"], fee=["-0.50"], tax=[""])
    assert propose_mapping(table, ".", ",", dayfirst=False)["col_value_extra"] == ["fee"]
    paypal = _table(Datum=["01.10.2026"], Name=["x"], Brutto=["-1,00"], Gebühr=["-0,50"], Netto=["-1,50"])
    mapping = propose_mapping(paypal)
    assert mapping["col_value"] == "Netto"
    assert "col_value_extra" not in mapping


def test_propose_mapping_finds_debit_credit_mark_for_unsigned_amounts():
    table = _table(
        Buchungstag=["01.10.2026", "02.10.2026"], Umsatz=["31,18", "100,00"], Status=["ok", "ok"], x=["S", "H"]
    )
    assert propose_mapping(table)["col_sign"] == "x"
    signed = _table(Buchungstag=["01.10.2026"], Umsatz=["-31,18"], x=["S"])
    assert "col_sign" not in propose_mapping(signed)


def test_propose_mapping_prefers_filled_text_columns():
    table = _table(
        Datum=["01.10.2026", "02.10.2026"],
        Artikelbezeichnung=["", ""],
        Typ=["Zahlung", "Gutschrift"],
        Netto=["-1,00", "1,00"],
    )
    assert propose_mapping(table)["col_description"] == "Typ"


def test_propose_profile_returns_stored_profile(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("Datum;Text;Betrag\n01.02.2024;a;-1,00\n", encoding="utf-8")
    stored = ImportProfile(name="mine", col_date="Datum", col_value="Betrag")
    assert propose_profile(path, [stored]) == (stored, stored)
    profile, matched = propose_profile(path)
    assert matched is None
    assert (profile.col_date, profile.col_description, profile.col_value) == ("Datum", "Text", "Betrag")


def test_propose_profile_of_empty_file(tmp_path):
    path = tmp_path / "x.csv"
    path.write_text("", encoding="utf-8")
    profile, matched = propose_profile(path)
    assert matched is None
    assert profile.col_date == ""


# ------------------------------------------------------------------ profile and names
def test_profile_value_extra_roundtrip_and_validation():
    profile = ImportProfile(col_value="amount", col_value_extra=["fee", "tax"])
    data = profile.to_dict()
    data["col_value_extra"].append("changed")
    assert profile.col_value_extra == ["fee", "tax"]
    assert ImportProfile.from_dict(profile.to_dict()) == profile
    assert ImportProfile.from_dict({"col_value_extra": "fee"}).col_value_extra == []
    assert profile.missing_columns(["date", "amount", "fee"]) == ["col_date", "col_value_extra"]
    assert ImportProfile(col_date="d", col_credit="Haben").missing_columns(["d", "Haben"]) == []


def test_fold_and_candidates_handle_broken_and_account_columns():
    assert fold("ZahlungsempfÃ¤nger*in") == fold("Zahlungsempfänger*in")
    assert fold("Beg�nstigter") == fold("Begünstigter")
    columns = ["Auftraggeberkonto", "IBAN Auftraggeber", "Konto-Nr.", "Name Zahlungsbeteiligter"]
    assert column_candidates(columns, "col_recipient") == ["Name Zahlungsbeteiligter"]
    assert guess_mapping(["Booking Date", "Partner Name", "Account Name", "Amount (EUR)", "Payment Reference"]) == {
        "col_date": "Booking Date",
        "col_recipient": "Partner Name",
        "col_description": "Payment Reference",
        "col_value": "Amount (EUR)",
    }


# ------------------------------------------------------------------ rules from broken text
@pytest.mark.parametrize(
    ("text", "regex"),
    [
        ("REWE Markt", "REWE Markt"),
        ("Miete\r\nOktober", r"Miete\s+Oktober"),
        ("Gehalt Oktober", r"Gehalt\s+Oktober"),
        ("AUGUST 2021          BLUB", r"AUGUST 2021\s+BLUB"),
        ("Einkauf\tFiliale", r"Einkauf\s+Filiale"),
        ("  B�ckerei MÃ¼ller (1) ", "B�ckerei MÃ¼ller \\(1\\)"),
        ("", ""),
    ],
)
def test_regex_for_survives_whitespace_and_broken_characters(text, regex):
    assert regex_for(text) == regex
    assert pd.Series([text]).str.contains(regex_for(text), regex=True).iloc[0]
