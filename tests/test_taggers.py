# -*- coding: utf-8 -*-

import datetime
import os
import pandas as pd

from mymoneyvisualizer.naming import Naming as Nn
from mymoneyvisualizer.taggers import Taggers


# TODO two times same tag: core dump?!

def test_taggers_create(tmp_path, test_config):
    config_filepath = test_config.dir_path + "/taggers.yaml"

    taggers = Taggers(config=test_config)

    for i in range(50):
        taggers.add(name=str(i), regex_recipient="", regex_description=str(i), tag=str(i))
    assert len(taggers) == 50

    taggers.save()
    assert os.path.isfile(config_filepath)

    taggers.delete("40")
    assert len(taggers) == 49

    # save accounts using single account
    os.remove(config_filepath)
    taggers.get_by_name("41").save()
    assert os.path.isfile(config_filepath)

    #rename tagger
    t41 = taggers.get_by_name("41")
    t41.name = "1337"
    t41.save()
    assert "1337" in taggers


def test_taggers_tag_df(tmp_path, test_config):
    taggers = Taggers(config=test_config)
    for i in range(50):
        taggers.add(name=str(i), regex_recipient="", regex_description=str(i), tag=str(i))

    dates = []
    recipients = []
    descriptions = []
    values= []
    for i in range(100):
        dates += [datetime.date(2018, 11, 24)]
        recipients += [""]
        descriptions += [str(i)]
        values += [13.37]

    test_df = pd.DataFrame({
        Nn.date: dates,
        Nn.recipient: recipients,
        Nn.description: descriptions,
        Nn.value: values,
    })

    test_df = taggers.tag_df(test_df)

    # TODO multiple taggers with simiilar regex: what to test for?
    assert test_df[Nn.tag].nunique() == 50
