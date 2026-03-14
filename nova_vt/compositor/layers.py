from __future__ import annotations
from dataclasses import dataclass, field


Rect = tuple[int, int, int, int]  # (x, y, w, h)


@dataclass
class CaptureLayer:
    device: str
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "capture", "device": self.device, "rect": list(self.rect)}


@dataclass
class AvatarLayer:
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "avatar", "rect": list(self.rect)}


@dataclass
class ImageLayer:
    path: str
    rect: Rect
    opacity: float = 1.0

    def to_dict(self) -> dict:
        return {"type": "image", "path": self.path, "rect": list(self.rect), "opacity": self.opacity}


@dataclass
class TextLayer:
    content: str
    font_size: int
    color: str
    rect: Rect

    def to_dict(self) -> dict:
        return {"type": "text", "content": self.content,
                "font_size": self.font_size, "color": self.color, "rect": list(self.rect)}


Layer = CaptureLayer | AvatarLayer | ImageLayer | TextLayer


def layer_from_dict(d: dict) -> Layer:
    t = d["type"]
    rect = tuple(d["rect"])
    if t == "capture":
        return CaptureLayer(device=d["device"], rect=rect)
    if t == "avatar":
        return AvatarLayer(rect=rect)
    if t == "image":
        return ImageLayer(path=d["path"], rect=rect, opacity=d.get("opacity", 1.0))
    if t == "text":
        return TextLayer(content=d["content"], font_size=d["font_size"],
                         color=d["color"], rect=rect)
    raise ValueError(f"Unknown layer type: {t!r}")
