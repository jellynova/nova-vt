from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage


class TikTokChatProvider:
    """TikTok LIVE chat adapter backed by TikTokLive (read-only).

    NOTE: TikTok RTMP push endpoint is TBD. send() raises NotImplementedError.
    """

    _TIKTOK_COLOR = "#fe2c55"

    def __init__(self) -> None:
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def connect(self, credentials: dict) -> None:
        self._credentials = credentials
        self._stop_event.clear()
        self._start_client()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        raise NotImplementedError(
            "TikTok chat send is TBD — RTMP push endpoint not yet confirmed."
        )

    def _handle_chat(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text=event.comment,
                event_type="message",
            )
        )

    def _handle_gift(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text=getattr(event.gift, "name", ""),
                event_type="gift",
            )
        )

    def _handle_follow(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text="",
                event_type="follow",
            )
        )

    def _start_client(self) -> None:
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="TikTokChatThread"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, GiftEvent, FollowEvent

        username = self._credentials.get("username", "")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        provider_ref = self

        client = TikTokLiveClient(unique_id=username)

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            provider_ref._handle_chat(event)

        @client.on(GiftEvent)
        async def on_gift(event: GiftEvent) -> None:
            provider_ref._handle_gift(event)

        @client.on(FollowEvent)
        async def on_follow(event: FollowEvent) -> None:
            provider_ref._handle_follow(event)

        try:
            self._loop.run_until_complete(client.start())
        except Exception:
            pass
        finally:
            self._loop.close()
