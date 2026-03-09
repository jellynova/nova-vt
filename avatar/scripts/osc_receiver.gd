# avatar/scripts/osc_receiver.gd
# Receives OSC messages from the Python face tracker and emits face_data_received signal.
# Requires the GodotOSC addon: https://github.com/game-this-weekend/godot-osc
# Enable in Project Settings → Plugins after copying addons/osc/ to avatar/addons/osc/
extends Node

signal face_data_received(data: Dictionary)

var _osc_server: OSCServer
const PORT = 9000

func _ready():
	_osc_server = OSCServer.new()
	_osc_server.connect("message_received", _on_message)
	_osc_server.listen(PORT)
	print("[nova-vt] OSC receiver listening on port ", PORT)

func _on_message(address: String, args: Array):
	var param_name = address.replace("/avatar/parameters/", "")
	emit_signal("face_data_received", {param_name: args[0]})

func _exit_tree():
	_osc_server.stop()
