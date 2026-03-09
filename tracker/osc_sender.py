from pythonosc.udp_client import SimpleUDPClient
from tracker.face_tracker import FaceData

# OSC address mapping — uses VRChat/VSeeFace standard parameter names
OSC_MAP = {
    "head_yaw":    "/avatar/parameters/HeadYaw",
    "head_pitch":  "/avatar/parameters/HeadPitch",
    "head_roll":   "/avatar/parameters/HeadRoll",
    "mouth_open":  "/avatar/parameters/MouthOpen",
    "blink_left":  "/avatar/parameters/BlinkLeft",
    "blink_right": "/avatar/parameters/BlinkRight",
    "brow_left":   "/avatar/parameters/BrowLeft",
    "brow_right":  "/avatar/parameters/BrowRight",
}


class OscSender:
    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self._client = SimpleUDPClient(host, port)

    def send(self, data: FaceData):
        for field_name, osc_address in OSC_MAP.items():
            value = getattr(data, field_name)
            self._client.send_message(osc_address, value)
