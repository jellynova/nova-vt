# nova-vt Redesign — Design Spec

**Date:** 2026-03-14
**Status:** Approved
**Scope:** Replace Godot + OBS with a self-contained Python streaming studio

---

## 1. Core Architecture

**Stack:** Python 3.12+, PyQt6, TOML config
**Pattern:** Monolithic process, one `QThread` per subsystem, `queue.Queue` for inter-thread frame passing

```
MainWindow (Qt main thread)
├── RendererThread      → produces RGBA frames (numpy)
├── TrackingThread      → produces TrackingFrame (pose + blend shapes)
├── CompositorThread    → consumes frames + tracking → produces composite RGBA
├── AudioThread         → sounddevice capture/mix → PCM chunks
└── EncoderThread       → consumes composite + audio → ffmpeg stdin → RTMP
```

Frame queues are bounded (`maxsize=2`) to apply natural backpressure — if the encoder falls behind, the compositor drops rather than buffers indefinitely.

Config lives in `~/.config/nova-vt/config.toml` (non-sensitive) and `~/.config/nova-vt/secrets.toml` (tokens/passwords, mode 600).

**App name:** nova-vt (no rename)

---

## 2. VRM Renderer

**Library:** `moderngl` (EGL headless, no display server required — native Wayland compatible)
**Model format:** VRM 0.x / 1.0 via `pygltflib`
**Skinning:** Linear Blend Skinning in numpy, per-frame on CPU (GPU upload each frame)
**Shader:** MToon toon shader implemented in GLSL (ported from VRM spec)
**Output resolution:** 1920×1080 RGBA offscreen framebuffer
**Framing:** Upper body (head + torso + arms to wrist)

Pipeline per frame:
1. Receive `PoseDict` (54 bones) + blend shape weights from TrackingThread
2. Apply LBS → update vertex buffer
3. Apply blend shapes → morph targets on GPU
4. Render to offscreen FBO → `glReadPixels` → numpy RGBA array
5. Push to CompositorThread queue

No Godot, no v4l2loopback, no virtual camera — rendering is entirely in-process.

---

## 3. Tracking

**Face:** MediaPipe `FaceLandmarker` — 52 ARKit-compatible blend shapes (eye blink, jaw open, brow raise, etc.)
**Body:** MediaPipe `PoseLandmarker` — upper-body landmarks mapped to VRM humanoid bones (neck, spine, shoulders, upper/lower arms)
**Webcam:** OpenCV `VideoCapture` with CAP_V4L2 backend, multi-path fallback (`/dev/video0`, `/dev/video1`, …)

**`TrackingProvider` protocol** — abstract interface that any tracking source implements:
```python
class TrackingProvider(Protocol):
    def get_frame(self) -> TrackingFrame: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

`TrackingFrame` carries:
- `pose: PoseDict` — 54-bone rotation dict, identity defaults
- `blend_shapes: dict[str, float]` — ARKit key → 0.0–1.0 weight
- `timestamp: float`

This protocol makes it straightforward to swap in depth cameras, VR controllers, or full-body tracking rigs later without touching the renderer or compositor.

---

## 4. Compositor

**Engine:** numpy alpha compositing (`src_alpha + dst * (1 - src_alpha)`) at 1920×1080
**Scene format:** JSON files in `~/.config/nova-vt/scenes/`

Each scene is a list of **layers** rendered back-to-front:
```json
{
  "name": "Gameplay",
  "layers": [
    {"type": "capture", "device": "/dev/video1", "rect": [0,0,1920,1080]},
    {"type": "avatar",  "rect": [1440,540,480,540]},
    {"type": "image",   "path": "overlay.png", "rect": [0,0,1920,100]}
  ]
}
```

Layer types: `capture` (capture card / webcam), `avatar` (VRM renderer output), `image` (static PNG/overlay), `browser` (future), `text`.

**Pre-set scenes:** Gameplay, Just Chatting, BRB, Intro, Ending — all editable.

**Scene editor:** Qt canvas widget (off-stream only) where layers can be dragged, resized, and reordered with mouse. Changes write back to the scene JSON immediately.

Scene switching is instant (compositor swaps the active scene JSON, no encode interruption).

---

## 5. Audio Mixer

**Library:** `sounddevice` (PortAudio bindings)
**Channels:**
| Channel | Source | Default |
|---------|--------|---------|
| Mic | selected input device | 75% |
| Game | capture card / loopback | 60% |
| BGM | file or stream | 30% |
| Master | sum of all | 90% |

Each channel has: volume (0–100), mute toggle, peak meter (exponential moving average).

Output is 48 kHz stereo PCM pushed to EncoderThread via queue. Monitor mix (what the streamer hears) is a separate mix sent back to a selected output device.

---

## 6. Encoder

**Tool:** `ffmpeg` subprocess, single encode
**Output:** Named FIFOs + `-f tee` muxer to fan out one encode to multiple RTMP destinations

```
ffmpeg -f rawvideo -pix_fmt rgba -s 1920x1080 -r 30 -i /dev/stdin \
       -f s16le -ar 48000 -ac 2 -i /dev/stdin \
       -c:v libx264 -preset veryfast -b:v 6000k \
       -c:a aac -b:a 160k \
       -f tee \
  "[f=flv]rtmp://live.twitch.tv/app/{key}|[f=flv]rtmp://a.rtmp.youtube.com/live2/{key}|[f=flv]rtmp://live-push.tiktok.com/live/{key}"
```

Streaming targets are enabled/disabled per-session — user picks which platforms to stream to before going live.

**Credentials** stored in `secrets.toml`, never logged or displayed in plaintext.

---

## 7. Dashboard UI

**Layout:** Studio + Chat (PyQt6, dark theme, purple accent `#7c3aed`)

```
┌─────────────────────────────────────┬──────────────┐
│  STREAM PREVIEW (16:9)   ● LIVE     │  ● Twitch     │
│                                     │  ● YouTube    │
│                                     │  ● TikTok     │
├──────────────────────────────────   ├───────────────│
│  [GAMEPLAY] [JUST CHATTING] [BRB].. │  All Twitch   │
├─────────────────────────────────────│  YT  TikTok   │
│  MIC──▓▓▓░  GAME──▓▓░░  BGM──▓░░░  ├───────────────│
│  MASTER─▓▓▓▓▓▓▓▓░   [⏹ END STREAM]│  chat feed    │
└─────────────────────────────────────┴───────────────┘
```

**Left panel (≈75%):**
- Stream preview — live composite at reduced res for display
- Scene switcher strip — one button per scene, active highlighted in purple
- Audio mixer row — horizontal sliders, mute buttons, peak VU meters, END STREAM button

**Right panel (≈25%):**
- Per-platform stats: viewer count + likes/subs per platform, color-coded by platform
- Chat tabs: All / Twitch / YouTube / TikTok
- Unified chat feed: platform badge, username (colored), message; sub/raid events highlighted
- Reply input + Send button (posts to all selected platforms or per-tab platform)

**Top bar:** app name · stream timer · ● LIVE indicator · settings gear

**Pre-stream state:**
- Preview button → starts VRM renderer + webcam, shows composite in preview pane (no encode)
- Settings button → opens credentials dialog (OBS legacy tab kept for compatibility, Twitch/YouTube/TikTok OAuth tabs)
- Go Live button → starts encoder, activates chat connections

---

## File Layout (target)

```
nova-vt/
├── nova_vt/
│   ├── main.py                  # entry point, MainWindow
│   ├── renderer/
│   │   ├── vrm_renderer.py      # moderngl EGL renderer
│   │   ├── vrm_loader.py        # pygltflib → mesh/skin/morph data
│   │   └── mtoon.glsl           # MToon vertex + fragment shaders
│   ├── tracking/
│   │   ├── provider.py          # TrackingProvider protocol + TrackingFrame
│   │   ├── mediapipe_tracker.py # FaceLandmarker + PoseLandmarker
│   │   └── pose_map.py          # landmark → VRM bone rotation mapping
│   ├── compositor/
│   │   ├── compositor.py        # numpy compositing engine
│   │   ├── scene.py             # scene JSON load/save/edit
│   │   └── layers.py            # layer types (capture, avatar, image, text)
│   ├── audio/
│   │   └── mixer.py             # sounddevice mixer + monitor
│   ├── encoder/
│   │   └── encoder.py           # ffmpeg subprocess + tee RTMP
│   ├── dashboard/
│   │   ├── window.py            # MainWindow (Studio+Chat layout)
│   │   ├── preview.py           # QLabel/QOpenGLWidget stream preview
│   │   ├── scene_editor.py      # drag-resize Qt canvas editor
│   │   ├── chat.py              # unified chat widget + platform tabs
│   │   └── settings_dialog.py   # credentials / preferences dialog
│   └── config.py                # TOML load/save, secrets.toml handling
├── docs/
│   └── superpowers/specs/
│       └── 2026-03-14-nova-vt-redesign-design.md
└── pyproject.toml
```

---

## Key Trade-offs & Decisions

| Decision | Why |
|----------|-----|
| EGL headless (no Godot) | Native Wayland, no XWayland popup, no v4l2loopback complexity |
| Single ffmpeg tee | One encode pass for all platforms; simpler than per-platform processes |
| CPU LBS + numpy | Keeps GPU pipeline simple (no compute shaders needed for upper-body at 30fps) |
| `TrackingProvider` protocol | Swap in depth/VR tracking without touching renderer |
| Bounded frame queues | Natural backpressure; compositor drops under load rather than OOM |
| TOML config | Human-readable, easy to hand-edit, no DB dependency |

---

## Out of Scope (this version)

- Full body tracking (legs, feet) — architecture supports it via TrackingProvider
- Hand/finger tracking — same
- Browser source layers
- Clip recording / highlight capture
- Mobile companion app
- Multi-GPU / external encoder (NVENC) — can add `-c:v h264_nvenc` to ffmpeg later
