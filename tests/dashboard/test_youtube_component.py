import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_youtube_worker_not_configured_without_secrets(qtbot, tmp_path):
    get_app()
    from dashboard.components.youtube import YouTubeWorker
    worker = YouTubeWorker(
        secrets_file=tmp_path / "nonexistent.json",
        token_file=tmp_path / "nonexistent.token",
    )
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker.check_config()
    assert ComponentStatus.NOT_CONFIGURED in statuses


def test_youtube_worker_running_with_valid_token(qtbot, tmp_path):
    get_app()
    from dashboard.components.youtube import YouTubeWorker
    secrets = tmp_path / "secrets.json"
    secrets.write_text("{}")
    token = tmp_path / "youtube.token"
    token.write_text("{}")

    worker = YouTubeWorker(secrets_file=secrets, token_file=token)
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.youtube.YouTubeWorker._build_service', return_value=MagicMock()):
        worker.check_config()
        assert ComponentStatus.RUNNING in statuses
