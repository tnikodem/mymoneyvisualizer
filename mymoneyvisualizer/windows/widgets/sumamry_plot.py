# -*- coding: utf-8 -*-

import logging
import warnings
import datetime
import numpy as np
import pandas as pd


import pyqtgraph as pg


from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QVBoxLayout, QWidget, QTextEdit, QComboBox
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.constants import PLOT_COLORS, GREY_BACKGROUND_COLOR
from mymoneyvisualizer.windows.widgets.budget_control import BudgetControl

pg.setConfigOptions(antialias=True)


logger = logging.getLogger(__name__)


class SummaryPlotWidget(QWidget):
    def __init__(self, parent, main, category):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.category = category

        self.layout = QVBoxLayout()

        # Plot header
        self.budget_control = BudgetControl(parent=self, main=self.main)
        self.layout.addWidget(self.budget_control)

        # Plot Widget
        hlayout2 = QHBoxLayout()
        self.plot_graph = pg.PlotWidget()
        self.plot_graph.addLegend()
        self.plot_graph.setBackground("w")
        axis = pg.DateAxisItem(orientation='bottom')
        self.plot_graph.plotItem.setAxisItems({"bottom": axis})
        hlayout2.addWidget(self.plot_graph)

        # Budget summary
        self.budget_viewer = QTextEdit()
        self.budget_viewer.setFixedWidth(255)
        hlayout2.addWidget(self.budget_viewer)
        self.layout.addLayout(hlayout2)

        self.setLayout(self.layout)

        # Add Actions
        self.main.add_update_callback(self.draw_plot)
        self.main.add_update_callback(self.update_budget)

    def update_budget(self):
        # calculate budget period statistics
        df_summary = self.main.df_summary
        df_summary_income = self.main.df_summary_income
        if df_summary is None or len(df_summary) < 1:
            return
        if df_summary_income is None or len(df_summary_income) < 1:
            return

        budget_period_start = self.main.config.settings[nn.budget][self.category]["start"]
        budget_period_end = self.main.config.settings[nn.budget][self.category]["end"]
        timestamp_start = pd.Timestamp(budget_period_start, 1, 1)
        timestamp_end = pd.Timestamp(budget_period_end, 12, 31)

        mask = (df_summary_income.index >= timestamp_start) & (
            df_summary_income.index <= timestamp_end)
        expected_total_budget = df_summary_income[mask]["average_income"].sum() * \
            self.main.config.settings[nn.budget][self.category]["factor"]

        # expected_total_budget = self.main.statistics_numbers["expected_income"] * \
        #     self.main.config.settings[nn.budget][self.category]["factor"]

        # calculate day coverage
        last_date = self.main.statistics_numbers["last_date"]
        total_days = 0
        covered_days = 0
        for year in range(budget_period_start, budget_period_end+1):
            total_days += pd.Timestamp(year, 12, 31).dayofyear
            if pd.Timestamp(year, 12, 31) < last_date:
                covered_days += pd.Timestamp(year, 12, 31).dayofyear
            else:
                covered_days += last_date.day_of_year
        remaining_months = (total_days-covered_days)/30.
        is_complete_year = covered_days == total_days

        if budget_period_start == budget_period_end:
            budget_period_text = f"{budget_period_start}"
        else:
            budget_period_text = f"{budget_period_start}-{budget_period_end}"

        budget_text = f"""<h2>{self.category.title()} budget {budget_period_text}</h2>
        covered days: {covered_days}/{total_days} ({round(covered_days/total_days*100)}%)<br/>
        last day: {self.main.statistics_numbers["last_date"].strftime("%d.%m.%Y")}<br/>
        remaining: {round(remaining_months, 1)} months
        <br/>
        <font size='4' type='Consolas'>
        <table>
        <tr>
            <td><b>{"Total" if is_complete_year else "Expected"}:</b></td>
            <td>{round(expected_total_budget)} €</td>
        </tr>
        <tr>
        </tr>
        """

        mask = (df_summary.index >= timestamp_start) & (
            df_summary.index <= timestamp_end)
        df_summary_budget = df_summary[mask]
        total_consumed = 0
        for tag_cat in reversed(list(self.main.config.tag_categories.get())):
            if tag_cat.category != self.category:
                continue
            if tag_cat.name not in df_summary_budget.columns:
                continue
            consumed = -df_summary_budget[tag_cat.name].sum()
            total_consumed += consumed

            # TODO think about how to refactor this in a good way
            tag_cat_name = tag_cat.name
            if tag_cat_name in ["", " "]:
                tag_cat_name = "unassigned"
            budget_text += f"""
            <tr>
                <td>{tag_cat_name}:</td>
                <td>{round(consumed)} €</td>
            </tr>
            """

        budget_text += f"""
        <tr>
            <td><b>Consumed total:</b></td>
            <td><b>{round(total_consumed)} €</b></td>
        </tr>
        <tr>
        </tr>
        """
        if is_complete_year:
            budget_text += f"""
            <tr>
                <td>Difference:</td>
                <td>{round(expected_total_budget-total_consumed)} €</td>
            </tr>
            """
        else:
            budget_text += f"""
            <tr>
                <td>Remaining total:</td>
                <td>{round(expected_total_budget-total_consumed)} €</td>
            </tr>
            <tr>
                <td>Remaining per month:</td>
                <td>{round((expected_total_budget-total_consumed)/remaining_months)} €</td>
            </tr>
            <tr>
                <td>Trend end of year: </td>
                <td>{round((expected_total_budget - (total_consumed * total_days / covered_days)))} €</td>
            </tr>"""
        budget_text += """
        </table>
        </font>
        """
        self.budget_viewer.setHtml(budget_text)

    def draw_plot(self):
        self.plot_graph.clear()
        df = self.main.df_summary
        df_income = self.main.df_summary_income
        if df is None or len(df) < 2:
            return
        ds_dates = (df.index.astype(np.int64)*1e-9).astype(int).values

        # Highlight budget period
        budget_period_start = self.main.config.settings[nn.budget][self.category]["start"]
        budget_period_end = self.main.config.settings[nn.budget][self.category]["end"]
        start = int(datetime.datetime(budget_period_start, 1, 1).timestamp())
        end = int(datetime.datetime(budget_period_end, 12, 31).timestamp())
        pen = pg.mkPen(color=GREY_BACKGROUND_COLOR, width=2,
                       style=Qt.PenStyle.DashLine)
        v_bar_start = pg.InfiniteLine(
            movable=False, pos=start, angle=90, pen=pen)
        v_bar_end = pg.InfiniteLine(movable=False, pos=end, angle=90, pen=pen)
        self.plot_graph.addItem(v_bar_start)
        self.plot_graph.addItem(v_bar_end)

        # Plot Income/Budget
        x_income = ds_dates
        y_income = [0]
        if df_income is not None and len(df_income) > 0:
            x_income = (df_income.index.astype(
                np.int64)*1e-9).astype(int).values
            y_income = df_income["average_income"] * \
                self.main.config.settings[nn.budget][self.category]["factor"]
            pen = pg.mkPen(color=(0, 0, 0), width=2)
            self.plot_graph.plot(x_income, y_income, pen=pen, name=nn.budget)

        # Calculate stacked data series
        stacked_data_series = [dict(
            name=None,
            dataseries=np.zeros(len(df))
        )]
        for tag_cat in reversed(list(self.main.config.tag_categories.get())):
            if tag_cat.category != self.category:
                continue
            if tag_cat.name not in df.columns:
                continue
            last_data = stacked_data_series[-1]["dataseries"]
            stacked_data_series += [dict(
                name=tag_cat.name,
                dataseries=last_data - df[tag_cat.name]
            )]

        # draw from last to first to make colors agree with legend
        for i in range(len(stacked_data_series)-1, 0, -1):
            stack_data = stacked_data_series[i]
            color = PLOT_COLORS[self.category][i % 10]
            pen = pg.mkPen(color=color, width=2)
            self.plot_graph.plot(
                ds_dates, stack_data["dataseries"], pen=pen, name=stack_data[nn.name])
            # TODO maybe use stepMode ?!

            curve1 = pg.PlotDataItem(ds_dates, stack_data["dataseries"])
            curve2 = pg.PlotDataItem(
                ds_dates, stacked_data_series[i-1]["dataseries"])

            # FIXME/TODO check FillBetweenItem method of pyqtgraph
            # Why is there an intersection? How can we disable it without hacking?
            # def updatePath(self):
            # ...
            # for p1, p2 in zip(ps1, ps2):
            #     # intersection = p1.intersected(p2)
            #     # if not intersection.isEmpty():
            #     #     path.addPolygon(intersection)
            #     path.addPolygon(p1 + p2)
            self.plot_graph.addItem(pg.FillBetweenItem(
                curve1=curve1, curve2=curve2, brush=(*color, 100)))

        # band between top and work
        if df_income is not None and len(df_income) > 0:
            curve1 = pg.PlotDataItem(
                ds_dates, stacked_data_series[-1]["dataseries"])
            curve2 = pg.PlotDataItem(ds_dates, y_income[df.index])
            self.plot_graph.addItem(pg.FillBetweenItem(
                curve1=curve1, curve2=curve2, brush=(0, 0, 0, 25)))

        # Define axis ranges
        # assume first month not complete
        min_x = min(x_income[1], ds_dates[1])
        max_x = max(x_income[-1], ds_dates[-1])
        min_y = 0
        max_y = max(y_income)
        for stack_data in stacked_data_series:
            max_y = max(max_y, max(stack_data["dataseries"]))
        self.plot_graph.setYRange(min_y, max_y*1.2, padding=0)
        with warnings.catch_warnings(action="ignore"):
            self.plot_graph.setXRange(min_x, max_x, padding=0)
