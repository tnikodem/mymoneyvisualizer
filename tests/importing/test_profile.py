import pytest

from mymoneyvisualizer.importing.profile import ImportProfile, find_profile, guess_mapping


def test_roundtrip():
    profile = ImportProfile(name="dkb", encoding="cp1252", skiprows=4, col_date="Buchungsdatum", drop_duplicates=False)
    assert ImportProfile.from_dict(profile.to_dict()) == profile


def test_from_dict_coerces_types_and_ignores_unknown_keys():
    data = {
        "name": 1,
        "separator": ",",
        "thousands": "",
        "dayfirst": 0,
        "skiprows": "9",
        "col_description": None,
        "unknown": ["x"],
    }
    profile = ImportProfile.from_dict(data)
    assert (profile.name, profile.separator, profile.thousands) == ("1", ",", "")
    assert profile.skiprows == 9
    assert profile.dayfirst is False
    assert profile.col_description == ""
    assert profile.drop_duplicates is True


def test_missing_columns():
    profile = ImportProfile(col_date="Datum", col_recipient="Name", col_value="Betrag")
    assert profile.missing_columns(["Datum", "Name"]) == ["col_value"]
    assert profile.missing_columns(["Datum", "Betrag"]) == ["col_recipient"]  # mapped, but not in the file
    assert profile.with_mapping(col_description="Text").missing_columns(["Datum", "Name", "Text", "Betrag"]) == []
    assert ImportProfile().missing_columns(["x"]) == ["col_date", "col_value"]
    assert profile.mapping["col_date"] == "Datum"


def test_recipient_and_description_are_optional():
    profile = ImportProfile(col_date="Belegdatum", col_value="Betrag (€)")
    assert profile.missing_columns(["Belegdatum", "Betrag (€)"]) == []


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"separator": ""}, "separator"),
        ({"separator": ";;"}, "separator"),
        ({"decimal": ""}, "decimal"),
        ({"thousands": ","}, "thousands"),
        ({"thousands": "ab"}, "thousands"),
        ({"skiprows": -1}, "skiprows"),
    ],
)
def test_errors(changes, field):
    profile = ImportProfile(decimal=",", thousands=".")
    for key, value in changes.items():
        setattr(profile, key, value)
    assert field in profile.errors()


def test_no_errors_for_defaults():
    assert ImportProfile().errors() == {}
    assert ImportProfile(thousands="").errors() == {}


@pytest.mark.parametrize(
    ("columns", "expected"),
    [
        (
            [
                "Buchungsdatum",
                "Wertstellung",
                "Status",
                "Zahlungspflichtige*r",
                "Zahlungsempfänger*in",
                "Verwendungszweck",
                "Umsatztyp",
                "Betrag (€)",
            ],
            ("Buchungsdatum", "Zahlungsempfänger*in", "Verwendungszweck", "Betrag (€)"),
        ),
        (
            [
                "Buchung",
                "Valuta",
                "Auftraggeber/Empfänger",
                "Buchungstext",
                "Verwendungszweck",
                "Saldo",
                "Währung",
                "Betrag",
                "Währung (2)",
            ],
            ("Buchung", "Auftraggeber/Empfänger", "Verwendungszweck", "Betrag"),
        ),
        (
            [
                "Auftragskonto",
                "Buchungstag",
                "Valutadatum",
                "Buchungstext",
                "Verwendungszweck",
                "Lastschrift Ursprungsbetrag",
                "Beguenstigter/Zahlungspflichtiger",
                "Betrag",
                "Waehrung",
            ],
            ("Buchungstag", "Beguenstigter/Zahlungspflichtiger", "Verwendungszweck", "Betrag"),
        ),
        (["Date", "Payee", "Memo", "Amount"], ("Date", "Payee", "Memo", "Amount")),
    ],
)
def test_guess_mapping_for_common_banks(columns, expected):
    mapping = guess_mapping(columns)
    assert tuple(mapping[f] for f in ("col_date", "col_recipient", "col_description", "col_value")) == expected


def test_guess_mapping_partial_and_unique():
    assert guess_mapping(["foo", "Datum"]) == {"col_date": "Datum"}
    assert guess_mapping([]) == {}


def test_guess_mapping_prefers_booking_date_over_value_date():
    """Regression: the DKB credit card export got "Wertstellung" instead of "Belegdatum" (exact match won)."""
    columns = ["Belegdatum", "Wertstellung", "Status", "Beschreibung", "Umsatztyp", "Betrag (€)", "Fremdwährungsbetrag"]
    assert guess_mapping(columns) == {
        "col_date": "Belegdatum",
        "col_description": "Beschreibung",
        "col_value": "Betrag (€)",
    }
    assert guess_mapping(["Wertstellung", "Text", "Betrag"])["col_date"] == "Wertstellung"  # only as fallback
    assert guess_mapping(["Valuta", "Text", "Betrag"])["col_date"] == "Valuta"


def test_guess_mapping_broker_export():
    columns = [
        "datetime",
        "date",
        "type",
        "name",
        "amount",
        "fee",
        "tax",
        "original_amount",
        "description",
        "counterparty_name",
    ]
    mapping = guess_mapping(columns)
    assert (mapping["col_date"], mapping["col_recipient"], mapping["col_value"]) == ("date", "name", "amount")


def test_find_profile():
    a = ImportProfile(name="a", col_date="d", col_recipient="r", col_description="x", col_value="v")
    b = ImportProfile(name="b", col_date="Datum", col_recipient="Name", col_description="Text", col_value="Betrag")
    assert find_profile([a, b], ["Datum", "Name", "Text", "Betrag", "Saldo"]) is b
    assert find_profile([a, b], ["Datum"]) is None
    assert find_profile([], ["x"]) is None
