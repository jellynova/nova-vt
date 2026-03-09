# nova-vt Design Document

**Date:** 2026-03-09
**Project:** nova-vt — Linux-native 3D vtuber streaming toolkit
**Streamer:** Nova
**Game:** Pokopia (and future titles)

---

## Overview

A fully Linux-native vtuber streaming toolkit that connects webcam face tracking to a 3D avatar and streams to Twitch + YouTube simultaneously. Built around three coordinating components: a Python orchestrator, a Godot 3D avatar renderer, and OBS for output.

---

## Architecture

```
[Webcam] → [Python: MediaPipe face tracker]
                    ↓ OSC (python-osc)
           [Godot 4: 3D avatar renderer + VRM model]
                    ↓ Virtual Camera (v4l2loopback)
           [OBS: scene management + multistream output]
                    ↑ obs-websocket
           [Python: orchestrator daemon]
           ├── Scene switching logic
           ├── Twitch chat bot (alerts, reactions)
           └── YouTube chat bot
```

---

## Components

### 1. Face Tracker (`tracker/`)
- **MediaPipe FaceMesh** — 468-point face landmark detection
- **Head pose estimation** — pitch/yaw/roll from landmarks
- **Expression detection** — blink, mouth open, brow raise, etc.
- Sends data to Godot via **OSC protocol** (standard in vtubing)
- Runs as a Python process, ~30fps tracking

### 2. Avatar Renderer (`avatar/`)
- **Godot 4** project with `godot-vrm` plugin
- Loads a `.vrm` file (created in VRoid Studio)
- Receives OSC messages → drives VRM blendshapes + bone rotations
- Outputs via **v4l2loopback** virtual camera to OBS
- Headless rendering mode for performance

### 3. Orchestrator (`orchestrator/`)
- Python daemon that coordinates everything
- **obs-websocket-py** — scene switching, source control
- **Twitch IRC bot** — chat overlay, sub/follow alerts, avatar reactions
- **YouTube Live API** — chat reading for multistream
- Config-driven scene definitions (gameplay, just-chatting, BRB, starting-soon)

### 4. Overlays (`overlays/`)
- HTML/CSS/JS pages loaded as OBS browser sources
- Chat overlay, alert box, stream info panels
- Themed to match avatar aesthetic

---

## Tech Stack

| Component | Technology |
|---|---|
| Face tracking | Python 3 + MediaPipe |
| Tracker → Avatar bridge | OSC (python-osc / Godot OSC plugin) |
| 3D avatar rendering | Godot 4 + godot-vrm |
| Avatar model format | VRM (created in VRoid Studio) |
| Virtual camera | v4l2loopback kernel module |
| Stream management | OBS Studio |
| OBS automation | obs-websocket + obs-websocket-py |
| Chat bots | twitchio (Twitch) + YouTube Data API |
| Multistreaming | RTMP to Twitch + YouTube simultaneously |
| Overlays | HTML/CSS/JS browser sources |

---

## Project Structure

```
nova-vt/
├── tracker/          # MediaPipe face tracking
├── avatar/           # Godot 4 project + VRM
├── orchestrator/     # Python daemon
├── overlays/         # HTML overlay pages
├── config/           # Stream scenes, alert config
├── docs/             # Setup guides
└── README.md
```

---

## Key Design Decisions

- **OSC as the bridge** — industry standard, clean separation, easy to debug
- **Godot over web** — lower latency, native Linux, more control over rendering
- **Python orchestrator** — flexible glue; chat bots, alerts, and OBS control in one place
- **HTML overlays** — easiest to style and update without touching Godot or Python

---

## Success Criteria

- [ ] Avatar tracks face in real-time with <100ms latency
- [ ] Avatar visible in OBS as a virtual camera source
- [ ] Streaming simultaneously to Twitch and YouTube
- [ ] Chat messages appear in overlay
- [ ] Follow/sub alerts trigger on screen
- [ ] Scene switching works (gameplay → just-chatting → BRB)

---

## Out of Scope (v1)

- Body / hand tracking
- AI chat interaction
- VR headset support
- Mobile companion app
