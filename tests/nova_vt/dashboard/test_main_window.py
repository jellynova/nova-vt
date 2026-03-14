import sys
import queue
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel
from PyQt6.QtCore import Qt
from nova_vt.dashboard.window import MainWindow, StreamState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_window(qtbot):
    """Build MainWindow with fully mocked pipeline dependencies."""
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")

    mock_mixer = MagicMock()
    mock_mixer.get_peak_level = MagicMock(return_value=0.0)

    preview_queue = queue.Queue(maxsize=2)
    scenes = ["Gameplay", "Just Chatting", "BRB"]

    window = MainWindow(
        config=mock_config,
        preview_queue=preview_queue,
        mixer=mock_mixer,
        scenes=scenes,
        start_preview_fn=MagicMock(),
        stop_preview_fn=MagicMock(),
        go_live_fn=MagicMock(),
        end_stream_fn=MagicMock(),
    )
    qtbot.addWidget(window)
    return window, preview_queue


def test_main_window_initial_state_is_idle(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert window.state == StreamState.IDLE


def test_main_window_idle_shows_preview_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    assert window._preview_btn.isVisible()


def test_main_window_idle_go_live_button_disabled(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert not window._go_live_btn.isEnabled()


def test_main_window_click_preview_transitions_to_previewing(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.PREVIEWING


def test_main_window_previewing_enables_go_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window._go_live_btn.isEnabled()


def test_main_window_previewing_shows_edit_scenes_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window._edit_scenes_btn.isVisible()


def test_main_window_click_go_live_transitions_to_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.LIVE


def test_main_window_live_hides_edit_scenes_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert not window._edit_scenes_btn.isVisible()


def test_main_window_live_enables_end_stream(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window._audio_mixer._end_stream_btn.isEnabled()


def test_main_window_live_indicator_shows_when_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window._live_indicator.isVisible()
    assert "LIVE" in window._live_indicator.text()


def test_main_window_live_indicator_hidden_when_idle(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert not window._live_indicator.isVisible()


def test_main_window_end_stream_transitions_to_idle(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    window._on_end_stream()
    assert window.state == StreamState.IDLE
    window._end_stream_fn.assert_called_once()
    window._stop_preview_fn.assert_called_once()


def test_main_window_calls_start_preview_fn(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    window._start_preview_fn.assert_called_once()


def test_main_window_calls_go_live_fn(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    window._go_live_fn.assert_called_once()


def test_main_window_has_settings_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert window._settings_btn is not None


def test_main_window_scene_switcher_has_all_scenes(qapp, qtbot):
    window, _ = make_window(qtbot)
    buttons = window._scene_switcher.findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    assert "Gameplay" in labels
    assert "Just Chatting" in labels
    assert "BRB" in labels
