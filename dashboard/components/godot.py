import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GODOT_PATH = _PROJECT_ROOT / "avatar"
_GODOT_SCENE = str(_GODOT_PATH / "scenes" / "main.tscn")


class GodotWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("godot", parent)
        self._proc: subprocess.Popen | None = None
        self._timer = QTimer()
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._check_health)

    def start_godot(self):
        if not shutil.which("godot"):
            self._emit_status(ComponentStatus.ERROR, "godot not found in PATH")
            return
        if self._proc and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(
                ["godot", "--path", str(_GODOT_PATH), _GODOT_SCENE]
            )
            self._emit_status(ComponentStatus.RUNNING, f"pid {self._proc.pid}")
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def stop_godot(self):
        self._timer.stop()
        if self._proc:
            self._proc.terminate()
            self._proc = None
        self._emit_status(ComponentStatus.STOPPED)

    def _check_health(self):
        if self._proc and self._proc.poll() is not None:
            self._emit_status(ComponentStatus.ERROR, f"exited with {self._proc.returncode}")
            self._timer.stop()
