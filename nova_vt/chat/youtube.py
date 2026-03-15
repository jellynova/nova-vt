from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage

_log = logging.getLogger(__name__)


class YouTubeChatProvider:
    """YouTube Live Chat adapter using google-api-python-client (polling).

    Polls the liveChatMessages.list endpoint every *poll_interval* seconds
    (or the interval returned by the API, whichever is longer).
    """

    _YT_COLOR = "#ff0000"

    def __init__(self, poll_interval: float = 5.0) -> None:
        self._poll_interval = poll_interval
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._service = None   # googleapiclient.discovery resource
        self._thread: Optional[threading.Thread] = None

    def connect(self, credentials: dict) -> None:
        if self._thread is not None and self._thread.is_alive():
            _log.debug("YouTubeChatProvider.connect() called while already polling — ignored")
            return
        self._credentials = credentials
        self._stop_event.clear()
        self._start_polling()

    def disconnect(self) -> None:
        self._stop_event.set()

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        if self._service is None:
            raise RuntimeError("YouTubeChatProvider: not connected")
        raise NotImplementedError("YouTube chat send not yet implemented")

    def _start_polling(self) -> None:
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="YouTubePollThread"
        )
        self._thread.start()

    def _poll_loop(self) -> None:
        if self._service is None:
            self._service = self._build_service()

        live_chat_id = self._credentials.get("live_chat_id", "")
        next_page_token: Optional[str] = None

        while not self._stop_event.is_set():
            try:
                request = self._service.liveChatMessages().list(
                    liveChatId=live_chat_id,
                    part="snippet,authorDetails",
                    pageToken=next_page_token,
                    maxResults=200,
                )
                response = request.execute()
                items = response.get("items", [])
                next_page_token = response.get("nextPageToken")
                api_interval_ms = response.get("pollingIntervalMillis", self._poll_interval * 1000)
                self._parse_and_emit(items)
                wait = max(self._poll_interval, api_interval_ms / 1000.0)
            except Exception:
                _log.exception("YouTubeChatProvider: poll error for live_chat_id %r", live_chat_id)
                wait = self._poll_interval

            self._stop_event.wait(timeout=wait)

    def _parse_and_emit(self, items: list[dict]) -> None:
        if self._message_callback is None:
            return
        for item in items:
            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            username = author.get("displayName", "unknown")
            msg_type = snippet.get("type", "")

            if msg_type == "textMessageEvent":
                text = snippet.get("textMessageDetails", {}).get("messageText", "")
                event_type = "message"
            elif msg_type == "superChatEvent":
                text = snippet.get("superChatDetails", {}).get("userComment", "")
                event_type = "gift"
            elif msg_type == "newSponsorEvent":
                text = ""
                event_type = "sub"
            else:
                continue

            self._message_callback(
                ChatMessage(
                    platform="youtube",
                    username=username,
                    color=self._YT_COLOR,
                    text=text,
                    event_type=event_type,
                )
            )

    def _build_service(self):
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        creds = Credentials(
            token=self._credentials.get("access_token", ""),
            refresh_token=self._credentials.get("refresh_token"),
            client_id=self._credentials.get("client_id"),
            client_secret=self._credentials.get("client_secret"),
            token_uri=self._credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
        )
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
