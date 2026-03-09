from dataclasses import dataclass
import math
import numpy as np
import cv2

# MediaPipe 0.10+ uses the Tasks API; model file must be downloaded separately.
# See docs/setup.md for download instructions.
# Default path relative to project root:
DEFAULT_MODEL_PATH = "face_landmarker.task"


@dataclass
class FaceData:
    head_yaw: float = 0.0    # left/right rotation in degrees
    head_pitch: float = 0.0  # up/down rotation
    head_roll: float = 0.0   # tilt rotation
    mouth_open: float = 0.0  # 0.0-1.0
    blink_left: float = 0.0  # 0.0-1.0 (0=open, 1=closed)
    blink_right: float = 0.0
    brow_left: float = 0.0   # -1.0 to 1.0 (down to up)
    brow_right: float = 0.0


class FaceTracker:
    def __init__(self, model_path: str = DEFAULT_MODEL_PATH):
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision as mp_vision

            options = mp_vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=model_path),
                running_mode=mp_vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.5,
                min_tracking_confidence=0.5,
            )
            self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)
            self._mp = mp
        except Exception:
            # Model file not found or mediapipe unavailable — graceful degradation.
            # process() will return None until a valid model is loaded.
            self._landmarker = None
            self._mp = None

    def process(self, frame: np.ndarray) -> FaceData | None:
        """Process a BGR frame and return FaceData or None if no face detected."""
        if self._landmarker is None:
            return None

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        result = self._landmarker.detect(mp_image)

        if not result.face_landmarks:
            return None

        landmarks = result.face_landmarks[0]
        h, w = frame.shape[:2]
        pts = [(lm.x * w, lm.y * h, lm.z * w) for lm in landmarks]
        return self._extract_face_data(pts)

    def _extract_face_data(self, pts) -> FaceData:
        return FaceData(
            head_yaw=self._estimate_yaw(pts),
            head_pitch=self._estimate_pitch(pts),
            head_roll=self._estimate_roll(pts),
            mouth_open=self._estimate_mouth_open(pts),
            blink_left=self._estimate_blink(pts, eye='left'),
            blink_right=self._estimate_blink(pts, eye='right'),
            brow_left=self._estimate_brow(pts, side='left'),
            brow_right=self._estimate_brow(pts, side='right'),
        )

    def _estimate_yaw(self, pts) -> float:
        nose_tip = pts[1]
        nose_bridge = pts[168]
        return float(nose_tip[0] - nose_bridge[0]) * 0.5

    def _estimate_pitch(self, pts) -> float:
        nose = pts[1]
        chin = pts[152]
        return float(nose[1] - chin[1]) * 0.05

    def _estimate_roll(self, pts) -> float:
        left = pts[33]
        right = pts[263]
        dy = right[1] - left[1]
        dx = right[0] - left[0]
        return float(math.degrees(math.atan2(dy, dx)))

    def _estimate_mouth_open(self, pts) -> float:
        upper = pts[13]
        lower = pts[14]
        dist = abs(upper[1] - lower[1])
        return min(1.0, dist / 20.0)

    def _estimate_blink(self, pts, eye: str) -> float:
        if eye == 'left':
            top, bottom, left, right = pts[159], pts[145], pts[33], pts[133]
        else:
            top, bottom, left, right = pts[386], pts[374], pts[362], pts[263]
        vert = abs(top[1] - bottom[1])
        horiz = abs(left[0] - right[0])
        ear = vert / (horiz + 1e-6)
        return max(0.0, min(1.0, 1.0 - (ear / 0.3)))

    def _estimate_brow(self, pts, side: str) -> float:
        if side == 'left':
            brow, eye = pts[107], pts[159]
        else:
            brow, eye = pts[336], pts[386]
        dist = eye[1] - brow[1]
        return max(-1.0, min(1.0, (dist - 25) / 15.0))

    def close(self):
        if self._landmarker is not None:
            self._landmarker.close()
