"""nova-vt application entrypoint.

Creates and wires the full pipeline:
  AudioMixer (QThread) → encoder_queue → EncoderThread (QThread) → ffmpeg → RTMP
  TwitchChatProvider + YouTubeChatProvider + TikTokChatProvider → ChatManager → MainWindow
  StatsPollerThread → StreamStats → MainWindow (5 s UI refresh)
  MainWindow (PyQt6 QMainWindow) — idle → previewing → live state machine
"""
from __future__ import annotations

import queue
import sys
import time
import tomllib
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# AppConfig — thin TOML-backed config compatible with SettingsDialog API
# ---------------------------------------------------------------------------

class AppConfig:
    """TOML-backed configuration with get/set/save and secret storage.

    Secrets are kept in a separate ``secrets.toml`` file alongside ``config.toml``
    so they are never accidentally committed.
    """

    def __init__(self, config_path: Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "config.toml"
        self._config_path = config_path
        self._secrets_path = config_path.parent / "secrets.toml"
        self._data: dict[str, Any] = {}
        self._secrets: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self._config_path.exists():
            with open(self._config_path, "rb") as f:
                self._data = tomllib.load(f)
        if self._secrets_path.exists():
            with open(self._secrets_path, "rb") as f:
                self._secrets = tomllib.load(f)

    def get(self, section: str, key: str) -> str | None:
        return self._data.get(section, {}).get(key)

    def get_secret(self, section: str, key: str) -> str | None:
        return self._secrets.get(section, {}).get(key)

    def set(self, section: str, key: str, value: str) -> None:
        self._data.setdefault(section, {})[key] = value

    def set_secret(self, section: str, key: str, value: str) -> None:
        self._secrets.setdefault(section, {})[key] = value

    def save(self) -> None:
        try:
            import tomli_w
        except ImportError:
            # tomli_w is optional; fall back to a basic serialiser
            _write_toml(self._config_path, self._data)
            _write_toml(self._secrets_path, self._secrets)
            return
        self._config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._config_path, "wb") as f:
            tomli_w.dump(self._data, f)
        with open(self._secrets_path, "wb") as f:
            tomli_w.dump(self._secrets, f)

    # Convenience accessors used by the rest of main()
    @property
    def scenes(self) -> list[str]:
        raw = self._data.get("scenes", {})
        return list(raw.values()) if isinstance(raw, dict) else []

    @property
    def rtmp_targets(self) -> list[str]:
        return self._data.get("stream", {}).get("rtmp_targets", [])


def _write_toml(path: Path, data: dict) -> None:
    """Minimal TOML writer — handles one level of sections + string/int values."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for section, values in data.items():
        if isinstance(values, dict):
            lines.append(f"[{section}]")
            for k, v in values.items():
                if isinstance(v, str):
                    lines.append(f'{k} = "{v}"')
                else:
                    lines.append(f"{k} = {v}")
        else:
            # top-level scalar
            if isinstance(values, str):
                lines.append(f'{section} = "{values}"')
            else:
                lines.append(f"{section} = {values}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main() -> None:
    from PyQt6.QtWidgets import QApplication

    app = QApplication(sys.argv)
    app.setApplicationName("nova-vt")

    # ── Config ───────────────────────────────────────────────────────────
    config = AppConfig()

    # ── Audio pipeline ───────────────────────────────────────────────────
    from nova_vt.audio.mixer import AudioMixer, MixerConfig, ChannelConfig

    encoder_queue: queue.Queue[bytes] = queue.Queue(maxsize=16)
    mixer_config = MixerConfig(
        mic_config=ChannelConfig(volume=75, muted=False, device=None),
        game_config=ChannelConfig(volume=60, muted=False, device=None),
        bgm_config=ChannelConfig(volume=30, muted=False, device=None),
        master_volume=90,
        monitor_device=config.get("audio", "monitor_device"),
    )
    mixer = AudioMixer(config=mixer_config, encoder_queue=encoder_queue)

    # ── Encoder ──────────────────────────────────────────────────────────
    from nova_vt.encoder.encoder import EncoderThread, EncoderConfig

    video_queue: queue.Queue = queue.Queue(maxsize=4)
    encoder_config = EncoderConfig(rtmp_targets=config.rtmp_targets)
    encoder = EncoderThread(
        config=encoder_config,
        video_queue=video_queue,
        audio_queue=encoder_queue,
    )

    # ── Chat ─────────────────────────────────────────────────────────────
    from nova_vt.chat.provider import ChatManager
    from nova_vt.chat.twitch import TwitchChatProvider
    from nova_vt.chat.youtube import YouTubeChatProvider
    from nova_vt.chat.tiktok import TikTokChatProvider

    chat_manager = ChatManager()

    twitch_token = config.get_secret("twitch", "oauth_token") or ""
    twitch_client_id = config.get_secret("twitch", "client_id") or ""
    twitch_client_secret = config.get_secret("twitch", "client_secret") or ""
    twitch_broadcaster_id = config.get_secret("twitch", "broadcaster_user_id") or ""

    if twitch_client_id and twitch_client_secret and twitch_token:
        twitch = TwitchChatProvider()
        chat_manager.add_provider("twitch", twitch)
        twitch.connect({
            "client_id": twitch_client_id,
            "client_secret": twitch_client_secret,
            "token": twitch_token,
            "broadcaster_user_id": twitch_broadcaster_id,
        })

    yt_token = config.get_secret("youtube", "access_token") or ""
    yt_chat_id = config.get("youtube", "live_chat_id") or ""
    if yt_token and yt_chat_id:
        youtube = YouTubeChatProvider()
        chat_manager.add_provider("youtube", youtube)
        youtube.connect({"access_token": yt_token, "live_chat_id": yt_chat_id})

    tiktok_username = config.get("tiktok", "username") or ""
    if tiktok_username:
        tiktok = TikTokChatProvider()
        chat_manager.add_provider("tiktok", tiktok)
        tiktok.connect({"username": tiktok_username})

    # ── Stats ────────────────────────────────────────────────────────────
    from nova_vt.chat.stats import StreamStats, StatsPollerThread

    stream_stats = StreamStats()
    # Fetchers are stubs — real implementations would hit platform APIs
    stats_poller = StatsPollerThread(stats=stream_stats, fetchers={}, interval=30.0)
    stats_poller.start()

    # ── Preview queue (video frames from future compositor) ──────────────
    preview_queue: queue.Queue = queue.Queue(maxsize=4)

    # ── Callbacks ────────────────────────────────────────────────────────
    def start_preview() -> None:
        mixer.start()

    def stop_preview() -> None:
        mixer.stop_mixing()

    def go_live() -> None:
        stream_stats.set_stream_start(time.time())
        if config.rtmp_targets:
            encoder.start()

    def end_stream() -> None:
        encoder.stop_encoding()
        stream_stats.reset()

    # ── Window ───────────────────────────────────────────────────────────
    from nova_vt.dashboard.window import MainWindow

    window = MainWindow(
        config=config,
        preview_queue=preview_queue,
        mixer=mixer,
        scenes=config.scenes or ["Gameplay", "Just Chatting", "BRB"],
        start_preview_fn=start_preview,
        stop_preview_fn=stop_preview,
        go_live_fn=go_live,
        end_stream_fn=end_stream,
        chat_manager=chat_manager,
        stream_stats=stream_stats,
    )
    window.show()

    exit_code = app.exec()

    # ── Cleanup ──────────────────────────────────────────────────────────
    stats_poller.stop()
    for provider_name in list(chat_manager._providers.keys()):
        try:
            chat_manager._providers[provider_name].disconnect()
        except Exception:
            pass

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
