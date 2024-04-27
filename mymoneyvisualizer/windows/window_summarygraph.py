# -*- coding: utf-8 -*-

import logging

import numpy as np
import pandas as pd

from PyQt6.QtWidgets import QMainWindow, QPushButton
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QMainWindow, QWidget

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.select_exclude_tagger import ExcludeTaggerSelectComboBox
from mymoneyvisualizer.windows.widgets.assign_tag_category import AssignTagCategoryWidget
from mymoneyvisualizer.windows.widgets.sumamry_plot import SummaryPlotWidget


logger = logging.getLogger(__name__)


class SummaryGraphWidget(QWidget):
    def __init__(self, parent, main):
        super(SummaryGraphWidget, self).__init__(parent)
        self.main = main
        self.parent = parent

        self.layout = QHBoxLayout(self)

        self.assign_tagcategories = AssignTagCategoryWidget(
            parent=self, main=main)
        self.layout.addWidget(self.assign_tagcategories)

        vlayout = QVBoxLayout(self)
        self.plot_basic = SummaryPlotWidget(self, main=main, category=nn.basic)
        vlayout.addWidget(self.plot_basic)
        self.plot_optional = SummaryPlotWidget(
            self, main=main, category=nn.optional)
        vlayout.addWidget(self.plot_optional)

        self.layout.addLayout(vlayout, 100)


class WindowSummaryGraph(QMainWindow):
    def __init__(self, parent, config):
        super(WindowSummaryGraph, self).__init__(parent)
        self.config = config
        self.update_callbacks = []
        self.updateing = True

        self.df_summary = None
        self.df_summary_income = None
        self.budgets = {nn.basic: 0.5,
                        nn.optional: 0.3
                        }

        super().__init__()
        logger.debug("starting main window")

        self.title = 'My Money Visualiser'
        self.left = 100
        self.top = 100

        self.width = 1200
        self.height = 1000
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        layout = QVBoxLayout()

        # Navigation Bar
        hlayout = QHBoxLayout()
        self.button = QPushButton('Start', self)
        self.button.setFixedHeight(30)
        self.button.setFixedWidth(130)
        hlayout.addWidget(self.button)
        self.multi_select = ExcludeTaggerSelectComboBox(self, main=self)
        hlayout.addWidget(self.multi_select)
        layout.addLayout(hlayout)

        # graph
        self.summary_graph = SummaryGraphWidget(parent=self, main=self)
        layout.addWidget(self.summary_graph)

        # Window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        self.run_update_callbacks()

    @staticmethod
    def get_base_tag(tag):
        tag = str(tag)
        tags = tag.split(".")
        tag_out = tags[0]
        return tag_out

    def add_update_callback(self, func):
        self.update_callbacks += [func]

    def run_update_callbacks(self):
        self.updateing = True
        self.get_data()
        for func in self.update_callbacks:
            func()
        self.updateing = False

    def set_excluded_tags(self, tags):
        self.config.settings[nn.exclude_tags] = list(tags)
        self.config.save_settings()
        self.run_update_callbacks()

    def update_category_and_sort(self, new_sorted_tags):
        self.config.tag_categories.update_category_and_sort(
            new_sorted_tags=new_sorted_tags)
        self.run_update_callbacks()

    def update_budget(self, category, budget):
        self.budgets[category] = budget
        self.run_update_callbacks()

    def get_data(self):

        dfs = []
        account_names = []
        for acc in self.config.accounts.get():
            account_names += [acc.name]
            df = acc.df
            if len(df) < 1:
                continue
            dfs += [df]

        if len(dfs) < 1:
            return
        df = pd.concat(dfs, sort=False)
        df = df.loc[~(df[nn.tag].isin(account_names)), :]

        if nn.exclude_tags in self.config.settings and len(self.config.settings[nn.exclude_tags]) > 0:
            df = df.loc[~(df[nn.tag].isin(
                set(self.config.settings[nn.exclude_tags]))), :]

        if len(df) < 1:
            return

        df[nn.tag] = df[nn.tag].apply(self.get_base_tag)
        df = df[[nn.date, nn.value, nn.tag]]

        # Fill holes
        temp_dates = pd.date_range(
            df[nn.date].min(), df[nn.date].max(), freq='1ME')
        temp_values = pd.DataFrame({nn.date: temp_dates,
                                    nn.value: [0]*len(temp_dates),
                                    nn.tag: [" "]*len(temp_dates),
                                    })
        df = pd.concat([df, temp_values], sort=False)

        # create
        dfg = df.groupby([nn.tag, pd.Grouper(freq="3ME", key=nn.date)]).agg(
            {nn.value: "sum"}).reset_index()
        dfp = dfg.pivot(index=nn.date, columns=nn.tag,
                        values=["value"]).fillna(0.)
        dfp.columns = dfp.columns.get_level_values(1)

        # assume first and last row are not complete
        dfp = dfp[1:-1]

        # Add missing in tag categories
        for col in dfp.columns:
            if col not in self.config.tag_categories:
                self.config.tag_categories.add(name=col, category="basic")

        self.df_summary = dfp

        # TODO calc from category, make baseline 0 if no income is selected
        self.df_summary_income = np.zeros(len(dfp))
        for tag_cat in self.config.tag_categories.get():
            if tag_cat.category != nn.income:
                continue
            if tag_cat.name not in dfp.columns:
                continue
            self.df_summary_income += dfp[tag_cat.name]
