import os
import logging
import yaml
from yaml.loader import SafeLoader
import zipfile

from mymoneyvisualizer.taggers import Taggers
from mymoneyvisualizer.importers import Importers
from mymoneyvisualizer.accounts import Accounts
from mymoneyvisualizer.tag_categories import TagCategories
from mymoneyvisualizer.constants import DEFAULT_SETTINGS

logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/configuration.yaml"


def overwrite_dict(old_dict, new_dict):
    for key, value in new_dict.items():
        if isinstance(value, dict):
            value = overwrite_dict(old_dict=old_dict[key], new_dict=value)
        old_dict[key] = value
    return old_dict


class Configuration:
    def __init__(self, dir_path):
        self.dir_path = dir_path
        self.settings = dict()
        self.update_callbacks = list()

        self.load_settings()
        self.importers = Importers(dir_path=dir_path)
        self.taggers = Taggers(dir_path=dir_path)
        self.tag_categories = TagCategories(dir_path=dir_path)
        self.accounts = Accounts(dir_path=dir_path, taggers=self.taggers)

        # add action and callbacks
        self.accounts.tag_dfs()
        self.taggers.add_update_callback(self.accounts.tag_dfs)

    def save_settings(self):
        settings_filepath = self.dir_path+CONTAINER_FILEPATH
        if not os.path.exists(self.dir_path):
            os.mkdir(self.dir_path)

        with open(settings_filepath, 'w') as outfile:
            yaml.dump(self.settings, outfile, default_flow_style=False)

    def load_settings(self):
        self.settings = DEFAULT_SETTINGS

        settings_filepath = self.dir_path+CONTAINER_FILEPATH
        if not os.path.isfile(settings_filepath):
            return

        loaded_settings = yaml.load(
            open(settings_filepath).read(), Loader=SafeLoader)

        self.settings = overwrite_dict(
            old_dict=self.settings, new_dict=loaded_settings)


# TODO refactor store and reading zip to "backup" or similar


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
            self.save_file_by_name(
                zipf=zipf, filepath=self.importers.container_filepath)
            self.taggers.save()
            self.save_file_by_name(
                zipf=zipf, filepath=self.taggers.container_filepath)
            self.tag_categories.save()
            self.save_file_by_name(
                zipf=zipf, filepath=self.tag_categories.container_filepath)
            for acc in self.accounts.get():
                acc.save()
                self.save_file_by_name(
                    zipf=zipf, filepath=acc.db_filepath, folder="accounts/")
            self.save_file_by_name(
                zipf=zipf, filepath=self.accounts.container_filepath)

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
