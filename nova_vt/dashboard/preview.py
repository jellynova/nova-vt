"""PreviewWidget — displays 960×540 half-res compositor frames via QTimer."""
from __future__ import annotations

import queue
from typing import Optional

import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class PreviewWidget(QWidget):
    """Polls *preview_queue* at 30 fps and renders RGBA numpy frames into a QLabel."""

    def __init__(self, preview_queue: queue.Queue, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._queue = preview_queue

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setStyleSheet("background-color: #0a0a14; color: #94a3b8;")
        self._label.setText("No Preview")
        self._label.setMinimumSize(960, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.setMinimumSize(960, 540)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start()

    def _poll_frame(self) -> None:
        """Pull the latest frame from the queue (discard stale backlog) and display it."""
        frame: Optional[np.ndarray] = None
        try:
            while True:
                frame = self._queue.get_nowait()
        except queue.Empty:
            pass

        if frame is None:
            return

        # frame is HxWx4 RGBA uint8, shape (540, 960, 4)
        h, w, _ = frame.shape
        # QImage expects contiguous memory; ensure C-contiguous
        frame_c = np.ascontiguousarray(frame)
        image = QImage(
            frame_c.data,
            w,
            h,
            w * 4,
            QImage.Format.Format_RGBA8888,
        )
        # Keep reference so GC doesn't free the array while QImage uses it
        self._last_frame = frame_c
        self._label.setPixmap(QPixmap.fromImage(image))
        self._label.setText("")

    def stop(self) -> None:
        """Stop the polling timer (call on shutdown)."""
        self._timer.stop()
