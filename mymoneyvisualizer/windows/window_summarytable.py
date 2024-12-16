import logging
import datetime
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QPushButton, QComboBox, QLabel

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.summary_table import SummaryTableWidget
from mymoneyvisualizer.windows.widgets.select_exclude_tags import SelectExcludeTags


logger = logging.getLogger(__name__)


class SummaryWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.layout = QVBoxLayout(self)

        # Month selection
        layout_control_buttons = QHBoxLayout()
        self.button_before = QPushButton('previous month', self)
        self.button_before.setFixedWidth(250)
        layout_control_buttons.addWidget(self.button_before)
        self.button_after = QPushButton('next month', self)
        self.button_after.setFixedWidth(250)
        layout_control_buttons.addWidget(self.button_after)

        # Set tag level
        self.tag_level_label = QLabel("Tag Level:", self)
        self.tag_level_label.setFixedWidth(50)
        layout_control_buttons.addWidget(self.tag_level_label)
        self.tag_level_combobox = QComboBox()
        self.tag_level_combobox.addItem('Base')
        self.tag_level_combobox.addItem('One')
        self.tag_level_combobox.addItem('Two')
        self.tag_level_combobox.addItem('Three')
        layout_control_buttons.addWidget(self.tag_level_combobox)

        # Exclude tags
        self.multi_select = SelectExcludeTags(self, main)
        self.multi_select.setFixedWidth(250)
        layout_control_buttons.addWidget(self.multi_select)

        layout_control_buttons.addStretch()

        self.layout.addLayout(layout_control_buttons)

        self.table = SummaryTableWidget(parent=self, main=self.main, type="all")
        self.layout.addWidget(self.table, 1)

        self.table_total = SummaryTableWidget(parent=self, main=self.main, type="total")
        self.layout.addWidget(self.table_total)

        # Actions
        self.button_before.clicked.connect(self.main.month_before)
        self.button_after.clicked.connect(self.main.month_after)

        self.tag_level_combobox.currentIndexChanged.connect(self.main.tag_level_changed)


class WindowSummaryTable(QMainWindow):
    def __init__(self, parent, config, detail_month_window):
        super(WindowSummaryTable, self).__init__(parent)
        self.config = config
        self.detail_month_window = detail_month_window

        self.summary_df_all = None
        self.summary_df_total = None

        self.excluded_tags = set()
        self.update_callbacks = [self.update_summary_df]
        now = datetime.datetime.now()
        date_upto = datetime.datetime(now.year, now.month, 1) + datetime.timedelta(days=32)
        self.date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        self.date_from = datetime.datetime(date_upto.year - 1, date_upto.month, 1)

        self.tag_level = 0

        self.left = 50
        self.top = 50
        self.width = 1700
        self.height = 800
        self.setWindowTitle("Summary")
        self.setGeometry(self.left, self.top, self.width, self.height)

        layout = QVBoxLayout()
        self.summary_widget = SummaryWidget(parent=self, main=self)
        layout.addWidget(self.summary_widget)

        # Window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    # TODO move callbacks in seperate class

    def add_update_callback(self, func):
        self.update_callbacks += [func]

    def run_update_callbacks(self):
        for func in self.update_callbacks:
            func()

    def set_excluded_tags(self, tags):
        self.excluded_tags = set(tags)
        self.run_update_callbacks()

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

    def tag_level_changed(self, index):
        if index == self.tag_level:
            return
        self.tag_level = index
        self.run_update_callbacks()

    def open_detailmonth(self, month, tag):
        self.detail_month_window.open_detailmonth(month=month, tag=tag)

    def get_base_tag(self, tag):
        tag = str(tag)
        tags = tag.split(".")
        if self.tag_level == 0:
            tag_out = tags[0]
        else:
            tag_out = ".".join(tags[0:self.tag_level+1])
        return tag_out

    def summary_df(self, type):
        if type == "all":
            return self.summary_df_all
        elif type == "total":
            return self.summary_df_total

    # TODO unittest method

    def update_summary_df(self):
        logger.debug(f"request summary df from {self.date_from} upto {self.date_upto}")

        df = self.config.accounts.get_summary_df(date_from=self.date_from, date_upto=self.date_upto)
        if df is None:
            return None
        if len(self.excluded_tags) > 0:
            df = df[~(df[nn.tag].isin(self.excluded_tags))]
        if len(df) < 1:
            return None

        df[nn.tag] = df[nn.tag].apply(self.get_base_tag)

        # Calculate pivot table
        dfg = df.groupby([nn.tag, pd.Grouper(freq="1ME", key=nn.date)], as_index=False).agg({nn.value: "sum"})
        dfp = dfg.pivot(index=nn.date, columns=nn.tag, values="value")
        timeseries_complete_range = pd.date_range(start=self.date_from, end=self.date_upto, freq="1ME")
        dfp = dfp.reindex(timeseries_complete_range).resample("1ME").sum()
        dfp = dfp.T
        dfp["total"] = dfp.sum(axis=1)
        dfp["monthly average"] = dfp["total"] / len(dfp.columns)
        dfp = dfp.reset_index()
        self.summary_df_all = dfp

        # Calculate Total expenses
        df_total = pd.DataFrame({**dfp.sum().to_dict()}, index=["total"])
        df_total[nn.tag] = "total"
        self.summary_df_total = df_total

        return dfp
