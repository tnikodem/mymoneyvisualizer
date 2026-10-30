"""The look of the application: colors, font and one style sheet for all windows.

Widgets choose a variant with a dynamic property, e.g. ``button.setProperty("primary", True)`` for the main action
of a window or ``frame.setProperty("card", True)`` for a white card on the grey window background.
"""

from __future__ import annotations

import html
from pathlib import Path

from PyQt6.QtCore import QEvent, QLibraryInfo, QLocale, QObject, Qt, QTranslator
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory, QToolTip, QWidget

BACKGROUND = "#f4f6f9"
SURFACE = "#ffffff"
SUBTLE = "#f8f9fb"
BORDER = "#dde2e8"
GRID = "#eef1f4"
TEXT = "#1f2933"
MUTED = "#66707d"
ACCENT = "#2a78d6"
ACCENT_HOVER = "#1c5cab"
ACCENT_LIGHT = "#e7f0fc"
SELECTION = "#d7e6fa"
GOOD = "#1e7d3a"
GOOD_LIGHT = "#e3f3e8"
BAD = "#c5221f"
BAD_LIGHT = "#fce8e6"
WARNING = "#9a5b00"
WARNING_LIGHT = "#fdf1dc"

#: Categorical chart colors in their fixed order (validated for color vision deficiencies as adjacent pairs).
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948")
#: The rest of the categories in a chart with more categories than colors.
OTHER = "#9aa3ad"
#: Arrows of combo and spin boxes (a style sheet that styles their frame has to draw them itself).
ICONS = (Path(__file__).parent / "icons").as_posix()

STYLE_SHEET = f"""
QMainWindow, QDialog {{ background: {BACKGROUND}; }}
QToolTip {{
    background: {TEXT}; color: white; border: none; padding: 6px 8px; border-radius: 4px;
}}

QPushButton {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid #c7ced7; border-radius: 6px;
    padding: 5px 14px; min-height: 20px;
}}
QPushButton:hover {{ background: #eef2f6; border-color: #aab4c0; }}
QPushButton:pressed {{ background: #e2e8ef; }}
QPushButton:disabled {{ color: #a3abb5; background: {BACKGROUND}; border-color: {BORDER}; }}
QPushButton[primary="true"] {{
    background: {ACCENT}; color: white; border: 1px solid {ACCENT}; font-weight: 600;
}}
QPushButton[primary="true"]:hover {{ background: {ACCENT_HOVER}; border-color: {ACCENT_HOVER}; }}
QPushButton[primary="true"]:disabled {{ background: #a9c6ec; border-color: #a9c6ec; color: white; }}
QPushButton[link="true"] {{ border: none; background: transparent; color: {ACCENT}; padding: 2px 4px; }}
QPushButton[link="true"]:hover {{ text-decoration: underline; }}

QLineEdit, QComboBox, QSpinBox, QDateEdit {{
    background: {SURFACE}; border: 1px solid #c7ced7; border-radius: 6px; padding: 3px 8px; min-height: 22px;
    selection-background-color: {SELECTION}; selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateEdit:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: #a3abb5; background: {BACKGROUND}; }}
QComboBox, QDateEdit {{ padding-right: 22px; }}
QSpinBox {{ padding-right: 20px; }}
QComboBox::drop-down, QDateEdit::drop-down {{
    subcontrol-origin: padding; subcontrol-position: center right; border: none; width: 20px;
}}
QSpinBox::up-button, QSpinBox::down-button {{ subcontrol-origin: border; width: 18px; border: none; }}
QSpinBox::up-button {{ subcontrol-position: top right; margin-top: 3px; }}
QSpinBox::down-button {{ subcontrol-position: bottom right; margin-bottom: 3px; }}
QComboBox::down-arrow, QDateEdit::down-arrow, QSpinBox::down-arrow {{
    image: url({ICONS}/chevron-down.svg); width: 10px; height: 6px;
}}
QSpinBox::up-arrow {{ image: url({ICONS}/chevron-up.svg); width: 10px; height: 6px; }}
QTreeView QComboBox, QTreeView QSpinBox {{ border-color: transparent; background: transparent; }}
QTreeView QComboBox:hover, QTreeView QSpinBox:hover {{ border-color: #c7ced7; background: {SURFACE}; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; selection-background-color: {SELECTION};
    selection-color: {TEXT}; outline: 0;
}}

QTableView, QTreeView, QListView, QTextBrowser {{
    background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 8px; gridline-color: {GRID};
    selection-background-color: {SELECTION}; selection-color: {TEXT}; alternate-background-color: {SUBTLE};
    outline: 0;
}}
QTreeView::item {{ min-height: 30px; }}
QHeaderView::section {{
    background: {SUBTLE}; color: #4a5562; font-weight: 600; border: none;
    border-bottom: 1px solid {BORDER}; border-right: 1px solid {GRID}; padding: 5px 8px;
}}
QTableCornerButton::section {{ background: {SUBTLE}; border: none; }}

QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; background: {SURFACE}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {MUTED}; padding: 7px 16px; border: none; border-bottom: 2px solid transparent;
}}
QTabBar::tab:selected {{ color: {ACCENT}; border-bottom: 2px solid {ACCENT}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {TEXT}; }}

QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{ background: #c9d0d8; border-radius: 4px; }}
QScrollBar::handle:vertical {{ min-height: 30px; }}
QScrollBar::handle:horizontal {{ min-width: 30px; }}
QScrollBar::handle:hover {{ background: #aab4c0; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QFrame[card="true"] {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame[banner="true"] {{ background: {ACCENT_LIGHT}; border: 1px solid #c3d8f5; border-radius: 8px; }}
QFrame[card="true"][tone="good"] {{ border-left: 4px solid {GOOD}; }}
QFrame[card="true"][tone="bad"] {{ border-left: 4px solid {BAD}; }}
QFrame[card="true"][tone="warning"] {{ border-left: 4px solid {WARNING}; }}
QLabel {{ background: transparent; border: none; }}
QLabel[role="title"] {{ font-size: 17pt; font-weight: 600; }}
QLabel[role="heading"] {{ font-size: 12pt; font-weight: 600; }}
QLabel[role="hint"] {{ color: {MUTED}; }}
QLabel[role="kpi"] {{ font-size: 19pt; font-weight: 600; }}
QLabel[role="step"] {{
    background: {ACCENT_LIGHT}; color: {ACCENT}; border-radius: 14px; font-weight: 700;
    min-width: 28px; max-width: 28px; min-height: 28px; max-height: 28px;
}}
QLabel[tone="good"] {{ color: {GOOD}; }}
QLabel[tone="bad"] {{ color: {BAD}; }}
QLabel[tone="warning"] {{ color: {WARNING}; }}
QLabel[role="chip"] {{ border-radius: 4px; padding: 1px 6px; }}
QToolButton[help="true"] {{
    background: {SURFACE}; color: {MUTED}; border: 1px solid #c7ced7; border-radius: 12px; font-weight: 700;
    min-width: 22px; max-width: 22px; min-height: 22px; max-height: 22px;
}}
QToolButton[help="true"]:hover {{ color: {ACCENT}; border-color: {ACCENT}; }}
QToolButton[close="true"] {{ background: transparent; border: none; color: {MUTED}; padding: 2px 6px; }}
QToolButton[close="true"]:hover {{ color: {TEXT}; }}
"""


def apply_style(app: QApplication) -> None:
    """Fusion with a light palette and the style sheet; Fusion draws the same on every platform."""
    app.setStyle(QStyleFactory.create("Fusion"))
    palette = QPalette()
    for role, color in (
        (QPalette.ColorRole.Window, BACKGROUND),
        (QPalette.ColorRole.WindowText, TEXT),
        (QPalette.ColorRole.Base, SURFACE),
        (QPalette.ColorRole.AlternateBase, SUBTLE),
        (QPalette.ColorRole.Text, TEXT),
        (QPalette.ColorRole.Button, SURFACE),
        (QPalette.ColorRole.ButtonText, TEXT),
        (QPalette.ColorRole.ToolTipBase, TEXT),
        (QPalette.ColorRole.ToolTipText, SURFACE),
        (QPalette.ColorRole.PlaceholderText, "#98a1ac"),
        (QPalette.ColorRole.Highlight, SELECTION),
        (QPalette.ColorRole.HighlightedText, TEXT),
        (QPalette.ColorRole.Link, ACCENT),
    ):
        palette.setColor(role, QColor(color))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor("#a3abb5"))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor("#a3abb5"))
    app.setPalette(palette)
    font = app.font()
    font.setPointSizeF(max(font.pointSizeF(), 10.0))
    app.setFont(font)
    app.setStyleSheet(STYLE_SHEET)
    if not hasattr(app, "tooltip_wrapper"):
        app.tooltip_wrapper = TooltipWrapper(app)
        app.installEventFilter(app.tooltip_wrapper)


def rich(text: str) -> str:
    """A tooltip as rich text: Qt wraps the lines of rich text, a long plain text would be one endless line."""
    if not text or Qt.mightBeRichText(text):
        return text
    return "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"


class TooltipWrapper(QObject):
    """Shows plain text tooltips of widgets as rich text, so that long explanations wrap."""

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # noqa: N802 (Qt API)
        if event.type() == QEvent.Type.ToolTip and isinstance(watched, QWidget):
            text = watched.toolTip()
            if text and not Qt.mightBeRichText(text):
                QToolTip.showText(event.globalPos(), rich(text), watched)
                return True
        return False


def use_german(app: QApplication) -> None:
    """German texts in Qt's own dialogs (Ja/Nein, file dialogs) and German number and date formats."""
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Germany))
    translator = QTranslator(app)
    if translator.load("qtbase_de", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)


def set_variant(widget: QWidget, name: str, value) -> None:
    """Set a style property and apply it at once (Qt does not restyle on property changes by itself)."""
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    widget.style().unpolish(widget)
    widget.style().polish(widget)
