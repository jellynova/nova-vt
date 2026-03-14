"""Maps MediaPipe PoseLandmarker world landmarks (33 points) to VRM bone rotations.

MediaPipe landmark indices (upper body subset used here):
  0  = nose          11 = left shoulder   12 = right shoulder
  13 = left elbow    14 = right elbow     15 = left wrist
  16 = right wrist   23 = left hip        24 = right hip

Unmapped VRM bones (fingers, legs, etc.) default to identity quaternion.
"""
from __future__ import annotations

import math
import numpy as np
from nova_vt.tracking.provider import PoseDict, Quaternion, VRM_BONE_NAMES, identity_pose


def landmarks_to_pose(landmarks: list) -> PoseDict:
    """Convert MediaPipe world landmarks to VRM PoseDict.

    Args:
        landmarks: list of objects with .x .y .z (world-space metres)

    Returns:
        PoseDict with all 54 VRM bone names; unmapped bones = identity.
    """
    pose = identity_pose()
    if len(landmarks) < 25:
        return pose

    pts = np.array([[l.x, l.y, l.z] for l in landmarks], dtype=np.float32)

    # Neck: vector from mid-hip to mid-shoulder, expressed as a rotation
    mid_shoulder = (pts[11] + pts[12]) * 0.5
    mid_hip = (pts[23] + pts[24]) * 0.5
    spine_vec = mid_shoulder - mid_hip
    pose["spine"] = _vec_to_quat(spine_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    # Head: nose relative to mid-shoulder
    nose = pts[0]
    head_vec = nose - mid_shoulder
    pose["head"] = _vec_to_quat(head_vec, ref=np.array([0, 1, 0], dtype=np.float32))

    # Shoulders: upper arm direction
    l_upper = pts[13] - pts[11]  # elbow - shoulder
    r_upper = pts[14] - pts[12]
    pose["leftUpperArm"] = _vec_to_quat(l_upper, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightUpperArm"] = _vec_to_quat(r_upper, ref=np.array([1, 0, 0], dtype=np.float32))

    # Forearms: wrist - elbow
    l_lower = pts[15] - pts[13]
    r_lower = pts[16] - pts[14]
    pose["leftLowerArm"] = _vec_to_quat(l_lower, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightLowerArm"] = _vec_to_quat(r_lower, ref=np.array([1, 0, 0], dtype=np.float32))

    # Shoulder bones (clavicle-level): rotation from mid-shoulder to each shoulder
    left_shoulder_vec = pts[11] - mid_shoulder
    right_shoulder_vec = pts[12] - mid_shoulder
    pose["leftShoulder"] = _vec_to_quat(left_shoulder_vec, ref=np.array([-1, 0, 0], dtype=np.float32))
    pose["rightShoulder"] = _vec_to_quat(right_shoulder_vec, ref=np.array([1, 0, 0], dtype=np.float32))

    return pose


def _vec_to_quat(vec: np.ndarray, ref: np.ndarray) -> Quaternion:
    """Return the quaternion rotating `ref` to align with `vec`."""
    v = vec / (np.linalg.norm(vec) + 1e-8)
    r = ref / (np.linalg.norm(ref) + 1e-8)
    cross = np.cross(r, v)
    dot = float(np.dot(r, v))
    cross_len = np.linalg.norm(cross)
    if cross_len < 1e-8:
        # Parallel or anti-parallel
        if dot > 0:
            return (0.0, 0.0, 0.0, 1.0)
        # Anti-parallel: rotate 180° around any perpendicular axis
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
