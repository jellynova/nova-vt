# nova-vt Dashboard UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Studio+Chat PyQt6 dashboard that wires together all pipeline threads and presents them as a unified streaming control surface.

**Architecture:** MainWindow hosts a left panel (~75%) with preview, scene switcher, and audio mixer, and a right panel (~25%) with platform stats, chat tabs, and reply input. A state machine (idle → previewing → live) gates which threads run and which UI elements are visible. All widgets communicate with pipeline threads exclusively via bounded `queue.Queue` and Qt signals — no direct thread method calls from the UI.

**Tech Stack:** PyQt6, pytest-qt

**Spec:** `docs/superpowers/specs/2026-03-14-nova-vt-redesign-design.md`

**Prerequisites:** Plans 1 and 2 must be complete before executing this plan.

---

## Chunk 1: Visual Foundation

### Task 1: Theme

**Files:**
- Create: `nova_vt/dashboard/theme.py`
- Create: `tests/nova_vt/dashboard/__init__.py`
- Create: `tests/nova_vt/dashboard/test_theme.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_theme.py`:
```python
import pytest
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton
from nova_vt.dashboard.theme import (
    COLOR_BG,
    COLOR_SURFACE,
    COLOR_ACCENT,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_DANGER,
    apply_theme,
    accent_button_style,
    danger_button_style,
    panel_style,
)


@pytest.fixture(scope="module")
def qapp():
    import sys
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_color_constants():
    assert COLOR_BG == "#0f0f1a"
    assert COLOR_ACCENT == "#7c3aed"
    assert COLOR_DANGER == "#dc2626"
    assert COLOR_TEXT.startswith("#")
    assert COLOR_SURFACE.startswith("#")
    assert COLOR_TEXT_DIM.startswith("#")


def test_accent_button_style_contains_accent_color():
    style = accent_button_style()
    assert COLOR_ACCENT in style


def test_danger_button_style_contains_danger_color():
    style = danger_button_style()
    assert COLOR_DANGER in style


def test_panel_style_contains_surface_color():
    style = panel_style()
    assert COLOR_SURFACE in style


def test_apply_theme_sets_stylesheet(qapp):
    widget = QWidget()
    apply_theme(qapp)
    # After apply_theme the app stylesheet should reference the bg color
    sheet = qapp.styleSheet()
    assert COLOR_BG in sheet
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_theme.py -v 2>&1 | head -30
```

Expected output: `ImportError` or `ModuleNotFoundError` for `nova_vt.dashboard.theme`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/__init__.py`:
```python
```

`nova_vt/dashboard/theme.py`:
```python
"""Dark purple theme constants and stylesheet helpers for nova-vt dashboard."""

COLOR_BG = "#0f0f1a"
COLOR_SURFACE = "#1a1a2e"
COLOR_SURFACE_RAISED = "#22223a"
COLOR_ACCENT = "#7c3aed"
COLOR_ACCENT_HOVER = "#6d28d9"
COLOR_TEXT = "#e2e8f0"
COLOR_TEXT_DIM = "#94a3b8"
COLOR_DANGER = "#dc2626"
COLOR_DANGER_HOVER = "#b91c1c"
COLOR_SUCCESS = "#16a34a"
COLOR_BORDER = "#2d2d4e"


def accent_button_style() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_TEXT};
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {COLOR_ACCENT_HOVER};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_SURFACE_RAISED};
            color: {COLOR_TEXT_DIM};
        }}
    """


def danger_button_style() -> str:
    return f"""
        QPushButton {{
            background-color: {COLOR_DANGER};
            color: {COLOR_TEXT};
            border: none;
            border-radius: 4px;
            padding: 6px 14px;
            font-weight: bold;
        }}
        QPushButton:hover {{
            background-color: {COLOR_DANGER_HOVER};
        }}
        QPushButton:disabled {{
            background-color: {COLOR_SURFACE_RAISED};
            color: {COLOR_TEXT_DIM};
        }}
    """


def panel_style() -> str:
    return f"""
        QWidget {{
            background-color: {COLOR_SURFACE};
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
        }}
    """


def apply_theme(app) -> None:
    """Apply the global dark/purple stylesheet to the QApplication."""
    app.setStyleSheet(f"""
        QMainWindow, QDialog, QWidget {{
            background-color: {COLOR_BG};
            color: {COLOR_TEXT};
            font-family: "Inter", "Segoe UI", sans-serif;
            font-size: 13px;
        }}
        QLabel {{
            color: {COLOR_TEXT};
            background-color: transparent;
            border: none;
        }}
        QPushButton {{
            background-color: {COLOR_SURFACE_RAISED};
            color: {COLOR_TEXT};
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            padding: 5px 12px;
        }}
        QPushButton:hover {{
            background-color: {COLOR_ACCENT};
            border-color: {COLOR_ACCENT};
        }}
        QPushButton:checked {{
            background-color: {COLOR_ACCENT};
            border-color: {COLOR_ACCENT};
            color: {COLOR_TEXT};
        }}
        QSlider::groove:horizontal {{
            background: {COLOR_SURFACE_RAISED};
            height: 6px;
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            background: {COLOR_ACCENT};
            width: 14px;
            height: 14px;
            border-radius: 7px;
            margin: -4px 0;
        }}
        QSlider::sub-page:horizontal {{
            background: {COLOR_ACCENT};
            border-radius: 3px;
        }}
        QProgressBar {{
            background-color: {COLOR_SURFACE_RAISED};
            border: none;
            border-radius: 2px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {COLOR_SUCCESS};
            border-radius: 2px;
        }}
        QLineEdit, QComboBox {{
            background-color: {COLOR_SURFACE_RAISED};
            color: {COLOR_TEXT};
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            padding: 4px 8px;
        }}
        QLineEdit:focus, QComboBox:focus {{
            border-color: {COLOR_ACCENT};
        }}
        QTabWidget::pane {{
            border: 1px solid {COLOR_BORDER};
            background-color: {COLOR_SURFACE};
        }}
        QTabBar::tab {{
            background-color: {COLOR_SURFACE_RAISED};
            color: {COLOR_TEXT_DIM};
            padding: 6px 14px;
            border: none;
        }}
        QTabBar::tab:selected {{
            background-color: {COLOR_ACCENT};
            color: {COLOR_TEXT};
        }}
        QListWidget {{
            background-color: {COLOR_SURFACE};
            border: none;
            color: {COLOR_TEXT};
        }}
        QListWidget::item:hover {{
            background-color: {COLOR_SURFACE_RAISED};
        }}
        QScrollBar:vertical {{
            background: {COLOR_SURFACE};
            width: 8px;
        }}
        QScrollBar::handle:vertical {{
            background: {COLOR_BORDER};
            border-radius: 4px;
        }}
        QGroupBox {{
            border: 1px solid {COLOR_BORDER};
            border-radius: 4px;
            margin-top: 8px;
            padding-top: 8px;
            color: {COLOR_TEXT_DIM};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
        }}
    """)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_theme.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_theme.py::test_color_constants
PASSED tests/nova_vt/dashboard/test_theme.py::test_accent_button_style_contains_accent_color
PASSED tests/nova_vt/dashboard/test_theme.py::test_danger_button_style_contains_danger_color
PASSED tests/nova_vt/dashboard/test_theme.py::test_panel_style_contains_surface_color
PASSED tests/nova_vt/dashboard/test_theme.py::test_apply_theme_sets_stylesheet
5 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/__init__.py nova_vt/dashboard/theme.py tests/nova_vt/dashboard/__init__.py tests/nova_vt/dashboard/test_theme.py && git commit -m "feat(dashboard): add theme constants and stylesheet helpers

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Core Display Widgets

### Task 2: PreviewWidget

**Files:**
- Create: `nova_vt/dashboard/preview.py`
- Create: `tests/nova_vt/dashboard/test_preview.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_preview.py`:
```python
import sys
import queue
import numpy as np
import pytest
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from nova_vt.dashboard.preview import PreviewWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_preview_widget_initial_size(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    assert widget.minimumWidth() == 960
    assert widget.minimumHeight() == 540


def test_preview_widget_shows_placeholder(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # Before any frame arrives, pixmap should be null or placeholder exists
    label_pixmap = widget._label.pixmap()
    # Either no pixmap (null) or a placeholder was set — either is valid
    # The key assertion: widget is visible and _label exists
    assert widget._label is not None


def test_preview_widget_renders_frame(qapp, qtbot):
    """Put an RGBA frame on the queue; after timer tick it should appear as pixmap."""
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    widget.show()

    # Push a green 960x540 RGBA frame
    frame = np.zeros((540, 960, 4), dtype=np.uint8)
    frame[:, :, 1] = 200  # green channel
    frame[:, :, 3] = 255  # fully opaque
    q.put_nowait(frame)

    # Wait for the QTimer to fire and call _poll_frame
    qtbot.waitUntil(lambda: widget._label.pixmap() is not None and not widget._label.pixmap().isNull(), timeout=500)
    pm = widget._label.pixmap()
    assert pm.width() == 960
    assert pm.height() == 540


def test_preview_widget_empty_queue_does_not_crash(qapp, qtbot):
    """Polling an empty queue should be a no-op, not raise."""
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # Manually call poll — should not raise
    widget._poll_frame()


def test_preview_widget_timer_interval(qapp, qtbot):
    q = queue.Queue(maxsize=2)
    widget = PreviewWidget(preview_queue=q)
    qtbot.addWidget(widget)
    # 30 fps → ~33ms interval
    assert widget._timer.interval() <= 34
    assert widget._timer.interval() >= 32
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_preview.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.preview`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/preview.py`:
```python
"""PreviewWidget — displays 960×540 half-res compositor frames via QTimer."""
from __future__ import annotations

import queue
from typing import Optional

import numpy as np
from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtGui import QImage, QPixmap
from PyQt6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget


class PreviewWidget(QWidget):
    """Polls *preview_queue* at 30 fps and renders RGBA numpy frames into a QLabel."""

    def __init__(self, preview_queue: queue.Queue, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._queue = preview_queue

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._label.setStyleSheet("background-color: #0a0a14; color: #94a3b8;")
        self._label.setText("No Preview")
        self._label.setMinimumSize(960, 540)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self.setMinimumSize(960, 540)

        self._timer = QTimer(self)
        self._timer.setInterval(33)  # ~30 fps
        self._timer.timeout.connect(self._poll_frame)
        self._timer.start()

    def _poll_frame(self) -> None:
        """Pull the latest frame from the queue (discard stale backlog) and display it."""
        frame: Optional[np.ndarray] = None
        try:
            while True:
                frame = self._queue.get_nowait()
        except queue.Empty:
            pass

        if frame is None:
            return

        # frame is HxWx4 RGBA uint8, shape (540, 960, 4)
        h, w, _ = frame.shape
        # QImage expects contiguous memory; ensure C-contiguous
        frame_c = np.ascontiguousarray(frame)
        image = QImage(
            frame_c.data,
            w,
            h,
            w * 4,
            QImage.Format.Format_RGBA8888,
        )
        # Keep reference so GC doesn't free the array while QImage uses it
        self._last_frame = frame_c
        self._label.setPixmap(QPixmap.fromImage(image))
        self._label.setText("")

    def stop(self) -> None:
        """Stop the polling timer (call on shutdown)."""
        self._timer.stop()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_preview.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_preview.py::test_preview_widget_initial_size
PASSED tests/nova_vt/dashboard/test_preview.py::test_preview_widget_shows_placeholder
PASSED tests/nova_vt/dashboard/test_preview.py::test_preview_widget_renders_frame
PASSED tests/nova_vt/dashboard/test_preview.py::test_preview_widget_empty_queue_does_not_crash
PASSED tests/nova_vt/dashboard/test_preview.py::test_preview_widget_timer_interval
5 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/preview.py tests/nova_vt/dashboard/test_preview.py && git commit -m "feat(dashboard): add PreviewWidget with 30fps QTimer frame polling

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 3: SceneSwitcherWidget

**Files:**
- Create: `nova_vt/dashboard/scene_switcher.py`
- Create: `tests/nova_vt/dashboard/test_scene_switcher.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_scene_switcher.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_scene_switcher.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.scene_switcher`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/scene_switcher.py`:
```python
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

    # ------------------------------------------------------------------
    def active_scene(self) -> str:
        for btn in self._buttons:
            if btn.isChecked():
                return btn.text()
        return self._scenes[0] if self._scenes else ""

    def set_scenes(self, scenes: list[str]) -> None:
        """Replace current scene buttons with a new list."""
        # Remove old buttons
        for btn in self._buttons:
            self._layout.removeWidget(btn)
            btn.deleteLater()
        self._buttons.clear()
        self._scenes = list(scenes)

        # Re-insert before the trailing stretch
        stretch_item = self._layout.takeAt(self._layout.count() - 1)

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

    # ------------------------------------------------------------------
    def _on_button_clicked(self) -> None:
        sender = self.sender()
        if not isinstance(sender, QPushButton):
            return
        for btn in self._buttons:
            btn.setChecked(btn is sender)
        self.scene_changed.emit(sender.text())
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_scene_switcher.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_creates_one_button_per_scene
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_first_scene_active_by_default
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_click_changes_active
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_active_button_is_checked
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_emits_signal_on_change
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_buttons_always_enabled
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::test_scene_switcher_set_scenes_updates_buttons
7 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/scene_switcher.py tests/nova_vt/dashboard/test_scene_switcher.py && git commit -m "feat(dashboard): add SceneSwitcherWidget with scene_changed signal

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Audio & Chat

### Task 4: AudioMixerWidget

**Files:**
- Create: `nova_vt/dashboard/audio_mixer.py`
- Create: `tests/nova_vt/dashboard/test_audio_mixer_widget.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_audio_mixer_widget.py`:
```python
import sys
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication, QSlider, QPushButton, QProgressBar
from PyQt6.QtCore import Qt
from nova_vt.dashboard.audio_mixer import AudioMixerWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


CHANNELS = ["mic", "game", "bgm", "master"]
DEFAULTS = {"mic": 75, "game": 60, "bgm": 30, "master": 90}


def make_widget(qtbot):
    mock_mixer = MagicMock()
    mock_mixer.get_peak_level = MagicMock(return_value=0.0)
    widget = AudioMixerWidget(mixer=mock_mixer)
    qtbot.addWidget(widget)
    return widget, mock_mixer


def test_audio_mixer_has_four_channels(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    sliders = widget.findChildren(QSlider)
    assert len(sliders) == 4


def test_audio_mixer_default_values(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    for ch, expected in DEFAULTS.items():
        assert widget.get_volume(ch) == expected, f"{ch} should default to {expected}"


def test_audio_mixer_slider_change_updates_volume(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget._sliders["mic"].setValue(50)
    assert widget.get_volume("mic") == 50


def test_audio_mixer_slider_calls_mixer_set_volume(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget._sliders["game"].setValue(40)
    mock_mixer.set_volume.assert_called_with("game", 40)


def test_audio_mixer_mute_toggle_calls_mixer(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    widget.show()
    mute_btn = widget._mute_buttons["mic"]
    qtbot.mouseClick(mute_btn, Qt.MouseButton.LeftButton)
    mock_mixer.set_mute.assert_called_with("mic", True)
    qtbot.mouseClick(mute_btn, Qt.MouseButton.LeftButton)
    mock_mixer.set_mute.assert_called_with("mic", False)


def test_audio_mixer_has_vu_meters(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    meters = widget.findChildren(QProgressBar)
    assert len(meters) == 4


def test_audio_mixer_vu_meter_range(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    for ch in CHANNELS:
        bar = widget._vu_meters[ch]
        assert bar.minimum() == 0
        assert bar.maximum() == 100


def test_audio_mixer_vu_update_from_mock(qapp, qtbot):
    widget, mock_mixer = make_widget(qtbot)
    mock_mixer.get_peak_level.return_value = 0.75
    widget._update_vu_meters()
    for ch in CHANNELS:
        assert widget._vu_meters[ch].value() == 75


def test_audio_mixer_end_stream_button_exists(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    assert widget._end_stream_btn is not None


def test_audio_mixer_end_stream_emits_signal(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.show()
    with qtbot.waitSignal(widget.end_stream_requested, timeout=500):
        qtbot.mouseClick(widget._end_stream_btn, Qt.MouseButton.LeftButton)


def test_audio_mixer_end_stream_disabled_when_not_live(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.set_live(False)
    assert not widget._end_stream_btn.isEnabled()


def test_audio_mixer_end_stream_enabled_when_live(qapp, qtbot):
    widget, _ = make_widget(qtbot)
    widget.set_live(True)
    assert widget._end_stream_btn.isEnabled()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_audio_mixer_widget.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.audio_mixer`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/audio_mixer.py`:
```python
"""AudioMixerWidget — per-channel volume sliders, mute toggles, VU meters, END STREAM button."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtCore import QTimer, pyqtSignal, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import (
    COLOR_DANGER,
    COLOR_DANGER_HOVER,
    COLOR_TEXT,
    COLOR_SURFACE_RAISED,
    COLOR_BORDER,
    COLOR_ACCENT,
    danger_button_style,
)

_CHANNELS = ["mic", "game", "bgm", "master"]
_DEFAULTS = {"mic": 75, "game": 60, "bgm": 30, "master": 90}

_MUTE_STYLE = f"""
    QPushButton {{
        background-color: {COLOR_SURFACE_RAISED};
        color: {COLOR_TEXT};
        border: 1px solid {COLOR_BORDER};
        border-radius: 3px;
        padding: 3px 8px;
        font-size: 11px;
    }}
    QPushButton:checked {{
        background-color: {COLOR_DANGER};
        border-color: {COLOR_DANGER};
    }}
"""


class AudioMixerWidget(QWidget):
    """Horizontal row of channel strips with sliders, mute buttons, and VU meters.

    Signals:
        end_stream_requested: emitted when the END STREAM button is clicked.
    """

    end_stream_requested = pyqtSignal()

    def __init__(self, mixer: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._mixer = mixer
        self._sliders: dict[str, QSlider] = {}
        self._mute_buttons: dict[str, QPushButton] = {}
        self._vu_meters: dict[str, QProgressBar] = {}

        outer = QHBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(12)

        for ch in _CHANNELS:
            strip = self._build_channel_strip(ch)
            outer.addLayout(strip)

        outer.addStretch()

        # END STREAM button
        self._end_stream_btn = QPushButton("⏹ END STREAM")
        self._end_stream_btn.setStyleSheet(danger_button_style())
        self._end_stream_btn.setEnabled(False)
        self._end_stream_btn.clicked.connect(self.end_stream_requested.emit)
        outer.addWidget(self._end_stream_btn)

        # VU meter update timer
        self._vu_timer = QTimer(self)
        self._vu_timer.setInterval(50)  # 20 fps for meters
        self._vu_timer.timeout.connect(self._update_vu_meters)
        self._vu_timer.start()

    # ------------------------------------------------------------------
    def _build_channel_strip(self, channel: str) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignHCenter)

        label = QLabel(channel.upper())
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(label)

        slider = QSlider(Qt.Orientation.Vertical)
        slider.setRange(0, 100)
        slider.setValue(_DEFAULTS[channel])
        slider.setFixedHeight(80)
        slider.valueChanged.connect(lambda val, ch=channel: self._on_volume_changed(ch, val))
        layout.addWidget(slider, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._sliders[channel] = slider

        mute_btn = QPushButton("M")
        mute_btn.setCheckable(True)
        mute_btn.setFixedWidth(32)
        mute_btn.setStyleSheet(_MUTE_STYLE)
        mute_btn.toggled.connect(lambda checked, ch=channel: self._mixer.set_mute(ch, checked))
        layout.addWidget(mute_btn, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._mute_buttons[channel] = mute_btn

        vu = QProgressBar()
        vu.setRange(0, 100)
        vu.setValue(0)
        vu.setTextVisible(False)
        vu.setFixedWidth(20)
        vu.setFixedHeight(60)
        vu.setOrientation(Qt.Orientation.Vertical)
        layout.addWidget(vu, alignment=Qt.AlignmentFlag.AlignHCenter)
        self._vu_meters[channel] = vu

        return layout

    # ------------------------------------------------------------------
    def get_volume(self, channel: str) -> int:
        return self._sliders[channel].value()

    def set_live(self, live: bool) -> None:
        self._end_stream_btn.setEnabled(live)

    def _on_volume_changed(self, channel: str, value: int) -> None:
        self._mixer.set_volume(channel, value)

    def _update_vu_meters(self) -> None:
        for ch in _CHANNELS:
            peak: float = self._mixer.get_peak_level(ch) if hasattr(self._mixer, "get_peak_level") else 0.0
            self._vu_meters[ch].setValue(int(peak * 100))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_audio_mixer_widget.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_has_four_channels
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_default_values
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_slider_change_updates_volume
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_slider_calls_mixer_set_volume
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_mute_toggle_calls_mixer
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_has_vu_meters
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_vu_meter_range
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_vu_update_from_mock
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_end_stream_button_exists
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_end_stream_emits_signal
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_end_stream_disabled_when_not_live
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py::test_audio_mixer_end_stream_enabled_when_live
12 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/audio_mixer.py tests/nova_vt/dashboard/test_audio_mixer_widget.py && git commit -m "feat(dashboard): add AudioMixerWidget with sliders, mute, VU meters, END STREAM

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 5: ChatWidget

**Files:**
- Create: `nova_vt/dashboard/chat_widget.py`
- Create: `tests/nova_vt/dashboard/test_chat_widget.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_chat_widget.py`:
```python
import sys
import pytest
from dataclasses import dataclass
from PyQt6.QtWidgets import QApplication, QTabWidget, QListWidget, QLineEdit, QPushButton
from PyQt6.QtCore import Qt
from nova_vt.dashboard.chat_widget import ChatWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


@dataclass
class FakeChatMessage:
    platform: str
    username: str
    color: str
    text: str
    event_type: str = "message"


def test_chat_widget_has_four_tabs(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    tabs = widget.findChildren(QTabWidget)
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.count() == 4
    labels = [tab.tabText(i) for i in range(tab.count())]
    assert labels == ["All", "Twitch", "YouTube", "TikTok"]


def test_chat_widget_message_appears_in_all_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="viewer1", color="#9146FF", text="Hello!")
    widget.add_message(msg)
    all_list = widget._lists["All"]
    assert all_list.count() == 1
    assert "viewer1" in all_list.item(0).text()
    assert "Hello!" in all_list.item(0).text()


def test_chat_widget_message_appears_in_platform_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="youtube", username="yt_fan", color="#FF0000", text="Nice stream")
    widget.add_message(msg)
    yt_list = widget._lists["YouTube"]
    assert yt_list.count() == 1
    assert "yt_fan" in yt_list.item(0).text()


def test_chat_widget_twitch_message_not_in_youtube_tab(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="twitch_user", color="#9146FF", text="hi")
    widget.add_message(msg)
    yt_list = widget._lists["YouTube"]
    assert yt_list.count() == 0


def test_chat_widget_sub_event_highlighted(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    msg = FakeChatMessage(platform="twitch", username="subber", color="#9146FF", text="subscribed!", event_type="sub")
    widget.add_message(msg)
    all_list = widget._lists["All"]
    item = all_list.item(0)
    # Sub events should have a different foreground color
    assert item.foreground().color().name() != "#e2e8f0"


def test_chat_widget_has_reply_input(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    assert widget._reply_input is not None
    assert isinstance(widget._reply_input, QLineEdit)


def test_chat_widget_has_send_button(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    assert widget._send_button is not None
    assert isinstance(widget._send_button, QPushButton)


def test_chat_widget_send_emits_signal(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget._reply_input.setText("test message")
    with qtbot.waitSignal(widget.message_send_requested, timeout=500) as blocker:
        qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert blocker.args[0] == "test message"


def test_chat_widget_send_clears_input(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    widget._reply_input.setText("something")
    qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert widget._reply_input.text() == ""


def test_chat_widget_send_includes_platform_when_tab_selected(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    widget.show()
    # Switch to Twitch tab (index 1)
    widget._tabs.setCurrentIndex(1)
    widget._reply_input.setText("hello twitch")
    signals = []
    widget.message_send_requested.connect(lambda text, plat: signals.append((text, plat)))
    qtbot.mouseClick(widget._send_button, Qt.MouseButton.LeftButton)
    assert signals[0] == ("hello twitch", "twitch")


def test_chat_widget_multiple_messages_prepend(qapp, qtbot):
    widget = ChatWidget()
    qtbot.addWidget(widget)
    for i in range(3):
        msg = FakeChatMessage(platform="twitch", username=f"user{i}", color="#fff", text=f"msg{i}")
        widget.add_message(msg)
    all_list = widget._lists["All"]
    assert all_list.count() == 3
    # Most recent message should be at the top (row 0)
    assert "user2" in all_list.item(0).text()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_chat_widget.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.chat_widget`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/chat_widget.py`:
```python
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

    # ------------------------------------------------------------------
    def add_message(self, msg: Any) -> None:
        """Insert *msg* (ChatMessage or duck-type) into relevant list widgets."""
        display = f"[{msg.platform}] {msg.username}: {msg.text}"
        tab_name = _PLATFORM_TAB.get(msg.platform, "")

        for list_name, lst in self._lists.items():
            if list_name != "All" and list_name != tab_name:
                continue
            item = QListWidgetItem(display)
            # Color-code events
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_chat_widget.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_has_four_tabs
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_message_appears_in_all_tab
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_message_appears_in_platform_tab
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_twitch_message_not_in_youtube_tab
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_sub_event_highlighted
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_has_reply_input
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_has_send_button
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_send_emits_signal
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_send_clears_input
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_send_includes_platform_when_tab_selected
PASSED tests/nova_vt/dashboard/test_chat_widget.py::test_chat_widget_multiple_messages_prepend
11 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/chat_widget.py tests/nova_vt/dashboard/test_chat_widget.py && git commit -m "feat(dashboard): add ChatWidget with platform tabs, events, and reply input

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Stats, Settings, Scene Editor

### Task 6: PlatformStatsWidget

**Files:**
- Create: `nova_vt/dashboard/platform_stats.py`
- Create: `tests/nova_vt/dashboard/test_platform_stats.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_platform_stats.py`:
```python
import sys
import pytest
from PyQt6.QtWidgets import QApplication, QLabel
from nova_vt.dashboard.platform_stats import PlatformStatsWidget


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def test_platform_stats_has_three_rows(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    # One row per platform
    assert widget._rows["twitch"] is not None
    assert widget._rows["youtube"] is not None
    assert widget._rows["tiktok"] is not None


def test_platform_stats_initial_zero(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    for plat in ("twitch", "youtube", "tiktok"):
        label = widget._viewer_labels[plat]
        assert "0" in label.text()


def test_platform_stats_update_viewer_count(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    widget.update_stats("twitch", viewers=1234, likes=56)
    label = widget._viewer_labels["twitch"]
    assert "1234" in label.text()


def test_platform_stats_update_likes(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    widget.update_stats("youtube", viewers=500, likes=99)
    label = widget._likes_labels["youtube"]
    assert "99" in label.text()


def test_platform_stats_twitch_color_coded(qapp, qtbot):
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    # Twitch row label should contain the Twitch purple color
    row = widget._rows["twitch"]
    sheet = row.styleSheet()
    # The platform label color for Twitch is #9146FF
    assert "#9146FF" in sheet or "#9146ff" in sheet.lower()


def test_platform_stats_update_from_stream_stats(qapp, qtbot):
    """update_from_stream_stats accepts a dict mapping platform→{viewers,likes}."""
    widget = PlatformStatsWidget()
    qtbot.addWidget(widget)
    stats = {
        "twitch": {"viewers": 300, "likes": 10},
        "youtube": {"viewers": 150, "likes": 5},
        "tiktok": {"viewers": 75, "likes": 200},
    }
    widget.update_from_stream_stats(stats)
    assert "300" in widget._viewer_labels["twitch"].text()
    assert "150" in widget._viewer_labels["youtube"].text()
    assert "75" in widget._viewer_labels["tiktok"].text()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_platform_stats.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.platform_stats`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/platform_stats.py`:
```python
"""PlatformStatsWidget — per-platform viewer count and likes display."""
from __future__ import annotations

from typing import Any, Optional

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget
from PyQt6.QtCore import Qt

_PLATFORM_META = {
    "twitch": {"label": "Twitch", "color": "#9146FF"},
    "youtube": {"label": "YouTube", "color": "#FF0000"},
    "tiktok": {"label": "TikTok", "color": "#69C9D0"},
}


class PlatformStatsWidget(QWidget):
    """Shows viewer counts + likes for Twitch, YouTube, and TikTok."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows: dict[str, QWidget] = {}
        self._viewer_labels: dict[str, QLabel] = {}
        self._likes_labels: dict[str, QLabel] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        for platform, meta in _PLATFORM_META.items():
            row = QWidget()
            row.setStyleSheet(f"QWidget {{ border-left: 3px solid {meta['color']}; padding-left: 6px; }}")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(4, 2, 4, 2)

            name_label = QLabel(meta["label"])
            name_label.setFixedWidth(70)
            name_label.setStyleSheet(f"color: {meta['color']}; font-weight: bold; border: none;")
            row_layout.addWidget(name_label)

            viewer_label = QLabel("👁 0")
            viewer_label.setStyleSheet("border: none; color: #e2e8f0;")
            row_layout.addWidget(viewer_label)

            likes_label = QLabel("♥ 0")
            likes_label.setStyleSheet("border: none; color: #94a3b8;")
            row_layout.addWidget(likes_label)

            row_layout.addStretch()
            layout.addWidget(row)

            self._rows[platform] = row
            self._viewer_labels[platform] = viewer_label
            self._likes_labels[platform] = likes_label

        layout.addStretch()

    def update_stats(self, platform: str, viewers: int, likes: int) -> None:
        if platform not in self._viewer_labels:
            return
        self._viewer_labels[platform].setText(f"👁 {viewers}")
        self._likes_labels[platform].setText(f"♥ {likes}")

    def update_from_stream_stats(self, stats: dict[str, dict[str, int]]) -> None:
        for platform, data in stats.items():
            self.update_stats(platform, data.get("viewers", 0), data.get("likes", 0))
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_platform_stats.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_has_three_rows
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_initial_zero
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_update_viewer_count
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_update_likes
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_twitch_color_coded
PASSED tests/nova_vt/dashboard/test_platform_stats.py::test_platform_stats_update_from_stream_stats
6 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/platform_stats.py tests/nova_vt/dashboard/test_platform_stats.py && git commit -m "feat(dashboard): add PlatformStatsWidget with color-coded viewer counts

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 7: SettingsDialog

**Files:**
- Create: `nova_vt/dashboard/settings_dialog.py`
- Create: `tests/nova_vt/dashboard/test_settings_dialog.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_settings_dialog.py`:
```python
import sys
import pytest
from unittest.mock import patch, MagicMock
from PyQt6.QtWidgets import QApplication, QTabWidget, QLineEdit, QPushButton, QComboBox
from PyQt6.QtCore import Qt
from nova_vt.dashboard.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_dialog(qtbot):
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")
    with patch("nova_vt.dashboard.settings_dialog.sounddevice") as mock_sd:
        mock_sd.query_devices.return_value = [
            {"name": "Built-in Output", "max_output_channels": 2},
            {"name": "USB Headset", "max_output_channels": 2},
        ]
        dialog = SettingsDialog(config=mock_config)
        qtbot.addWidget(dialog)
        return dialog, mock_config


def test_settings_dialog_has_four_tabs(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    tabs = dialog.findChildren(QTabWidget)
    assert len(tabs) == 1
    tab = tabs[0]
    assert tab.count() == 4
    labels = [tab.tabText(i) for i in range(tab.count())]
    assert "Twitch" in labels
    assert "YouTube" in labels
    assert "TikTok" in labels
    assert "Audio" in labels


def test_settings_dialog_twitch_tab_has_fields(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    tabs = dialog.findChildren(QTabWidget)[0]
    # Find Twitch tab index
    idx = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Twitch")
    tabs.setCurrentIndex(idx)
    assert dialog._twitch_channel is not None
    assert dialog._twitch_client_id is not None
    assert dialog._twitch_token is not None
    assert isinstance(dialog._twitch_channel, QLineEdit)


def test_settings_dialog_twitch_connect_button_exists(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._twitch_connect_btn is not None
    assert isinstance(dialog._twitch_connect_btn, QPushButton)


def test_settings_dialog_youtube_tab_has_fields(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._yt_client_secret_path is not None
    assert isinstance(dialog._yt_client_secret_path, QLineEdit)
    assert dialog._yt_auth_btn is not None


def test_settings_dialog_tiktok_tab_has_username_field(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._tiktok_username is not None
    assert isinstance(dialog._tiktok_username, QLineEdit)


def test_settings_dialog_audio_tab_has_monitor_dropdown(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    assert dialog._monitor_device_combo is not None
    assert isinstance(dialog._monitor_device_combo, QComboBox)


def test_settings_dialog_audio_monitor_dropdown_populated(qapp, qtbot):
    dialog, _ = make_dialog(qtbot)
    combo = dialog._monitor_device_combo
    device_names = [combo.itemText(i) for i in range(combo.count())]
    assert "Built-in Output" in device_names
    assert "USB Headset" in device_names


def test_settings_dialog_save_writes_config(qapp, qtbot):
    dialog, mock_config = make_dialog(qtbot)
    dialog._twitch_channel.setText("mystream")
    dialog._save()
    mock_config.set.assert_any_call("twitch", "channel", "mystream")
    mock_config.save.assert_called()


def test_settings_dialog_save_writes_token_as_secret(qapp, qtbot):
    dialog, mock_config = make_dialog(qtbot)
    dialog._twitch_token.setText("oauth:abc123")
    dialog._save()
    mock_config.set_secret.assert_any_call("twitch", "oauth_token", "oauth:abc123")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_settings_dialog.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.settings_dialog`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/settings_dialog.py`:
```python
"""SettingsDialog — Twitch/YouTube/TikTok credentials and audio preferences."""
from __future__ import annotations

from typing import Any, Optional

try:
    import sounddevice
except ImportError:  # allow import without sounddevice in test environments that mock it
    sounddevice = None  # type: ignore

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.theme import accent_button_style


class SettingsDialog(QDialog):
    """Modal dialog for configuring stream credentials and audio device."""

    def __init__(self, config: Any, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._config = config
        self.setWindowTitle("nova-vt Settings")
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_twitch_tab(), "Twitch")
        self._tabs.addTab(self._build_youtube_tab(), "YouTube")
        self._tabs.addTab(self._build_tiktok_tab(), "TikTok")
        self._tabs.addTab(self._build_audio_tab(), "Audio")
        layout.addWidget(self._tabs)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._load_config()

    # ------------------------------------------------------------------
    def _build_twitch_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._twitch_channel = QLineEdit()
        self._twitch_client_id = QLineEdit()
        self._twitch_token = QLineEdit()
        self._twitch_token.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("Channel:", self._twitch_channel)
        form.addRow("Client ID:", self._twitch_client_id)
        form.addRow("OAuth Token:", self._twitch_token)
        self._twitch_connect_btn = QPushButton("Connect")
        self._twitch_connect_btn.setStyleSheet(accent_button_style())
        form.addRow("", self._twitch_connect_btn)
        return w

    def _build_youtube_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._yt_client_secret_path = QLineEdit()
        self._yt_client_secret_path.setPlaceholderText("/path/to/client_secret.json")
        form.addRow("Client Secret JSON:", self._yt_client_secret_path)
        self._yt_auth_btn = QPushButton("Authorize via Browser")
        self._yt_auth_btn.setStyleSheet(accent_button_style())
        form.addRow("", self._yt_auth_btn)
        return w

    def _build_tiktok_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._tiktok_username = QLineEdit()
        self._tiktok_username.setPlaceholderText("@username")
        form.addRow("Username:", self._tiktok_username)
        note = QLabel("TikTok chat is read-only. RTMP push endpoint TBD.")
        note.setWordWrap(True)
        form.addRow(note)
        return w

    def _build_audio_tab(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        self._monitor_device_combo = QComboBox()
        self._populate_audio_devices()
        form.addRow("Monitor Output Device:", self._monitor_device_combo)
        return w

    def _populate_audio_devices(self) -> None:
        self._monitor_device_combo.clear()
        if sounddevice is None:
            return
        try:
            devices = sounddevice.query_devices()
            for dev in devices:
                if dev.get("max_output_channels", 0) > 0:
                    self._monitor_device_combo.addItem(dev["name"])
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _load_config(self) -> None:
        self._twitch_channel.setText(self._config.get("twitch", "channel") or "")
        self._twitch_client_id.setText(self._config.get("twitch", "client_id") or "")
        self._twitch_token.setText(self._config.get_secret("twitch", "oauth_token") or "")
        self._yt_client_secret_path.setText(self._config.get("youtube", "client_secret_path") or "")
        self._tiktok_username.setText(self._config.get("tiktok", "username") or "")
        saved_device = self._config.get("audio", "monitor_device") or ""
        if saved_device:
            idx = self._monitor_device_combo.findText(saved_device)
            if idx >= 0:
                self._monitor_device_combo.setCurrentIndex(idx)

    def _save(self) -> None:
        self._config.set("twitch", "channel", self._twitch_channel.text())
        self._config.set("twitch", "client_id", self._twitch_client_id.text())
        self._config.set_secret("twitch", "oauth_token", self._twitch_token.text())
        self._config.set("youtube", "client_secret_path", self._yt_client_secret_path.text())
        self._config.set("tiktok", "username", self._tiktok_username.text())
        self._config.set("audio", "monitor_device", self._monitor_device_combo.currentText())
        self._config.save()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_settings_dialog.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_has_four_tabs
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_twitch_tab_has_fields
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_twitch_connect_button_exists
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_youtube_tab_has_fields
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_tiktok_tab_has_username_field
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_audio_tab_has_monitor_dropdown
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_audio_monitor_dropdown_populated
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_save_writes_config
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::test_settings_dialog_save_writes_token_as_secret
9 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/settings_dialog.py tests/nova_vt/dashboard/test_settings_dialog.py && git commit -m "feat(dashboard): add SettingsDialog with OAuth and audio tabs

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 8: SceneEditorDialog

**Files:**
- Create: `nova_vt/dashboard/scene_editor.py`
- Create: `tests/nova_vt/dashboard/test_scene_editor.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_scene_editor.py`:
```python
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
    # Items are added in layer order; last added is on top in QGraphicsScene
    # We check that at least one item is at pos 0,0 (capture layer)
    positions = [(item.x(), item.y()) for item in items]
    assert (0.0, 0.0) in positions


def test_scene_editor_accept_writes_back_scene(qapp, qtbot):
    from nova_vt.dashboard.scene_editor import _SCALE
    dialog = make_dialog(qtbot)
    # Move the first _items entry (capture layer, initially at source origin 0,0)
    # by a known number of canvas pixels, then verify the source-coord rect updates.
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_scene_editor.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.scene_editor`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/scene_editor.py`:
```python
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
    """Modal scene editor. Only open when not live.

    After the user clicks OK, call get_updated_scene() to retrieve the
    modified scene dict, then save_scene(path) to persist it.
    """

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
        self._view.setRenderHint(self._view.renderHints())
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_scene_editor.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_shows_canvas
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_has_one_item_per_layer
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_items_have_correct_positions
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_accept_writes_back_scene
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_preserves_layer_types
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_title_contains_scene_name
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_empty_layers_does_not_crash
PASSED tests/nova_vt/dashboard/test_scene_editor.py::test_scene_editor_save_scene_writes_json
8 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/scene_editor.py tests/nova_vt/dashboard/test_scene_editor.py && git commit -m "feat(dashboard): add SceneEditorDialog with drag-resize layer canvas

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 5: MainWindow and Integration

### Task 9: MainWindow

**Files:**
- Create: `nova_vt/dashboard/window.py`
- Create: `tests/nova_vt/dashboard/test_main_window.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_main_window.py`:
```python
import sys
import queue
import pytest
from unittest.mock import MagicMock, patch
from PyQt6.QtWidgets import QApplication, QPushButton, QLabel
from PyQt6.QtCore import Qt
from nova_vt.dashboard.window import MainWindow, StreamState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_window(qtbot):
    """Build MainWindow with fully mocked pipeline dependencies."""
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")

    mock_mixer = MagicMock()
    mock_mixer.get_peak_level = MagicMock(return_value=0.0)

    preview_queue = queue.Queue(maxsize=2)
    scenes = ["Gameplay", "Just Chatting", "BRB"]

    window = MainWindow(
        config=mock_config,
        preview_queue=preview_queue,
        mixer=mock_mixer,
        scenes=scenes,
        start_preview_fn=MagicMock(),
        stop_preview_fn=MagicMock(),
        go_live_fn=MagicMock(),
        end_stream_fn=MagicMock(),
    )
    qtbot.addWidget(window)
    return window, preview_queue


def test_main_window_initial_state_is_idle(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert window.state == StreamState.IDLE


def test_main_window_idle_shows_preview_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert window._preview_btn.isVisible()


def test_main_window_idle_go_live_button_disabled(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert not window._go_live_btn.isEnabled()


def test_main_window_click_preview_transitions_to_previewing(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.PREVIEWING


def test_main_window_previewing_enables_go_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window._go_live_btn.isEnabled()


def test_main_window_previewing_shows_edit_scenes_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window._edit_scenes_btn.isVisible()


def test_main_window_click_go_live_transitions_to_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.LIVE


def test_main_window_live_hides_edit_scenes_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert not window._edit_scenes_btn.isVisible()


def test_main_window_live_enables_end_stream(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window._audio_mixer._end_stream_btn.isEnabled()


def test_main_window_live_indicator_shows_when_live(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window._live_indicator.isVisible()
    assert "LIVE" in window._live_indicator.text()


def test_main_window_live_indicator_hidden_when_idle(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert not window._live_indicator.isVisible()


def test_main_window_end_stream_transitions_to_idle(qapp, qtbot):
    window, fns = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    window._on_end_stream()
    assert window.state == StreamState.IDLE
    fns["end_stream"].assert_called_once()
    fns["stop_preview"].assert_called_once()


def test_main_window_calls_start_preview_fn(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    window._start_preview_fn.assert_called_once()


def test_main_window_calls_go_live_fn(qapp, qtbot):
    window, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    window._go_live_fn.assert_called_once()


def test_main_window_has_settings_button(qapp, qtbot):
    window, _ = make_window(qtbot)
    assert window._settings_btn is not None


def test_main_window_scene_switcher_has_all_scenes(qapp, qtbot):
    window, _ = make_window(qtbot)
    from PyQt6.QtWidgets import QPushButton
    buttons = window._scene_switcher.findChildren(QPushButton)
    labels = [b.text() for b in buttons]
    assert "Gameplay" in labels
    assert "Just Chatting" in labels
    assert "BRB" in labels
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_main_window.py -v 2>&1 | head -20
```

Expected output: `ImportError` for `nova_vt.dashboard.window`.

- [ ] **Step 3: Write minimal implementation**

`nova_vt/dashboard/window.py`:
```python
"""MainWindow — Studio+Chat layout, stream state machine, thread orchestration."""
from __future__ import annotations

import queue
from enum import Enum, auto
from typing import Any, Callable, Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nova_vt.dashboard.audio_mixer import AudioMixerWidget
from nova_vt.dashboard.chat_widget import ChatWidget
from nova_vt.dashboard.platform_stats import PlatformStatsWidget
from nova_vt.dashboard.preview import PreviewWidget
from nova_vt.dashboard.scene_switcher import SceneSwitcherWidget
from nova_vt.dashboard.theme import (
    COLOR_ACCENT,
    COLOR_DANGER,
    COLOR_TEXT,
    COLOR_TEXT_DIM,
    COLOR_SURFACE,
    COLOR_SURFACE_RAISED,
    accent_button_style,
    apply_theme,
)


class StreamState(Enum):
    IDLE = auto()
    PREVIEWING = auto()
    LIVE = auto()


class MainWindow(QMainWindow):
    """Top-level application window.

    Dependency-injected callbacks allow test isolation without real threads.

    Args:
        config: Config object with get/set/get_secret/set_secret/save.
        preview_queue: Bounded queue from which PreviewWidget reads frames.
        mixer: AudioMixer-compatible object (or mock).
        scenes: List of scene names to populate the scene switcher.
        start_preview_fn: Called when Preview button is clicked.
        stop_preview_fn: Called when transitioning away from preview/live.
        go_live_fn: Called when Go Live button is clicked.
        end_stream_fn: Called when END STREAM is triggered.
    """

    def __init__(
        self,
        config: Any,
        preview_queue: queue.Queue,
        mixer: Any,
        scenes: list[str],
        start_preview_fn: Callable[[], None],
        stop_preview_fn: Callable[[], None],
        go_live_fn: Callable[[], None],
        end_stream_fn: Callable[[], None],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._start_preview_fn = start_preview_fn
        self._stop_preview_fn = stop_preview_fn
        self._go_live_fn = go_live_fn
        self._end_stream_fn = end_stream_fn
        self.state = StreamState.IDLE

        self.setWindowTitle("nova-vt")
        self.setMinimumSize(1400, 820)

        apply_theme(self._qapp())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())

        content = QHBoxLayout()
        content.setContentsMargins(8, 8, 8, 8)
        content.setSpacing(8)

        left = self._build_left_panel(preview_queue, mixer, scenes)
        content.addWidget(left, stretch=3)

        right = self._build_right_panel()
        content.addWidget(right, stretch=1)

        root.addLayout(content)

        self._apply_state()

    # ------------------------------------------------------------------
    def _qapp(self):
        from PyQt6.QtWidgets import QApplication
        return QApplication.instance()

    # ------------------------------------------------------------------
    def _build_top_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet(f"background-color: {COLOR_SURFACE}; border-bottom: 1px solid #2d2d4e;")
        bar.setFixedHeight(44)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("nova-vt")
        title.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {COLOR_ACCENT}; background: transparent; border: none;")
        layout.addWidget(title)

        self._stream_timer_label = QLabel("00:00:00")
        self._stream_timer_label.setStyleSheet(f"color: {COLOR_TEXT_DIM}; background: transparent; border: none;")
        layout.addWidget(self._stream_timer_label)

        layout.addStretch()

        self._live_indicator = QLabel("● LIVE")
        self._live_indicator.setStyleSheet(f"color: {COLOR_DANGER}; font-weight: bold; background: transparent; border: none;")
        self._live_indicator.setVisible(False)
        layout.addWidget(self._live_indicator)

        self._settings_btn = QPushButton("⚙")
        self._settings_btn.setToolTip("Settings")
        self._settings_btn.setFixedSize(32, 32)
        self._settings_btn.clicked.connect(self._open_settings)
        layout.addWidget(self._settings_btn)

        # Stream timer
        self._timer_elapsed = 0
        self._stream_clock = QTimer(self)
        self._stream_clock.setInterval(1000)
        self._stream_clock.timeout.connect(self._tick_timer)

        return bar

    def _build_left_panel(self, preview_queue: queue.Queue, mixer: Any, scenes: list[str]) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # Preview
        self._preview_widget = PreviewWidget(preview_queue=preview_queue)
        layout.addWidget(self._preview_widget)

        # Preview + Go Live controls
        ctrl_row = QHBoxLayout()
        self._preview_btn = QPushButton("▶ Preview")
        self._preview_btn.setStyleSheet(accent_button_style())
        self._preview_btn.clicked.connect(self._on_preview)
        ctrl_row.addWidget(self._preview_btn)

        self._go_live_btn = QPushButton("🔴 Go Live")
        self._go_live_btn.setStyleSheet(accent_button_style())
        self._go_live_btn.setEnabled(False)
        self._go_live_btn.clicked.connect(self._on_go_live)
        ctrl_row.addWidget(self._go_live_btn)

        self._edit_scenes_btn = QPushButton("✏ Edit Scenes")
        self._edit_scenes_btn.clicked.connect(self._open_scene_editor)
        self._edit_scenes_btn.setVisible(False)
        ctrl_row.addWidget(self._edit_scenes_btn)

        ctrl_row.addStretch()
        layout.addLayout(ctrl_row)

        # Scene switcher
        self._scene_switcher = SceneSwitcherWidget(scenes=scenes)
        self._scene_switcher.scene_changed.connect(self._on_scene_changed)
        layout.addWidget(self._scene_switcher)

        # Audio mixer
        self._audio_mixer = AudioMixerWidget(mixer=mixer)
        self._audio_mixer.end_stream_requested.connect(self._on_end_stream)
        layout.addWidget(self._audio_mixer)

        return panel

    def _build_right_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        self._platform_stats = PlatformStatsWidget()
        self._platform_stats.setFixedHeight(120)
        layout.addWidget(self._platform_stats)

        self._chat_widget = ChatWidget()
        self._chat_widget.message_send_requested.connect(self._on_chat_send)
        layout.addWidget(self._chat_widget)

        return panel

    # ------------------------------------------------------------------
    def _apply_state(self) -> None:
        """Update all UI elements to reflect self.state."""
        idle = self.state == StreamState.IDLE
        previewing = self.state == StreamState.PREVIEWING
        live = self.state == StreamState.LIVE

        self._preview_btn.setVisible(idle or previewing)
        self._go_live_btn.setEnabled(previewing)
        self._edit_scenes_btn.setVisible(previewing)
        self._live_indicator.setVisible(live)
        self._audio_mixer.set_live(live)

    # ------------------------------------------------------------------
    def _on_preview(self) -> None:
        self.state = StreamState.PREVIEWING
        self._start_preview_fn()
        self._apply_state()

    def _on_go_live(self) -> None:
        self.state = StreamState.LIVE
        self._go_live_fn()
        self._timer_elapsed = 0
        self._stream_clock.start()
        self._apply_state()

    def _on_end_stream(self) -> None:
        self._stream_clock.stop()
        self._end_stream_fn()
        self._stop_preview_fn()  # full teardown: encoder + preview threads
        self.state = StreamState.IDLE
        self._apply_state()

    def _on_scene_changed(self, scene_name: str) -> None:
        # Forward scene change to compositor (injected or connected externally)
        pass

    def _on_chat_send(self, text: str, platform: str) -> None:
        # Forward to ChatManager (connected externally in main.py)
        pass

    def _tick_timer(self) -> None:
        self._timer_elapsed += 1
        h = self._timer_elapsed // 3600
        m = (self._timer_elapsed % 3600) // 60
        s = self._timer_elapsed % 60
        self._stream_timer_label.setText(f"{h:02d}:{m:02d}:{s:02d}")

    def _open_settings(self) -> None:
        from nova_vt.dashboard.settings_dialog import SettingsDialog
        dlg = SettingsDialog(config=self._config, parent=self)
        dlg.exec()

    def _open_scene_editor(self) -> None:
        # In real use, load the active scene JSON; here we open an empty editor
        from nova_vt.dashboard.scene_editor import SceneEditorDialog
        scene_data = {"name": self._scene_switcher.active_scene(), "layers": []}
        dlg = SceneEditorDialog(scene_data=scene_data, parent=self)
        if dlg.exec():
            pass  # save_scene() called by caller with path from config

    def closeEvent(self, event) -> None:
        self._preview_widget.stop()
        self._stop_preview_fn()
        super().closeEvent(event)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_main_window.py -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_initial_state_is_idle
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_idle_shows_preview_button
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_idle_go_live_button_disabled
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_click_preview_transitions_to_previewing
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_previewing_enables_go_live
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_previewing_shows_edit_scenes_button
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_click_go_live_transitions_to_live
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_live_hides_edit_scenes_button
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_live_enables_end_stream
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_live_indicator_shows_when_live
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_live_indicator_hidden_when_idle
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_end_stream_transitions_to_idle
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_calls_start_preview_fn
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_calls_go_live_fn
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_has_settings_button
PASSED tests/nova_vt/dashboard/test_main_window.py::test_main_window_scene_switcher_has_all_scenes
16 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/dashboard/window.py tests/nova_vt/dashboard/test_main_window.py && git commit -m "feat(dashboard): add MainWindow with idle/previewing/live state machine

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 6: End-to-End Smoke Test

### Task 10: End-to-end pytest-qt smoke test

**Files:**
- Create: `tests/nova_vt/dashboard/test_e2e_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/dashboard/test_e2e_smoke.py`:
```python
"""End-to-end smoke test: open MainWindow, exercise the full Preview→Live→EndStream flow.

All pipeline threads are replaced with mocks so the test needs no EGL, no
sounddevice, and no real webcam. A real numpy frame is pushed onto the
preview_queue to verify the PreviewWidget actually renders it.
"""
import sys
import queue
import time
import numpy as np
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from nova_vt.dashboard.window import MainWindow, StreamState


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication(sys.argv)
    return app


def make_window(qtbot):
    mock_config = MagicMock()
    mock_config.get = MagicMock(return_value="")
    mock_config.get_secret = MagicMock(return_value="")

    mock_mixer = MagicMock()
    mock_mixer.get_peak_level = MagicMock(return_value=0.0)

    preview_queue = queue.Queue(maxsize=4)
    scenes = ["Gameplay", "Just Chatting", "BRB", "Intro", "Ending"]

    start_preview_fn = MagicMock()
    stop_preview_fn = MagicMock()
    go_live_fn = MagicMock()
    end_stream_fn = MagicMock()

    window = MainWindow(
        config=mock_config,
        preview_queue=preview_queue,
        mixer=mock_mixer,
        scenes=scenes,
        start_preview_fn=start_preview_fn,
        stop_preview_fn=stop_preview_fn,
        go_live_fn=go_live_fn,
        end_stream_fn=end_stream_fn,
    )
    qtbot.addWidget(window)
    return window, preview_queue, {
        "start_preview": start_preview_fn,
        "stop_preview": stop_preview_fn,
        "go_live": go_live_fn,
        "end_stream": end_stream_fn,
    }


def test_e2e_full_stream_lifecycle(qapp, qtbot):
    """Full lifecycle: idle → preview → live → end stream."""
    window, preview_queue, fns = make_window(qtbot)
    window.show()

    # ── 1. Initial state ────────────────────────────────────────────────
    assert window.state == StreamState.IDLE
    assert not window._go_live_btn.isEnabled()
    assert not window._live_indicator.isVisible()

    # ── 2. Click Preview ────────────────────────────────────────────────
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.PREVIEWING
    fns["start_preview"].assert_called_once()
    assert window._go_live_btn.isEnabled()
    assert window._edit_scenes_btn.isVisible()

    # ── 3. Push a frame onto the preview queue ───────────────────────────
    frame = np.zeros((540, 960, 4), dtype=np.uint8)
    frame[:, :, 0] = 180  # red channel — distinct test pattern
    frame[:, :, 3] = 255
    preview_queue.put_nowait(frame)

    # Wait for PreviewWidget's QTimer to consume the frame
    qtbot.waitUntil(
        lambda: (
            window._preview_widget._label.pixmap() is not None
            and not window._preview_widget._label.pixmap().isNull()
        ),
        timeout=500,
    )
    pm = window._preview_widget._label.pixmap()
    assert pm.width() == 960
    assert pm.height() == 540

    # ── 4. Click Go Live ────────────────────────────────────────────────
    qtbot.mouseClick(window._go_live_btn, Qt.MouseButton.LeftButton)
    assert window.state == StreamState.LIVE
    fns["go_live"].assert_called_once()
    assert window._live_indicator.isVisible()
    assert "LIVE" in window._live_indicator.text()
    assert not window._edit_scenes_btn.isVisible()
    assert window._audio_mixer._end_stream_btn.isEnabled()

    # ── 5. Switch scene while live ──────────────────────────────────────
    from PyQt6.QtWidgets import QPushButton
    scene_buttons = window._scene_switcher.findChildren(QPushButton)
    assert len(scene_buttons) == 5
    qtbot.mouseClick(scene_buttons[1], Qt.MouseButton.LeftButton)
    assert window._scene_switcher.active_scene() == "Just Chatting"

    # ── 6. End Stream ────────────────────────────────────────────────────
    qtbot.mouseClick(window._audio_mixer._end_stream_btn, Qt.MouseButton.LeftButton)
    fns["end_stream"].assert_called_once()
    assert window.state == StreamState.IDLE
    assert not window._live_indicator.isVisible()
    assert not window._audio_mixer._end_stream_btn.isEnabled()


def test_e2e_preview_widget_handles_burst_of_frames(qapp, qtbot):
    """Push multiple frames rapidly; widget must not crash and should show latest."""
    window, preview_queue, _ = make_window(qtbot)
    window.show()
    qtbot.mouseClick(window._preview_btn, Qt.MouseButton.LeftButton)

    for i in range(10):
        frame = np.full((540, 960, 4), i * 25, dtype=np.uint8)
        frame[:, :, 3] = 255
        try:
            preview_queue.put_nowait(frame)
        except queue.Full:
            pass  # expected when queue is full — compositor drops

    qtbot.waitUntil(
        lambda: (
            window._preview_widget._label.pixmap() is not None
            and not window._preview_widget._label.pixmap().isNull()
        ),
        timeout=500,
    )
    # Widget is alive and showing something — no crash
    assert not window._preview_widget._label.pixmap().isNull()


def test_e2e_chat_message_flow(qapp, qtbot):
    """Add a chat message via the ChatWidget slot and verify it appears in the All tab."""
    from dataclasses import dataclass

    @dataclass
    class Msg:
        platform: str
        username: str
        color: str
        text: str
        event_type: str = "message"

    window, _, _ = make_window(qtbot)
    window.show()

    msg = Msg(platform="twitch", username="twitchfan", color="#9146FF", text="Hello from test!")
    window._chat_widget.add_message(msg)

    all_list = window._chat_widget._lists["All"]
    assert all_list.count() == 1
    assert "twitchfan" in all_list.item(0).text()
    assert "Hello from test!" in all_list.item(0).text()


def test_e2e_platform_stats_update(qapp, qtbot):
    """Verify PlatformStatsWidget updates propagate correctly in the full window."""
    window, _, _ = make_window(qtbot)
    window.show()

    window._platform_stats.update_from_stream_stats({
        "twitch": {"viewers": 999, "likes": 42},
        "youtube": {"viewers": 500, "likes": 10},
        "tiktok": {"viewers": 200, "likes": 888},
    })

    assert "999" in window._platform_stats._viewer_labels["twitch"].text()
    assert "888" in window._platform_stats._likes_labels["tiktok"].text()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/test_e2e_smoke.py -v 2>&1 | head -30
```

Expected output: All tests collected but failing because `nova_vt.dashboard.window` doesn't exist yet (this step runs after Task 9 is committed).

- [ ] **Step 3: No additional implementation needed**

The smoke tests exercise code implemented in Tasks 1–9. If all previous tasks pass, these should pass without further changes. If a test reveals a gap, fix the relevant widget file from that task before proceeding.

- [ ] **Step 4: Run test suite to verify all smoke tests pass**

```bash
cd /home/nova/git/nova-vt && QT_QPA_PLATFORM=offscreen pytest tests/nova_vt/dashboard/ -v
```

Expected output:
```
PASSED tests/nova_vt/dashboard/test_theme.py::...           (5 tests)
PASSED tests/nova_vt/dashboard/test_preview.py::...         (5 tests)
PASSED tests/nova_vt/dashboard/test_scene_switcher.py::...  (7 tests)
PASSED tests/nova_vt/dashboard/test_audio_mixer_widget.py:: (12 tests)
PASSED tests/nova_vt/dashboard/test_chat_widget.py::...     (11 tests)
PASSED tests/nova_vt/dashboard/test_platform_stats.py::...  (6 tests)
PASSED tests/nova_vt/dashboard/test_settings_dialog.py::... (9 tests)
PASSED tests/nova_vt/dashboard/test_scene_editor.py::...    (8 tests)
PASSED tests/nova_vt/dashboard/test_main_window.py::...     (16 tests)
PASSED tests/nova_vt/dashboard/test_e2e_smoke.py::...       (4 tests)
83 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add tests/nova_vt/dashboard/test_e2e_smoke.py && git commit -m "test(dashboard): add end-to-end smoke tests for full stream lifecycle

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Summary

| Task | Widget / File | Tests | Key Behavior |
|------|--------------|-------|--------------|
| 1 | `theme.py` | 5 | Color constants, stylesheet helpers, `apply_theme` |
| 2 | `preview.py` | 5 | QLabel + QTimer 30fps, RGBA→QPixmap, empty queue no-op |
| 3 | `scene_switcher.py` | 7 | One QPushButton per scene, `scene_changed` signal, always enabled |
| 4 | `audio_mixer.py` | 12 | 4-channel sliders, mute toggles, VU meters, END STREAM signal |
| 5 | `chat_widget.py` | 11 | 4 tabs, per-platform routing, event colors, reply send signal |
| 6 | `platform_stats.py` | 6 | Color-coded rows, viewer+likes labels, `update_from_stream_stats` |
| 7 | `settings_dialog.py` | 9 | 4 tabs, OAuth fields, sounddevice device dropdown, save to Config |
| 8 | `scene_editor.py` | 8 | QGraphicsScene canvas, drag-move items, `get_updated_scene`, `save_scene` |
| 9 | `window.py` | 16 | idle/previewing/live state machine, DI callbacks, top bar, layout wiring |
| 10 | `test_e2e_smoke.py` | 4 | Full lifecycle + frame render + chat + stats with all-mock pipeline |
