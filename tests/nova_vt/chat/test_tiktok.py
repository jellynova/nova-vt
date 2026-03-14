from __future__ import annotations

import unittest.mock as mock

import pytest

from nova_vt.chat.provider import ChatMessage
from nova_vt.chat.tiktok import TikTokChatProvider


class TestTikTokChatProvider:
    def _make_provider(self) -> TikTokChatProvider:
        return TikTokChatProvider()

    def test_on_message_registers_callback(self):
        provider = self._make_provider()
        cb = mock.Mock()
        provider.on_message(cb)
        assert provider._message_callback is cb

    def test_connect_stores_credentials(self):
        provider = self._make_provider()
        with mock.patch.object(provider, "_start_client", return_value=None):
            provider.connect({"username": "@nova_vt"})
        assert provider._credentials["username"] == "@nova_vt"

    def test_disconnect_sets_stop_flag(self):
        provider = self._make_provider()
        provider.disconnect()
        assert provider._stop_event.is_set()

    def test_send_raises_not_implemented(self):
        """TikTok RTMP push endpoint is TBD; send is not implemented."""
        provider = self._make_provider()
        with pytest.raises(NotImplementedError, match="TBD"):
            provider.send("hello tiktok")

    def test_handle_chat_event_fires_callback(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.user.nickname = "TikTokViewer"
        fake_event.comment = "love your stream!"

        provider._handle_chat(fake_event)

        assert len(received) == 1
        m = received[0]
        assert m.platform == "tiktok"
        assert m.username == "TikTokViewer"
        assert m.text == "love your stream!"
        assert m.event_type == "message"

    def test_handle_gift_event_fires_callback(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.user.nickname = "GiftSender"
        fake_event.gift.name = "Rose"

        provider._handle_gift(fake_event)

        assert len(received) == 1
        m = received[0]
        assert m.platform == "tiktok"
        assert m.event_type == "gift"
        assert m.username == "GiftSender"

    def test_handle_subscribe_event_fires_callback(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.user.nickname = "NewFollower"

        provider._handle_subscribe(fake_event)

        assert len(received) == 1
        assert received[0].event_type == "sub"
        assert received[0].username == "NewFollower"

    def test_handle_chat_no_callback_does_not_raise(self):
        provider = self._make_provider()
        fake_event = mock.MagicMock()
        fake_event.user.nickname = "someone"
        fake_event.comment = "hi"
        provider._handle_chat(fake_event)  # no crash
