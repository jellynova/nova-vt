# avatar/scripts/virtual_camera.gd
# Pipes avatar viewport frames to v4l2loopback virtual camera via ffmpeg.
# See docs/virtual-camera-setup.md for full setup instructions.
# Recommended for v1: use OBS Window Capture pointed at the Godot window instead.
extends Node

const DEVICE = "/dev/video10"
const WIDTH = 1280
const HEIGHT = 720

func _ready():
	print("[nova-vt] Virtual camera: targeting ", DEVICE)
	print("[nova-vt] Tip: For v1, use OBS Window Capture on the Godot window instead.")
	# Full ffmpeg pipe approach: see docs/virtual-camera-setup.md
