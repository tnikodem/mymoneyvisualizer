# -*- coding: utf-8 -*-

import logging

import numpy as np
import pandas as pd


import pyqtgraph as pg


from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QApplication, QLineEdit, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt


from mymoneyvisualizer.naming import Naming as nn

pg.setConfigOptions(antialias=True)


logger = logging.getLogger(__name__)


COLORS = {nn.basic: [
    (246, 112, 136),  # Soft pink
    (219, 136, 49),   # Warm orange
    (173, 156, 49),   # Muted yellow
    (119, 170, 49),   # Earthy green
    (51, 176, 122),   # Refreshing teal
    (53, 172, 164),   # Cool turquoise
    (56, 168, 197),   # Serene blue
    (110, 154, 244),  # Sky-blue
    (204, 121, 244),  # Lavender-purple
    (245, 101, 204)   # Vibrant magenta
],
    nn.optional: [
    (246, 112, 136),  # Soft pink
    (219, 136, 49),   # Warm orange
    (173, 156, 49),   # Muted yellow
    (119, 170, 49),   # Earthy green
    (51, 176, 122),   # Refreshing teal
    (53, 172, 164),   # Cool turquoise
    (56, 168, 197),   # Serene blue
    (110, 154, 244),  # Sky-blue
    (204, 121, 244),  # Lavender-purple
    (245, 101, 204)   # Vibrant magenta
], }


class SummaryPlotWidget(QWidget):
    def __init__(self, parent, main, category):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.category = category

        self.layout = QVBoxLayout(self)

        # Budget selector
        hlayout = QHBoxLayout(self)
        hlayout.addWidget(
            QLabel(f"<b>{self.category.title()} expenses</b> with budget factor: ", self))
        self.budget_edit = QLineEdit(parent=self)
        self.budget_edit.setFixedWidth(35)
        self.budget_edit.setText(str(self.main.budgets[self.category]))
        # self.budget_edit.setAlignment(Qt.AlignmentFlag.AlignLeft)
        hlayout.addWidget(self.budget_edit)
        hlayout.addStretch()
        self.layout.addLayout(hlayout)

        # Plot Widget
        self.plot_graph = pg.PlotWidget()
        self.plot_graph.addLegend()

        self.plot_graph.setBackground("w")
        axis = pg.DateAxisItem(orientation='bottom')
        self.plot_graph.plotItem.setAxisItems({"bottom": axis})
        self.layout.addWidget(self.plot_graph)

        self.setLayout(self.layout)

        # Add Actions
        self.main.add_update_callback(self.draw_plot)
        self.budget_edit.textChanged.connect(self.update_budget)

    def update_budget(self, budget):
        try:
            budget = float(budget)
            assert budget >= 0 and budget <= 1
        except Exception as e:
            self.budget_edit.setStyleSheet("QLineEdit"
                                           "{"
                                           "background : #dc5b6a;"
                                           "}")
            return

        self.budget_edit.setStyleSheet("QLineEdit"
                                       "{"
                                       "background : white;"
                                       "}")
        self.main.update_budget(category=self.category, budget=budget)

    def draw_plot(self):
        self.plot_graph.clear()
        df = self.main.df_summary
        ds_income = self.main.df_summary_income
        if df is None or len(df) < 1:
            return

        ds_dates = (df.index.astype(np.int64)*1e-9).astype(int).values
        ds_income = ds_income * self.main.budgets[self.category]

        # Add income
        pen = pg.mkPen(color=(0, 0, 0), width=2)
        self.plot_graph.plot(ds_dates, ds_income, pen=pen, name=nn.income)

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

            color = COLORS[self.category][i % 10]
            pen = pg.mkPen(color=color, width=2)
            self.plot_graph.plot(
                ds_dates, stack_data["dataseries"], pen=pen, name=stack_data[nn.name])

            curve1 = pg.PlotDataItem(ds_dates, stack_data["dataseries"])
            curve2 = pg.PlotDataItem(
                ds_dates, stacked_data_series[i-1]["dataseries"])

            # TODO check FillBetweenItem method of pyqtgraph
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
        # curve1 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x_before)
        curve1 = pg.PlotDataItem(
            ds_dates, stacked_data_series[-1]["dataseries"])
        curve2 = pg.PlotDataItem(ds_dates, ds_income)
        self.plot_graph.addItem(pg.FillBetweenItem(
            curve1=curve1, curve2=curve2, brush=(0, 0, 0, 25)))

        # Define ranges
        max_y = max(ds_income)
        for stack_data in stacked_data_series:
            max_y = max(max_y, max(stack_data["dataseries"]))

        self.plot_graph.setXRange(ds_dates[0], ds_dates[-1], padding=0)
        self.plot_graph.setYRange(0, max_y*1.2, padding=0)