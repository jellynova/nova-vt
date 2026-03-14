import sys
import pytest
from PyQt6.QtWidgets import QApplication, QPushButton
from PyQt6.QtCore import Qt
from nova_vt.dashboard.scene_switcher import SceneSwitcherWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


SCENES = ["Gameplay", "Just Chatting", "BRB", "Intro", "Ending"]


def test_scene_switcher_creates_one_button_per_scene(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    buttons = widget.findChildren(QPushButton)
    assert len(buttons) == len(SCENES)
    labels = [b.text() for b in buttons]
    assert labels == SCENES


def test_scene_switcher_first_scene_active_by_default(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    assert widget.active_scene() == SCENES[0]


def test_scene_switcher_click_changes_active(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    widget.show()
    buttons = widget.findChildren(QPushButton)
    qtbot.mouseClick(buttons[2], Qt.MouseButton.LeftButton)
    assert widget.active_scene() == SCENES[2]


def test_scene_switcher_active_button_is_checked(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    widget.show()
    buttons = widget.findChildren(QPushButton)
    qtbot.mouseClick(buttons[1], Qt.MouseButton.LeftButton)
    assert buttons[1].isChecked()
    assert not buttons[0].isChecked()
    assert not buttons[2].isChecked()


def test_scene_switcher_emits_signal_on_change(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    widget.show()
    buttons = widget.findChildren(QPushButton)
    with qtbot.waitSignal(widget.scene_changed, timeout=500) as blocker:
        qtbot.mouseClick(buttons[3], Qt.MouseButton.LeftButton)
    assert blocker.args == [SCENES[3]]


def test_scene_switcher_buttons_always_enabled(qapp, qtbot):
    """Buttons must be enabled regardless of stream state."""
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    for btn in widget.findChildren(QPushButton):
        assert btn.isEnabled()


def test_scene_switcher_set_scenes_updates_buttons(qapp, qtbot):
    widget = SceneSwitcherWidget(scenes=SCENES)
    qtbot.addWidget(widget)
    new_scenes = ["A", "B"]
    widget.set_scenes(new_scenes)
    buttons = widget.findChildren(QPushButton)
    assert [b.text() for b in buttons] == new_scenes
    assert widget.active_scene() == "A"
