import logging
import datetime
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QHBoxLayout
from PyQt6.QtWidgets import QComboBox, QLabel, QLineEdit

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.summary_table import SummaryTableWidget
from mymoneyvisualizer.windows.widgets.select_exclude_tags import SelectExcludeTags


logger = logging.getLogger(__name__)


class SummaryWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.layout = QVBoxLayout(self)

        layout_control_buttons = QHBoxLayout()

        # Month selection
        self.start_month_label = QLabel("Start Month:", self)
        layout_control_buttons.addWidget(self.start_month_label)
        self.start_month_combobox = QComboBox()
        layout_control_buttons.addWidget(self.start_month_combobox)
        self.end_month_label = QLabel("End Month:", self)
        layout_control_buttons.addWidget(self.end_month_label)
        self.end_month_combobox = QComboBox()
        layout_control_buttons.addWidget(self.end_month_combobox)
        time = datetime.datetime.now()
        time = datetime.datetime(time.year, time.month, 1)
        for i in range(0, 12*12):
            self.start_month_combobox.addItem(time.strftime('%Y-%m'))
            self.end_month_combobox.addItem(time.strftime('%Y-%m'))
            time = time - datetime.timedelta(days=2)
            time = datetime.datetime(time.year, time.month, 1)
        self.end_month_combobox.setCurrentIndex(1)
        self.start_month_combobox.setCurrentIndex(11)

        # Exclude tags
        self.multi_select = SelectExcludeTags(self, main)
        self.multi_select.setFixedWidth(250)
        layout_control_buttons.addWidget(self.multi_select)

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

        # Filter tags
        self.filter_tag_label = QLabel("Filter Tag:", self)
        self.filter_tag_label.setFixedWidth(50)
        layout_control_buttons.addWidget(self.filter_tag_label)
        self.filter_tag_textbox = QLineEdit(self)
        self.filter_tag_textbox.setFixedWidth(175)
        layout_control_buttons.addWidget(self.filter_tag_textbox)

        layout_control_buttons.addStretch()

        self.layout.addLayout(layout_control_buttons)

        # Summary Table
        self.table = SummaryTableWidget(parent=self, main=self.main)
        self.layout.addWidget(self.table, 1)

        # Actions
        self.start_month_combobox.currentTextChanged.connect(self.main.set_date_from)
        self.end_month_combobox.currentTextChanged.connect(self.main.set_date_upto)
        self.tag_level_combobox.currentIndexChanged.connect(self.main.tag_level_changed)
        self.filter_tag_textbox.textChanged.connect(self.main.set_tag_filter)


class WindowSummaryTable(QMainWindow):
    def __init__(self, parent, config, detail_month_window):
        super(WindowSummaryTable, self).__init__(parent)
        self.config = config
        self.detail_month_window = detail_month_window

        self.sort_column = nn.total
        self.sort_order = 0

        time = datetime.datetime.now()
        time = datetime.datetime(time.year, time.month, 1)
        self.date_upto = time
        for i in range(12):
            time = time - datetime.timedelta(days=2)
            time = datetime.datetime(time.year, time.month, 1)
        self.date_from = time

        self.excluded_tags = set()
        self.update_callbacks = []

        self.tag_filter = ""
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

    def set_tag_filter(self, text):
        self.tag_filter = text
        self.run_update_callbacks()

    def set_date_from(self, date_str):
        date = datetime.datetime.strptime(date_str, "%Y-%m")
        date_from = datetime.datetime(date.year, date.month, 1)
        if date_from >= self.date_upto:
            date_upto = date + datetime.timedelta(days=2)
            self.date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        self.date_from = date_from
        self.run_update_callbacks()

    def set_date_upto(self, date_str):
        date = datetime.datetime.strptime(date_str, "%Y-%m")
        date_upto = date + datetime.timedelta(days=32)
        date_upto = datetime.datetime(date_upto.year, date_upto.month, 1)
        if date_upto <= self.date_from:
            date_from = date_upto - datetime.timedelta(days=2)
            self.date_from = datetime.datetime(date_from.year, date_from.month, 1)
        self.date_upto = date_upto
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

    # TODO unittest this method

    def get_summary_df(self):

        if self.date_from is None or self.date_upto is None:
            return
        df = self.config.accounts.get_summary_df(date_from=self.date_from, date_upto=self.date_upto)
        if df is None:
            return
        # Filter df
        if self.tag_filter != "":
            df = df[df[nn.tag].str.startswith(self.tag_filter)]
        if len(self.excluded_tags) > 0:
            df = df[~(df[nn.tag].isin(self.excluded_tags))]
        if len(df) < 1:
            return

        df[nn.tag] = df[nn.tag].apply(self.get_base_tag)

        # Calculate pivot table
        dfg = df.groupby([nn.tag, pd.Grouper(freq="1ME", key=nn.date)], as_index=False).agg({nn.value: "sum"})
        dfp = dfg.pivot(index=nn.date, columns=nn.tag, values="value")
        timeseries_complete_range = pd.date_range(start=self.date_from, end=self.date_upto, freq="1ME")
        dfp = dfp.reindex(timeseries_complete_range).resample("1ME").sum()
        dfp = dfp.T
        n_month = len(dfp.columns)
        dfp[nn.total] = dfp.sum(axis=1)
        dfp["monthly average"] = dfp[nn.total] / n_month
        dfp = dfp.reset_index()

        for col in dfp.columns:
            if isinstance(col, datetime.datetime):
                col_str = col.strftime("%Y-%m")
            else:
                col_str = str(col)
            if col_str == self.sort_column:
                dfp = dfp.sort_values(by=col, ascending=self.sort_order == 0)
                break

        # Calculate Total expenses
        df_total = pd.DataFrame({**dfp.sum().to_dict()}, index=[nn.total])
        df_total[nn.tag] = nn.total

        df_combined = pd.concat([dfp, df_total])

        return df_combined
