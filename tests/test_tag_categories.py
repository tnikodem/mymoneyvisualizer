# -*- coding: utf-8 -*-

import datetime
import os
import pandas as pd

from mymoneyvisualizer.naming import Naming as Nn


def test_category_matcher():
    new_sorted_tag_names = [' ', 'food', 'amazon', 'bank', 'cash', 'hobby', 'home', 'mobility', 'person', 'savings', 'transfer', 'work']
    old_sorted_tag_names = [' ', 'amazon', 'bank', 'cash', 'food', 'hobby', 'home', 'mobility', 'person', 'savings', 'transfer', 'work']

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


    assert new_order == new_sorted_tag_names

