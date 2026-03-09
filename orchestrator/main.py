import asyncio
import subprocess
import sys
from pathlib import Path

from orchestrator.config import load_config
from orchestrator.obs_controller import OBSController
from orchestrator.twitch_bot import TwitchBot, AlertEvent, AlertType
from orchestrator.overlay_server import start_overlay_server, broadcast_chat, broadcast_alert

TRACKER_CMD = [sys.executable, "-m", "tracker.main"]
GODOT_SCENE = str(Path(__file__).parent.parent / "avatar" / "scenes" / "main.tscn")


async def _run():
    config = load_config()

    print("[nova-vt] Starting nova-vt orchestrator")

    # Start face tracker subprocess
    tracker_proc = subprocess.Popen(TRACKER_CMD, cwd=Path(__file__).parent.parent)
    print(f"[nova-vt] Face tracker started (pid {tracker_proc.pid})")

    # Start Godot avatar renderer
    godot_proc = subprocess.Popen(
        ["godot", "--path", str(Path(__file__).parent.parent / "avatar"), GODOT_SCENE]
    )
    print(f"[nova-vt] Godot avatar started (pid {godot_proc.pid})")

    # Connect to OBS
    obs = OBSController(
        host=config.obs_host,
        port=config.obs_port,
        password=config.obs_password,
    )
    print(f"[nova-vt] Connected to OBS at {config.obs_host}:{config.obs_port}")

    # Start overlay WebSocket server
    ws_server = await start_overlay_server()

    # Alert handler — broadcast to overlays
    def on_alert(event: AlertEvent):
        asyncio.create_task(broadcast_alert(event.display_text))
        if event.type == AlertType.CHAT:
            asyncio.create_task(broadcast_chat(event.user, event.message))

    # Start Twitch bot
    if config.twitch_token and config.twitch_channel:
        bot = TwitchBot(
            token=config.twitch_token,
            channel=config.twitch_channel,
            on_alert=on_alert,
        )
        asyncio.create_task(bot.start())
        print(f"[nova-vt] Twitch bot connecting to #{config.twitch_channel}")

    print("[nova-vt] All systems go! Press Ctrl+C to stop.")

    # Graceful shutdown via asyncio signal handler
    loop = asyncio.get_running_loop()
    stop = loop.create_future()

    for sig in (2, 15):  # SIGINT, SIGTERM
        try:
            loop.add_signal_handler(sig, lambda: stop.set_result(None) if not stop.done() else None)
        except (NotImplementedError, RuntimeError):
            pass

    await stop

    print("[nova-vt] Shutting down...")
    tracker_proc.terminate()
    godot_proc.terminate()
    ws_server.close()
    obs.disconnect()
    print("[nova-vt] Goodbye!")


def main():
    asyncio.run(_run())


if __name__ == "__main__":
    main()
