# -*- coding: utf-8 -*-

import os

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.importers import Importers, Importer


def test_importers_create(tmp_path, test_config):
    config_filepath = test_config.dir_path + "/importers.yaml"

    imps = Importers(config=test_config)

    imp_names = []
    for i in range(5):
        imp = imps.add()
        imp_names += [imp.name]
    assert len(imps) == 5

    imps.save()
    assert os.path.isfile(config_filepath)

    imps.delete(imp_names[0])
    assert len(imps) == 4

    # save accounts using single account
    os.remove(config_filepath)
    imps.get_by_name(imp_names[1]).save()
    assert os.path.isfile(config_filepath)

    # rename tagger
    t3 = imps.get_by_name(imp_names[2])
    t3.name = "importer_1337"
    t3.save()
    assert "importer_1337" in imps


def test_importers_determine_config(test_input_latin1):
    filepath, config = test_input_latin1
    imp = Importer(parent=None)
    imp.determine_and_set_config(config={}, filepath=filepath)
    config = imp.config
    assert nn.encoding in imp.config
    assert imp.config[nn.encoding] == config[nn.encoding]
    assert nn.seperator in config
    assert imp.config[nn.seperator] == config[nn.seperator]
    assert nn.skiprows in config
    assert imp.config[nn.skiprows] == config[nn.skiprows]
    assert set(imp.available_columns) == {nn.date + " fää", nn.recipient + " föö", nn.description + " foo",
                                          nn.value + " foo", nn.tag, nn.tagger_name, nn.transaction_id}


def test_importers_load_latin1(test_input_df, test_input_latin1):
    filepath, config = test_input_latin1
    imp = Importer(parent=None, **config)
    df = imp.load_df(filepath=filepath)
    assert set(test_input_df.columns) == set(df.columns)
    assert len(test_input_df) == len(df)
    assert test_input_df[nn.value].sum() == df[nn.value].sum()


def test_importers_load_utf8(test_input_df, test_input_utf8):
    filepath, config = test_input_utf8
    imp = Importer(parent=None, **config)
    df = imp.load_df(filepath=filepath)
    assert set(test_input_df.columns) == set(df.columns)
    assert len(test_input_df) == len(df)
    assert test_input_df[nn.value].sum() == df[nn.value].sum()


def test_importers_get_working(tmp_path, test_config, test_input_df, test_input_latin1, test_input_utf8):
    filepath, config = test_input_latin1
    filepath2, config2 = test_input_utf8

    imps = Importers(config=test_config)

    # no importer yet, determine right enconding, tc..
    imp = imps.get_working_importer(filepath=filepath)
    assert imp.name is None
    assert imp.config[nn.encoding] == config[nn.encoding]
    assert imp.config[nn.seperator] == config[nn.seperator]
    assert imp.config[nn.skiprows] == config[nn.skiprows]

    # test importer working
    imp.config[nn.decimal] = config[nn.decimal]
    imp.col_date = config[nn.col_date]
    imp.col_description = config[nn.col_description]
    imp.col_recipient = config[nn.col_recipient]
    imp.col_value = config[nn.col_value]

    df = imp.load_df(filepath=filepath)
    assert set(test_input_df.columns) == set(df.columns)
    assert len(test_input_df) == len(df)
    assert test_input_df[nn.value].sum() == df[nn.value].sum()

    # save importer and get it back
    imp.name = "test1"
    imp.save()
    assert len(imps) == 1
    imp2 = imps.get_working_importer(filepath=filepath)
    df = imp2.load_df(filepath=filepath)
    assert set(test_input_df.columns) == set(df.columns)
    assert len(test_input_df) == len(df)
    assert test_input_df[nn.value].sum() == df[nn.value].sum()
    assert imp2.name == "test1"

    # make sure it is not saved two times
    imp2.save()
    assert len(imps) == 1

    # add second importer
    imp3 = imps.get_working_importer(filepath=filepath2)
    assert imp3.name is None
    assert imp3.config[nn.encoding] == config2[nn.encoding]
    assert imp3.config[nn.seperator] == config2[nn.seperator]
    assert imp3.config[nn.skiprows] == config2[nn.skiprows]
    # test 1st importer still working
    imp4 = imps.get_working_importer(filepath=filepath)
    assert imp4.name == imp.name
    assert imp4.config[nn.encoding] == config[nn.encoding]
    assert imp4.config[nn.seperator] == config[nn.seperator]
    assert imp4.config[nn.skiprows] == config[nn.skiprows]
