import numpy as np
from nova_vt.tracking.pose_map import landmarks_to_pose
from nova_vt.tracking.provider import VRM_BONE_NAMES, IDENTITY_QUATERNION


class _FakeLandmark:
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x = x; self.y = y; self.z = z


def make_landmarks(n=33):
    return [_FakeLandmark() for _ in range(n)]


def test_returns_dict_with_all_bone_names():
    pose = landmarks_to_pose(make_landmarks())
    assert set(pose.keys()) == set(VRM_BONE_NAMES)


def test_unmapped_bones_are_identity():
    pose = landmarks_to_pose(make_landmarks())
    assert pose["leftThumbProximal"] == IDENTITY_QUATERNION
    assert pose["rightIndexDistal"] == IDENTITY_QUATERNION


def test_shoulder_differs_when_landmarks_differ():
    lms = make_landmarks()
    lms[11] = _FakeLandmark(x=0.3, y=-0.4, z=0.1)
    lms[12] = _FakeLandmark(x=-0.3, y=-0.4, z=0.1)
    pose = landmarks_to_pose(lms)
    assert pose["leftShoulder"] != IDENTITY_QUATERNION or pose["rightShoulder"] != IDENTITY_QUATERNION


def test_quaternion_is_unit_length():
    lms = make_landmarks()
    lms[11] = _FakeLandmark(x=0.5, y=-0.5, z=0.2)
    pose = landmarks_to_pose(lms)
    for bone, q in pose.items():
        length = sum(v ** 2 for v in q) ** 0.5
        assert abs(length - 1.0) < 1e-5, f"{bone} quaternion not unit length: {q}"
