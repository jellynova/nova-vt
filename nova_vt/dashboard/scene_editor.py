"""SceneEditorDialog — drag-resize layer editor for compositor scenes."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QBrush, QColor, QFont, QPen
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsSimpleTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import (
    COLOR_SURFACE_RAISED,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    accent_button_style,
)

# Scale factor: scene canvas fits 1920×1080 source into an 800×450 display
_SCALE = 800 / 1920

_ASSETS_DIR = Path.home() / ".config" / "nova-vt" / "assets"

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

_LAYER_LABELS: dict[str, str] = {
    "capture": "📷 Capture",
    "avatar": "🎭 Avatar",
    "image": "🖼 Image",
    "text": "T Text",
}


def _copy_to_assets(src: str) -> str:
    """Copy *src* into the assets directory and return the destination path string.

    If a file with the same name already exists and has the same size, skips the
    copy and returns the existing path. On name collision with a different size,
    appends a numeric suffix to avoid clobbering.
    """
    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    src_path = Path(src)
    dest = _ASSETS_DIR / src_path.name

    if dest.exists():
        if dest.stat().st_size == src_path.stat().st_size:
            return str(dest)
        # Name collision — add suffix
        stem = src_path.stem
        suffix = src_path.suffix
        i = 1
        while dest.exists():
            dest = _ASSETS_DIR / f"{stem}_{i}{suffix}"
            i += 1

    shutil.copy2(src, dest)
    return str(dest)


class _LayerItem(QGraphicsRectItem):
    """A movable rect item representing one compositor layer, with a visible label."""

    def __init__(self, layer: dict[str, Any]) -> None:
        x, y, w, h = layer["rect"]
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

        # Label: type icon + short source name
        source = layer.get("content") or layer.get("path") or layer.get("device") or ""
        source_short = Path(source).name if source else ""
        base_label = _LAYER_LABELS.get(layer_type, layer_type)
        label_text = f"{base_label}\n{source_short}" if source_short else base_label

        self._label = QGraphicsSimpleTextItem(label_text, self)
        font = QFont()
        font.setPointSize(7)
        self._label.setFont(font)
        self._label.setBrush(QBrush(QColor("#e2e8f0")))
        self._label.setPos(4, 4)

        self.setToolTip(f"{layer_type}: {source}")

    def layer_type(self) -> str:
        return self._layer.get("type", "image")

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
    """Modal scene editor with add/delete layer controls and file copy-to-assets."""

    def __init__(self, scene_data: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene_data = scene_data
        self.setWindowTitle(f"Edit Scene — {scene_data.get('name', '')}")
        self.setMinimumSize(820, 640)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Add Layer toolbar ─────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {COLOR_SURFACE_RAISED}; border-radius: 4px;")
        toolbar_row = QHBoxLayout(toolbar)
        toolbar_row.setContentsMargins(8, 6, 8, 6)
        toolbar_row.setSpacing(8)

        add_label = QLabel("Add layer:")
        add_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; background: transparent;")
        toolbar_row.addWidget(add_label)

        for layer_type, label in [
            ("image",   "🖼 Background / Image"),
            ("avatar",  "🎭 VTuber Avatar"),
            ("capture", "📷 Capture / Webcam"),
            ("text",    "T  Text Overlay"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(accent_button_style())
            btn.clicked.connect(lambda checked, lt=layer_type: self._add_layer(lt))
            toolbar_row.addWidget(btn)

        toolbar_row.addStretch()

        delete_btn = QPushButton("🗑 Delete Selected")
        delete_btn.clicked.connect(self._delete_selected)
        toolbar_row.addWidget(delete_btn)

        layout.addWidget(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────
        self._gscene = QGraphicsScene()
        self._gscene.setSceneRect(0, 0, 800, 450)
        self._gscene.setBackgroundBrush(QBrush(QColor("#0a0a14")))

        self._items: list[_LayerItem] = []
        for layer in scene_data.get("layers", []):
            self._add_item(layer)

        self._view = QGraphicsView(self._gscene)
        self._view.setFixedSize(804, 454)
        layout.addWidget(self._view)

        # ── Legend ────────────────────────────────────────────────────────
        legend_row = QHBoxLayout()
        legend_row.addStretch()
        for layer_type, color in _LAYER_BORDER.items():
            dot = QLabel(f"■ {_LAYER_LABELS[layer_type]}")
            dot.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")
            legend_row.addWidget(dot)
            legend_row.addSpacing(12)
        layout.addLayout(legend_row)

        # ── Buttons ───────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _add_item(self, layer: dict[str, Any]) -> None:
        item = _LayerItem(layer)
        self._gscene.addItem(item)
        self._items.append(item)

    def _add_layer(self, layer_type: str) -> None:
        """Prompt for source info, copy file if needed, add layer to canvas."""
        if layer_type == "image":
            self._add_image_layer()
        elif layer_type == "avatar":
            self._add_avatar_layer()
        elif layer_type == "capture":
            self._add_capture_layer()
        elif layer_type == "text":
            self._add_text_layer()

    def _add_image_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Image",
            str(Path.home()),
            "Images (*.png *.jpg *.jpeg *.gif *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        try:
            dest = _copy_to_assets(path)
        except Exception as e:
            QMessageBox.warning(self, "Copy failed", f"Could not copy file:\n{e}")
            return
        layer = {"type": "image", "path": dest, "rect": [0, 0, 1920, 1080], "opacity": 1.0}
        self._add_item(layer)

    def _add_avatar_layer(self) -> None:
        # Avatar layer uses the renderer output — no file needed
        layer = {"type": "avatar", "rect": [1440, 540, 480, 540]}
        self._add_item(layer)

    def _add_capture_layer(self) -> None:
        # Let user pick a video device or file
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Video Device or File",
            "/dev",
            "Video Devices (video*);;All Files (*)",
        )
        if not path:
            # Fall back to typed input
            device, ok = QInputDialog.getText(
                self,
                "Capture Device",
                "Enter device path (e.g. /dev/video0):",
                text="/dev/video0",
            )
            if not ok or not device.strip():
                return
            path = device.strip()
        layer = {"type": "capture", "device": path, "rect": [0, 0, 1920, 1080]}
        self._add_item(layer)

    def _add_text_layer(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Text Layer",
            "Enter text (supports {total_viewers}, {stream_time}, etc.):",
        )
        if not ok or not text.strip():
            return
        layer = {
            "type": "text",
            "content": text.strip(),
            "font_size": 32,
            "color": "#ffffff",
            "rect": [20, 1040, 600, 40],
        }
        self._add_item(layer)

    def _delete_selected(self) -> None:
        for item in list(self._gscene.selectedItems()):
            if item in self._items:
                self._items.remove(item)
            self._gscene.removeItem(item)

    # ── Public API ────────────────────────────────────────────────────────

    def get_updated_scene(self) -> dict[str, Any]:
        """Return the scene dict with all layer rects updated from canvas positions."""
        updated_layers = [item.to_layer_dict() for item in self._items]
        return {**self._scene_data, "layers": updated_layers}

    def save_scene(self, path: Path) -> None:
        """Write the updated scene dict as JSON to *path*."""
        data = self.get_updated_scene()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
