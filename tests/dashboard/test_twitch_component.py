import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_twitch_worker_not_configured_without_token(qtbot):
    get_app()
    from dashboard.components.twitch import TwitchWorker
    worker = TwitchWorker(token="", channel="", client_id="")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker.check_config()
    assert ComponentStatus.NOT_CONFIGURED in statuses


def test_oauth_server_extracts_token():
    from dashboard.components.twitch import _extract_token_from_callback
    token = _extract_token_from_callback("/?access_token=abc123&scope=chat")
    assert token == "abc123"


def test_oauth_server_returns_none_without_token():
    from dashboard.components.twitch import _extract_token_from_callback
    token = _extract_token_from_callback("/callback")
    assert token is None
