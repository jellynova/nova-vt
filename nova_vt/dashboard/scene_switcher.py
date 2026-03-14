"""SceneSwitcherWidget — horizontal strip of scene-select buttons."""
from __future__ import annotations

from typing import Optional

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QSizePolicy, QWidget

from nova_vt.dashboard.theme import COLOR_ACCENT, COLOR_SURFACE_RAISED, COLOR_TEXT, COLOR_BORDER


_BUTTON_STYLE = f"""
    QPushButton {{
        background-color: {COLOR_SURFACE_RAISED};
        color: {COLOR_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: 500;
    }}
    QPushButton:checked {{
        background-color: {COLOR_ACCENT};
        border-color: {COLOR_ACCENT};
        color: {COLOR_TEXT};
        font-weight: bold;
    }}
    QPushButton:hover:!checked {{
        border-color: {COLOR_ACCENT};
    }}
"""


class SceneSwitcherWidget(QWidget):
    """Horizontal strip with one checkable QPushButton per scene.

    Signals:
        scene_changed(str): emitted with the new scene name when the active scene changes.
    """

    scene_changed = pyqtSignal(str)

    def __init__(self, scenes: list[str], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scenes: list[str] = []
        self._buttons: list[QPushButton] = []

        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 4)
        self._layout.setSpacing(6)
        self._layout.addStretch()

        self.set_scenes(scenes)

    def active_scene(self) -> str:
        for btn in self._buttons:
            if btn.isChecked():
                return btn.text()
        return self._scenes[0] if self._scenes else ""

    def set_scenes(self, scenes: list[str]) -> None:
        """Replace current scene buttons with a new list."""
        for btn in self._buttons:
            self._layout.removeWidget(btn)
            btn.setParent(None)  # type: ignore[arg-type]
            btn.deleteLater()
        self._buttons.clear()
        self._scenes = list(scenes)

        self._layout.takeAt(self._layout.count() - 1)

        for i, name in enumerate(self._scenes):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setChecked(i == 0)
            btn.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
            btn.setStyleSheet(_BUTTON_STYLE)
            btn.clicked.connect(self._on_button_clicked)
            self._layout.addWidget(btn)
            self._buttons.append(btn)

        self._layout.addStretch()

    def _on_button_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        for btn in self._buttons:
            btn.setChecked(btn is sender)
        self.scene_changed.emit(sender.text())
