# -*- coding: utf-8 -*-

import os
import logging
import yaml
from yaml.loader import SafeLoader
from collections import OrderedDict


logger = logging.getLogger(__name__)


class OrderedDataContainer:
    def __init__(self, container_filepath="./container_config.yaml"):
        self.container_filepath = container_filepath
        self.data_objects = OrderedDict()
        self.update_callbacks = []
        self.load()

    def __len__(self):
        return len(self.data_objects)

    def __contains__(self, item):
        return item in self.data_objects

    def __str__(self):
        return self.container_filepath + ":\n" + str(self.data_objects)

    def __repr__(self):
        return self.__str__()

    # TODO refactor to standard
    def __iter__(self):
        for v in self.data_objects.values():
            yield v

    def get(self):
        for f in self.data_objects.keys():
            yield self.data_objects[f]

    def get_by_index(self, index):
        if index <= len(self):
            for i, data in enumerate(self.get()):
                if i == index:
                    return data

    def get_by_name(self, name):
        if name in self.data_objects:
            return self.data_objects[name]

    def items(self):
        for i in self.data_objects.items():
            yield i

    def keys(self):
        for k in self.data_objects.keys():
            yield k

    def values(self):
        for v in self.data_objects.values():
            yield v

    def load(self):
        logger.debug(
            f"loading {self.__class__} from {self.container_filepath}")
        data = None
        if os.path.isfile(self.container_filepath):
            data = yaml.load(
                open(self.container_filepath).read(), Loader=SafeLoader)
        logger.debug("data loaded: " + str(data))
        if data is not None:
            self.data_objects.clear()
            for conf in data:
                logger.debug("loading obj: "+str(conf))
                self.add(**conf)
        self.run_update_callbacks()

    def save(self):
        data = []
        for o in self.get():
            data += [o.to_dict()]

        dir_path = os.path.dirname(self.container_filepath)
        if not os.path.exists(dir_path):
            os.mkdir(dir_path)

        with open(self.container_filepath, 'w') as outfile:
            yaml.dump(data, outfile, default_flow_style=False)

        # update stored names
        data_objects_new = OrderedDict()
        for o in self.get():
            data_objects_new[o.name] = o
        self.data_objects = data_objects_new

        self.run_update_callbacks()

    def add(self, name, obj):
        if name in self.data_objects:
            i = 1
            while f"{name}_{i}" in self:
                i += 1
            name = f"{name}_{i}"
            obj.name = name
        self.data_objects[name] = obj
        # Data container must be always saved seperately.No update callback after adding one element!
        return obj

    def delete(self, name):
        if name in self.data_objects:
            self.data_objects.pop(name)
        self.save()

    def add_update_callback(self, func):
        self.update_callbacks += [func]
        logger.debug(
            f"add callback {func.__module__} .{func.__name__} to {self.__class__}")

    def run_update_callbacks(self):
        logger.debug(f"running callbacks for {self.__class__}")
        for func in self.update_callbacks:
            logger.debug("run callback " + str(func.__module__) +
                         "." + str(func.__name__))
            func()
