import asyncio
import json
import threading
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler
import websockets

_chat_clients: set = set()
_alert_clients: set = set()


async def _chat_handler(websocket):
    _chat_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        _chat_clients.discard(websocket)


async def _alert_handler(websocket):
    _alert_clients.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        _alert_clients.discard(websocket)


async def _ws_router(websocket):
    path = websocket.request.path
    if path == "/chat":
        await _chat_handler(websocket)
    elif path == "/alerts":
        await _alert_handler(websocket)


async def broadcast_chat(user: str, message: str):
    if _chat_clients:
        data = json.dumps({"user": user, "message": message})
        await asyncio.gather(*[c.send(data) for c in _chat_clients])


async def broadcast_alert(text: str):
    if _alert_clients:
        data = json.dumps({"text": text})
        await asyncio.gather(*[c.send(data) for c in _alert_clients])


def start_overlay_server(port: int = 7777):
    """Start HTTP server for overlay files + WebSocket server."""
    overlay_dir = Path(__file__).parent.parent / "overlays"

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(overlay_dir), **kwargs)

        def log_message(self, *args):
            pass  # suppress access logs

    http = HTTPServer(("localhost", 7778), Handler)
    threading.Thread(target=http.serve_forever, daemon=True).start()
    print(f"[overlays] HTTP serving overlays at http://localhost:7778/")
    print(f"[overlays] WebSocket server at ws://localhost:{port}/")
    return websockets.serve(_ws_router, "localhost", port)
