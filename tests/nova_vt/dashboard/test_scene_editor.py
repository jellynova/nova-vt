import sys
import json
import tempfile
from pathlib import Path
import pytest
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt
from nova_vt.dashboard.scene_editor import SceneEditorDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


SAMPLE_SCENE = {
    "name": "Test Scene",
    "layers": [
        {"type": "capture", "device": "/dev/video0", "rect": [0, 0, 1920, 1080]},
        {"type": "avatar", "rect": [1440, 540, 480, 540]},
        {"type": "image", "path": "overlay.png", "rect": [0, 0, 1920, 100]},
    ],
}


def make_dialog(qtbot, scene_data=None):
    if scene_data is None:
        scene_data = SAMPLE_SCENE
    dialog = SceneEditorDialog(scene_data=scene_data)
    qtbot.addWidget(dialog)
    return dialog


def test_scene_editor_shows_canvas(qapp, qtbot):
    dialog = make_dialog(qtbot)
    views = dialog.findChildren(QGraphicsView)
    assert len(views) == 1


def test_scene_editor_has_one_item_per_layer(qapp, qtbot):
    dialog = make_dialog(qtbot)
    scene = dialog._gscene
    assert len(scene.items()) == len(SAMPLE_SCENE["layers"])


def test_scene_editor_items_have_correct_positions(qapp, qtbot):
    dialog = make_dialog(qtbot)
    scene = dialog._gscene
    items = scene.items()
    positions = [(item.x(), item.y()) for item in items]
    assert (0.0, 0.0) in positions


def test_scene_editor_accept_writes_back_scene(qapp, qtbot):
    from nova_vt.dashboard.scene_editor import _SCALE
    dialog = make_dialog(qtbot)
    # Move the first _items entry (capture layer, initially at source origin 0,0)
    item = dialog._items[0]
    dx_canvas, dy_canvas = 80.0, 45.0
    item.setPos(dx_canvas, dy_canvas)
    result = dialog.get_updated_scene()
    layer = result["layers"][0]
    assert layer["rect"][0] == int(dx_canvas / _SCALE)
    assert layer["rect"][1] == int(dy_canvas / _SCALE)


def test_scene_editor_preserves_layer_types(qapp, qtbot):
    dialog = make_dialog(qtbot)
    result = dialog.get_updated_scene()
    types = [l["type"] for l in result["layers"]]
    assert "capture" in types
    assert "avatar" in types
    assert "image" in types


def test_scene_editor_title_contains_scene_name(qapp, qtbot):
    dialog = make_dialog(qtbot)
    assert "Test Scene" in dialog.windowTitle()


def test_scene_editor_empty_layers_does_not_crash(qapp, qtbot):
    empty_scene = {"name": "Empty", "layers": []}
    dialog = make_dialog(qtbot, scene_data=empty_scene)
    assert len(dialog._gscene.items()) == 0


def test_scene_editor_save_scene_writes_json(qapp, qtbot):
    dialog = make_dialog(qtbot)
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "test_scene.json"
        dialog.save_scene(path)
        with open(path) as f:
            data = json.load(f)
        assert data["name"] == "Test Scene"
        assert len(data["layers"]) == 3
