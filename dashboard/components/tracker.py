import subprocess
import sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus

_TRACKER_CMD = [sys.executable, "-m", "tracker.main"]
_PROJECT_ROOT = Path(__file__).parent.parent.parent


class TrackerWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("tracker", parent)
        self._proc: subprocess.Popen | None = None
        self._timer = QTimer()
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._check_health)

    def start_tracker(self):
        if self._proc and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(_TRACKER_CMD, cwd=_PROJECT_ROOT)
            self._emit_status(ComponentStatus.RUNNING, f"pid {self._proc.pid}")
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def stop_tracker(self):
        self._timer.stop()
        if self._proc:
            self._proc.terminate()
            self._proc = None
        self._emit_status(ComponentStatus.STOPPED)

    def _check_health(self):
        if self._proc and self._proc.poll() is not None:
            self._emit_status(ComponentStatus.ERROR, f"exited with {self._proc.returncode}")
            self._timer.stop()
