MyMoneyVisualizer
=================

Where did all my money go? Simple tool (100% offline) for visualizing your income and expenses.


Installation
------------

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
