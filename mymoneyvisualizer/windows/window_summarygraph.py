# -*- coding: utf-8 -*-

import logging

import datetime
import numpy as np
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QMainWindow, QWidget, QLabel, QComboBox

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.select_exclude_tags import SelectExcludeTags
from mymoneyvisualizer.windows.widgets.select_average_tags import SelectAverageTags

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


class AggregationSelect(QWidget):
    def __init__(self, parent, main):
        super(AggregationSelect, self).__init__(parent)
        self.main = main
        self.layout = QHBoxLayout(self)
        self.label = QLabel("Aggregate months")
        self.label.setFixedWidth(100)
        self.layout.addWidget(self.label)

        self.combobox = QComboBox()
        self.combobox.addItem('1')
        self.combobox.addItem('2')
        self.combobox.addItem('3')
        self.combobox.addItem('6')
        self.combobox.addItem('12')
        self.combobox.setFixedWidth(40)
        self.layout.addWidget(self.combobox)

        self.update_combobox()

        # add action
        self.combobox.currentTextChanged.connect(
            self.main.update_plot_aggregation_month)

    def update_combobox(self):
        current_text = "3"
        if nn.plot_aggregation_month in self.main.config.settings:
            current_text = str(
                self.main.config.settings[nn.plot_aggregation_month])
        self.combobox.setCurrentText(current_text)


class WindowSummaryGraph(QMainWindow):
    def __init__(self, parent, config):
        super(WindowSummaryGraph, self).__init__(parent)
        self.config = config
        self.update_callbacks = []
        self.updateing = True

        self.df_summary = None
        self.df_summary_income = None
        # TODO move into config settings
        self.budgets = {nn.basic: 0.5,
                        nn.optional: 0.3
                        }

        self.statistics_numbers = {}

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
        # TODO figure out how to correctly implement multiselect
        # hlayout.addStretch(2)
        self.aggregation_select = AggregationSelect(parent=self, main=self)
        hlayout.addWidget(self.aggregation_select)

        self.select_average_tags = SelectAverageTags(self, main=self)
        hlayout.addWidget(self.select_average_tags)

        self.multi_select_excluded_tags = SelectExcludeTags(self, main=self)
        hlayout.addWidget(self.multi_select_excluded_tags)
        layout.addLayout(hlayout)

        # graph
        self.summary_graph = SummaryGraphWidget(parent=self, main=self)
        layout.addWidget(self.summary_graph)

        # Window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

        self.run_update_callbacks()

    def add_update_callback(self, func):
        self.update_callbacks += [func]

    def run_update_callbacks(self):
        self.updateing = True
        self.get_data()
        for func in self.update_callbacks:
            func()
        self.updateing = False

    def update_plot_aggregation_month(self, value):
        self.config.settings[nn.plot_aggregation_month] = int(value)
        self.config.save_settings()
        self.run_update_callbacks()

    def set_average_tags(self, tags):
        self.config.settings[nn.average_tags] = list(tags)
        self.config.save_settings()
        self.run_update_callbacks()

    def set_excluded_tags(self, tags):
        self.config.settings[nn.exclude_tags] = list(tags)
        self.config.save_settings()
        self.run_update_callbacks()

    def update_category_and_sort(self, new_sorted_tags):
        self.config.tag_categories.update_category_and_sort(
            new_sorted_tags=new_sorted_tags)
        self.run_update_callbacks()

    def update_budget_factor(self, category, budget):
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

        # TODO change "tag" to "base tag", as this is what it really is here..
        df[nn.tag] = df[nn.tag].str.split(".").str[0]
        df = df[[nn.date, nn.value, nn.tag]]

        # Fill holes
        temp_dates = pd.date_range(
            df[nn.date].min(), df[nn.date].max(), freq='1ME')
        temp_values = pd.DataFrame({nn.date: temp_dates,
                                    nn.value: [0]*len(temp_dates),
                                    nn.tag: [" "]*len(temp_dates),
                                    })
        df = pd.concat([df, temp_values], sort=False)

        # Pivot Table
        aggregate_months = self.config.settings.get(
            nn.plot_aggregation_month, 3)
        dfg = df.groupby([nn.tag, pd.Grouper(freq=f"{aggregate_months}ME", key=nn.date)]).agg(
            {nn.value: "sum"}).reset_index()
        dfp = dfg.pivot(index=nn.date, columns=nn.tag,
                        values=["value"]).fillna(0.)
        dfp.columns = dfp.columns.get_level_values(1)

        # Average columns
        if nn.average_tags in self.config.settings:
            index = (dfp.index.astype(np.int64)*1e-12).astype(int)
            for tag in self.config.settings[nn.average_tags]:
                # assume first and last entry are not complete
                center_index = index[1:-1]
                center_series = dfp[tag][1:-1]
                coef = np.polyfit(x=center_index, y=center_series, deg=1)
                poly1d_fn = np.poly1d(coef)
                values = index.map(poly1d_fn)
                mean_rel_diff = np.mean(np.abs((dfp[tag] - values) / values))
                if mean_rel_diff > 1:
                    coef = np.polyfit(x=center_index, y=center_series, deg=0)
                    poly0d_fn = np.poly1d(coef)
                    values = index.map(poly0d_fn)
                dfp[tag] = values

        # assume first row is not complete
        dfp = dfp[1:]

        # Add missing in tag categories
        for col in dfp.columns:
            if col not in self.config.tag_categories:
                self.config.tag_categories.add(name=col, category="basic")

        self.df_summary = dfp

        # get income series
        self.df_summary_income = np.zeros(len(dfp))
        for tag_cat in self.config.tag_categories.get():
            if tag_cat.category != nn.income:
                continue
            if tag_cat.name not in dfp.columns:
                continue
            self.df_summary_income += dfp[tag_cat.name]

        # calculate budget numbers
        # for the moment calculate budget for last year, make it later choosable
        budget_year = df[nn.date].max().year
        budget_dates = pd.date_range(datetime.date(budget_year-1, 12, 31),
                                     datetime.date(budget_year, 12, 31),
                                     freq=f"{aggregate_months}ME")
        budget_dates = budget_dates[1:]

        if len(budget_dates) < 1:
            return

        # calculated expected income in last year
        index = (dfp.index.astype(np.int64)*1e-12).astype(int)
        center_index = index[1:-1]
        center_series = self.df_summary_income[1:-1]
        deg = 1
        if len(center_series) < 1:
            return
        elif len(center_series) < 2:
            deg = 0
        coef = np.polyfit(x=center_index, y=center_series, deg=deg)
        poly1d_fn = np.poly1d(coef)
        budget_index = (budget_dates.astype(np.int64)*1e-12).astype(int)
        expected_income = budget_index.map(poly1d_fn)
        expected_income = np.sum(expected_income)
        self.statistics_numbers = dict(
            budget_year=budget_year,
            expected_income=expected_income,
            last_date=df[nn.date].max(),
            consumed_budget=dict()
        )

        exclude_tags = set()
        if nn.exclude_tags in self.config.settings and len(self.config.settings[nn.exclude_tags]) > 0:
            exclude_tags = set(self.config.settings[nn.exclude_tags])

        df_budget_year = df.query(f"{nn.date} > {budget_year}")
        for tag_cat in self.config.tag_categories.values():
            if tag_cat.name in exclude_tags:
                continue

            self.statistics_numbers["consumed_budget"][tag_cat.name] = df_budget_year.query(
                f"{nn.tag} == '{tag_cat.name}'")[nn.value].sum()
