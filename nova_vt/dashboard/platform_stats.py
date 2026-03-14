"""PlatformStatsWidget — per-platform viewer count and likes display."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

_PLATFORM_META = {
    "twitch": {"label": "Twitch", "color": "#9146FF"},
    "youtube": {"label": "YouTube", "color": "#FF0000"},
    "tiktok": {"label": "TikTok", "color": "#69C9D0"},
}


class PlatformStatsWidget(QWidget):
    """Shows viewer counts + likes for Twitch, YouTube, and TikTok."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, QWidget] = {}
        self._viewer_labels: dict[str, QLabel] = {}
        self._likes_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for platform, meta in _PLATFORM_META.items():
            row = QWidget()
            row.setStyleSheet(f"QWidget {{ border-left: 3px solid {meta['color']}; padding-left: 6px; }}")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)

            name_label = QLabel(meta["label"])
            name_label.setFixedWidth(70)
            name_label.setStyleSheet(f"color: {meta['color']}; font-weight: bold; border: none;")
            row_layout.addWidget(name_label)

            viewer_label = QLabel("👁 0")
            viewer_label.setStyleSheet("border: none; color: #e2e8f0;")
            row_layout.addWidget(viewer_label)

            likes_label = QLabel("♥ 0")
            likes_label.setStyleSheet("border: none; color: #94a3b8;")
            row_layout.addWidget(likes_label)

            row_layout.addStretch()
            layout.addWidget(row)

            self._rows[platform] = row
            self._viewer_labels[platform] = viewer_label
            self._likes_labels[platform] = likes_label

        layout.addStretch()

    def update_stats(self, platform: str, viewers: int, likes: int) -> None:
        if platform not in self._viewer_labels:
            return
        self._viewer_labels[platform].setText(f"👁 {viewers}")
        self._likes_labels[platform].setText(f"♥ {likes}")

    def update_from_stream_stats(self, stats: dict[str, dict[str, int]]) -> None:
        for platform, data in stats.items():
            self.update_stats(platform, data.get("viewers", 0), data.get("likes", 0))
