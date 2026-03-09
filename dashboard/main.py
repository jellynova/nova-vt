import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QFileSystemWatcher

from dashboard.theme import load_theme, generate_qss
from dashboard.window import NovaVTWindow
from dashboard.components.tracker import TrackerWorker
from dashboard.components.godot import GodotWorker
from dashboard.components.obs import OBSWorker
from dashboard.components.twitch import TwitchWorker
from dashboard.components.youtube import YouTubeWorker
from dashboard.components.overlays import OverlayWorker
from orchestrator.config import load_config

_THEME_PATH = Path.home() / ".config" / "nova-vt" / "theme.toml"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("nova-vt")

    # Load theme
    theme = load_theme(_THEME_PATH)
    app.setStyleSheet(generate_qss(theme))

    # Hot-reload theme on file change
    watcher = QFileSystemWatcher([str(_THEME_PATH)])
    def _reload_theme(path):
        t = load_theme(Path(path))
        app.setStyleSheet(generate_qss(t))
    watcher.fileChanged.connect(_reload_theme)

    # Load config
    config = load_config()

    # Create workers
    tracker  = TrackerWorker()
    godot    = GodotWorker()
    obs      = OBSWorker(config.obs_host, config.obs_port, config.obs_password)
    twitch   = TwitchWorker(config.twitch_token, config.twitch_channel, config.twitch_client_id)
    youtube  = YouTubeWorker()
    overlays = OverlayWorker()

    # Initial status checks
    twitch.check_config()
    youtube.check_config()

    # Start overlay server immediately
    overlays.start_overlays()

    # Build and show window
    window = NovaVTWindow(config, obs, twitch, youtube, tracker, godot, overlays, theme)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
