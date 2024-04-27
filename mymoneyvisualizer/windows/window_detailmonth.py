# -*- coding: utf-8 -*-

import logging

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.multi_account_table import MultiAccountTable, ResizeMainWindow

logger = logging.getLogger(__name__)


class DetailMonthWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.layout = QVBoxLayout(self)
        self.multi_account_table = MultiAccountTable(
            self, main=self.main, double_click_action=self.main.open_tagger_window)
        self.layout.addWidget(self.multi_account_table)

        # add callbacks
        self.main.config.accounts.add_update_callback(self.update)

    def update(self):
        logger.debug("update")
        self.main.get_multi_account_df()
        self.multi_account_table.update_table()


class WindowDetailMonth(ResizeMainWindow):
    def __init__(self, parent, config):
        super().__init__()
        self.main_window = parent
        self.config = config
        self.month = None
        self.tag = None
        self.multi_account_df = None

        self.left = 100
        self.top = 100
        self.width = 1500
        self.height = 900
        self.setGeometry(self.left, self.top, self.width, self.height)
        layout = QVBoxLayout()
        self.label_widget = QLabel()
        layout.addWidget(self.label_widget)
        self.detailmonth_widget = DetailMonthWidget(parent=self, main=self)
        layout.addWidget(self.detailmonth_widget)

        # Window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def get_multi_account_df(self):
        logger.debug("requesting filtered df")
        if self.tag is None or self.month is None:
            return None
        df = self.config.accounts.get_base_tag_df(base_tag=self.tag)
        if df is None or len(df) < 1:
            return None
        df = df.loc[df[nn.date].astype(str).str.slice(0, 7) == self.month, :]
        df = df.sort_values([nn.date]).reset_index(drop=True)
        logger.debug(f"return filtered df with len {len(df)}")
        self.multi_account_df = df

    def open_detailmonth(self, month, tag):
        self.month = month
        self.tag = tag
        logger.debug(f"opening month {month}: {tag}")
        self.label_widget.setText(f"All transaction in {month} for {tag}:")
        self.setWindowTitle(f"{tag} in {month}")
        self.detailmonth_widget.update()
        self.show()

    def open_tagger_window(self, row_dict):
        print(row_dict)
        self.main_window.tagger_window.open_or_create_tagger(tagger_name=row_dict[nn.tagger_name],
                                                             transaction_id=row_dict[nn.transaction_id])
