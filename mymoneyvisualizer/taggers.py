# -*- coding: utf-8 -*-
import logging

import re
import pandas as pd
from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer


logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/taggers.yaml"

ONE_TIME_TAG_TAGGER_NAME = "one_time_tag"


class Taggers(OrderedDataContainer):
    def __init__(self, dir_path):
        super().__init__(container_filepath=dir_path+CONTAINER_FILEPATH)
        logger.debug("started taggers")

    def add(self, name=None, regex_recipient="", regex_description="", tag="", **kwargs):
        name = self.get_free_tagger_name(name)
        new_tagger = Tagger(parent=self, name=name, regex_recipient=regex_recipient,
                            regex_description=regex_description, tag=tag)
        logger.debug("added new tagger "+str(name))
        return super().add(name=name, obj=new_tagger)

    def tag_df(self, df):
        logger.debug("tagging df")
        if df is None or len(df) < 1:
            return df
        mask = df[nn.tagger_name] != ONE_TIME_TAG_TAGGER_NAME
        # There could be tags overwriting other tags. make sure that result is always the same by starting from a clean state
        # FIXME an empty string is converted to NaT??!!
        df.loc[mask, nn.tag] = " "
        df.loc[mask, nn.tagger_name] = ""
        for tagger in self.get():
            df = tagger.tag_df(df)
        return df

    def get_unique_tags(self):
        tag_set = set()
        for f in self.get():
            tag_set.add(f.tag)
        tags = sorted(list(tag_set))
        logger.debug(f"get unique tags: {tags}")
        return tags

    def get_free_tagger_name(self, name=None):
        if name is None:
            name = "new_tagger"
        if name not in self and name != ONE_TIME_TAG_TAGGER_NAME:
            return name
        i = 1
        while f"{name}_{i}" in self:
            i += 1
        return f"{name}_{i}"

    def get_or_create(self, name, regex_recipient, regex_description, tag, transaction_id):
        logger.debug("get or create name: " + str(name))
        if name == "":
            name = self.get_free_tagger_name()
        tagger = self.get_by_name(name=name)
        if tagger is None:
            tagger = Tagger(parent=self, name=name, regex_recipient=regex_recipient, regex_description=regex_description,
                            tag=tag, transaction_id=transaction_id)
        tagger.transaction_id = transaction_id
        return tagger

    @staticmethod
    def save_one_time_tag(tag, transaction_id, accounts):
        for account in accounts:
            account.tag_transaction_id(
                transaction_id=transaction_id, tag=tag, tagger_name=ONE_TIME_TAG_TAGGER_NAME)


class Tagger:
    def __init__(self, parent, name, regex_recipient, regex_description, tag, transaction_id=None):
        self.parent = parent
        self.name = name
        self.regex_recipient = regex_recipient
        self.regex_description = regex_description
        self.tag = tag
        self.transaction_id = transaction_id
        logger.debug("created tagger: "+str(self))

    def __str__(self):
        return f"Tagger: {self.name}, tag: {self.tag}"

    def __repr__(self):
        return self.__str__()

    def to_dict(self):
        return {nn.name: self.name,
                nn.regex_recipient: self.regex_recipient,
                nn.regex_description: self.regex_description,
                nn.tag: self.tag,
                }

    def save(self):
        logger.debug("saving tagger: "+str(self.name))
        if self.name not in self.parent:
            self.parent.add(**self.to_dict())
        self.parent.save()

    def recipient_matches(self, test_string):
        if self.regex_recipient == "":
            return True
        try:
            pattern = re.compile(self.regex_recipient)
            return bool(re.match(pattern, test_string))
        except Exception as e:
            logger.error(f"could not handle: {self.regex_recipient}")
            logger.error(e)
            return False

    def description_matches(self, test_string):
        if self.regex_description == "":
            return True
        try:
            pattern = re.compile(self.regex_description)
            return bool(re.match(pattern, test_string))
        except Exception as e:
            logger.error(f"could not handle: {self.regex_description}")
            logger.error(e)
            return False

    def mask_recipient(self, df):
        mask = pd.Series(True, index=df.index)
        if self.regex_recipient != "":
            try:
                mask = df[nn.recipient].str.contains(
                    pat=self.regex_recipient, na=False, regex=True)
            except Exception as e:
                logger.error(f"could not handle: {self.regex_recipient}")
                logger.error(e)
                mask = None
        return mask

    def mask_description(self, df):
        mask = pd.Series(True, index=df.index)
        if self.regex_description != "":
            try:
                mask = df[nn.description].str.contains(
                    pat=self.regex_description, na=False, regex=True)
            except Exception as e:
                logger.error(f"could not handle: {self.regex_description}")
                logger.error(e)
                mask = None
        return mask

    def tag_df(self, df):
        mask = self.mask_recipient(df)
        mask &= self.mask_description(df)
        mask &= df[nn.tagger_name] != ONE_TIME_TAG_TAGGER_NAME
        if mask is None:
            return df

        df.loc[mask, nn.tag] = self.tag
        df.loc[mask, nn.tagger_name] = self.name

        return df
