# -*- coding: utf-8 -*-

import logging
from PyQt6.QtWidgets import QMainWindow, QPushButton
from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout

from mymoneyvisualizer.windows.window_addtransaction import WindowAddTransaction
from mymoneyvisualizer.windows.window_tagger import WindowTagger
from mymoneyvisualizer.windows.window_taggeroverview import WindowTaggerOverview
from mymoneyvisualizer.windows.window_accounts import WindowAccounts
from mymoneyvisualizer.windows.window_detailmonth import WindowDetailMonth
from mymoneyvisualizer.windows.window_summarytable import WindowSummaryTable
from mymoneyvisualizer.windows.window_summarygraph import WindowSummaryGraph
from mymoneyvisualizer.windows.window_importdata import WindowImportData

logger = logging.getLogger(__name__)


class WindowMain(QMainWindow):

    def __init__(self, config):
        self.config = config
        super().__init__()
        logger.debug("starting main window")

        self.title = 'My Money Visualiser'
        self.left = 500
        self.top = 500
        self.width = 320
        self.height = 200
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.accounts_button = QPushButton('Accounts', self)
        self.accounts_button.resize(250, 32)
        self.accounts_button.move(40, 0)

        self.summary_button = QPushButton('Summary Table', self)
        self.summary_button.resize(250, 32)
        self.summary_button.move(40, 50)

        self.graph_button = QPushButton('Summary Graph', self)
        self.graph_button.resize(250, 32)
        self.graph_button.move(40, 100)

        # # TODO optimize window imports. Which window must be initialised here, which can also in subwindows?
        # # Make sure you still have the overview which window is connected to which
        self.addtrans_window = WindowAddTransaction(
            parent=self, config=self.config)
        self.tagger_window = WindowTagger(parent=self, config=self.config)
        self.importdata_window = WindowImportData(parent=self, config=self.config,
                                                  tagger_window=self.tagger_window)

        self.tagger_overview_window = WindowTaggerOverview(parent=self, config=self.config,
                                                           tagger_window=self.tagger_window)

        self.accounts_window = WindowAccounts(parent=self, config=self.config,
                                              tagger_window=self.tagger_window,
                                              tagger_overview_window=self.tagger_overview_window,
                                              addtrans_window=self.addtrans_window,
                                              importdata_window=self.importdata_window,
                                              )
        self.detail_month_window = WindowDetailMonth(
            parent=self, config=self.config)
        self.summary_window = WindowSummaryTable(parent=self, config=self.config,
                                                 detail_month_window=self.detail_month_window)
        self.summarygraph_window = WindowSummaryGraph(
            parent=self, config=self.config)

        # #actions
        self.accounts_button.clicked.connect(self.accounts_window.show)
        self.summary_button.clicked.connect(self.summary_window.show)
        self.graph_button.clicked.connect(self.summarygraph_window.show)

        logger.debug("starting main window finished")
        self.show()
