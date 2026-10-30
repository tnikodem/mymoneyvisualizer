MyMoneyVisualizer
=================

Where did all my money go? Simple tool (100% offline) for visualizing your income and expenses.


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
environment variable `MMV_DATA_DIR`.

Importing Data
--------------
Basically all banks offer on their website the option to export transaction data as CSV.
Open **Accounts**, select an account and click **Import data**. Encoding, separator, header line, number and
date format are detected and the columns for date, recipient, description and value are proposed for common
German banks. Check the preview and import. The settings are stored as an import profile and used again for the
next file with the same columns. Transactions that are already in the account are skipped, so overlapping
exports can be imported safely.

Categories and Rules
--------------------
Each transaction gets a category. Double click a transaction or use **Add Rule** in the rules overview to define a
new *rule*. A rule assigns its category to all transactions whose recipient and description match its regular
expressions. Rules are applied in order, later ones win. A single transaction can get a **manual category** that
wins over all rules.

Split category and subcategory with a point, e.g. `household.food.grocery`. Transactions categorized with the name
of one of your accounts are internal transfers between your own accounts and can be hidden.

A rule can mark transactions as *recurring every n years* (e.g. a yearly insurance). The budget graph spreads
them over that period and expects them to happen again.

Income & Expenses and Budget
----------------------------
* **Income & Expenses**: monthly sums per category. Months that differ clearly from the median of the previous 12
  months are highlighted (red: more expenses / less income, green: the opposite). Double click a cell to see its
  transactions.
* **Budget**: stacked needs and wants compared with a share of your income. Drag main categories between the
  lists to change their budget group.


Development
-----------

    pip install -e ".[dev]"
    pytest --cov                 # tests incl. GUI tests (headless)
    ruff check . && ruff format .
    mmv --debug

Structure of the package:

| package                         | content                                                                    |
|---------------------------------|----------------------------------------------------------------------------|
| `mymoneyvisualizer.domain`      | pure logic on pandas tables: categorization, income & expenses, budget     |
| `mymoneyvisualizer.importing`   | CSV format detection, import profiles, duplicate detection                 |
| `mymoneyvisualizer.storage`     | data directory (CSV + YAML), atomic writes, backups                        |
| `mymoneyvisualizer.app`         | `AppModel`: state and use cases, emits `changed(topics)`; no Qt            |
| `mymoneyvisualizer.ui`          | PyQt6 windows; they only display data and call `AppModel`                  |

Everything except `ui` can be used and tested without a GUI. `tests/test_characterization.py` compares the
analysis with numbers recorded from version 0.1 (see `tests/data/README.md`).
