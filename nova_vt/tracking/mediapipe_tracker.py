from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from nova_vt.tracking.provider import (
    TrackingFrame,
    TrackingProvider,
    PoseDict,
    identity_pose,
)
from nova_vt.tracking.pose_map import landmarks_to_pose

# MediaPipe task model files — downloaded separately
_FACE_TASK = Path(__file__).parents[2] / "face_landmarker.task"
_BODY_TASK = Path(__file__).parents[2] / "pose_landmarker.task"

_ARKIT_NAMES: tuple[str, ...] = (
    "eyeBlinkLeft", "eyeBlinkRight", "eyeLookDownLeft", "eyeLookDownRight",
    "eyeLookInLeft", "eyeLookInRight", "eyeLookOutLeft", "eyeLookOutRight",
    "eyeLookUpLeft", "eyeLookUpRight", "eyeSquintLeft", "eyeSquintRight",
    "eyeWideLeft", "eyeWideRight", "jawForward", "jawLeft", "jawOpen", "jawRight",
    "mouthClose", "mouthDimpleLeft", "mouthDimpleRight", "mouthFrownLeft",
    "mouthFrownRight", "mouthFunnel", "mouthLeft", "mouthLowerDownLeft",
    "mouthLowerDownRight", "mouthPressLeft", "mouthPressRight", "mouthPucker",
    "mouthRight", "mouthRollLower", "mouthRollUpper", "mouthShrugLower",
    "mouthShrugUpper", "mouthSmileLeft", "mouthSmileRight", "mouthStretchLeft",
    "mouthStretchRight", "mouthUpperUpLeft", "mouthUpperUpRight",
    "noseSneerLeft", "noseSneerRight", "cheekPuff", "cheekSquintLeft",
    "cheekSquintRight", "browDownLeft", "browDownRight", "browInnerUp",
    "browOuterUpLeft", "browOuterUpRight", "tongueOut",
)


class MediaPipeTracker(QThread):
    """Captures webcam and runs MediaPipe FaceLandmarker + PoseLandmarker.

    Thread-safe: call get_frame() from any thread.
    Gracefully skips face/pose if model files are not present.
    """

    error = pyqtSignal(str)
    # Emitted on the tracker's own thread each time a new TrackingFrame is ready.
    # Connect to VRMRenderer.update_tracking via Qt::QueuedConnection for thread safety.
    frame_updated = pyqtSignal(object)

    def __init__(self, camera_index: int = 0) -> None:
        super().__init__()
        self._camera_index = camera_index
        self._stop_event = threading.Event()
        self._frame_lock = threading.Lock()
        self._latest = TrackingFrame()

    def get_frame(self) -> TrackingFrame:
        with self._frame_lock:
            return self._latest

    def stop(self) -> None:  # type: ignore[override]
        self._stop_event.set()

    def run(self) -> None:
        try:
            self._run_loop()
        except Exception as exc:
            self.error.emit(str(exc))

    def _run_loop(self) -> None:
        cap = self._open_camera()
        face_landmarker = self._build_face_landmarker()
        pose_landmarker = self._build_pose_landmarker()

        while not self._stop_event.is_set():
            if cap is None or not cap.isOpened():
                self._stop_event.wait(0.5)
                continue
            ret, bgr = cap.read()
            if not ret:
                continue

            try:
                import mediapipe as mp
                rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
                mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
                ts = int(time.time() * 1000)

                blend_shapes: dict[str, float] = {}
                pose = identity_pose()

                if face_landmarker:
                    result = face_landmarker.detect_for_video(mp_image, ts)
                    if result.face_blendshapes:
                        for cat in result.face_blendshapes[0]:
                            arkit = _normalise_arkit(cat.category_name.replace("_", ""))
                            if arkit:
                                blend_shapes[arkit] = max(0.0, min(1.0, cat.score))

                if pose_landmarker:
                    result = pose_landmarker.detect_for_video(mp_image, ts)
                    if result.pose_world_landmarks:
                        pose = landmarks_to_pose(result.pose_world_landmarks[0])

                new_frame = TrackingFrame(
                    pose=pose,
                    blend_shapes=blend_shapes,
                    timestamp=time.time(),
                )
                with self._frame_lock:
                    self._latest = new_frame
                self.frame_updated.emit(new_frame)
            except Exception:
                pass  # don't crash the loop on a bad frame

        if cap:
            cap.release()

    def _open_camera(self) -> Optional[cv2.VideoCapture]:
        for backend in [cv2.CAP_V4L2, cv2.CAP_ANY]:
            cap = cv2.VideoCapture(self._camera_index, backend)
            if cap.isOpened():
                return cap
        return None

    def _build_face_landmarker(self):
        if not _FACE_TASK.exists():
            return None
        try:
            import mediapipe as mp
            opts = mp.tasks.vision.FaceLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(_FACE_TASK)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                output_face_blendshapes=True,
                num_faces=1,
            )
            return mp.tasks.vision.FaceLandmarker.create_from_options(opts)
        except Exception:
            return None

    def _build_pose_landmarker(self):
        if not _BODY_TASK.exists():
            return None
        try:
            import mediapipe as mp
            opts = mp.tasks.vision.PoseLandmarkerOptions(
                base_options=mp.tasks.BaseOptions(model_asset_path=str(_BODY_TASK)),
                running_mode=mp.tasks.vision.RunningMode.VIDEO,
                num_poses=1,
            )
            return mp.tasks.vision.PoseLandmarker.create_from_options(opts)
        except Exception:
            return None


def _normalise_arkit(name: str) -> str | None:
    for arkit in _ARKIT_NAMES:
        if name.lower() == arkit.lower():
            return arkit
    return None
