import pytest

import datetime
import pandas as pd
import uuid

from mymoneyvisualizer.naming import Naming as Nn
from mymoneyvisualizer.configuration import Configuration


@pytest.fixture(scope="function")
def test_input_df():
    dates = []
    recipients = []
    descriptions = []
    values = []
    for i in range(10):
        dates += [datetime.datetime(2018, 7, 6)]
        recipients += ["rec a"]
        descriptions += ["des " + str(i)]
        values += [13.37*i]
    for i in range(10):
        dates += [datetime.datetime(2018, 11, 24)]
        recipients += ["rec a"]
        descriptions += ["des " + str(i)]
        values += [13.37*i]
    for i in range(10):
        dates += [datetime.datetime(2018, 11, 24)]
        recipients += ["rec b"]
        descriptions += ["des " + str(i)]
        values += [13.37*i]
    for i in range(10):
        dates += [datetime.datetime(2018, 11, 25)]
        recipients += ["rec a"]
        descriptions += ["des duplicate"]
        values += [13.37*i]

    df = pd.DataFrame({
        Nn.date: dates,
        Nn.recipient: recipients,
        Nn.description: descriptions,
        Nn.value: values,
        Nn.tag: [""]*len(dates),
        Nn.tagger_name: [""]*len(dates)
    })
    df[Nn.transaction_id] = df.apply(lambda x: str(uuid.uuid4()), axis=1)
    return df


@pytest.fixture(scope="function")
def test_input_latin1(tmp_path, test_input_df):
    filepath = str(tmp_path) + "/test_imput_latin1.csv"
    df = test_input_df.copy()
    config = {
        Nn.col_date: Nn.date+" fää",
        Nn.col_recipient: Nn.recipient + " föö",
        Nn.col_description: Nn.description + " foo",
        Nn.col_value: Nn.value + " foo",
        Nn.seperator: ";",
        Nn.thousands: ".",
        Nn.decimal: ",",
        Nn.dayfirst: True,
        Nn.skiprows: 6,
        Nn.encoding: "latin-1"
    }

    df = df.rename(columns={
        Nn.date: config[Nn.col_date],
        Nn.recipient: config[Nn.col_recipient],
        Nn.description: config[Nn.col_description],
        Nn.value: config[Nn.col_value], })

    with open(filepath, mode='w', encoding=config[Nn.encoding]) as f:
        for i in range(config[Nn.skiprows]):
            f.write("'bar \n")

    df.to_csv(filepath, mode="a", encoding=config[Nn.encoding], sep=config[Nn.seperator], decimal=config[Nn.decimal],
              date_format='%d-%m-%Y', index=False)

    return filepath, config


@pytest.fixture(scope="function")
def test_input_utf8(tmp_path, test_input_df):
    filepath = str(tmp_path) + "/" + "test_imput_utf8.csv"
    df = test_input_df.copy()

    config = {
        Nn.col_date: Nn.date+" foo",
        Nn.col_recipient: Nn.recipient + " foo",
        Nn.col_description: Nn.description + " foo",
        Nn.col_value: Nn.value + " foo",
        Nn.seperator: ",",
        Nn.thousands: "",
        Nn.decimal: ".",
        Nn.dayfirst: False,
        Nn.skiprows: 9,
        Nn.encoding: "utf-8"
    }

    df = df.rename(columns={
        Nn.date: config[Nn.col_date],
        Nn.recipient: config[Nn.col_recipient],
        Nn.description: config[Nn.col_description],
        Nn.value: config[Nn.col_value]})

    with open(filepath, mode='w', encoding=config[Nn.encoding]) as f:
        for i in range(config[Nn.skiprows]):
            f.write("'bar \n")

    df.to_csv(filepath, mode="a", encoding=config[Nn.encoding], sep=config[Nn.seperator], decimal=config[Nn.decimal],
              index=False)

    return filepath, config


class TestConfig:
    def __init__(self, dir_path):
        self.dir_path = dir_path


@pytest.fixture(scope="function")
def test_config(tmp_path):
    return TestConfig(dir_path=str(tmp_path)+"/config")


@pytest.fixture(scope="function")
def config(tmp_path):
    return Configuration(dir_path=str(tmp_path)+"/config")


@pytest.fixture(scope="function")
def config_full(config):
    acc1 = config.accounts.add("acc1")
    acc1.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag1", value=30.1)
    acc1.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag2", value=20.1)
    acc1.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag3", value=10.1)

    acc2 = config.accounts.add("acc2")
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag1", value=300.1)
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag2", value=200.1)
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag2", value=200.1)
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag3", value=100.1)
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag3", value=100.1)
    acc2.add_entry(date=datetime.datetime(2019, 1, 1),
                   recipient="", description="tag3", value=100.1)

    config.taggers.add(name="tagger1", regex_description="tag1", tag="tag1")
    config.taggers.add(name="tagger2", regex_description="tag2", tag="tag2")
    config.taggers.add(name="tagger3", regex_description="tag3", tag="tag3")

    config.accounts.tag_dfs()

    return config
