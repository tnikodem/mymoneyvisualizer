# -*- coding: utf-8 -*-

import logging
import pandas as pd

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView

from mymoneyvisualizer.naming import Naming as nn


logger = logging.getLogger(__name__)


class MyTableWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.columns = [nn.account, nn.date, nn.recipient, nn.description, nn.value, nn.tag, nn.tagger_name]
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setColumnWidth(0, 100)
        self.table_widget.setColumnWidth(1, 80)
        self.table_widget.setColumnWidth(2, 180)
        self.table_widget.setColumnWidth(3, 516)
        self.table_widget.setColumnWidth(4, 80)
        self.table_widget.setColumnWidth(5, 150)
        self.table_widget.setColumnWidth(6, 0)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # add actions and callbacks
        self.main.config.accounts.add_update_callback(self.update_table)
        self.table_widget.doubleClicked.connect(self.open_tagger_window)

    def open_tagger_window(self, item):
        tagger_name = self.table_widget.item(item.row(), 6).text()
        self.main.open_tagger_window(tagger_name=tagger_name)

    def update_table(self):
        df = self.main.get_filtered_df()
        if df is None or len(df) < 1:
            self.table_widget.setRowCount(0)
            return
        self.table_widget.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(self.columns):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                else:
                    item = QTableWidgetItem(str(row[col]))
                self.table_widget.setItem(i, j, item)


class DetailMonthWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.table = MyTableWidget(self, main=self.main)
        self.table.resize(1200, 750)
        self.table.move(0, 0)


class WindowDetailMonth(QMainWindow):
    def __init__(self, parent, config, tagger_window):
        super(WindowDetailMonth, self).__init__(parent)
        self.config = config
        self.tagger_window = tagger_window

        self.left = 100
        self.top = 100
        self.width = 1500
        self.height = 900
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.detailmonth_widget = DetailMonthWidget(parent=self, main=self)
        self.detailmonth_widget.resize(1400, 800)
        self.detailmonth_widget.move(0, 0)

        self.month = None
        self.tag = None

    def open_detailmonth(self, month, tag):
        self.month = month
        self.tag = tag
        logger.debug(f"opening month {month}: {tag}")
        self.setWindowTitle(f"{tag} in {month}")
        self.detailmonth_widget.table.update_table()
        self.show()

    def open_tagger_window(self, tagger_name):
        self.tagger_window.open_or_create_tagger(tagger_name=tagger_name)

    def get_filtered_df(self):
        logger.debug("requesting filtered df")
        if self.tag is None or self.month is None:
            return None
        dfs = [] 
        for acc in self.config.accounts.get():
            if len(acc.df) < 1:
                continue
            acc.df.loc[:, nn.account] = acc.name
            df = acc.df.loc[acc.df[nn.date].astype(str).str.slice(0, 7) == self.month, :]
            df = df[df[nn.tag].str.contains(self.tag)]  # selected tag, FIXME, mixture of tags and subtags possible
            dfs += [df]
        if len(dfs) > 0:
            df_result = pd.concat(dfs, sort=False)
        else:
            df_result = pd.DataFrame({f: [] for f in self.detailmonth_widget.table.columns})
        
        df_result = df_result.sort_values([nn.date]).reset_index(drop=True)
        logger.debug(f"return filtered df with len {len(df_result)}")
        return df_result
