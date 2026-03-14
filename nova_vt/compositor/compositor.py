from __future__ import annotations

import queue
import threading
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from nova_vt.compositor.scene import Scene
from nova_vt.compositor.layers import (
    CaptureLayer, AvatarLayer, ImageLayer, TextLayer, Layer,
)


def alpha_over(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """Alpha-composite `src` over `dst` (both H×W×4 uint8). Returns new array."""
    src_a = src[:, :, 3:4].astype(np.float32) / 255.0
    dst_a = dst[:, :, 3:4].astype(np.float32) / 255.0
    out_a = src_a + dst_a * (1.0 - src_a)
    src_rgb = src[:, :, :3].astype(np.float32)
    dst_rgb = dst[:, :, :3].astype(np.float32)
    out_rgb = (src_rgb * src_a + dst_rgb * dst_a * (1.0 - src_a)) / (out_a + 1e-8)
    result = np.zeros_like(dst)
    result[:, :, :3] = np.clip(out_rgb, 0, 255).astype(np.uint8)
    result[:, :, 3] = np.clip(out_a[:, :, 0] * 255, 0, 255).astype(np.uint8)
    return result


class Compositor(QThread):
    """Composites layers each frame and pushes to preview_queue (and encoder_queue when live).

    Layer order: back-to-front (layers[0] is bottommost).
    """

    error = pyqtSignal(str)

    def __init__(
        self,
        scene: Scene,
        avatar_queue: queue.Queue,
        preview_queue: queue.Queue,
        width: int = 1920,
        height: int = 1080,
        fps: int = 30,
        encoder_queue: Optional[queue.Queue] = None,
        stats: Optional[object] = None,  # StreamStats, added in Plan 2
    ) -> None:
        super().__init__()
        self._scene = scene
        self._avatar_q = avatar_queue
        self._preview_q = preview_queue
        self._encoder_q = encoder_queue
        self._stats = stats
        self._width = width
        self._height = height
        self._fps = fps
        self._stop_event = threading.Event()
        self._scene_lock = threading.Lock()
        self._capture_caches: dict[str, cv2.VideoCapture] = {}
        self._image_caches: dict[str, np.ndarray] = {}
        self._latest_avatar: Optional[np.ndarray] = None

    def switch_scene(self, scene: Scene) -> None:
        with self._scene_lock:
            self._scene = scene

    def set_encoder_queue(self, q: Optional[queue.Queue]) -> None:
        self._encoder_q = q

    def stop(self) -> None:  # type: ignore[override]
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._composite_loop()
        except Exception as exc:
            self.error.emit(str(exc))

    def _composite_loop(self) -> None:
        frame_time = 1.0 / self._fps
        while not self._stop_event.is_set():
            t0 = time.perf_counter()

            # Drain avatar queue for latest frame
            while True:
                try:
                    self._latest_avatar = self._avatar_q.get_nowait()
                except queue.Empty:
                    break

            with self._scene_lock:
                scene = self._scene

            canvas = np.zeros((self._height, self._width, 4), dtype=np.uint8)
            for layer in scene.layers:
                layer_img = self._render_layer(layer)
                if layer_img is not None:
                    canvas = self._blit(canvas, layer_img, layer)

            # Push preview (half-res)
            preview = canvas[::2, ::2]
            try:
                self._preview_q.put_nowait(preview)
            except queue.Full:
                pass

            # Push to encoder when live
            if self._encoder_q is not None:
                try:
                    self._encoder_q.put_nowait(canvas)
                except queue.Full:
                    pass

            elapsed = time.perf_counter() - t0
            sleep = frame_time - elapsed
            if sleep > 0:
                self._stop_event.wait(sleep)

        for cap in self._capture_caches.values():
            cap.release()

    def _render_layer(self, layer: Layer) -> Optional[np.ndarray]:
        if isinstance(layer, AvatarLayer):
            if self._latest_avatar is None:
                return None
            w, h = layer.rect[2], layer.rect[3]
            return cv2.resize(self._latest_avatar, (w, h), interpolation=cv2.INTER_LINEAR)

        if isinstance(layer, CaptureLayer):
            cap = self._capture_caches.get(layer.device)
            if cap is None:
                cap = cv2.VideoCapture(layer.device, cv2.CAP_V4L2)
                self._capture_caches[layer.device] = cap
            if not cap.isOpened():
                return None
            ret, bgr = cap.read()
            if not ret:
                return None
            rgba = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGBA)
            w, h = layer.rect[2], layer.rect[3]
            return cv2.resize(rgba, (w, h), interpolation=cv2.INTER_LINEAR)

        if isinstance(layer, ImageLayer):
            img = self._image_caches.get(layer.path)
            if img is None:
                raw = cv2.imread(layer.path, cv2.IMREAD_UNCHANGED)
                if raw is None:
                    return None
                if raw.shape[2] == 3:
                    raw = cv2.cvtColor(raw, cv2.COLOR_BGR2RGBA)
                else:
                    raw = cv2.cvtColor(raw, cv2.COLOR_BGRA2RGBA)
                self._image_caches[layer.path] = raw
                img = raw
            w, h = layer.rect[2], layer.rect[3]
            resized = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR)
            if layer.opacity < 1.0:
                resized = resized.copy()
                resized[:, :, 3] = (resized[:, :, 3] * layer.opacity).astype(np.uint8)
            return resized

        if isinstance(layer, TextLayer):
            content = self._resolve_template(layer.content)
            w, h = layer.rect[2], layer.rect[3]
            img = np.zeros((h, w, 4), dtype=np.uint8)
            color_hex = layer.color.lstrip("#")
            r, g, b = int(color_hex[0:2], 16), int(color_hex[2:4], 16), int(color_hex[4:6], 16)
            scale = layer.font_size / 30.0
            cv2.putText(img, content, (4, h - 8), cv2.FONT_HERSHEY_SIMPLEX,
                        scale, (b, g, r, 255), 1, cv2.LINE_AA)
            return img

        return None

    def _blit(self, canvas: np.ndarray, layer_img: np.ndarray, layer: Layer) -> np.ndarray:
        x, y = layer.rect[0], layer.rect[1]
        h, w = layer_img.shape[:2]
        # Clamp to canvas bounds
        x2 = min(x + w, self._width)
        y2 = min(y + h, self._height)
        if x2 <= x or y2 <= y:
            return canvas
        cw, ch = x2 - x, y2 - y
        roi = canvas[y:y2, x:x2]
        src = layer_img[:ch, :cw]
        canvas[y:y2, x:x2] = alpha_over(roi, src)
        return canvas

    def _resolve_template(self, content: str) -> str:
        if self._stats is None:
            return content
        # StreamStats attributes (added in Plan 2)
        replacements = {
            "{total_viewers}": str(getattr(self._stats, "total_viewers", 0)),
            "{twitch_viewers}": str(getattr(self._stats, "twitch_viewers", 0)),
            "{youtube_viewers}": str(getattr(self._stats, "youtube_viewers", 0)),
            "{tiktok_viewers}": str(getattr(self._stats, "tiktok_viewers", 0)),
            "{stream_time}": getattr(self._stats, "stream_time_str", "00:00:00"),
        }
        for k, v in replacements.items():
            content = content.replace(k, v)
        return content
