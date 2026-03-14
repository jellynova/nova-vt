from __future__ import annotations

import time
import threading
import unittest.mock as mock

import pytest

from nova_vt.chat.provider import ChatMessage
from nova_vt.chat.youtube import YouTubeChatProvider


class TestYouTubeChatProvider:
    def _make_provider(self) -> YouTubeChatProvider:
        return YouTubeChatProvider(poll_interval=0.05)

    def test_on_message_registers_callback(self):
        provider = self._make_provider()
        cb = mock.Mock()
        provider.on_message(cb)
        assert provider._message_callback is cb

    def test_connect_stores_credentials(self):
        provider = self._make_provider()
        with mock.patch.object(provider, "_start_polling", return_value=None):
            provider.connect({"access_token": "ya29.xxx", "live_chat_id": "abc123"})
        assert provider._credentials["live_chat_id"] == "abc123"

    def test_disconnect_stops_polling(self):
        provider = self._make_provider()
        provider.disconnect()
        assert provider._stop_event.is_set()

    def test_send_raises_not_implemented(self):
        """YouTube Live Chat API requires OAuth; send() raises for now if not connected."""
        provider = self._make_provider()
        with pytest.raises(RuntimeError, match="not connected"):
            provider.send("hello")

    def test_parse_message_items_fires_callback(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_items = [
            {
                "snippet": {
                    "type": "textMessageEvent",
                    "textMessageDetails": {"messageText": "Hello from YT"},
                    "authorChannelId": "UCxxx",
                },
                "authorDetails": {
                    "displayName": "YouTubeViewer",
                    "profileImageUrl": "",
                },
            }
        ]
        provider._parse_and_emit(fake_items)

        assert len(received) == 1
        m = received[0]
        assert m.platform == "youtube"
        assert m.username == "YouTubeViewer"
        assert m.text == "Hello from YT"
        assert m.event_type == "message"

    def test_parse_super_chat_event(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_items = [
            {
                "snippet": {
                    "type": "superChatEvent",
                    "superChatDetails": {"userComment": "HYPE"},
                    "authorChannelId": "UCyyy",
                },
                "authorDetails": {
                    "displayName": "SuperChatUser",
                    "profileImageUrl": "",
                },
            }
        ]
        provider._parse_and_emit(fake_items)

        assert len(received) == 1
        assert received[0].event_type == "gift"
        assert received[0].text == "HYPE"

    def test_parse_membership_event(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_items = [
            {
                "snippet": {
                    "type": "newSponsorEvent",
                    "authorChannelId": "UCzzz",
                },
                "authorDetails": {
                    "displayName": "NewMember",
                    "profileImageUrl": "",
                },
            }
        ]
        provider._parse_and_emit(fake_items)

        assert len(received) == 1
        assert received[0].event_type == "sub"

    def test_poll_loop_calls_api_repeatedly(self):
        provider = YouTubeChatProvider(poll_interval=0.05)
        provider._credentials = {"live_chat_id": "lc123", "access_token": "ya29.x"}
        provider._message_callback = lambda m: None

        call_count = {"n": 0}

        def _fake_list(liveChatId, part, pageToken=None, maxResults=200):
            call_count["n"] += 1
            fake_req = mock.MagicMock()
            fake_req.execute.return_value = {
                "items": [],
                "nextPageToken": "tok",
                "pollingIntervalMillis": 50,
            }
            return fake_req

        mock_service = mock.MagicMock()
        mock_service.liveChatMessages().list = _fake_list
        provider._service = mock_service

        t = threading.Thread(target=provider._poll_loop, daemon=True)
        t.start()
        time.sleep(0.3)
        provider.disconnect()
        t.join(timeout=1.0)

        assert call_count["n"] >= 2
