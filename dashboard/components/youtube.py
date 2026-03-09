import threading
from pathlib import Path
from PyQt6.QtCore import pyqtSignal
from dashboard.components.base import ComponentWorker, ComponentStatus

_DEFAULT_SECRETS = Path("client_secrets.json")
_DEFAULT_TOKEN   = Path.home() / ".config" / "nova-vt" / "youtube.token"
_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


class YouTubeWorker(ComponentWorker):
    auth_complete = pyqtSignal()

    def __init__(self, secrets_file: Path = _DEFAULT_SECRETS,
                 token_file: Path = _DEFAULT_TOKEN, parent=None):
        super().__init__("youtube", parent)
        self._secrets_file = Path(secrets_file)
        self._token_file = Path(token_file)
        self._service = None

    def check_config(self):
        if not self._secrets_file.exists():
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "client_secrets.json missing")
            return
        if not self._token_file.exists():
            self._emit_status(ComponentStatus.NOT_CONFIGURED, "not authenticated")
            return
        try:
            self._service = self._build_service()
            self._emit_status(ComponentStatus.RUNNING, "authenticated")
        except Exception as e:
            self._emit_status(ComponentStatus.ERROR, str(e))

    def _build_service(self):
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
        import json

        with open(self._token_file) as f:
            creds_data = json.load(f)
        creds = Credentials.from_authorized_user_info(creds_data, _SCOPES)
        return build("youtube", "v3", credentials=creds)

    def start_oauth(self):
        if not self._secrets_file.exists():
            self._emit_status(ComponentStatus.ERROR, "client_secrets.json not found")
            return

        self._emit_status(ComponentStatus.CONNECTING, "waiting for browser...")

        def _run():
            try:
                from google_auth_oauthlib.flow import InstalledAppFlow
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self._secrets_file), _SCOPES
                )
                creds = flow.run_local_server(port=8080, open_browser=True)
                self._token_file.parent.mkdir(parents=True, exist_ok=True)
                with open(self._token_file, "w") as f:
                    f.write(creds.to_json())
                self._service = self._build_service()
                self._emit_status(ComponentStatus.RUNNING, "authenticated")
                self.auth_complete.emit()
            except Exception as e:
                self._emit_status(ComponentStatus.ERROR, str(e))

        threading.Thread(target=_run, daemon=True).start()
