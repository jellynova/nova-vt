from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from nova_vt.compositor.layers import Layer, layer_from_dict, AvatarLayer, CaptureLayer, ImageLayer, TextLayer


@dataclass
class Scene:
    name: str
    layers: list[Layer] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"name": self.name, "layers": [l.to_dict() for l in self.layers]}

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(
            name=d["name"],
            layers=[layer_from_dict(l) for l in d.get("layers", [])],
        )


def load_scene(path: Path) -> Scene:
    return Scene.from_dict(json.loads(path.read_text()))


def save_scene(scene: Scene, path: Path) -> None:
    path.write_text(json.dumps(scene.to_dict(), indent=2))


def default_scenes() -> list[Scene]:
    return [
        Scene("Gameplay", [
            CaptureLayer(device="/dev/video1", rect=(0, 0, 1920, 1080)),
            AvatarLayer(rect=(1440, 540, 480, 540)),
        ]),
        Scene("Just Chatting", [
            AvatarLayer(rect=(560, 0, 800, 1080)),
        ]),
        Scene("BRB", [
            TextLayer(content="BRB — back soon!", font_size=72, color="#a78bfa", rect=(660, 480, 600, 120)),
        ]),
        Scene("Intro", [
            TextLayer(content="Starting soon...", font_size=64, color="#e9d5ff", rect=(660, 480, 600, 120)),
        ]),
        Scene("Ending", [
            TextLayer(content="Thanks for watching! 💜", font_size=64, color="#e9d5ff", rect=(560, 480, 800, 120)),
        ]),
    ]
