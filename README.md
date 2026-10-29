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
environment variable `MMV_DATA_DIR`. Version 0.1 kept the data in `./config` of the directory `mmv` was started
from; if such a directory exists it is still used and migrated automatically.

Importing Data
--------------
Basically all banks offer on their website the option to export transaction data as CSV.
Open **Accounts**, select an account and click **Import data**. Encoding, separator, header line, number and
date format are detected and the columns for date, recipient, description and value are proposed for common
German banks. Check the preview and import. The settings are stored as an import profile and used again for the
next file with the same columns. Transactions that are already in the account are skipped, so overlapping
exports can be imported safely.

Tags and Subtags
----------------
Each transaction can be given a tag. Either double click on a transaction or use **Add Tagger** in the tagger
overview to define a new *tagger*. A tagger tags all transactions whose recipient and description match its
regular expressions. Taggers are applied in order, later ones win. A single transaction can get a **one time tag**
that wins over all taggers.

Split tag and subtag with a point, e.g. `household.food.grocery`. Transactions tagged with the name of one of
your accounts are transfers between your own accounts and can be hidden in the summary.

A tagger can mark transactions as *recurring every n years* (e.g. a yearly insurance). The budget graph spreads
them over that period and expects them to happen again.

Summary and Budget
------------------
* **Summary Table**: monthly sums per tag. Months that differ clearly from the median of the previous 12 months
  are highlighted (red: more expenses / less income, green: the opposite). Double click a cell to see its
  transactions.
* **Summary Graph**: stacked basic and optional expenses compared with a share of your income. Drag tags between
  the lists to change their category.


Development
-----------

    pip install -e ".[dev]"
    pytest --cov                 # tests incl. GUI tests (headless)
    ruff check . && ruff format .
    mmv --debug

Structure of the package:

| package                         | content                                                                    |
|---------------------------------|----------------------------------------------------------------------------|
| `mymoneyvisualizer.domain`      | pure logic on pandas tables: tagging, summary table, budget, models        |
| `mymoneyvisualizer.importing`   | CSV format detection, import profiles, duplicate detection                 |
| `mymoneyvisualizer.storage`     | data directory (CSV + YAML), atomic writes, migration of 0.1, backups      |
| `mymoneyvisualizer.app`         | `AppModel`: state and use cases, emits `changed(topics)`; no Qt            |
| `mymoneyvisualizer.ui`          | PyQt6 windows; they only display data and call `AppModel`                  |

Everything except `ui` can be used and tested without a GUI. `tests/test_characterization.py` compares the
analysis with numbers recorded from version 0.1 (see `tests/data/README.md`).
