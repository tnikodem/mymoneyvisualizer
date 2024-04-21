# -*- coding: utf-8 -*-
import logging
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


class MyTaggerOverviewWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        # TODO make only row selectable
        self.columns = [nn.name, nn.tag, nn.count, nn.sum]
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setColumnWidth(0, 200)
        self.table_widget.setColumnWidth(1, 200)
        self.table_widget.setColumnWidth(2, 100)
        self.table_widget.setColumnWidth(3, 100)
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.verticalHeader().setVisible(False)

        # FIXME not working correctly?! update after sort is enabled
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # add actions
        self.main.config.accounts.add_update_callback(self.update_table)
        self.table_widget.doubleClicked.connect(self.open_tagger)

        self.update_table()

    def update_table(self):
        df = self.main.get_taggeroverview_df()
        if df is None or len(df) < 1:
            self.table_widget.setRowCount(0)
            return
        # FIXME in PyQt need to disable sorting while udpating ?!
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(self.columns):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                else:
                    item = QTableWidgetItem(str(row[col]))
                self.table_widget.setItem(i, j, item)
        self.table_widget.setSortingEnabled(True)

    def open_tagger(self, item):
        tagger_name = self.table_widget.item(item.row(), 0).text()
        self.main.open_tagger(tagger_name)


class WindowTaggerOverview(QMainWindow):
    def __init__(self, parent, config, tagger_window):
        super(WindowTaggerOverview, self).__init__(parent)
        self.config = config
        self.tagger_window = tagger_window

        self.title = 'Taggers'
        self.left = 50
        self.top = 50
        self.width = 900
        self.height = 800
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.table = MyTaggerOverviewWidget(parent=self, main=self)
        self.table.resize(835, 770)
        self.table.move(30, 30)

        self.button_ok = QPushButton('OK', self)
        self.button_ok.resize(250, 32)
        self.button_ok.move(40, 0)
        self.button_ok.clicked.connect(self.close)

        self.button_add = QPushButton('Add Tagger', self)
        self.button_add.resize(250, 32)
        self.button_add.move(280, 0)
        self.button_add.clicked.connect(self.add_tagger)

        self.button_delete = QPushButton('Delete Tagger', self)
        self.button_delete.resize(250, 32)
        self.button_delete.move(520, 0)
        self.button_delete.clicked.connect(self.delete_tagger)

    def open(self):
        self.table.update_table()
        self.show()

    def add_tagger(self):
        self.tagger_window.open_or_create_tagger()

    # FIXME first cell is sometimes "half" seleted in light blue. This is notcovered by selectedIndexe... why? what now?
    def delete_tagger(self):
        for item in self.table.table_widget.selectedIndexes():
            tagger_name = self.table.table_widget.item(item.row(), 0).text()
            self.config.taggers.delete(name=tagger_name)

    def open_tagger(self, tagger_name):
        self.tagger_window.open_or_create_tagger(tagger_name=tagger_name)

    def get_taggeroverview_df(self):
        return self._get_taggeroverview_df(accounts=self.config.accounts, taggers=self.config.taggers)

    # TODO unittest this method
    @staticmethod
    def _get_taggeroverview_df(accounts, taggers):
        logger.debug("request tagoverview df")
        if accounts is None or taggers is None or len(accounts) < 1:
            return

        dfs = []
        for acc in accounts.get():
            dfs += [acc.df]
        df = pd.concat(dfs, sort=False)

        names = []
        tags = []
        counts = []
        sums = []
        for tagger in taggers.get():
            names += [tagger.name]
            tags += [tagger.tag]
            tmpdf = df.loc[df[nn.tagger_name] == tagger.name, :]
            counts += [len(tmpdf)]
            sums += [round(tmpdf[nn.value].sum(), 2)]

        return_df = pd.DataFrame({nn.name: names, nn.tag: tags, nn.count: counts, nn.sum: sums})
        logger.debug(f"return tag overview df with len {len(names)} \n {return_df.head()}")
        return return_df
