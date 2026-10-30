import pytest
from PyQt6.QtWidgets import QMessageBox

from mymoneyvisualizer.app import AppModel
from mymoneyvisualizer.domain.models import Tagger
from mymoneyvisualizer.ui.common import Window
from mymoneyvisualizer.ui.main_window import MainWindow

from ..helpers import transactions


class Dialogs:
    """Records message boxes instead of showing them; ``answer`` is returned for questions."""

    def __init__(self):
        self.answer = QMessageBox.StandardButton.Yes
        self.shown = []

    def question(self, parent, title, text, *args, **kwargs):
        self.shown.append(("question", title, text))
        return self.answer

    def message(self, kind):
        def show(parent, title, text, *args, **kwargs):
            self.shown.append((kind, title, text))
            return QMessageBox.StandardButton.Ok

        return show


@pytest.fixture(autouse=True)
def immediate_refresh(monkeypatch):
    """Windows refresh at once instead of after a short delay, so tests can check right after a change.

    ``test_lazy_refresh.py`` checks the delayed refresh itself.
    """
    monkeypatch.setattr(Window, "REFRESH_DELAY_MS", None)


@pytest.fixture(autouse=True)
def dialogs(monkeypatch):
    recorder = Dialogs()
    monkeypatch.setattr(QMessageBox, "question", recorder.question)
    for kind in ("information", "warning", "critical"):
        monkeypatch.setattr(QMessageBox, kind, recorder.message(kind))
    return recorder


@pytest.fixture
def model(tmp_path):
    model = AppModel.open(tmp_path / "data")
    model.add_account("giro")
    model.add_account("spar")
    rows = []
    for month in range(1, 13):
        rows += [
            (f"2023-{month:02d}-01", "ACME GmbH", "Gehalt", 3000.0),
            (f"2023-{month:02d}-03", "Vermieter", "Miete", -900.0),
            (f"2023-{month:02d}-10", "REWE", "Einkauf", -100.0),
            (f"2023-{month:02d}-12", "Shell", "Tanken", -60.0),
            (f"2023-{month:02d}-15", "ShareNow", "Fahrt", -15.0),
            (f"2023-{month:02d}-20", "Ich", "Sparen", -200.0),
        ]
    rows += [("2024-01-10", "REWE", "Einkauf", -450.0), ("2024-01-11", "Kiosk", "Zeitung", -2.5)]
    model.import_transactions("giro", transactions(*rows))
    model.import_transactions("spar", transactions(("2023-06-20", "Ich", "Sparen Eingang", 200.0)))
    for tagger in (
        Tagger("salary", tag="income.salary", regex_recipient="ACME"),
        Tagger("rent", tag="household.rent", regex_description="Miete"),
        Tagger("groceries", tag="household.food", regex_recipient="REWE"),
        Tagger("fuel", tag="car.fuel", regex_recipient="Shell"),
        Tagger("sharing", tag="carsharing", regex_recipient="ShareNow"),
        Tagger("saving", tag="spar", regex_description="^Sparen$"),
    ):
        model.save_tagger(tagger)
    model.assign_categories({"income": ["income"], "basic": ["household", "car"], "optional": ["carsharing", ""]})
    model.set_budget_period(2023, 2023)
    return model


@pytest.fixture
def main(qtbot, model):
    window = MainWindow(model)
    qtbot.addWidget(window)
    window.show()
    return window
