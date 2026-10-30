import codecs

import pytest

from mymoneyvisualizer.importing.sniff import (
    clean_columns,
    detect_dayfirst,
    detect_decimal,
    detect_encoding,
    detect_header_record,
    detect_separator,
    read_text,
    sniff_format,
    split_records,
)

from .conftest import DKB, ENGLISH, ING, SPARKASSE


def test_detect_encoding_prefers_utf8():
    """Regression: every UTF-8 file with umlauts was detected as latin-1 (more characters won)."""
    assert detect_encoding("Bäckerei Müller".encode()) == "utf-8"
    assert detect_encoding(b"plain ascii") == "utf-8"


def test_detect_encoding_bom_and_windows_codepages():
    assert detect_encoding(codecs.BOM_UTF8 + "Größe".encode()) == "utf-8-sig"
    assert detect_encoding("Größe 5 €".encode("cp1252")) == "cp1252"
    assert detect_encoding(b"\x81\x8d\x8f") == "latin-1"  # undefined in cp1252


def test_read_text_with_unknown_encoding_falls_back(tmp_path):
    path = tmp_path / "x.csv"
    path.write_bytes("Müller".encode())
    assert read_text(path, "no-such-codec") == ("Müller", "utf-8")
    assert read_text(path, "ascii")[0] == "M��ller"


def test_split_records_handles_quotes_and_line_numbers():
    records = split_records('a;b\n"x;y";"multi\nline"\nz;w\n', ";")
    assert [r.fields for r in records] == [["a", "b"], ["x;y", "multi\nline"], ["z", "w"]]
    assert [r.line for r in records] == [0, 1, 3]


@pytest.mark.parametrize(
    ("text", "separator"),
    [(DKB, ";"), (ING, ";"), (SPARKASSE, ";"), (ENGLISH, ","), ("a\tb\tc\n1\t2\t3\n", "\t"), ("single column\n", ";")],
)
def test_detect_separator(text, separator):
    assert detect_separator(text) == separator


def test_detect_header_ignores_preamble_and_footer():
    """Regression: a footer line such as ``Kontostand;100`` moved the detected header behind the data."""
    text = "Konto;DE123\n\ndate;recipient;description;value\n2024-02-01;A;x;-1\n2024-02-02;B;y;-2\nKontostand;100\n"
    records = split_records(text, ";")
    header = detect_header_record(records)
    assert records[header].line == 2
    assert records[header].fields[0] == "date"
    assert detect_header_record([]) == 0


def test_detect_header_skips_padded_preamble():
    records = split_records("Kontoauszug;;;\n;;;\nDatum;Name;Text;Betrag\n01.01.2024;a;b;-1\n02.01.2024;c;;-2\n", ";")
    assert records[detect_header_record(records)].line == 2
    only_padded = split_records("a;;;\nb;;;\n", ";")
    assert detect_header_record(only_padded) == 0


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["-3,50", "-2,20", "2500,00"], ","),  # regression: small German amounts were read as -350, -220, ...
        (["1.234,56", "-12,00"], ","),
        (["-4.20", "3,100.00"], "."),
        (["1.234.567"], ","),
        (["1,234,567"], "."),
        (["12.03.24", "01.02.2024", "DE12 3456", "Gebucht"], None),
        (["-3,50 €", "1,5%", "(12,00)"], ","),
        (["1,234", "5.678"], None),
        (["1,5", "2.5"], None),
    ],
)
def test_detect_decimal(values, expected):
    assert detect_decimal(values) == expected


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["31.01.2024", "01.02.2024"], True),
        (["01.02.24"], True),
        (["13/01/2024"], True),
        (["01/13/2024"], False),
        (["2024-01-31"], False),
        (["01/02/2024"], None),
        (["no dates", "1,5"], None),
    ],
)
def test_detect_dayfirst(values, expected):
    assert detect_dayfirst(values) is expected


def test_clean_columns():
    assert clean_columns(['﻿"Datum"', " 'Betrag' ", "", "Betrag", "Betrag"]) == [
        "Datum",
        "Betrag",
        "column 3",
        "Betrag (2)",
        "Betrag (3)",
    ]


def test_sniff_dkb(write):
    fmt = sniff_format(write(DKB))
    assert fmt.encoding == "utf-8-sig"
    assert fmt.separator == ";"
    assert fmt.skiprows == 4
    assert (fmt.decimal, fmt.thousands, fmt.dayfirst) == (",", ".", True)
    assert fmt.columns[0] == "Buchungsdatum"
    assert fmt.columns[-1] == "column 9"


def test_sniff_ing_cp1252(write):
    fmt = sniff_format(write(ING, encoding="cp1252"))
    assert fmt.encoding == "cp1252"
    assert fmt.skiprows == 7
    assert "Auftraggeber/Empfänger" in fmt.columns
    assert fmt.columns.count("Währung") == 1 and "Währung (2)" in fmt.columns


def test_sniff_english(write):
    fmt = sniff_format(write(ENGLISH))
    assert (fmt.separator, fmt.skiprows, fmt.decimal, fmt.thousands, fmt.dayfirst) == (",", 0, ".", ",", False)
    assert fmt.columns == ("Date", "Payee", "Memo", "Amount")


def test_sniff_defaults_for_undecidable_files(write):
    fmt = sniff_format(write("Datum;Text;Betrag\n01/02/2024;x;5\n"))
    assert (fmt.decimal, fmt.dayfirst) == (",", True)
    assert sniff_format(write("")).columns == ()
