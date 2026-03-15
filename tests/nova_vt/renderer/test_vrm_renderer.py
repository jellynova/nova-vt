import os
import queue
import time
from pathlib import Path
import numpy as np
import pytest

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

try:
    import moderngl
    HAS_EGL = True
except Exception:
    HAS_EGL = False

from nova_vt.renderer.vrm_loader import VRMLoader
from nova_vt.renderer.vrm_renderer import VRMRenderer

VRM_PATH = Path(__file__).parents[3] / "model.vrm"


@pytest.mark.skipif(not HAS_EGL, reason="moderngl/EGL not available")
def test_renderer_produces_rgba_frame():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")

    preview_q: queue.Queue = queue.Queue(maxsize=2)
    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=preview_q, width=192, height=108)
    renderer.start()
    time.sleep(1.0)
    renderer.stop()
    renderer.wait(3000)

    assert not preview_q.empty(), "renderer did not produce any frames"
    frame = preview_q.get_nowait()
    assert isinstance(frame, np.ndarray)
    assert frame.shape == (54, 96, 4), f"Expected (54, 96, 4) half-res preview, got {frame.shape}"
    assert frame.dtype == np.uint8


@pytest.mark.skipif(not HAS_EGL, reason="moderngl/EGL not available")
def test_renderer_stops_cleanly():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")
    preview_q: queue.Queue = queue.Queue(maxsize=2)
    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=preview_q, width=192, height=108)
    renderer.start()
    time.sleep(0.3)
    renderer.stop()
    assert renderer.wait(3000), "renderer thread did not exit within 3s"
