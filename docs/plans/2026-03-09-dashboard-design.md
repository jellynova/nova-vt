# nova-vt Dashboard Design

**Date:** 2026-03-09
**Feature:** PyQt6 operator dashboard — replaces orchestrator CLI as primary entrypoint

---

## Overview

A full PyQt6 dashboard that lives on a second monitor while streaming. It manages all nova-vt components (face tracker, Godot avatar, OBS, Twitch, YouTube, overlays), shows live webcam + avatar feeds side by side, and handles OAuth login for Twitch and YouTube.

A separate `install.sh` script handles all system-level setup before first launch.

---

## Layout

```
┌─────────────────────────────────────────────────┐
│  📷 Webcam (raw)    │  🎭 Godot avatar output   │  ← ~40% height
├─────────────────────┴───────────────────────────┤
│  Tracker ●  │  OBS ●  │  Twitch ●  │  YouTube ● │
│  Godot ●    │  Overlays ●                        │  ← status pills
├─────────────────────────────────────────────────┤
│  [▶ Start Stream]  [⏹ Stop]  Scene: [Gameplay ▾]│
│  💬 Recent chat (last 8 messages)                │
└─────────────────────────────────────────────────┘
```

Status pills: green (running), amber (stopped/not configured), red (error). Clicking amber/red expands an inline fix panel.

---

## Install Script (`install.sh`)

Runs once before first launch. Does everything:

1. `sudo pacman -S godot obs-studio v4l2loopback-dkms python python-pip obs-v4l2sink`
2. `sudo modprobe v4l2loopback ...` + writes persistence config
3. `python -m venv .venv && pip install -e .`
4. Downloads `face_landmarker.task` from Google storage

After running, the dashboard launches clean with all deps present.

---

## Component Status

Each pill shows runtime state only (everything is pre-installed):

| Component | States |
|---|---|
| Face Tracker | running / stopped / error |
| Godot Avatar | running / stopped / error |
| OBS | connected / disconnected / wrong password |
| Twitch | connected / not configured / connecting |
| YouTube | connected / not configured / connecting |
| Overlays | running / stopped |

Clicking a stopped pill starts it. Clicking a "not configured" pill opens the relevant setup inline.

---

## OAuth Login Flows

### Twitch
1. Pill shows "Connect" button
2. Dialog asks for Client ID (one-time, from dev.twitch.tv)
3. Opens browser to Twitch OAuth URL
4. Temporary local server on `localhost:17563` catches redirect
5. Token saved to `config/secrets.toml`
6. Pill goes green

### YouTube
1. Pill shows "Connect" button
2. Uses `google-auth-oauthlib` local server flow
3. Opens browser to Google OAuth
4. Callback caught on `localhost:8080`
5. Token saved to `~/.config/nova-vt/youtube.token`
6. Pill goes green

Both flows show a "Waiting for browser..." spinner. Timeout after 2 minutes.

---

## Camera Feeds

Two `QLabel` widgets updated by `QThread` workers:
- **Left:** raw webcam via OpenCV (`cv2.VideoCapture`)
- **Right:** Godot avatar via v4l2loopback device (`/dev/video10`) via OpenCV

Both run at ~30fps. If a source isn't available, shows a placeholder with the device name.

---

## Theming

Reads `~/.config/nova-vt/theme.toml` on launch, hot-reloads on file change.

```toml
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
```

Falls back to Catppuccin Mocha if file absent. `theme.py` generates a QSS stylesheet from these values and calls `app.setStyleSheet(qss)`.

---

## Project Structure

```
dashboard/
├── main.py           # QApplication entry point, theme load
├── window.py         # main window layout
├── camera.py         # QThread: webcam + avatar feed workers
├── theme.py          # reads theme.toml → generates QSS
├── components/
│   ├── tracker.py    # manages tracker subprocess, emits status signals
│   ├── godot.py      # manages Godot subprocess
│   ├── obs.py        # OBS websocket (wraps obs_controller.py)
│   ├── twitch.py     # Twitch bot + OAuth flow
│   └── youtube.py    # YouTube auth + status
install.sh            # one-time system setup script
```

New entry points in `pyproject.toml`:
- `nova-vt-dashboard = "dashboard.main:main"`
- `nova-vt` (CLI) unchanged for headless use

---

## Architecture

Dashboard IS the orchestrator. Each component wrapper runs in a `QThread`, emits `status_changed(ComponentStatus)` signals to update pills. Existing `orchestrator/` code reused as-is underneath.

---

## Out of Scope (v1)

- Scene editor / OBS source management
- Chat moderation tools
- Clip recording
- Mobile companion
