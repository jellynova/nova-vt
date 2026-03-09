from dataclasses import dataclass
from pathlib import Path
import tomllib

_DEFAULT_THEME_PATH = Path.home() / ".config" / "nova-vt" / "theme.toml"

CATPPUCCIN_MOCHA = {
    "background": "#1e1e2e",
    "surface":    "#313244",
    "primary":    "#cba6f7",
    "secondary":  "#89b4fa",
    "text":       "#cdd6f4",
    "text_muted": "#6c7086",
    "success":    "#a6e3a1",
    "warning":    "#f9e2af",
    "error":      "#f38ba8",
}


@dataclass
class ThemeColors:
    background: str = CATPPUCCIN_MOCHA["background"]
    surface:    str = CATPPUCCIN_MOCHA["surface"]
    primary:    str = CATPPUCCIN_MOCHA["primary"]
    secondary:  str = CATPPUCCIN_MOCHA["secondary"]
    text:       str = CATPPUCCIN_MOCHA["text"]
    text_muted: str = CATPPUCCIN_MOCHA["text_muted"]
    success:    str = CATPPUCCIN_MOCHA["success"]
    warning:    str = CATPPUCCIN_MOCHA["warning"]
    error:      str = CATPPUCCIN_MOCHA["error"]


def load_theme(path: Path | None = None) -> ThemeColors:
    p = path or _DEFAULT_THEME_PATH
    if not p.exists():
        return ThemeColors()
    try:
        with open(p, "rb") as f:
            raw = tomllib.load(f)
        c = raw.get("colors", {})
        return ThemeColors(**{k: c.get(k, v) for k, v in CATPPUCCIN_MOCHA.items()})
    except Exception:
        return ThemeColors()


def generate_qss(t: ThemeColors) -> str:
    return f"""
QMainWindow, QWidget {{
    background-color: {t.background};
    color: {t.text};
    font-family: 'Inter', 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QLabel {{
    color: {t.text};
}}
QPushButton {{
    background-color: {t.surface};
    color: {t.text};
    border: 1px solid {t.primary};
    border-radius: 6px;
    padding: 6px 14px;
}}
QPushButton:hover {{
    background-color: {t.primary};
    color: {t.background};
}}
QPushButton:disabled {{
    opacity: 0.4;
}}
QComboBox {{
    background-color: {t.surface};
    color: {t.text};
    border: 1px solid {t.text_muted};
    border-radius: 4px;
    padding: 4px 8px;
}}
QScrollArea, QListWidget {{
    background-color: {t.surface};
    border: none;
}}
.pill-green  {{ background-color: {t.success};  color: {t.background}; border-radius: 10px; padding: 3px 10px; }}
.pill-amber  {{ background-color: {t.warning};  color: {t.background}; border-radius: 10px; padding: 3px 10px; }}
.pill-red    {{ background-color: {t.error};    color: {t.background}; border-radius: 10px; padding: 3px 10px; }}
.pill-grey   {{ background-color: {t.text_muted}; color: {t.background}; border-radius: 10px; padding: 3px 10px; }}
.section-bg  {{ background-color: {t.surface}; border-radius: 8px; padding: 8px; }}
"""
