from PyQt6.QtCore import pyqtSignal, QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus
from orchestrator.obs_controller import OBSController


class OBSWorker(ComponentWorker):
    scene_changed = pyqtSignal(str)

    def __init__(self, host: str, port: int, password: str, parent=None):
        super().__init__("obs", parent)
        self._host = host
        self._port = port
        self._password = password
        self._ctrl: OBSController | None = None
        self._timer = QTimer()
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._poll)

    def connect_obs(self):
        self._emit_status(ComponentStatus.CONNECTING)
        try:
            self._ctrl = OBSController(self._host, self._port, self._password)
            scene = self._ctrl.current_scene()
            self._emit_status(ComponentStatus.RUNNING, scene)
            self.scene_changed.emit(scene)
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def switch_scene(self, scene_name: str):
        if self._ctrl:
            try:
                self._ctrl.switch_scene(scene_name)
                self.scene_changed.emit(scene_name)
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

    def disconnect_obs(self):
        self._timer.stop()
        if self._ctrl:
            self._ctrl.disconnect()
            self._ctrl = None
        self._emit_status(ComponentStatus.STOPPED)

    def _poll(self):
        if not self._ctrl:
            return
        try:
            scene = self._ctrl.current_scene()
            self.scene_changed.emit(scene)
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))
            self._timer.stop()
