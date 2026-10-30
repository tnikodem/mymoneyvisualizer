import tomllib
from pathlib import Path

from PyQt6.QtCore import QEvent, QLocale, QPoint
from PyQt6.QtGui import QHelpEvent
from PyQt6.QtWidgets import QApplication, QLabel, QMessageBox, QToolTip

from mymoneyvisualizer.ui.common import HelpButton, InfoBanner, KeyFigure, make_button
from mymoneyvisualizer.ui.style import BACKGROUND, ICONS, STYLE_SHEET, rich, set_variant

ROOT = Path(__file__).parents[2]


def test_the_application_is_styled_and_german(qapp):
    """The session fixture ``styled`` applied the style like ``mmv`` does."""
    assert qapp.palette().window().color().name() == BACKGROUND
    assert qapp.styleSheet() == STYLE_SHEET
    assert QLocale().language() == QLocale.Language.German


def test_arrow_icons_are_shipped():
    """A style sheet that styles combo and spin boxes has to draw their arrows; the icons are package data."""
    for name in ("chevron-down.svg", "chevron-up.svg"):
        assert (Path(ICONS) / name).is_file()
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert config["tool"]["setuptools"]["package-data"]["mymoneyvisualizer.ui"] == ["icons/*.svg"]


def test_variants(qtbot):
    label = QLabel()
    qtbot.addWidget(label)
    set_variant(label, "tone", "good")
    assert label.property("tone") == "good"
    set_variant(label, "tone", "good")  # unchanged: nothing to do
    button = make_button("Los", "Erklärung", primary=True)
    assert (button.property("primary"), button.toolTip()) == (True, "Erklärung")
    figure = KeyFigure("Sparquote", "Formel")
    figure.set("25 %", "Ziel 20 %", "good")
    assert (figure.value.text(), figure.detail.text(), figure.property("tone")) == ("25 %", "Ziel 20 %", "good")


def test_banner_shows_details_on_request(qtbot, monkeypatch, tmp_path):
    from mymoneyvisualizer.app import AppModel

    model = AppModel.open(tmp_path / "data")
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: shown.append((title, text)))
    banner = InfoBanner(model, "test", "kurz", "<p>lang</p>", "Titel")
    qtbot.addWidget(banner)
    banner.more_button.click()
    assert shown == [("Titel", "<p>lang</p>")]
    assert InfoBanner(model, "other", "nur kurz").more_button is None
    banner.dismiss()
    assert InfoBanner(model, "test", "kurz").isHidden()
    model.hide_hint("test")
    assert model.settings.hidden_hints == ["test"]


def test_help_button(qtbot, monkeypatch):
    shown = []
    monkeypatch.setattr(QMessageBox, "information", lambda parent, title, text: shown.append((title, text)))
    button = HelpButton("<p>So geht's</p>", "Hilfe")
    qtbot.addWidget(button)
    assert button.toolTip() == "<p>So geht's</p>"
    button.click()
    assert shown == [("Hilfe", "<p>So geht's</p>")]


def test_long_plain_tooltips_wrap():
    assert rich("Erste Zeile\nzweite <Zeile>") == "<p>Erste Zeile<br>zweite &lt;Zeile&gt;</p>"
    assert rich("<p>schon rich</p>") == "<p>schon rich</p>"
    assert rich("") == ""


def test_plain_tooltips_are_shown_as_rich_text(qtbot):
    """Qt only wraps the lines of rich text tooltips; the application turns plain ones into rich text."""
    label = QLabel("x")
    label.setToolTip("Eine lange Erklärung")
    qtbot.addWidget(label)
    label.show()
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(1, 1), label.mapToGlobal(QPoint(1, 1)))
    QApplication.sendEvent(label, event)
    assert QToolTip.text() == "<p>Eine lange Erklärung</p>"
    QToolTip.hideText()
