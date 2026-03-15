"""nova-vt application entrypoint.

Full pipeline:

  WebcamCaptureThread → compositor.webcam_queue ─┐
                                                   ├─→ Compositor → preview_queue → PreviewWidget
  MediaPipeTracker → VRMRenderer → compositor.avatar_queue ─┘          └─→ encoder_queue → EncoderThread → ffmpeg → RTMP

  TwitchChatProvider + YouTubeChatProvider + TikTokChatProvider → ChatManager → MainWindow
  StatsPollerThread → StreamStats → MainWindow (5 s UI refresh)
  MainWindow (PyQt6 QMainWindow) — idle → previewing → live state machine

When no VRM path is configured the avatar pipeline is skipped and only the
webcam feed (via the compositor) is shown.  When no scene JSON exists for the
active scene the compositor falls back to a full-canvas webcam display.
"""
from __future__ import annotations

import json
import logging
import queue

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
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
            if isinstance(values, str):
                lines.append(f'{section} = "{values}"')
            else:
                lines.append(f"{section} = {values}")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Viewer count fetchers (synchronous, for StatsPollerThread)
# ---------------------------------------------------------------------------

def _make_twitch_viewer_fetcher(
    client_id: str, token: str, broadcaster_user_id: str
):
    """Returns a callable() → int that fetches live viewer count from Twitch Helix."""
    import logging as _logging
    _log = _logging.getLogger(__name__)

    def fetch() -> int:
        import requests
        resp = requests.get(
            "https://api.twitch.tv/helix/streams",
            headers={"Client-Id": client_id, "Authorization": f"Bearer {token}"},
            params={"user_id": broadcaster_user_id},
            timeout=5,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return int(data[0]["viewer_count"]) if data else 0

    return fetch


def _make_youtube_viewer_fetcher(
    access_token: str,
    refresh_token: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
):
    """Returns a callable() → int that fetches concurrent viewers from YouTube Live."""
    import logging as _logging
    _log = _logging.getLogger(__name__)

    def fetch() -> int:
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        svc = build("youtube", "v3", credentials=creds, cache_discovery=False)
        resp = svc.liveBroadcasts().list(
            part="id",
            broadcastStatus="active",
            mine=True,
            maxResults=1,
        ).execute()
        items = resp.get("items", [])
        if not items:
            return 0
        video_id = items[0]["id"]
        vresp = svc.videos().list(
            part="liveStreamingDetails",
            id=video_id,
        ).execute()
        vitems = vresp.get("items", [])
        if not vitems:
            return 0
        details = vitems[0].get("liveStreamingDetails", {})
        return int(details.get("concurrentViewers", 0))

    return fetch


# ---------------------------------------------------------------------------
# Scene loader helper
# ---------------------------------------------------------------------------

def _load_scene_data(scene_name: str, camera_device: "str | int" = 0) -> dict[str, Any]:
    """Load scene JSON from ~/.config/nova-vt/scenes/<name>.json.

    Returns a default capture-layer scene if the file doesn't exist or is empty.
    """
    scene_path = Path.home() / ".config" / "nova-vt" / "scenes" / f"{scene_name}.json"
    if scene_path.exists():
        try:
            with open(scene_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("layers"):
                return data
        except Exception:
            pass
    # Default: full-canvas webcam capture so the preview is never blank
    return {
        "name": scene_name,
        "layers": [{"type": "capture", "device": str(camera_device), "rect": [0, 0, 1920, 1080], "z": 0}],
    }


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
    yt_refresh = config.get_secret("youtube", "refresh_token") or ""
    yt_client_id = config.get_secret("youtube", "client_id") or ""
    yt_client_secret = config.get_secret("youtube", "client_secret") or ""
    yt_chat_id = config.get("youtube", "live_chat_id") or ""
    if yt_token and yt_chat_id:
        youtube = YouTubeChatProvider()
        chat_manager.add_provider("youtube", youtube)
        youtube.connect({
            "access_token": yt_token,
            "refresh_token": yt_refresh,
            "client_id": yt_client_id,
            "client_secret": yt_client_secret,
            "live_chat_id": yt_chat_id,
        })

    tiktok_username = config.get("tiktok", "username") or ""
    if tiktok_username:
        tiktok = TikTokChatProvider()
        chat_manager.add_provider("tiktok", tiktok)
        tiktok.connect({"username": tiktok_username})

    # ── Stats ────────────────────────────────────────────────────────────
    from nova_vt.chat.stats import StreamStats, StatsPollerThread

    stream_stats = StreamStats()

    stat_fetchers: dict[str, Any] = {}
    if twitch_client_id and twitch_token and twitch_broadcaster_id:
        stat_fetchers["twitch"] = _make_twitch_viewer_fetcher(
            client_id=twitch_client_id,
            token=twitch_token,
            broadcaster_user_id=twitch_broadcaster_id,
        )
    if yt_token and yt_chat_id:
        stat_fetchers["youtube"] = _make_youtube_viewer_fetcher(
            access_token=yt_token,
            refresh_token=yt_refresh,
            client_id=yt_client_id,
            client_secret=yt_client_secret,
        )

    stats_poller = StatsPollerThread(stats=stream_stats, fetchers=stat_fetchers, interval=30.0)
    stats_poller.start()

    # ── Compositor ───────────────────────────────────────────────────────
    from nova_vt.compositor.compositor import Compositor

    preview_queue: queue.Queue = queue.Queue(maxsize=4)
    compositor = Compositor(preview_queue=preview_queue, fps=30)

    # ── VRM Renderer (optional — initialised lazily in start_preview) ───
    _vrm_renderer: list[Any] = []
    _config_vrm_path = config.get("renderer", "vrm_path") or ""

    # ── Webcam capture ───────────────────────────────────────────────────
    from nova_vt.capture.webcam import WebcamCaptureThread

    # Camera device: prefer the explicit device path from [camera] section,
    # fall back to legacy [tracker] camera_index integer for compatibility.
    camera_device: str | int = (
        config.get("camera", "device")
        or int(config.get("tracker", "camera_index") or 0)
    )
    _webcam: list[WebcamCaptureThread] = []

    # ── MediaPipe tracker (optional — gracefully skips missing model files) ──
    from nova_vt.tracking.mediapipe_tracker import MediaPipeTracker

    _tracker: list[MediaPipeTracker] = []

    # ── Initial scene ────────────────────────────────────────────────────
    scene_names = config.scenes or ["Gameplay", "Just Chatting", "BRB"]
    _active_scene: list[str] = [scene_names[0]]

    compositor.set_scene(_load_scene_data(_active_scene[0], camera_device))

    # ── Callbacks ────────────────────────────────────────────────────────

    def _init_vrm_renderer(scene_data: dict) -> None:
        """Try to initialise VRM renderer from config path or scene avatar layers."""
        if _vrm_renderer:
            return  # already running

        # Prefer the config-level vrm_path; fall back to first avatar layer with one
        candidate = _config_vrm_path or next(
            (
                l.get("vrm_path", "")
                for l in scene_data.get("layers", [])
                if l.get("type") == "avatar" and l.get("vrm_path")
            ),
            "",
        )
        if not candidate or not Path(candidate).exists():
            logging.getLogger(__name__).info("No VRM path found — avatar renderer disabled")
            return
        try:
            from nova_vt.renderer.vrm_loader import VRMLoader
            from nova_vt.renderer.vrm_renderer import VRMRenderer
            loader = VRMLoader(candidate)
            renderer = VRMRenderer(
                loader=loader,
                preview_queue=compositor.avatar_queue,
                fps=30,
            )
            _vrm_renderer.append(renderer)
            logging.getLogger(__name__).info("VRM renderer ready: %s", candidate)
        except Exception as exc:
            logging.getLogger(__name__).warning("VRM renderer init failed (%s)", exc)

    def start_preview() -> None:
        # Load scene so we can extract the VRM path from avatar layers if needed
        scene = _load_scene_data(_active_scene[0], camera_device)
        compositor.set_scene(scene)

        # Webcam → compositor.webcam_queue (not preview_queue directly)
        t = WebcamCaptureThread(
            frame_queue=compositor.webcam_queue,
            device=camera_device,
        )
        _webcam.clear()
        _webcam.append(t)
        t.start()

        # VRM renderer — initialise now so scene avatar layers can provide the path
        _init_vrm_renderer(scene)

        # MediaPipe tracker → VRM renderer (if available)
        if _vrm_renderer:
            cam_idx = int(camera_device) if isinstance(camera_device, int) else 0
            tracker = MediaPipeTracker(camera_index=cam_idx)
            _tracker.clear()
            _tracker.append(tracker)
            # frame_updated is a cross-thread signal; Qt delivers it safely
            tracker.frame_updated.connect(_vrm_renderer[0].update_tracking)
            tracker.start()
            _vrm_renderer[0].start()

        compositor.start()
        mixer.start()

    def stop_preview() -> None:
        if _webcam:
            _webcam[0].stop()
            _webcam.clear()
        if _tracker:
            _tracker[0].stop()
            _tracker[0].wait()
            _tracker.clear()
        if _vrm_renderer:
            _vrm_renderer[0].stop()
            _vrm_renderer[0].wait()
            _vrm_renderer.clear()
        compositor.stop()
        compositor.wait()
        mixer.stop_mixing()

    def go_live() -> None:
        stream_stats.set_stream_start(time.time())
        if config.rtmp_targets:
            compositor.set_encoder_queue(video_queue)
            encoder.start()

    def end_stream() -> None:
        compositor.set_encoder_queue(None)
        encoder.stop_encoding()
        stream_stats.reset()

    def on_scene_changed(scene_name: str) -> None:
        _active_scene[0] = scene_name
        compositor.set_scene(_load_scene_data(scene_name, camera_device))

    # ── Window ───────────────────────────────────────────────────────────
    from nova_vt.dashboard.window import MainWindow

    window = MainWindow(
        config=config,
        preview_queue=preview_queue,
        mixer=mixer,
        scenes=scene_names,
        start_preview_fn=start_preview,
        stop_preview_fn=stop_preview,
        go_live_fn=go_live,
        end_stream_fn=end_stream,
        chat_manager=chat_manager,
        stream_stats=stream_stats,
        scene_changed_fn=on_scene_changed,
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
