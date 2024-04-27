# -*- coding: utf-8 -*-
import logging
import datetime

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


TABLE_COLUMNS = [nn.transaction_id, nn.tagger_name,
                 nn.account, nn.date,
                 nn.recipient, nn.description, nn.value, nn.tag]


class ResizeMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize_callbacks = []

    def resizeEvent(self, event):
        width = self.size().width()
        for f in self.resize_callbacks:
            f(width=width)
        QMainWindow.resizeEvent(self, event)


class MultiAccountTable(QWidget):
    def __init__(self, parent, main, get_first_row_color=None, double_click_action=None):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.double_click_action = double_click_action
        self.get_first_row_color = get_first_row_color

        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(TABLE_COLUMNS))
        self.table_widget.setHorizontalHeaderLabels(TABLE_COLUMNS)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setColumnHidden(0, True)
        self.table_widget.setColumnHidden(1, True)
        self.table_widget.setColumnWidth(2, 100)
        self.table_widget.setColumnWidth(3, 80)
        self.table_widget.setColumnWidth(4, 280)
        self.table_widget.setColumnWidth(5, 735)
        self.table_widget.setColumnWidth(6, 80)
        self.table_widget.setColumnWidth(7, 150)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # add actions and callbacks
        self.main.resize_callbacks += [self.resize_window]
        if double_click_action is not None:
            self.table_widget.doubleClicked.connect(self.row_selected)

    def row_selected(self, item):
        row_dict = dict()
        i_row = item.row()
        for i_col, col in enumerate(TABLE_COLUMNS):
            row_dict[col] = self.table_widget.item(i_row, i_col).text()
        self.double_click_action(row_dict)

    def resize_window(self, width):
        additional_width = max(width - 1500, -200)
        additional_width = int(additional_width/2)
        self.table_widget.setColumnWidth(4, 280+additional_width)
        self.table_widget.setColumnWidth(5, 735+additional_width)

    def update_table(self):
        df = self.main.multi_account_df
        if df is None:
            self.table_widget.setRowCount(0)
            return
        # Reset sorting such that transactin_id is during start always first
        self.table_widget.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(len(df))

        first_row_color = None
        if self.get_first_row_color is not None:
            first_row_color = self.get_first_row_color()

        for col in TABLE_COLUMNS:
            assert col in df.columns

        for i, row in df.reset_index(drop=True).iterrows():
            for j, col in enumerate(TABLE_COLUMNS):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                elif isinstance(row[col], datetime.datetime):
                    item = QTableWidgetItem(str(row[col].strftime("%d.%m.%Y")))
                else:
                    item = QTableWidgetItem(str(row[col]))
                if first_row_color is not None and i == 0:
                    item.setBackground(QColor(*first_row_color))
                self.table_widget.setItem(i, j, item)

        self.table_widget.setSortingEnabled(True)

        logger.debug(f"table updated \n {df.head()}")
