"""Maps MediaPipe PoseLandmarker world landmarks (33 points) to VRM bone rotations.

MediaPipe landmark indices (upper body subset used here):
  0  = nose          11 = left shoulder   12 = right shoulder
  13 = left elbow    14 = right elbow     15 = left wrist
  16 = right wrist   23 = left hip        24 = right hip

Unmapped VRM bones default to identity quaternion.
"""
from __future__ import annotations

import math
import numpy as np
from nova_vt.tracking.provider import PoseDict, Quaternion, VRM_BONE_NAMES, identity_pose


def landmarks_to_pose(landmarks: list) -> PoseDict:
    """Convert MediaPipe world landmarks to VRM PoseDict."""
    pose = identity_pose()
    if len(landmarks) < 25:
        return pose

    pts = np.array([[l.x, l.y, l.z] for l in landmarks], dtype=np.float32)

    mid_shoulder = (pts[11] + pts[12]) * 0.5
    mid_hip = (pts[23] + pts[24]) * 0.5
    spine_vec = mid_shoulder - mid_hip
    pose["spine"] = _vec_to_quat(spine_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    nose = pts[0]
    head_vec = nose - mid_shoulder
    pose["head"] = _vec_to_quat(head_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    l_upper = pts[13] - pts[11]
    r_upper = pts[14] - pts[12]
    pose["leftUpperArm"] = _vec_to_quat(l_upper, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightUpperArm"] = _vec_to_quat(r_upper, ref=np.array([1, 0, 0], dtype=np.float32))

    l_lower = pts[15] - pts[13]
    r_lower = pts[16] - pts[14]
    pose["leftLowerArm"] = _vec_to_quat(l_lower, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightLowerArm"] = _vec_to_quat(r_lower, ref=np.array([1, 0, 0], dtype=np.float32))

    shoulder_vec = pts[11] - pts[12]
    shoulder_diff = pts[11][1] - pts[12][1]
    tilt = max(-0.3, min(0.3, shoulder_diff))
    # Also incorporate horizontal shoulder spread to detect asymmetric poses
    shoulder_spread = float(np.linalg.norm(shoulder_vec[:2]))
    tilt_left = tilt + max(-0.1, min(0.1, shoulder_vec[0] * 0.2))
    tilt_right = tilt - max(-0.1, min(0.1, shoulder_vec[0] * 0.2))
    pose["leftShoulder"] = _axis_angle_quat(np.array([0, 0, 1], dtype=np.float32), tilt_left)
    pose["rightShoulder"] = _axis_angle_quat(np.array([0, 0, -1], dtype=np.float32), tilt_right)

    return pose


def _vec_to_quat(vec: np.ndarray, ref: np.ndarray) -> Quaternion:
    v = vec / (np.linalg.norm(vec) + 1e-8)
    r = ref / (np.linalg.norm(ref) + 1e-8)
    cross = np.cross(r, v)
    dot = float(np.dot(r, v))
    cross_len = np.linalg.norm(cross)
    if cross_len < 1e-8:
        if dot > 0:
            return (0.0, 0.0, 0.0, 1.0)
        perp = np.cross(r, np.array([1.0, 0.0, 0.0]))
        if np.linalg.norm(perp) < 1e-8:
            perp = np.cross(r, np.array([0.0, 1.0, 0.0]))
        perp /= np.linalg.norm(perp)
        return (float(perp[0]), float(perp[1]), float(perp[2]), 0.0)
    axis = cross / cross_len
    angle = math.atan2(cross_len, dot)
    s = math.sin(angle / 2)
    return (float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(math.cos(angle / 2)))


def _axis_angle_quat(axis: np.ndarray, angle: float) -> Quaternion:
    s = math.sin(angle / 2)
    c = math.cos(angle / 2)
    return (float(axis[0] * s), float(axis[1] * s), float(axis[2] * s), float(c))
