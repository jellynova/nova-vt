"""ChatWidget — tabbed chat feed with unified + per-platform views and reply input."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtGui import QColor, QBrush
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import COLOR_ACCENT, COLOR_DANGER, COLOR_TEXT, accent_button_style

# Map platform string → tab name
_PLATFORM_TAB = {
    "twitch": "Twitch",
    "youtube": "YouTube",
    "tiktok": "TikTok",
}

_TAB_PLATFORM = {v: k for k, v in _PLATFORM_TAB.items()}

_EVENT_COLORS = {
    "sub": "#f59e0b",
    "raid": "#10b981",
    "gift": "#8b5cf6",
}


class ChatWidget(QWidget):
    """Tabbed chat feed widget.

    Signals:
        message_send_requested(str text, str platform): emitted when the user sends a reply.
            platform is "" when the All tab is selected (send to all).
    """

    message_send_requested = pyqtSignal(str, str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._lists: dict[str, QListWidget] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._tabs = QTabWidget()
        for tab_name in ("All", "Twitch", "YouTube", "TikTok"):
            lst = QListWidget()
            lst.setWordWrap(True)
            lst.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            self._tabs.addTab(lst, tab_name)
            self._lists[tab_name] = lst
        layout.addWidget(self._tabs)

        # Reply row
        reply_row = QHBoxLayout()
        reply_row.setSpacing(6)
        self._reply_input = QLineEdit()
        self._reply_input.setPlaceholderText("Send a message…")
        self._reply_input.returnPressed.connect(self._send)
        reply_row.addWidget(self._reply_input)

        self._send_button = QPushButton("Send")
        self._send_button.setStyleSheet(accent_button_style())
        self._send_button.clicked.connect(self._send)
        reply_row.addWidget(self._send_button)
        layout.addLayout(reply_row)

    def add_message(self, msg: Any) -> None:
        """Insert *msg* (ChatMessage or duck-type) into relevant list widgets."""
        display = f"[{msg.platform}] {msg.username}: {msg.text}"
        tab_name = _PLATFORM_TAB.get(msg.platform, "")

        for list_name, lst in self._lists.items():
            if list_name != "All" and list_name != tab_name:
                continue
            item = QListWidgetItem(display)
            if hasattr(msg, "event_type") and msg.event_type in _EVENT_COLORS:
                item.setForeground(QBrush(QColor(_EVENT_COLORS[msg.event_type])))
            lst.insertItem(0, item)

    def _send(self) -> None:
        text = self._reply_input.text().strip()
        if not text:
            return
        current_tab = self._tabs.tabText(self._tabs.currentIndex())
        platform = _TAB_PLATFORM.get(current_tab, "")
        self._reply_input.clear()
        self.message_send_requested.emit(text, platform)
