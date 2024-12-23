# -*- coding: utf-8 -*-
import os
import pathlib
import logging
import warnings
import numpy as np
import pandas as pd
import uuid

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer

logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/accounts.yaml"
DEFAULT_DB_FILEPATH = "/accounts/"


class Accounts(OrderedDataContainer):
    def __init__(self, dir_path, taggers):
        logger.debug("creating Accounts")
        self.dir_path = dir_path
        self.taggers = taggers
        super().__init__(container_filepath=dir_path+CONTAINER_FILEPATH)

    def add(self, name=None, db_filepath=None, **kwargs):
        logger.debug("add account "+str(name)+" "+str(db_filepath))
        if name is None:
            # get new free account and filename
            i = 1
            name = "new account "
            while name + str(i) in self:
                i += 1
            name = name + str(i)
            db_filepath = (self.dir_path +
                           DEFAULT_DB_FILEPATH + name + ".csv").replace(" ", "_")

        if name in self:
            logger.warning(name + " already loaded, skipping....")
            return

        # create new account
        new_acc = Account(parent=self, name=name,
                          db_filepath=db_filepath, **kwargs)
        return super().add(name=name, obj=new_acc)

    def delete(self, name):
        logger.debug("trying to delete account "+str(name))
        if name in self:
            self.get_by_name(name=name).delete()
            super().delete(name)
            logger.debug("deleted "+str(name))

    def get_unique_tags(self):
        tag_set = set()
        for account in self.values():
            tag_set.update(account.df[nn.tag].unique())
        tags = sorted(list(tag_set))
        return tags

    def get_unique_base_tags(self):
        tags = self.get_unique_tags()
        base_tags = [t.split(".")[0] for t in tags]
        base_tags = sorted(list(set(base_tags)))
        return base_tags

    def get_base_tag_df(self, base_tag):
        dfs = []
        for account in self.values():
            if base_tag != "":
                mask = account.df[nn.tag].str.startswith(base_tag)
                dftmp = account.df[mask]
            else:
                dftmp = account.df
            if len(dftmp) < 1:
                continue

            with warnings.catch_warnings(action="ignore"):
                dftmp.loc[:, nn.account] = account.name
            dfs += [dftmp]
        if len(dfs) > 0:
            return pd.concat(dfs, sort=False)
        return None

    # TODO rename to get_tagger_df
    def get_tagger_df(self, tagger):
        logger.debug("get filtered df for "+tagger.name)

        dfs = []
        for account in self.get():
            logger.debug(f"filtering account {account.name}")
            tmpdf = account.get_tagger_df(tagger)
            tmpdf[nn.account] = account.name
            dfs += [tmpdf]

        if len(dfs) > 0:
            df_result = pd.concat(dfs, sort=False)
            df_result = df_result.sort_values(nn.date)
            df_result = df_result.reset_index(drop=True)
        else:
            columns = [nn.account, nn.date, nn.recipient,
                       nn.description, nn.value, nn.tag, nn.tagger_name]
            df_result = pd.DataFrame({f: [] for f in columns})

        logger.debug(f"result: {df_result.head()}")
        return df_result

    def get_combined_account_df(self, account_name):
        """
        get also other transactions lilnked to this account
        :param account_name:
        :return:
        """
        logger.debug("get_combined_df for "+account_name)
        dfs = []
        for acc in self.get():
            if len(acc) < 1:
                continue
            if acc.name == account_name:
                dfs += [acc.df]
                continue
            df = acc.df.loc[acc.df[nn.tag] == account_name, :]
            df.loc[:, nn.value] *= -1.
            dfs += [df]
        if len(dfs) < 1:
            return
        return pd.concat(dfs, sort=False).sort_values(nn.date, ascending=False).reset_index(drop=True)

    def tag_dfs(self):
        logger.debug("tagging dfs")
        if self.taggers is None:
            logger.debug("taggers not set, skip tagging")
            return
        for account in self:
            account.tag_df(self.taggers)
        logger.debug("dfs tagged")
        self.run_update_callbacks()

    def get_summary_df(self, date_from, date_upto):
        dfs = []
        for acc in self:
            df = acc.df
            df = df[(df[nn.date] >= date_from) & (df[nn.date] < date_upto)]
            if len(df) < 1:
                continue
            dfs += [df]
        if len(dfs) < 1:
            return
        df = pd.concat(dfs)
        return df


class Account(object):
    def __init__(self, parent, name, db_filepath):
        self.parent = parent
        self.name = str(name)
        if db_filepath is None and self.parent is not None:
            db_filepath = (self.parent.dir_path +
                           DEFAULT_DB_FILEPATH + name + ".csv").replace(" ", "_")
        self.db_filepath = db_filepath
        self.df = self.load()
        logger.info("created account: " + self.name +
                    " entries: " + str(len(self.df)))

    def __str__(self):
        return f"Account: {self.name}, DB: {self.db_filepath} ({len(self)})\n {self.df.head()}"

    def __repr__(self):
        return self.__str__()

    def __len__(self):
        return len(self.df)

    def load(self):
        if self.db_filepath is not None and os.path.isfile(self.db_filepath):
            self.df = pd.read_csv(self.db_filepath)
            self.df[nn.date] = pd.to_datetime(self.df[nn.date])
            self.df[nn.recipient] = self.df[nn.recipient].fillna("").astype(str)
            self.df[nn.description] = self.df[nn.description].fillna("").astype(str)
            self.df[nn.tag] = self.df[nn.tag].fillna("").astype(str)
            if nn.transaction_id not in self.df.columns:
                self.df[nn.transaction_id] = self.df.apply(lambda x: str(uuid.uuid4()), axis=1)
            mask_noid = self.df[nn.transaction_id].isnull()
            self.df.loc[mask_noid, nn.transaction_id] = self.df.loc[mask_noid, nn.transaction_id].apply(lambda x: str(uuid.uuid4()))
        else:
            self.df = pd.DataFrame({nn.transaction_id: [], nn.date: [], nn.recipient: [], nn.description: [], nn.value: [], nn.tag: [],
                                    nn.tagger_name: []})
        return self.df

    def save_db(self):
        # make sure folder exists
        filepath = os.path.dirname(self.db_filepath) + \
            "/" + self.name.replace(" ", "_") + ".csv"
        dir_path = os.path.dirname(filepath)
        if not os.path.exists(dir_path):
            pathlib.Path(dir_path).mkdir(parents=True, exist_ok=True)
        # rename csv file according to account name
        if os.path.normpath(filepath) != os.path.normpath(self.db_filepath):
            if os.path.isfile(self.db_filepath):
                os.rename(os.path.normpath(self.db_filepath),
                          os.path.normpath(filepath))
            self.db_filepath = filepath

        self.df.to_csv(self.db_filepath, index=False)
        logger.debug(
            f"saved {self.name} to {self.db_filepath}, in total entries: {len(self.df)}")

    def save(self, parent=None):
        self.save_db()
        if self.parent is None and parent is not None:
            self.parent = parent
            if self.name not in self.parent:
                self.parent.add(**self.to_dict())
            else:
                logger.warning(
                    "account with {self.name} already added, skipping....")

        if self.parent is not None:
            self.parent.save()

    def to_dict(self):
        return {nn.name: self.name,
                nn.db_filepath: self.db_filepath,
                }

    def update(self, df):
        if len(self.df) > 0:
            self.df = pd.concat([self.df, df], sort=False)
        else:
            self.df = df
        self.df = self.df.sort_values(
            [nn.date], ascending=False).reset_index(drop=True)
        logger.info(
            f"account {self.name} updated with {len(self.df)} new entries")
        self.save()

    def delete(self):
        if os.path.isfile(self.db_filepath):
            os.remove(self.db_filepath)
            logger.debug("deleted file "+str(self.db_filepath))

    def tag_df(self, taggers):
        self.df = taggers.tag_df(self.df)
        return self.df

    def get_tagger_df(self, tagger):
        df = self.df.copy()
        df = tagger.tag_df(df)  # TODO need to tag again?! tagger_collision
        logger.debug(f"df tagged: \n {df.head()}")
        mask = df[nn.tagger_name] == tagger.name
        if tagger.transaction_id is not None:
            mask |= df[nn.transaction_id] == tagger.transaction_id
        return df.loc[mask]

    def get_entries(self, date, recipient, description):
        mask = self.df[nn.date] == date
        return self.df[mask].query(f"{nn.recipient} == '{recipient}' and {nn.description} == '{description}'")

    def add_entry(self, date, recipient, description, value):
        newdf = pd.DataFrame({
            nn.transaction_id: [str(uuid.uuid4())],
            nn.date: [date],
            nn.description: [str(description)],
            nn.recipient: [str(recipient)],
            nn.value: [value],
            nn.tag: [""],
            nn.tagger_name: [""]
        })
        self.update(newdf)

    def get_unique(self, column):
        return self.df[column].unique()

    def tag_transaction_id(self, transaction_id, tag, tagger_name):
        mask = self.df[nn.transaction_id] == transaction_id
        if np.any(mask):
            self.df.loc[mask, nn.tag] = tag
            self.df.loc[mask, nn.tagger_name] = tagger_name
            self.save()
