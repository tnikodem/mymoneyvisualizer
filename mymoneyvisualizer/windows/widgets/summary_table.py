import logging
import datetime

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor


logger = logging.getLogger(__name__)


class SummaryTableWidget(QWidget):
    def __init__(self, parent, main, type):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.type = type

        self.columns = []

        self.table_widget = QTableWidget()
        self.table_widget.setMinimumWidth(1350)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.verticalHeader().setVisible(False)
        # self.table_widget.verticalHeader().setDefaultSectionSize(30)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        if self.type == "total":
            self.table_widget.horizontalHeader().setVisible(False)
            self.table_widget.setFixedHeight(30)

        # always exactly 12 month (tag, months ... , total, monthly average)
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

        # Set Sorting after sorting is enabled!
        self.table_widget.horizontalHeader().setSortIndicator(14, Qt.SortOrder.AscendingOrder)

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
        df = self.main.summary_df(type=self.type)
        if df is None:
            self.table_widget.setRowCount(0)
            return
        self.table_widget.setSortingEnabled(False)

        self.columns = []
        for col in df.columns:
            if isinstance(col, datetime.datetime):
                self.columns += [col.strftime("%Y-%m")]
            else:
                self.columns += [str(col)]
        self.table_widget.setHorizontalHeaderLabels(self.columns)

        self.table_widget.setRowCount(len(df))
        for i, row in df.reset_index(drop=True).iterrows():
            for j, col in enumerate(df.columns):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, float(round(row[col], 0)))
                else:
                    item = QTableWidgetItem(str(row[col]))
                if self.type == "total" or col == "total" or col == "monthly average":
                    item.setBackground(QColor(0, 0, 0, 100))
                self.table_widget.setItem(i, j, item)

        self.table_widget.setSortingEnabled(True)
