"""SettingsDialog — Twitch/YouTube/TikTok credentials and audio preferences."""
from __future__ import annotations

from typing import Any, Optional

try:
    import sounddevice
except ImportError:
    sounddevice = None  # type: ignore

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import accent_button_style


class SettingsDialog(QDialog):
    """Modal dialog for configuring stream credentials and audio device."""

    def __init__(self, config: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("nova-vt Settings")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_twitch_tab(), "Twitch")
        self._tabs.addTab(self._build_youtube_tab(), "YouTube")
        self._tabs.addTab(self._build_tiktok_tab(), "TikTok")
        self._tabs.addTab(self._build_audio_tab(), "Audio")
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_config()

    def _build_twitch_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._twitch_channel = QLineEdit()
        self._twitch_client_id = QLineEdit()
        self._twitch_token = QLineEdit()
        self._twitch_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Channel:", self._twitch_channel)
        form.addRow("Client ID:", self._twitch_client_id)
        form.addRow("OAuth Token:", self._twitch_token)
        self._twitch_connect_btn = QPushButton("Connect")
        self._twitch_connect_btn.setStyleSheet(accent_button_style())
        form.addRow("", self._twitch_connect_btn)
        return w

    def _build_youtube_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._yt_client_secret_path = QLineEdit()
        self._yt_client_secret_path.setPlaceholderText("/path/to/client_secret.json")
        form.addRow("Client Secret JSON:", self._yt_client_secret_path)
        self._yt_auth_btn = QPushButton("Authorize via Browser")
        self._yt_auth_btn.setStyleSheet(accent_button_style())
        form.addRow("", self._yt_auth_btn)
        return w

    def _build_tiktok_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._tiktok_username = QLineEdit()
        self._tiktok_username.setPlaceholderText("@username")
        form.addRow("Username:", self._tiktok_username)
        note = QLabel("TikTok chat is read-only. RTMP push endpoint TBD.")
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._monitor_device_combo = QComboBox()
        self._populate_audio_devices()
        form.addRow("Monitor Output Device:", self._monitor_device_combo)
        return w

    def _populate_audio_devices(self) -> None:
        self._monitor_device_combo.clear()
        if sounddevice is None:
            return
        try:
            devices = sounddevice.query_devices()
            for dev in devices:
                if dev.get("max_output_channels", 0) > 0:
                    self._monitor_device_combo.addItem(dev["name"])
        except Exception:
            pass

    def _load_config(self) -> None:
        self._twitch_channel.setText(self._config.get("twitch", "channel") or "")
        self._twitch_client_id.setText(self._config.get("twitch", "client_id") or "")
        self._twitch_token.setText(self._config.get_secret("twitch", "oauth_token") or "")
        self._yt_client_secret_path.setText(self._config.get("youtube", "client_secret_path") or "")
        self._tiktok_username.setText(self._config.get("tiktok", "username") or "")
        saved_device = self._config.get("audio", "monitor_device") or ""
        if saved_device:
            idx = self._monitor_device_combo.findText(saved_device)
            if idx >= 0:
                self._monitor_device_combo.setCurrentIndex(idx)

    def _save(self) -> None:
        self._config.set("twitch", "channel", self._twitch_channel.text())
        self._config.set("twitch", "client_id", self._twitch_client_id.text())
        self._config.set_secret("twitch", "oauth_token", self._twitch_token.text())
        self._config.set("youtube", "client_secret_path", self._yt_client_secret_path.text())
        self._config.set("tiktok", "username", self._tiktok_username.text())
        self._config.set("audio", "monitor_device", self._monitor_device_combo.currentText())
        self._config.save()
