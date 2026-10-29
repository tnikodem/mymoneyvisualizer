import dataclasses

import numpy as np
import pandas as pd
import pytest

from mymoneyvisualizer.domain.columns import RAW_COLUMNS, Col
from mymoneyvisualizer.importing.profile import ImportProfile, guess_mapping
from mymoneyvisualizer.importing.reader import (
    ImportFormatError,
    duplicate_keys,
    parse_amounts,
    parse_dates,
    preview_import,
    read_table,
    split_duplicates,
    to_transactions,
)
from mymoneyvisualizer.importing.sniff import sniff_format

from ..helpers import transactions
from .conftest import DKB, ENGLISH, ING, SPARKASSE


def _profile_for(path):
    fmt = sniff_format(path)
    profile = ImportProfile(**{k: v for k, v in dataclasses.asdict(fmt).items() if k != "columns"})
    return profile.with_mapping(**guess_mapping(fmt.columns))


def _load(path):
    profile = _profile_for(path)
    return to_transactions(read_table(path, profile), profile)


@pytest.mark.parametrize(
    ("values", "decimal", "thousands", "expected"),
    [
        (["-3,50", "2.500,00", "1.234.567,8"], ",", ".", [-3.5, 2500.0, 1234567.8]),
        (["-4.20", "3,100.00"], ".", ",", [-4.2, 3100.0]),
        (["-3,50 €", "EUR 12,00", "1 234,00", " 5,00"], ",", ".", [-3.5, 12.0, 1234.0, 5.0]),
        (["50,00-", "(12,00)", "+7,00", "-"], ",", ".", [-50.0, -12.0, 7.0, np.nan]),
        (["1'234.50"], ".", "", [1234.5]),
        (["abc", ""], ",", ".", [np.nan, np.nan]),
    ],
)
def test_parse_amounts(values, decimal, thousands, expected):
    np.testing.assert_array_equal(parse_amounts(pd.Series(values), decimal, thousands).to_numpy(), expected)


@pytest.mark.parametrize(
    ("values", "dayfirst", "expected"),
    [
        (["01.02.2024", "31.12.2023"], True, ["2024-02-01", "2023-12-31"]),
        (["01.02.24"], True, ["2024-02-01"]),
        (["2024-02-01", "2024-12-31"], True, ["2024-02-01", "2024-12-31"]),
        (["02/01/2024"], False, ["2024-02-01"]),
        (["02/01/2024"], True, ["2024-01-02"]),
        (["13/01/2024", "02/01/2024"], False, ["2024-01-13", "2024-01-02"]),
        (["06-07-2018"], True, ["2018-07-06"]),
        (["20240201"], True, ["2024-02-01"]),
        (["01.02.2024", "Kontostand"], True, ["2024-02-01", None]),
    ],
)
def test_parse_dates(values, dayfirst, expected):
    parsed = parse_dates(pd.Series(values), dayfirst)
    assert parsed.dtype == "datetime64[ns]"
    assert list(parsed) == [pd.NaT if e is None else pd.Timestamp(e) for e in expected]


def test_parse_dates_nothing_parseable():
    assert parse_dates(pd.Series(["x", "y"])).isna().all()


def test_read_table_pads_short_rows_and_skips_blank_lines(write):
    path = write("pre\nA;B;C\n1;2\n\n4;5;6;7\n")
    table = read_table(path, ImportProfile(skiprows=1))
    assert list(table.columns) == ["A", "B", "C"]
    assert table.values.tolist() == [["1", "2", ""], ["4", "5", "6"]]
    assert read_table(write("\n\n"), ImportProfile()).empty


def test_read_table_rejects_invalid_separator(write):
    with pytest.raises(ImportFormatError):
        read_table(write("a;b\n"), ImportProfile(separator=""))


def test_import_dkb(write):
    df, invalid, zero = _load(write(DKB))
    assert list(df.columns) == list(RAW_COLUMNS)
    assert (invalid, zero) == (0, 0)
    assert list(df[Col.value]) == [-3.5, 2500.0, -1050.0]
    assert list(df[Col.date]) == [pd.Timestamp("2024-01-31"), pd.Timestamp("2024-01-15"), pd.Timestamp("2024-01-13")]
    assert df[Col.recipient].iloc[0] == "Bäckerei Müller"
    assert df[Col.description].iloc[0] == "Brötchen; Kaffee"


def test_import_german_small_amounts_and_dates(write):
    """Regression: without a thousands separator in the file, ``-3,50`` was read as ``-350`` and
    ``01.02.2024`` as the 2nd of January because ``dayfirst`` was never detected."""
    path = write(
        "Buchungstag;Empfänger;Verwendungszweck;Betrag\n01.02.2024;Bäckerei;Brötchen;-3,50\n"
        "02.02.2024;ACME;Gehalt;2500,00\n",
        encoding="cp1252",
    )
    df, _, _ = _load(path)
    assert list(df[Col.value]) == [-3.5, 2500.0]
    assert list(df[Col.date]) == [pd.Timestamp("2024-02-01"), pd.Timestamp("2024-02-02")]
    assert df[Col.recipient].iloc[0] == "Bäckerei"


def test_import_ing_cp1252(write):
    df, _, _ = _load(write(ING, encoding="cp1252"))
    assert list(df[Col.value]) == [-23.45, -23.45, -2.2]
    assert df[Col.recipient].iloc[0] == "REWE Markt"


def test_import_sparkasse(write):
    df, _, _ = _load(write(SPARKASSE, encoding="cp1252"))
    assert list(df[Col.value]) == [-85.0, 120.5]
    assert list(df[Col.recipient]) == ["Stadtwerke", "Krankenkasse"]
    assert df[Col.date].iloc[0] == pd.Timestamp("2024-01-30")


def test_import_english_drops_zero_amounts(write):
    df, invalid, zero = _load(write(ENGLISH))
    assert list(df[Col.value]) == [-4.2, 3100.0]
    assert df[Col.description].iloc[0] == "Latte, large"
    assert (invalid, zero) == (0, 1)


def test_rows_with_invalid_date_or_amount_are_counted(write):
    path = write("Datum;Name;Text;Betrag\n01.02.2024;A;x;-1,00\nKontostand;;;100,00\n02.02.2024;B;y;kaputt\n")
    df, invalid, zero = _load(path)
    assert len(df) == 1
    assert (invalid, zero) == (2, 0)


def test_to_transactions_requires_complete_mapping(write):
    path = write("Datum;Name;Betrag\n01.02.2024;A;-1,00\n")
    profile = _profile_for(path)
    with pytest.raises(ImportFormatError, match="description"):
        to_transactions(read_table(path, profile), profile)
    profile = profile.with_mapping(col_description="Name", decimal=",", thousands=",")
    with pytest.raises(ImportFormatError, match="thousands"):
        to_transactions(read_table(path, profile), profile)


def test_identical_transactions_on_one_day_are_kept_unchanged():
    """Regression: the second of two identical transactions was renamed from ``Kaffee`` to ``Ka (3)``."""
    df = transactions(
        ("2024-02-01", "Kiosk", "Kaffee", -2.5),
        ("2024-02-01", "Kiosk", "Kaffee", -2.5),
        ("2024-02-02", "Kiosk", "Zeitung", -1.0),
    )
    preview = preview_import(_table(df), _PROFILE)
    assert list(preview.transactions[Col.description]) == ["Kaffee", "Kaffee", "Zeitung"]
    keys = duplicate_keys(preview.transactions)
    assert keys.is_unique
    assert keys.iloc[0].endswith("\x1f0") and keys.iloc[1].endswith("\x1f1")


_PROFILE = ImportProfile(
    col_date=Col.date,
    col_recipient=Col.recipient,
    col_description=Col.description,
    col_value=Col.value,
    decimal=".",
    thousands="",
)


def _table(df):
    return df.assign(**{Col.date: df[Col.date].dt.strftime("%Y-%m-%d"), Col.value: df[Col.value].astype(str)})


def test_reimport_is_idempotent():
    existing = transactions(("2024-02-01", "Kiosk", "Kaffee", -2.5), ("2024-02-01", "Kiosk", "Kaffee", -2.5))
    overlapping = transactions(
        ("2024-02-01", "Kiosk", "Kaffee", -2.5),
        ("2024-02-01", "Kiosk", "Kaffee", -2.5),
        ("2024-02-01", "Kiosk", "Kaffee", -2.5),
        ("2024-02-03", "Bäcker ", "Brot", -3.0),
    )
    preview = preview_import(_table(overlapping), _PROFILE, existing=existing)
    assert len(preview.duplicates) == 2
    assert list(preview.transactions[Col.description]) == ["Kaffee", "Brot"]
    combined = pd.concat([existing, preview.transactions])
    again = preview_import(_table(overlapping), _PROFILE, existing=combined)
    assert again.transactions.empty


def test_duplicates_ignore_whitespace_but_not_amount():
    existing = transactions(("2024-02-01", "REWE  Markt", "Einkauf ", -10.0))
    new = transactions(("2024-02-01", "REWE Markt", "Einkauf", -10.0), ("2024-02-01", "REWE Markt", "Einkauf", -11.0))
    unknown, known = split_duplicates(new, existing)
    assert list(unknown[Col.value]) == [-11.0]
    assert list(known[Col.value]) == [-10.0]
    assert split_duplicates(new, existing.iloc[0:0])[0] is new


def test_preview_since_and_drop_duplicates_switch():
    df = transactions(("2024-01-01", "a", "x", -1.0), ("2024-02-01", "b", "y", -2.0))
    preview = preview_import(_table(df), _PROFILE, existing=df, since=pd.Timestamp("2024-01-15"))
    assert preview.before_since == 1
    assert len(preview.duplicates) == 1
    assert preview.transactions.empty
    assert (preview.first_date, preview.last_date) == (pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01"))

    no_dedup = dataclasses.replace(_PROFILE, drop_duplicates=False)
    assert len(preview_import(_table(df), no_dedup, existing=df).transactions) == 2


def test_preview_of_empty_file():
    preview = preview_import(_table(transactions()), _PROFILE)
    assert preview.transactions.empty
    assert preview.first_date is None
