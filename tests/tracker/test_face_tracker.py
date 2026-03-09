import numpy as np
import pytest
from tracker.face_tracker import FaceTracker, FaceData


def make_blank_frame():
    return np.zeros((480, 640, 3), dtype=np.uint8)


def test_face_data_is_dataclass():
    data = FaceData()
    assert hasattr(data, 'head_yaw')
    assert hasattr(data, 'head_pitch')
    assert hasattr(data, 'head_roll')
    assert hasattr(data, 'mouth_open')
    assert hasattr(data, 'blink_left')
    assert hasattr(data, 'blink_right')
    assert hasattr(data, 'brow_left')
    assert hasattr(data, 'brow_right')


def test_face_tracker_returns_none_on_blank_frame():
    tracker = FaceTracker()
    frame = make_blank_frame()
    result = tracker.process(frame)
    assert result is None


def test_face_tracker_closes_cleanly():
    tracker = FaceTracker()
    tracker.close()  # should not raise
