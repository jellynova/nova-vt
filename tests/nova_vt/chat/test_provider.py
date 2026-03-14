from __future__ import annotations

from typing import Callable
import pytest

from nova_vt.chat.provider import ChatMessage, ChatManager, ChatProvider


# ---------------------------------------------------------------------------
# Fake provider for testing
# ---------------------------------------------------------------------------

class FakeProvider:
    """Minimal ChatProvider implementation for unit tests."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.connected = False
        self.credentials: dict = {}
        self._callback: Callable[[ChatMessage], None] | None = None
        self.sent: list[str] = []

    def connect(self, credentials: dict) -> None:
        self.credentials = credentials
        self.connected = True

    def disconnect(self) -> None:
        self.connected = False

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._callback = callback

    def send(self, text: str) -> None:
        self.sent.append(text)

    def _emit(self, msg: ChatMessage) -> None:
        if self._callback:
            self._callback(msg)


# ---------------------------------------------------------------------------
# ChatMessage tests
# ---------------------------------------------------------------------------

class TestChatMessage:
    def test_fields_accessible(self):
        msg = ChatMessage(
            platform="twitch",
            username="nova",
            color="#9147ff",
            text="hello chat",
            event_type="message",
        )
        assert msg.platform == "twitch"
        assert msg.username == "nova"
        assert msg.color == "#9147ff"
        assert msg.text == "hello chat"
        assert msg.event_type == "message"

    def test_event_type_sub(self):
        msg = ChatMessage(
            platform="youtube",
            username="viewer1",
            color="#ffffff",
            text="",
            event_type="sub",
        )
        assert msg.event_type == "sub"

    def test_event_type_raid(self):
        msg = ChatMessage(
            platform="twitch",
            username="raider",
            color="#ff0000",
            text="",
            event_type="raid",
        )
        assert msg.event_type == "raid"

    def test_event_type_gift(self):
        msg = ChatMessage(
            platform="twitch",
            username="gifter",
            color="#00ff00",
            text="",
            event_type="gift",
        )
        assert msg.event_type == "gift"


# ---------------------------------------------------------------------------
# ChatProvider structural tests (Protocol compliance)
# ---------------------------------------------------------------------------

class TestChatProviderProtocol:
    def test_fake_provider_is_compliant(self):
        """FakeProvider must implement all ChatProvider protocol methods."""
        from nova_vt.chat.provider import ChatProvider as CP
        # The protocol is not runtime_checkable by default; verify via duck typing
        provider: ChatProvider = FakeProvider("twitch")
        provider.connect({"token": "abc"})
        assert provider.connected  # type: ignore[attr-defined]
        provider.disconnect()
        assert not provider.connected  # type: ignore[attr-defined]
        provider.send("hello")
        assert provider.sent == ["hello"]  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# ChatManager tests
# ---------------------------------------------------------------------------

class TestChatManager:
    def _make_manager(self) -> tuple[ChatManager, FakeProvider, FakeProvider]:
        twitch = FakeProvider("twitch")
        youtube = FakeProvider("youtube")
        mgr = ChatManager()
        mgr.add_provider("twitch", twitch)
        mgr.add_provider("youtube", youtube)
        return mgr, twitch, youtube

    def test_send_none_broadcasts_to_all(self):
        mgr, twitch, youtube = self._make_manager()
        mgr.send("hello world", platform=None)
        assert "hello world" in twitch.sent
        assert "hello world" in youtube.sent

    def test_send_specific_platform_only(self):
        mgr, twitch, youtube = self._make_manager()
        mgr.send("twitch only", platform="twitch")
        assert "twitch only" in twitch.sent
        assert "twitch only" not in youtube.sent

    def test_send_unknown_platform_raises(self):
        mgr, _, _ = self._make_manager()
        with pytest.raises(KeyError):
            mgr.send("hello", platform="tiktok")

    def test_on_message_callback_fires(self):
        mgr, twitch, _ = self._make_manager()
        received: list[ChatMessage] = []
        mgr.on_message(lambda m: received.append(m))
        msg = ChatMessage("twitch", "nova", "#9147ff", "hi", "message")
        twitch._emit(msg)
        assert len(received) == 1
        assert received[0].platform == "twitch"
        assert received[0].text == "hi"

    def test_remove_provider(self):
        mgr, twitch, youtube = self._make_manager()
        mgr.remove_provider("twitch")
        mgr.send("only youtube", platform=None)
        assert "only youtube" not in twitch.sent
        assert "only youtube" in youtube.sent

    def test_add_duplicate_provider_replaces(self):
        mgr, twitch, _ = self._make_manager()
        twitch2 = FakeProvider("twitch")
        mgr.add_provider("twitch", twitch2)
        mgr.send("new only", platform=None)
        assert "new only" not in twitch.sent
        assert "new only" in twitch2.sent
