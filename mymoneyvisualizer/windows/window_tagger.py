# -*- coding: utf-8 -*-
import logging
from enum import Enum
import pandas as pd

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLineEdit, QLabel, QCompleter
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout
from PyQt6.QtCore import Qt

from mymoneyvisualizer.constants import DEFAULT_BACKGROUND_COLOR, GREEN_BACKGROUND_COLOR, RED_BACKGROUND_COLOR, GREY_BACKGROUND_COLOR

from mymoneyvisualizer.naming import Naming as nn
from mymoneyvisualizer.windows.widgets.multi_account_table import MultiAccountTable, ResizeMainWindow

logger = logging.getLogger(__name__)


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

        # Add actions
        self.recipient_regex_textbox.textChanged.connect(self.main.update)
        self.description_regex_textbox.textChanged.connect(self.main.update)


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
        self.multi_account_table = MultiAccountTable(
            self, main=self.main, get_first_row_color=self.get_first_row_color)
        self.layout.addWidget(self.multi_account_table)

        # Actions
        self.button_ok.clicked.connect(self.save)
        self.button_cancel.clicked.connect(self.parent().close)
        self.button_onetimetag.clicked.connect(self.toggle_one_time_tag)
        self.tag_textbox.textChanged.connect(self.main.update)

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

    def get_first_row_color(self):
        if self.main.mask_recipient_matches is None or self.main.mask_description_matches is None:
            first_row_color = GREY_BACKGROUND_COLOR
        elif self.main.mask_recipient_matches and self.main.mask_description_matches:
            first_row_color = GREEN_BACKGROUND_COLOR
        else:
            first_row_color = RED_BACKGROUND_COLOR
        return first_row_color

    def set_tagger_text(self, tagger):
        if self.tagger_definition_widget.name_textbox.text() != tagger.name:
            self.tagger_definition_widget.name_textbox.setText(tagger.name)
        if self.tagger_definition_widget.recipient_regex_textbox.text() != tagger.regex_recipient:
            self.tagger_definition_widget.recipient_regex_textbox.setText(
                tagger.regex_recipient)
        if self.tagger_definition_widget.description_regex_textbox.text() != tagger.regex_description:
            self.tagger_definition_widget.description_regex_textbox.setText(
                tagger.regex_description)

    def update(self):
        # Get and set color of elements
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

        self.tagger_definition_widget.recipient_regex_textbox.setStyleSheet(
            f"QLineEdit {{ background : rgb{recipient_color};}}")
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

        # Update table
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
        self.main.close()
        self.main.save_tagger()


class WindowTagger(ResizeMainWindow):
    def __init__(self, parent, config):
        super().__init__()
        self.config = config
        self.window_mode = WindowModes.tagger
        self.tagger = None
        self.multi_account_df = None
        self.mask_recipient_matches = None
        self.mask_description_matches = None
        self.updateing = False

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
        self.updateing = True
        logger.debug(
            f"open or create {tagger_name}, {description}, {recipient}, {tag}, {transaction_id}, overwrite {overwrite}")
        if overwrite and self.tagger is not None:
            if self.tagger.name != tagger_name:
                self.tagger.name = self.config.taggers.get_free_tagger_name(
                    tagger_name)
            self.tagger.regex_recipient = recipient
            self.tagger.regex_description = description
            self.tagger.tag = tag
            self.tagger.tranaction_id = transaction_id
        else:
            self.tagger = self.config.taggers.get_or_create(name=tagger_name, regex_description=description,
                                                            regex_recipient=recipient, tag=tag, transaction_id=transaction_id)

        self.setWindowTitle(self.tagger.name)
        self.get_multi_account_df()
        self.tagger_widget.set_tagger_text(tagger=self.tagger)
        self.tagger_widget.update()
        self.show()
        self.updateing = False

    def update(self):
        if self.updateing:
            return
        self.tagger_widget.reload_widget()
        self.updateing = False

    def get_multi_account_df(self):
        df = self.config.accounts.get_tagger_df(self.tagger)
        if self.tagger.transaction_id is not None:
            mask = df[nn.transaction_id] == self.tagger.transaction_id
            if self.window_mode == WindowModes.one_time_tag:
                df = df.loc[mask]
            else:
                df = pd.concat([
                    df.loc[mask],
                    df.loc[~mask]
                ])

            self.mask_recipient_matches = self.tagger.recipient_matches(
                test_string=df[nn.recipient].values[0])
            self.mask_description_matches = self.tagger.description_matches(
                test_string=df[nn.description].values[0])
        else:
            self.mask_recipient_matches = None
            self.mask_description_matches = None
        self.multi_account_df = df

    def save_tagger(self):
        if self.window_mode == WindowModes.one_time_tag:
            self.config.taggers.save_one_time_tag(
                tag=self.tagger.tag,
                transaction_id=self.tagger.transaction_id,
                accounts=self.config.accounts)
        else:
            self.tagger.save()
