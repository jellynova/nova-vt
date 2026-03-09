import pytest
from pathlib import Path
from dashboard.theme import load_theme, ThemeColors, generate_qss


def test_load_theme_returns_defaults_when_file_missing(tmp_path):
    theme = load_theme(tmp_path / "nonexistent.toml")
    assert theme.background == "#1e1e2e"  # catppuccin mocha default
    assert theme.primary == "#cba6f7"


def test_load_theme_reads_custom_colors(tmp_path):
    config = tmp_path / "theme.toml"
    config.write_text("""
[colors]
background   = "#000000"
surface      = "#111111"
primary      = "#ff0000"
secondary    = "#00ff00"
text         = "#ffffff"
text_muted   = "#888888"
success      = "#00ff00"
warning      = "#ffff00"
error        = "#ff0000"
""")
    theme = load_theme(config)
    assert theme.background == "#000000"
    assert theme.primary == "#ff0000"


def test_generate_qss_contains_colors(tmp_path):
    theme = ThemeColors()
    qss = generate_qss(theme)
    assert theme.background in qss
    assert theme.primary in qss
    assert "QMainWindow" in qss
