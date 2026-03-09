import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_tracker_worker_starts_subprocess(qtbot):
    get_app()
    from dashboard.components.tracker import TrackerWorker
    worker = TrackerWorker()
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.tracker.subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc
        worker.start_tracker()
        assert ComponentStatus.RUNNING in statuses


def test_tracker_worker_stops_cleanly(qtbot):
    get_app()
    from dashboard.components.tracker import TrackerWorker
    worker = TrackerWorker()

    with patch('dashboard.components.tracker.subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        worker.start_tracker()
        worker.stop_tracker()
        mock_proc.terminate.assert_called_once()


def test_godot_worker_detects_missing_binary(qtbot):
    get_app()
    from dashboard.components.godot import GodotWorker
    worker = GodotWorker()
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.godot.shutil.which', return_value=None):
        worker.start_godot()
        assert ComponentStatus.ERROR in statuses
