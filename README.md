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
environment variable `MMV_DATA_DIR`. **Save backup** and **Load backup** in the main window copy all data into a
zip file and back.


Workflow
--------
The main window leads through four steps:

1. **Accounts**: import the transactions of your bank accounts.
2. **Rules**: give every transaction a category. The main window counts the transactions without category,
   **Categorize** lists them.
3. **Income & Expenses**: check month by month what was paid (cash basis). Is every larger payment understood?
4. **Budget**: is the spending right in the long run? Payments are spread over the time they are used in (accrual
   basis) and compared with the 50/30/20 rule.


1. Importing data
-----------------
Basically all banks offer on their website the option to export transaction data as CSV.
Open **Accounts**, select an account and click **Import data**. Encoding, separator, header line, number and
date format are detected and the columns for date, recipient, description and value are proposed for common
German banks. Check the preview and import. The settings are stored as an import profile and used again for the
next file with the same columns. Transactions that are already in the account are skipped, so overlapping
exports can be imported safely.


2. Categories and rules
-----------------------
Every transaction gets a category such as `household.food.grocery`: the main category `household`, subcategories
after the points. Double click a transaction to categorize it:

* **all matching transactions (rule)**: a rule assigns its category to every transaction whose recipient and
  description contain its regular expressions. The proposal matches the recipient of the transaction; the preview
  shows all transactions the rule catches. Rules are applied in order, later ones win.
* **only this transaction (manual category)**: wins over all rules.

The cursor starts in the category: type it, choose a proposal with the arrow keys, **Enter** saves, **Escape**
cancels. Rules have no names; **Rules** lists what each one does: `#` (the order), what recipient and description
must contain, category, spread, residual value and the transactions it categorizes. Filter the list, e.g. by
`insurance`, and change category, spread or residual value right in the table: select the cell and type. Double
click a rule to edit it with all its transactions.

A transfer between two of your accounts gets the name of the receiving account as category, e.g. `Tagesgeld`. Such
internal transfers are no income or expense and can be hidden.


Spreading payments over time
----------------------------
A payment often covers more than the month in which it is paid. For the budget it is spread over the time in which
it is used, like accounting does it (accrual basis, *Periodisierung*). Set **Spread over** and, for things you will
sell again, the **Residual value** in the rule or for the single transaction:

| case                         | example                                       | spread                     | German term                    |
|------------------------------|-----------------------------------------------|----------------------------|--------------------------------|
| prepaid service period       | car insurance 600 € per year                  | 12 months: 50 € per month  | Rechnungsabgrenzung            |
| durable good                 | sofa 2,400 €, used ten years                  | 10 years: 20 € per month   | Abschreibung, Nutzungsdauer    |
| durable good with resale     | car 30,000 €, five years, 40 % residual value | 5 years: 300 € per month   | Wertverlust, Restwert          |
| sale of a spread purchase    | the car is sold for 10,000 € after 76 months  | 20,000 € over 76 months    | Verkauf, Restbuchwert          |

* Only the loss of value is spread. The residual value stays part of your assets and is no consumption.
* When you sell the thing, open the incoming payment, choose **only this transaction** and the purchase under
  **Sale of**. The estimate is then replaced by the facts: price minus sale proceeds, spread evenly over the months
  you owned it. The proceeds are no income.
* Nothing is projected into the future: only real payments are spread. The part of a spread that lies after the
  last transaction is already paid but not used yet.
* Spread what matters: amounts from a few hundred euros (German tax law expenses goods up to 800 € at once) that are
  used longer than a year, and payments for a service period. Typical useful lives: phone or laptop 3-5 years,
  furniture 10-15 years, kitchen 15 years, bike 7 years. For a car take the time you plan to keep it and the price
  you expect to get as residual value.


3. Income & Expenses (cash basis)
---------------------------------
Monthly sums per category, as paid. Months that differ clearly from the median of the previous 12 months are
highlighted (red: more expenses or less income, green: the opposite), so a missing or doubled payment, e.g. of the
rent, stands out. Below the categories: income, expenses (needs and wants), savings (transfers to savings) and the
net change of your accounts. Double click a cell to see its transactions.


4. Budget (accrual basis, 50/30/20)
-----------------------------------
Every main category belongs to a budget group; drag it into the right list. New main categories into which more
money comes than goes out start as income, all others as needs.

| group    | share of the net income | examples                                                              |
|----------|-------------------------|-----------------------------------------------------------------------|
| Income   |                         | salary, child benefit, interest, refunds                              |
| Needs    | 50 %                    | rent, utilities, groceries, insurance, the way to work                |
| Wants    | 30 %                    | leisure, restaurants, travel, hobbies, subscriptions                  |
| Savings  | 20 % (the rest)         | ETF savings plan, savings account that is not an account here         |

The key figure is the **savings rate**: income minus needs and wants, as a share of the income. Both directions
matter. Saving less than the target does not keep up your standard of living. Saving far more is a life not lived
now: money loses value through inflation and the quality of life does not grow with age. The budget therefore
says how much you could spend more per month (room for consumption) or should spend less. The rates do not depend
on inflation, so nothing is adjusted for it.

The graphs show the moving average of the last 12 months, the long-term view; uncheck **12-month average** for the
single months. Simulating the future with scenarios (inflation, retirement, crises) is the job of
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
| room for consumption     | Konsumspielraum                          | what could be spent more and still reach the savings goal |


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
