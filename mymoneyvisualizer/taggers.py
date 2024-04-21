# -*- coding: utf-8 -*-
import logging

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer


logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/taggers.yaml"

# TODO do we need a name for a tagger? tag is enough?!


class Taggers(OrderedDataContainer):
    def __init__(self, config):
        self.config = config
        super().__init__(container_filepath=self.config.dir_path+CONTAINER_FILEPATH)
        logger.debug("started taggers")

    def add(self, name=None, regex_recipient="", regex_description="", tag="", **kwargs):
        name = self.get_free_name(name)
        new_tagger = Tagger(parent=self, name=name, regex_recipient=regex_recipient,
                            regex_description=regex_description, tag=tag)
        logger.debug("added new tagger "+str(name))
        return super().add(name=name, obj=new_tagger)

    def tag_df(self, df):
        logger.debug("tagging df")
        if df is None or len(df) < 1:
            return df
        df.loc[:, nn.tag] = " "  # FIXME an empty string is converted to NaT??!!
        df.loc[:, nn.tagger_name] = ""
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

    def get_free_name(self, name=None):
        if name is None:
            name = "new_tagger"
        if name not in self:
            return name
        i = 1
        while f"{name}_{i}" in self:
            i += 1
        return f"{name}_{i}"

    def get_or_create(self, name, regex_recipient, regex_description, tag):
        logger.debug("get or create name: " + str(name))
        if name == "":
            name = self.get_free_name()
        tagger = self.get_by_name(name=name)
        if tagger is None:
            tagger = Tagger(parent=None, name=name, regex_recipient=regex_recipient, regex_description=regex_description,
                            tag=tag)
        return tagger


class Tagger:
    def __init__(self, parent, name, regex_recipient, regex_description, tag):
        self.parent = parent
        self.name = name
        self.regex_recipient = regex_recipient
        self.regex_description = regex_description
        self.tag = tag
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

    def save(self, parent=None):
        logger.debug("saving tagger: "+str(self.name))
        if self.parent is None and parent is not None:
            self.parent = parent
            self.parent.add(**self.to_dict())
        if self.parent is not None:
            self.parent.save()

    def tag_df(self, df):
        mask1 = None
        mask2 = None

        if self.regex_recipient != "":
            try:
                mask1 = df[nn.recipient].str.contains(pat=self.regex_recipient, na=False, regex=True)
            except Exception as e:
                logger.error(f"could not handle: {self.regex_recipient}")
                logger.error(e)

        if self.regex_description != "":
            try:
                mask2 = df[nn.description].str.contains(pat=self.regex_description, na=False, regex=True)
            except Exception as e:
                logger.error(f"could not handle: {self.regex_description}")
                logger.error(e)

        if mask1 is None and mask2 is None:
            df.loc[:, nn.tag] = self.tag
            df.loc[:, nn.tagger_name] = self.name
            return df
        
        if mask1 is None:
            mask = mask2
        elif mask2 is None:
            mask = mask1
        else:
            mask = mask1 & mask2

        df.loc[mask, nn.tag] = self.tag
        df.loc[mask, nn.tagger_name] = self.name

        return df
