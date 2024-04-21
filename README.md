MyMoneyVisualizer
=================

Where did all my money go? Simple tool (100% offline) for visualizing your income and expenses.


Installation
------------

Checkout code:
 
    $ git clone git@gitlab.com:tnikodem/mymoneyvisualizer.git mymoneyvisualizer
    $ cd mymoneyvisualizer
    
(Optional) Create and activate virtual environment:

    $ virtualenv -p python3 venv
    $ source venv/bin/activate
    
Install:

    $ pip install -e .
    
Start:

    $ mmv 

Importing Data
--------------
Basically all banks offer on their website the option to export transaction data and save it locally.
Sometimes the option is a bit hidden, in which case a search engine can help you.
Opening the account view it is possible to import many of such files by clicking on the **import** button.
In the import window check if the guessed format specifications are alright, and select according columns for date,
 recipient, transaction description and transaction value.

Tags and Subtags
----------------
Each transaction can be given a tag. Either double click on a transaction or use the **add tagger** button in the tagger overview to define a new *tagger*.
Each *tagger* gives all transactions based on recipient and description a tag using regex.
You can define subtags by splitting tag and subtag with a point, e.g. "household.food.grocery". 

Money Transfer
--------------
If you have two or more accounts you probably also transfer money between them.

#### Two transaction entries
If you have a transaction log in both accounts the proposed strategy is to give both transaction entries the same tag, e.g. "transfer".
In that case in the summary overview both transactions should cancel out.

#### One Transaction entry
In case you only have one transaction log, for example one bank account and *cash*, you can define as tag the name of the other account.
The money will be automatically associated with the other account, if the tag is equal to the account name.

Development
-----------

Start with debug logs:

    $ mmv --debug
    
Development installation:

    $ pip install -e ".[dev]"
    
Run Unit Tests:

    standard:
    $ py.test tests/
    
    with IPython support:
    $ py.test tests/ -s
    
    with coverage report:
    $ py.test --cov=mymoneyvisualizer --cov-report term --cov-report html:coverage tests/ 
