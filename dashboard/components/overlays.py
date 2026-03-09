import asyncio
import threading
from dashboard.components.base import ComponentWorker, ComponentStatus


class OverlayWorker(ComponentWorker):
    def __init__(self, parent=None):
        super().__init__("overlays", parent)
        self._server = None
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start_overlays(self):
        def _run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                from orchestrator.overlay_server import start_overlay_server
                server_coro = self._loop.run_until_complete(start_overlay_server())
                self._server = server_coro
                self._emit_status(ComponentStatus.RUNNING, "http://localhost:7778")
                self._loop.run_forever()
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

        self._thread = threading.Thread(target=_run, daemon=True)
        self._thread.start()

    def stop_overlays(self):
        if self._server:
            self._server.close()
        if self._loop:
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._emit_status(ComponentStatus.STOPPED)
