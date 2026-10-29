"""Create or edit a tagger, or tag a single transaction. Nothing is saved before OK."""

from __future__ import annotations

import enum
import re

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIntValidator
from PyQt6.QtWidgets import (
    QCompleter,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mymoneyvisualizer.app import TAGGERS, TRANSACTIONS, InvalidTaggerError
from mymoneyvisualizer.domain.columns import ONE_TIME_TAGGER, Col
from mymoneyvisualizer.domain.models import Tagger, clean_recurring
from mymoneyvisualizer.domain.tagging import regex_error, tagger_matches
from mymoneyvisualizer.ui.common import GREEN, GREY, RED, Window, line_edit_style
from mymoneyvisualizer.ui.table_model import DATE, MONEY, NUMBER, TAG, Column, DataFrameModel, DataFrameView

PREVIEW_COLUMNS = [
    Column(Col.account, "account", width=110),
    Column(Col.date, "date", DATE, 90),
    Column(Col.recipient, "recipient", width=260),
    Column(Col.description, "description", width=520),
    Column(Col.value, "value", MONEY, 90),
    Column(Col.recurring, "recurring", NUMBER, 70),
    Column(Col.tag, "tag", TAG, 150),
]


class Mode(enum.Enum):
    TAGGER = "tagger"
    ONE_TIME = "one time tag"


def regex_for(text: str) -> str:
    """Regex that matches ``text`` literally (spaces kept readable)."""
    return re.escape(text).replace("\\ ", " ")


class TaggerWindow(Window):
    topics = frozenset({TRANSACTIONS, TAGGERS})

    def __init__(self, model, bridge, parent: QWidget | None = None):
        super().__init__(model, bridge, parent)
        self.resize(1300, 800)
        self.mode = Mode.TAGGER
        self.original_name: str | None = None
        self.transaction_id: str | None = None
        self._loading = False

        self.ok_button = QPushButton("OK", self)
        self.ok_button.setDefault(True)
        self.cancel_button = QPushButton("Cancel", self)
        self.mode_button = QPushButton("One time tag", self)
        self.tag_edit = QLineEdit(self)
        self.recurring_edit = QLineEdit(self)
        self.recurring_edit.setValidator(QIntValidator(1, 100, self))
        self.recurring_edit.setPlaceholderText("every year")
        self.name_edit = QLineEdit(self)
        self.recipient_edit = QLineEdit(self)
        self.description_edit = QLineEdit(self)
        self.message_label = QLabel(self)
        self.message_label.setStyleSheet("color: #b00020;")

        controls = QHBoxLayout()
        controls.addWidget(self.ok_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(QLabel("Tag:", self))
        controls.addWidget(self.tag_edit, 1)
        controls.addWidget(QLabel("Recurring [years]:", self))
        controls.addWidget(self.recurring_edit)
        controls.addStretch(1)
        controls.addWidget(self.mode_button)

        self.definition = QWidget(self)
        form = QFormLayout(self.definition)
        form.addRow("Name:", self.name_edit)
        form.addRow("Recipient regex:", self.recipient_edit)
        form.addRow("Description regex:", self.description_edit)

        self.table_model = DataFrameModel(PREVIEW_COLUMNS, self, background=self._background)
        self.table = DataFrameView(self.table_model, self, sortable=False)

        central = QWidget(self)
        layout = QVBoxLayout(central)
        layout.addLayout(controls)
        layout.addWidget(self.definition)
        layout.addWidget(self.message_label)
        layout.addWidget(self.table)
        self.setCentralWidget(central)

        for edit in (self.tag_edit, self.recurring_edit, self.name_edit, self.recipient_edit, self.description_edit):
            edit.textChanged.connect(self.refresh)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.close)
        self.mode_button.clicked.connect(self.toggle_mode)

    # ------------------------------------------------------------------ opening
    def open_new(self) -> None:
        self._open(Tagger(self.model.free_tagger_name()), original_name=None, transaction_id=None)

    def open_tagger(self, name: str) -> None:
        tagger = self.model.tagger(name)
        if tagger is None:
            self.open_new()
        else:
            self._open(tagger, original_name=name, transaction_id=None)

    def open_for_transaction(self, transaction_id: str) -> None:
        """Edit the tagger of a transaction, its one-time tag, or propose a new tagger matching it."""
        row = self.model.transaction(transaction_id)
        if row is None:
            self.open_new()
            return
        tagger_name = row[Col.tagger_name]
        if tagger_name == ONE_TIME_TAGGER:
            draft = Tagger(
                self.model.free_tagger_name(),
                tag=row[Col.tag],
                recurring=clean_recurring(row[Col.recurring]),
                regex_recipient=regex_for(row[Col.recipient]),
                regex_description=regex_for(row[Col.description]),
            )
            self._open(draft, original_name=None, transaction_id=transaction_id, mode=Mode.ONE_TIME)
        elif self.model.tagger(tagger_name) is not None:
            self._open(self.model.tagger(tagger_name), original_name=tagger_name, transaction_id=transaction_id)
        else:
            draft = Tagger(
                self.model.free_tagger_name(),
                regex_recipient=regex_for(row[Col.recipient]),
                regex_description=regex_for(row[Col.description]),
            )
            self._open(draft, original_name=None, transaction_id=transaction_id)

    def _open(
        self, tagger: Tagger, original_name: str | None, transaction_id: str | None, mode: Mode = Mode.TAGGER
    ) -> None:
        self.original_name = original_name
        self.transaction_id = transaction_id
        self._loading = True
        try:
            self.name_edit.setText(tagger.name)
            self.tag_edit.setText(tagger.tag)
            self.recurring_edit.setText("" if tagger.recurring is None else str(tagger.recurring))
            self.recipient_edit.setText(tagger.regex_recipient)
            self.description_edit.setText(tagger.regex_description)
        finally:
            self._loading = False
        completer = QCompleter(self.model.unique_tags(), self)
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.tag_edit.setCompleter(completer)
        self.set_mode(mode)
        self.show()
        self.raise_()

    # ------------------------------------------------------------------ editing
    def draft(self) -> Tagger:
        return Tagger(
            name=self.name_edit.text().strip(),
            tag=self.tag_edit.text().strip(),
            regex_recipient=self.recipient_edit.text(),
            regex_description=self.description_edit.text(),
            recurring=clean_recurring(self.recurring_edit.text()),
        )

    def set_mode(self, mode: Mode) -> None:
        if mode == Mode.ONE_TIME and self.transaction_id is None:
            mode = Mode.TAGGER
        self.mode = mode
        self.definition.setHidden(mode == Mode.ONE_TIME)
        self.mode_button.setText("Tagger" if mode == Mode.ONE_TIME else "One time tag")
        self.mode_button.setEnabled(self.transaction_id is not None)
        self.refresh()

    def toggle_mode(self) -> None:
        self.set_mode(Mode.TAGGER if self.mode == Mode.ONE_TIME else Mode.ONE_TIME)

    def errors(self) -> dict[str, str]:
        if self.mode == Mode.ONE_TIME:
            return {}
        draft = self.draft()
        errors = {}
        for field, pattern in (
            ("regex_recipient", draft.regex_recipient),
            ("regex_description", draft.regex_description),
        ):
            error = regex_error(pattern)
            if error is not None:
                errors[field] = error
        return errors

    def refresh(self, *_args) -> None:
        if self._loading:
            return
        super().refresh()
        self.setWindowTitle("One time tag" if self.mode == Mode.ONE_TIME else self.draft().name or "Tagger")
        errors = self.errors()
        for field, edit in (("regex_recipient", self.recipient_edit), ("regex_description", self.description_edit)):
            edit.setStyleSheet(line_edit_style(self._regex_color(field, errors)))
            edit.setToolTip(errors.get(field, ""))
        self.message_label.setText("\n".join(f"Invalid regex: {e}" for e in errors.values()))
        self.ok_button.setEnabled(not errors)
        self.table_model.set_frame(self.preview())

    def preview(self):
        draft = self.draft()
        if self.mode == Mode.ONE_TIME:
            df = self.model.transactions()
            df = df.loc[df[Col.transaction_id] == self.transaction_id].copy()
            df[Col.tag] = draft.tag
            df[Col.recurring] = float("nan") if draft.recurring is None else float(draft.recurring)
            return df
        return self.model.preview_tagger(draft, self.original_name, self.transaction_id)

    def selected_matches(self) -> tuple[bool, bool] | None:
        """Whether the regexes match the transaction the window was opened for."""
        if self.transaction_id is None or self.errors():
            return None
        row = self.model.transaction(self.transaction_id)
        if row is None:
            return None
        return tagger_matches(self.draft(), row[Col.recipient], row[Col.description])

    def _regex_color(self, field: str, errors: dict[str, str]):
        if field in errors:
            return RED
        matches = self.selected_matches()
        if matches is None:
            return None
        return GREEN if matches[0 if field == "regex_recipient" else 1] else RED

    def _background(self, row: int, key: str):
        if row != 0 or self.transaction_id is None:
            return None
        frame = self.table_model.frame
        if frame.empty or frame[Col.transaction_id].iloc[0] != self.transaction_id:
            return None
        if self.mode == Mode.ONE_TIME:
            return GREY
        matches = self.selected_matches()
        return GREY if matches is None else (GREEN if all(matches) else RED)

    # ------------------------------------------------------------------ saving
    def accept(self) -> bool:
        draft = self.draft()
        if self.mode == Mode.ONE_TIME:
            if draft.tag:
                self.model.set_one_time_tag(self.transaction_id, draft.tag, draft.recurring)
            else:
                self.model.remove_one_time_tag(self.transaction_id)
        else:
            try:
                self.model.save_tagger(draft, self.original_name)
            except InvalidTaggerError as e:
                self.show_error("Invalid tagger", str(e))
                return False
        self.close()
        return True
