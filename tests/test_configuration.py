# -*- coding: utf-8 -*-

import datetime
import os
import zipfile
import pandas as pd

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.configuration import Configuration


def test_config_create(tmp_path):
    config = Configuration(dir_path=str(tmp_path)+"/config")
    assert config is not None
    assert config.accounts is not None
    assert config.taggers is not None
    assert config.importers is not None

    # add entries to elements
    account = config.accounts.add("foo")
    account.update(pd.DataFrame({nn.date: [datetime.datetime(2019, 1, 1)],
                          nn.recipient: ["bla"],
                          nn.description: ["blub"],
                          nn.value: [1337]
                          }))
    config.taggers.add("bar")
    config.importers.add("blub")

    # save config
    config_savefilepath = str(tmp_path)+"/config.zip"
    config.save(filepath=config_savefilepath)
    assert os.path.isfile(config_savefilepath)
    with zipfile.ZipFile(config_savefilepath, 'r') as myzip:
        saved_files = [f.filename for f in myzip.filelist]
        assert any("accounts.yaml" in f for f in saved_files)
        assert any("accounts/foo.csv" in f for f in saved_files)
        assert any("taggers.yaml" in f for f in saved_files)
        assert any("importers.yaml" in f for f in saved_files)

    # load config again
    config.accounts.delete("foo")
    config.taggers.delete("bar")
    config.importers.delete("blub")

    config.load(config_savefilepath)

    assert len(config.accounts) == 1
    assert len(config.accounts.get_by_name("foo")) == 1
    assert len(config.taggers) == 1
    assert len(config.importers) == 1
