from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage

_log = logging.getLogger(__name__)


class TwitchChatProvider:
    """Twitch chat adapter backed by twitchio v3 (EventSub WebSocket).

    Credentials dict keys:
        client_id          – Twitch application client ID
        client_secret      – Twitch application client secret
        token              – User access token with ``user:read:chat`` scope
        broadcaster_user_id – Numeric user-ID of the channel to watch
        bot_user_id        – Numeric user-ID for the token holder (may equal
                              broadcaster_user_id)

    Runs an asyncio event loop in a background daemon thread so the Qt
    main thread is never blocked.
    """

    def __init__(self) -> None:
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._pending_sends: list[str] = []
        self._sends_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client = None  # twitchio.Client instance, set in _run_loop

    def connect(self, credentials: dict) -> None:
        if self._thread is not None and self._thread.is_alive():
            _log.debug("TwitchChatProvider.connect() called while already connected — ignored")
            return
        self._credentials = credentials
        self._start_client()

    def disconnect(self) -> None:
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        """Queue *text* for sending on the next async iteration."""
        with self._sends_lock:
            self._pending_sends.append(text)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._schedule_flush)

    def _handle_raw_message(self, message) -> None:
        if self._message_callback is None:
            return
        colour = getattr(message, "colour", None)
        color_str = str(colour) if colour is not None else "#ffffff"
        msg = ChatMessage(
            platform="twitch",
            username=message.chatter.name,
            color=color_str,
            text=message.text,
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
            username=event.from_broadcaster.name,
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
        from twitchio.eventsub import (
            ChatMessageSubscription,
            ChannelSubscribeSubscription,
            ChannelRaidSubscription,
        )

        creds = self._credentials
        client_id = creds.get("client_id", "")
        client_secret = creds.get("client_secret", "")
        token = creds.get("token", "")
        broadcaster_user_id = creds.get("broadcaster_user_id", "")
        bot_user_id = creds.get("bot_user_id", "") or broadcaster_user_id

        provider_ref = self
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        client = twitchio.Client(client_id=client_id, client_secret=client_secret)
        self._client = client

        @client.listen()
        async def event_message(message: twitchio.ChatMessage) -> None:
            provider_ref._handle_raw_message(message)

        @client.listen()
        async def event_channel_subscribe(subscription) -> None:
            provider_ref._handle_sub_event(subscription)

        @client.listen()
        async def event_channel_raid(raid) -> None:
            provider_ref._handle_raid_event(raid)

        async def _run() -> None:
            await client.add_token(token, "")
            await client.subscribe_websocket(
                ChatMessageSubscription(
                    broadcaster_user_id=broadcaster_user_id,
                    user_id=bot_user_id,
                )
            )
            await client.subscribe_websocket(
                ChannelSubscribeSubscription(broadcaster_user_id=broadcaster_user_id)
            )
            await client.subscribe_websocket(
                ChannelRaidSubscription(to_broadcaster_user_id=broadcaster_user_id)
            )
            await client.login(token=token)

        try:
            self._loop.run_until_complete(_run())
        except Exception:
            _log.exception(
                "TwitchChatProvider: connection error for broadcaster_user_id %r",
                creds.get("broadcaster_user_id", ""),
            )
        finally:
            self._loop.close()

    def _schedule_flush(self) -> None:
        """Called on the asyncio thread to drain pending sends."""
        if self._client is None:
            return
        with self._sends_lock:
            pending = self._pending_sends[:]
            self._pending_sends.clear()
        for text in pending:
            self._loop.create_task(self._async_send(text))

    async def _async_send(self, text: str) -> None:
        if self._client is None:
            return
        broadcaster_user_id = self._credentials.get("broadcaster_user_id", "")
        try:
            await self._client.send_message(
                broadcaster_id=broadcaster_user_id,
                sender_id=self._credentials.get("bot_user_id", "") or broadcaster_user_id,
                message=text,
            )
        except Exception:
            pass
