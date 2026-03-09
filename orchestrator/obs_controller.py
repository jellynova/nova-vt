import obsws_python as obs


class OBSController:
    def __init__(self, host: str, port: int, password: str):
        self._client = obs.ReqClient(host=host, port=port, password=password)

    def switch_scene(self, scene_name: str):
        self._client.set_current_program_scene(scene_name)
        print(f"[obs] Switched to scene: {scene_name}")

    def current_scene(self) -> str:
        resp = self._client.get_current_program_scene()
        return resp.current_program_scene_name

    def start_stream(self):
        self._client.start_stream()
        print("[obs] Stream started")

    def stop_stream(self):
        self._client.stop_stream()
        print("[obs] Stream stopped")

    def disconnect(self):
        self._client.disconnect()
