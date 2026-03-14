from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage


class TwitchChatProvider:
    """Twitch chat adapter backed by twitchio.

    Runs an asyncio event loop in a background daemon thread so the Qt
    main thread is never blocked.
    """

    def __init__(self) -> None:
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._pending_sends: list[str] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client = None  # twitchio.Client instance, set in _start_client

    def connect(self, credentials: dict) -> None:
        self._credentials = credentials
        self._start_client()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        """Queue *text* for sending on the next async iteration."""
        self._pending_sends.append(text)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._flush_sends_sync)

    def _handle_raw_message(self, message) -> None:
        if self._message_callback is None:
            return
        color = getattr(message.author, "color", None) or "#ffffff"
        msg = ChatMessage(
            platform="twitch",
            username=message.author.name,
            color=color,
            text=message.content,
            event_type="message",
        )
        self._message_callback(msg)

    def _handle_sub_event(self, event) -> None:
        if self._message_callback is None:
            return
        msg = ChatMessage(
            platform="twitch",
            username=event.user.name,
            color="#9147ff",
            text="",
            event_type="sub",
        )
        self._message_callback(msg)

    def _handle_raid_event(self, event) -> None:
        if self._message_callback is None:
            return
        msg = ChatMessage(
            platform="twitch",
            username=event.raider.name,
            color="#ff6905",
            text="",
            event_type="raid",
        )
        self._message_callback(msg)

    def _start_client(self) -> None:
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="TwitchChatThread"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        import twitchio

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        token = self._credentials.get("token", "")
        channel = self._credentials.get("channel", "")

        provider_ref = self

        class _Bot(twitchio.Client):
            async def event_message(self, message: twitchio.Message) -> None:
                if message.echo:
                    return
                provider_ref._handle_raw_message(message)

            async def event_channel_subscribed(self, event) -> None:
                provider_ref._handle_sub_event(event)

            async def event_channel_raid(self, event) -> None:
                provider_ref._handle_raid_event(event)

        try:
            self._client = _Bot(token=token, initial_channels=[channel])
            self._loop.run_until_complete(self._client.start())
        except Exception:
            pass
        finally:
            self._loop.close()

    def _flush_sends_sync(self) -> None:
        if self._client is None:
            return
        while self._pending_sends:
            text = self._pending_sends.pop(0)
            self._loop.call_soon_threadsafe(self._loop.create_task, self._async_send(text))

    async def _async_send(self, text: str) -> None:
        if self._client is None:
            return
        channel_name = self._credentials.get("channel", "")
        channel = self._client.get_channel(channel_name)
        if channel is not None:
            await channel.send(text)
