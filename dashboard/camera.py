import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap


def _frame_to_qimage(frame: np.ndarray) -> QImage:
    h, w, ch = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)

    def __init__(self, device_index: int | str, fps: int = 30, parent=None):
        super().__init__(parent)
        self._device = device_index
        self._fps = fps
        self._running = False

    def run(self):
        self._running = True
        cap = cv2.VideoCapture(self._device)
        cap.set(cv2.CAP_PROP_FPS, self._fps)
        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(_frame_to_qimage(frame))
            else:
                self.msleep(100)
        cap.release()

    def stop(self):
        self._running = False
        self.wait(2000)


class WebcamWorker(CameraWorker):
    """Raw webcam feed."""
    def __init__(self, device_index: int = 0, parent=None):
        super().__init__(device_index, fps=30, parent=parent)


class AvatarCameraWorker(CameraWorker):
    """Godot avatar via v4l2loopback virtual camera."""
    def __init__(self, device: str = "/dev/video10", parent=None):
        super().__init__(device, fps=30, parent=parent)
