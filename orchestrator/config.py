from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class StreamConfig:
    # Tracker
    camera_index: int = 0
    tracker_fps: int = 30
    osc_host: str = "127.0.0.1"
    osc_port: int = 9000
    # OBS
    obs_host: str = "localhost"
    obs_port: int = 4455
    obs_password: str = ""
    # Stream
    twitch_channel: str = ""
    twitch_token: str = ""
    twitch_client_id: str = ""
    # Scenes
    scenes: dict = field(default_factory=dict)


def load_config(path: Path | None = None) -> StreamConfig:
    if path is None:
        path = Path(__file__).parent.parent / "config" / "config.toml"

    with open(path, "rb") as f:
        raw = tomllib.load(f)

    # Load secrets if they exist
    secrets_path = path.parent / "secrets.toml"
    secrets = {}
    if secrets_path.exists():
        with open(secrets_path, "rb") as f:
            secrets = tomllib.load(f)

    return StreamConfig(
        camera_index=raw["tracker"]["camera_index"],
        tracker_fps=raw["tracker"]["fps"],
        osc_host=raw["tracker"]["osc_host"],
        osc_port=raw["tracker"]["osc_port"],
        obs_host=raw["obs"]["host"],
        obs_port=raw["obs"]["port"],
        obs_password=secrets.get("obs", {}).get("password", ""),
        twitch_channel=raw["stream"]["twitch_channel"],
        twitch_token=secrets.get("twitch", {}).get("token", ""),
        twitch_client_id=secrets.get("twitch", {}).get("client_id", ""),
        scenes=raw["scenes"],
    )
