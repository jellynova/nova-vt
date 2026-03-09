# nova-vt

Nova's Linux-native 3D vtuber streaming toolkit.

## What This Does

- Tracks your face via webcam (MediaPipe FaceLandmarker)
- Drives a 3D VRM avatar in Godot 4 (via OSC)
- Manages OBS scenes automatically
- Shows chat + alerts as overlays
- Streams to Twitch + YouTube simultaneously

## Quick Start

1. Complete prerequisites in `docs/setup.md`
2. Copy `config/config.toml.example` → `config/config.toml`, fill in your details
3. Copy `config/secrets.toml.example` → `config/secrets.toml`, add your tokens
4. Download the MediaPipe face landmarker model:
   ```bash
   curl -L -o face_landmarker.task \
     https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
   ```

```bash
source .venv/bin/activate
python -m orchestrator.main
```

## Architecture

```
Webcam → Python (MediaPipe) → OSC → Godot 4 (VRM avatar)
                                           ↓
                               OBS (window capture + overlays)
                                           ↓
                             Twitch + YouTube (RTMP multistream)

Python orchestrator also runs: Twitch bot, alert handler, overlay WebSocket server
```

## Project Structure

- `tracker/` — MediaPipe face tracking + OSC sender
- `avatar/` — Godot 4 project with VRM avatar (GDScript)
- `orchestrator/` — Main daemon, OBS control, Twitch bot, overlay server
- `overlays/` — HTML/CSS/JS browser source overlays
- `config/` — Configuration files
- `tests/` — Python test suite
- `docs/` — Setup guides

## Running Tests

```bash
source .venv/bin/activate
pytest tests/ -v
```

## OBS Browser Sources

After `python -m orchestrator.main` is running, add in OBS:
- **Chat overlay:** `http://localhost:7778/chat.html` — 400×320 px
- **Alerts overlay:** `http://localhost:7778/alerts.html` — 800×200 px

## First Stream Checklist

- [ ] VRM avatar imported and tracking correctly in Godot
- [ ] OBS scenes configured (Gameplay, Just Chatting, BRB, Starting Soon)
- [ ] Overlays added as browser sources in OBS
- [ ] Test stream to YouTube (unlisted) completed
- [ ] Twitch stream key configured in `config/secrets.toml`
- [ ] `python -m orchestrator.main` runs cleanly
