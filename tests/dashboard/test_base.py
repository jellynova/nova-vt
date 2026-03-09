import sys
from dashboard.components.base import ComponentStatus, ComponentWorker
from PyQt6.QtCore import QCoreApplication


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_component_status_values():
    assert ComponentStatus.RUNNING.value == "running"
    assert ComponentStatus.STOPPED.value == "stopped"
    assert ComponentStatus.NOT_CONFIGURED.value == "not_configured"
    assert ComponentStatus.ERROR.value == "error"
    assert ComponentStatus.CONNECTING.value == "connecting"


def test_component_worker_emits_status(qtbot):
    get_app()
    worker = ComponentWorker("test")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker._emit_status(ComponentStatus.RUNNING)
    assert statuses == [ComponentStatus.RUNNING]
