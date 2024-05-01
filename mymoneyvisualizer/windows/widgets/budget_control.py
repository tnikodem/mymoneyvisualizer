import logging
import datetime


import pyqtgraph as pg


from PyQt6.QtWidgets import QWidget, QHBoxLayout
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QLineEdit, QWidget, QComboBox
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.constants import DEFAULT_BACKGROUND_COLOR, RED_BACKGROUND_COLOR

pg.setConfigOptions(antialias=True)


logger = logging.getLogger(__name__)


class BudgetControl(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.updateing = False
        self.category = self.parent().category

        self.layout = QHBoxLayout(self)

        self.layout.addWidget(
            QLabel(f"<b>{self.category.title()}</b> Budget:", self))

        # Budget factor
        self.budget_factor_edit = QLineEdit(parent=self)
        self.budget_factor_edit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.budget_factor_edit.setFixedWidth(25)
        self.budget_factor_edit.setText(
            str(round(self.main.config.settings[nn.budget][self.category]["factor"]*100)))
        self.layout.addWidget(self.budget_factor_edit)
        self.label2 = QLabel("% of income", self)
        self.label2.setFixedWidth(70)
        self.layout.addWidget(self.label2)

        # Budget period
        ten_last_years = []
        current_year = datetime.datetime.now().year
        for i in range(10):
            ten_last_years += [current_year-i]

        self.layout.addWidget(QLabel("Budget period"))
        self.budget_period_start_combo = QComboBox()
        for year in ten_last_years:
            self.budget_period_start_combo.addItem(str(year))
        self.budget_period_start_combo.setFixedWidth(50)
        self.layout.addWidget(self.budget_period_start_combo)
        self.layout.addWidget(QLabel("-"))
        self.budget_period_end_combo = QComboBox()
        for year in ten_last_years:
            self.budget_period_end_combo.addItem(str(year))
        self.budget_period_end_combo.setFixedWidth(50)
        self.layout.addWidget(self.budget_period_end_combo)

        self.layout.addStretch()

        self.setLayout(self.layout)

        # add action
        self.budget_period_start_combo.currentTextChanged.connect(
            lambda x: self.update_budget_period(selected_year=x, is_start=True))
        self.budget_period_end_combo.currentTextChanged.connect(
            lambda x: self.update_budget_period(selected_year=x, is_start=False))
        self.budget_factor_edit.textChanged.connect(
            self.update_budget_factor_settings)

        # Add callbacks
        self.main.add_update_callback(
            self.update_budget_period_elements)

    def update_budget_period_elements(self):
        self.updateing = True
        start = self.main.config.settings[nn.budget]["basic"]["start"]
        end = self.main.config.settings[nn.budget]["basic"]["end"]
        self.budget_period_start_combo.setCurrentText(str(start))
        self.budget_period_end_combo.setCurrentText(str(end))
        self.updateing = False

    def update_budget_period(self, selected_year, is_start):
        if self.updateing:
            return
        if is_start:
            start = int(selected_year)
            end = int(self.budget_period_end_combo.currentText())
        else:
            start = int(self.budget_period_start_combo.currentText())
            end = int(selected_year)
        if start > end:
            start = int(selected_year)
            end = int(selected_year)
        self.main.update_budget_period(
            category=self.category, start=start, end=end)

    def update_budget_factor_settings(self, budget_percent):
        try:
            budget_percent = float(budget_percent)
            budget_factor = budget_percent / 100.
            assert budget_factor >= 0 and budget_factor <= 1
        except Exception as e:
            self.budget_factor_edit.setStyleSheet(
                f"QLineEdit {{ background : rgb{RED_BACKGROUND_COLOR};}}")
            return
        self.budget_factor_edit.setStyleSheet(
            f"QLineEdit {{ background : rgb{DEFAULT_BACKGROUND_COLOR};}}")

        self.main.update_budget_factor(
            category=self.category, budget_factor=budget_factor)
