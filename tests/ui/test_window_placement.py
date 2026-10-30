"""Regression: windows opened from the main window were centered over it and had their title bar above the screen."""

import pytest
from PyQt6.QtCore import QRect, QSize

from mymoneyvisualizer.ui.common import TITLE_BAR_ESTIMATE, fit_into

AVAILABLE = QRect(0, 40, 1000, 700)  # e.g. a task bar at the top


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        (QRect(100, 100, 400, 300), QRect(100, 100, 400, 300)),  # inside: unchanged
        (QRect(100, -86, 400, 300), QRect(100, 40, 400, 300)),  # above the screen
        (QRect(-50, 600, 400, 300), QRect(0, 440, 400, 300)),  # left and below
        (QRect(900, 100, 400, 300), QRect(600, 100, 400, 300)),  # right
        (QRect(-10, -10, 1400, 930), QRect(0, 40, 1000, 700)),  # larger than the screen
    ],
)
def test_fit_into(frame, expected):
    assert fit_into(frame, AVAILABLE) == expected


def test_fit_into_keeps_title_bar_visible_if_minimum_is_too_large():
    fitted = fit_into(QRect(-300, -86, 1400, 930), AVAILABLE, minimum=QSize(1200, 800))
    assert fitted == QRect(0, 40, 1200, 800)  # sticks out at the right and bottom only


def _title_bar(window):
    margins = window.windowHandle().frameMargins()
    return margins.top() or TITLE_BAR_ESTIMATE


def _assert_on_screen(window):
    """Title bar always visible; the whole window if its minimum size fits the screen."""
    available, frame, title_bar = window.screen().availableGeometry(), window.frameGeometry(), _title_bar(window)
    assert frame.left() >= available.left()
    assert window.geometry().top() - title_bar >= available.top()
    minimum = window.minimumSizeHint()
    if minimum.width() <= available.width():
        assert frame.right() <= available.right()
    if minimum.height() + title_bar <= available.height():
        assert frame.bottom() <= available.bottom()


@pytest.mark.parametrize("name", ["accounts", "income_expenses", "budget", "rules"])
def test_windows_open_completely_on_screen(main, name):
    main.move(0, 0)  # main window at the top: centering over it pushes tall windows above the screen
    getattr(main, f"show_{name}")()
    _assert_on_screen(getattr(main, f"{name}_window"))


def test_rule_window_opens_on_screen(main):
    main.move(0, 0)
    main.open_rule()
    _assert_on_screen(main.rule_window)


def test_window_is_centered_over_main_window(main):
    available = main.screen().availableGeometry()
    main.move(available.center().x() - main.width() // 2, available.center().y())
    main.show_rules()
    window = main.rules_window
    assert abs(window.frameGeometry().center().x() - main.frameGeometry().center().x()) <= 1
    _assert_on_screen(window)


def test_position_chosen_by_user_is_kept(main):
    main.show_accounts()
    window = main.accounts_window
    window.resize(300, 200)
    window.move(15, 120)
    window.hide()
    main.show_accounts()
    assert window.pos().x() == 15 and window.pos().y() == 120


def test_window_without_visible_parent_is_centered_on_screen(main):
    main.hide()
    main.show_rules()
    window = main.rules_window
    available = window.screen().availableGeometry()
    _assert_on_screen(window)
    assert abs(window.frameGeometry().center().x() - available.center().x()) <= 1
