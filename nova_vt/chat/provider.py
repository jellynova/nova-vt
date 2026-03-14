from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable


# ---------------------------------------------------------------------------
# ChatMessage
# ---------------------------------------------------------------------------

@dataclass
class ChatMessage:
    """A single message or event from any chat platform."""
    platform: str    # "twitch" | "youtube" | "tiktok"
    username: str
    color: str       # hex color string, e.g. "#9147ff"
    text: str
    event_type: str  # "message" | "sub" | "raid" | "gift"


# ---------------------------------------------------------------------------
# ChatProvider Protocol
# ---------------------------------------------------------------------------

@runtime_checkable
class ChatProvider(Protocol):
    """Protocol every chat platform adapter must satisfy."""

    def connect(self, credentials: dict) -> None: ...
    def disconnect(self) -> None: ...
    def on_message(self, callback: Callable[[ChatMessage], None]) -> None: ...
    def send(self, text: str) -> None: ...


# ---------------------------------------------------------------------------
# ChatManager
# ---------------------------------------------------------------------------

class ChatManager:
    """Holds active ChatProvider instances and routes send() calls.

    send(text, platform=None)  → broadcast to all providers
    send(text, platform="twitch") → send to that provider only
    """

    def __init__(self) -> None:
        self._providers: dict[str, ChatProvider] = {}
        self._message_callbacks: list[Callable[[ChatMessage], None]] = []

    # ------------------------------------------------------------------
    # Provider registry
    # ------------------------------------------------------------------

    def add_provider(self, name: str, provider: ChatProvider) -> None:
        """Register a provider under the given name.

        Subscribes the manager's internal dispatcher to the provider's
        message stream.  If a provider with the same name already exists it
        is silently replaced (the old provider's callback remains registered
        on the old object — callers are responsible for disconnecting first).
        """
        self._providers[name] = provider
        provider.on_message(self._dispatch)

    def remove_provider(self, name: str) -> None:
        self._providers.pop(name, None)

    # ------------------------------------------------------------------
    # Message routing
    # ------------------------------------------------------------------

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        """Register a callback to receive all incoming messages."""
        self._message_callbacks.append(callback)

    def send(self, text: str, platform: str | None = None) -> None:
        """Send *text* to one platform (by name) or all active providers.

        Raises KeyError if *platform* is specified but not registered.
        """
        if platform is None:
            for provider in self._providers.values():
                provider.send(text)
        else:
            self._providers[platform].send(text)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _dispatch(self, msg: ChatMessage) -> None:
        for cb in self._message_callbacks:
            cb(msg)
