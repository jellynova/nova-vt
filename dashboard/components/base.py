from enum import Enum
from PyQt6.QtCore import QThread, pyqtSignal


class ComponentStatus(Enum):
    RUNNING        = "running"
    STOPPED        = "stopped"
    NOT_CONFIGURED = "not_configured"
    ERROR          = "error"
    CONNECTING     = "connecting"


class ComponentWorker(QThread):
    status_changed = pyqtSignal(ComponentStatus, str)  # status, message

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._status = ComponentStatus.STOPPED

    def _emit_status(self, status: ComponentStatus, message: str = ""):
        self._status = status
        self.status_changed.emit(status, message)

    @property
    def status(self) -> ComponentStatus:
        return self._status
