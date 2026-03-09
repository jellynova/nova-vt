from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QScrollArea,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSlot, QSize
from PyQt6.QtGui import QPixmap, QImage

from dashboard.components.base import ComponentStatus
from dashboard.camera import WebcamWorker, AvatarCameraWorker


_STATUS_STYLE = {
    ComponentStatus.RUNNING:        ("●", "#a6e3a1"),
    ComponentStatus.STOPPED:        ("●", "#6c7086"),
    ComponentStatus.NOT_CONFIGURED: ("●", "#f9e2af"),
    ComponentStatus.ERROR:          ("●", "#f38ba8"),
    ComponentStatus.CONNECTING:     ("◌", "#89b4fa"),
}

_SCENES = ["Gameplay", "Just Chatting", "BRB", "Starting Soon"]


class StatusPill(QFrame):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._label = QLabel(name)
        self._msg = QLabel("")

        for w in (self._dot, self._label, self._msg):
            layout.addWidget(w)

        self.update_status(ComponentStatus.STOPPED)

    def update_status(self, status: ComponentStatus, message: str = ""):
        dot, color = _STATUS_STYLE[status]
        self._dot.setText(dot)
        self._dot.setStyleSheet(f"color: {color};")
        self._msg.setText(f"({message})" if message else "")


class CameraPane(QLabel):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setText(placeholder)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(320, 240))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("border-radius: 8px;")

    @pyqtSlot(QImage)
    def update_frame(self, image: QImage):
        self.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class NovaVTWindow(QMainWindow):
    def __init__(self, config, obs_worker, twitch_worker, youtube_worker,
                 tracker_worker, godot_worker, overlay_worker, theme):
        super().__init__()
        self.setWindowTitle("nova-vt")
        self.resize(1280, 720)

        self._obs = obs_worker
        self._twitch = twitch_worker
        self._youtube = youtube_worker
        self._tracker = tracker_worker
        self._godot = godot_worker
        self._overlay = overlay_worker

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # --- Camera strip ---
        cam_row = QHBoxLayout()
        self._webcam_pane = CameraPane("📷  Webcam (no camera)")
        self._avatar_pane = CameraPane("🎭  Avatar (Godot not running)")
        cam_row.addWidget(self._webcam_pane)
        cam_row.addWidget(self._avatar_pane)
        root.addLayout(cam_row, stretch=4)

        # --- Status pills ---
        pills_row = QHBoxLayout()
        self._pills = {
            "tracker":  StatusPill("Tracker"),
            "godot":    StatusPill("Godot"),
            "obs":      StatusPill("OBS"),
            "twitch":   StatusPill("Twitch"),
            "youtube":  StatusPill("YouTube"),
            "overlays": StatusPill("Overlays"),
        }
        for pill in self._pills.values():
            pills_row.addWidget(pill)
        pills_row.addStretch()
        root.addLayout(pills_row)

        # --- Controls ---
        ctrl_row = QHBoxLayout()
        self._btn_start = QPushButton("▶  Start Stream")
        self._btn_stop  = QPushButton("⏹  Stop")
        self._scene_box = QComboBox()
        self._scene_box.addItems(_SCENES)

        for w in (self._btn_start, self._btn_stop, QLabel("Scene:"), self._scene_box):
            ctrl_row.addWidget(w)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        # --- Chat feed ---
        self._chat_list = QScrollArea()
        self._chat_widget = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._chat_list.setWidget(self._chat_widget)
        self._chat_list.setWidgetResizable(True)
        root.addWidget(self._chat_list, stretch=2)

        self._connect_signals()
        self._start_cameras()

    def _connect_signals(self):
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._scene_box.currentTextChanged.connect(self._on_scene_changed)

        for name, worker in [
            ("tracker", self._tracker),
            ("godot",   self._godot),
            ("obs",     self._obs),
            ("twitch",  self._twitch),
            ("youtube", self._youtube),
            ("overlays", self._overlay),
        ]:
            pill = self._pills[name]
            worker.status_changed.connect(
                lambda s, m, p=pill: p.update_status(s, m)
            )

        self._twitch.chat_message.connect(self._on_chat_message)

    def _start_cameras(self):
        self._webcam = WebcamWorker(device_index=0)
        self._webcam.frame_ready.connect(self._webcam_pane.update_frame)
        self._webcam.start()

        self._avatar_cam = AvatarCameraWorker()
        self._avatar_cam.frame_ready.connect(self._avatar_pane.update_frame)
        self._avatar_cam.start()

    def _on_start(self):
        self._tracker.start_tracker()
        self._godot.start_godot()
        self._obs.connect_obs()
        if self._twitch.status != ComponentStatus.RUNNING:
            self._twitch.start_bot()

    def _on_stop(self):
        self._tracker.stop_tracker()
        self._godot.stop_godot()
        self._obs.disconnect_obs()
        self._twitch.stop_bot()

    def _on_scene_changed(self, scene_name: str):
        self._obs.switch_scene(scene_name)

    @pyqtSlot(str, str)
    def _on_chat_message(self, user: str, message: str):
        label = QLabel(f"<b>{user}</b>: {message}")
        label.setWordWrap(True)
        self._chat_layout.insertWidget(0, label)
        while self._chat_layout.count() > 20:
            item = self._chat_layout.takeAt(self._chat_layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

    def closeEvent(self, event):
        self._webcam.stop()
        self._avatar_cam.stop()
        self._on_stop()
        super().closeEvent(event)
