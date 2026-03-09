# avatar/scripts/main.gd
# Nova-VT avatar scene. Loads VRM via GLTF and drives head rotation + mouth/blink
# from face tracker OSC data on port 9000. No Godot editor import needed.
extends Node

const VRM_PATH := "res://model.vrm"
const OSC_PORT := 9000

var _udp := PacketPeerUDP.new()
var _skeleton: Skeleton3D
var _head_bone_idx: int = -1
var _head_rotation := Vector3.ZERO   # degrees: pitch, yaw, roll

# Morph targets (GLTF blend shapes) keyed by mesh node
var _meshes: Array[MeshInstance3D] = []
# Map morph name → [mesh_idx, shape_idx] for fast lookup
var _morph_map: Dictionary = {}


func _ready() -> void:
	_setup_lighting()
	_setup_camera()
	_load_avatar()
	_udp.bind(OSC_PORT)
	print("[nova-vt] OSC listening on port ", OSC_PORT)


func _setup_lighting() -> void:
	var world_env := WorldEnvironment.new()
	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.118, 0.118, 0.176)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color.WHITE
	env.ambient_light_energy = 0.7
	world_env.environment = env
	add_child(world_env)

	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-40, 30, 0)
	light.light_energy = 1.2
	add_child(light)


func _setup_camera() -> void:
	var cam := Camera3D.new()
	cam.position = Vector3(0.0, 1.4, 1.5)
	cam.look_at(Vector3(0.0, 1.3, 0.0))
	add_child(cam)


func _load_avatar() -> void:
	if not FileAccess.file_exists(VRM_PATH):
		push_error("[nova-vt] VRM not found at: " + VRM_PATH)
		return

	var doc := GLTFDocument.new()
	var state := GLTFState.new()
	var path := ProjectSettings.globalize_path(VRM_PATH)
	var err := doc.append_from_file(path, state)
	if err != OK:
		push_error("[nova-vt] Failed to load VRM (error %d)" % err)
		return

	var avatar := doc.generate_scene(state)
	add_child(avatar)

	# Find skeleton for head bone rotation
	_skeleton = _find_typed(avatar, "Skeleton3D") as Skeleton3D
	if _skeleton:
		_head_bone_idx = _skeleton.find_bone("Head")
		print("[nova-vt] Head bone index: ", _head_bone_idx)
	else:
		push_warning("[nova-vt] No Skeleton3D found — head rotation disabled")

	# Index all blend shapes for mouth/blink
	_index_morphs(avatar)
	print("[nova-vt] Avatar ready. Morphs found: ", _morph_map.keys())


func _index_morphs(root: Node) -> void:
	for node in _collect_typed(root, "MeshInstance3D"):
		var mesh := node as MeshInstance3D
		if not mesh.mesh:
			continue
		var count := mesh.get_blend_shape_count()
		for i in count:
			var shape_name := mesh.mesh.get_blend_shape_name(i).to_lower()
			_morph_map[shape_name] = [_meshes.size(), i]
		_meshes.append(mesh)


func _process(_delta: float) -> void:
	while _udp.get_available_packet_count() > 0:
		var msg := _parse_osc(_udp.get_packet())
		if not msg.is_empty():
			_apply(msg.param, msg.value)


func _parse_osc(data: PackedByteArray) -> Dictionary:
	if data.size() < 8:
		return {}

	# Read null-terminated address string, then pad to 4-byte boundary
	var offset := 0
	var addr := ""
	while offset < data.size() and data[offset] != 0:
		addr += char(data[offset])
		offset += 1
	offset = (offset | 3) + 1

	# Read type tag string (starts with ',')
	if offset >= data.size() or char(data[offset]) != ",":
		return {}
	offset += 1
	var types := ""
	while offset < data.size() and data[offset] != 0:
		types += char(data[offset])
		offset += 1
	offset = (offset | 3) + 1

	# Read single float argument (big-endian)
	if types.begins_with("f") and offset + 4 <= data.size():
		var ba := PackedByteArray([
			data[offset + 3], data[offset + 2],
			data[offset + 1], data[offset]
		])
		return {
			"param": addr.replace("/avatar/parameters/", ""),
			"value": ba.decode_float(0),
		}
	return {}


func _apply(param: String, value: float) -> void:
	match param:
		"HeadYaw":
			_head_rotation.y = -value
			_update_head_bone()
		"HeadPitch":
			_head_rotation.x = value
			_update_head_bone()
		"HeadRoll":
			_head_rotation.z = -value
			_update_head_bone()
		"MouthOpen":
			_set_morph_any(["aa", "a", "mouthopen"], clampf(value, 0.0, 1.0))
		"BlinkLeft":
			_set_morph_any(["blink_l", "blink.l", "blinkleft"], clampf(value, 0.0, 1.0))
		"BlinkRight":
			_set_morph_any(["blink_r", "blink.r", "blinkright"], clampf(value, 0.0, 1.0))


func _update_head_bone() -> void:
	if not _skeleton or _head_bone_idx < 0:
		return
	var euler := Vector3(
		deg_to_rad(_head_rotation.x),
		deg_to_rad(_head_rotation.y),
		deg_to_rad(_head_rotation.z),
	)
	_skeleton.set_bone_pose_rotation(_head_bone_idx, Quaternion.from_euler(euler))


func _set_morph_any(candidates: Array, value: float) -> void:
	for name in candidates:
		if _morph_map.has(name):
			var entry: Array = _morph_map[name]
			_meshes[entry[0]].set_blend_shape_value(entry[1], value)
			return


# --- Helpers ---

func _find_typed(root: Node, class_name_str: String) -> Node:
	if root.get_class() == class_name_str:
		return root
	for child in root.get_children():
		var result := _find_typed(child, class_name_str)
		if result:
			return result
	return null


func _collect_typed(root: Node, class_name_str: String) -> Array:
	var results := []
	if root.get_class() == class_name_str:
		results.append(root)
	for child in root.get_children():
		results.append_array(_collect_typed(child, class_name_str))
	return results


func _exit_tree() -> void:
	_udp.close()
