from __future__ import annotations

import unittest.mock as mock
from typing import Callable

import pytest

from nova_vt.chat.provider import ChatMessage
from nova_vt.chat.twitch import TwitchChatProvider


class TestTwitchChatProvider:
    def _make_provider(self) -> TwitchChatProvider:
        return TwitchChatProvider()

    def test_on_message_registers_callback(self):
        provider = self._make_provider()
        callback = mock.Mock()
        provider.on_message(callback)
        assert provider._message_callback is callback

    def test_connect_stores_credentials(self):
        provider = self._make_provider()
        with mock.patch.object(provider, "_start_client", return_value=None):
            provider.connect({"token": "oauth:abc123", "channel": "nova_vt"})
        assert provider._credentials["token"] == "oauth:abc123"
        assert provider._credentials["channel"] == "nova_vt"

    def test_disconnect_sets_stop_flag(self):
        provider = self._make_provider()
        provider._stop_event.clear()
        provider.disconnect()
        assert provider._stop_event.is_set()

    def test_send_delegates_to_internal(self):
        provider = self._make_provider()
        provider._pending_sends = []
        provider.send("hello chat")
        assert "hello chat" in provider._pending_sends

    def test_handle_message_fires_callback(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_author = mock.MagicMock()
        fake_author.name = "viewer1"
        fake_author.color = "#ff0000"

        fake_msg = mock.MagicMock()
        fake_msg.author = fake_author
        fake_msg.content = "PogChamp"

        provider._handle_raw_message(fake_msg)

        assert len(received) == 1
        m = received[0]
        assert m.platform == "twitch"
        assert m.username == "viewer1"
        assert m.color == "#ff0000"
        assert m.text == "PogChamp"
        assert m.event_type == "message"

    def test_handle_message_no_callback_does_not_raise(self):
        provider = self._make_provider()
        fake_author = mock.MagicMock()
        fake_author.name = "viewer"
        fake_author.color = "#ffffff"
        fake_msg = mock.MagicMock()
        fake_msg.author = fake_author
        fake_msg.content = "hi"
        provider._handle_raw_message(fake_msg)

    def test_handle_sub_event_creates_sub_message(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.user.name = "subscriber1"
        provider._handle_sub_event(fake_event)

        assert len(received) == 1
        assert received[0].event_type == "sub"
        assert received[0].platform == "twitch"

    def test_handle_raid_event_creates_raid_message(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.raider.name = "raider_channel"
        provider._handle_raid_event(fake_event)

        assert len(received) == 1
        assert received[0].event_type == "raid"
        assert received[0].username == "raider_channel"
