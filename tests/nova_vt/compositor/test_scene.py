import json
import tempfile
from pathlib import Path
from nova_vt.compositor.scene import Scene, load_scene, save_scene
from nova_vt.compositor.layers import CaptureLayer, AvatarLayer, ImageLayer, TextLayer


def test_load_scene_from_dict():
    data = {
        "name": "Gameplay",
        "layers": [
            {"type": "capture", "device": "/dev/video0", "rect": [0, 0, 1920, 1080]},
            {"type": "avatar", "rect": [1440, 540, 480, 540]},
        ]
    }
    scene = Scene.from_dict(data)
    assert scene.name == "Gameplay"
    assert len(scene.layers) == 2
    assert isinstance(scene.layers[0], CaptureLayer)
    assert isinstance(scene.layers[1], AvatarLayer)


def test_save_and_load_roundtrip():
    with tempfile.TemporaryDirectory() as d:
        scene = Scene(name="BRB", layers=[
            ImageLayer(path="/tmp/brb.png", rect=(0, 0, 1920, 1080)),
            TextLayer(content="BRB — back soon!", font_size=64, color="#ffffff", rect=(760, 500, 400, 80)),
        ])
        path = Path(d) / "brb.json"
        save_scene(scene, path)
        loaded = load_scene(path)
        assert loaded.name == "BRB"
        assert len(loaded.layers) == 2
        assert isinstance(loaded.layers[0], ImageLayer)
        assert isinstance(loaded.layers[1], TextLayer)
        assert loaded.layers[1].content == "BRB — back soon!"


def test_text_layer_has_template_vars():
    layer = TextLayer(content="{total_viewers} watching", font_size=32, color="#fff", rect=(0, 0, 200, 40))
    assert "{total_viewers}" in layer.content


def test_default_scenes_include_gameplay():
    from nova_vt.compositor.scene import default_scenes
    scenes = default_scenes()
    names = [s.name for s in scenes]
    assert "Gameplay" in names
    assert "BRB" in names
    assert "Just Chatting" in names
