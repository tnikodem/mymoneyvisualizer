# -*- coding: utf-8 -*-

import logging
import re
import datetime

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QCheckBox, QComboBox
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QDateEdit
from PyQt6.QtWidgets import QAbstractItemView

from PyQt6.QtCore import Qt, QDate 

from mymoneyvisualizer.naming import Naming as Nn
logger = logging.getLogger(__name__)


class MyTableWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.columns = [Nn.date, Nn.recipient, Nn.description, Nn.value, Nn.tag, Nn.tagger_name]
        self.table_widget = QTableWidget()
        self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.setColumnWidth(0, 80)
        self.table_widget.setColumnWidth(1, 180)
        self.table_widget.setColumnWidth(2, 516)
        self.table_widget.setColumnWidth(3, 150)
        self.table_widget.setColumnWidth(4, 130)
        self.table_widget.setColumnWidth(5, 0)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.table_widget.verticalHeader().setVisible(False)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # actions and callback
        self.table_widget.doubleClicked.connect(self.open_or_create_new_tagger)

    def open_or_create_new_tagger(self, item):
        row = item.row()
        rec = re.escape(self.table_widget.item(row, 1).text())
        des = re.escape(self.table_widget.item(row, 2).text())
        tagger_name = self.table_widget.item(row, 5).text()
        self.main.open_tagger_window(tagger_name=tagger_name, recipient=rec, description=des)

    def update_table(self, df):
        if df is None or len(df) < 1:
            self.table_widget.setRowCount(0)
            return
        self.table_widget.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(self.columns):
                if col not in row:
                    item = QTableWidgetItem("")
                elif isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                elif isinstance(row[col], datetime.datetime):
                    item = QTableWidgetItem(str(row[col].strftime("%d.%m.%Y")))
                else:
                    item = QTableWidgetItem(str(row[col]))
                self.table_widget.setItem(i, j, item)


class MyImportDataWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.import_button = QPushButton('Import', self)
        self.import_button.resize(150, 40)
        self.import_button.move(1000, 70)
        self.import_button.clicked.connect(self.main.save)

        # Create textbox "Seperator"
        self.label_sep = QLabel(self)
        self.label_sep.setText('Seperator:')
        self.label_sep.move(20, 20)
        self.textbox_sep = QLineEdit(self)
        self.textbox_sep.setText(";")
        self.textbox_sep.move(85, 10)
        self.textbox_sep.resize(20, 30)
        self.textbox_sep.returnPressed.connect(self.reload)

        # Create textbox "Decimal"
        self.label_dec = QLabel(self)
        self.label_dec.setText('Decimal:')
        self.label_dec.move(120, 20)
        self.textbox_dec = QLineEdit(self)
        self.textbox_dec.setText(",")
        self.textbox_dec.move(175, 10)
        self.textbox_dec.resize(20, 30)
        self.textbox_dec.returnPressed.connect(self.reload)

        # Create textbox "Thousands"
        self.label_thou = QLabel(self)
        self.label_thou.setText('Thousands:')
        self.label_thou.move(207, 20)
        self.textbox_thou = QLineEdit(self)
        self.textbox_thou.setText(".")
        self.textbox_thou.move(275, 10)
        self.textbox_thou.resize(20, 30)
        self.textbox_thou.returnPressed.connect(self.reload)

        # Create textbox "Header Lines"
        self.label_nheader = QLabel(self)
        self.label_nheader.setText('Header Lines:')
        self.label_nheader.move(305, 20)
        self.textbox_nheader = QLineEdit(self)
        self.textbox_nheader.setText("13")
        self.textbox_nheader.move(388, 10)
        self.textbox_nheader.resize(50, 30)
        self.textbox_nheader.returnPressed.connect(self.reload)

        self.label_since = QLabel(self)
        self.label_since.setText('Since:')
        self.label_since.move(690, 20)
        self.dateedit = QDateEdit(self, calendarPopup=True)
        self.dateedit.resize(100, 30)
        self.dateedit.move(740, 10)
        self.dateedit.dateChanged.connect(self.reload)

        # Create textbox "Dayfirst"
        self.checkbox_dayfirst = QCheckBox('Day First', self)
        self.checkbox_dayfirst.move(455, 18)
        self.checkbox_dayfirst.setChecked(False)
        self.checkbox_dayfirst.stateChanged.connect(self.reload)

        # Create textbox "Drop duplicates"
        self.checkbox_drop_duplicates = QCheckBox('Drop Duplicates', self)
        self.checkbox_drop_duplicates.move(550, 17)
        self.checkbox_drop_duplicates.setChecked(True)
        self.checkbox_drop_duplicates.stateChanged.connect(self.reload)

        # Create textbox "Date Column"
        self.label_datecol = QLabel(self)
        self.label_datecol.setText('Date:')
        self.label_datecol.move(20, 60)
        self.combobox_datecol = QComboBox(self)
        self.combobox_datecol.move(20, 80)
        self.combobox_datecol.resize(200, 30)
        self.combobox_datecol.currentIndexChanged.connect(self.reload)

        # Create textbox "Recipient Column"
        self.label_reccol = QLabel(self)
        self.label_reccol.setText('Recipient:')
        self.label_reccol.move(240, 60)
        self.combobox_reccol = QComboBox(self)
        self.combobox_reccol.move(240, 80)
        self.combobox_reccol.resize(200, 30)
        self.combobox_reccol.currentIndexChanged.connect(self.reload)

        # Create textbox "Description Column"
        self.label_descol = QLabel(self)
        self.label_descol.setText('Description:')
        self.label_descol.move(480, 60)
        self.combobox_descol = QComboBox(self)
        self.combobox_descol.move(480, 80)
        self.combobox_descol.resize(200, 30)
        self.combobox_descol.currentIndexChanged.connect(self.reload)

        # Create textbox "Value Column"
        self.label_valuecol = QLabel(self)
        self.label_valuecol.setText('Value:')
        self.label_valuecol.move(700, 60)
        self.combobox_valuecol = QComboBox(self)
        self.combobox_valuecol.move(700, 80)
        self.combobox_valuecol.resize(200, 30)
        self.combobox_valuecol.currentIndexChanged.connect(self.reload)

        # Create Table
        self.table = MyTableWidget(parent=self, main=self.main)
        self.table.resize(1200, 700)
        self.table.move(10, 180)

    def reload(self):
        if self.main.loading:
            return
        config = {}
        config[Nn.seperator] = self.textbox_sep.text()
        config[Nn.decimal] = self.textbox_dec.text()
        config[Nn.thousands] = self.textbox_thou.text()
        try:
            config[Nn.skiprows] = int(self.textbox_nheader.text())
        except Exception as e:
            logger.error(e)
        config[Nn.import_since] = self.dateedit.dateTime().toPyDateTime()
        config[Nn.dayfirst] = self.checkbox_dayfirst.isChecked()
        config[Nn.col_date] = self.combobox_datecol.currentText()
        config[Nn.col_recipient] = self.combobox_reccol.currentText()
        config[Nn.col_description] = self.combobox_descol.currentText()
        config[Nn.col_value] = self.combobox_valuecol.currentText()
        config[Nn.drop_duplicates] = self.checkbox_drop_duplicates.isChecked()
        self.main.load_importer(config=config)

    def update_window_elements(self, importer):
        logger.debug(f"update window elements {importer}")
        available_columns = importer.available_columns
        self.combobox_datecol.clear()
        self.combobox_datecol.addItem("-")
        self.combobox_datecol.addItems(available_columns)
        for idx, col_name in enumerate(available_columns):
            if importer.col_date == col_name:
                self.combobox_datecol.setCurrentIndex(idx + 1)
                break

        self.combobox_reccol.clear()
        self.combobox_reccol.addItem("-")
        self.combobox_reccol.addItems(available_columns)
        for idx, col_name in enumerate(available_columns):
            if importer.col_recipient == col_name:
                self.combobox_reccol.setCurrentIndex(idx + 1)
                break

        self.combobox_descol.clear()
        self.combobox_descol.addItem("-")
        self.combobox_descol.addItems(available_columns)
        for idx, col_name in enumerate(available_columns):
            if importer.col_description == col_name:
                self.combobox_descol.setCurrentIndex(idx + 1)
                break

        self.combobox_valuecol.clear()
        self.combobox_valuecol.addItem("-")
        self.combobox_valuecol.addItems(available_columns)
        for idx, col_name in enumerate(available_columns):
            if importer.col_value == col_name:
                self.combobox_valuecol.setCurrentIndex(idx + 1)
                break

        self.textbox_sep.setText(importer.seperator)
        self.textbox_dec.setText(importer.decimal)
        self.textbox_thou.setText(importer.thousands)
        self.textbox_nheader.setText(str(importer.skiprows))
        self.checkbox_dayfirst.setChecked(importer.dayfirst)
        self.checkbox_drop_duplicates.setChecked(importer.drop_duplicates)

        if importer.import_since is not None:
            qt_date = QDate.fromString(importer.import_since.strftime("%d.%m.%Y"), 'dd.MM.yyyy')
            self.dateedit.setDate(qt_date)


class WindowImportData(QMainWindow):
    def __init__(self, parent, config, tagger_window):
        super(WindowImportData, self).__init__(parent)
        self.config = config
        self.tagger_window = tagger_window

        self.left = 100
        self.top = 100
        self.width = 1500
        self.height = 900
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.import_data_widget = MyImportDataWidget(parent=self, main=self)
        self.import_data_widget.resize(1400, 800)
        self.import_data_widget.move(0, 30)

        self.loading = False
        self.account_name = None
        self.filepath = None
        self.importer = None
        self.update_df = None

    def open_new_data(self, filepath, account_name):
        logger.debug(f"open new data window for {account_name} and {filepath}")
        self.filepath = filepath
        self.account_name = account_name
        self.setWindowTitle(f"Import  <{filepath}>  into  {self.account_name}")
        self.load_importer()
        self.show()

    def open_tagger_window(self, tagger_name, recipient, description):
        self.tagger_window.open_or_create_tagger(tagger_name=tagger_name, recipient=recipient, description=description)

    def save(self):
        if self.update_df is not None and len(self.update_df) > 0:
            self.close()
            account = self.config.accounts.get_by_name(self.account_name)
            account.update(self.update_df)
            self.importer.save()

    def load_importer(self, config=None):
        logger.debug(f"load importer with config {config}")
        if self.loading:
            return
        self.loading = True
        self.importer = self.config.importers.get_working_importer(filepath=self.filepath, config=config)
        account = self.config.accounts.get_by_name(self.account_name)
        self.update_df = self.importer.load_df(self.filepath, account)
        self.update_df = self.config.taggers.tag_df(self.update_df)
        self.import_data_widget.table.update_table(df=self.update_df)
        self.import_data_widget.update_window_elements(importer=self.importer)
        self.loading = False
