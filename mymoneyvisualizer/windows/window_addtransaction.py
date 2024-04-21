# -*- coding: utf-8 -*-

import logging
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton, QCalendarWidget
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn


logger = logging.getLogger(__name__)


class MyAddTransWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.account_name = None

        # Create calendar "transaction date"
        self.calendar_widget = QCalendarWidget(self)
        self.calendar_widget.setGridVisible(False)
        self.calendar_widget.resize(250, 250)
        self.calendar_widget.move(25, 10)

        # Create textbox "recipient"
        self.rec_label = QLabel(self)
        self.rec_label.setText('Recipient:')
        self.rec_label.move(300, 10)
        self.rec_textbox = QLineEdit(self)
        self.rec_textbox.move(300, 30)
        self.rec_textbox.resize(200, 40)

        # Create textbox "description"
        self.des_label = QLabel(self)
        self.des_label.setText('Description:')
        self.des_label.move(300, 80)
        self.des_textbox = QLineEdit(self)
        self.des_textbox.move(300, 100)
        self.des_textbox.resize(200, 40)

        # Create textbox "value"
        self.value_label = QLabel(self)
        self.value_label.setText('Value:')
        self.value_label.move(300, 150)
        self.value_textbox = QLineEdit(self)
        self.value_textbox.move(300, 170)
        self.value_textbox.resize(200, 40)

        # Create button "Add"
        self.add_button = QPushButton('Add', self)
        self.add_button.move(300, 230)
        self.add_button.resize(250, 32)
        self.add_button.clicked.connect(self.save)

        self.msg_label = QLabel(self)
        self.msg_label.move(25, 300)
        self.msg_label.resize(500, 30)

        # actions and callbacks
        self.calendar_widget.activated.connect(self.rec_textbox.setFocus)

    def key_pressed(self, key):
        if key == Qt.Key.Key_Escape:
            self.parent().close()
        elif key == Qt.Key.Key_Up:
            if self.calendar_widget.hasFocus():
                pass
            else:
                self.focusPreviousChild()
        elif key == Qt.Key.Key_Down:
            if self.calendar_widget.hasFocus():
                pass
            elif self.value_textbox.hasFocus():
                pass
            else:
                self.focusNextChild()
        elif key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            if self.value_textbox.hasFocus():
                self.save()
            else:
                self.focusNextChild()

    def open(self, account_name):
        self.account_name = account_name
        account = self.main.get_account(account_name=account_name)

        self.msg_label.setText('')

        # TODO do not create always new compelter, update?!
        rec_completer = QCompleter(account.get_unique(nn.recipient))
        rec_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        rec_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.rec_textbox.setCompleter(rec_completer)
        des_completer = QCompleter(account.get_unique(nn.description))
        des_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        des_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.des_textbox.setCompleter(des_completer)

    def save(self):
        try:
            date = pd.to_datetime(self.calendar_widget.selectedDate().toPyDate())
            value = float(self.value_textbox.text())
        except Exception as e:
            logger.error(e)
            self.msg_label.setText("Could not save: " + str(e))
            return

        account = self.main.get_account(account_name=self.account_name)
        account.add_entry(date=date, recipient=self.rec_textbox.text(),
                          description=self.des_textbox.text(), value=value)

        self.rec_textbox.clear()
        self.rec_textbox.setFocus()
        self.des_textbox.clear()
        self.value_textbox.clear()

        self.msg_label.setText(f"Saved entry. Total entries in account: {len(account)}")


class WindowAddTransaction(QMainWindow):
    def __init__(self, parent, config):
        super(WindowAddTransaction, self).__init__(parent)
        self.config = config
        self.left = 300
        self.top = 300
        self.width = 600
        self.height = 400
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.addtrans_widget = MyAddTransWidget(parent=self, main=self)
        self.addtrans_widget.resize(550, 350)
        self.addtrans_widget.move(0, 30)

    def open_addtrans(self, account_name):
        logger.debug("open window_addtransaction")
        self.setWindowTitle(f"Add Transaction in {account_name}")
        self.addtrans_widget.open(account_name=account_name)
        self.show()

    def keyPressEvent(self, e):
        self.addtrans_widget.key_pressed(e.key())

    def get_account(self, account_name):
        return self.config.accounts.get_by_name(account_name)


