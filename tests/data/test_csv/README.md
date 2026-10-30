Bank exports for tests
======================

All transactions, names, IBANs and amounts are made up. The layouts are reconstructed from knowledge of
the export formats, not copied from real downloads; details of real exports may differ.

`expected.yaml` holds the ground truth for every file: the rows the importer must produce (date, recipient,
description, value, including text that is broken on purpose), the number of skipped rows and a category per
transaction. It comes from the generator of these files, never from the importer.
`tests/importing/test_bank_exports.py` imports every file with automatic detection, creates a rule per
transaction from its texts and checks the income & expenses table per category.

| file | layout | special |
|---|---|---|
| `transactions1.csv` | DKB Girokonto (since 2023) | UTF-8 BOM, `-1.050` without decimals, recipient of incoming payments is the own name |
| `transactions2.csv` | broker with card (Trade Republic like, guessed) | comma, ISO timestamps, value = `amount` + `fee` + `tax` |
| `transactions3.csv` | DKB Visa | no recipient column, date = Belegdatum, foreign currency column |
| `transactions4.csv` | DKB Girokonto (until 2023) | umlauts already destroyed (`�`), trailing `;` |
| `ing_girokonto.csv` | ING | Windows-1252, no quotes, long preamble with notice text |
| `sparkasse_camt.csv` | Sparkasse CSV-CAMT V2 | Windows-1252, dates `dd.mm.yy` |
| `volksbank_neu.csv` | Volksbank/Raiffeisenbank (current) | recipient = `Name Zahlungsbeteiligter` |
| `volksbank_alt_soll_haben.csv` | Volksbank/Raiffeisenbank (old) | unsigned amount + `S`/`H` column, multi-line purpose, balance lines |
| `deutsche_bank.csv` | Deutsche Bank | empty `Betrag`, amounts in `Soll`/`Haben`, padded preamble, `Wert` is a date |
| `postbank.csv` | Postbank (older) | padded preamble, amounts with `€` |
| `comdirect.csv` | comdirect | no recipient column, pending row `offen`, balance line |
| `commerzbank.csv` | Commerzbank | no recipient column, `Auftraggeberkonto` is an account number |
| `n26.csv` | N26 | comma, ISO dates, English headers |
| `paypal.csv` | PayPal (German) | comma with decimal comma, value = `Netto`, description = `Typ` |
| `defekt_doppelt_kodiert.csv` | DKB, double encoded | `Ã¤` instead of `ä`, also in the header |
| `defekt_gemischte_kodierung.csv` | Sparkasse, merged | UTF-8 with two lines in Windows-1252 |
| `defekt_excel_unicode.txt` | ING saved by Excel as "Unicode text" | UTF-16 with BOM, tabs |
| `defekt_trennzeichen_im_text.csv` | two ING exports merged | unquoted `;` in the purpose, second header, sum line |
| `defekt_steuerzeichen.csv` | N26 | NUL bytes, tab, line break and U+2028 in the text |
