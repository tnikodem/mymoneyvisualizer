# -*- coding: utf-8 -*-
import logging

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


class MyTableWidgetMultiAccount(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.columns = [nn.account, nn.date, nn.recipient, nn.description, nn.value, nn.tag]
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setColumnWidth(0, 100)
        self.table_widget.setColumnWidth(1, 80)
        self.table_widget.setColumnWidth(2, 180)
        self.table_widget.setColumnWidth(3, 516)
        self.table_widget.setColumnWidth(4, 80)
        self.table_widget.setColumnWidth(5, 150)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

    def update_table(self):
        df = self.main.get_filtered_df()
        self.table_widget.setRowCount(len(df))
        for i, row in df.iterrows():
            for j, col in enumerate(self.columns):
                if col not in row:
                    item = QTableWidgetItem("")
                elif isinstance(row[col], (int, float)):
                    item = QTableWidgetItem()
                    item.setData(Qt.ItemDataRole.EditRole, row[col])
                else:
                    item = QTableWidgetItem(str(row[col]))
                self.table_widget.setItem(i, j, item)

        logger.debug(f"table updated \n {df.head()}")


class MyTaggerWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main

        self.button_ok = QPushButton('OK', self)
        self.button_ok.resize(250, 32)
        self.button_ok.move(40, 0)
        self.button_ok.clicked.connect(self.save)

        self.button_update = QPushButton('Update', self)
        self.button_update.resize(250, 32)
        self.button_update.move(300, 0)
        self.button_update.clicked.connect(self.update_widget)

        self.button_cancel = QPushButton('Cancel', self)
        self.button_cancel.resize(250, 32)
        self.button_cancel.move(560, 0)
        self.button_cancel.clicked.connect(self.parent().close)

        # Create textbox "name"
        self.name_label = QLabel(self)
        self.name_label.setText('Name:')
        self.name_label.move(20, 50)
        self.name_textbox = QLineEdit(self)
        self.name_textbox.move(150, 50)
        self.name_textbox.resize(200, 40)
        # self.name_textbox.setReadOnly(True)

        # Create textbox "regex recipient"
        self.rec_regex_label = QLabel(self)
        self.rec_regex_label.setText('Recipient Regex:')
        self.rec_regex_label.move(20, 120)
        self.rec_regex_textbox = QLineEdit(self)
        self.rec_regex_textbox.move(150, 120)
        self.rec_regex_textbox.resize(200, 40)

        # Create textbox "regex description"
        self.des_regex_label = QLabel(self)
        self.des_regex_label.setText('Description Regex:')
        self.des_regex_label.move(600, 120)
        self.des_regex_textbox = QLineEdit(self)
        self.des_regex_textbox.move(750, 120)
        self.des_regex_textbox.resize(200, 40)

        # Create textbox "tag"
        self.tag_label = QLabel(self)
        self.tag_label.setText('Tag:')
        self.tag_label.move(20, 200)
        self.tag_textbox = QLineEdit(self)
        self.tag_textbox.move(150, 200)
        self.tag_textbox.resize(200, 40)

        # Create Table
        self.table = MyTableWidgetMultiAccount(self, main=self.main)
        self.table.resize(1200, 800)
        self.table.move(0, 250)

    def open(self):
        logger.debug("open")
        self.name_textbox.setText(self.main.tagger.name)
        self.rec_regex_textbox.setText(self.main.tagger.regex_recipient)
        self.des_regex_textbox.setText(self.main.tagger.regex_description)
        # TODO every time create a new autocompleter??!! make autocompleter nicer
        unique_tags = self.main.config.taggers.get_unique_tags()
        logger.debug(f"unique tags: {unique_tags}")
        tag_completer = QCompleter(unique_tags)
        self.tag_textbox.setText(self.main.tagger.tag)
        tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_textbox.setCompleter(tag_completer)

        self.table.update_table()

    def update_widget(self):
        self.main.open_or_create_tagger(tagger_name=self.name_textbox.text(),
                                        description=self.des_regex_textbox.text(),
                                        recipient=self.rec_regex_textbox.text(),
                                        tag=self.tag_textbox.text(),
                                        overwrite=True)

    def save(self):
        self.update_widget()
        self.parent().close()
        self.main.save_tagger()


class WindowTagger(QMainWindow):
    def __init__(self, parent, config):
        super(WindowTagger, self).__init__(parent)
        self.config = config
        self.left = 100
        self.top = 100
        self.width = 1500
        self.height = 900
        self.setGeometry(self.left, self.top, self.width, self.height)

        self.tagger_widget = MyTaggerWidget(parent=self, main=self)
        self.tagger_widget.resize(1400, 800)
        self.tagger_widget.move(0, 30)

        # properties
        self.tagger = None

    def open_or_create_tagger(self, tagger_name="", description="", recipient="", tag="", overwrite=False):
        logger.debug(f"open or create {tagger_name}, {description}, {recipient}, {tag}, overwrite {overwrite}")
        if overwrite and self.tagger is not None:
            if self.tagger.name != tagger_name:
                self.tagger.name = self.config.taggers.get_free_name(tagger_name)
            self.tagger.regex_recipient = recipient
            self.tagger.regex_description = description
            self.tagger.tag = tag
        else:
            self.tagger = self.config.taggers.get_or_create(name=tagger_name, regex_description=description,
                                                            regex_recipient=recipient, tag=tag)
        self.setWindowTitle(self.tagger.name)
        self.tagger_widget.open()
        self.show()

    def get_filtered_df(self):
        return self.config.accounts.get_filtered_df(self.tagger)

    def save_tagger(self):
        self.tagger.save(self.config.taggers)

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            self.tagger_widget.update_widget()
