# -*- coding: utf-8 -*-

import datetime
import os
import pandas as pd

from mymoneyvisualizer.naming import Naming as Nn
from mymoneyvisualizer.accounts import Account, Accounts


def test_create_account(tmp_path):
    db_filepath = str(tmp_path)+"/test.csv"

    # new account
    account = Account(parent=None, name="test", db_filepath=db_filepath)
    assert type(account.df) == pd.DataFrame

    # add entry
    newdf = pd.DataFrame({Nn.date: [datetime.datetime(2019, 1, 1)],
                          Nn.recipient: ["bla"],
                          Nn.description: ["blub"],
                          Nn.value: [1337],
                          Nn.tag: [""],
                          Nn.tagger_name: [""]
                          })
    account.update(newdf)

    # save account
    account.save()

    assert os.path.isfile(db_filepath)

    # load account from csv and compare with acc1
    account2 = Account(parent=None, name="test2", db_filepath=db_filepath)

    assert len(account.df) == len(account2.df)
    # assert account2.df.equals(account.df)  # FIXME not working??!

    # rename account
    account.name = "test_account3"
    account.save()
    assert os.path.isfile(str(tmp_path)+"/test_account3.csv")


def test_create_accounts(tmp_path, test_config):
    config_filepath = test_config.dir_path + "/accounts.yaml"
    default_db_filepath = test_config.dir_path + "/accounts/"
    # config_filepath2 = str(tmp_path)+"/test_accounts2.yaml"

    # new accounts
    accounts = Accounts(dir_path=test_config.dir_path, taggers=None)
    assert accounts is not None
    assert len(accounts) == 0

    # add empty accounts
    acc_names = []
    for i in range(3):
        acc = accounts.add()
        acc_names += [acc.name]
        assert len(accounts) == i+1

    # save accounts
    accounts.save()
    assert os.path.isfile(config_filepath)

    # delete account
    accounts.delete(acc_names[0])
    assert len(accounts) == 2

    # save accounts using single account, create account db csv
    os.remove(config_filepath)
    accounts.get_by_name(acc_names[1]).save()
    assert os.path.isfile(config_filepath)
    assert os.path.isfile(default_db_filepath +
                          acc_names[1].replace(" ", "_")+".csv")

    # delete account with csv
    accounts.delete(acc_names[1])
    assert not os.path.isfile(
        default_db_filepath+acc_names[1].replace(" ", "_")+".csv")
    assert len(accounts) == 1

    # load accounts
    accounts2 = Accounts(dir_path=test_config.dir_path, taggers=None)
    assert len(accounts) == len(accounts2)

    # manual add account
    db_filepath = str(tmp_path)+"/test4.csv"
    account4 = Account(parent=None, name="test4", db_filepath=db_filepath)
    account4.save(parent=accounts)
    assert len(accounts) == 2
    assert "test4" in accounts


def test_one_time_tag(config_full):
    # Check tag is set
    transactions_ids = []
    for i, account in enumerate(config_full.accounts):
        transactions_ids += [account.df[Nn.transaction_id].values[i]]
    for t_id in transactions_ids:
        config_full.taggers.save_one_time_tag(
            tag="test_tag", transaction_id=t_id, accounts=config_full.accounts)
    for i, account in enumerate(config_full.accounts):
        assert account.df[Nn.tag].values[i] == "test_tag"

    # Check tag is not overwritten
    config_full.accounts.tag_dfs()
    for i, account in enumerate(config_full.accounts):
        assert account.df[Nn.tag].values[i] == "test_tag"
