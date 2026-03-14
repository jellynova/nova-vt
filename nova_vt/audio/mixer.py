from __future__ import annotations

import queue
import threading
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except Exception:
    _SD_AVAILABLE = False


@dataclass
class ChannelConfig:
    volume: int          # 0–100
    muted: bool
    device: Optional[str]  # PortAudio device name, or None for default


@dataclass
class MixerConfig:
    sample_rate: int = 48000
    channels: int = 2
    blocksize: int = 2048
    mic_config: ChannelConfig = field(default_factory=lambda: ChannelConfig(75, False, None))
    game_config: ChannelConfig = field(default_factory=lambda: ChannelConfig(60, False, None))
    bgm_config: ChannelConfig = field(default_factory=lambda: ChannelConfig(30, False, None))
    master_volume: int = 90
    monitor_device: Optional[str] = None


class AudioMixer(QThread):
    """Captures mic + game audio via sounddevice, mixes to PCM s16le.

    Pushes mixed chunks to encoder_queue (bytes, s16le stereo 48 kHz).
    """

    error = pyqtSignal(str)

    _EMA_ATTACK = 0.3
    _EMA_DECAY  = 0.05

    def __init__(self, config: MixerConfig, encoder_queue: queue.Queue, parent=None) -> None:
        super().__init__(parent)
        self._config = config
        self._encoder_queue = encoder_queue
        self._stop_event = threading.Event()
        self._peak_ema: dict[str, float] = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        self._lock = threading.Lock()

    def stop_mixing(self) -> None:
        self._stop_event.set()

    def get_peaks(self) -> dict[str, float]:
        with self._lock:
            return dict(self._peak_ema)

    def set_volume(self, channel: str, volume: int) -> None:
        volume = max(0, min(100, volume))
        with self._lock:
            cfg = self._channel_cfg(channel)
            if cfg is not None:
                cfg.volume = volume
            elif channel == "master":
                self._config.master_volume = volume

    def set_mute(self, channel: str, muted: bool) -> None:
        with self._lock:
            cfg = self._channel_cfg(channel)
            if cfg is not None:
                cfg.muted = muted

    def _channel_cfg(self, channel: str) -> Optional[ChannelConfig]:
        return {"mic": self._config.mic_config, "game": self._config.game_config,
                "bgm": self._config.bgm_config}.get(channel)

    def _apply_channel_gain(self, buf: np.ndarray, volume: int, muted: bool) -> np.ndarray:
        if muted:
            return np.zeros_like(buf)
        return buf * (volume / 100.0)

    def _apply_master_gain(self, buf: np.ndarray, master_volume: int) -> np.ndarray:
        return buf * (master_volume / 100.0)

    def _update_peak(self, channel: str, buf: np.ndarray) -> None:
        peak = float(np.max(np.abs(buf))) if buf.size > 0 else 0.0
        alpha = self._EMA_ATTACK if peak > self._peak_ema[channel] else self._EMA_DECAY
        # Dict item assignment is atomic under the GIL; no lock needed here.
        self._peak_ema[channel] = alpha * peak + (1.0 - alpha) * self._peak_ema[channel]

    def _mix_and_enqueue(self, mic: np.ndarray, game: np.ndarray, bgm: np.ndarray) -> None:
        cfg = self._config
        mixed = (
            self._apply_channel_gain(mic, cfg.mic_config.volume, cfg.mic_config.muted)
            + self._apply_channel_gain(game, cfg.game_config.volume, cfg.game_config.muted)
            + self._apply_channel_gain(bgm, cfg.bgm_config.volume, cfg.bgm_config.muted)
        )
        mixed = self._apply_master_gain(mixed, cfg.master_volume)
        self._update_peak("master", mixed)
        mixed = np.clip(mixed, -1.0, 1.0)
        pcm = (mixed * 32767).astype(np.int16)
        try:
            self._encoder_queue.put_nowait(pcm.tobytes())
        except queue.Full:
            pass

    def run(self) -> None:
        if not _SD_AVAILABLE:
            self.error.emit("sounddevice not available")
            return
        cfg = self._config
        sr, bs, ch = cfg.sample_rate, cfg.blocksize, cfg.channels
        _mic_buf:  list[Optional[np.ndarray]] = [None]
        _game_buf: list[Optional[np.ndarray]] = [None]

        def _mic_cb(indata, frames, time_info, status):
            buf = indata.copy()
            self._update_peak("mic", buf)
            _mic_buf[0] = buf

        def _game_cb(indata, frames, time_info, status):
            buf = indata.copy()
            self._update_peak("game", buf)
            _game_buf[0] = buf

        try:
            mic_stream = sd.InputStream(samplerate=sr, channels=ch, blocksize=bs,
                                        dtype="float32", callback=_mic_cb,
                                        device=cfg.mic_config.device)
            game_stream = sd.InputStream(samplerate=sr, channels=ch, blocksize=bs,
                                         dtype="float32", callback=_game_cb,
                                         device=cfg.game_config.device)
            with mic_stream, game_stream:
                while not self._stop_event.is_set():
                    mic = _mic_buf[0] if _mic_buf[0] is not None else np.zeros((bs, ch), dtype=np.float32)
                    game = _game_buf[0] if _game_buf[0] is not None else np.zeros((bs, ch), dtype=np.float32)
                    bgm = np.zeros((bs, ch), dtype=np.float32)
                    self._mix_and_enqueue(mic, game, bgm)
                    self._stop_event.wait(bs / sr)
        except Exception as exc:
            self.error.emit(str(exc))
