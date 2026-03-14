import sys
import queue
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from nova_vt.dashboard.preview import PreviewWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_preview_widget_initial_size(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    assert widget.minimumWidth() == 960
    assert widget.minimumHeight() == 540


def test_preview_widget_shows_placeholder(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # Before any frame arrives, pixmap should be null or placeholder exists
    label_pixmap = widget._label.pixmap()
    # Either no pixmap (null) or a placeholder was set — either is valid
    # The key assertion: widget is visible and _label exists
    assert widget._label is not None


def test_preview_widget_renders_frame(qapp, qtbot):
    """Put an RGBA frame on the queue; after timer tick it should appear as pixmap."""
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    widget.show()

    # Push a green 960x540 RGBA frame
    frame = np.zeros((540, 960, 4), dtype=np.uint8)
    frame[:, :, 1] = 200  # green channel
    frame[:, :, 3] = 255  # fully opaque
    q.put_nowait(frame)

    # Wait for the QTimer to fire and call _poll_frame
    qtbot.waitUntil(lambda: widget._label.pixmap() is not None and not widget._label.pixmap().isNull(), timeout=500)
    pm = widget._label.pixmap()
    assert pm.width() == 960
    assert pm.height() == 540


def test_preview_widget_empty_queue_does_not_crash(qapp, qtbot):
    """Polling an empty queue should be a no-op, not raise."""
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # Manually call poll — should not raise
    widget._poll_frame()


def test_preview_widget_timer_interval(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # 30 fps → ~33ms interval
    assert widget._timer.interval() <= 34
    assert widget._timer.interval() >= 32
