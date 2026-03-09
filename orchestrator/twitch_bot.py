from dataclasses import dataclass, field
from enum import Enum
from typing import Callable
import asyncio
from twitchio.ext import commands


class AlertType(Enum):
    SUB = "sub"
    FOLLOW = "follow"
    CHEER = "cheer"
    RAID = "raid"
    CHAT = "chat"


@dataclass
class AlertEvent:
    type: AlertType
    user: str = ""
    message: str = ""
    bits: int = 0
    viewer_count: int = 0

    @property
    def display_text(self) -> str:
        match self.type:
            case AlertType.SUB:
                return f"{self.user} just subscribed! {self.message}"
            case AlertType.FOLLOW:
                return f"{self.user} followed!"
            case AlertType.CHEER:
                return f"{self.user} cheered {self.bits} bits!"
            case AlertType.RAID:
                return f"{self.user} raided with {self.viewer_count} viewers!"
            case AlertType.CHAT:
                return f"{self.user}: {self.message}"
            case _:
                return f"{self.user}: {self.type.value}"


def parse_alert(event_type: str, user: str = "", message: str = "",
                bits: int = 0, viewer_count: int = 0) -> AlertEvent:
    return AlertEvent(
        type=AlertType(event_type),
        user=user,
        message=message,
        bits=bits,
        viewer_count=viewer_count,
    )


class TwitchBot(commands.Bot):
    def __init__(self, token: str, channel: str,
                 on_alert: Callable[[AlertEvent], None]):
        super().__init__(token=token, prefix="!", initial_channels=[channel])
        self._on_alert = on_alert
        self._channel = channel

    async def event_ready(self):
        print(f"[twitch] Connected as {self.nick} in #{self._channel}")

    async def event_message(self, message):
        if message.echo:
            return
        event = parse_alert("chat", user=message.author.name,
                            message=message.content)
        self._on_alert(event)

    async def event_sub(self, sub):
        event = parse_alert("sub", user=sub.user.name,
                            message=sub.message or "")
        self._on_alert(event)

    async def event_cheer(self, cheer):
        event = parse_alert("cheer", user=cheer.user.name,
                            bits=cheer.bits)
        self._on_alert(event)
