# Virtual Camera Setup

nova-vt can feed the Godot avatar into OBS in two ways:

## Option A: OBS Window Capture (Recommended for v1)

1. In Godot, run the avatar scene (it opens a window)
2. In OBS, add a **Window Capture** source
3. Select the Godot window
4. Crop to show only the avatar (right-click → Filters → Crop)

No extra setup needed. Works immediately.

## Option B: v4l2loopback Virtual Camera

For a proper virtual camera that appears in `/dev/video10`:

### Prerequisites

```bash
sudo pacman -S v4l2loopback-dkms
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="nova-vt-cam" exclusive_caps=1
```

For persistence, create `/etc/modules-load.d/v4l2loopback.conf`:
```
v4l2loopback
```

And `/etc/modprobe.d/v4l2loopback.conf`:
```
options v4l2loopback devices=1 video_nr=10 card_label="nova-vt-cam" exclusive_caps=1
```

### Verify

```bash
v4l2-ctl --list-devices
# Should show: nova-vt-cam (/dev/video10)
```

### In OBS

Add a **Video Capture Device** source and select `nova-vt-cam`.

## Full ffmpeg Pipe Approach

The `virtual_camera.gd` script skeleton is in `avatar/scripts/virtual_camera.gd`.
Full implementation pipes SubViewport pixel data via ffmpeg to the v4l2 device.
This requires Godot 4's `RenderingServer` API for frame capture.
