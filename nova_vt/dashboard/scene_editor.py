"""SceneEditorDialog — drag-resize layer editor for compositor scenes."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from PyQt6.QtCore import Qt, QPointF, QRectF
from PyQt6.QtGui import QBrush, QColor, QFont, QPen, QPixmap
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import COLOR_SURFACE_RAISED, COLOR_TEXT_DIM, accent_button_style

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

_HANDLE = 8  # half-size of corner handle hit area


def _copy_to_assets(src: str) -> str:
    """Copy *src* into the assets directory and return the destination path.

    Skips copy if an identically-sized file already exists at the destination.
    Appends a numeric suffix on name collision with a different file.
    """
    _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    src_path = Path(src)
    dest = _ASSETS_DIR / src_path.name
    if dest.exists():
        if dest.stat().st_size == src_path.stat().st_size:
            return str(dest)
        stem, suffix = src_path.stem, src_path.suffix
        i = 1
        while dest.exists():
            dest = _ASSETS_DIR / f"{stem}_{i}{suffix}"
            i += 1
    shutil.copy2(src, dest)
    return str(dest)


class _LayerItem(QGraphicsRectItem):
    """Movable + resizable layer rect with inline image/text preview.

    Corner handles (purple squares) are drawn in paint() and detected via
    mouse event proximity — no child items needed, so resize is trivially
    handled by updating self.rect() and the preview auto-follows.
    """

    def __init__(self, layer: dict[str, Any]) -> None:
        x, y, w, h = layer["rect"]
        super().__init__(QRectF(0.0, 0.0, w * _SCALE, h * _SCALE))
        self.setPos(x * _SCALE, y * _SCALE)
        self._layer = layer

        # Resize state
        self._resize_corner: str | None = None
        self._resize_start: QPointF | None = None
        self._resize_orig_rect: QRectF | None = None
        self._resize_orig_pos: QPointF | None = None

        # Cache pixmap for image layers
        self._pixmap: QPixmap | None = None
        if layer.get("type") == "image":
            p = layer.get("path", "")
            if p and Path(p).exists():
                self._pixmap = QPixmap(p)

        layer_type = layer.get("type", "image")
        fill = QColor(_LAYER_COLORS.get(layer_type, "#2d2d4e"))
        fill.setAlpha(100)
        self.setBrush(QBrush(fill))
        self.setPen(QPen(QColor(_LAYER_BORDER.get(layer_type, "#7c3aed")), 2))

        self.setFlags(
            QGraphicsRectItem.GraphicsItemFlag.ItemIsMovable
            | QGraphicsRectItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsRectItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

    # ── Painting ──────────────────────────────────────────────────────────

    def paint(self, painter, option, widget=None) -> None:  # type: ignore[override]
        super().paint(painter, option, widget)
        r = self.rect()
        layer_type = self._layer.get("type", "image")

        # Image preview — draw pixmap scaled to current rect
        if layer_type == "image" and self._pixmap and not self._pixmap.isNull():
            painter.drawPixmap(r.toRect(), self._pixmap)
        else:
            # Fallback label for non-image or missing image
            source = (
                self._layer.get("content")
                or self._layer.get("vrm_path")
                or self._layer.get("path")
                or self._layer.get("device")
                or ""
            )
            source_short = Path(source).name if source else ""
            base = _LAYER_LABELS.get(layer_type, layer_type)
            label = f"{base}\n{source_short}" if source_short else base
            painter.setPen(QPen(QColor("#e2e8f0")))
            f = QFont()
            f.setPointSize(7)
            painter.setFont(f)
            painter.drawText(
                r.adjusted(6, 6, -6, -6),
                Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
                label,
            )

        # Text layer — draw actual content
        if layer_type == "text":
            text = self._layer.get("content", "")
            color_str = self._layer.get("color", "#ffffff")
            painter.setPen(QPen(QColor(color_str)))
            f = QFont()
            px = max(8, int(self._layer.get("font_size", 32) * _SCALE))
            f.setPixelSize(px)
            painter.setFont(f)
            painter.drawText(r.adjusted(4, 4, -4, -4), Qt.TextFlag.TextWordWrap, text)

        # Corner resize handles
        painter.setPen(QPen(QColor("#7c3aed"), 1))
        painter.setBrush(QBrush(QColor("#ffffff")))
        hs = _HANDLE / 2
        for cx, cy in [
            (0, 0),
            (r.width(), 0),
            (0, r.height()),
            (r.width(), r.height()),
        ]:
            painter.drawRect(QRectF(cx - hs, cy - hs, _HANDLE, _HANDLE))

    # ── Resize hit detection ──────────────────────────────────────────────

    def _corner_at(self, pos: QPointF) -> str | None:
        r = self.rect()
        x, y = pos.x(), pos.y()
        hs = _HANDLE + 2  # slightly generous hit area
        if abs(x) < hs and abs(y) < hs:
            return "tl"
        if abs(x - r.width()) < hs and abs(y) < hs:
            return "tr"
        if abs(x) < hs and abs(y - r.height()) < hs:
            return "bl"
        if abs(x - r.width()) < hs and abs(y - r.height()) < hs:
            return "br"
        return None

    def hoverMoveEvent(self, event) -> None:  # type: ignore[override]
        corner = self._corner_at(event.pos())
        if corner in ("tl", "br"):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif corner in ("tr", "bl"):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeAllCursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        corner = self._corner_at(event.pos())
        if corner and event.button() == Qt.MouseButton.LeftButton:
            self._resize_corner = corner
            self._resize_start = event.scenePos()
            self._resize_orig_rect = QRectF(self.rect())
            self._resize_orig_pos = QPointF(self.pos())
            event.accept()
        else:
            self._resize_corner = None
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[override]
        if self._resize_corner and self._resize_start and self._resize_orig_rect:
            dx = event.scenePos().x() - self._resize_start.x()
            dy = event.scenePos().y() - self._resize_start.y()
            r = QRectF(self._resize_orig_rect)
            pos = QPointF(self._resize_orig_pos)
            min_side = _HANDLE * 3

            if "l" in self._resize_corner:
                new_w = r.width() - dx
                if new_w > min_side:
                    pos.setX(self._resize_orig_pos.x() + dx)
                    r.setWidth(new_w)
            if "r" in self._resize_corner:
                new_w = r.width() + dx
                if new_w > min_side:
                    r.setWidth(new_w)
            if "t" in self._resize_corner:
                new_h = r.height() - dy
                if new_h > min_side:
                    pos.setY(self._resize_orig_pos.y() + dy)
                    r.setHeight(new_h)
            if "b" in self._resize_corner:
                new_h = r.height() + dy
                if new_h > min_side:
                    r.setHeight(new_h)

            self.setPos(pos)
            self.setRect(r)
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[override]
        self._resize_corner = None
        super().mouseReleaseEvent(event)

    # ── Data export ───────────────────────────────────────────────────────

    def to_layer_dict(self) -> dict[str, Any]:
        pos = self.pos()
        r = self.rect()
        updated = dict(self._layer)
        updated["rect"] = [
            int(pos.x() / _SCALE),
            int(pos.y() / _SCALE),
            int(r.width() / _SCALE),
            int(r.height() / _SCALE),
        ]
        return updated


# ── Dialog ────────────────────────────────────────────────────────────────────

class SceneEditorDialog(QDialog):
    """Modal scene editor with add/delete layer controls and file copy-to-assets."""

    def __init__(self, scene_data: dict[str, Any], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._scene_data = scene_data
        self.setWindowTitle(f"Edit Scene — {scene_data.get('name', '')}")
        self.setMinimumSize(820, 660)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)

        # ── Add layer toolbar ─────────────────────────────────────────────
        toolbar = QWidget()
        toolbar.setStyleSheet(f"background-color: {COLOR_SURFACE_RAISED}; border-radius: 4px;")
        row = QHBoxLayout(toolbar)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(8)

        add_lbl = QLabel("Add:")
        add_lbl.setStyleSheet(f"color: {COLOR_TEXT_DIM}; background: transparent;")
        row.addWidget(add_lbl)

        for lt, label in [
            ("image",   "🖼 Image"),
            ("avatar",  "🎭 Avatar"),
            ("capture", "📷 Capture"),
            ("text",    "T Text"),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(accent_button_style())
            btn.clicked.connect(lambda _checked, t=lt: self._add_layer(t))
            row.addWidget(btn)

        row.addStretch()

        del_btn = QPushButton("🗑 Delete Selected")
        del_btn.clicked.connect(self._delete_selected)
        row.addWidget(del_btn)

        layout.addWidget(toolbar)

        # ── Canvas ────────────────────────────────────────────────────────
        self._gscene = QGraphicsScene()
        self._gscene.setSceneRect(0, 0, 800, 450)
        self._gscene.setBackgroundBrush(QBrush(QColor("#0a0a14")))

        self._items: list[_LayerItem] = []
        for layer in scene_data.get("layers", []):
            self._push_item(layer)

        self._view = QGraphicsView(self._gscene)
        self._view.setFixedSize(804, 454)
        layout.addWidget(self._view)

        # ── Legend ────────────────────────────────────────────────────────
        legend = QHBoxLayout()
        legend.addStretch()
        hint = QLabel("Drag to move · drag corner handles to resize · click to select")
        hint.setStyleSheet(f"color: {COLOR_TEXT_DIM}; font-size: 11px; background: transparent;")
        legend.addWidget(hint)
        legend.addSpacing(16)
        for lt, color in _LAYER_BORDER.items():
            dot = QLabel(f"■ {_LAYER_LABELS[lt]}")
            dot.setStyleSheet(f"color: {color}; background: transparent; font-size: 11px;")
            legend.addWidget(dot)
            legend.addSpacing(8)
        layout.addLayout(legend)

        # ── OK / Cancel ───────────────────────────────────────────────────
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── Internal ──────────────────────────────────────────────────────────

    def _push_item(self, layer: dict[str, Any]) -> None:
        item = _LayerItem(layer)
        self._gscene.addItem(item)
        self._items.append(item)

    def _add_layer(self, layer_type: str) -> None:
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
        self._push_item({"type": "image", "path": dest, "rect": [0, 0, 1920, 1080], "opacity": 1.0})

    def _add_avatar_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose VRM Avatar",
            str(Path.home()),
            "VRM Files (*.vrm);;All Files (*)",
        )
        if not path:
            return
        try:
            dest = _copy_to_assets(path)
        except Exception as e:
            QMessageBox.warning(self, "Copy failed", f"Could not copy VRM:\n{e}")
            return
        # Bottom-right quarter default position
        self._push_item({"type": "avatar", "vrm_path": dest, "rect": [1440, 540, 480, 540]})

    def _add_capture_layer(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose Video Device or File",
            "/dev",
            "Video Devices (video*);;All Files (*)",
        )
        if not path:
            device, ok = QInputDialog.getText(
                self,
                "Capture Device",
                "Enter device path (e.g. /dev/video0):",
                text="/dev/video0",
            )
            if not ok or not device.strip():
                return
            path = device.strip()
        self._push_item({"type": "capture", "device": path, "rect": [0, 0, 1920, 1080]})

    def _add_text_layer(self) -> None:
        text, ok = QInputDialog.getText(
            self,
            "Text Layer",
            "Enter text (supports {total_viewers}, {stream_time}, etc.):",
        )
        if not ok or not text.strip():
            return
        self._push_item({
            "type": "text",
            "content": text.strip(),
            "font_size": 32,
            "color": "#ffffff",
            "rect": [20, 1040, 600, 40],
        })

    def _delete_selected(self) -> None:
        for item in list(self._gscene.selectedItems()):
            if item in self._items:
                self._items.remove(item)
            self._gscene.removeItem(item)

    # ── Public API ────────────────────────────────────────────────────────

    def get_updated_scene(self) -> dict[str, Any]:
        return {**self._scene_data, "layers": [i.to_layer_dict() for i in self._items]}

    def save_scene(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.get_updated_scene(), f, indent=2)
