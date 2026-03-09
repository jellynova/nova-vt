# nova-vt Setup Guide

## Prerequisites

### 1. System packages (Arch Linux)

```bash
sudo pacman -S godot obs-studio v4l2loopback-dkms python python-pip git
sudo pacman -S obs-v4l2sink  # optional: for virtual camera approach
```

### 2. Load v4l2loopback (optional)

```bash
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="nova-vt-cam" exclusive_caps=1
```

### 3. Python environment

```bash
cd ~/git/nova-vt
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### 4. Create your VRM avatar

Use VRoid Studio (available via Flatpak) to create and export `avatar.vrm`.
Place it at `avatar/avatar.vrm`.

### 5. Set up Godot project

1. Open Godot 4, create a new project at `~/git/nova-vt/avatar/`
2. Install the godot-vrm addon: https://github.com/V-Sekai/godot-vrm/releases
   - Extract and copy `addons/vrm/` to `avatar/addons/vrm/`
   - Enable in Project → Project Settings → Plugins
3. Install the GodotOSC addon: https://github.com/game-this-weekend/godot-osc
   - Copy `addons/osc/` to `avatar/addons/osc/`
   - Enable in Project Settings → Plugins
4. Import `avatar.vrm` in the FileSystem panel
5. Create `avatar/scenes/main.tscn` with this structure:
   - Node3D (Main)
     - Camera3D
     - DirectionalLight3D
     - VRMAvatar (your imported VRM scene)
     - OscReceiver (Node, attach `scripts/osc_receiver.gd`)
   - Attach `scripts/avatar_controller.gd` to VRMAvatar
   - Connect OscReceiver.face_data_received → AvatarController.apply_face_data

### 6. OBS WebSocket

In OBS → Tools → WebSocket Server Settings:
- Enable WebSocket server
- Port: 4455
- Note your password → add to `config/secrets.toml`

### 7. Twitch credentials

- Create a Twitch app at dev.twitch.tv
- Get OAuth token via twitchio docs
- Add to `config/secrets.toml`

### 8. YouTube credentials (optional)

- Create a Google Cloud project
- Enable YouTube Data API v3
- Download `client_secrets.json` to project root

### 9. Multistream setup

Install obs-multi-rtmp: https://github.com/sorayuki/obs-multi-rtmp/releases

In OBS → Tools → Multiple RTMP Outputs:
- Twitch: `rtmp://live.twitch.tv/app/YOUR_STREAM_KEY`
- YouTube: `rtmp://a.rtmp.youtube.com/live2/YOUR_STREAM_KEY`

Add stream keys to `config/secrets.toml`.
