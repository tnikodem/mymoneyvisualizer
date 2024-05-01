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

        self.layout = QHBoxLayout()

        self.assign_tagcategories = AssignTagCategoryWidget(
            parent=self, main=main)
        self.layout.addWidget(self.assign_tagcategories)

        vlayout = QVBoxLayout()
        self.plot_basic = SummaryPlotWidget(self, main=main, category=nn.basic)
        vlayout.addWidget(self.plot_basic)
        self.plot_optional = SummaryPlotWidget(
            self, main=main, category=nn.optional)
        vlayout.addWidget(self.plot_optional)

        self.layout.addLayout(vlayout, 100)

        self.setLayout(self.layout)


class AggregationSelect(QWidget):
    def __init__(self, parent, main):
        super(AggregationSelect, self).__init__(parent)
        self.main = main
        self.layout = QHBoxLayout()
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
        self.combobox.setCurrentText(
            str(self.main.config.settings[nn.plot_aggregation_month]))
        self.layout.addWidget(self.combobox)

        self.setLayout(self.layout)

        # add action
        self.combobox.currentTextChanged.connect(
            self.main.update_plot_aggregation_month)


class WindowSummaryGraph(QMainWindow):
    def __init__(self, parent, config):
        super(WindowSummaryGraph, self).__init__(parent)

        self.config = config
        self.update_callbacks = []
        self.updateing = True

        self.df_summary = None
        self.df_summary_income = None
        self.statistics_numbers = {}

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

    def update_budget_period(self, category, start, end):
        self.config.settings[nn.budget][nn.basic]["start"] = start
        self.config.settings[nn.budget][nn.basic]["end"] = end
        self.config.settings[nn.budget][nn.optional]["start"] = start
        self.config.settings[nn.budget][nn.optional]["end"] = end

        self.config.save_settings()
        self.run_update_callbacks()

    def update_budget_factor(self, category, budget_factor):
        self.config.settings[nn.budget][category]["factor"] = budget_factor
        self.config.save_settings()
        self.run_update_callbacks()

    def get_data(self):
        budget_period_start = self.config.settings[nn.budget]["basic"]["start"]
        budget_period_end = self.config.settings[nn.budget]["basic"]["end"]

        # get df with all transactions
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
        if len(self.config.settings[nn.exclude_tags]) > 0:
            df = df.loc[~(df[nn.tag].isin(
                set(self.config.settings[nn.exclude_tags]))), :]
        if len(df) < 1:
            return
        # TODO change "tag" to "base tag", as this is what it really is here..
        df[nn.tag] = df[nn.tag].str.split(".").str[0]
        df = df[[nn.date, nn.value, nn.tag]]

        first_date = df[nn.date].min()
        last_date = df[nn.date].max()

        # Fill holes
        fill_dates = pd.date_range(first_date, last_date, freq='1ME')
        fill_values = pd.DataFrame({nn.date: fill_dates,
                                    nn.value: [0]*len(fill_dates),
                                    nn.tag: [" "]*len(fill_dates),
                                    })
        df = pd.concat([df, fill_values], sort=False)

        # Pivot Table
        aggregate_months = self.config.settings.get(
            nn.plot_aggregation_month, 3)
        dfg = df.groupby([nn.tag, pd.Grouper(freq=f"{aggregate_months}ME", key=nn.date)]).agg(
            {nn.value: "sum"}).reset_index()
        dfp = dfg.pivot(index=nn.date, columns=nn.tag,
                        values=["value"]).fillna(0.)
        dfp.columns = dfp.columns.get_level_values(1)

        # Add missing base_tags in tag_categories
        for col in dfp.columns:
            if col not in self.config.tag_categories:
                self.config.tag_categories.add(name=col, category=nn.basic)

        self.df_summary = dfp

        # get average income series + extrapolation
        if len(dfp) < 3:
            return

        ds_income = np.zeros(len(dfp))
        for tag_cat in self.config.tag_categories.get():
            if tag_cat.category != nn.income:
                continue
            if tag_cat.name not in dfp.columns:
                continue
            ds_income += dfp[tag_cat.name]

        # assume first and last value not complete
        fit_dates = dfp.index.values[1:-1]
        x_fit = (fit_dates.astype(np.int64)*1e-12).astype(int)
        y_fit = ds_income[1:-1]

        coef = np.polyfit(x=x_fit, y=y_fit, deg=1)
        poly1d_fn = np.poly1d(coef)

        analysis_period_start = min(datetime.datetime(
            budget_period_start-1, 12, 31), first_date)
        analysis_period_end = max(
            datetime.datetime(budget_period_end, 12, 31),
            datetime.datetime(last_date.year, 12, 31),)
        analysis_period_dates = pd.date_range(analysis_period_start, analysis_period_end,
                                              freq=f"{aggregate_months}ME")
        x_analysis_period = (analysis_period_dates.astype(
            np.int64)*1e-12).astype(int)
        average_income = x_analysis_period.map(poly1d_fn)

        self.df_summary_income = pd.DataFrame(index=analysis_period_dates,
                                              data=dict(average_income=average_income))

        self.statistics_numbers = dict(
            first_date=first_date,
            last_date=last_date
        )
