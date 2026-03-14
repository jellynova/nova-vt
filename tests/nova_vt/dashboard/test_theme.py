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
