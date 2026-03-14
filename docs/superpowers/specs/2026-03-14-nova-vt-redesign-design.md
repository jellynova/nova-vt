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
├── TrackingThread      → produces TrackingFrame (pose + blend shapes)
├── RendererThread      → consumes TrackingFrame → produces RGBA frames (numpy)
├── CompositorThread    → consumes RGBA frames → produces composite RGBA
├── AudioThread         → sounddevice capture/mix → produces PCM chunks   ┐
└── EncoderThread       → consumes composite + PCM → ffmpeg FIFOs → RTMP  ┘
```

Frame queues are bounded (`maxsize=2`) to apply natural backpressure — if the encoder falls behind, the compositor drops rather than buffers indefinitely.

A `StreamStats` dataclass (viewer counts, stream duration) is held in a thread-safe `threading.Lock`-protected shared object, updated by a `StatsPollerThread` that polls each active platform's API every 30 seconds and by chat provider events (e.g., sub/raid counts). CompositorThread reads `StreamStats` on each frame to resolve `{viewer_count}` and `{stream_time}` template variables in text layers.

Config lives in `~/.config/nova-vt/config.toml` (non-sensitive) and `~/.config/nova-vt/secrets.toml` (tokens/passwords). The app creates `secrets.toml` with mode 600 on first write and warns at startup if the file permissions are broader than that (does not refuse to start, but logs a warning).

**App name:** nova-vt (no rename)

### Thread Shutdown Protocol

Shutdown order (reverse of startup): EncoderThread → AudioThread → CompositorThread → RendererThread → TrackingThread.

Each thread's main loop checks a `threading.Event` stop flag. When a thread is told to stop:
1. The stop flag is set.
2. The thread's *input* queue is drained by pushing a sentinel (`None`) so the thread unblocks from any `queue.get()` call.
3. The thread exits its loop, cleans up resources, and emits a `finished` signal.
4. The caller waits for `finished` before stopping the next thread.

For EncoderThread specifically: after the stop flag is set, it flushes any remaining frames from its queue, writes EOF to ffmpeg's FIFO inputs, and waits for the ffmpeg subprocess to exit cleanly before returning.

If any thread raises an unhandled exception, it catches it, emits a `error(str)` signal to the main thread, sets its own stop flag, and exits. MainWindow connects all `error` signals to a handler that initiates full system shutdown and shows an error dialog.

### Preview vs. Live Modes

The system has two operating modes:

**Preview mode** (renderer + tracking + compositor running, encoder stopped): The compositor pushes frames to a `preview_queue` that the dashboard's preview widget reads via a `QTimer`. The `encoder_queue` is not created in this mode. No encode or RTMP output occurs.

**Live mode** (all threads running): The compositor pushes frames to both `preview_queue` (display) and `encoder_queue` (encode). If `encoder_queue` is full, the frame is dropped (non-blocking `put_nowait`, catch `queue.Full`). Preview continues regardless of encoder health.

Transition from preview → live starts EncoderThread and AudioThread without restarting the compositor or renderer.

---

## 2. VRM Renderer

**Library:** `moderngl` (EGL headless, no display server required — native Wayland compatible)
**Model format:** VRM 0.x targeted; VRM 1.0 supported with a compatibility shim in `vrm_loader.py` that normalises blend shape key names (VRM 0.x uses `BlendShapeProxy` with group names like `A`, `Blink`; VRM 1.0 uses `Expression` with names like `aa`, `blinkLeft`). The loader detects version from `extensions.VRM` vs `extensions.VRMC_vrm` and maps both to a unified internal `ExpressionMap` keyed by ARKit names.
**Skinning:** Linear Blend Skinning in numpy, per-frame on CPU (GPU upload each frame)
**Shader:** MToon toon shader implemented in GLSL (ported from VRM spec)
**Output resolution:** 1920×1080 RGBA offscreen framebuffer
**Framing:** Upper body (head + torso + arms to wrist)

Pipeline per frame:
1. Receive `PoseDict` (humanoid bone rotations) + `ExpressionMap` weights from TrackingThread
2. Apply LBS → update vertex buffer
3. Apply blend shapes → morph targets on GPU
4. Render to offscreen FBO → `glReadPixels` → numpy RGBA array
5. Push to CompositorThread queue (non-blocking, drop if full)

No Godot, no v4l2loopback, no virtual camera — rendering is entirely in-process.

**Rewrite note:** This replaces the existing `avatar/` Godot project entirely. The old `dashboard/components/godot.py`, `dashboard/camera.py` (AvatarCameraWorker), and `avatar/` directory will be deleted. See File Layout section.

---

## 3. Tracking

**Face:** MediaPipe `FaceLandmarker` — 52 ARKit-compatible blend shapes (eye blink, jaw open, brow raise, etc.)
**Body:** MediaPipe `PoseLandmarker` — 33 landmarks, upper-body subset (landmarks 0–22) mapped to VRM humanoid bones

**Bone mapping (`pose_map.py`):** MediaPipe produces 33 world-space landmarks. `pose_map.py` converts relevant pairs into local rotation quaternions for the following VRM bones: `neck`, `spine`, `leftShoulder`, `rightShoulder`, `leftUpperArm`, `rightUpperArm`, `leftLowerArm`, `rightLowerArm`. All other VRM humanoid bones default to identity quaternion. `PoseDict` is therefore a `dict[str, Quaternion]` with all 54 standard VRM humanoid bone names as keys, the majority of which are identity at any given frame.

**Webcam:** OpenCV `VideoCapture` with CAP_V4L2 backend, multi-path fallback (`/dev/video0`, `/dev/video1`, …)

**`TrackingProvider` protocol** — abstract interface that any tracking source implements:
```python
class TrackingProvider(Protocol):
    def get_frame(self) -> TrackingFrame: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

`TrackingFrame` carries:
- `pose: PoseDict` — `dict[str, Quaternion]`, all 54 VRM humanoid bone names, unmapped bones = identity
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
    {"type": "image",   "path": "overlay.png", "rect": [0,0,1920,100]},
    {"type": "text",    "content": "!discord", "font_size": 32, "color": "#ffffff", "rect": [20,1040,400,40]}
  ]
}
```

**Layer types:**
- `capture` — live video from capture card or webcam (`device` path, `rect`)
- `avatar` — VRM renderer output frame (`rect`)
- `image` — static PNG/JPEG overlay (`path`, `rect`, optional `opacity`)
- `text` — static or semi-dynamic text (`content`, `font_size`, `color`, `rect`); `content` may include template variables resolved by the compositor each frame from `StreamStats`:
  - `{total_viewers}` — sum across all active platforms
  - `{twitch_viewers}`, `{youtube_viewers}`, `{tiktok_viewers}` — per-platform counts (0 if platform not active)
  - `{stream_time}` — HH:MM:SS elapsed since Go Live
- `browser` — future; out of scope for this version

**Pre-set scenes:** Gameplay, Just Chatting, BRB, Intro, Ending — all editable.

**Scene editor:** Qt canvas widget available only when **not live**. While live, the Edit button is hidden. The editor lets layers be dragged, resized, and reordered with mouse. Changes write back to the scene JSON immediately. Scene *switching* (between existing scenes) is always available, live or not.

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

Output is 48 kHz stereo PCM pushed to EncoderThread via queue. Monitor mix (what the streamer hears) is a separate mix sent back to a **selected monitor output device**, configured in Settings → Audio → Monitor Output (dropdown of available PortAudio output devices). The selected device name is stored in `config.toml` as `[audio] monitor_device = "..."`.

---

## 6. Encoder

**Tool:** `ffmpeg` subprocess, single encode
**Input:** Two named FIFOs — one for video, one for audio — written by EncoderThread

```
/tmp/nova-vt-video.fifo   ← EncoderThread writes raw RGBA frames
/tmp/nova-vt-audio.fifo   ← EncoderThread writes raw PCM s16le
```

**FIFO lifecycle:** On startup, EncoderThread calls `os.unlink()` on each FIFO path (ignoring `FileNotFoundError`) then `os.mkfifo()` to create fresh FIFOs — this handles stale files from a previous crash. On shutdown, EncoderThread unlinks both FIFOs after ffmpeg exits.

**Open-order deadlock prevention:** A named FIFO blocks `open()` until both ends connect. EncoderThread opens each FIFO for writing in a separate daemon thread (one per FIFO) concurrently with launching the ffmpeg subprocess. This ensures the writer-open and reader-open happen in parallel and neither side blocks indefinitely.

ffmpeg reads from both FIFOs simultaneously:

```
ffmpeg \
  -f rawvideo -pix_fmt rgba -s 1920x1080 -r 30 -i /tmp/nova-vt-video.fifo \
  -f s16le -ar 48000 -ac 2               -i /tmp/nova-vt-audio.fifo \
  -vf format=yuv420p \
  -c:v libx264 -preset veryfast -b:v 6000k \
  -c:a aac -b:a 160k \
  -f tee \
  "[f=flv]rtmp://live.twitch.tv/app/{key}|[f=flv]rtmp://a.rtmp.youtube.com/live2/{key}|[f=flv]rtmp://TBD-tiktok-ingest/{key}"
# Note: TikTok RTMP ingest endpoint and key format must be confirmed before implementation.
# TikTok does not publish a stable public RTMP push URL; this may require using TikTok's
# Creator Studio settings or a third-party relay. Implement Twitch + YouTube first.
```

The tee output string is built at runtime from only the platforms the user has enabled for the session.

On shutdown: EncoderThread closes both FIFOs (writes EOF), then calls `ffmpeg_proc.wait(timeout=10)`. If ffmpeg does not exit within 10 seconds, it is killed.

Streaming targets are enabled/disabled per-session — user picks which platforms to stream to before going live.

**Credentials** stored in `secrets.toml`, never logged or displayed in plaintext.

---

## 7. Chat

**In scope:** Twitch IRC, YouTube Live Chat API, TikTok LIVE (unofficial WebSocket or open-source library). Each platform has a `ChatProvider` class with a consistent interface:

```python
class ChatProvider(Protocol):
    def connect(self, credentials: dict) -> None: ...
    def disconnect(self) -> None: ...
    def on_message(self, callback: Callable[[ChatMessage], None]) -> None: ...
    def send(self, text: str) -> None: ...
```

`ChatMessage` carries: `platform`, `username`, `color`, `text`, `event_type` (message / sub / raid / gift).

Chat providers run in their own threads (or asyncio tasks wrapped in a QThread) and emit messages via Qt signals to the chat widget. Reconnect is automatic with exponential backoff (max 30s). Chat is activated on Go Live and deactivated on End Stream.

**Library choices:** Twitch — `twitchio`; YouTube — `google-api-python-client` (polling); TikTok — `TikTokLive` (open source, chat reading only — RTMP push endpoint TBD separately).

**Send routing:** A `ChatManager` class holds references to all active `ChatProvider` instances. The send dispatcher signature is `ChatManager.send(text: str, platform: str | None = None)`. If `platform` is `None`, the message is sent to all active providers. If a specific platform tab is selected in the UI, its name is passed as `platform`, and only that provider's `send()` is called.

---

## 8. Dashboard UI

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
- Stream preview — composite frames displayed at 960×540 (half resolution, scaled on display by Qt). The compositor produces 1920×1080; `preview_queue` carries frames downscaled to 960×540 via numpy `[::2, ::2]` slice before queuing, keeping the preview path cheap.
- Scene switcher strip — one button per scene, active highlighted in purple. Always available (live or not).
- Audio mixer row — horizontal sliders, mute buttons, peak VU meters, END STREAM button.
- **Edit Scenes button** — visible only when **not live**. Opens the scene editor canvas in a modal dialog.

**Right panel (≈25%):**
- Per-platform stats: viewer count + likes/subs per platform, color-coded by platform.
- Chat tabs: All / Twitch / YouTube / TikTok.
- Unified chat feed: platform badge, username (colored), message; sub/raid events highlighted.
- Reply input + Send button (posts to all active platforms or the tab's platform if a specific tab is selected).

**Top bar:** app name · stream timer · ● LIVE indicator · settings gear

**Pre-stream state:**
- Preview button → starts RendererThread + TrackingThread + CompositorThread in preview mode (no encoder), shows composite in preview pane.
- Settings button → opens credentials dialog (Twitch/YouTube/TikTok OAuth tabs; Audio tab for monitor device selection).
- Go Live button → starts EncoderThread + AudioThread + chat providers, transitions to live mode.

---

## File Layout (target)

**This is a clean-slate rewrite.** The existing top-level packages (`orchestrator/`, `tracker/`, `dashboard/`, `config/`, `avatar/`, `overlays/`) will be deleted and replaced with a single `nova_vt/` package. `pyproject.toml` entry points will be updated accordingly.

```
nova-vt/
├── nova_vt/
│   ├── main.py                  # entry point, MainWindow
│   ├── config.py                # TOML load/save, secrets.toml handling
│   ├── renderer/
│   │   ├── vrm_renderer.py      # moderngl EGL renderer thread
│   │   ├── vrm_loader.py        # pygltflib → mesh/skin/morph data, VRM 0.x/1.0 compat
│   │   └── mtoon.glsl           # MToon vertex + fragment shaders
│   ├── tracking/
│   │   ├── provider.py          # TrackingProvider protocol + TrackingFrame + PoseDict
│   │   ├── mediapipe_tracker.py # FaceLandmarker + PoseLandmarker thread
│   │   └── pose_map.py          # landmark → VRM bone rotation mapping (33→54 bones)
│   ├── compositor/
│   │   ├── compositor.py        # numpy compositing engine thread
│   │   ├── scene.py             # scene JSON load/save
│   │   └── layers.py            # layer types: capture, avatar, image, text
│   ├── audio/
│   │   └── mixer.py             # sounddevice mixer + monitor thread
│   ├── encoder/
│   │   └── encoder.py           # named FIFO management + ffmpeg subprocess + tee RTMP
│   ├── chat/
│   │   ├── provider.py          # ChatProvider protocol + ChatMessage + ChatManager
│   │   ├── stats.py             # StreamStats dataclass + StatsPollerThread
│   │   ├── twitch.py            # twitchio-based provider
│   │   ├── youtube.py           # google-api polling provider
│   │   └── tiktok.py            # TikTokLive provider (chat only; RTMP TBD)
│   └── dashboard/
│       ├── window.py            # MainWindow (Studio+Chat layout), thread orchestration
│       ├── preview.py           # QLabel preview widget (960×540 display)
│       ├── scene_editor.py      # drag-resize Qt canvas editor (modal, off-stream only)
│       ├── chat_widget.py       # unified chat widget + platform tabs
│       └── settings_dialog.py   # credentials / audio preferences dialog
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
| Named FIFOs for ffmpeg input | Two separate streams (video + audio) cannot share a single stdin fd |
| CPU LBS + numpy | Keeps GPU pipeline simple (no compute shaders needed for upper-body at 30fps) |
| `TrackingProvider` protocol | Swap in depth/VR tracking without touching renderer |
| Bounded frame queues + drop | Natural backpressure; compositor drops under load rather than OOM |
| TOML config | Human-readable, easy to hand-edit, no DB dependency |
| Preview mode without encoder | Compositor feeds preview widget directly; encoder queue not created until Go Live |
| Clean-slate rewrite | Existing package boundaries don't match new architecture; migration would create more complexity than a fresh start |

---

## Out of Scope (this version)

- Full body tracking (legs, feet) — architecture supports it via TrackingProvider
- Hand/finger tracking — same
- Browser source layers (type defined, implementation deferred)
- Clip recording / highlight capture
- Mobile companion app
- Multi-GPU / external encoder (NVENC) — can add `-c:v h264_nvenc` to ffmpeg command later
- text layer template variables beyond `{total_viewers}`, `{twitch_viewers}`, `{youtube_viewers}`, `{tiktok_viewers}`, and `{stream_time}`
- TikTok RTMP push (endpoint TBD — Twitch + YouTube implemented first)
