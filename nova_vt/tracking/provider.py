from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Full VRM 0.x humanoid bone name list (54 bones)
VRM_BONE_NAMES: tuple[str, ...] = (
    "hips", "spine", "chest", "upperChest", "neck", "head",
    "leftEye", "rightEye",
    "leftShoulder", "rightShoulder",
    "leftUpperArm", "rightUpperArm",
    "leftLowerArm", "rightLowerArm",
    "leftHand", "rightHand",
    "leftThumbProximal", "leftThumbIntermediate", "leftThumbDistal",
    "leftIndexProximal", "leftIndexIntermediate", "leftIndexDistal",
    "leftMiddleProximal", "leftMiddleIntermediate", "leftMiddleDistal",
    "leftRingProximal", "leftRingIntermediate", "leftRingDistal",
    "leftLittleProximal", "leftLittleIntermediate", "leftLittleDistal",
    "rightThumbProximal", "rightThumbIntermediate", "rightThumbDistal",
    "rightIndexProximal", "rightIndexIntermediate", "rightIndexDistal",
    "rightMiddleProximal", "rightMiddleIntermediate", "rightMiddleDistal",
    "rightRingProximal", "rightRingIntermediate", "rightRingDistal",
    "rightLittleProximal", "rightLittleIntermediate", "rightLittleDistal",
    "leftUpperLeg", "rightUpperLeg",
    "leftLowerLeg", "rightLowerLeg",
    "leftFoot", "rightFoot",
    "leftToes", "rightToes",
)

Quaternion = tuple[float, float, float, float]
PoseDict = dict[str, Quaternion]

IDENTITY_QUATERNION: Quaternion = (0.0, 0.0, 0.0, 1.0)


def identity_pose() -> PoseDict:
    """Return a PoseDict with all 54 bones set to identity rotation."""
    return {bone: IDENTITY_QUATERNION for bone in VRM_BONE_NAMES}


@dataclass
class TrackingFrame:
    pose: PoseDict = field(default_factory=identity_pose)
    blend_shapes: dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@runtime_checkable
class TrackingProvider(Protocol):
    def get_frame(self) -> TrackingFrame: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
