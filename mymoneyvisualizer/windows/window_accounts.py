# -*- coding: utf-8 -*-
import logging
import re
import datetime

from PyQt6.QtWidgets import QMainWindow, QVBoxLayout, QTabWidget, QLineEdit, QLabel
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QWidget, QPushButton, QMessageBox
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn


logger = logging.getLogger(__name__)


class MyTableWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.columns = [nn.transaction_id, nn.tagger_name,
                        nn.date, nn.recipient,
                        nn.description, nn.value, nn.tag]
        self.table_widget = QTableWidget()
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.setColumnHidden(0, True)
        self.table_widget.setColumnHidden(1, True)
        self.table_widget.setColumnWidth(2, 80)
        self.table_widget.setColumnWidth(3, 300)
        self.table_widget.setColumnWidth(4, 600)
        self.table_widget.setColumnWidth(5, 150)
        self.table_widget.setColumnWidth(6, 130)

        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.table_widget.verticalHeader().setVisible(False)

        # FIXME not working correctly??! update after sorting is enabled
        # self.table_widget.setSortingEnabled(True)
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        # add actions and callbacks
        self.table_widget.doubleClicked.connect(self.open_or_create_new_tagger)

    def update_table(self, df):
        if df is None or len(df) < 1:
            self.table_widget.setRowCount(0)
            return
        # FIXME in PyQt need to disable sorting while udpating ?!
        self.table_widget.setSortingEnabled(False)
        self.table_widget.setRowCount(len(df))
        for i, row in df.reset_index(drop=True).iterrows():
            for j, col in enumerate(self.columns):
                if isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                elif isinstance(row[col], datetime.datetime):
                    item = QTableWidgetItem(str(row[col].strftime("%d.%m.%Y")))
                else:
                    item = QTableWidgetItem(str(row[col]))
                self.table_widget.setItem(i, j, item)

        self.table_widget.setSortingEnabled(True)

    def get_columns(self):
        columns = dict()
        for i in range(self.table_widget.horizontalHeader().count()):
            columns[self.table_widget.horizontalHeaderItem(i).text()] = i
        return columns

    def open_or_create_new_tagger(self, item):
        row = item.row()

        columns = self.get_columns()
        recipient = self.table_widget.item(row, columns[nn.recipient]).text()
        description = self.table_widget.item(
            row, columns[nn.description]).text()
        tagger_name = self.table_widget.item(
            row, columns[nn.tagger_name]).text()
        transaction_id = self.table_widget.item(
            row, columns[nn.transaction_id]).text()

        self.main.open_tagger_window(
            tagger_name=tagger_name, recipient=recipient, description=description, transaction_id=transaction_id)


class SingleAccountWidget(QWidget):
    def __init__(self, parent, main, tab_index):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.tab_index = tab_index

        self.layout = QVBoxLayout(self)

        # Create textbox "Name"
        self.name_label = QLabel(self)
        self.name_label.setText('Name:')
        self.name_label.move(20, 20)
        self.name_textbox = QLineEdit(self)

        self.name_textbox.setText(self.main.get_account(self.tab_index).name)
        self.name_textbox.move(80, 20)
        self.name_textbox.resize(200, 40)
        self.name_textbox.returnPressed.connect(self.click_save)

        # Create Button "Import"
        self.import_button = QPushButton('Import', self)
        self.import_button.resize(250, 32)
        self.import_button.move(40, 100)
        self.import_button.clicked.connect(self.click_import)

        # Create Button "Save
        self.savebutton = QPushButton('Save', self)
        self.savebutton.resize(200, 32)
        self.savebutton.move(400, 100)
        self.savebutton.clicked.connect(self.click_save)

        # Create Button "Delete"
        self.deltransbutton = QPushButton('Delete Transaction', self)
        self.deltransbutton.resize(200, 32)
        self.deltransbutton.move(700, 100)
        self.deltransbutton.clicked.connect(self.click_delete_entry)

        # Create Button "Add"
        self.addtransbutton = QPushButton('Add Transaction', self)
        self.addtransbutton.resize(200, 32)
        self.addtransbutton.move(1000, 100)
        self.addtransbutton.clicked.connect(self.click_add_entry)

        # Create Table
        self.table = MyTableWidget(self, main=self.main)
        self.table.resize(1300, 700)
        self.table.move(30, 150)

        # actions and callbacks
        self.main.config.accounts.add_update_callback(self.update_view)

        self.update_view()

    def update_view(self):
        df = self.main.get_account_df(self.tab_index)
        self.table.update_table(df=df)

    def click_import(self):
        logger.debug("opening import window")
        self.main.open_importdata_window(account_index=self.tab_index)

    def click_save(self):
        logger.debug(f"saving account {self.tab_index}")
        acc_name = self.name_textbox.text()
        self.main.set_tab_text(index=self.tab_index, text=acc_name)
        account = self.main.get_account(self.tab_index)
        account.name = acc_name
        account.save()

    def click_add_entry(self):
        logger.debug(f"add entry for account {self.tab_index}")
        self.main.open_add_entry_window(account_index=self.tab_index)

    def click_delete_entry(self):
        rows = sorted(set(index.row()
                      for index in self.table.table_widget.selectedIndexes()))
        logger.debug(
            f"delete {len(rows)} entries for account {self.tab_index}")
        dates = []
        recs = []
        dess = []
        for row in rows:
            dates += [self.table.table_widget.item(row, 0).text()]
            recs += [self.table.table_widget.item(row, 1).text()]
            dess += [self.table.table_widget.item(row, 2).text()]
        for date, rec, des in zip(dates, recs, dess):
            # value = self.table.table_widget.item(row, 3).text()
            self.main.delete_entry(
                account_index=self.tab_index, date=date, recipient=rec, description=des)


class AccountsWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.n_tabs = 0
        self.layout = QVBoxLayout(self)
        # Initialize tab screen
        self.tabs = QTabWidget()
        self.tab_widgets = []
        self.tabs.resize(300, 200)
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
        for acc in self.main.config.accounts.get():
            self.add_tab(acc)

    def add_tab(self, account):
        idx = self.n_tabs
        logger.debug(f"adding tab for account {account.name} with index {idx}")
        tab = QWidget()
        self.tabs.addTab(tab, account.name)
        tab.layout = QVBoxLayout(self)
        saw = SingleAccountWidget(self, main=self.main, tab_index=idx)
        tab.layout.addWidget(saw)
        tab.setLayout(tab.layout)
        self.tab_widgets += [saw]
        self.n_tabs += 1


class WindowAccounts(QMainWindow):
    def __init__(self, parent, config,
                 tagger_window,
                 tagger_overview_window,
                 addtrans_window,
                 importdata_window):
        super(WindowAccounts, self).__init__(parent)
        self.config = config
        self.tagger_window = tagger_window
        self.tagger_overview_window = tagger_overview_window
        self.addtrans_window = addtrans_window
        self.importdata_window = importdata_window

        self.title = 'My Money Visualiser'
        self.left = 0
        self.top = 0
        self.width = 1370
        self.height = 1000
        self.setWindowTitle(self.title)
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.new_acc_button = QPushButton('New Account', self)
        self.new_acc_button.clicked.connect(self.create_new_account)
        self.new_acc_button.resize(250, 32)
        self.new_acc_button.move(40, 0)

        self.taggers_button = QPushButton('Taggers', self)
        self.taggers_button.clicked.connect(self.open_tagger_overview_window)
        self.taggers_button.resize(250, 32)
        self.taggers_button.move(340, 0)

        self.load_proj_button = QPushButton('Load Project', self)
        self.load_proj_button.clicked.connect(self.load_project)
        self.load_proj_button.resize(250, 32)
        self.load_proj_button.move(640, 0)

        self.save_proj_button = QPushButton('Save Project', self)
        self.save_proj_button.clicked.connect(self.save_project)
        self.save_proj_button.resize(250, 32)
        self.save_proj_button.move(940, 0)

        self.tab_widget = AccountsWidget(self, main=self)
        self.tab_widget.move(0, 50)
        self.tab_widget.resize(1360, 950)

    def create_new_account(self):
        new_account = self.config.accounts.add()
        self.tab_widget.add_tab(new_account)

    def open_tagger_window(self, tagger_name, recipient, description, transaction_id):
        recipient_regex = re.escape(recipient).replace(r"\ ", " ")
        description_regex = re.escape(description).replace(r"\ ", " ")
        self.tagger_window.open_or_create_tagger(tagger_name=tagger_name, recipient=recipient_regex,
                                                 description=description_regex, transaction_id=transaction_id)

    def open_tagger_overview_window(self):
        self.tagger_overview_window.open()

    def open_add_entry_window(self, account_index):
        account_name = self.get_account(account_index=account_index).name
        self.addtrans_window.open_addtrans(account_name=account_name)

    def delete_entry(self, account_index, date, recipient, description, force=False):
        account = self.get_account(account_index=account_index)
        df_del = account.get_entries(
            date=date, recipient=recipient, description=description)
        if len(df_del) < 1:
            return
        if not force:
            msg = f"Delete {date} - {recipient} - {description}? \n" \
                f"Affected entries: {len(df_del)}\n{df_del.head()}"
            reply = QMessageBox.question(
                self, 'Message', msg, QMessageBox.Yes, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return
        account.delete_entries(
            date=date, recipient=recipient, description=description)

    @staticmethod
    def open_file_dialog(parent):
        options = QFileDialog.Option.DontUseNativeDialog
        file_name, _ = QFileDialog.getOpenFileName(parent, "Import account file", "",
                                                   "All Files (*);;Csv Files (*.csv)", options=options)
        return file_name

    def open_importdata_window(self, account_index):
        account_name = self.get_account(account_index=account_index).name
        filepath = self.open_file_dialog(parent=self)
        if filepath is None or len(filepath) < 1:
            return
        self.importdata_window.open_new_data(
            filepath=filepath, account_name=account_name)

    def set_tab_text(self, index, text):
        self.tab_widget.tabs.setTabText(index, text)

    def get_account_df(self, index):
        account_name = self.config.accounts.get_by_index(index).name
        return self.config.accounts.get_combined_account_df(account_name=account_name)

    def get_account(self, account_index):
        return self.config.accounts.get_by_index(account_index)

    # added param to be compatible to PyQt interface
    def save_project(self, param=False, filepath=None):
        logger.debug("save project " + str(filepath))
        if filepath is None:
            proposed_name = "mmv_backup_" + \
                datetime.datetime.now().strftime("%Y_%m_%d__%H_%M_%S") + ".zip"
            options = QFileDialog.Option.DontUseNativeDialog
            filepath, _ = QFileDialog.getSaveFileName(self, "Save Project", proposed_name,
                                                      "Zip Files (*.zip)", options=options)
        if filepath:
            logger.debug("saving project as " + filepath)
            self.config.save(filepath=filepath)

    # added param to be compatible to PyQt interface
    def load_project(self, param=False, filepath=None):
        logger.debug("load project " + str(filepath))
        if filepath is None:
            options = QFileDialog.Option.DontUseNativeDialog
            filepath, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Zip Files (*.zip)",
                                                      options=options)
        if filepath:
            logger.debug("saving project as " + filepath)
            self.config.load(filepath=filepath)
