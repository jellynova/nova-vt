import sys
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QTabWidget, QLineEdit, QPushButton, QComboBox
from PyQt6.QtCore import Qt
from nova_vt.dashboard.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_dialog(qtbot):
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")
    with patch("nova_vt.dashboard.settings_dialog.sounddevice") as mock_sd:
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Output", "max_output_channels": 2},
            {"name": "USB Headset", "max_output_channels": 2},
        ]
        dialog = SettingsDialog(config=mock_config)
        qtbot.addWidget(dialog)
        return dialog, mock_config


def test_settings_dialog_has_four_tabs(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    tabs = dialog.findChildren(QTabWidget)
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.count() == 4
    labels = [tab.tabText(i) for i in range(tab.count())]
    assert "Twitch" in labels
    assert "YouTube" in labels
    assert "TikTok" in labels
    assert "Audio" in labels


def test_settings_dialog_twitch_tab_has_fields(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._twitch_channel is not None
    assert dialog._twitch_client_id is not None
    assert dialog._twitch_token is not None
    assert isinstance(dialog._twitch_channel, QLineEdit)


def test_settings_dialog_twitch_connect_button_exists(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._twitch_connect_btn is not None
    assert isinstance(dialog._twitch_connect_btn, QPushButton)


def test_settings_dialog_youtube_tab_has_fields(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._yt_client_secret_path is not None
    assert isinstance(dialog._yt_client_secret_path, QLineEdit)
    assert dialog._yt_auth_btn is not None


def test_settings_dialog_tiktok_tab_has_username_field(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._tiktok_username is not None
    assert isinstance(dialog._tiktok_username, QLineEdit)


def test_settings_dialog_audio_tab_has_monitor_dropdown(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._monitor_device_combo is not None
    assert isinstance(dialog._monitor_device_combo, QComboBox)


def test_settings_dialog_audio_monitor_dropdown_populated(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    combo = dialog._monitor_device_combo
    device_names = [combo.itemText(i) for i in range(combo.count())]
    assert "Built-in Output" in device_names
    assert "USB Headset" in device_names


def test_settings_dialog_save_writes_config(qapp, qtbot):
    dialog, mock_config = make_dialog(qtbot)
    dialog._twitch_channel.setText("mystream")
    dialog._save()
    mock_config.set.assert_any_call("twitch", "channel", "mystream")
    mock_config.save.assert_called()


def test_settings_dialog_save_writes_token_as_secret(qapp, qtbot):
    dialog, mock_config = make_dialog(qtbot)
    dialog._twitch_token.setText("oauth:abc123")
    dialog._save()
    mock_config.set_secret.assert_any_call("twitch", "oauth_token", "oauth:abc123")
