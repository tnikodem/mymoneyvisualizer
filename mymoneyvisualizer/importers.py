# -*- coding: utf-8 -*-

import logging
import numpy as np
import pandas as pd
import uuid

from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer
from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/importers.yaml"


# TODO put last used importer to the top

class Importers(OrderedDataContainer):
    def __init__(self, config):
        self.config = config
        super().__init__(container_filepath=self.config.dir_path+CONTAINER_FILEPATH)
        logger.debug("started importers")

    def add(self, name=None, **kwargs):
        logger.info("add new importer")
        if name is None:
            i = 1
            name = "importer_"
            while name + str(i) in self:
                i += 1
            name = name + str(i)

        if name in self:
            logger.warning(name + " already loaded, skipping....")
            return

        new_importer = Importer(parent=self, name=name, **kwargs)
        return super().add(name=name, obj=new_importer)

    def get_working_importer(self, filepath, config=None):
        importer = None
        if config is None:
            logger.debug("analyzing " + str(filepath))
            for imp in self.get():
                df = imp.load_df(filepath=filepath)
                if df is None:
                    continue
                if nn.date not in df.columns:
                    continue
                if nn.recipient not in df.columns:
                    continue
                if nn.description not in df.columns:
                    continue
                if nn.value not in df.columns:
                    continue
                logger.info("found working importer: "+str(imp.name))
                importer = imp
                break
        if importer is None:
            if config is None:
                config = {}
            importer = Importer(parent=self, **config)
            # overwrite must-be config, and match importer to file
            importer.determine_and_set_config(filepath=filepath, config=config)
        return importer


class Importer:
    def __init__(self, parent, name=None, skiprows=0, encoding="latin-1",
                 thousands=',', decimal='.', dayfirst=False, seperator=";",
                 col_date="",
                 col_recipient="",
                 col_description="",
                 col_value="",
                 drop_duplicates=True,
                 import_since=None,
                 **kwargs):

        self.parent = parent
        self.name = name
        self.col_date = col_date
        self.col_recipient = col_recipient
        self.col_description = col_description
        self.col_value = col_value
        self.import_since = import_since
        self.config = {
            nn.seperator: seperator,
            nn.thousands: thousands,
            nn.decimal: decimal,
            nn.dayfirst: dayfirst,
            nn.skiprows: skiprows,
            nn.encoding: encoding
        }
        self.available_columns = []
        self.drop_duplicates = drop_duplicates
        logger.debug("created new importer: "+str(self))

    def __str__(self):
        return str(self.to_dict()) + "\n available columns: " + str(self.available_columns)

    def __repr__(self):
        return self.__str__()

    def to_dict(self):
        return {nn.name: self.name,
                nn.col_date: self.col_date,
                nn.col_recipient: self.col_recipient,
                nn.col_description: self.col_description,
                nn.col_value: self.col_value,
                **self.config}

    def save(self):
        if self.name not in self.parent:
            self.parent.add(**self.to_dict())
        self.parent.save()

    @property
    def seperator(self):
        if nn.seperator in self.config:
            return self.config[nn.seperator]

    @property
    def decimal(self):
        if nn.decimal in self.config:
            return self.config[nn.decimal]

    @property
    def thousands(self):
        if nn.thousands in self.config:
            return self.config[nn.thousands]

    @property
    def skiprows(self):
        if nn.skiprows in self.config:
            return self.config[nn.skiprows]

    @property
    def dayfirst(self):
        if nn.dayfirst in self.config:
            return self.config[nn.dayfirst]

    @staticmethod
    def determine_encoding(config, filepath):
        # TODO better way to determine encoding?!
        encodings = ["utf-8", "latin-1"]
        n_char_max = 0
        for enc in encodings:
            try:
                with open(filepath, 'r', encoding=enc) as f:
                    n_char = 0
                    for line in f:
                        n_char += len(line)
                    if n_char > n_char_max:
                        config[nn.encoding] = enc
                        n_char_max = n_char
            except Exception:
                pass
        return config

    @staticmethod
    def determine_seperator(config, filepath):
        seps = [";", ","]
        n_sep_best = 0
        for sep in seps:
            nsep = []
            with open(filepath, 'r', encoding=config[nn.encoding]) as f:
                for line in f:
                    nsep += [line.count(sep)]
            sep_media_count = np.median(nsep)
            if sep_media_count > n_sep_best:
                n_sep_best = sep_media_count
                config[nn.seperator] = sep
        return config

    @staticmethod
    def determine_n_header_lines(config, filepath):
        nsep = []
        with open(filepath, 'r', encoding=config[nn.encoding]) as f:
            for line in f:
                nsep += [line.count(config[nn.seperator])]
        nsep = np.median(nsep)
        i_header = 0
        with open(filepath, 'r', encoding=config[nn.encoding]) as f:
            for i, line in enumerate(f):
                if line.count(config[nn.seperator]) != nsep:
                    i_header = i + 1
        config[nn.skiprows] = i_header
        return config

    @staticmethod
    def determine_decimal(config, filepath):
        # either '.' or ','
        if config[nn.seperator] == ',':
            config[nn.decimal] = '.'
            config[nn.thousands] = ''
            return config
        n_more_comma = 0
        with open(filepath, 'r', encoding=config[nn.encoding]) as f:
            for i, line in enumerate(f):
                if i < config[nn.skiprows]:
                    continue
                col_entries = line.split(config[nn.seperator])
                for e in col_entries:
                    if len(e) > 12:
                        continue
                    i_point = e.rfind(".")
                    i_comma = e.rfind(",")
                    if i_point < 0 or i_comma < 0:
                        continue
                    if i_point < i_comma:
                        n_more_comma += 1
                    else:
                        n_more_comma -= 1
        logger.debug(f"determine decimal: n_more_comma: {n_more_comma}")
        if n_more_comma > 0:
            config[nn.decimal] = ','
            config[nn.thousands] = '.'
        else:
            config[nn.decimal] = '.'
            config[nn.thousands] = ','
        return config

    @staticmethod
    def determine_available_columns(config, filepath):
        available_columns = []
        with open(filepath, 'r', encoding=config[nn.encoding]) as f:
            for i, line in enumerate(f):
                if i == config[nn.skiprows]:
                    line = line.replace("\n", "")
                    available_columns = line.split(config[nn.seperator])
                    break
        cleaned_columns = []
        for col in available_columns:
            if len(col) < 1:
                continue
            if col[0] == '"' or col[0] == "'":
                col = col[1:]
            if col[-1] == '"' or col[-1] == "'":
                col = col[:-1]
            cleaned_columns += [col]
        return cleaned_columns

    def determine_and_set_config(self, filepath, config=None):
        logger.debug(f"determining config additional to {config}")
        if config is None:
            config = {}

        if nn.encoding not in config:
            config = self.determine_encoding(config=config, filepath=filepath)
        self.config[nn.encoding] = config[nn.encoding]

        if nn.seperator not in config:
            config = self.determine_seperator(config=config, filepath=filepath)
        self.config[nn.seperator] = config[nn.seperator]

        if nn.skiprows not in config:
            config = self.determine_n_header_lines(
                config=config, filepath=filepath)
        self.config[nn.skiprows] = config[nn.skiprows]

        if nn.decimal not in config:
            config = self.determine_decimal(config=config, filepath=filepath)
        self.config[nn.decimal] = config[nn.decimal]
        self.config[nn.thousands] = config[nn.thousands]

        logger.debug(f"config determined: {config}")
        self.available_columns = self.determine_available_columns(
            config=self.config, filepath=filepath)
        logger.debug(f"available columns determined: {self.available_columns}")

    def load_df(self, filepath, account=None):
        logger.info("loading "+str(filepath))
        self.available_columns = self.determine_available_columns(
            config=self.config, filepath=filepath)

        # adjust config for read_csv method from pandas
        # if not parsing dates at the very first step bad things may happen?!
        load_config = self.config.copy()
        if self.col_date != '' and self.col_date in self.available_columns:
            load_config["parse_dates"] = [self.col_date]
        # read csv crash with certain >thousands< values
        if nn.thousands in load_config:
            if load_config[nn.thousands] in ["", load_config[nn.seperator], load_config[nn.decimal]]:
                del load_config[nn.thousands]
        # read csv from pandas uses >sep< not >seperator<
        load_config["sep"] = load_config[nn.seperator]
        del load_config[nn.seperator]

        df_load = None
        try:
            df_load = pd.read_csv(filepath, **load_config)
            if self.col_date in df_load.columns:
                date_config = dict()
                if "dayfirst" in load_config.keys():
                    date_config["dayfirst"] = load_config["dayfirst"]
                if "yearfirst" in load_config.keys():
                    date_config["yearfirst"] = load_config["yearfirst"]
                df_load[self.col_date] = pd.to_datetime(
                    df_load[self.col_date], **date_config)
        except ValueError as e:
            logger.error(f"Error in pd.read_csv(): {e}")
        if df_load is None:
            return
        logger.debug(f"loaded df: \n {df_load.head()}")

        # postprocessing
        df_dict = {}
        if self.col_date in df_load.columns:
            df_dict[nn.date] = df_load[self.col_date]
        if self.col_recipient in df_load.columns:
            df_dict[nn.recipient] = df_load[self.col_recipient].fillna("")
        if self.col_description in df_load.columns:
            df_dict[nn.description] = df_load[self.col_description].fillna("")
        if self.col_value in df_load.columns:
            try:
                df_dict[nn.value] = df_load[self.col_value].astype(float)
            except Exception as e:
                logger.error(e)
                df_dict[nn.value] = [np.nan] * len(df_load)

        df = pd.DataFrame(df_dict)
        df[nn.tag] = ""
        df[nn.tagger_name] = ""
        df[nn.transaction_id] = df.apply(lambda x: str(uuid.uuid4()), axis=1)

        if len(df) < 1:
            logger.debug("after postprocessing df empty")
            return df

        if nn.date in df and isinstance(df[nn.date].values[0], np.datetime64):
            min_date = df[nn.date].min()
            if self.import_since is None or self.import_since < min_date:
                self.import_since = df[nn.date].min()
                logger.debug("Based on data set import_since to "
                             f"{self.import_since}")
            else:
                df = df[df[nn.date] >= self.import_since]

        for col in [nn.date, nn.recipient, nn.description, nn.value]:
            if col not in df:
                logger.debug(f"{col} not in df")
                return df
        logger.debug(f"a 'complete' df loaded \n {df.head()}")

        # if in insert multiple entries, add (1), (2), ... to description
        # first add (2), if there are really more than one, than replace (2) by (i)
        duplicate_columns = [nn.date, nn.recipient, nn.description]
        df.loc[~df.index.isin(df.drop_duplicates().index),
               nn.description] += " (2)"
        i = 2
        while len(df.loc[~df.index.isin(df.drop_duplicates(subset=duplicate_columns).index), nn.description]) > 0:
            leni = len(str(i))
            i += 1
            mask = ~df.index.isin(df.drop_duplicates(
                subset=duplicate_columns).index)
            df.loc[mask, nn.description] = df.loc[mask,
                                                  nn.description].str.slice(stop=-(3 + leni)) + f" ({i})"

        # drop entries which are already present in account
        if self.drop_duplicates and account is not None:
            logger.info("removing duplicates")
            dfu = df.merge(account.df, on=duplicate_columns,
                           how="left", indicator=True, suffixes=('', '_y'))
            dfu = dfu.query("_merge == 'left_only'").reset_index(drop=True)
            df = dfu[[nn.transaction_id, nn.date,
                      nn.recipient, nn.description, nn.value]]

        return df
