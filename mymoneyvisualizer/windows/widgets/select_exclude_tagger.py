# -*- coding: utf-8 -*-

import logging

import numpy as np
import pandas as pd


import pyqtgraph as pg


from pyqt6_multiselect_combobox import MultiSelectComboBox

from PyQt6.QtWidgets import QMainWindow, QPushButton, QSizePolicy

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
import sys
from PyQt6.QtWidgets import QApplication, QMainWindow, QWidget
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QLabel, QListWidget, QAbstractItemView
from PyQt6.QtCore import Qt


from mymoneyvisualizer.naming import Naming as nn

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)


class ExcludeTaggerSelectComboBox(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.updateing = True

        self.label = QLabel("Exclude:", self)
        self.multi_select = MultiSelectComboBox(self)

        self.layout = QHBoxLayout(self)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.multi_select)
        self.setLayout(self.layout)

        # add actions
        self.main.config.taggers.add_update_callback(self.update_tag_list)
        # FIXME only gets triggered if there are visible changes! Functionality missing currently in widget!
        self.multi_select.currentTextChanged.connect(self.update_excluded_tags)

        self.update_tag_list()

    def update_excluded_tags(self, a):
        if not self.updateing:
            self.main.set_excluded_tags(self.multi_select.currentData())

    def update_tag_list(self):
        self.updateing = True
        unique_tags = self.main.config.taggers.get_unique_tags()
        self.multi_select.clear()

        excluded_tags = []
        if nn.exclude_tags in self.main.config.settings:
            excluded_tags = self.main.config.settings[nn.exclude_tags]

        selected_indexes = []
        for i, tag in enumerate(unique_tags):
            self.multi_select.addItem(tag, tag)
            if tag in excluded_tags:
                selected_indexes += [i]
        if len(selected_indexes) > 0:
            self.multi_select.setCurrentIndexes(selected_indexes)
        self.updateing = False
