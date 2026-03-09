import cv2
import signal
import sys
import tomllib
from pathlib import Path
from tracker.face_tracker import FaceTracker
from tracker.osc_sender import OscSender


def load_config():
    config_path = Path(__file__).parent.parent / "config" / "config.toml"
    with open(config_path, "rb") as f:
        return tomllib.load(f)


def main():
    config = load_config()
    tracker_cfg = config["tracker"]

    tracker = FaceTracker()
    sender = OscSender(
        host=tracker_cfg["osc_host"],
        port=tracker_cfg["osc_port"],
    )
    cap = cv2.VideoCapture(tracker_cfg["camera_index"])
    cap.set(cv2.CAP_PROP_FPS, tracker_cfg["fps"])

    running = True

    def handle_sigterm(sig, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    print(f"[nova-tracker] Starting on camera {tracker_cfg['camera_index']}")
    print(f"[nova-tracker] Sending OSC to {tracker_cfg['osc_host']}:{tracker_cfg['osc_port']}")

    while running:
        ret, frame = cap.read()
        if not ret:
            print("[nova-tracker] Camera read failed, retrying...")
            continue

        face_data = tracker.process(frame)
        if face_data:
            sender.send(face_data)

    cap.release()
    tracker.close()
    print("[nova-tracker] Stopped.")


if __name__ == "__main__":
    main()
