"""End-to-end smoke test: open MainWindow, exercise the full Preview→Live→EndStream flow.

All pipeline threads are replaced with mocks so the test needs no EGL, no
sounddevice, and no real webcam. A real numpy frame is pushed onto the
preview_queue to verify the PreviewWidget actually renders it.
"""
import sys
import queue
import numpy as np
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from nova_vt.dashboard.window import MainWindow, StreamState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_window(qtbot):
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")

    mock_mixer = MagicMock()
    mock_mixer.get_peak_level = MagicMock(return_value=0.0)

    preview_queue = queue.Queue(maxsize=4)
    scenes = ["Gameplay", "Just Chatting", "BRB", "Intro", "Ending"]

    start_preview_fn = MagicMock()
    stop_preview_fn = MagicMock()
    go_live_fn = MagicMock()
    end_stream_fn = MagicMock()

    window = MainWindow(
        config=mock_config,
        preview_queue=preview_queue,
        mixer=mock_mixer,
        scenes=scenes,
        start_preview_fn=start_preview_fn,
        stop_preview_fn=stop_preview_fn,
        go_live_fn=go_live_fn,
        end_stream_fn=end_stream_fn,
    )
    qtbot.addWidget(window)
    return window, preview_queue, {
        "start_preview": start_preview_fn,
        "stop_preview": stop_preview_fn,
        "go_live": go_live_fn,
        "end_stream": end_stream_fn,
    }


def test_e2e_full_stream_lifecycle(qapp, qtbot):
    """Full lifecycle: idle → preview → live → end stream."""
    window, preview_queue, fns = make_window(qtbot)
    window.show()

    # ── 1. Initial state ────────────────────────────────────────────────
    assert window.state == StreamState.IDLE
    assert not window._go_live_btn.isEnabled()
    assert not window._live_indicator.isVisible()

    # ── 2. Click Preview ────────────────────────────────────────────────
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.PREVIEWING
    fns["start_preview"].assert_called_once()
    assert window._go_live_btn.isEnabled()
    assert window._edit_scenes_btn.isVisible()

    # ── 3. Push a frame onto the preview queue ───────────────────────────
    frame = np.zeros((540, 960, 4), dtype=np.uint8)
    frame[:, :, 0] = 180  # red channel — distinct test pattern
    frame[:, :, 3] = 255
    preview_queue.put_nowait(frame)

    # Wait for PreviewWidget's QTimer to consume the frame
    qtbot.waitUntil(
        lambda: (
            window._preview_widget._label.pixmap() is not None
            and not window._preview_widget._label.pixmap().isNull()
        ),
        timeout=500,
    )
    pm = window._preview_widget._label.pixmap()
    assert pm.width() == 960
    assert pm.height() == 540

    # ── 4. Click Go Live ────────────────────────────────────────────────
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.LIVE
    fns["go_live"].assert_called_once()
    assert window._live_indicator.isVisible()
    assert "LIVE" in window._live_indicator.text()
    assert not window._edit_scenes_btn.isVisible()
    assert window._audio_mixer._end_stream_btn.isEnabled()

    # ── 5. Switch scene while live ──────────────────────────────────────
    from PyQt6.QtWidgets import QPushButton
    scene_buttons = window._scene_switcher.findChildren(QPushButton)
    assert len(scene_buttons) == 5
    qtbot.mouseClick(scene_buttons[1], Qt.MouseButton.LeftButton)
    assert window._scene_switcher.active_scene() == "Just Chatting"

    # ── 6. End Stream ────────────────────────────────────────────────────
    qtbot.mouseClick(window._audio_mixer._end_stream_btn, Qt.MouseButton.LeftButton)
    fns["end_stream"].assert_called_once()
    assert window.state == StreamState.IDLE
    assert not window._live_indicator.isVisible()
    assert not window._audio_mixer._end_stream_btn.isEnabled()


def test_e2e_preview_widget_handles_burst_of_frames(qapp, qtbot):
    """Push multiple frames rapidly; widget must not crash and should show latest."""
    window, preview_queue, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)

    for i in range(10):
        frame = np.full((540, 960, 4), i * 25, dtype=np.uint8)
        frame[:, :, 3] = 255
        try:
            preview_queue.put_nowait(frame)
        except queue.Full:
            pass  # expected when queue is full — compositor drops

    qtbot.waitUntil(
        lambda: (
            window._preview_widget._label.pixmap() is not None
            and not window._preview_widget._label.pixmap().isNull()
        ),
        timeout=500,
    )
    # Widget is alive and showing something — no crash
    assert not window._preview_widget._label.pixmap().isNull()


def test_e2e_chat_message_flow(qapp, qtbot):
    """Add a chat message via the ChatWidget slot and verify it appears in the All tab."""
    from dataclasses import dataclass

    @dataclass
    class Msg:
        platform: str
        username: str
        color: str
        text: str
        event_type: str = "message"

    window, _, _ = make_window(qtbot)
    window.show()

    msg = Msg(platform="twitch", username="twitchfan", color="#9146FF", text="Hello from test!")
    window._chat_widget.add_message(msg)

    all_list = window._chat_widget._lists["All"]
    assert all_list.count() == 1
    assert "twitchfan" in all_list.item(0).text()
    assert "Hello from test!" in all_list.item(0).text()


def test_e2e_platform_stats_update(qapp, qtbot):
    """Verify PlatformStatsWidget updates propagate correctly in the full window."""
    window, _, _ = make_window(qtbot)
    window.show()

    window._platform_stats.update_from_stream_stats({
        "twitch": {"viewers": 999, "likes": 42},
        "youtube": {"viewers": 500, "likes": 10},
        "tiktok": {"viewers": 200, "likes": 888},
    })

    assert "999" in window._platform_stats._viewer_labels["twitch"].text()
    assert "888" in window._platform_stats._likes_labels["tiktok"].text()
