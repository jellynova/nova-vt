"""MainWindow — Studio+Chat layout, stream state machine, thread orchestration."""
from __future__ import annotations

import logging
import queue
from enum import Enum, auto
from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, QTimer, pyqtSignal

_log = logging.getLogger(__name__)
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.audio_mixer import AudioMixerWidget
from nova_vt.dashboard.chat_widget import ChatWidget
from nova_vt.dashboard.platform_stats import PlatformStatsWidget
from nova_vt.dashboard.preview import PreviewWidget
from nova_vt.dashboard.scene_switcher import SceneSwitcherWidget
from nova_vt.dashboard.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_SURFACE,
    COLOR_SURFACE_RAISED,
    accent_button_style,
    apply_theme,
)


class StreamState(Enum):
    IDLE = auto()
    PREVIEWING = auto()
    LIVE = auto()


class MainWindow(QMainWindow):
    """Top-level application window.

    Dependency-injected callbacks allow test isolation without real threads.
    Chat messages from background threads are bridged safely via a queued
    pyqtSignal so no Qt widget is ever touched from a non-main thread.
    """

    # Bridge signal: emits ChatMessage objects from background provider threads
    # onto the Qt main thread before forwarding to ChatWidget.
    _chat_message_received: pyqtSignal = pyqtSignal(object)

    def __init__(
        self,
        config: Any,
        preview_queue: queue.Queue,
        mixer: Any,
        scenes: list[str],
        start_preview_fn: Callable[[], None],
        stop_preview_fn: Callable[[], None],
        go_live_fn: Callable[[], None],
        end_stream_fn: Callable[[], None],
        chat_manager: Any = None,
        stream_stats: Any = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._start_preview_fn = start_preview_fn
        self._stop_preview_fn = stop_preview_fn
        self._go_live_fn = go_live_fn
        self._end_stream_fn = end_stream_fn
        self._stream_stats = stream_stats
        self._chat_manager = chat_manager
        self.state = StreamState.IDLE

        self.setWindowTitle("nova-vt")
        self.setMinimumSize(1400, 820)

        from PyQt6.QtWidgets import QApplication
        app = QApplication.instance()
        if app is not None:
            apply_theme(app)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        content = QHBoxLayout()
        content.setContentsMargins(8, 8, 8, 8)
        content.setSpacing(8)

        left = self._build_left_panel(preview_queue, mixer, scenes)
        content.addWidget(left, stretch=3)

        right = self._build_right_panel()
        content.addWidget(right, stretch=1)

        root.addLayout(content)

        # Wire chat: background threads emit into this signal; Qt queues delivery
        # to the main thread before calling ChatWidget.add_message.
        self._chat_message_received.connect(self._chat_widget.add_message)
        if chat_manager is not None:
            chat_manager.on_message(self._chat_message_received.emit)

        # Stats polling timer (UI-side, 5 s) — updates PlatformStatsWidget
        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(5000)
        self._stats_timer.timeout.connect(self._refresh_stats)

        self._apply_state()

    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background-color: {COLOR_SURFACE}; border-bottom: 1px solid #2d2d4e;")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("nova-vt")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_ACCENT}; background: transparent; border: none;")
        layout.addWidget(title)

        self._stream_timer_label = QLabel("00:00:00")
        self._stream_timer_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; background: transparent; border: none;")
        layout.addWidget(self._stream_timer_label)

        layout.addStretch()

        self._live_indicator = QLabel("● LIVE")
        self._live_indicator.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: bold; background: transparent; border: none;")
        self._live_indicator.setVisible(False)
        layout.addWidget(self._live_indicator)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.setFixedSize(32, 32)
        self._settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(self._settings_btn)

        self._timer_elapsed = 0
        self._stream_clock = QTimer(self)
        self._stream_clock.setInterval(1000)
        self._stream_clock.timeout.connect(self._tick_timer)

        return bar

    def _build_left_panel(self, preview_queue: queue.Queue, mixer: Any, scenes: list[str]) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._preview_widget = PreviewWidget(preview_queue=preview_queue)
        layout.addWidget(self._preview_widget)

        ctrl_row = QHBoxLayout()
        self._preview_btn = QPushButton("▶ Preview")
        self._preview_btn.setStyleSheet(accent_button_style())
        self._preview_btn.clicked.connect(self._on_preview)
        ctrl_row.addWidget(self._preview_btn)

        self._go_live_btn = QPushButton("🔴 Go Live")
        self._go_live_btn.setStyleSheet(accent_button_style())
        self._go_live_btn.setEnabled(False)
        self._go_live_btn.clicked.connect(self._on_go_live)
        ctrl_row.addWidget(self._go_live_btn)

        self._edit_scenes_btn = QPushButton("✏ Edit Scenes")
        self._edit_scenes_btn.clicked.connect(self._open_scene_editor)
        self._edit_scenes_btn.setVisible(False)
        ctrl_row.addWidget(self._edit_scenes_btn)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        self._scene_switcher = SceneSwitcherWidget(scenes=scenes)
        self._scene_switcher.scene_changed.connect(self._on_scene_changed)
        layout.addWidget(self._scene_switcher)

        self._audio_mixer = AudioMixerWidget(mixer=mixer)
        self._audio_mixer.end_stream_requested.connect(self._on_end_stream)
        layout.addWidget(self._audio_mixer)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._platform_stats = PlatformStatsWidget()
        self._platform_stats.setFixedHeight(120)
        layout.addWidget(self._platform_stats)

        self._chat_widget = ChatWidget()
        self._chat_widget.message_send_requested.connect(self._on_chat_send)
        layout.addWidget(self._chat_widget)

        return panel

    def _apply_state(self) -> None:
        idle = self.state == StreamState.IDLE
        previewing = self.state == StreamState.PREVIEWING
        live = self.state == StreamState.LIVE

        self._preview_btn.setVisible(idle or previewing)
        self._go_live_btn.setEnabled(previewing)
        self._edit_scenes_btn.setVisible(not live)  # available in IDLE + PREVIEWING
        self._live_indicator.setVisible(live)
        self._audio_mixer.set_live(live)

    def _on_preview(self) -> None:
        self.state = StreamState.PREVIEWING
        self._start_preview_fn()
        self._apply_state()

    def _on_go_live(self) -> None:
        self.state = StreamState.LIVE
        self._go_live_fn()
        self._timer_elapsed = 0
        self._stream_clock.start()
        self._stats_timer.start()
        self._apply_state()

    def _on_end_stream(self) -> None:
        self._stream_clock.stop()
        self._stats_timer.stop()
        self._end_stream_fn()
        self._stop_preview_fn()
        self.state = StreamState.IDLE
        self._apply_state()

    def _refresh_stats(self) -> None:
        if self._stream_stats is None:
            return
        self._platform_stats.update_from_stream_stats({
            "twitch": {"viewers": self._stream_stats.twitch_viewers, "likes": 0},
            "youtube": {"viewers": self._stream_stats.youtube_viewers, "likes": 0},
            "tiktok": {"viewers": self._stream_stats.tiktok_viewers, "likes": 0},
        })

    def _on_scene_changed(self, scene_name: str) -> None:
        # Signals the nova-vt compositor to switch the active scene layer set.
        # Compositor integration is wired via start_preview_fn / go_live_fn callbacks
        # once the video compositor component is implemented.
        _log.debug("Scene changed: %r", scene_name)

    def _on_chat_send(self, text: str, platform: str) -> None:
        if self._chat_manager is None or not text.strip():
            return
        # platform is "All" when the unified tab is active → broadcast to all providers
        target: str | None = platform if platform != "All" else None
        try:
            self._chat_manager.send(text, target)
        except Exception:
            _log.exception("Chat send failed (platform=%r)", platform)

    def _tick_timer(self) -> None:
        self._timer_elapsed += 1
        h = self._timer_elapsed // 3600
        m = (self._timer_elapsed % 3600) // 60
        s = self._timer_elapsed % 60
        self._stream_timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _open_settings(self) -> None:
        from nova_vt.dashboard.settings_dialog import SettingsDialog
        dlg = SettingsDialog(config=self._config, parent=self)
        dlg.exec()

    def _open_scene_editor(self) -> None:
        import json
        from pathlib import Path
        from nova_vt.dashboard.scene_editor import SceneEditorDialog

        scene_name = self._scene_switcher.active_scene()
        scenes_dir = Path.home() / ".config" / "nova-vt" / "scenes"
        scenes_dir.mkdir(parents=True, exist_ok=True)
        scene_path = scenes_dir / f"{scene_name}.json"

        if scene_path.exists():
            try:
                with open(scene_path, "r", encoding="utf-8") as f:
                    scene_data = json.load(f)
            except Exception:
                scene_data = {"name": scene_name, "layers": []}
        else:
            scene_data = {"name": scene_name, "layers": []}

        dlg = SceneEditorDialog(scene_data=scene_data, parent=self)
        if dlg.exec():
            dlg.save_scene(scene_path)

    def closeEvent(self, event) -> None:
        self._preview_widget.stop()
        self._stop_preview_fn()
        super().closeEvent(event)
