# -*- coding: utf-8 -*-
import logging
from enum import Enum
import pandas as pd
import datetime

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)

GREY_BACKGROUND_COLOR = (123, 123, 123)
DEFAULT_BACKGROUND_COLOR = (255, 255, 255)
GREEN_BACKGROUND_COLOR = (203, 255, 179)
RED_BACKGROUND_COLOR = (255, 122, 111)


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
    def __init__(self, parent, main, color_first_row=False, double_click_action=None):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.double_click_action = double_click_action
        self.color_first_row = color_first_row

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
        self.table_widget.sortByColumn(-1, Qt.SortOrder.AscendingOrder)
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(len(df))

        # TODO add condotional coloring
        # if self.main.mask_recipient_matches is None or self.main.mask_description_matches is None:
        #     first_row_color = QColor(*DEFAULT_BACKGROUND_COLOR)
        # elif self.main.mask_recipient_matches and self.main.mask_description_matches:
        #     first_row_color = QColor(*GREEN_BACKGROUND_COLOR)
        # else:
        #     first_row_color = QColor(*RED_BACKGROUND_COLOR)

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
                if self.color_first_row and i == 0:
                    item.setBackground(QColor(*GREY_BACKGROUND_COLOR))
                self.table_widget.setItem(i, j, item)

        self.table_widget
        self.table_widget.setSortingEnabled(True)

        logger.debug(f"table updated \n {df.head()}")
