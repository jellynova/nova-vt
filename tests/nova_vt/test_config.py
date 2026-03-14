import os
import stat
import tempfile
from pathlib import Path
import pytest
from nova_vt.config import Config


def test_load_defaults():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        assert cfg.get("app", "vrm_path") == ""
        assert cfg.get("app", "camera_index") == 0


def test_set_and_get():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set("app", "camera_index", 2)
        assert cfg.get("app", "camera_index") == 2


def test_save_and_reload():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set("app", "vrm_path", "/home/nova/model.vrm")
        cfg.save()
        cfg2 = Config(config_dir=Path(d))
        assert cfg2.get("app", "vrm_path") == "/home/nova/model.vrm"


def test_secrets_created_with_mode_600():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set_secret("stream_keys", "twitch", "mykey")
        cfg.save()
        secrets_path = Path(d) / "secrets.toml"
        assert secrets_path.exists()
        mode = oct(stat.S_IMODE(os.stat(secrets_path).st_mode))
        assert mode == oct(0o600)


def test_get_secret():
    with tempfile.TemporaryDirectory() as d:
        cfg = Config(config_dir=Path(d))
        cfg.set_secret("stream_keys", "twitch", "abc123")
        cfg.save()
        cfg2 = Config(config_dir=Path(d))
        assert cfg2.get_secret("stream_keys", "twitch") == "abc123"
