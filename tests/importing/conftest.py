"""Synthetic exports in the layout of common German banks (all data made up)."""

import pytest

DKB = """﻿"Girokonto";"DE12 3456 7890 1234 5678 90"
""
"Kontostand vom 31.01.2024:";"1.234,56 €"
""
"Buchungsdatum";"Wertstellung";"Status";"Zahlungspflichtige*r";"Zahlungsempfänger*in";"Verwendungszweck";"Umsatztyp";"Betrag (€)";
"31.01.24";"31.01.24";"Gebucht";"Max Muster";"Bäckerei Müller";"Brötchen; Kaffee";"Ausgang";"-3,50";
"15.01.24";"15.01.24";"Gebucht";"ACME GmbH";"Max Muster";"Gehalt Januar";"Eingang";"2.500,00";
"13.01.24";"13.01.24";"Gebucht";"Max Muster";"Vermieter";"Miete";"Ausgang";"-1.050,00";
"""

ING = """Umsatzanzeige;Datei erstellt am: 01.02.2024 10:00
;Letztes Update: aktuell

IBAN;DE12 3456 7890 1234 5678 90
Kontoname;Girokonto
Bank;ING

Buchung;Valuta;Auftraggeber/Empfänger;Buchungstext;Verwendungszweck;Saldo;Währung;Betrag;Währung
31.01.2024;31.01.2024;REWE Markt;Lastschrift;Einkauf;1.000,00;EUR;-23,45;EUR
31.01.2024;31.01.2024;REWE Markt;Lastschrift;Einkauf;1.023,45;EUR;-23,45;EUR
02.01.2024;02.01.2024;Kiosk;Kartenzahlung;Zeitung;1.046,90;EUR;-2,20;EUR
"""

SPARKASSE = (
    '"Auftragskonto";"Buchungstag";"Valutadatum";"Buchungstext";"Verwendungszweck";'
    '"Lastschrift Ursprungsbetrag";"Beguenstigter/Zahlungspflichtiger";"Betrag";"Waehrung";"Info"\n'
    '"DE123";"30.01.24";"30.01.24";"FOLGELASTSCHRIFT";"Strom Januar";"";"Stadtwerke";"-85,00";"EUR";'
    '"Umsatz gebucht"\n'
    '"DE123";"03.01.24";"03.01.24";"GUTSCHRIFT";"Erstattung";"";"Krankenkasse";"120,50";"EUR";"Umsatz gebucht"\n'
)

ENGLISH = """Date,Payee,Memo,Amount
2024-01-31,Coffee Shop,"Latte, large",-4.20
2024-01-15,ACME Inc,Salary,"3,100.00"
2024-01-02,Bookstore,Books,-0.00
"""


@pytest.fixture
def write(tmp_path):
    def _write(text, name="export.csv", encoding="utf-8"):
        path = tmp_path / name
        path.write_bytes(text.encode(encoding))
        return path

    return _write
