"""Pure-numpy layer rendering for the compositor.

Each render_* function alpha-composites its content onto *canvas* (H×W×4 uint8)
at *rect* = (x, y, w, h) in canvas pixel coordinates using Porter-Duff src-over.
"""
from __future__ import annotations

import logging
from typing import Any

import cv2
import numpy as np

_log = logging.getLogger(__name__)

# Module-level image cache: path → RGBA uint8 array (original resolution)
_image_cache: dict[str, np.ndarray] = {}


# ── Compositing primitive ────────────────────────────────────────────────────

def alpha_over(base: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """Porter-Duff src-over: *overlay* drawn on top of *base*.

    Both arrays are H×W×4 uint8.  Returns a new H×W×4 uint8 array.
    """
    a = overlay[:, :, 3:4].astype(np.float32) / 255.0
    inv_a = 1.0 - a
    rgb = (overlay[:, :, :3].astype(np.float32) * a
           + base[:, :, :3].astype(np.float32) * inv_a)
    alpha = overlay[:, :, 3:4].astype(np.float32) + base[:, :, 3:4].astype(np.float32) * inv_a
    return np.concatenate([rgb, alpha], axis=2).clip(0, 255).astype(np.uint8)


def _place(canvas: np.ndarray, tile: np.ndarray, rect: tuple[int, int, int, int]) -> None:
    """Resize *tile* to *rect* dimensions and alpha-composite onto *canvas* in-place."""
    H, W = canvas.shape[:2]
    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return

    tile_resized = cv2.resize(tile, (w, h), interpolation=cv2.INTER_LINEAR)

    # Clamp to canvas bounds
    x1, y1 = max(x, 0), max(y, 0)
    x2, y2 = min(x + w, W), min(y + h, H)
    if x2 <= x1 or y2 <= y1:
        return
    tx1, ty1 = x1 - x, y1 - y
    tx2, ty2 = tx1 + (x2 - x1), ty1 + (y2 - y1)

    canvas[y1:y2, x1:x2] = alpha_over(
        canvas[y1:y2, x1:x2],
        tile_resized[ty1:ty2, tx1:tx2],
    )


# ── Layer renderers ──────────────────────────────────────────────────────────

def render_capture(
    canvas: np.ndarray,
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
) -> None:
    """Blit a webcam frame (BGR or RGBA, any resolution) onto *canvas* at *rect*."""
    if frame.ndim == 3 and frame.shape[2] == 3:
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    elif frame.ndim == 3 and frame.shape[2] == 4:
        pass  # already RGBA
    else:
        return
    _place(canvas, frame, rect)


def render_avatar(
    canvas: np.ndarray,
    frame: np.ndarray,
    rect: tuple[int, int, int, int],
) -> None:
    """Blit an avatar RGBA frame onto *canvas* at *rect*."""
    _place(canvas, frame, rect)


def render_image(
    canvas: np.ndarray,
    src: str,
    rect: tuple[int, int, int, int],
) -> None:
    """Load (and cache) *src* as RGBA, then blit onto *canvas* at *rect*."""
    if src not in _image_cache:
        img = cv2.imread(src, cv2.IMREAD_UNCHANGED)
        if img is None:
            _log.warning("compositor: could not load image %r", src)
            return
        if img.ndim == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
        elif img.shape[2] == 3:
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
        _image_cache[src] = img

    _place(canvas, _image_cache[src], rect)


def render_text(
    canvas: np.ndarray,
    layer: dict[str, Any],
    rect: tuple[int, int, int, int],
) -> None:
    """Render text from *layer* dict onto *canvas* at *rect* using Pillow."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        _log.warning("compositor: Pillow not installed — text layers skipped")
        return

    text = layer.get("text", "")
    if not text:
        return

    x, y, w, h = rect
    if w <= 0 or h <= 0:
        return

    color_hex = layer.get("color", "#ffffff").lstrip("#")
    try:
        r_c = int(color_hex[0:2], 16)
        g_c = int(color_hex[2:4], 16)
        b_c = int(color_hex[4:6], 16)
    except ValueError:
        r_c, g_c, b_c = 255, 255, 255

    font_size = max(8, int(layer.get("font_size", 32)))

    tile = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(tile)

    font = ImageFont.load_default()
    for font_path in (
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            font = ImageFont.truetype(font_path, font_size)
            break
        except Exception:
            continue

    draw.text((4, 4), text, font=font, fill=(r_c, g_c, b_c, 255))

    tile_arr = np.array(tile, dtype=np.uint8)
    # Pillow RGBA → already RGBA, no conversion needed
    _place(canvas, tile_arr, rect)
