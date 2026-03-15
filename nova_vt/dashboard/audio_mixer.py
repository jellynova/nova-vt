"""AudioMixerWidget — per-channel volume sliders, mute toggles, VU meters, END STREAM button."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import (
    COLOR_DANGER,
    COLOR_TEXT,
    COLOR_SURFACE_RAISED,
    COLOR_BORDER,
    danger_button_style,
)

_CHANNELS = ["mic", "game", "bgm", "master"]
_DEFAULTS = {"mic": 75, "game": 60, "bgm": 30, "master": 90}

_MUTE_STYLE = f"""
    QPushButton {{
        background-color: {COLOR_SURFACE_RAISED};
        color: {COLOR_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 3px;
        padding: 3px 8px;
        font-size: 11px;
    }}
    QPushButton:checked {{
        background-color: {COLOR_DANGER};
        border-color: {COLOR_DANGER};
    }}
"""


class AudioMixerWidget(QWidget):
    """Horizontal row of channel strips with sliders, mute buttons, and VU meters.

    Signals:
        end_stream_requested: emitted when the END STREAM button is clicked.
    """

    end_stream_requested = pyqtSignal()

    def __init__(self, mixer: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mixer = mixer
        self._sliders: dict[str, QSlider] = {}
        self._mute_buttons: dict[str, QPushButton] = {}
        self._vu_meters: dict[str, QProgressBar] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)

        for ch in _CHANNELS:
            strip = self._build_channel_strip(ch)
            outer.addLayout(strip)

        outer.addStretch()

        self._end_stream_btn = QPushButton("⏹ END STREAM")
        self._end_stream_btn.setStyleSheet(danger_button_style())
        self._end_stream_btn.setEnabled(True)
        self._end_stream_btn.clicked.connect(self.end_stream_requested.emit)
        outer.addWidget(self._end_stream_btn)

        self._vu_timer = QTimer(self)
        self._vu_timer.setInterval(50)  # 20 fps for meters
        self._vu_timer.timeout.connect(self._update_vu_meters)
        self._vu_timer.start()

    def _build_channel_strip(self, channel: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        label = QLabel(channel.upper())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(0, 100)
        slider.setValue(_DEFAULTS[channel])
        slider.setFixedHeight(80)
        slider.valueChanged.connect(lambda val, ch=channel: self._on_volume_changed(ch, val))
        layout.addWidget(slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._sliders[channel] = slider

        mute_btn = QPushButton("M")
        mute_btn.setCheckable(True)
        mute_btn.setFixedWidth(32)
        mute_btn.setStyleSheet(_MUTE_STYLE)
        mute_btn.toggled.connect(lambda checked, ch=channel: self._mixer.set_mute(ch, checked))
        layout.addWidget(mute_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._mute_buttons[channel] = mute_btn

        vu = QProgressBar()
        vu.setRange(0, 100)
        vu.setValue(0)
        vu.setTextVisible(False)
        vu.setFixedWidth(20)
        vu.setFixedHeight(60)
        vu.setOrientation(Qt.Orientation.Vertical)
        layout.addWidget(vu, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._vu_meters[channel] = vu

        return layout

    def get_volume(self, channel: str) -> int:
        return self._sliders[channel].value()

    def set_live(self, live: bool) -> None:
        self._end_stream_btn.setEnabled(live)

    def _on_volume_changed(self, channel: str, value: int) -> None:
        self._mixer.set_volume(channel, value)

    def _update_vu_meters(self) -> None:
        if not hasattr(self._mixer, "get_peaks"):
            return
        peaks: dict[str, float] = self._mixer.get_peaks()
        for ch in _CHANNELS:
            self._vu_meters[ch].setValue(int(peaks.get(ch, 0.0) * 100))
