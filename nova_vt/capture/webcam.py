"""WebcamCaptureThread — reads webcam frames and pushes RGBA numpy arrays to a queue."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Optional

import cv2
import numpy as np

_log = logging.getLogger(__name__)

_PREVIEW_W = 960
_PREVIEW_H = 540


class WebcamCaptureThread(threading.Thread):
    """Captures frames from a webcam and drops them onto *frame_queue* at ~30 fps.

    Frames are HxWx4 RGBA uint8 arrays sized (_PREVIEW_H, _PREVIEW_W, 4).
    The queue is filled with put_nowait; full queue frames are silently dropped
    so the preview always shows the latest frame without backing up.

    *device* may be either an integer index (0, 1, …) or a V4L2 device path
    string such as "/dev/video2".
    """

    def __init__(
        self,
        frame_queue: queue.Queue,
        device: "int | str" = 0,
        # Legacy alias kept for callers that still use camera_index= kwarg
        camera_index: "int | None" = None,
        fps: int = 30,
    ) -> None:
        super().__init__(daemon=True, name="WebcamCaptureThread")
        self._queue = frame_queue
        self._device: int | str = camera_index if camera_index is not None else device
        self._fps = fps
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        cap = cv2.VideoCapture(self._device)
        if not cap.isOpened():
            _log.error("WebcamCaptureThread: could not open camera %r", self._device)
            return

        cap.set(cv2.CAP_PROP_FPS, self._fps)
        interval = 1.0 / self._fps

        _log.info("WebcamCaptureThread: started (device=%r, %d fps)", self._device, self._fps)

        try:
            while not self._stop_event.wait(timeout=interval):
                ok, bgr = cap.read()
                if not ok:
                    _log.warning("WebcamCaptureThread: frame read failed, retrying")
                    continue

                # Resize to preview dimensions and convert BGR → RGBA
                resized = cv2.resize(bgr, (_PREVIEW_W, _PREVIEW_H), interpolation=cv2.INTER_LINEAR)
                rgba = cv2.cvtColor(resized, cv2.COLOR_BGR2RGBA)

                try:
                    self._queue.put_nowait(rgba)
                except queue.Full:
                    pass  # consumer is behind — drop frame, keep latest
        finally:
            cap.release()
            _log.info("WebcamCaptureThread: stopped")
