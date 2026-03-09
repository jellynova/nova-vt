from unittest.mock import MagicMock, patch
import pytest
from orchestrator.twitch_bot import AlertEvent, AlertType, parse_alert


def test_parse_sub_event():
    event = parse_alert("sub", user="TestUser", message="Love the stream!")
    assert event.type == AlertType.SUB
    assert event.user == "TestUser"
    assert event.message == "Love the stream!"


def test_parse_follow_event():
    event = parse_alert("follow", user="NewFollower")
    assert event.type == AlertType.FOLLOW
    assert event.user == "NewFollower"


def test_parse_cheer_event():
    event = parse_alert("cheer", user="Cheerer", bits=100)
    assert event.type == AlertType.CHEER
    assert event.bits == 100


def test_alert_event_has_display_text():
    event = parse_alert("sub", user="TestUser")
    assert "TestUser" in event.display_text
