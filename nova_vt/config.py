from __future__ import annotations

import os
import stat
import tomllib
import warnings
from pathlib import Path
from typing import Any

import tomli_w

_DEFAULTS: dict = {
    "app": {
        "vrm_path": "",
        "camera_index": 0,
        "fps": 30,
    },
    "audio": {
        "mic_volume": 75,
        "game_volume": 60,
        "bgm_volume": 30,
        "master_volume": 90,
        "monitor_device": "",
    },
    "stream": {
        "enabled_platforms": ["twitch", "youtube"],
    },
}

_SECRET_DEFAULTS: dict = {
    "stream_keys": {
        "twitch": "",
        "youtube": "",
        "tiktok": "",
    },
    "twitch": {
        "token": "",
        "client_id": "",
    },
    "youtube": {
        "client_secret_path": "",
    },
}


class Config:
    """Loads and saves nova-vt config from ~/.config/nova-vt/.

    Non-sensitive values live in config.toml.
    Sensitive values (keys, tokens) live in secrets.toml (mode 600).
    """

    def __init__(self, config_dir: Path | None = None) -> None:
        self._dir = config_dir or Path.home() / ".config" / "nova-vt"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._config_path = self._dir / "config.toml"
        self._secrets_path = self._dir / "secrets.toml"
        self._data = _deep_merge(_DEFAULTS, self._load_toml(self._config_path))
        self._secrets = _deep_merge(_SECRET_DEFAULTS, self._load_secrets())

    # --- public API ---

    def get(self, section: str, key: str) -> Any:
        return self._data.get(section, {}).get(key)

    def set(self, section: str, key: str, value: Any) -> None:
        self._data.setdefault(section, {})[key] = value

    def get_secret(self, section: str, key: str) -> Any:
        return self._secrets.get(section, {}).get(key)

    def set_secret(self, section: str, key: str, value: Any) -> None:
        self._secrets.setdefault(section, {})[key] = value

    def save(self) -> None:
        self._config_path.write_bytes(tomli_w.dumps(self._data).encode())
        self._write_secrets_atomic(tomli_w.dumps(self._secrets).encode())

    def _write_secrets_atomic(self, data: bytes) -> None:
        """Write secrets.toml atomically with mode 0o600.

        Uses a tempfile + os.replace so the file is never world-readable,
        and tracks the fd close state to avoid a double-close on error.
        """
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self._dir, suffix=".tmp")
        fd_closed = False
        try:
            os.write(tmp_fd, data)
            os.close(tmp_fd)
            fd_closed = True
            os.chmod(tmp_path, 0o600)
            os.replace(tmp_path, self._secrets_path)
        except Exception:
            if not fd_closed:
                os.close(tmp_fd)
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    # --- private ---

    def _load_toml(self, path: Path) -> dict:
        if not path.exists():
            return {}
        with open(path, "rb") as f:
            return tomllib.load(f)

    def _load_secrets(self) -> dict:
        if not self._secrets_path.exists():
            return {}
        mode = stat.S_IMODE(os.stat(self._secrets_path).st_mode)
        if mode & 0o077:
            warnings.warn(
                f"secrets.toml permissions are {oct(mode)} — expected 0o600. "
                "Other users may be able to read your stream keys.",
                stacklevel=2,
            )
        return self._load_toml(self._secrets_path)


def _deep_merge(base: dict, override: dict) -> dict:
    result = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = _deep_merge(result[k], v)
        else:
            result[k] = v
    return result
