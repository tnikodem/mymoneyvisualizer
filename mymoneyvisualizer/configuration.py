# -*- coding: utf-8 -*-
import logging
import os
import zipfile

from mymoneyvisualizer.taggers import Taggers
from mymoneyvisualizer.importers import Importers
from mymoneyvisualizer.accounts import Accounts
from mymoneyvisualizer.tag_categories import TagCategories


logger = logging.getLogger(__name__)


class Configuration:
    def __init__(self, dir_path):
        self.dir_path = dir_path
        # self.accounts = None
        # self.taggers = None
        # self.importers = None

        self.importers = Importers(config=self)
        self.taggers = Taggers(config=self)
        self.accounts = Accounts(config=self)
        self.tag_categories = TagCategories(config=self)

        # add action and callbacks
        self.accounts.tag_dfs()
        self.taggers.add_update_callback(self.accounts.tag_dfs)

    @staticmethod
    def save_file_by_name(zipf, filepath, folder=""):
        filename = os.path.basename(filepath)
        zipf.write(filename=filepath, arcname=folder+filename)

    def save(self, filepath):
        """
        save complete configuration in zip file
        :param filepath:
        :return:
        """
        with zipfile.ZipFile(filepath, 'w', zipfile.ZIP_DEFLATED) as zipf:
            self.importers.save()
            self.save_file_by_name(zipf=zipf, filepath=self.importers.container_filepath)
            self.taggers.save()
            self.save_file_by_name(zipf=zipf, filepath=self.taggers.container_filepath)
            self.tag_categories.save()
            self.save_file_by_name(zipf=zipf, filepath=self.tag_categories.container_filepath)
            for acc in self.accounts.get():
                acc.save()
                self.save_file_by_name(zipf=zipf, filepath=acc.db_filepath, folder="accounts/")
            self.save_file_by_name(zipf=zipf, filepath=self.accounts.container_filepath)

    def _load_accounts(self, myzip):
        for name in myzip.namelist():
            if "accounts" in name:
                myzip.extract(name, self.dir_path)
            self.accounts.load()

    def _load_taggers(self, myzip):
        for name in myzip.namelist():
            if "taggers.yaml" in name:
                myzip.extract(name, self.dir_path)
            self.taggers.load()

    def _load_tag_cetegories(self, myzip):
        for name in myzip.namelist():
            if "tag_categories.yaml" in name:
                myzip.extract(name, self.dir_path)
            self.tag_categories.load()        

    def _load_importers(self, myzip):
        for name in myzip.namelist():
            if "importers.yaml" in name:
                myzip.extract(name, self.dir_path)
            self.importers.load()

    def load(self, filepath):
        """
        load complete configuration from zip file
        :param filepath:
        :return:
        """
        # delete current account db files, all conf files are overwritten anyhow
        for acc in self.accounts.get():
            acc.delete()

        with zipfile.ZipFile(filepath, 'r') as myzip:
            self._load_accounts(myzip=myzip)
            self._load_taggers(myzip=myzip)
            self._load_importers(myzip=myzip)
