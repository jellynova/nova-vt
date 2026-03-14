import time
import threading
import pytest
import numpy as np
from nova_vt.tracking.mediapipe_tracker import MediaPipeTracker
from nova_vt.tracking.provider import TrackingFrame, VRM_BONE_NAMES


def test_tracker_implements_provider_protocol():
    from nova_vt.tracking.provider import TrackingProvider
    tracker = MediaPipeTracker(camera_index=0)
    assert isinstance(tracker, TrackingProvider)


def test_get_frame_before_start_returns_identity():
    tracker = MediaPipeTracker(camera_index=0)
    frame = tracker.get_frame()
    assert isinstance(frame, TrackingFrame)
    # All poses should be identity before camera is open
    for bone, q in frame.pose.items():
        assert q == (0.0, 0.0, 0.0, 1.0), f"{bone} should be identity"


def test_tracker_start_stop_without_camera():
    """Tracker should start and stop without raising even if camera fails to open."""
    tracker = MediaPipeTracker(camera_index=99)  # non-existent
    tracker.start()
    time.sleep(0.2)
    tracker.stop()
    assert tracker.wait(2000), "tracker did not stop within 2s"


def test_blend_shapes_are_valid_range():
    """blend_shapes values should always be clamped 0..1."""
    tracker = MediaPipeTracker(camera_index=0)
    frame = tracker.get_frame()
    for k, v in frame.blend_shapes.items():
        assert 0.0 <= v <= 1.0, f"{k} = {v} out of range"
