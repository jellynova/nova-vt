"""Compositor — combines scene layers into output frames at 30 fps.

Architecture
------------
The Compositor owns two *source queues* that upstream producers push into:

  * ``webcam_queue``  — WebcamCaptureThread pushes (H, W, 3|4) uint8 BGR/RGBA frames
  * ``avatar_queue``  — VRMRenderer pushes (H, W, 4) uint8 RGBA frames

Every tick the compositor drains both queues (keeping only the latest frame),
alpha-composites the active scene layers in z-order, then pushes:

  * preview_queue   — half-resolution (960×540) for the preview widget
  * encoder_queue   — full-resolution (1920×1080) when live; None otherwise

Thread-safe public API:

  * ``set_scene(scene_data)``       — swap the active scene dict
  * ``set_encoder_queue(q|None)``   — enable/disable live encoder output
  * ``stop()``                      — request graceful shutdown
"""
from __future__ import annotations

import logging
import queue
import threading
import time
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from nova_vt.compositor.layers import (
    alpha_over,
    render_avatar,
    render_capture,
    render_image,
    render_text,
)

_log = logging.getLogger(__name__)

_DEFAULT_W = 1920
_DEFAULT_H = 1080

# Cached "No signal" placeholder — generated once on first use
_NO_SIGNAL_CACHE: dict[tuple[int, int], np.ndarray] = {}


def _no_signal_frame(width: int, height: int) -> np.ndarray:
    """Return a dark-grey RGBA placeholder with centred 'No Signal' text."""
    key = (width, height)
    if key in _NO_SIGNAL_CACHE:
        return _NO_SIGNAL_CACHE[key]

    canvas = np.full((height, width, 4), (30, 30, 40, 255), dtype=np.uint8)

    # Draw centred text with Pillow if available, otherwise skip
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.fromarray(canvas, mode="RGBA")
        draw = ImageDraw.Draw(img)
        font_size = max(24, height // 18)
        font = ImageFont.load_default()
        for fp in (
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

        text = "No Signal\nOpen Settings (\u2699) \u2192 Camera to select a device"
        bbox = draw.multiline_textbbox((0, 0), text, font=font)
        tx = (width - (bbox[2] - bbox[0])) // 2
        ty = (height - (bbox[3] - bbox[1])) // 2
        draw.multiline_text((tx, ty), text, font=font, fill=(160, 160, 180, 255), align="center")
        canvas = np.array(img, dtype=np.uint8)
    except Exception:
        pass  # Pillow not installed — plain dark slate is fine

    _NO_SIGNAL_CACHE[key] = canvas
    return canvas


class Compositor(QThread):
    """Alpha-compositing engine that merges webcam + avatar + overlay layers.

    Start it with ``compositor.start()`` (QThread API).
    Stop it with ``compositor.stop()`` followed by ``compositor.wait()``.
    """

    error = pyqtSignal(str)

    def __init__(
        self,
        preview_queue: queue.Queue,
        width: int = _DEFAULT_W,
        height: int = _DEFAULT_H,
        fps: int = 30,
        encoder_queue: queue.Queue | None = None,
    ) -> None:
        super().__init__()
        self._preview_q = preview_queue
        self._encoder_q = encoder_queue
        self._width = width
        self._height = height
        self._fps = fps
        self._stop = threading.Event()

        # External producers push frames into these queues.
        self.webcam_queue: queue.Queue = queue.Queue(maxsize=2)
        self.avatar_queue: queue.Queue = queue.Queue(maxsize=2)

        # Latest drained frames (compositor thread only after drain)
        self._webcam_frame: np.ndarray | None = None
        self._avatar_frame: np.ndarray | None = None

        # Active scene — guarded by _scene_lock
        self._scene_data: dict[str, Any] = {"layers": []}
        self._scene_lock = threading.Lock()

    # ── Public API ───────────────────────────────────────────────────────────

    def set_scene(self, scene_data: dict[str, Any]) -> None:
        """Swap the active scene (thread-safe, takes effect on next frame)."""
        with self._scene_lock:
            self._scene_data = scene_data

    def set_encoder_queue(self, q: queue.Queue | None) -> None:
        """Enable (q is a Queue) or disable (q is None) encoder output."""
        self._encoder_q = q

    def stop(self) -> None:
        """Signal the composite loop to exit."""
        self._stop.set()

    # ── QThread entry point ──────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._composite_loop()
        except Exception as exc:
            _log.exception("Compositor crashed")
            self.error.emit(str(exc))

    # ── Internal ─────────────────────────────────────────────────────────────

    def _composite_loop(self) -> None:
        frame_time = 1.0 / self._fps
        while not self._stop.is_set():
            t0 = time.perf_counter()

            self._drain_sources()
            canvas = self._composite()

            # Half-res preview (960×540 for 1920×1080 source)
            preview = canvas[::2, ::2]
            try:
                self._preview_q.put_nowait(preview)
            except queue.Full:
                pass

            if self._encoder_q is not None:
                try:
                    self._encoder_q.put_nowait(canvas)
                except queue.Full:
                    pass

            elapsed = time.perf_counter() - t0
            sleep = frame_time - elapsed
            if sleep > 0:
                self._stop.wait(sleep)

    def _drain_sources(self) -> None:
        """Pull the most recent frame from each source queue, dropping stale ones."""
        try:
            while True:
                self._webcam_frame = self.webcam_queue.get_nowait()
        except queue.Empty:
            pass

        try:
            while True:
                self._avatar_frame = self.avatar_queue.get_nowait()
        except queue.Empty:
            pass

    def _composite(self) -> np.ndarray:
        """Build and return a (H, W, 4) uint8 RGBA canvas for the current frame."""
        canvas = np.zeros((self._height, self._width, 4), dtype=np.uint8)

        with self._scene_lock:
            layers = sorted(
                self._scene_data.get("layers", []),
                key=lambda l: l.get("z", 0),
            )

        if not layers:
            # No scene configured — show raw webcam feed at full canvas size,
            # or a "No signal" placeholder if no frame has arrived yet.
            if self._webcam_frame is not None:
                frame = self._webcam_frame
                if frame.ndim == 3 and frame.shape[2] == 3:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
                resized = cv2.resize(frame, (self._width, self._height), interpolation=cv2.INTER_LINEAR)
                canvas[:] = resized
            else:
                canvas[:] = _no_signal_frame(self._width, self._height)
            return canvas

        for layer in layers:
            ltype = layer.get("type", "")
            rect_raw = layer.get("rect", [0, 0, self._width, self._height])
            rect = (
                int(rect_raw[0]),
                int(rect_raw[1]),
                int(rect_raw[2]),
                int(rect_raw[3]),
            )

            if ltype == "capture":
                if self._webcam_frame is not None:
                    render_capture(canvas, self._webcam_frame, rect)

            elif ltype == "avatar":
                if self._avatar_frame is not None:
                    render_avatar(canvas, self._avatar_frame, rect)

            elif ltype == "image":
                src = layer.get("src", "")
                if src:
                    render_image(canvas, src, rect)

            elif ltype == "text":
                render_text(canvas, layer, rect)

            else:
                _log.debug("compositor: unknown layer type %r — skipping", ltype)

        return canvas
