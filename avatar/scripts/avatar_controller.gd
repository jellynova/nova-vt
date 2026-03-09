# avatar/scripts/avatar_controller.gd
# Controls VRM avatar blendshapes and bone rotations from face tracking data.
# Attach to the VRMAvatar node in main.tscn.
# Set vrm_root export to the VRM root node containing BlendShapeProxy.
extends Node3D

@export var vrm_root: Node3D

var _blend_shape_proxy  # VRMBlendShapeProxy

func _ready():
	if vrm_root:
		_blend_shape_proxy = vrm_root.get_node_or_null("BlendShapeProxy")

func apply_face_data(param: String, value: float):
	match param:
		"HeadYaw":
			vrm_root.rotation_degrees.y = value
		"HeadPitch":
			vrm_root.rotation_degrees.x = value
		"HeadRoll":
			vrm_root.rotation_degrees.z = value
		"MouthOpen":
			_set_blend("aa", value)
		"BlinkLeft":
			_set_blend("blink_l", value)
		"BlinkRight":
			_set_blend("blink_r", value)
		"BrowLeft", "BrowRight":
			pass  # extend in v2

func _set_blend(shape: String, value: float):
	if _blend_shape_proxy:
		_blend_shape_proxy.set(shape, clampf(value, 0.0, 1.0))
