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


#from mymoneyvisualizer.windows.pyqtgraph_extensions.LegendItem import LegendItem
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
        selected_indexes = []
        for i, tag in enumerate(unique_tags):
            self.multi_select.addItem(tag, tag)
            if tag in self.main.excluded_tags:
                selected_indexes += [i]
        if len(selected_indexes) > 0:
            self.multi_select.setCurrentIndexes(selected_indexes)
        self.updateing = False


class SummaryGraphWidget(QWidget):

    def __init__(self, parent, main):
        super(SummaryGraphWidget, self).__init__(parent)
        self.main = main
        self.parent = parent

        self.layout = QHBoxLayout(self)

        vlayout = QVBoxLayout(self)
        # Tag List Widget
        vlayout.addWidget(QLabel("Income:", self))
        self.list_widget_income = QListWidget()
        self.list_widget_income.setFixedWidth(150)
        #self.list_widget_income.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_income.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        vlayout.addWidget(self.list_widget_income)
        vlayout.addWidget(QLabel("Expenses (Basic):", self))
        self.list_widget_basic = QListWidget()
        self.list_widget_basic.setFixedWidth(150)
        self.list_widget_basic.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)        
        #self.list_widget_basic.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_basic.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        vlayout.addWidget(self.list_widget_basic)
        vlayout.addWidget(QLabel("Expenses (Optional):", self))
        self.list_widget_optional = QListWidget()
        self.list_widget_optional.setFixedWidth(150)
        #self.list_widget_optional.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_optional.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        vlayout.addWidget(self.list_widget_optional)

        self.layout.addLayout(vlayout)

        # Plot Widget
        self.plot_graph = pg.PlotWidget()
        self.plot_graph.addLegend()

        self.plot_graph.setBackground("w")
        axis = pg.DateAxisItem(orientation='bottom')
        self.plot_graph.plotItem.setAxisItems({"bottom": axis})        
        self.layout.addWidget(self.plot_graph)

        self.setLayout(self.layout)
        self.draw_plot()

        # Add Actions
        self.main.add_update_callback(self.draw_plot)

        self.list_widget_basic.itemChanged.connect(self.update_basic_list)
        self.list_widget_optional.itemChanged.connect(self.update_optional_list)
        self.list_widget_income.itemChanged.connect(self.update_income_list)


    def update_basic_list(self, item):
        idx = self.list_widget_basic.indexFromItem(item)
        idx = idx.row()
        print(f"basic {idx}")
        self.main.update_tag_categories(tag_name=item.text(), idx=idx, category="basic")

    def update_optional_list(self, item):
        idx = self.list_widget_optional.indexFromItem(item)
        idx = idx.row()
        print(f"optional {idx}")
        self.main.update_tag_categories(tag_name=item.text(), idx=idx, category="optional")

    def update_income_list(self, item):
        idx = self.list_widget_income.indexFromItem(item)
        idx = idx.row()
        print(f"income {idx}")
        self.main.update_tag_categories(tag_name=item.text(), idx=idx, category="income")



    def draw_plot(self):
        print("draw plot")


        self.plot_graph.clear()
        self.list_widget_income.clear()
        self.list_widget_basic.clear()        
        self.list_widget_optional.clear()

        df = self.parent.get_data()
        if df is None or len(df) < 1:
            return


        self.plot_graph.setXRange(df.index.astype(np.int64).values[0]*1e-9, df.index.astype(np.int64).values[-1]*1e-9, padding=0)
        self.plot_graph.setYRange(0, 30000, padding=0)


        # TODO How to plot income?
        pen = pg.mkPen(color=(0,0,0), width=2)
        self.plot_graph.plot(df.index.astype(np.int64)*1e-9, list(df["work"]), pen=pen, name="work")
        self.list_widget_income.addItem("work")

        data_x_before = [0] * len(df)

        # PLot basic
        colors = [
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
        ]        
        i_basic = 0
        for tag_cat in self.main.config.tag_categories.get():
            if tag_cat.category != "basic":
                continue
            if tag_cat.name not in df.columns:
                continue
            print(tag_cat.name)
            self.list_widget_basic.addItem(tag_cat.name)
            color = colors[i_basic%10]
            data_x = data_x_before - df[tag_cat.name]
            pen = pg.mkPen(color=color, width=2)
            self.plot_graph.plot(df.index.astype(np.int64)*1e-9, data_x, pen=pen, name=tag_cat.name)
            curve1 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x_before)
            curve2 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x)
            self.plot_graph.addItem(pg.FillBetweenItem(curve1=curve1, curve2=curve2, brush=(*color, 100)))
            data_x_before = data_x
            i_basic += 1            
        # Plot optional
        colors = [
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
        ]        
        i_optional = 0
        for tag_cat in self.main.config.tag_categories.get():
            if tag_cat.category != "optional":
                continue
            if tag_cat.name not in df.columns:
                continue
            self.list_widget_optional.addItem(tag_cat.name)
            color = colors[i_optional%10]
            data_x = data_x_before - df[tag_cat.name]
            pen = pg.mkPen(color=color, width=2)
            self.plot_graph.plot(df.index.astype(np.int64)*1e-9, data_x, pen=pen, name=tag_cat.name)
            curve1 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x_before)
            curve2 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x)
            self.plot_graph.addItem(pg.FillBetweenItem(curve1=curve1, curve2=curve2, brush=(*color, 100)))
            data_x_before = data_x       
            i_optional += 1 


        # band between top and work
        # curve1 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, data_x_before)
        curve1 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, [0] * len(df))        
        curve2 = pg.PlotDataItem(df.index.astype(np.int64)*1e-9, df["work"])
        self.plot_graph.addItem(pg.FillBetweenItem(curve1=curve1, curve2=curve2, brush=(0,0,0, 25)))        


class WindowGraph(QMainWindow):
    def __init__(self, parent, config):
        super(WindowGraph, self).__init__(parent)
        self.config = config
        self.update_callbacks = []
        self.updateing = True

        self.excluded_tags = set()

        super().__init__()
        logger.debug("starting main window")

        self.title = 'My Money Visualiser'
        self.left = 100
        self.top = 100
        
        self.width = 1000
        self.height = 600
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

        self.updateing = False

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
        for func in self.update_callbacks:
            func()    
        self.updateing = False
    
    def set_excluded_tags(self, tags):
        self.excluded_tags = set(tags)
        self.run_update_callbacks()


    def update_tag_categories(self, tag_name, idx, category):
        if self.updateing:
            return
        tag_names_basic = []
        for x in range(self.summary_graph.list_widget_basic.count()):
            list_item = self.summary_graph.list_widget_basic.item(x)
            if (category == "basic" and x == idx) or list_item.text() != tag_name:
                tag_names_basic += [list_item.text()]

        tag_names_optional = []
        for x in range(self.summary_graph.list_widget_optional.count()):
            list_item = self.summary_graph.list_widget_optional.item(x)
            if (category == "optional" and x == idx) or list_item.text() != tag_name:
                tag_names_optional += [list_item.text()]

        tag_names_income = []
        for x in range(self.summary_graph.list_widget_income.count()):
            list_item = self.summary_graph.list_widget_income.item(x)
            if (category == "income" and x == idx) or list_item.text() != tag_name:
                tag_names_income += [list_item.text()]

        new_sorted_tags = dict(
            basic=tag_names_basic,
            optional=tag_names_optional,
            income=tag_names_income)
        
        self.config.tag_categories.update_category_and_sort(new_sorted_tags=new_sorted_tags)

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
        if len(self.excluded_tags) > 0:
            df = df.loc[~(df[nn.tag].isin(self.excluded_tags)), :]

        if len(df) < 1:
            return
        

        df[nn.tag] = df[nn.tag].apply(self.get_base_tag)
        df = df[[nn.date, nn.value, nn.tag]]
        
        # Fill holes
        temp_dates = pd.date_range(df[nn.date].min(), df[nn.date].max(), freq='1ME')
        temp_values = pd.DataFrame({nn.date: temp_dates,
                                    nn.value: [0]*len(temp_dates),
                                    nn.tag: [" "]*len(temp_dates),
                                    })
        df = pd.concat([df, temp_values], sort=False)

        # create 
        dfg = df.groupby([nn.tag, pd.Grouper(freq="3ME", key=nn.date)]).agg({nn.value: "sum"}).reset_index()
        dfp = dfg.pivot(index=nn.date, columns=nn.tag, values=["value"]).fillna(0.)
        dfp.columns = dfp.columns.get_level_values(1)

        #dfp.index = (dfp.index.astype(str).str.replace("-", "").astype(int) / 100).astype(int)

        # assume first and last row are not complete
        dfp = dfp[1:-1]

        # Add missing in tag categories
        for col in dfp.columns:
            if col not in self.config.tag_categories:
                self.config.tag_categories.add(name=col, category="basic")        

        return dfp



        # # Graph
        # pg.setConfigOptions(antialias=True)
        # self.plot_graph = pg.PlotWidget()
        # self.plot_graph.addLegend()
        # self.plot_graph.setXRange(1, 10)
        # self.plot_graph.setYRange(20, 40)
        # styles = {"color": "red", "font-size": "18px"}
        # self.plot_graph.setTitle('Temperature vs Time', **styles)
        # self.plot_graph.setLabel("left", "Temperature (°C)", **styles)
        # self.plot_graph.setLabel("bottom", "Time (min)", **styles)
        # self.plot_graph.setBackground("w")
        # time = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        # temperature_1 = [30, 32, 34, 32, 33, 31, 29, 32, 35, 30]
        # temperature_2 = [32, 35, 40, 22, 38, 32, 27, 38, 32, 38]
        # pen = pg.mkPen(color=(255, 0, 0))
        # self.plot_graph.plot(time, temperature_1, pen=pen, name="blub 1")
        # pen = pg.mkPen(color=(0, 254, 0))
        # self.plot_graph.plot(time, temperature_2, pen=pen, name="blub 2", 
        #                      #fillLevel=0, 
        #                      #fillOutline=True,
        #                      #fillBrush=(50,50,200,50)
        #                      )
        # self.plot_graph.addItem(pg.InfiniteLine(pos=30, angle=0, pen=pen))
        # self.plot_graph.addItem(pg.BarGraphItem(x=range(5), height=[1,5,2,4,3], width=0.5))
        # curve1 = pg.PlotDataItem(time, temperature_1)
        # curve2 = pg.PlotDataItem(time, temperature_2)
        # self.plot_graph.addItem(pg.FillBetweenItem(curve1=curve1, curve2=curve2, brush=(50,50,200,50)))
        # layout.addWidget(self.plot_graph)