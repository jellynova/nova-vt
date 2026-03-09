import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_obs_worker_connects_successfully(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="test")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.obs.OBSController') as mock_cls:
        mock_ctrl = MagicMock()
        mock_ctrl.current_scene.return_value = "Gameplay"
        mock_cls.return_value = mock_ctrl
        worker.connect_obs()
        assert ComponentStatus.RUNNING in statuses


def test_obs_worker_emits_error_on_connection_failure(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="wrong")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.obs.OBSController', side_effect=Exception("refused")):
        worker.connect_obs()
        assert ComponentStatus.ERROR in statuses


def test_obs_worker_emits_current_scene(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="test")
    scenes = []
    worker.scene_changed.connect(lambda s: scenes.append(s))

    with patch('dashboard.components.obs.OBSController') as mock_cls:
        mock_ctrl = MagicMock()
        mock_ctrl.current_scene.return_value = "BRB"
        mock_cls.return_value = mock_ctrl
        worker.connect_obs()
        assert "BRB" in scenes
