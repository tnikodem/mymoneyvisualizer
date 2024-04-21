# -*- coding: utf-8 -*-
import logging
from collections import OrderedDict

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.utils.datacontainer import OrderedDataContainer


logger = logging.getLogger(__name__)

CONTAINER_FILEPATH = "/tag_categories.yaml"

# TODO do we need a name for a tagger? tag is enough?!


class TagCategories(OrderedDataContainer):
    def __init__(self, config):
        self.config = config
        super().__init__(container_filepath=self.config.dir_path+CONTAINER_FILEPATH)
        logger.debug("started taggers")

    def add(self, name, category):
        new_tag_category = TagCategory(
            parent=self, name=name, category=category)
        logger.debug("added new tag catgegory: "+str(name))
        return super().add(name=name, obj=new_tag_category)

    @staticmethod
    def match_orders(old_sorted_tag_names, new_sorted_tag_names):
        new_order = []
        i_old = 0
        i_new = 0
        while i_old < len(old_sorted_tag_names) and i_new < len(new_sorted_tag_names):
            tag_name_old = old_sorted_tag_names[i_old]
            tag_name_new = new_sorted_tag_names[i_new]
            if tag_name_old == tag_name_new:
                if tag_name_new not in new_order:
                    new_order += [tag_name_new]
                i_old += 1
                i_new += 1
            elif tag_name_old not in new_sorted_tag_names:
                new_order += [tag_name_old]
                i_old += 1
            else:
                if tag_name_new not in new_order:
                    new_order += [tag_name_new]
                i_new += 1
        return new_order

    def update_category_and_sort(self, new_sorted_tags):
        new_sorted_tag_names = []
        for category, tag_names in new_sorted_tags.items():
            new_sorted_tag_names += tag_names
            for name in tag_names:
                tag_cat = self.get_by_name(name)
                if tag_cat.category != category:
                    tag_cat.category = category

        old_sorted_tag_names = []
        for tag_cat in self:
            old_sorted_tag_names += [tag_cat.name]

        new_order = self.match_orders(old_sorted_tag_names=old_sorted_tag_names,
                                      new_sorted_tag_names=new_sorted_tag_names)

        new_data_objects = OrderedDict()
        for tag_cat_name in new_order:
            tag_cat = self.get_by_name(tag_cat_name)
            assert tag_cat is not None
            new_data_objects[tag_cat_name] = tag_cat
        self.data_objects = new_data_objects

        self.save()


class TagCategory:
    def __init__(self, parent, name, category):
        self.parent = parent
        self.name = name
        self.category = category

    def __str__(self):
        return f"TagCategory: {self.name}, category: {self.category}"

    def __repr__(self):
        return self.__str__()

    def to_dict(self):
        return {nn.name: self.name,
                nn.category: self.category,
                }

    def save(self, parent=None):
        logger.debug("saving tagger: "+str(self.name))
        if self.parent is None and parent is not None:
            self.parent = parent
            self.parent.add(**self.to_dict())
        if self.parent is not None:
            self.parent.save()
