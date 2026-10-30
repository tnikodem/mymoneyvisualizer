"""Windows collect changes for a short time and refresh once (other UI tests refresh at once)."""

import pytest

from mymoneyvisualizer.domain.columns import Col
from mymoneyvisualizer.domain.models import Tagger
from mymoneyvisualizer.ui.common import Window

DELAY = 60


@pytest.fixture(autouse=True)
def lazy(monkeypatch):
    monkeypatch.setattr(Window, "REFRESH_DELAY_MS", DELAY)


def _count_refreshes(monkeypatch, window):
    calls = []
    original = window.refresh

    def counting(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(window, "refresh", counting)
    window._refresh_timer.timeout.disconnect()
    window._refresh_timer.timeout.connect(window.refresh)
    return calls


def _summary(main):
    main.show_summary()
    window = main.summary_window
    window.set_months("2023-07", "2024-01")
    return window


def test_model_changes_are_collected(main, model, qtbot, monkeypatch):
    window = _summary(main)
    calls = _count_refreshes(monkeypatch, window)
    for i in range(5):
        model.save_tagger(Tagger(f"lazy{i}", tag=f"lazy{i}", regex_recipient="Kiosk"))
    assert calls == []  # nothing yet
    qtbot.waitUntil(lambda: calls == [1], timeout=2000)
    assert "lazy4" in set(window.table_model.frame[Col.tag])
    qtbot.wait(2 * DELAY)
    assert calls == [1]  # one refresh for five changes


def test_flush_refreshes_at_once(main, model):
    window = _summary(main)
    model.save_tagger(Tagger("now", tag="now", regex_recipient="Kiosk"))
    assert "now" not in set(window.table_model.frame[Col.tag])
    window.flush()
    assert "now" in set(window.table_model.frame[Col.tag])
    window.flush()  # nothing scheduled: no error


def test_tagger_window_validates_at_once_and_previews_later(main, model, qtbot):
    main.open_tagger()
    window = main.tagger_window
    window.recipient_edit.setText("([")
    assert not window.ok_button.isEnabled()  # immediate
    window.recipient_edit.setText("Kiosk")
    assert window.ok_button.isEnabled()
    assert len(window.table_model.frame) > 1  # still the preview of the empty tagger, updated after the delay
    qtbot.waitUntil(lambda: list(window.table_model.frame[Col.recipient]) == ["Kiosk"], timeout=2000)


def test_hidden_windows_are_not_refreshed(main, model, qtbot, monkeypatch):
    window = _summary(main)
    window.hide()
    calls = _count_refreshes(monkeypatch, window)
    model.save_tagger(Tagger("hidden", tag="hidden", regex_recipient="Kiosk"))
    qtbot.wait(3 * DELAY)
    assert calls == []
    window.show()
    assert calls == [1]
