# nova-vt Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a PyQt6 operator dashboard that replaces the CLI orchestrator as the primary nova-vt entrypoint, with live camera feeds, component status pills, OAuth login flows, and matugen theming.

**Architecture:** A `QMainWindow` with three regions (camera strip, status pills, controls + chat). Each component (tracker, Godot, OBS, Twitch, YouTube, overlays) runs in a `QThread` and emits `status_changed` signals to update its pill. Camera feeds are two `QThread` workers reading OpenCV frames and emitting `QImage` signals to `QLabel` widgets. `install.sh` handles all system setup before first launch.

**Tech Stack:** Python 3.11+, PyQt6, OpenCV, python-osc, obsws-python, twitchio, google-auth-oauthlib, websockets, tomllib (stdlib)

---

## Prerequisites

Run `install.sh` before anything else (see Task 1).

---

## Task 1: install.sh + pyproject.toml update

**Files:**
- Create: `install.sh`
- Modify: `pyproject.toml`

**Step 1: Write install.sh**

```bash
#!/usr/bin/env bash
set -e

echo "=== nova-vt installer ==="
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[1/5] Installing system packages..."
sudo pacman -S --needed --noconfirm \
    godot obs-studio v4l2loopback-dkms python python-pip git \
    obs-v4l2sink

echo "[2/5] Loading v4l2loopback..."
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="nova-vt-cam" exclusive_caps=1
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf > /dev/null
echo "options v4l2loopback devices=1 video_nr=10 card_label=nova-vt-cam exclusive_caps=1" \
    | sudo tee /etc/modprobe.d/v4l2loopback.conf > /dev/null

echo "[3/5] Setting up Python environment..."
cd "$SCRIPT_DIR"
python -m venv .venv
source .venv/bin/activate
pip install -e . --quiet

echo "[4/5] Downloading face landmarker model..."
curl -L --progress-bar -o face_landmarker.task \
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"

echo "[5/5] Creating config directory..."
mkdir -p ~/.config/nova-vt
if [ ! -f ~/.config/nova-vt/theme.toml ]; then
    cat > ~/.config/nova-vt/theme.toml << 'EOF'
[colors]
background   = "#1e1e2e"
surface      = "#313244"
primary      = "#cba6f7"
secondary    = "#89b4fa"
text         = "#cdd6f4"
text_muted   = "#6c7086"
success      = "#a6e3a1"
warning      = "#f9e2af"
error        = "#f38ba8"
EOF
    echo "Default theme written to ~/.config/nova-vt/theme.toml"
fi

echo ""
echo "=== Done! Run: source .venv/bin/activate && nova-vt-dashboard ==="
```

**Step 2: Make executable**

```bash
chmod +x install.sh
```

**Step 3: Add PyQt6 to pyproject.toml**

In `pyproject.toml`, add `"PyQt6"` to the dependencies list and a new script:

```toml
dependencies = [
    "mediapipe",
    "opencv-python",
    "python-osc",
    "obsws-python",
    "twitchio",
    "google-api-python-client",
    "google-auth-oauthlib",
    "websockets",
    "PyQt6",
    "pytest",
]

[project.scripts]
nova-vt = "orchestrator.main:main"
nova-tracker = "tracker.main:main"
nova-vt-dashboard = "dashboard.main:main"
```

**Step 4: Commit**

```bash
git add install.sh pyproject.toml
git commit -m "feat: add install.sh and PyQt6 dependency"
```

---

## Task 2: Theme System

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/theme.py`
- Create: `tests/dashboard/__init__.py`
- Create: `tests/dashboard/test_theme.py`

**Step 1: Write the failing test**

```python
# tests/dashboard/test_theme.py
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
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_theme.py -v
```

Expected: `ModuleNotFoundError: No module named 'dashboard'`

**Step 3: Write implementation**

```python
# dashboard/__init__.py
# (empty)
```

```python
# dashboard/theme.py
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
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_theme.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/ tests/dashboard/
git commit -m "feat: add dashboard theme system with matugen config support"
```

---

## Task 3: Component Base (Status Enum + Signal Base)

**Files:**
- Create: `dashboard/components/__init__.py`
- Create: `dashboard/components/base.py`
- Create: `tests/dashboard/test_base.py`

**Step 1: Write the failing test**

```python
# tests/dashboard/test_base.py
from dashboard.components.base import ComponentStatus, ComponentWorker
from PyQt6.QtCore import QCoreApplication
import sys


def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_component_status_values():
    assert ComponentStatus.RUNNING.value == "running"
    assert ComponentStatus.STOPPED.value == "stopped"
    assert ComponentStatus.NOT_CONFIGURED.value == "not_configured"
    assert ComponentStatus.ERROR.value == "error"
    assert ComponentStatus.CONNECTING.value == "connecting"


def test_component_worker_emits_status(qtbot):
    app = get_app()
    worker = ComponentWorker("test")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker._emit_status(ComponentStatus.RUNNING)
    assert statuses == [ComponentStatus.RUNNING]
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_base.py -v
```

Expected: `ModuleNotFoundError`

**Step 3: Write implementation**

```python
# dashboard/components/__init__.py
# (empty)
```

```python
# dashboard/components/base.py
from enum import Enum
from PyQt6.QtCore import QThread, pyqtSignal


class ComponentStatus(Enum):
    RUNNING       = "running"
    STOPPED       = "stopped"
    NOT_CONFIGURED = "not_configured"
    ERROR         = "error"
    CONNECTING    = "connecting"


class ComponentWorker(QThread):
    status_changed = pyqtSignal(ComponentStatus, str)  # status, message

    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.name = name
        self._status = ComponentStatus.STOPPED

    def _emit_status(self, status: ComponentStatus, message: str = ""):
        self._status = status
        self.status_changed.emit(status, message)

    @property
    def status(self) -> ComponentStatus:
        return self._status
```

**Step 4: Install pytest-qt for Qt signal testing**

```bash
source .venv/bin/activate && pip install pytest-qt --quiet
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_base.py -v
```

Expected: Both tests PASS

**Step 6: Commit**

```bash
git add dashboard/components/ tests/dashboard/test_base.py
git commit -m "feat: add ComponentStatus enum and ComponentWorker base class"
```

---

## Task 4: Tracker + Godot Component Workers

**Files:**
- Create: `dashboard/components/tracker.py`
- Create: `dashboard/components/godot.py`
- Create: `tests/dashboard/test_components.py`

**Step 1: Write the failing tests**

```python
# tests/dashboard/test_components.py
import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus

def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_tracker_worker_starts_subprocess(qtbot):
    get_app()
    from dashboard.components.tracker import TrackerWorker
    worker = TrackerWorker()
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.tracker.subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_popen.return_value = mock_proc
        worker.start_tracker()
        assert ComponentStatus.RUNNING in statuses


def test_tracker_worker_stops_cleanly(qtbot):
    get_app()
    from dashboard.components.tracker import TrackerWorker
    worker = TrackerWorker()

    with patch('dashboard.components.tracker.subprocess.Popen') as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc
        worker.start_tracker()
        worker.stop_tracker()
        mock_proc.terminate.assert_called_once()


def test_godot_worker_detects_missing_binary(qtbot):
    get_app()
    from dashboard.components.godot import GodotWorker
    worker = GodotWorker()
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.godot.shutil.which', return_value=None):
        worker.start_godot()
        assert ComponentStatus.ERROR in statuses
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_components.py -v
```

**Step 3: Write implementations**

```python
# dashboard/components/tracker.py
import subprocess
import sys
from pathlib import Path
from PyQt6.QtCore import QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus

_TRACKER_CMD = [sys.executable, "-m", "tracker.main"]
_PROJECT_ROOT = Path(__file__).parent.parent.parent


class TrackerWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("tracker", parent)
        self._proc: subprocess.Popen | None = None
        self._timer = QTimer()
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._check_health)

    def start_tracker(self):
        if self._proc and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(_TRACKER_CMD, cwd=_PROJECT_ROOT)
            self._emit_status(ComponentStatus.RUNNING, f"pid {self._proc.pid}")
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def stop_tracker(self):
        self._timer.stop()
        if self._proc:
            self._proc.terminate()
            self._proc = None
        self._emit_status(ComponentStatus.STOPPED)

    def _check_health(self):
        if self._proc and self._proc.poll() is not None:
            self._emit_status(ComponentStatus.ERROR, f"exited with {self._proc.returncode}")
            self._timer.stop()
```

```python
# dashboard/components/godot.py
import shutil
import subprocess
from pathlib import Path
from PyQt6.QtCore import QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus

_PROJECT_ROOT = Path(__file__).parent.parent.parent
_GODOT_PATH = _PROJECT_ROOT / "avatar"
_GODOT_SCENE = str(_GODOT_PATH / "scenes" / "main.tscn")


class GodotWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("godot", parent)
        self._proc: subprocess.Popen | None = None
        self._timer = QTimer()
        self._timer.setInterval(2000)
        self._timer.timeout.connect(self._check_health)

    def start_godot(self):
        if not shutil.which("godot"):
            self._emit_status(ComponentStatus.ERROR, "godot not found in PATH")
            return
        if self._proc and self._proc.poll() is None:
            return
        try:
            self._proc = subprocess.Popen(
                ["godot", "--path", str(_GODOT_PATH), _GODOT_SCENE]
            )
            self._emit_status(ComponentStatus.RUNNING, f"pid {self._proc.pid}")
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def stop_godot(self):
        self._timer.stop()
        if self._proc:
            self._proc.terminate()
            self._proc = None
        self._emit_status(ComponentStatus.STOPPED)

    def _check_health(self):
        if self._proc and self._proc.poll() is not None:
            self._emit_status(ComponentStatus.ERROR, f"exited with {self._proc.returncode}")
            self._timer.stop()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_components.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/components/tracker.py dashboard/components/godot.py tests/dashboard/test_components.py
git commit -m "feat: add tracker and godot component workers"
```

---

## Task 5: OBS Component Worker

**Files:**
- Create: `dashboard/components/obs.py`
- Create: `tests/dashboard/test_obs_component.py`

**Step 1: Write the failing test**

```python
# tests/dashboard/test_obs_component.py
import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus

def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_obs_worker_connects_successfully(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="test")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.obs.OBSController') as mock_cls:
        mock_ctrl = MagicMock()
        mock_ctrl.current_scene.return_value = "Gameplay"
        mock_cls.return_value = mock_ctrl
        worker.connect_obs()
        assert ComponentStatus.RUNNING in statuses


def test_obs_worker_emits_error_on_connection_failure(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="wrong")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.obs.OBSController', side_effect=Exception("refused")):
        worker.connect_obs()
        assert ComponentStatus.ERROR in statuses


def test_obs_worker_emits_current_scene(qtbot):
    get_app()
    from dashboard.components.obs import OBSWorker
    worker = OBSWorker(host="localhost", port=4455, password="test")
    scenes = []
    worker.scene_changed.connect(lambda s: scenes.append(s))

    with patch('dashboard.components.obs.OBSController') as mock_cls:
        mock_ctrl = MagicMock()
        mock_ctrl.current_scene.return_value = "BRB"
        mock_cls.return_value = mock_ctrl
        worker.connect_obs()
        assert "BRB" in scenes
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_obs_component.py -v
```

**Step 3: Write implementation**

```python
# dashboard/components/obs.py
from PyQt6.QtCore import pyqtSignal, QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus
from orchestrator.obs_controller import OBSController


class OBSWorker(ComponentWorker):
    scene_changed = pyqtSignal(str)

    def __init__(self, host: str, port: int, password: str, parent=None):
        super().__init__("obs", parent)
        self._host = host
        self._port = port
        self._password = password
        self._ctrl: OBSController | None = None
        self._timer = QTimer()
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._poll)

    def connect_obs(self):
        self._emit_status(ComponentStatus.CONNECTING)
        try:
            self._ctrl = OBSController(self._host, self._port, self._password)
            scene = self._ctrl.current_scene()
            self._emit_status(ComponentStatus.RUNNING, scene)
            self.scene_changed.emit(scene)
            self._timer.start()
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def switch_scene(self, scene_name: str):
        if self._ctrl:
            try:
                self._ctrl.switch_scene(scene_name)
                self.scene_changed.emit(scene_name)
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

    def disconnect_obs(self):
        self._timer.stop()
        if self._ctrl:
            self._ctrl.disconnect()
            self._ctrl = None
        self._emit_status(ComponentStatus.STOPPED)

    def _poll(self):
        if not self._ctrl:
            return
        try:
            scene = self._ctrl.current_scene()
            self.scene_changed.emit(scene)
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))
            self._timer.stop()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_obs_component.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/components/obs.py tests/dashboard/test_obs_component.py
git commit -m "feat: add OBS component worker with scene polling"
```

---

## Task 6: Twitch Component Worker + OAuth

**Files:**
- Create: `dashboard/components/twitch.py`
- Create: `tests/dashboard/test_twitch_component.py`

**Step 1: Write the failing test**

```python
# tests/dashboard/test_twitch_component.py
import sys
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus

def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_twitch_worker_not_configured_without_token(qtbot):
    get_app()
    from dashboard.components.twitch import TwitchWorker
    worker = TwitchWorker(token="", channel="", client_id="")
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker.check_config()
    assert ComponentStatus.NOT_CONFIGURED in statuses


def test_oauth_server_extracts_token():
    from dashboard.components.twitch import _extract_token_from_callback
    token = _extract_token_from_callback("/?access_token=abc123&scope=chat")
    assert token == "abc123"


def test_oauth_server_returns_none_without_token():
    from dashboard.components.twitch import _extract_token_from_callback
    token = _extract_token_from_callback("/callback")
    assert token is None
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_twitch_component.py -v
```

**Step 3: Write implementation**

```python
# dashboard/components/twitch.py
import asyncio
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from PyQt6.QtCore import pyqtSignal, QTimer
from dashboard.components.base import ComponentWorker, ComponentStatus

_OAUTH_PORT = 17563
_OAUTH_REDIRECT = f"http://localhost:{_OAUTH_PORT}/callback"
_OAUTH_SCOPES = "chat:read+chat:edit+channel:read:subscriptions+bits:read"

# Page that captures the OAuth fragment (#access_token=...) and forwards it as a query param
_CALLBACK_HTML = """<!DOCTYPE html><html><body>
<p>Connecting to nova-vt...</p>
<script>
const hash = window.location.hash.slice(1);
const params = new URLSearchParams(hash);
const token = params.get('access_token');
if (token) {
    fetch('/token?access_token=' + encodeURIComponent(token))
        .then(() => { document.body.innerHTML = '<h2>Connected! Close this tab.</h2>'; });
} else {
    document.body.innerHTML = '<h2>No token found. Try again.</h2>';
}
</script></body></html>"""


def _extract_token_from_callback(path: str) -> str | None:
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    tokens = params.get("access_token", [])
    return tokens[0] if tokens else None


class TwitchWorker(ComponentWorker):
    token_received = pyqtSignal(str)
    chat_message = pyqtSignal(str, str)  # user, message
    alert = pyqtSignal(str)              # display_text

    def __init__(self, token: str, channel: str, client_id: str, parent=None):
        super().__init__("twitch", parent)
        self._token = token
        self._channel = channel
        self._client_id = client_id
        self._bot = None
        self._bot_thread: threading.Thread | None = None

    def check_config(self):
        if not self._token or not self._channel:
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "token or channel missing")
        else:
            self._emit_status(ComponentStatus.STOPPED)

    def start_oauth(self, client_id: str):
        """Open browser OAuth flow. Emits token_received when done."""
        self._client_id = client_id
        captured = {"token": None}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/token"):
                    token = _extract_token_from_callback(self.path)
                    if token:
                        captured["token"] = token
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(_CALLBACK_HTML.encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(("localhost", _OAUTH_PORT), Handler)
        server.timeout = 120

        url = (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={_OAUTH_REDIRECT}"
            f"&response_type=token"
            f"&scope={_OAUTH_SCOPES}"
        )
        webbrowser.open(url)
        self._emit_status(ComponentStatus.CONNECTING, "waiting for browser...")

        def _serve():
            # Wait until token captured or timeout
            import time
            start = time.time()
            while not captured["token"] and time.time() - start < 120:
                server.handle_request()
            server.server_close()
            if captured["token"]:
                self.token_received.emit(captured["token"])
            else:
                self._emit_status(ComponentStatus.NOT_CONFIGURED, "OAuth timed out")

        threading.Thread(target=_serve, daemon=True).start()

    def start_bot(self):
        from orchestrator.twitch_bot import TwitchBot, AlertEvent, AlertType

        def on_alert(event: AlertEvent):
            self.alert.emit(event.display_text)
            if event.type == AlertType.CHAT:
                self.chat_message.emit(event.user, event.message)

        self._emit_status(ComponentStatus.CONNECTING, f"#{self._channel}")

        def _run():
            try:
                bot = TwitchBot(
                    token=self._token,
                    channel=self._channel,
                    on_alert=on_alert,
                )
                self._bot = bot
                asyncio.run(bot.start())
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

        self._bot_thread = threading.Thread(target=_run, daemon=True)
        self._bot_thread.start()
        self._emit_status(ComponentStatus.RUNNING, f"#{self._channel}")

    def stop_bot(self):
        if self._bot:
            asyncio.run(self._bot.close())
            self._bot = None
        self._emit_status(ComponentStatus.STOPPED)
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_twitch_component.py -v
```

Expected: All 3 tests PASS

**Step 5: Commit**

```bash
git add dashboard/components/twitch.py tests/dashboard/test_twitch_component.py
git commit -m "feat: add Twitch component worker with browser OAuth flow"
```

---

## Task 7: YouTube Component Worker + OAuth

**Files:**
- Create: `dashboard/components/youtube.py`
- Create: `tests/dashboard/test_youtube_component.py`

**Step 1: Write the failing test**

```python
# tests/dashboard/test_youtube_component.py
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from PyQt6.QtCore import QCoreApplication
from dashboard.components.base import ComponentStatus

def get_app():
    return QCoreApplication.instance() or QCoreApplication(sys.argv)


def test_youtube_worker_not_configured_without_secrets(qtbot, tmp_path):
    get_app()
    from dashboard.components.youtube import YouTubeWorker
    worker = YouTubeWorker(
        secrets_file=tmp_path / "nonexistent.json",
        token_file=tmp_path / "nonexistent.token",
    )
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))
    worker.check_config()
    assert ComponentStatus.NOT_CONFIGURED in statuses


def test_youtube_worker_running_with_valid_token(qtbot, tmp_path):
    get_app()
    from dashboard.components.youtube import YouTubeWorker
    secrets = tmp_path / "secrets.json"
    secrets.write_text("{}")
    token = tmp_path / "youtube.token"
    token.write_text("{}")

    worker = YouTubeWorker(secrets_file=secrets, token_file=token)
    statuses = []
    worker.status_changed.connect(lambda s, m: statuses.append(s))

    with patch('dashboard.components.youtube.YouTubeWorker._build_service', return_value=MagicMock()):
        worker.check_config()
        assert ComponentStatus.RUNNING in statuses
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/dashboard/test_youtube_component.py -v
```

**Step 3: Write implementation**

```python
# dashboard/components/youtube.py
import threading
import webbrowser
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from dashboard.components.base import ComponentWorker, ComponentStatus

_DEFAULT_SECRETS = Path("client_secrets.json")
_DEFAULT_TOKEN   = Path.home() / ".config" / "nova-vt" / "youtube.token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


class YouTubeWorker(ComponentWorker):
    auth_complete = pyqtSignal()

    def __init__(self, secrets_file: Path = _DEFAULT_SECRETS,
                 token_file: Path = _DEFAULT_TOKEN, parent=None):
        super().__init__("youtube", parent)
        self._secrets_file = Path(secrets_file)
        self._token_file = Path(token_file)
        self._service = None

    def check_config(self):
        if not self._secrets_file.exists():
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "client_secrets.json missing")
            return
        if not self._token_file.exists():
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "not authenticated")
            return
        try:
            self._service = self._build_service()
            self._emit_status(ComponentStatus.RUNNING, "authenticated")
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import json

        with open(self._token_file) as f:
            creds_data = json.load(f)
        creds = Credentials.from_authorized_user_info(creds_data, _SCOPES)
        return build("youtube", "v3", credentials=creds)

    def start_oauth(self):
        """Open Google OAuth flow in browser, save token."""
        if not self._secrets_file.exists():
            self._emit_status(ComponentStatus.ERROR, "client_secrets.json not found")
            return

        self._emit_status(ComponentStatus.CONNECTING, "waiting for browser...")

        def _run():
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
                import json

                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._secrets_file), _SCOPES
                )
                creds = flow.run_local_server(port=8080, open_browser=True)
                self._token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._token_file, "w") as f:
                    f.write(creds.to_json())
                self._service = self._build_service()
                self._emit_status(ComponentStatus.RUNNING, "authenticated")
                self.auth_complete.emit()
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

        threading.Thread(target=_run, daemon=True).start()
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/dashboard/test_youtube_component.py -v
```

Expected: Both tests PASS

**Step 5: Commit**

```bash
git add dashboard/components/youtube.py tests/dashboard/test_youtube_component.py
git commit -m "feat: add YouTube component worker with OAuth flow"
```

---

## Task 8: Camera Feed Workers

**Files:**
- Create: `dashboard/camera.py`

**Note:** No unit test — OpenCV capture is hardware-bound. Verified via manual smoke test at end.

**Step 1: Write implementation**

```python
# dashboard/camera.py
import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal, Qt
from PyQt6.QtGui import QImage, QPixmap


def _frame_to_qimage(frame: np.ndarray) -> QImage:
    h, w, ch = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    return QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()


class CameraWorker(QThread):
    frame_ready = pyqtSignal(QImage)

    def __init__(self, device_index: int | str, fps: int = 30, parent=None):
        super().__init__(parent)
        self._device = device_index
        self._fps = fps
        self._running = False

    def run(self):
        self._running = True
        cap = cv2.VideoCapture(self._device)
        cap.set(cv2.CAP_PROP_FPS, self._fps)
        while self._running:
            ret, frame = cap.read()
            if ret:
                self.frame_ready.emit(_frame_to_qimage(frame))
            else:
                self.msleep(100)
        cap.release()

    def stop(self):
        self._running = False
        self.wait(2000)


class WebcamWorker(CameraWorker):
    """Raw webcam feed."""
    def __init__(self, device_index: int = 0, parent=None):
        super().__init__(device_index, fps=30, parent=parent)


class AvatarCameraWorker(CameraWorker):
    """Godot avatar via v4l2loopback virtual camera."""
    def __init__(self, device: str = "/dev/video10", parent=None):
        super().__init__(device, fps=30, parent=parent)
```

**Step 2: Commit**

```bash
git add dashboard/camera.py
git commit -m "feat: add camera feed workers for webcam and avatar virtual cam"
```

---

## Task 9: Main Window

**Files:**
- Create: `dashboard/window.py`

**Note:** UI code — verified visually. No unit test.

**Step 1: Write implementation**

```python
# dashboard/window.py
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QComboBox, QScrollArea,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, pyqtSlot, QSize
from PyQt6.QtGui import QPixmap, QImage

from dashboard.components.base import ComponentStatus
from dashboard.camera import WebcamWorker, AvatarCameraWorker


_STATUS_STYLE = {
    ComponentStatus.RUNNING:        ("●", "#a6e3a1"),
    ComponentStatus.STOPPED:        ("●", "#6c7086"),
    ComponentStatus.NOT_CONFIGURED: ("●", "#f9e2af"),
    ComponentStatus.ERROR:          ("●", "#f38ba8"),
    ComponentStatus.CONNECTING:     ("◌", "#89b4fa"),
}

_SCENES = ["Gameplay", "Just Chatting", "BRB", "Starting Soon"]


class StatusPill(QFrame):
    def __init__(self, name: str, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        self._dot = QLabel("●")
        self._label = QLabel(name)
        self._msg = QLabel("")
        self._msg.setObjectName("pill-msg")

        for w in (self._dot, self._label, self._msg):
            layout.addWidget(w)

        self.update_status(ComponentStatus.STOPPED)

    def update_status(self, status: ComponentStatus, message: str = ""):
        dot, color = _STATUS_STYLE[status]
        self._dot.setText(dot)
        self._dot.setStyleSheet(f"color: {color};")
        self._msg.setText(f"({message})" if message else "")


class CameraPane(QLabel):
    def __init__(self, placeholder: str, parent=None):
        super().__init__(parent)
        self.setText(placeholder)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(QSize(320, 240))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("border-radius: 8px;")

    @pyqtSlot(QImage)
    def update_frame(self, image: QImage):
        self.setPixmap(
            QPixmap.fromImage(image).scaled(
                self.size(),
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )


class NovaVTWindow(QMainWindow):
    def __init__(self, config, obs_worker, twitch_worker, youtube_worker,
                 tracker_worker, godot_worker, overlay_worker, theme):
        super().__init__()
        self.setWindowTitle("nova-vt")
        self.resize(1280, 720)

        self._obs = obs_worker
        self._twitch = twitch_worker
        self._youtube = youtube_worker
        self._tracker = tracker_worker
        self._godot = godot_worker
        self._overlay = overlay_worker

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(8)
        root.setContentsMargins(12, 12, 12, 12)

        # --- Camera strip ---
        cam_row = QHBoxLayout()
        self._webcam_pane = CameraPane("📷  Webcam (no camera)")
        self._avatar_pane = CameraPane("🎭  Avatar (Godot not running)")
        cam_row.addWidget(self._webcam_pane)
        cam_row.addWidget(self._avatar_pane)
        root.addLayout(cam_row, stretch=4)

        # --- Status pills ---
        pills_row = QHBoxLayout()
        self._pills = {
            "tracker":  StatusPill("Tracker"),
            "godot":    StatusPill("Godot"),
            "obs":      StatusPill("OBS"),
            "twitch":   StatusPill("Twitch"),
            "youtube":  StatusPill("YouTube"),
            "overlays": StatusPill("Overlays"),
        }
        for pill in self._pills.values():
            pills_row.addWidget(pill)
        pills_row.addStretch()
        root.addLayout(pills_row)

        # --- Controls ---
        ctrl_row = QHBoxLayout()
        self._btn_start = QPushButton("▶  Start Stream")
        self._btn_stop  = QPushButton("⏹  Stop")
        self._scene_box = QComboBox()
        self._scene_box.addItems(_SCENES)

        for w in (self._btn_start, self._btn_stop, QLabel("Scene:"), self._scene_box):
            ctrl_row.addWidget(w)
        ctrl_row.addStretch()
        root.addLayout(ctrl_row)

        # --- Chat feed ---
        self._chat_list = QScrollArea()
        self._chat_widget = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_widget)
        self._chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._chat_list.setWidget(self._chat_widget)
        self._chat_list.setWidgetResizable(True)
        root.addWidget(self._chat_list, stretch=2)

        self._connect_signals()
        self._start_cameras()

    def _connect_signals(self):
        self._btn_start.clicked.connect(self._on_start)
        self._btn_stop.clicked.connect(self._on_stop)
        self._scene_box.currentTextChanged.connect(self._on_scene_changed)

        for name, worker in [
            ("tracker", self._tracker),
            ("godot",   self._godot),
            ("obs",     self._obs),
            ("twitch",  self._twitch),
            ("youtube", self._youtube),
            ("overlays", self._overlay),
        ]:
            pill = self._pills[name]
            worker.status_changed.connect(
                lambda s, m, p=pill: p.update_status(s, m)
            )

        self._twitch.chat_message.connect(self._on_chat_message)

    def _start_cameras(self):
        self._webcam = WebcamWorker(device_index=0)
        self._webcam.frame_ready.connect(self._webcam_pane.update_frame)
        self._webcam.start()

        self._avatar_cam = AvatarCameraWorker()
        self._avatar_cam.frame_ready.connect(self._avatar_pane.update_frame)
        self._avatar_cam.start()

    def _on_start(self):
        self._tracker.start_tracker()
        self._godot.start_godot()
        self._obs.connect_obs()
        if self._twitch.status != ComponentStatus.RUNNING:
            self._twitch.start_bot()

    def _on_stop(self):
        self._tracker.stop_tracker()
        self._godot.stop_godot()
        self._obs.disconnect_obs()
        self._twitch.stop_bot()

    def _on_scene_changed(self, scene_name: str):
        self._obs.switch_scene(scene_name)

    @pyqtSlot(str, str)
    def _on_chat_message(self, user: str, message: str):
        label = QLabel(f"<b>{user}</b>: {message}")
        label.setWordWrap(True)
        self._chat_layout.insertWidget(0, label)
        # Keep last 20 messages
        while self._chat_layout.count() > 20:
            item = self._chat_layout.takeAt(self._chat_layout.count() - 1)
            if item.widget():
                item.widget().deleteLater()

    def closeEvent(self, event):
        self._webcam.stop()
        self._avatar_cam.stop()
        self._on_stop()
        super().closeEvent(event)
```

**Step 2: Commit**

```bash
git add dashboard/window.py
git commit -m "feat: add main dashboard window with camera panes, status pills, and controls"
```

---

## Task 10: Dashboard Entry Point + Overlay Worker

**Files:**
- Create: `dashboard/components/overlays.py`
- Create: `dashboard/main.py`

**Step 1: Write overlay worker**

```python
# dashboard/components/overlays.py
import asyncio
import threading
from dashboard.components.base import ComponentWorker, ComponentStatus


class OverlayWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("overlays", parent)
        self._server = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start_overlays(self):
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                from orchestrator.overlay_server import start_overlay_server
                server_coro = self._loop.run_until_complete(start_overlay_server())
                self._server = server_coro
                self._emit_status(ComponentStatus.RUNNING, "http://localhost:7778")
                self._loop.run_forever()
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop_overlays(self):
        if self._server:
            self._server.close()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._emit_status(ComponentStatus.STOPPED)
```

**Step 2: Write entry point**

```python
# dashboard/main.py
import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QFileSystemWatcher

from dashboard.theme import load_theme, generate_qss
from dashboard.window import NovaVTWindow
from dashboard.components.tracker import TrackerWorker
from dashboard.components.godot import GodotWorker
from dashboard.components.obs import OBSWorker
from dashboard.components.twitch import TwitchWorker
from dashboard.components.youtube import YouTubeWorker
from dashboard.components.overlays import OverlayWorker
from orchestrator.config import load_config

_THEME_PATH = Path.home() / ".config" / "nova-vt" / "theme.toml"


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("nova-vt")

    # Load theme
    theme = load_theme(_THEME_PATH)
    app.setStyleSheet(generate_qss(theme))

    # Hot-reload theme on file change
    watcher = QFileSystemWatcher([str(_THEME_PATH)])
    def _reload_theme(path):
        t = load_theme(Path(path))
        app.setStyleSheet(generate_qss(t))
    watcher.fileChanged.connect(_reload_theme)

    # Load config
    config = load_config()

    # Create workers
    tracker  = TrackerWorker()
    godot    = GodotWorker()
    obs      = OBSWorker(config.obs_host, config.obs_port, config.obs_password)
    twitch   = TwitchWorker(config.twitch_token, config.twitch_channel, config.twitch_client_id)
    youtube  = YouTubeWorker()
    overlays = OverlayWorker()

    # Initial status checks
    twitch.check_config()
    youtube.check_config()

    # Start overlay server immediately
    overlays.start_overlays()

    # Build and show window
    window = NovaVTWindow(config, obs, twitch, youtube, tracker, godot, overlays, theme)
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

**Step 3: Run full test suite to verify nothing broken**

```bash
pytest tests/ -v
```

Expected: All tests PASS

**Step 4: Smoke test the dashboard**

```bash
source .venv/bin/activate
pip install PyQt6 --quiet
nova-vt-dashboard
```

Expected: Dashboard window opens, theme applied, camera panes show placeholders (no camera attached), all pills show grey/amber.

**Step 5: Commit**

```bash
git add dashboard/components/overlays.py dashboard/main.py
git commit -m "feat: add overlay worker and dashboard entry point — wires all components"
```

---

## Done!

Full test suite should pass. The dashboard launches with `nova-vt-dashboard` (or `python -m dashboard.main`).

**First-time setup checklist:**
- [ ] Run `./install.sh` once
- [ ] Set up `config/config.toml` with your channel name
- [ ] Click Twitch pill → Connect → browser opens
- [ ] Click YouTube pill → Connect → browser opens
- [ ] Click **▶ Start Stream** — all pills go green
- [ ] Add OBS browser sources: `http://localhost:7778/chat.html` + `alerts.html`
