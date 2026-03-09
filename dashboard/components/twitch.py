import asyncio
import threading
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from PyQt6.QtCore import pyqtSignal
from dashboard.components.base import ComponentWorker, ComponentStatus

_OAUTH_PORT = 17563
_OAUTH_REDIRECT = f"http://localhost:{_OAUTH_PORT}/callback"
_OAUTH_SCOPES = "chat:read+chat:edit+channel:read:subscriptions+bits:read"

_CALLBACK_HTML = """<!DOCTYPE html><html><body>
<p>Connecting to nova-vt...</p>
<script>
const hash = window.location.hash.slice(1);
const params = new URLSearchParams(hash);
const token = params.get('access_token');
if (token) {
    fetch('/token?access_token=' + encodeURIComponent(token))
        .then(() => { document.body.innerHTML = '<h2>Connected! Close this tab.</h2>'; });
} else {
    document.body.innerHTML = '<h2>No token found. Try again.</h2>';
}
</script></body></html>"""


def _extract_token_from_callback(path: str) -> str | None:
    parsed = urlparse(path)
    params = parse_qs(parsed.query)
    tokens = params.get("access_token", [])
    return tokens[0] if tokens else None


class TwitchWorker(ComponentWorker):
    token_received = pyqtSignal(str)
    chat_message = pyqtSignal(str, str)  # user, message
    alert = pyqtSignal(str)              # display_text

    def __init__(self, token: str, channel: str, client_id: str, parent=None):
        super().__init__("twitch", parent)
        self._token = token
        self._channel = channel
        self._client_id = client_id
        self._bot = None
        self._bot_loop: asyncio.AbstractEventLoop | None = None
        self._bot_thread: threading.Thread | None = None

    def check_config(self):
        if not self._token or not self._channel:
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "token or channel missing")
        else:
            self._emit_status(ComponentStatus.STOPPED)

    def start_oauth(self, client_id: str):
        self._client_id = client_id
        captured = {"token": None}

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path.startswith("/token"):
                    token = _extract_token_from_callback(self.path)
                    if token:
                        captured["token"] = token
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK")
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(_CALLBACK_HTML.encode())

            def log_message(self, *args):
                pass

        server = HTTPServer(("localhost", _OAUTH_PORT), Handler)
        server.timeout = 120

        url = (
            f"https://id.twitch.tv/oauth2/authorize"
            f"?client_id={client_id}"
            f"&redirect_uri={_OAUTH_REDIRECT}"
            f"&response_type=token"
            f"&scope={_OAUTH_SCOPES}"
        )
        webbrowser.open(url)
        self._emit_status(ComponentStatus.CONNECTING, "waiting for browser...")

        def _serve():
            import time
            start = time.time()
            while not captured["token"] and time.time() - start < 120:
                server.handle_request()
            server.server_close()
            if captured["token"]:
                self.token_received.emit(captured["token"])
            else:
                self._emit_status(ComponentStatus.NOT_CONFIGURED, "OAuth timed out")

        threading.Thread(target=_serve, daemon=True).start()

    def start_bot(self):
        from orchestrator.twitch_bot import TwitchBot, AlertEvent, AlertType

        def on_alert(event: AlertEvent):
            self.alert.emit(event.display_text)
            if event.type == AlertType.CHAT:
                self.chat_message.emit(event.user, event.message)

        self._emit_status(ComponentStatus.CONNECTING, f"#{self._channel}")

        def _run():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._bot_loop = loop
            try:
                bot = TwitchBot(
                    token=self._token,
                    channel=self._channel,
                    on_alert=on_alert,
                )
                self._bot = bot
                self._emit_status(ComponentStatus.RUNNING, f"#{self._channel}")
                loop.run_until_complete(bot.start())
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))
            finally:
                self._bot_loop = None

        self._bot_thread = threading.Thread(target=_run, daemon=True)
        self._bot_thread.start()

    def stop_bot(self):
        if self._bot and self._bot_loop:
            asyncio.run_coroutine_threadsafe(self._bot.close(), self._bot_loop)
        self._bot = None
        self._bot_loop = None
        self._emit_status(ComponentStatus.STOPPED)
