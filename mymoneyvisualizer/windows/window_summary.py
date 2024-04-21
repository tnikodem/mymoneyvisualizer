# -*- coding: utf-8 -*-
import logging
import datetime
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import QLabel


from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from pyqt6_multiselect_combobox import MultiSelectComboBox


from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


class MyTableWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.columns = []

        self.table_widget = QTableWidget()
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        # always exactly 12 month (tag, months ... , total, mthly average)
        self.table_widget.setColumnCount(15)
        self.table_widget.setColumnWidth(0, 180)
        for i in range(1, 14):
            self.table_widget.setColumnWidth(i, 80)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # add actions
        self.table_widget.doubleClicked.connect(self.open_window_detail)
        self.main.config.accounts.add_update_callback(self.update_table)
        self.main.add_update_callback(self.update_table)

        self.update_table()

    def open_window_summary_tag(self, tag):
        # TODO implement tag overview window (similar to monthly overview, however without month cut
        logger.error("not implemented")

    def open_window_detail(self, item):
        if item.column() == 0:
            self.open_window_summary_tag(item.data())
        else:
            month = self.columns[item.column()]
            tag = self.table_widget.item(item.row(), 0).text()
            self.main.open_detailmonth(month=month, tag=tag)

    def update_table(self):
        df = self.main.summary_df()
        if df is None:
            self.table_widget.setRowCount(0)
            return
        self.columns = df.columns
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(df.columns):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, float(round(row[col], 0)))
                else:
                    item = QTableWidgetItem(str(row[col]))
                if col == "total" or col == "monthly average" or i == len(df) - 1:
                    item.setBackground(QColor(0, 0, 0, 100))
                self.table_widget.setItem(i, j, item)


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


class SummaryWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)

        self.button_before = QPushButton('previous month', self)
        self.button_before.resize(250, 32)
        self.button_before.move(40, 0)
        self.button_before.clicked.connect(self.main.month_before)

        self.button_after = QPushButton('next month', self)
        self.button_after.resize(250, 32)
        self.button_after.move(340, 0)
        self.button_after.clicked.connect(self.main.month_after)

        self.multi_select = ExcludeTaggerSelectComboBox(self, main)
        self.multi_select.resize(300, 44)
        self.multi_select.move(600, 0)

        self.table = MyTableWidget(parent=self, main=self.main)
        self.table.resize(1700, 600)
        self.table.move(40, 80)


class WindowSummary(QMainWindow):
    def __init__(self, parent, config, detail_month_window):
        super(WindowSummary, self).__init__(parent)
        self.config = config
        self.detail_month_window = detail_month_window

        self.title = 'Summary'
        self.left = 50
        self.top = 50
        self.width = 1700
        self.height = 800
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.date_from, self.date_upto = None, None
        self.set_current_date_window()
        self.excluded_tags = set()

        self.update_callbacks = []

        self.summary_widget = SummaryWidget(parent=self, main=self)
        self.summary_widget.resize(1600, 700)
        self.summary_widget.move(30, 30)

    def add_update_callback(self, func):
        self.update_callbacks += [func]

    def run_update_callbacks(self):
        for func in self.update_callbacks:
            func()

    def set_excluded_tags(self, tags):
        self.excluded_tags = set(tags)
        self.run_update_callbacks()

    def set_current_date_window(self):
        now = datetime.datetime.now()
        date_upto = datetime.datetime(now.year, now.month, 1) + datetime.timedelta(days=32)  # mth at most 31 days
        self.date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        self.date_from = datetime.datetime(date_upto.year - 1, date_upto.month, 1)

    def month_before(self):
        date_upto = self.date_upto - datetime.timedelta(days=2)
        self.date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        self.date_from = datetime.datetime(date_upto.year - 1, date_upto.month, 1)
        self.run_update_callbacks()

    def month_after(self):
        date_upto = self.date_upto + datetime.timedelta(days=32)  # month at most 31 days
        self.date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        self.date_from = datetime.datetime(date_upto.year - 1, date_upto.month, 1)
        self.run_update_callbacks()

    def open_detailmonth(self, month, tag):
        self.detail_month_window.open_detailmonth(month=month, tag=tag)

    @staticmethod
    def get_base_tag(tag):
        tag = str(tag)
        tags = tag.split(".")
        tag_out = tags[0]
        return tag_out

    # TODO unittest method
    def summary_df(self):
        logger.debug(f"request summary df from {self.date_from} upto {self.date_upto}")
        dfs = []
        account_names = []
        for acc in self.config.accounts.get():
            account_names += [acc.name]
            df = acc.df
            df = df[(df[nn.date] >= self.date_from) & (df[nn.date] < self.date_upto)]
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

        temp_dates = pd.date_range(self.date_from, self.date_upto, freq='1ME')
        temp_values = pd.DataFrame({nn.date: temp_dates,
                                    nn.value: [0]*len(temp_dates),
                                    nn.tag: ["temp_tag_43643564356345"]*len(temp_dates),
                                    })
        df = pd.concat([df, temp_values], sort=False)

        df[nn.tag] = df[nn.tag].apply(self.get_base_tag)

        # calculate pivot table
        dfg = df.groupby([nn.tag, pd.Grouper(freq="1ME", key=nn.date)]).agg({nn.value: "sum"}).reset_index()
        dfp = dfg.pivot(index=nn.tag, columns=nn.date, values=["value"]).fillna(0)
        dfp = dfp[dfp.index != "temp_tag_43643564356345"]
        dfp.columns = [t.strftime('%Y-%m') for a, t in dfp.columns]
        ncol = len(dfp.columns)
        dfp["total"] = dfp.sum(axis=1)
        dfp["monthly average"] = dfp["total"] / ncol
        dfp = dfp.sort_values(["total"], ascending=True)

        df_total = pd.DataFrame({**dfp.sum().to_dict()}, index=["total"])
        dfp = pd.concat([dfp, df_total], axis=0)
        dfp.index.name = "tag"
        dfp = dfp.reset_index()
        logger.debug(f"return summary_df with len {len(dfp)}")
        return dfp
