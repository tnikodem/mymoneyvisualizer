import logging

import pyqtgraph as pg

from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtWidgets import QLabel, QListWidget, QAbstractItemView

# from mymoneyvisualizer.naming import Naming as nn

pg.setConfigOptions(antialias=True)

logger = logging.getLogger(__name__)


class AssignTagCategoryWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.layout = QVBoxLayout(self)

        self.layout.addWidget(QLabel("Income:", self))
        self.list_widget_income = QListWidget()
        self.list_widget_income.setFixedWidth(150)
        # self.list_widget_income.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_income.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop)
        self.layout.addWidget(self.list_widget_income)
        self.layout.addWidget(QLabel("Expenses (Basic):", self))
        self.list_widget_basic = QListWidget()
        self.list_widget_basic.setFixedWidth(150)
        self.list_widget_basic.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection)
        # self.list_widget_basic.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_basic.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop)
        self.layout.addWidget(self.list_widget_basic)
        self.layout.addWidget(QLabel("Expenses (Optional):", self))
        self.list_widget_optional = QListWidget()
        self.list_widget_optional.setFixedWidth(150)
        # self.list_widget_optional.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.list_widget_optional.setDragDropMode(
            QAbstractItemView.DragDropMode.DragDrop)
        self.layout.addWidget(self.list_widget_optional)

        # Add actions
        self.main.add_update_callback(self.fill_list_elements)

        self.list_widget_basic.itemChanged.connect(self.basic_list_updated)
        self.list_widget_optional.itemChanged.connect(
            self.optional_list_updated)
        self.list_widget_income.itemChanged.connect(self.income_list_updated)

    def basic_list_updated(self, item):
        if self.main.updateing:
            return
        idx = self.list_widget_basic.indexFromItem(item)
        idx = idx.row()
        self.update_tag_categories(
            tag_name=item.text(), idx=idx, category="basic")

    def optional_list_updated(self, item):
        if self.main.updateing:
            return
        idx = self.list_widget_optional.indexFromItem(item)
        idx = idx.row()
        self.update_tag_categories(
            tag_name=item.text(), idx=idx, category="optional")

    def income_list_updated(self, item):
        if self.main.updateing:
            return
        idx = self.list_widget_income.indexFromItem(item)
        idx = idx.row()
        self.update_tag_categories(
            tag_name=item.text(), idx=idx, category="income")

    def update_tag_categories(self, tag_name, idx, category):
        tag_names_basic = []
        for x in range(self.list_widget_basic.count()):
            list_item = self.list_widget_basic.item(x)
            if (category == "basic" and x == idx) or list_item.text() != tag_name:
                tag_names_basic += [list_item.text()]

        tag_names_optional = []
        for x in range(self.list_widget_optional.count()):
            list_item = self.list_widget_optional.item(x)
            if (category == "optional" and x == idx) or list_item.text() != tag_name:
                tag_names_optional += [list_item.text()]

        tag_names_income = []
        for x in range(self.list_widget_income.count()):
            list_item = self.list_widget_income.item(x)
            if (category == "income" and x == idx) or list_item.text() != tag_name:
                tag_names_income += [list_item.text()]

        new_sorted_tags = dict(
            basic=tag_names_basic,
            optional=tag_names_optional,
            income=tag_names_income)

        self.main.update_category_and_sort(new_sorted_tags=new_sorted_tags)

    def fill_list_elements(self):
        self.list_widget_income.clear()
        self.list_widget_basic.clear()
        self.list_widget_optional.clear()

        df = self.main.df_summary
        if df is None or len(df) < 1:
            return

        for tag_cat in self.main.config.tag_categories.get():
            if tag_cat.category != "basic":
                continue
            if tag_cat.name not in df.columns:
                continue
            self.list_widget_basic.addItem(tag_cat.name)

        for tag_cat in self.main.config.tag_categories.get():
            if tag_cat.category != "optional":
                continue
            if tag_cat.name not in df.columns:
                continue
            self.list_widget_optional.addItem(tag_cat.name)

        for tag_cat in self.main.config.tag_categories.get():
            if tag_cat.category != "income":
                continue
            if tag_cat.name not in df.columns:
                continue
            self.list_widget_income.addItem(tag_cat.name)
