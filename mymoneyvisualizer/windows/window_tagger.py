# -*- coding: utf-8 -*-
import logging
from enum import Enum
import pandas as pd

from PyQt6.QtWidgets import QWidget, QMainWindow, QVBoxLayout, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem
from PyQt6.QtWidgets import QAbstractItemView
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor

from mymoneyvisualizer.naming import Naming as nn

logger = logging.getLogger(__name__)


DEFAULT_BACKGROUND_COLOR = (255, 255, 255)
GREEN_BACKGROUND_COLOR = (203, 255, 179)
RED_BACKGROUND_COLOR = (255, 122, 111)


class WindowModes(Enum):
    tagger = 1
    one_time_tag = 2


class TaggerDefinition(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        # Tagger definition
        self.layout_tagger_definition = QVBoxLayout()
        # Create textbox "name"
        self.name_label = QLabel("Name:", self)
        self.layout_tagger_definition.addWidget(self.name_label)
        self.name_textbox = QLineEdit(self)
        self.name_textbox.setFixedWidth(200)
        self.layout_tagger_definition.addWidget(self.name_textbox)
        # Create textbox "regex recipient"
        self.recipient_regex_label = QLabel("Recipient Regex:", self)
        self.layout_tagger_definition.addWidget(self.recipient_regex_label)
        self.recipient_regex_textbox = QLineEdit(self)
        self.recipient_regex_textbox.setMinimumWidth(200)
        self.layout_tagger_definition.addWidget(self.recipient_regex_textbox)
        # Create textbox "regex description"
        self.description_regex_label = QLabel("Description Regex:", self)
        self.layout_tagger_definition.addWidget(self.description_regex_label)
        self.description_regex_textbox = QLineEdit(self)
        self.description_regex_textbox.setMinimumWidth(200)
        self.layout_tagger_definition.addWidget(self.description_regex_textbox)
        self.setLayout(self.layout_tagger_definition)


class MyTableWidgetMultiAccount(QWidget):
    # TODO refactor and combine with account Tablewidget?!
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.columns = [nn.transaction_id, nn.account, nn.date, nn.recipient,
                        nn.description, nn.value, nn.tag]
        self.table_widget = QTableWidget()
        self.table_widget.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table_widget.setColumnCount(len(self.columns))
        self.table_widget.setHorizontalHeaderLabels(self.columns)
        self.table_widget.verticalHeader().setVisible(False)
        self.table_widget.setColumnHidden(0, True)
        self.table_widget.setColumnWidth(1, 100)
        self.table_widget.setColumnWidth(2, 80)
        self.table_widget.setColumnWidth(3, 280)
        self.table_widget.setColumnWidth(4, 735)
        self.table_widget.setColumnWidth(5, 80)
        self.table_widget.setColumnWidth(6, 150)
        self.table_widget.verticalHeader().setDefaultSectionSize(60)
        self.table_widget.horizontalHeader().setStretchLastSection(True)
        self.layout = QVBoxLayout(self)
        self.layout.addWidget(self.table_widget)
        self.setLayout(self.layout)
        self.main.resize_callbacks += [self.resize_window]

    def resize_window(self, width):
        additional_width = max(width - 1500, -200)
        additional_width = int(additional_width/2)
        self.table_widget.setColumnWidth(3, 280+additional_width)
        self.table_widget.setColumnWidth(4, 735+additional_width)

    def update_table(self):
        if self.main.mask_recipient_matches is None or self.main.mask_description_matches is None:
            first_row_color = QColor(*DEFAULT_BACKGROUND_COLOR)
        elif self.main.mask_recipient_matches and self.main.mask_description_matches:
            first_row_color = QColor(*GREEN_BACKGROUND_COLOR)
        else:
            first_row_color = QColor(*RED_BACKGROUND_COLOR)

        df = self.main.filtered_df
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
                if i == 0:
                    item.setBackground(first_row_color)
                self.table_widget.setItem(i, j, item)

        logger.debug(f"table updated \n {df.head()}")


class MyTaggerWidget(QWidget):
    def __init__(self, parent, main):
        super(QWidget, self).__init__(parent)
        self.main = main
        self.mode = WindowModes.tagger
        self.layout = QVBoxLayout(self)

        layout_control_buttons = QHBoxLayout()

        # Control buttons
        self.button_ok = QPushButton('OK', self)
        self.button_ok.setFixedWidth(150)
        layout_control_buttons.addWidget(self.button_ok)
        self.button_cancel = QPushButton('Cancel', self)
        self.button_cancel.setFixedWidth(150)
        layout_control_buttons.addWidget(self.button_cancel)
        # Tag
        layout_control_buttons.addWidget(QLabel("Tag:    ", self))
        self.tag_textbox = QLineEdit(self)
        self.tag_textbox.setMaximumWidth(200)
        layout_control_buttons.addWidget(self.tag_textbox)
        layout_control_buttons.addStretch()
        # One time tag toggle
        self.button_onetimetag = QPushButton('One time tag', self)
        self.button_onetimetag.setFixedWidth(150)
        layout_control_buttons.addWidget(self.button_onetimetag)

        self.layout.addLayout(layout_control_buttons)

        # Tagger Definition
        self.tagger_definition_widget = TaggerDefinition(self, main=self.main)
        self.layout.addWidget(self.tagger_definition_widget)

        # Create Table
        self.multi_account_table = MyTableWidgetMultiAccount(
            self, main=self.main)
        self.layout.addWidget(self.multi_account_table)

        # Actions
        self.button_ok.clicked.connect(self.save)
        self.button_cancel.clicked.connect(self.parent().close)
        self.button_onetimetag.clicked.connect(self.toggle_one_time_tag)

    def toggle_one_time_tag(self):
        if self.main.window_mode == WindowModes.tagger:
            self.button_onetimetag.setText("Tagger")
            self.tagger_definition_widget.setHidden(True)
            self.main.window_mode = WindowModes.one_time_tag
        else:
            self.button_onetimetag.setText("One time tag")
            self.tagger_definition_widget.setHidden(False)
            self.main.window_mode = WindowModes.tagger
        self.reload_widget()

    def update(self):
        logger.debug("update")
        self.main.get_filtered_df()

        if self.main.mask_recipient_matches is None:
            recipient_color = DEFAULT_BACKGROUND_COLOR
        elif self.main.mask_recipient_matches:
            recipient_color = GREEN_BACKGROUND_COLOR
        else:
            recipient_color = RED_BACKGROUND_COLOR

        if self.main.mask_description_matches is None:
            description_color = DEFAULT_BACKGROUND_COLOR
        elif self.main.mask_description_matches:
            description_color = GREEN_BACKGROUND_COLOR
        else:
            description_color = RED_BACKGROUND_COLOR

        # Update text elements
        self.tagger_definition_widget.name_textbox.setText(
            self.main.tagger.name)
        self.tagger_definition_widget.recipient_regex_textbox.setText(
            self.main.tagger.regex_recipient)
        self.tagger_definition_widget.recipient_regex_textbox.setStyleSheet(
            f"QLineEdit {{ background : rgb{recipient_color};}}")
        self.tagger_definition_widget.description_regex_textbox.setText(
            self.main.tagger.regex_description)
        self.tagger_definition_widget.description_regex_textbox.setStyleSheet(
            f"QLineEdit {{ background : rgb{description_color};}}")

        # Update tag completer
        # TODO every time create a new autocompleter??!! update compelte text of autocompleter instead if possible?!
        unique_tags = self.main.config.taggers.get_unique_tags()
        logger.debug(f"unique tags: {unique_tags}")
        tag_completer = QCompleter(unique_tags)
        self.tag_textbox.setText(self.main.tagger.tag)
        tag_completer.setFilterMode(Qt.MatchFlag.MatchContains)
        tag_completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_textbox.setCompleter(tag_completer)

        self.multi_account_table.update_table()

    def reload_widget(self):
        self.main.open_or_create_tagger(tagger_name=self.tagger_definition_widget.name_textbox.text(),
                                        description=self.tagger_definition_widget.description_regex_textbox.text(),
                                        recipient=self.tagger_definition_widget.recipient_regex_textbox.text(),
                                        tag=self.tag_textbox.text(),
                                        transaction_id=self.main.tagger.transaction_id,
                                        overwrite=True)

    def save(self):
        self.reload_widget()
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
        self.config = config
        self.window_mode = WindowModes.tagger
        self.tagger = None
        self.filtered_df = None
        self.mask_recipient_matches = None
        self.mask_description_matches = None

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

    def open_or_create_tagger(self, tagger_name="", description="", recipient="", tag="", transaction_id=None, overwrite=False):
        logger.debug(f"open or create {tagger_name}, {description}, {
                     recipient}, {tag}, {transaction_id}, overwrite {overwrite}")
        if overwrite and self.tagger is not None:
            if self.tagger.name != tagger_name:
                self.tagger.name = self.config.taggers.get_free_name(
                    tagger_name)
            self.tagger.regex_recipient = recipient
            self.tagger.regex_description = description
            self.tagger.tag = tag
            self.tagger.tranaction_id = transaction_id
        else:
            self.tagger = self.config.taggers.get_or_create(name=tagger_name, regex_description=description,
                                                            regex_recipient=recipient, tag=tag, transaction_id=transaction_id)

        self.setWindowTitle(self.tagger.name)
        self.tagger_widget.update()
        self.show()

    def get_filtered_df(self):
        df = self.config.accounts.get_filtered_df(self.tagger)
        if self.tagger.transaction_id is not None:
            mask = df[nn.transaction_id] == self.tagger.transaction_id
            if self.window_mode == WindowModes.one_time_tag:
                df = df.loc[mask]
            else:
                df = pd.concat([
                    df.loc[mask],
                    df.loc[~mask]
                ])

            self.mask_recipient_matches = self.tagger.mask_recipient(
                df=df.loc[:0]).values[0]
            self.mask_description_matches = self.tagger.mask_description(
                df=df.loc[:0]).values[0]
        else:
            self.mask_recipient_matches = None
            self.mask_description_matches = None
        self.filtered_df = df

    def save_tagger(self):
        self.tagger.save(self.config.taggers)

    def keyPressEvent(self, e):
        key = e.key()
        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_Enter or key == Qt.Key.Key_Return:
            self.tagger_widget.reload_widget()
