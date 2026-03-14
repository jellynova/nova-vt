import queue
import time
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication
import sys
_app = QApplication.instance() or QApplication(sys.argv)
from nova_vt.compositor.compositor import Compositor
from nova_vt.compositor.scene import Scene
from nova_vt.compositor.layers import AvatarLayer


def make_rgba(h, w, r, g, b, a=255) -> np.ndarray:
    arr = np.zeros((h, w, 4), dtype=np.uint8)
    arr[:, :] = [r, g, b, a]
    return arr


def test_compositor_alpha_blend():
    """Alpha compositing: semi-transparent foreground over opaque background."""
    bg = make_rgba(4, 4, 255, 0, 0, 255)   # opaque red
    fg = make_rgba(4, 4, 0, 0, 255, 128)   # 50% blue over red
    from nova_vt.compositor.compositor import alpha_over
    result = alpha_over(bg, fg)
    # Result blue channel should be ~128, red ~127
    assert result[0, 0, 2] > 100  # blue present
    assert result[0, 0, 0] > 50   # red still visible


def test_compositor_produces_frames():
    scene = Scene("test", [AvatarLayer(rect=(0, 0, 192, 108))])
    avatar_q: queue.Queue = queue.Queue(maxsize=2)
    preview_q: queue.Queue = queue.Queue(maxsize=4)

    # Pre-fill avatar queue with a frame
    avatar_frame = make_rgba(108, 192, 128, 64, 200, 255)
    avatar_q.put_nowait(avatar_frame)

    comp = Compositor(
        scene=scene,
        avatar_queue=avatar_q,
        preview_queue=preview_q,
        width=192,
        height=108,
        fps=10,
    )
    comp.start()
    time.sleep(0.5)
    comp.stop()
    comp.wait(2000)

    assert not preview_q.empty(), "compositor produced no frames"
    frame = preview_q.get_nowait()
    # Compositor pushes canvas[::2, ::2] (half-res) to preview_queue
    assert frame.shape == (54, 96, 4), f"Expected (54, 96, 4) half-res preview, got {frame.shape}"


def test_compositor_stop_is_clean():
    scene = Scene("empty", [])
    preview_q: queue.Queue = queue.Queue(maxsize=2)
    comp = Compositor(scene=scene, avatar_queue=queue.Queue(), preview_queue=preview_q,
                      width=192, height=108, fps=10)
    comp.start()
    time.sleep(0.2)
    comp.stop()
    assert comp.wait(2000), "compositor did not stop within 2s"
