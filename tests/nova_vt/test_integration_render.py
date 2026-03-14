"""Integration test: full rendering pipeline → PNG.

Requires: model.vrm present, EGL available, MediaPipe models optional.
Run: EGL_PLATFORM=surfaceless pytest tests/nova_vt/test_integration_render.py -v -s
"""
import os
import queue
import time
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("EGL_PLATFORM", "surfaceless")

try:
    import moderngl
    import cv2
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

from PyQt6.QtWidgets import QApplication
import sys
_app = QApplication.instance() or QApplication(sys.argv)

VRM_PATH = Path(__file__).parents[2] / "model.vrm"
OUTPUT_PATH = Path("/tmp/nova-vt-test-frame.png")


@pytest.mark.skipif(not HAS_DEPS, reason="moderngl or cv2 not installed")
def test_pipeline_renders_to_png():
    if not VRM_PATH.exists():
        pytest.skip("model.vrm not found")

    from nova_vt.renderer.vrm_loader import VRMLoader
    from nova_vt.renderer.vrm_renderer import VRMRenderer
    from nova_vt.compositor.compositor import Compositor
    from nova_vt.compositor.scene import Scene
    from nova_vt.compositor.layers import AvatarLayer

    avatar_q: queue.Queue = queue.Queue(maxsize=2)
    preview_q: queue.Queue = queue.Queue(maxsize=4)

    loader = VRMLoader(VRM_PATH)
    renderer = VRMRenderer(loader, preview_queue=avatar_q, width=960, height=540)
    scene = Scene("test", [AvatarLayer(rect=(0, 0, 960, 540))])
    comp = Compositor(scene=scene, avatar_queue=avatar_q, preview_queue=preview_q,
                      width=960, height=540, fps=10)

    renderer.start()
    comp.start()
    time.sleep(2.0)
    renderer.stop()
    comp.stop()
    renderer.wait(3000)
    comp.wait(3000)

    assert not preview_q.empty(), "pipeline produced no composite frames"
    frame = preview_q.get_nowait()
    assert frame.dtype == np.uint8
    assert frame.ndim == 3 and frame.shape[2] == 4

    # Write to PNG for visual inspection
    bgra = cv2.cvtColor(frame, cv2.COLOR_RGBA2BGRA)
    cv2.imwrite(str(OUTPUT_PATH), bgra)
    print(f"\nFrame written to {OUTPUT_PATH} — inspect visually.")
    assert OUTPUT_PATH.exists()
