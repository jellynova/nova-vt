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
