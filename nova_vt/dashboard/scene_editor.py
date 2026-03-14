"""SceneEditorDialog — drag-resize layer editor for compositor scenes."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QBrush, QColor, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QVBoxLayout,
    QWidget,
)

# Scale factor: scene canvas fits 1920×1080 source into an 800×450 display
_SCALE = 800 / 1920

_LAYER_COLORS: dict[str, str] = {
    "capture": "#1e3a5f",
    "avatar": "#3b1f6e",
    "image": "#1f4a2e",
    "text": "#4a3010",
}

_LAYER_BORDER: dict[str, str] = {
    "capture": "#3b82f6",
    "avatar": "#8b5cf6",
    "image": "#22c55e",
    "text": "#f59e0b",
}


class _LayerItem(QGraphicsRectItem):
    """A movable, resizable rect item representing one compositor layer."""

    def __init__(self, layer: dict[str, Any]) -> None:
        x, y, w, h = layer["rect"]
        # IMPORTANT: rect is (0,0,w,h) — origin encoded in setPos, not rect
        super().__init__(QRectF(0.0, 0.0, w * _SCALE, h * _SCALE))
        self.setPos(x * _SCALE, y * _SCALE)
        self._layer = layer
        layer_type = layer.get("type", "image")
        fill = QColor(_LAYER_COLORS.get(layer_type, "#2d2d4e"))
        fill.setAlpha(160)
        self.setBrush(QBrush(fill))
        border_color = _LAYER_BORDER.get(layer_type, "#7c3aed")
        self.setPen(QPen(QColor(border_color), 1.5))
        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setToolTip(f"{layer_type}: {layer.get('device', layer.get('path', ''))}")

    def layer_type(self) -> str:
        return self._layer.get("type", "image")

    def original_layer(self) -> dict[str, Any]:
        return self._layer

    def to_layer_dict(self) -> dict[str, Any]:
        """Return updated layer dict with rect reflecting current canvas position."""
        pos = self.pos()
        r = self.rect()
        x = int(pos.x() / _SCALE)
        y = int(pos.y() / _SCALE)
        w = int(r.width() / _SCALE)
        h = int(r.height() / _SCALE)
        updated = dict(self._layer)
        updated["rect"] = [x, y, w, h]
        return updated


class SceneEditorDialog(QDialog):
    """Modal scene editor."""

    def __init__(self, scene_data: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene_data = scene_data
        self.setWindowTitle(f"Edit Scene — {scene_data.get('name', '')}")
        self.setMinimumSize(820, 520)

        layout = QVBoxLayout(self)

        self._gscene = QGraphicsScene()
        self._gscene.setSceneRect(0, 0, 800, 450)
        self._gscene.setBackgroundBrush(QBrush(QColor("#0a0a14")))

        self._items: list[_LayerItem] = []
        for layer in scene_data.get("layers", []):
            item = _LayerItem(layer)
            self._gscene.addItem(item)
            self._items.append(item)

        self._view = QGraphicsView(self._gscene)
        self._view.setFixedSize(804, 454)
        layout.addWidget(self._view)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_updated_scene(self) -> dict[str, Any]:
        """Return the scene dict with all layer rects updated from canvas positions."""
        updated_layers = [item.to_layer_dict() for item in self._items]
        return {**self._scene_data, "layers": updated_layers}

    def save_scene(self, path: Path) -> None:
        """Write the updated scene dict as JSON to *path*."""
        data = self.get_updated_scene()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
