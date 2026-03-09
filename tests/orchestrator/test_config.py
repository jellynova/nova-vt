import pytest
from pathlib import Path
from orchestrator.config import load_config, StreamConfig


def test_load_config_returns_config_object(tmp_path):
    config_content = """
[tracker]
camera_index = 0
fps = 30
osc_host = "127.0.0.1"
osc_port = 9000

[obs]
host = "localhost"
port = 4455

[stream]
twitch_channel = "test_channel"

[scenes]
gameplay = "Gameplay"
just_chatting = "Just Chatting"
brb = "BRB"
starting_soon = "Starting Soon"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    cfg = load_config(config_file)
    assert isinstance(cfg, StreamConfig)
    assert cfg.obs_host == "localhost"
    assert cfg.obs_port == 4455
    assert cfg.twitch_channel == "test_channel"
    assert cfg.scenes["gameplay"] == "Gameplay"


def test_load_config_has_scene_names(tmp_path):
    config_content = """
[tracker]
camera_index = 0
fps = 30
osc_host = "127.0.0.1"
osc_port = 9000

[obs]
host = "localhost"
port = 4455

[stream]
twitch_channel = "test_channel"

[scenes]
gameplay = "Gameplay"
just_chatting = "Just Chatting"
brb = "BRB"
starting_soon = "Starting Soon"
"""
    config_file = tmp_path / "config.toml"
    config_file.write_text(config_content)

    cfg = load_config(config_file)
    assert "gameplay" in cfg.scenes
    assert "brb" in cfg.scenes
