MyMoneyVisualizer
=================

Where did all my money go? A simple tool (100 % offline) for the finances of a private household: import the
exports of your bank, categorize the transactions and see at a glance whether you spend too much or too little.


Installation
------------

Requires Python 3.11 or newer.

    python -m venv venv
    source venv/bin/activate        # Windows: venv\Scripts\activate
    pip install .

Start:

    mmv

Your data is stored in the user data directory (e.g. `%LOCALAPPDATA%\MyMoneyVisualizer` on Windows,
`~/.local/share/MyMoneyVisualizer` on Linux). Choose another place with `mmv --data-dir PATH` or the
environment variable `MMV_DATA_DIR`. **Sicherung speichern** and **Sicherung laden** in the main window copy all
data into a zip file and back.

The user interface is German; this README names its buttons as they are labelled.


Workflow
--------
The main window leads through four steps, shows the state of each and highlights the next one:

1. **Konten** (accounts): import the transactions of your bank accounts.
2. **Kategorisieren** (categorize): give every transaction a category. **Ohne Kategorie** lists the transactions
   without one, **Regeln** all rules.
3. **Einnahmen & Ausgaben** (income & expenses): check month by month what was paid (cash basis). Is every larger
   payment understood?
4. **Budget**: is the spending right in the long run? Payments are spread over the time they are used in (accrual
   basis) and compared with the 50/30/20 rule. The main window already shows the savings rate.

Little text stays on screen: buttons, columns and key figures explain themselves in tooltips, every window has a
**?** with its explanation. The windows with numbers say in a banner how they count; close it with **✕** once read,
it does not come back.


1. Importing data
-----------------
Basically all banks offer on their website the option to export transaction data as CSV. Open **Konten**, select an
account and click **CSV-Datei importieren**. Encoding, separator, header line, number and date format are detected
and the columns for date, recipient, description and value are proposed for common German banks. Check the preview
and import; the file format can be corrected under **Erweiterte Einstellungen**. The settings are stored as an
import profile and used again for the next file with the same columns. Transactions that are already in the account
are skipped, so overlapping exports can be imported safely.


2. Categories and rules
-----------------------
Every transaction gets a category such as `household.food.grocery`: the main category `household`, subcategories
after the points. Double click a transaction to categorize it:

* **alle passenden Buchungen (Regel)**: a rule assigns its category to every transaction whose recipient and
  description contain its regular expressions. The proposal matches the recipient of the transaction; the preview
  shows all transactions the rule catches. Rules are applied in order, later ones win.
* **nur diese Buchung** (manual category): wins over all rules.

The cursor starts in the category: type it, choose a proposal with the arrow keys, **Enter** saves, **Escape**
cancels. Rules have no names; **Regeln** lists what each one does: `#` (the order), what recipient and description
must contain, category, spread, residual value and the transactions it categorizes. **überschrieben** counts the
transactions it matches that get their category from a later rule or a manual category; many of them and no
transactions of its own mean the rule is superfluous or in the wrong place. Filter the list, e.g. by `insurance`, and
change category, spread or residual value right in the table: select the cell and type. Double click a rule to edit
it with all its transactions; the ones another rule takes are grey and name that rule.

A transfer between two of your accounts gets the name of the receiving account as category, e.g. `Tagesgeld`. Such
internal transfers are no income or expense and can be hidden.


Spreading payments over time
----------------------------
A payment often covers more than the month in which it is paid. For the budget it is spread over the time in which
it is used, like accounting does it (accrual basis, *Periodisierung*). Set **Verteilen über** and, for things you
will sell again, the **Restwert** in the rule or for the single transaction:

| case                         | example                                       | spread                     | German term                    |
|------------------------------|-----------------------------------------------|----------------------------|--------------------------------|
| prepaid service period       | car insurance 600 € per year                  | 12 months: 50 € per month  | Rechnungsabgrenzung            |
| durable good                 | sofa 2,400 €, used ten years                  | 10 years: 20 € per month   | Abschreibung, Nutzungsdauer    |
| durable good with resale     | car 30,000 €, five years, 40 % residual value | 5 years: 300 € per month   | Wertverlust, Restwert          |
| sale of a spread purchase    | the car is sold for 10,000 € after 76 months  | 20,000 € over 76 months    | Verkauf, Restbuchwert          |

* Only the loss of value is spread. The residual value stays part of your assets and is no consumption.
* When you sell the thing, open the incoming payment, choose **nur diese Buchung** and the purchase under
  **Verkauf von**. The estimate is then replaced by the facts: price minus sale proceeds, spread evenly over the months
  you owned it. The proceeds are no income.
* Nothing is projected into the future: only real payments are spread. The part of a spread that lies after the
  last transaction is already paid but not used yet.
* Spread what matters: amounts from a few hundred euros (German tax law expenses goods up to 800 € at once) that are
  used longer than a year, and payments for a service period. Typical useful lives: phone or laptop 3-5 years,
  furniture 10-15 years, kitchen 15 years, bike 7 years. For a car take the time you plan to keep it and the price
  you expect to get as residual value.


3. Einnahmen & Ausgaben (cash basis)
------------------------------------
Monthly sums per category, as paid. **Zeitraum** chooses the last twelve complete months, a calendar year or a
period of your own. Months that differ clearly from the median of the previous 12 months are highlighted (red: more
expenses or less income, green: the opposite), so a missing or doubled payment, e.g. of the rent, stands out. Below
the categories: income, expenses (needs and wants), savings (transfers to savings) and the net change of your
accounts (*Saldo*). Double click a cell to see its transactions.

Why the numbers differ from the budget: this table counts a payment in the month it was paid, the budget spreads it
over the months it is used in and leaves out internal transfers. The car insurance of 684 € in January is -684 € in
January here and -57 € in every month in the budget; over the year both add up to the same. **Mehr** in the banner
of both windows (*Zahlungssicht* and *periodengerecht*) and their **?** explain it.


4. Budget (accrual basis, 50/30/20)
-----------------------------------
**Zeitraum** is the last twelve complete months (the default), a calendar year or **Eigener Zeitraum** from one month
to another. The current month only counts when it is over, so a half month does not distort the averages.

Four key figures answer the main question: **Nettoeinkommen** and **Konsumausgaben** per month, the **Sparquote**
(savings rate) against its target and the **Abstand zum Sparziel**: how much you could spend more per month, or
should spend less, to reach the savings target. Below, **Kategorien** lists per month every budget group and main
category with its share of the income and, for a period of 12 months, the change against the 12 months before (red:
worse, green: better), so large cost factors and growing ones stand out. A click on a row shows its development in
the chart next to it, another click (or Escape, or **Gesamt** in the path above the chart) the whole again. A double
click lists everything that counts in the period: also payments made before and spread into it, and of payments
spread beyond it only their share (**Betrag im Zeitraum**); together they add up to the value in the budget.
**verteilt** names the whole amount spread and for how long, e.g. `-900,00 € über 1 Jahr`.

Drag a category in **Kategorien** to change its order (also in the chart) or, dropped into another group, its group;
a drag selects nothing, so the chart stays as it is, also in the overall view.
Every main category belongs to a budget group. **Gruppen & Ziele** opens a window with a list per group: drag a
category into another list or use its context menu, and set the targets of the groups there. New main categories into
which more money comes than goes out start as income, all others as needs.

| group                         | share of the net income | examples                                               |
|-------------------------------|-------------------------|--------------------------------------------------------|
| Einkommen (income)            |                         | salary, child benefit, interest, refunds               |
| Grundbedarf (needs)           | 50 %                    | rent, utilities, groceries, insurance, the way to work |
| Freizeit & Lebensstil (wants) | 30 %                    | leisure, restaurants, travel, hobbies, subscriptions   |
| Sparen (savings)              | 20 % (the rest)         | ETF savings plan, savings account that is not tracked  |

The key figure is the **savings rate**: income minus needs and wants, as a share of the income. Both directions
matter. Saving less than the target does not keep up your standard of living. Saving far more is a life not lived
now: money loses value through inflation and the quality of life does not grow with age. The budget therefore says
how much you could spend more per month or should spend less (distance to the savings target). The rates do not
depend on inflation, so nothing is adjusted for it.

The chart shows the moving average of the last 12 months, the long-term view, from the first month with a full year
before it; uncheck **gleitender Ø 12 Monate** for the single months. Two blue lines mark the period, another one
shows the average in it. Zoom with the mouse wheel or **+** and **−**, drag to move, **↺** shows all.
The mouse on an area shows its value in that month, a click lists its transactions (for the moving average those of
the 12 months up to it).

Simulating the future with scenarios (inflation, retirement, crises) is the job of
[futureplanner](https://github.com/tnikodem/futureplanner); the spread monthly amounts per category are its input.


Glossary
--------

| here                     | German                                   | meaning                                                   |
|--------------------------|------------------------------------------|-----------------------------------------------------------|
| category, main category  | Kategorie, Hauptkategorie                | what a transaction is for                                 |
| rule                     | Kategorisierungsregel                    | categorizes all matching transactions                     |
| manual category          | Einzelzuordnung                          | category of one transaction, wins over the rules          |
| internal transfer        | Umbuchung                                | transfer between your own accounts                        |
| cash basis               | Zahlungssicht, Zufluss-Abfluss-Prinzip   | counted when paid                                         |
| accrual basis            | periodengerechte Sicht, Periodisierung   | counted when used                                         |
| prepaid expense          | (aktive) Rechnungsabgrenzung             | payment for a later service period                        |
| depreciation             | Abschreibung (AfA)                       | price of a durable good spread over its useful life       |
| useful life              | Nutzungsdauer                            | how long a durable good is used                           |
| residual value           | Restwert                                 | what a durable good is still worth at the end             |
| savings rate             | Sparquote                                | share of the income that is not consumed                  |
| consumption expenditure  | Konsumausgaben                           | needs and wants; savings are no consumption               |
| distance to the target   | Abstand zum Sparziel                     | what could be spent more and still reach the savings goal |


Development
-----------

    pip install -e ".[dev]"
    pytest --cov                 # tests incl. GUI tests (headless)
    ruff check . && ruff format .
    mmv --debug

Structure of the package:

| package                         | content                                                                    |
|---------------------------------|----------------------------------------------------------------------------|
| `mymoneyvisualizer.domain`      | pure logic on pandas tables: categorization, accrual, analysis, budget     |
| `mymoneyvisualizer.importing`   | CSV format detection, import profiles, duplicate detection                 |
| `mymoneyvisualizer.storage`     | data directory (CSV + YAML), atomic writes, backups                        |
| `mymoneyvisualizer.app`         | `AppModel`: state and use cases, emits `changed(topics)`; no Qt            |
| `mymoneyvisualizer.ui`          | PyQt6 windows; they only display data and call `AppModel`                  |

Everything except `ui` can be used and tested without a GUI. All test data is made up; the repository is public,
so real account data must never be committed (`tests/test_private_data.py` checks for real IBANs). Before version
1.0 the data format may change without compatibility code; a conversion script is provided for such changes.
