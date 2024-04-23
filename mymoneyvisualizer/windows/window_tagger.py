# -*- coding: utf-8 -*-
import logging

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


class MyTableWidgetMultiAccount(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.columns = [nn.account, nn.date, nn.recipient,
                        nn.description, nn.value, nn.tag]
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setColumnWidth(0, 100)
        self.table_widget.setColumnWidth(1, 80)
        self.table_widget.setColumnWidth(2, 280)
        self.table_widget.setColumnWidth(3, 735)
        self.table_widget.setColumnWidth(4, 80)
        self.table_widget.setColumnWidth(5, 150)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.table_widget.horizontalHeader().setStretchLastSection(True)

        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)

        self.main.resize_callbacks += [self.resize_window]

    def resize_window(self, width):
        additional_width = max(width - 1500, -200)
        additional_width = int(additional_width/2)
        self.table_widget.setColumnWidth(2, 280+additional_width)
        self.table_widget.setColumnWidth(3, 735+additional_width)

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

        self.layout = QVBoxLayout(self)

        layout_control_buttons = QHBoxLayout()

        # Control buttons
        self.button_ok = QPushButton('OK', self)
        self.button_ok.setFixedWidth(150)
        layout_control_buttons.addWidget(self.button_ok)
        self.button_cancel = QPushButton('Cancel', self)
        self.button_cancel.setFixedWidth(150)
        layout_control_buttons.addWidget(self.button_cancel)
        layout_control_buttons.addStretch()
        self.layout.addLayout(layout_control_buttons)

        # Actions
        self.button_ok.clicked.connect(self.save)
        self.button_cancel.clicked.connect(self.parent().close)

        # Tagger definition
        layout_tagger_definition = QHBoxLayout()
        # Create textbox "name"
        self.name_label = QLabel("Name:", self)
        layout_tagger_definition.addWidget(self.name_label)
        self.name_textbox = QLineEdit(self)
        self.name_textbox.setFixedWidth(200)
        layout_tagger_definition.addWidget(self.name_textbox)
        # Create textbox "regex recipient"
        self.recipient_regex_label = QLabel("Recipient Regex:", self)
        layout_tagger_definition.addWidget(self.recipient_regex_label)
        self.recipient_regex_textbox = QLineEdit(self)
        self.recipient_regex_textbox.setMinimumWidth(200)
        layout_tagger_definition.addWidget(self.recipient_regex_textbox)
        # Create textbox "regex description"
        self.description_regex_label = QLabel("Description Regex:", self)
        layout_tagger_definition.addWidget(self.description_regex_label)
        self.description_regex_textbox = QLineEdit(self)
        self.description_regex_textbox.setMinimumWidth(200)
        layout_tagger_definition.addWidget(self.description_regex_textbox)
        # layout_tagger_definition.addStretch()
        self.layout.addLayout(layout_tagger_definition)

        # Tag
        layout_tag_definition = QHBoxLayout()
        layout_tag_definition.addWidget(QLabel("Tag:    ", self))
        self.tag_textbox = QLineEdit(self)
        self.tag_textbox.setMaximumWidth(200)
        layout_tag_definition.addWidget(self.tag_textbox)
        layout_tag_definition.addStretch()
        self.layout.addLayout(layout_tag_definition)

        # Create Table
        self.multi_account_table = MyTableWidgetMultiAccount(
            self, main=self.main)
        self.layout.addWidget(self.multi_account_table)

    def open(self):
        logger.debug("open")
        self.name_textbox.setText(self.main.tagger.name)
        self.recipient_regex_textbox.setText(self.main.tagger.regex_recipient)
        self.description_regex_textbox.setText(
            self.main.tagger.regex_description)
        # TODO every time create a new autocompleter??!! make autocompleter nicer
        unique_tags = self.main.config.taggers.get_unique_tags()
        logger.debug(f"unique tags: {unique_tags}")
        tag_completer = QCompleter(unique_tags)
        self.tag_textbox.setText(self.main.tagger.tag)
        tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_textbox.setCompleter(tag_completer)

        self.multi_account_table.update_table()

    def update_widget(self):
        self.main.open_or_create_tagger(tagger_name=self.name_textbox.text(),
                                        description=self.description_regex_textbox.text(),
                                        recipient=self.recipient_regex_textbox.text(),
                                        tag=self.tag_textbox.text(),
                                        overwrite=True)

    def save(self):
        self.update_widget()
        self.parent().close()
        self.main.save_tagger()


class MyMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.resize_callbacks = []

    def resizeEvent(self, event):
        width = self.size().width()
        for f in self.resize_callbacks:
            f(width=width)
        QMainWindow.resizeEvent(self, event)


class WindowTagger(MyMainWindow):
    def __init__(self, parent, config):
        super().__init__()
        # super(WindowTagger, self).__init__(parent)
        self.config = config
        self.tagger = None

        self.left = 100
        self.top = 100
        self.width = 1500
        self.height = 800
        self.setGeometry(self.left, self.top, self.width, self.height)

        layout = QVBoxLayout()
        self.tagger_widget = MyTaggerWidget(parent=self, main=self)
        layout.addWidget(self.tagger_widget)

        # Window
        widget = QWidget()
        widget.setLayout(layout)
        self.setCentralWidget(widget)

    def open_or_create_tagger(self, tagger_name="", description="", recipient="", tag="", overwrite=False):
        logger.debug(f"open or create {tagger_name}, {description}, {
                     recipient}, {tag}, overwrite {overwrite}")
        if overwrite and self.tagger is not None:
            if self.tagger.name != tagger_name:
                self.tagger.name = self.config.taggers.get_free_name(
                    tagger_name)
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
