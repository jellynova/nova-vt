"""SettingsDialog — Twitch/YouTube/TikTok credentials, VRM model, and audio preferences."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

try:
    import sounddevice
except ImportError:
    sounddevice = None  # type: ignore

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import accent_button_style


class SettingsDialog(QDialog):
    """Modal dialog for configuring stream credentials, avatar model, and audio device."""

    def __init__(self, config: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("nova-vt Settings")
        self.setMinimumWidth(500)

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_model_tab(), "Avatar Model")
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

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_model_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        path_row = QHBoxLayout()
        self._vrm_path = QLineEdit()
        self._vrm_path.setPlaceholderText("/path/to/avatar.vrm")
        path_row.addWidget(self._vrm_path)

        browse_btn = QPushButton("Browse…")
        browse_btn.setStyleSheet(accent_button_style())
        browse_btn.clicked.connect(self._browse_vrm)
        path_row.addWidget(browse_btn)

        form.addRow("VRM File:", path_row)

        note = QLabel(
            "Select a VRM 0.x or 1.0 avatar file. "
            "The model will be rendered in the preview and stream output."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _browse_vrm(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select VRM Avatar", str(Path.home()), "VRM Files (*.vrm)"
        )
        if path:
            self._vrm_path.setText(path)

    def _build_twitch_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._twitch_channel = QLineEdit()
        self._twitch_channel.setPlaceholderText("your_channel_name")
        form.addRow("Channel:", self._twitch_channel)

        self._twitch_client_id = QLineEdit()
        form.addRow("Client ID:", self._twitch_client_id)

        self._twitch_client_secret = QLineEdit()
        self._twitch_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client Secret:", self._twitch_client_secret)

        self._twitch_token = QLineEdit()
        self._twitch_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._twitch_token.setPlaceholderText("oauth:...")
        form.addRow("OAuth Token:", self._twitch_token)

        self._twitch_broadcaster_id = QLineEdit()
        self._twitch_broadcaster_id.setPlaceholderText("numeric user ID")
        form.addRow("Broadcaster User ID:", self._twitch_broadcaster_id)

        note = QLabel(
            "Get your OAuth token at twitchapps.com/tmi. "
            "Your Broadcaster User ID is shown in the Twitch Developer Console."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _build_youtube_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)

        self._yt_client_id = QLineEdit()
        form.addRow("Client ID:", self._yt_client_id)

        self._yt_client_secret = QLineEdit()
        self._yt_client_secret.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Client Secret:", self._yt_client_secret)

        self._yt_access_token = QLineEdit()
        self._yt_access_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Access Token:", self._yt_access_token)

        self._yt_refresh_token = QLineEdit()
        self._yt_refresh_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Refresh Token:", self._yt_refresh_token)

        self._yt_live_chat_id = QLineEdit()
        self._yt_live_chat_id.setPlaceholderText("liveChatId from YouTube Studio")
        form.addRow("Live Chat ID:", self._yt_live_chat_id)

        note = QLabel(
            "Create OAuth 2.0 credentials in Google Cloud Console with the YouTube Data API v3 scope. "
            "Exchange an authorization code for access/refresh tokens using the OAuth Playground "
            "(oauth2.googleapis.com/tokeninfo). "
            "The Live Chat ID is found in YouTube Studio → Go Live → Stream Details."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _build_tiktok_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._tiktok_username = QLineEdit()
        self._tiktok_username.setPlaceholderText("@username")
        form.addRow("Username:", self._tiktok_username)
        note = QLabel(
            "TikTok chat is read-only via the open-source TikTokLive library. "
            "RTMP push support is pending a confirmed public endpoint."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._monitor_device_combo = QComboBox()
        self._populate_audio_devices()
        form.addRow("Monitor Output Device:", self._monitor_device_combo)
        note = QLabel(
            "Select the audio device you'll use to monitor your stream mix through headphones."
        )
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _populate_audio_devices(self) -> None:
        self._monitor_device_combo.clear()
        self._monitor_device_combo.addItem("(none)")
        if sounddevice is None:
            return
        try:
            devices = sounddevice.query_devices()
            for dev in devices:
                if dev.get("max_output_channels", 0) > 0:
                    self._monitor_device_combo.addItem(dev["name"])
        except Exception:
            pass

    # ── Load / Save ───────────────────────────────────────────────────────────

    def _load_config(self) -> None:
        # Avatar model
        self._vrm_path.setText(self._config.get("renderer", "vrm_path") or "")

        # Twitch
        self._twitch_channel.setText(self._config.get("twitch", "channel") or "")
        self._twitch_client_id.setText(self._config.get_secret("twitch", "client_id") or "")
        self._twitch_client_secret.setText(self._config.get_secret("twitch", "client_secret") or "")
        self._twitch_token.setText(self._config.get_secret("twitch", "oauth_token") or "")
        self._twitch_broadcaster_id.setText(self._config.get_secret("twitch", "broadcaster_user_id") or "")

        # YouTube
        self._yt_client_id.setText(self._config.get_secret("youtube", "client_id") or "")
        self._yt_client_secret.setText(self._config.get_secret("youtube", "client_secret") or "")
        self._yt_access_token.setText(self._config.get_secret("youtube", "access_token") or "")
        self._yt_refresh_token.setText(self._config.get_secret("youtube", "refresh_token") or "")
        self._yt_live_chat_id.setText(self._config.get("youtube", "live_chat_id") or "")

        # TikTok
        self._tiktok_username.setText(self._config.get("tiktok", "username") or "")

        # Audio
        saved_device = self._config.get("audio", "monitor_device") or ""
        if saved_device:
            idx = self._monitor_device_combo.findText(saved_device)
            if idx >= 0:
                self._monitor_device_combo.setCurrentIndex(idx)

    def _save(self) -> None:
        # Avatar model
        self._config.set("renderer", "vrm_path", self._vrm_path.text())

        # Twitch (credentials in secrets)
        self._config.set("twitch", "channel", self._twitch_channel.text())
        self._config.set_secret("twitch", "client_id", self._twitch_client_id.text())
        self._config.set_secret("twitch", "client_secret", self._twitch_client_secret.text())
        self._config.set_secret("twitch", "oauth_token", self._twitch_token.text())
        self._config.set_secret("twitch", "broadcaster_user_id", self._twitch_broadcaster_id.text())

        # YouTube (credentials in secrets; live_chat_id is non-sensitive)
        self._config.set_secret("youtube", "client_id", self._yt_client_id.text())
        self._config.set_secret("youtube", "client_secret", self._yt_client_secret.text())
        self._config.set_secret("youtube", "access_token", self._yt_access_token.text())
        self._config.set_secret("youtube", "refresh_token", self._yt_refresh_token.text())
        self._config.set("youtube", "live_chat_id", self._yt_live_chat_id.text())

        # TikTok
        self._config.set("tiktok", "username", self._tiktok_username.text())

        # Audio
        device = self._monitor_device_combo.currentText()
        self._config.set("audio", "monitor_device", "" if device == "(none)" else device)

        self._config.save()
