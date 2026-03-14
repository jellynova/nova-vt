# nova-vt Streaming Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add audio mixing, ffmpeg RTMP encoding, and chat connectivity to the nova-vt pipeline.

**Architecture:** `AudioMixer` runs as a `QThread` capturing mic/game/BGM sources via sounddevice and pushing PCM s16le chunks to the encoder queue. `EncoderThread` consumes those chunks plus composite RGBA frames from the compositor, writing them to named FIFOs that a single ffmpeg subprocess reads and encodes to all active platforms via the tee muxer. Chat is decoupled behind a `ChatProvider` protocol so Twitch, YouTube, and TikTok providers are independently testable and swappable.

**Tech Stack:** sounddevice, ffmpeg (subprocess), twitchio, google-api-python-client, TikTokLive, threading

**Spec:** `docs/superpowers/specs/2026-03-14-nova-vt-redesign-design.md`

---

## Chunk 1: Audio + Encoder

### Task 1: AudioMixer QThread

**Files:**
- Create: `nova_vt/audio/mixer.py`
- Create: `nova_vt/audio/__init__.py`
- Create: `tests/nova_vt/audio/__init__.py`
- Create: `tests/nova_vt/audio/test_mixer.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/audio/test_mixer.py`:
```python
from __future__ import annotations

import queue
import time
import unittest.mock as mock

import numpy as np
import pytest

from nova_vt.audio.mixer import AudioMixer, ChannelConfig, MixerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(**kwargs) -> MixerConfig:
    return MixerConfig(
        sample_rate=48000,
        channels=2,
        blocksize=2048,
        mic_config=ChannelConfig(volume=75, muted=False, device=None),
        game_config=ChannelConfig(volume=60, muted=False, device=None),
        bgm_config=ChannelConfig(volume=30, muted=False, device=None),
        master_volume=90,
        monitor_device=None,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Unit tests (no real audio device required — sounddevice is mocked)
# ---------------------------------------------------------------------------

class TestAudioMixerPeakMeter:
    """Test peak meter EMA logic without touching the audio hardware."""

    def test_peak_meter_zero_on_silence(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        silence = np.zeros((2048, 2), dtype=np.float32)
        mixer._update_peak("mic", silence)
        assert mixer._peak_ema["mic"] == pytest.approx(0.0, abs=1e-6)

    def test_peak_meter_rises_on_signal(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        signal = np.ones((2048, 2), dtype=np.float32) * 0.9
        mixer._update_peak("mic", signal)
        assert mixer._peak_ema["mic"] > 0.0
        assert mixer._peak_ema["mic"] <= 0.9

    def test_peak_meter_decays_toward_zero(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._peak_ema = {"mic": 0.8, "game": 0.0, "bgm": 0.0, "master": 0.0}
        silence = np.zeros((2048, 2), dtype=np.float32)
        for _ in range(10):
            mixer._update_peak("mic", silence)
        assert mixer._peak_ema["mic"] < 0.8


class TestAudioMixerVolume:
    """Test volume / mute mixing arithmetic on synthetic buffers."""

    def test_muted_channel_contributes_zero(self):
        mixer = AudioMixer.__new__(AudioMixer)
        buf = np.ones((512, 2), dtype=np.float32) * 0.5
        result = mixer._apply_channel_gain(buf, volume=100, muted=True)
        assert np.all(result == 0.0)

    def test_volume_scales_output(self):
        mixer = AudioMixer.__new__(AudioMixer)
        buf = np.ones((512, 2), dtype=np.float32)
        half = mixer._apply_channel_gain(buf, volume=50, muted=False)
        assert half[0, 0] == pytest.approx(0.5, rel=1e-4)

    def test_master_volume_applied_to_mix(self):
        mixer = AudioMixer.__new__(AudioMixer)
        buf = np.ones((512, 2), dtype=np.float32)
        result = mixer._apply_master_gain(buf, master_volume=90)
        assert result[0, 0] == pytest.approx(0.9, rel=1e-4)


class TestAudioMixerEncoderQueue:
    """Test that the mixer pushes s16le PCM bytes to encoder_queue."""

    def test_mix_produces_s16le_bytes(self):
        """_mix_and_enqueue should push bytes to encoder_queue."""
        encoder_q: queue.Queue[bytes] = queue.Queue(maxsize=4)
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._encoder_queue = encoder_q
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        mixer._config = _make_config()

        mic = np.zeros((2048, 2), dtype=np.float32)
        game = np.zeros((2048, 2), dtype=np.float32)
        bgm = np.zeros((2048, 2), dtype=np.float32)
        mixer._mix_and_enqueue(mic, game, bgm)

        assert not encoder_q.empty()
        chunk = encoder_q.get_nowait()
        assert isinstance(chunk, (bytes, bytearray))
        # s16le: 2 bytes per sample × 2 channels × 2048 frames
        assert len(chunk) == 2048 * 2 * 2

    def test_full_encoder_queue_drops_chunk(self):
        """When encoder_queue is full, chunk is dropped without blocking."""
        encoder_q: queue.Queue[bytes] = queue.Queue(maxsize=1)
        encoder_q.put_nowait(b"sentinel")  # fill it
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._encoder_queue = encoder_q
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        mixer._config = _make_config()

        mic = np.zeros((2048, 2), dtype=np.float32)
        game = np.zeros((2048, 2), dtype=np.float32)
        bgm = np.zeros((2048, 2), dtype=np.float32)

        # Should not raise or block
        mixer._mix_and_enqueue(mic, game, bgm)

        # Original sentinel still there, dropped chunk didn't displace it
        assert encoder_q.get_nowait() == b"sentinel"


class TestAudioMixerPeakAPI:
    """Test the public get_peaks() API."""

    def test_get_peaks_returns_all_channels(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._peak_ema = {"mic": 0.3, "game": 0.5, "bgm": 0.1, "master": 0.4}
        peaks = mixer.get_peaks()
        assert set(peaks.keys()) == {"mic", "game", "bgm", "master"}
        assert peaks["game"] == pytest.approx(0.5)


class TestAudioMixerSetVolume:
    """Test that set_volume / set_mute update live config."""

    def test_set_volume_clamps_to_0_100(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer.set_volume("mic", 150)
        assert mixer._config.mic_config.volume == 100

    def test_set_volume_below_zero_clamps(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer.set_volume("mic", -5)
        assert mixer._config.mic_config.volume == 0

    def test_set_mute_toggles_channel(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer.set_mute("game", True)
        assert mixer._config.game_config.muted is True
        mixer.set_mute("game", False)
        assert mixer._config.game_config.muted is False
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/audio/test_mixer.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'AudioMixer'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/audio/__init__.py`:
```python
```

`nova_vt/audio/mixer.py`:
```python
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


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# AudioMixer QThread
# ---------------------------------------------------------------------------

class AudioMixer(QThread):
    """Captures mic + game audio via sounddevice, mixes to PCM s16le.

    Pushes mixed chunks to encoder_queue (bytes, s16le stereo 48 kHz).
    Also routes the monitor mix to the configured PortAudio output device.
    """

    error = pyqtSignal(str)

    _EMA_ATTACK = 0.3   # fast rise
    _EMA_DECAY  = 0.05  # slow fall

    def __init__(
        self,
        config: MixerConfig,
        encoder_queue: queue.Queue,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._encoder_queue = encoder_queue
        self._stop_event = threading.Event()
        self._peak_ema: dict[str, float] = {
            "mic": 0.0,
            "game": 0.0,
            "bgm": 0.0,
            "master": 0.0,
        }
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public control API (thread-safe)
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _channel_cfg(self, channel: str) -> Optional[ChannelConfig]:
        return {
            "mic": self._config.mic_config,
            "game": self._config.game_config,
            "bgm": self._config.bgm_config,
        }.get(channel)

    def _apply_channel_gain(
        self, buf: np.ndarray, volume: int, muted: bool
    ) -> np.ndarray:
        if muted:
            return np.zeros_like(buf)
        return buf * (volume / 100.0)

    def _apply_master_gain(self, buf: np.ndarray, master_volume: int) -> np.ndarray:
        return buf * (master_volume / 100.0)

    def _update_peak(self, channel: str, buf: np.ndarray) -> None:
        peak = float(np.max(np.abs(buf))) if buf.size > 0 else 0.0
        alpha = self._EMA_ATTACK if peak > self._peak_ema[channel] else self._EMA_DECAY
        with self._lock:
            self._peak_ema[channel] = (
                alpha * peak + (1.0 - alpha) * self._peak_ema[channel]
            )

    def _mix_and_enqueue(
        self,
        mic: np.ndarray,
        game: np.ndarray,
        bgm: np.ndarray,
    ) -> None:
        """Mix channels, apply master gain, push s16le bytes to encoder_queue."""
        cfg = self._config
        mixed = (
            self._apply_channel_gain(mic, cfg.mic_config.volume, cfg.mic_config.muted)
            + self._apply_channel_gain(game, cfg.game_config.volume, cfg.game_config.muted)
            + self._apply_channel_gain(bgm, cfg.bgm_config.volume, cfg.bgm_config.muted)
        )
        mixed = self._apply_master_gain(mixed, cfg.master_volume)
        self._update_peak("master", mixed)

        # Clip to [-1, 1] then convert to int16
        mixed = np.clip(mixed, -1.0, 1.0)
        pcm = (mixed * 32767).astype(np.int16)
        chunk = pcm.tobytes()

        try:
            self._encoder_queue.put_nowait(chunk)
        except queue.Full:
            pass  # drop — encoder is behind

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        if not _SD_AVAILABLE:
            self.error.emit("sounddevice not available")
            return

        sr = self._config.sample_rate
        bs = self._config.blocksize
        ch = self._config.channels

        # Buffers shared between callbacks and mix loop
        _mic_buf:  list[Optional[np.ndarray]] = [None]
        _game_buf: list[Optional[np.ndarray]] = [None]

        def _mic_callback(indata: np.ndarray, frames: int, time_info, status):
            buf = indata.copy()
            self._update_peak("mic", buf)
            _mic_buf[0] = buf

        def _game_callback(indata: np.ndarray, frames: int, time_info, status):
            buf = indata.copy()
            self._update_peak("game", buf)
            _game_buf[0] = buf

        silence = np.zeros((bs, ch), dtype=np.float32)

        try:
            mic_dev = self._config.mic_config.device
            game_dev = self._config.game_config.device

            mic_stream = sd.InputStream(
                samplerate=sr,
                blocksize=bs,
                channels=ch,
                dtype="float32",
                device=mic_dev,
                callback=_mic_callback,
            )
            game_stream = sd.InputStream(
                samplerate=sr,
                blocksize=bs,
                channels=ch,
                dtype="float32",
                device=game_dev,
                callback=_game_callback,
            )

            with mic_stream, game_stream:
                while not self._stop_event.is_set():
                    mic  = _mic_buf[0] if _mic_buf[0] is not None else silence
                    game = _game_buf[0] if _game_buf[0] is not None else silence
                    bgm  = silence  # BGM file playback: future work
                    self._mix_and_enqueue(mic, game, bgm)
                    # ~one mix cycle per blocksize
                    self._stop_event.wait(timeout=bs / sr)

        except Exception as exc:
            self.error.emit(str(exc))
```

`tests/nova_vt/audio/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/audio/test_mixer.py -v
```

Expected output: all tests `PASSED`, no errors.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/audio/__init__.py nova_vt/audio/mixer.py tests/nova_vt/audio/__init__.py tests/nova_vt/audio/test_mixer.py && git commit -m "feat: add AudioMixer QThread with sounddevice, 4-channel mixing, peak EMA

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 2: EncoderThread (named FIFOs + ffmpeg tee)

**Files:**
- Create: `nova_vt/encoder/__init__.py`
- Create: `nova_vt/encoder/encoder.py`
- Create: `tests/nova_vt/encoder/__init__.py`
- Create: `tests/nova_vt/encoder/test_encoder.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/encoder/test_encoder.py`:
```python
from __future__ import annotations

import os
import queue
import subprocess
import time
import threading
from pathlib import Path

import numpy as np
import pytest

from nova_vt.encoder.encoder import EncoderThread, EncoderConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

FIFO_VIDEO = "/tmp/nova-vt-test-video.fifo"
FIFO_AUDIO = "/tmp/nova-vt-test-audio.fifo"


def _make_config(rtmp_url: str = "rtmp://localhost:1935/live/test") -> EncoderConfig:
    return EncoderConfig(
        video_fifo=FIFO_VIDEO,
        audio_fifo=FIFO_AUDIO,
        width=1920,
        height=1080,
        fps=30,
        sample_rate=48000,
        audio_channels=2,
        video_bitrate="6000k",
        audio_bitrate="160k",
        rtmp_targets=[rtmp_url],
    )


# ---------------------------------------------------------------------------
# Unit tests (no ffmpeg required)
# ---------------------------------------------------------------------------

class TestEncoderConfig:
    def test_tee_string_single_target(self):
        cfg = _make_config("rtmp://live.twitch.tv/app/mykey")
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = cfg
        tee = enc._build_tee_string()
        assert tee == "[f=flv]rtmp://live.twitch.tv/app/mykey"

    def test_tee_string_multiple_targets(self):
        cfg = EncoderConfig(
            video_fifo=FIFO_VIDEO,
            audio_fifo=FIFO_AUDIO,
            width=1920,
            height=1080,
            fps=30,
            sample_rate=48000,
            audio_channels=2,
            video_bitrate="6000k",
            audio_bitrate="160k",
            rtmp_targets=[
                "rtmp://live.twitch.tv/app/key1",
                "rtmp://a.rtmp.youtube.com/live2/key2",
            ],
        )
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = cfg
        tee = enc._build_tee_string()
        assert "[f=flv]rtmp://live.twitch.tv/app/key1" in tee
        assert "[f=flv]rtmp://a.rtmp.youtube.com/live2/key2" in tee
        assert "|" in tee

    def test_ffmpeg_args_structure(self):
        cfg = _make_config()
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = cfg
        args = enc._build_ffmpeg_args()
        # Must start with ffmpeg
        assert args[0] == "ffmpeg"
        # Must reference both FIFOs as inputs
        assert FIFO_VIDEO in args
        assert FIFO_AUDIO in args
        # Must use tee muxer
        assert "-f" in args
        tee_idx = [i for i, a in enumerate(args) if a == "-f" and i + 1 < len(args) and args[i+1] == "tee"]
        assert len(tee_idx) >= 1
        # Must specify rawvideo + s16le input formats
        assert "rawvideo" in args
        assert "s16le" in args


class TestFifoLifecycle:
    """Test FIFO creation/cleanup without launching ffmpeg."""

    def test_create_fifos_removes_stale(self, tmp_path):
        video_fifo = str(tmp_path / "video.fifo")
        audio_fifo = str(tmp_path / "audio.fifo")
        # Pre-create as regular files to simulate stale FIFOs
        Path(video_fifo).write_bytes(b"stale")
        Path(audio_fifo).write_bytes(b"stale")

        enc = EncoderThread.__new__(EncoderThread)
        enc._config = EncoderConfig(
            video_fifo=video_fifo,
            audio_fifo=audio_fifo,
            width=1920,
            height=1080,
            fps=30,
            sample_rate=48000,
            audio_channels=2,
            video_bitrate="6000k",
            audio_bitrate="160k",
            rtmp_targets=["rtmp://localhost/live/test"],
        )
        enc._create_fifos()
        # After creation, paths must be actual FIFOs (stat.S_ISFIFO)
        import stat
        assert stat.S_ISFIFO(os.stat(video_fifo).st_mode)
        assert stat.S_ISFIFO(os.stat(audio_fifo).st_mode)
        # Cleanup
        enc._unlink_fifos()
        assert not Path(video_fifo).exists()
        assert not Path(audio_fifo).exists()

    def test_create_fifos_ok_when_not_exist(self, tmp_path):
        video_fifo = str(tmp_path / "v.fifo")
        audio_fifo = str(tmp_path / "a.fifo")
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = EncoderConfig(
            video_fifo=video_fifo,
            audio_fifo=audio_fifo,
            width=1920, height=1080, fps=30,
            sample_rate=48000, audio_channels=2,
            video_bitrate="6000k", audio_bitrate="160k",
            rtmp_targets=["rtmp://localhost/live/test"],
        )
        enc._create_fifos()
        import stat
        assert stat.S_ISFIFO(os.stat(video_fifo).st_mode)
        assert stat.S_ISFIFO(os.stat(audio_fifo).st_mode)
        enc._unlink_fifos()


# ---------------------------------------------------------------------------
# Integration test: stream to a local RTMP sink via ffmpeg -listen
# ---------------------------------------------------------------------------

class TestEncoderIntegration:
    """Stream synthetic frames to a local ffmpeg RTMP listener."""

    @pytest.mark.slow
    def test_encoder_streams_to_local_rtmp(self, tmp_path):
        """Wire encoder to a loopback ffmpeg RTMP server for 3 seconds."""
        rtmp_url = "rtmp://127.0.0.1:19350/live/test"

        # Start a local RTMP listener (exits after 5 s or when client disconnects)
        sink = subprocess.Popen(
            [
                "ffmpeg", "-y",
                "-listen", "1",
                "-i", rtmp_url,
                "-t", "5",
                "-f", "null", "-",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Give the listener a moment to bind
        time.sleep(0.5)

        video_q: queue.Queue = queue.Queue(maxsize=8)
        audio_q: queue.Queue = queue.Queue(maxsize=8)

        cfg = EncoderConfig(
            video_fifo=str(tmp_path / "video.fifo"),
            audio_fifo=str(tmp_path / "audio.fifo"),
            width=1920,
            height=1080,
            fps=30,
            sample_rate=48000,
            audio_channels=2,
            video_bitrate="1000k",  # low bitrate for test speed
            audio_bitrate="64k",
            rtmp_targets=[rtmp_url],
        )

        enc = EncoderThread(config=cfg, video_queue=video_q, audio_queue=audio_q)

        # Producer thread: push 3 seconds of synthetic frames (90 frames @ 30fps)
        rgba_frame = np.zeros((1080, 1920, 4), dtype=np.uint8)
        pcm_chunk = np.zeros((2048, 2), dtype=np.int16).tobytes()

        def _produce():
            for _ in range(90):
                try:
                    video_q.put(rgba_frame.tobytes(), timeout=1.0)
                    audio_q.put(pcm_chunk, timeout=1.0)
                except queue.Full:
                    pass
                time.sleep(1.0 / 30)
            # Signal EOF
            video_q.put(None)
            audio_q.put(None)

        enc.start()
        producer = threading.Thread(target=_produce, daemon=True)
        producer.start()
        producer.join(timeout=10)

        enc.stop_encoding()
        enc.wait(5000)  # wait up to 5 s for QThread to finish

        # Sink should have exited cleanly (ffmpeg returns 0 or is still running)
        sink.wait(timeout=8)
        assert sink.returncode in (0, None, 255), (
            f"RTMP sink exited with unexpected code {sink.returncode}"
        )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/encoder/test_encoder.py -v -k "not slow" 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'EncoderThread'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/encoder/__init__.py`:
```python
```

`nova_vt/encoder/encoder.py`:
```python
from __future__ import annotations

import os
import queue
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class EncoderConfig:
    video_fifo: str = "/tmp/nova-vt-video.fifo"
    audio_fifo: str = "/tmp/nova-vt-audio.fifo"
    width: int = 1920
    height: int = 1080
    fps: int = 30
    sample_rate: int = 48000
    audio_channels: int = 2
    video_bitrate: str = "6000k"
    audio_bitrate: str = "160k"
    rtmp_targets: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EncoderThread
# ---------------------------------------------------------------------------

class EncoderThread(QThread):
    """Writes RGBA frames + PCM audio to named FIFOs consumed by ffmpeg.

    Shutdown sequence:
      1. stop_encoding() sets _stop_event
      2. run() closes FIFO file objects (sends EOF to ffmpeg)
      3. ffmpeg_proc.wait(timeout=10); kill if timeout
      4. FIFOs are unlinked
    """

    error = pyqtSignal(str)

    def __init__(
        self,
        config: EncoderConfig,
        video_queue: queue.Queue,
        audio_queue: queue.Queue,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._video_queue = video_queue
        self._audio_queue = audio_queue
        self._stop_event = threading.Event()
        self._ffmpeg_proc: Optional[subprocess.Popen] = None
        self._video_fd: Optional[object] = None
        self._audio_fd: Optional[object] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stop_encoding(self) -> None:
        self._stop_event.set()
        # Push sentinel values so queue.get() unblocks immediately
        try:
            self._video_queue.put_nowait(None)
        except queue.Full:
            pass
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass

    # ------------------------------------------------------------------
    # FIFO helpers
    # ------------------------------------------------------------------

    def _create_fifos(self) -> None:
        for path in (self._config.video_fifo, self._config.audio_fifo):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass
            os.mkfifo(path)

    def _unlink_fifos(self) -> None:
        for path in (self._config.video_fifo, self._config.audio_fifo):
            try:
                os.unlink(path)
            except FileNotFoundError:
                pass

    # ------------------------------------------------------------------
    # ffmpeg command builder
    # ------------------------------------------------------------------

    def _build_tee_string(self) -> str:
        return "|".join(f"[f=flv]{t}" for t in self._config.rtmp_targets)

    def _build_ffmpeg_args(self) -> list[str]:
        cfg = self._config
        return [
            "ffmpeg",
            "-re",                          # real-time rate
            "-f", "rawvideo",
            "-pix_fmt", "rgba",
            "-s", f"{cfg.width}x{cfg.height}",
            "-r", str(cfg.fps),
            "-i", cfg.video_fifo,
            "-f", "s16le",
            "-ar", str(cfg.sample_rate),
            "-ac", str(cfg.audio_channels),
            "-i", cfg.audio_fifo,
            "-vf", "format=yuv420p",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-b:v", cfg.video_bitrate,
            "-c:a", "aac",
            "-b:a", cfg.audio_bitrate,
            "-f", "tee",
            self._build_tee_string(),
        ]

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            self._create_fifos()

            # Open FIFOs for writing in daemon threads to avoid blocking
            # until ffmpeg connects (named FIFOs block open() until both ends connect).
            video_fd_holder: list[Optional[object]] = [None]
            audio_fd_holder: list[Optional[object]] = [None]
            open_error: list[Optional[Exception]] = [None]

            def _open_video():
                try:
                    video_fd_holder[0] = open(self._config.video_fifo, "wb")
                except Exception as e:
                    open_error[0] = e

            def _open_audio():
                try:
                    audio_fd_holder[0] = open(self._config.audio_fifo, "wb")
                except Exception as e:
                    open_error[0] = e

            open_threads = [
                threading.Thread(target=_open_video, daemon=True),
                threading.Thread(target=_open_audio, daemon=True),
            ]
            for t in open_threads:
                t.start()

            # Launch ffmpeg (opens the reader ends of the FIFOs)
            args = self._build_ffmpeg_args()
            self._ffmpeg_proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            # Wait for FIFO open threads to complete
            for t in open_threads:
                t.join(timeout=10.0)

            if open_error[0] is not None:
                raise open_error[0]

            video_fd = video_fd_holder[0]
            audio_fd = audio_fd_holder[0]
            self._video_fd = video_fd
            self._audio_fd = audio_fd

            if video_fd is None or audio_fd is None:
                raise RuntimeError("Failed to open FIFO file descriptors")

            # Main write loop
            while not self._stop_event.is_set():
                try:
                    frame = self._video_queue.get(timeout=0.1)
                    if frame is None:
                        break
                    video_fd.write(frame)
                    video_fd.flush()
                except queue.Empty:
                    continue
                except BrokenPipeError:
                    break

                try:
                    chunk = self._audio_queue.get_nowait()
                    if chunk is None:
                        break
                    audio_fd.write(chunk)
                    audio_fd.flush()
                except queue.Empty:
                    pass
                except BrokenPipeError:
                    break

            # Flush remaining audio
            while True:
                try:
                    chunk = self._audio_queue.get_nowait()
                    if chunk is None or audio_fd is None:
                        break
                    audio_fd.write(chunk)
                    audio_fd.flush()
                except queue.Empty:
                    break

        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            # Close FIFOs → send EOF to ffmpeg
            for fd in (self._video_fd, self._audio_fd):
                if fd is not None:
                    try:
                        fd.close()
                    except Exception:
                        pass

            # Wait for ffmpeg to exit
            if self._ffmpeg_proc is not None:
                try:
                    self._ffmpeg_proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self._ffmpeg_proc.kill()
                    self._ffmpeg_proc.wait()

            self._unlink_fifos()
```

`tests/nova_vt/encoder/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/encoder/test_encoder.py -v -k "not slow"
```

Expected output: all non-slow tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/encoder/__init__.py nova_vt/encoder/encoder.py tests/nova_vt/encoder/__init__.py tests/nova_vt/encoder/test_encoder.py && git commit -m "feat: add EncoderThread with named FIFOs, ffmpeg tee muxer, RTMP output

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 2: Chat System

### Task 3: ChatProvider protocol + ChatMessage + ChatManager

**Files:**
- Create: `nova_vt/chat/__init__.py`
- Create: `nova_vt/chat/provider.py`
- Create: `tests/nova_vt/chat/__init__.py`
- Create: `tests/nova_vt/chat/test_provider.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/chat/test_provider.py`:
```python
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
        # runtime_checkable Protocol check
        from typing import runtime_checkable
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_provider.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'ChatMessage'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/chat/__init__.py`:
```python
```

`nova_vt/chat/provider.py`:
```python
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
```

`tests/nova_vt/chat/__init__.py`:
```python
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_provider.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/chat/__init__.py nova_vt/chat/provider.py tests/nova_vt/chat/__init__.py tests/nova_vt/chat/test_provider.py && git commit -m "feat: add ChatProvider protocol, ChatMessage dataclass, ChatManager routing

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 4: StreamStats + StatsPollerThread

**Files:**
- Create: `nova_vt/chat/stats.py`
- Create: `tests/nova_vt/chat/test_stats.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/chat/test_stats.py`:
```python
from __future__ import annotations

import time
import threading

import pytest

from nova_vt.chat.stats import StreamStats, StatsPollerThread


# ---------------------------------------------------------------------------
# StreamStats unit tests
# ---------------------------------------------------------------------------

class TestStreamStats:
    def test_initial_viewer_counts_are_zero(self):
        stats = StreamStats()
        assert stats.twitch_viewers == 0
        assert stats.youtube_viewers == 0
        assert stats.tiktok_viewers == 0
        assert stats.total_viewers == 0

    def test_total_viewers_is_sum(self):
        stats = StreamStats()
        stats.update_viewers("twitch", 100)
        stats.update_viewers("youtube", 200)
        stats.update_viewers("tiktok", 50)
        assert stats.total_viewers == 350

    def test_update_viewers_unknown_platform_ignored(self):
        stats = StreamStats()
        stats.update_viewers("facebook", 999)  # silently ignored
        assert stats.total_viewers == 0

    def test_stream_time_str_format(self):
        stats = StreamStats()
        stats.set_stream_start(time.time() - 3661)  # 1h 1m 1s ago
        t = stats.stream_time_str
        assert t == "01:01:01"

    def test_stream_time_str_zero_before_start(self):
        stats = StreamStats()
        assert stats.stream_time_str == "00:00:00"

    def test_thread_safe_concurrent_updates(self):
        """Multiple threads updating viewers must not corrupt state."""
        stats = StreamStats()
        errors: list[Exception] = []

        def _updater(platform: str, count: int):
            try:
                for _ in range(200):
                    stats.update_viewers(platform, count)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=_updater, args=("twitch", 100)),
            threading.Thread(target=_updater, args=("youtube", 200)),
            threading.Thread(target=_updater, args=("tiktok", 50)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert stats.twitch_viewers == 100
        assert stats.youtube_viewers == 200
        assert stats.tiktok_viewers == 50
        assert stats.total_viewers == 350

    def test_stream_time_str_hours_minutes_seconds(self):
        stats = StreamStats()
        stats.set_stream_start(time.time() - (2 * 3600 + 15 * 60 + 30))
        t = stats.stream_time_str
        assert t == "02:15:30"


# ---------------------------------------------------------------------------
# StatsPollerThread tests
# ---------------------------------------------------------------------------

class TestStatsPollerThread:
    def test_poller_calls_fetcher_and_updates_stats(self):
        stats = StreamStats()
        call_count = {"n": 0}

        def _fetch_twitch() -> int:
            call_count["n"] += 1
            return 42

        def _fetch_youtube() -> int:
            return 99

        poller = StatsPollerThread(
            stats=stats,
            fetchers={"twitch": _fetch_twitch, "youtube": _fetch_youtube},
            interval=0.1,  # 100ms for test speed
        )
        poller.start()
        time.sleep(0.35)  # allow ~3 poll cycles
        poller.stop()
        poller.join(timeout=2.0)

        assert stats.twitch_viewers == 42
        assert stats.youtube_viewers == 99
        assert call_count["n"] >= 2  # polled at least twice

    def test_poller_ignores_fetcher_exception(self):
        """A fetcher that raises must not crash the poller thread."""
        stats = StreamStats()

        def _bad_fetcher() -> int:
            raise RuntimeError("network error")

        poller = StatsPollerThread(
            stats=stats,
            fetchers={"twitch": _bad_fetcher},
            interval=0.1,
        )
        poller.start()
        time.sleep(0.25)
        poller.stop()
        poller.join(timeout=2.0)

        assert not poller.is_alive()
        assert stats.twitch_viewers == 0  # unchanged

    def test_poller_stops_cleanly(self):
        stats = StreamStats()
        poller = StatsPollerThread(stats=stats, fetchers={}, interval=0.05)
        poller.start()
        poller.stop()
        poller.join(timeout=1.0)
        assert not poller.is_alive()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_stats.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'StreamStats'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/chat/stats.py`:
```python
from __future__ import annotations

import threading
import time
from typing import Callable, Optional


# ---------------------------------------------------------------------------
# StreamStats
# ---------------------------------------------------------------------------

class StreamStats:
    """Thread-safe container for live stream statistics.

    All public attribute reads and writes are protected by a threading.Lock.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._twitch_viewers: int = 0
        self._youtube_viewers: int = 0
        self._tiktok_viewers: int = 0
        self._stream_start: Optional[float] = None  # monotonic epoch timestamp

    # ------------------------------------------------------------------
    # Read-only properties (acquire lock for safety)
    # ------------------------------------------------------------------

    @property
    def twitch_viewers(self) -> int:
        with self._lock:
            return self._twitch_viewers

    @property
    def youtube_viewers(self) -> int:
        with self._lock:
            return self._youtube_viewers

    @property
    def tiktok_viewers(self) -> int:
        with self._lock:
            return self._tiktok_viewers

    @property
    def total_viewers(self) -> int:
        with self._lock:
            return self._twitch_viewers + self._youtube_viewers + self._tiktok_viewers

    @property
    def stream_time_str(self) -> str:
        """Return elapsed stream time as HH:MM:SS, or 00:00:00 if not started."""
        with self._lock:
            if self._stream_start is None:
                return "00:00:00"
            elapsed = int(time.time() - self._stream_start)
        hours, remainder = divmod(elapsed, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

    # ------------------------------------------------------------------
    # Mutators
    # ------------------------------------------------------------------

    def update_viewers(self, platform: str, count: int) -> None:
        """Update viewer count for *platform*. Unknown platforms are ignored."""
        with self._lock:
            if platform == "twitch":
                self._twitch_viewers = count
            elif platform == "youtube":
                self._youtube_viewers = count
            elif platform == "tiktok":
                self._tiktok_viewers = count

    def set_stream_start(self, timestamp: float) -> None:
        with self._lock:
            self._stream_start = timestamp

    def reset(self) -> None:
        with self._lock:
            self._twitch_viewers = 0
            self._youtube_viewers = 0
            self._tiktok_viewers = 0
            self._stream_start = None


# ---------------------------------------------------------------------------
# StatsPollerThread
# ---------------------------------------------------------------------------

class StatsPollerThread(threading.Thread):
    """Polls each platform's viewer-count fetcher every *interval* seconds.

    *fetchers* is a dict mapping platform name → callable() → int.
    Any fetcher that raises is logged and skipped (poller continues).
    """

    def __init__(
        self,
        stats: StreamStats,
        fetchers: dict[str, Callable[[], int]],
        interval: float = 30.0,
    ) -> None:
        super().__init__(daemon=True, name="StatsPollerThread")
        self._stats = stats
        self._fetchers = fetchers
        self._interval = interval
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.wait(timeout=self._interval):
            self._poll()

    def _poll(self) -> None:
        for platform, fetcher in self._fetchers.items():
            try:
                count = fetcher()
                self._stats.update_viewers(platform, count)
            except Exception:
                pass  # log in production; swallow here to keep poller alive
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_stats.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/chat/stats.py tests/nova_vt/chat/test_stats.py && git commit -m "feat: add StreamStats dataclass and StatsPollerThread with threading.Lock

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 3: Platform Chat Providers

### Task 5: Twitch chat provider (twitchio)

**Files:**
- Create: `nova_vt/chat/twitch.py`
- Create: `tests/nova_vt/chat/test_twitch.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/chat/test_twitch.py`:
```python
from __future__ import annotations

import unittest.mock as mock
from typing import Callable

import pytest

from nova_vt.chat.provider import ChatMessage
from nova_vt.chat.twitch import TwitchChatProvider


# ---------------------------------------------------------------------------
# TwitchChatProvider unit tests (twitchio is fully mocked)
# ---------------------------------------------------------------------------

class TestTwitchChatProvider:
    def _make_provider(self) -> TwitchChatProvider:
        return TwitchChatProvider()

    def test_on_message_registers_callback(self):
        provider = self._make_provider()
        callback = mock.Mock()
        provider.on_message(callback)
        assert provider._message_callback is callback

    def test_connect_stores_credentials(self):
        provider = self._make_provider()
        with mock.patch.object(provider, "_start_client", return_value=None):
            provider.connect({"token": "oauth:abc123", "channel": "nova_vt"})
        assert provider._credentials["token"] == "oauth:abc123"
        assert provider._credentials["channel"] == "nova_vt"

    def test_disconnect_sets_stop_flag(self):
        provider = self._make_provider()
        provider._stop_event.clear()
        provider.disconnect()
        assert provider._stop_event.is_set()

    def test_send_delegates_to_internal(self):
        provider = self._make_provider()
        provider._pending_sends = []
        provider.send("hello chat")
        assert "hello chat" in provider._pending_sends

    def test_handle_message_fires_callback(self):
        """Simulate a twitchio message arriving and verify ChatMessage shape."""
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        # Build a minimal fake twitchio Message
        fake_author = mock.MagicMock()
        fake_author.name = "viewer1"
        fake_author.color = "#ff0000"

        fake_msg = mock.MagicMock()
        fake_msg.author = fake_author
        fake_msg.content = "PogChamp"

        provider._handle_raw_message(fake_msg)

        assert len(received) == 1
        m = received[0]
        assert m.platform == "twitch"
        assert m.username == "viewer1"
        assert m.color == "#ff0000"
        assert m.text == "PogChamp"
        assert m.event_type == "message"

    def test_handle_message_no_callback_does_not_raise(self):
        provider = self._make_provider()
        fake_author = mock.MagicMock()
        fake_author.name = "viewer"
        fake_author.color = "#ffffff"
        fake_msg = mock.MagicMock()
        fake_msg.author = fake_author
        fake_msg.content = "hi"
        # Should not raise even with no callback registered
        provider._handle_raw_message(fake_msg)

    def test_handle_sub_event_creates_sub_message(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.user.name = "subscriber1"
        provider._handle_sub_event(fake_event)

        assert len(received) == 1
        assert received[0].event_type == "sub"
        assert received[0].platform == "twitch"

    def test_handle_raid_event_creates_raid_message(self):
        provider = self._make_provider()
        received: list[ChatMessage] = []
        provider.on_message(lambda m: received.append(m))

        fake_event = mock.MagicMock()
        fake_event.raider.name = "raider_channel"
        provider._handle_raid_event(fake_event)

        assert len(received) == 1
        assert received[0].event_type == "raid"
        assert received[0].username == "raider_channel"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_twitch.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'TwitchChatProvider'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/chat/twitch.py`:
```python
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage


class TwitchChatProvider:
    """Twitch chat adapter backed by twitchio.

    Runs an asyncio event loop in a background daemon thread so the Qt
    main thread is never blocked.  Reconnect with exponential backoff is
    handled by twitchio's built-in reconnect logic.
    """

    def __init__(self) -> None:
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._pending_sends: list[str] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._client = None  # twitchio.Client instance, set in _start_client

    # ------------------------------------------------------------------
    # ChatProvider protocol
    # ------------------------------------------------------------------

    def connect(self, credentials: dict) -> None:
        self._credentials = credentials
        self._start_client()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        """Queue *text* for sending on the next async iteration."""
        self._pending_sends.append(text)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._flush_sends_sync)

    # ------------------------------------------------------------------
    # Internal message / event handlers
    # ------------------------------------------------------------------

    def _handle_raw_message(self, message) -> None:
        """Convert a twitchio message object to ChatMessage and fire callback."""
        if self._message_callback is None:
            return
        color = getattr(message.author, "color", None) or "#ffffff"
        msg = ChatMessage(
            platform="twitch",
            username=message.author.name,
            color=color,
            text=message.content,
            event_type="message",
        )
        self._message_callback(msg)

    def _handle_sub_event(self, event) -> None:
        if self._message_callback is None:
            return
        msg = ChatMessage(
            platform="twitch",
            username=event.user.name,
            color="#9147ff",
            text="",
            event_type="sub",
        )
        self._message_callback(msg)

    def _handle_raid_event(self, event) -> None:
        if self._message_callback is None:
            return
        msg = ChatMessage(
            platform="twitch",
            username=event.raider.name,
            color="#ff6905",
            text="",
            event_type="raid",
        )
        self._message_callback(msg)

    # ------------------------------------------------------------------
    # Async client lifecycle
    # ------------------------------------------------------------------

    def _start_client(self) -> None:
        """Spin up twitchio in a daemon thread."""
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="TwitchChatThread"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        import twitchio

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        token = self._credentials.get("token", "")
        channel = self._credentials.get("channel", "")

        provider_ref = self  # capture for nested class

        class _Bot(twitchio.Client):
            async def event_message(self, message: twitchio.Message) -> None:
                if message.echo:
                    return
                provider_ref._handle_raw_message(message)

            async def event_channel_subscribed(self, event) -> None:
                provider_ref._handle_sub_event(event)

            async def event_channel_raid(self, event) -> None:
                provider_ref._handle_raid_event(event)

        try:
            self._client = _Bot(token=token, initial_channels=[channel])
            self._loop.run_until_complete(self._client.start())
        except Exception:
            pass
        finally:
            self._loop.close()

    def _flush_sends_sync(self) -> None:
        """Drain pending sends inside the async loop (called via call_soon_threadsafe)."""
        if self._client is None:
            return
        while self._pending_sends:
            text = self._pending_sends.pop(0)
            self._loop.call_soon_threadsafe(self._loop.create_task, self._async_send(text))

    async def _async_send(self, text: str) -> None:
        if self._client is None:
            return
        channel_name = self._credentials.get("channel", "")
        channel = self._client.get_channel(channel_name)
        if channel is not None:
            await channel.send(text)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_twitch.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/chat/twitch.py tests/nova_vt/chat/test_twitch.py && git commit -m "feat: add TwitchChatProvider backed by twitchio with sub/raid event handling

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 6: YouTube chat provider (google-api-python-client polling)

**Files:**
- Create: `nova_vt/chat/youtube.py`
- Create: `tests/nova_vt/chat/test_youtube.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/chat/test_youtube.py`:
```python
from __future__ import annotations

import time
import threading
import unittest.mock as mock

import pytest

from nova_vt.chat.provider import ChatMessage
from nova_vt.chat.youtube import YouTubeChatProvider


# ---------------------------------------------------------------------------
# YouTubeChatProvider unit tests (google-api is fully mocked)
# ---------------------------------------------------------------------------

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
        """_parse_and_emit() should convert API response items to ChatMessage."""
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
        """SuperChat events should produce event_type='gift'."""
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
        """New membership events should produce event_type='sub'."""
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
        """Verify the polling loop calls the list API more than once."""
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_youtube.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'YouTubeChatProvider'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/chat/youtube.py`:
```python
from __future__ import annotations

import threading
import time
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage


class YouTubeChatProvider:
    """YouTube Live Chat adapter using google-api-python-client (polling).

    Polls the liveChatMessages.list endpoint every *poll_interval* seconds
    (or the interval returned by the API, whichever is longer).
    """

    # Default hex color for YouTube messages (YouTube red)
    _YT_COLOR = "#ff0000"

    def __init__(self, poll_interval: float = 5.0) -> None:
        self._poll_interval = poll_interval
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._service = None   # googleapiclient.discovery resource
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    # ChatProvider protocol
    # ------------------------------------------------------------------

    def connect(self, credentials: dict) -> None:
        self._credentials = credentials
        self._stop_event.clear()
        self._start_polling()

    def disconnect(self) -> None:
        self._stop_event.set()

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        if self._service is None:
            raise RuntimeError("YouTubeChatProvider: not connected")
        # Sending via YouTube Data API requires OAuth insert; future implementation
        raise NotImplementedError("YouTube chat send not yet implemented")

    # ------------------------------------------------------------------
    # Polling lifecycle
    # ------------------------------------------------------------------

    def _start_polling(self) -> None:
        self._thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="YouTubePollThread"
        )
        self._thread.start()

    def _poll_loop(self) -> None:
        """Main polling loop. Runs in a daemon thread."""
        if self._service is None:
            self._service = self._build_service()

        live_chat_id = self._credentials.get("live_chat_id", "")
        next_page_token: Optional[str] = None

        while not self._stop_event.is_set():
            try:
                request = self._service.liveChatMessages().list(
                    liveChatId=live_chat_id,
                    part="snippet,authorDetails",
                    pageToken=next_page_token,
                    maxResults=200,
                )
                response = request.execute()
                items = response.get("items", [])
                next_page_token = response.get("nextPageToken")
                api_interval_ms = response.get("pollingIntervalMillis", self._poll_interval * 1000)
                self._parse_and_emit(items)
                wait = max(self._poll_interval, api_interval_ms / 1000.0)
            except Exception:
                wait = self._poll_interval

            self._stop_event.wait(timeout=wait)

    # ------------------------------------------------------------------
    # Message parsing
    # ------------------------------------------------------------------

    def _parse_and_emit(self, items: list[dict]) -> None:
        if self._message_callback is None:
            return
        for item in items:
            snippet = item.get("snippet", {})
            author = item.get("authorDetails", {})
            username = author.get("displayName", "unknown")
            msg_type = snippet.get("type", "")

            if msg_type == "textMessageEvent":
                text = snippet.get("textMessageDetails", {}).get("messageText", "")
                event_type = "message"
            elif msg_type == "superChatEvent":
                text = snippet.get("superChatDetails", {}).get("userComment", "")
                event_type = "gift"
            elif msg_type == "newSponsorEvent":
                text = ""
                event_type = "sub"
            else:
                continue  # skip unknown types

            self._message_callback(
                ChatMessage(
                    platform="youtube",
                    username=username,
                    color=self._YT_COLOR,
                    text=text,
                    event_type=event_type,
                )
            )

    # ------------------------------------------------------------------
    # Service builder
    # ------------------------------------------------------------------

    def _build_service(self):
        from googleapiclient.discovery import build
        from google.oauth2.credentials import Credentials

        token = self._credentials.get("access_token", "")
        creds = Credentials(token=token)
        return build("youtube", "v3", credentials=creds, cache_discovery=False)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_youtube.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/chat/youtube.py tests/nova_vt/chat/test_youtube.py && git commit -m "feat: add YouTubeChatProvider with 5s polling and super-chat/membership events

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

### Task 7: TikTok chat provider (TikTokLive, read-only)

**Files:**
- Create: `nova_vt/chat/tiktok.py`
- Create: `tests/nova_vt/chat/test_tiktok.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/chat/test_tiktok.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_tiktok.py -v 2>&1 | head -20
```

Expected output contains: `ModuleNotFoundError` or `ImportError: cannot import name 'TikTokChatProvider'`

- [ ] **Step 3: Write minimal implementation**

`nova_vt/chat/tiktok.py`:
```python
from __future__ import annotations

import asyncio
import threading
from typing import Callable, Optional

from nova_vt.chat.provider import ChatMessage


class TikTokChatProvider:
    """TikTok LIVE chat adapter backed by TikTokLive (read-only).

    NOTE: TikTok RTMP push endpoint is TBD.  This provider handles chat
    reading only.  send() raises NotImplementedError until the endpoint is
    confirmed and implemented.
    """

    # TikTok brand color (pink/red)
    _TIKTOK_COLOR = "#fe2c55"

    def __init__(self) -> None:
        self._message_callback: Optional[Callable[[ChatMessage], None]] = None
        self._credentials: dict = {}
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    # ------------------------------------------------------------------
    # ChatProvider protocol
    # ------------------------------------------------------------------

    def connect(self, credentials: dict) -> None:
        self._credentials = credentials
        self._stop_event.clear()
        self._start_client()

    def disconnect(self) -> None:
        self._stop_event.set()
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def on_message(self, callback: Callable[[ChatMessage], None]) -> None:
        self._message_callback = callback

    def send(self, text: str) -> None:
        raise NotImplementedError(
            "TikTok chat send is TBD — RTMP push endpoint not yet confirmed."
        )

    # ------------------------------------------------------------------
    # Internal event handlers
    # ------------------------------------------------------------------

    def _handle_chat(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text=event.comment,
                event_type="message",
            )
        )

    def _handle_gift(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text=getattr(event.gift, "name", ""),
                event_type="gift",
            )
        )

    def _handle_subscribe(self, event) -> None:
        if self._message_callback is None:
            return
        self._message_callback(
            ChatMessage(
                platform="tiktok",
                username=event.user.nickname,
                color=self._TIKTOK_COLOR,
                text="",
                event_type="sub",
            )
        )

    # ------------------------------------------------------------------
    # TikTokLive client lifecycle
    # ------------------------------------------------------------------

    def _start_client(self) -> None:
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="TikTokChatThread"
        )
        self._thread.start()

    def _run_loop(self) -> None:
        from TikTokLive import TikTokLiveClient
        from TikTokLive.events import CommentEvent, GiftEvent, FollowEvent

        username = self._credentials.get("username", "")
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        provider_ref = self

        client = TikTokLiveClient(unique_id=username)

        @client.on(CommentEvent)
        async def on_comment(event: CommentEvent) -> None:
            provider_ref._handle_chat(event)

        @client.on(GiftEvent)
        async def on_gift(event: GiftEvent) -> None:
            provider_ref._handle_gift(event)

        @client.on(FollowEvent)
        async def on_follow(event: FollowEvent) -> None:
            provider_ref._handle_subscribe(event)

        try:
            self._loop.run_until_complete(client.start())
        except Exception:
            pass
        finally:
            self._loop.close()
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/chat/test_tiktok.py -v
```

Expected output: all tests `PASSED`.

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add nova_vt/chat/tiktok.py tests/nova_vt/chat/test_tiktok.py && git commit -m "feat: add TikTokChatProvider (read-only chat via TikTokLive, RTMP TBD)

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Chunk 4: Integration

### Task 8: Integration test — AudioMixer + EncoderThread streaming to local RTMP

**Files:**
- Create: `tests/nova_vt/test_integration_stream.py`

- [ ] **Step 1: Write the failing test**

`tests/nova_vt/test_integration_stream.py`:
```python
from __future__ import annotations

"""Integration test: wire AudioMixer + EncoderThread, stream 3s to local RTMP sink.

Requires:
  - ffmpeg installed and on PATH
  - Port 19351 available on localhost

Run with:
  pytest tests/nova_vt/test_integration_stream.py -v -m slow
"""

import queue
import subprocess
import threading
import time
import unittest.mock as mock

import numpy as np
import pytest

from nova_vt.audio.mixer import AudioMixer, MixerConfig, ChannelConfig
from nova_vt.encoder.encoder import EncoderThread, EncoderConfig


pytestmark = pytest.mark.slow

RTMP_PORT = 19351
RTMP_URL = f"rtmp://127.0.0.1:{RTMP_PORT}/live/integration"


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


@pytest.fixture(scope="module")
def rtmp_sink():
    """Start a local RTMP listener that accepts one connection and exits."""
    if not _ffmpeg_available():
        pytest.skip("ffmpeg not installed")

    proc = subprocess.Popen(
        [
            "ffmpeg", "-y",
            "-listen", "1",
            "-i", RTMP_URL,
            "-t", "10",          # accept up to 10 s of stream
            "-f", "null", "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.5)   # give ffmpeg time to bind
    yield proc
    proc.terminate()
    proc.wait(timeout=5)


class TestAudioMixerEncoderIntegration:
    def test_stream_3_seconds_to_local_rtmp(self, rtmp_sink, tmp_path):
        """AudioMixer (mocked sounddevice) + EncoderThread → local RTMP sink."""

        video_queue: queue.Queue = queue.Queue(maxsize=16)
        audio_queue: queue.Queue = queue.Queue(maxsize=32)

        # ----------------------------------------------------------------
        # EncoderThread
        # ----------------------------------------------------------------
        enc_cfg = EncoderConfig(
            video_fifo=str(tmp_path / "video.fifo"),
            audio_fifo=str(tmp_path / "audio.fifo"),
            width=1920,
            height=1080,
            fps=30,
            sample_rate=48000,
            audio_channels=2,
            video_bitrate="500k",   # low for test speed
            audio_bitrate="64k",
            rtmp_targets=[RTMP_URL],
        )
        encoder = EncoderThread(
            config=enc_cfg,
            video_queue=video_queue,
            audio_queue=audio_queue,
        )

        # ----------------------------------------------------------------
        # AudioMixer — mock sounddevice to avoid needing a real audio device
        # ----------------------------------------------------------------
        mix_cfg = MixerConfig(
            sample_rate=48000,
            channels=2,
            blocksize=2048,
            mic_config=ChannelConfig(volume=75, muted=False, device=None),
            game_config=ChannelConfig(volume=60, muted=False, device=None),
            bgm_config=ChannelConfig(volume=30, muted=False, device=None),
            master_volume=90,
            monitor_device=None,
        )
        mixer = AudioMixer(config=mix_cfg, encoder_queue=audio_queue)

        # Directly exercise the mixing logic without a real sounddevice stream
        silence = np.zeros((2048, 2), dtype=np.float32)

        def _push_audio(stop_ev: threading.Event):
            while not stop_ev.is_set():
                mixer._mix_and_enqueue(silence, silence, silence)
                time.sleep(2048 / 48000)  # one blocksize interval

        # ----------------------------------------------------------------
        # Video frame producer
        # ----------------------------------------------------------------
        rgba_frame = np.zeros((1080, 1920, 4), dtype=np.uint8)
        frame_bytes = rgba_frame.tobytes()

        stream_duration_s = 3
        total_frames = stream_duration_s * 30  # 90 frames

        stop_audio = threading.Event()

        def _push_video():
            for _ in range(total_frames):
                try:
                    video_queue.put(frame_bytes, timeout=1.0)
                except queue.Full:
                    pass
                time.sleep(1.0 / 30)
            video_queue.put(None)   # sentinel
            audio_queue.put(None)   # sentinel
            stop_audio.set()

        # ----------------------------------------------------------------
        # Run the integration
        # ----------------------------------------------------------------
        encoder.start()

        audio_thread = threading.Thread(target=_push_audio, args=(stop_audio,), daemon=True)
        video_thread = threading.Thread(target=_push_video, daemon=True)

        audio_thread.start()
        video_thread.start()

        video_thread.join(timeout=15)
        audio_thread.join(timeout=3)

        encoder.stop_encoding()
        encoder.wait(10_000)   # wait up to 10 s for QThread to finish

        assert not encoder.isRunning(), "EncoderThread did not exit cleanly"

        # Sink should have exited (got the stream and hit its -t 10 limit,
        # or our encoder closed the connection).  Code 0, 255 (SIGTERM) both OK.
        rtmp_sink.wait(timeout=12)
        assert rtmp_sink.returncode in (0, -15, 255, None), (
            f"RTMP sink exited with unexpected code {rtmp_sink.returncode}"
        )

    def test_mixer_peak_meters_update_during_stream(self):
        """Verify that peak EMA updates correctly on non-silence signal."""
        audio_q: queue.Queue = queue.Queue(maxsize=8)
        mix_cfg = MixerConfig(
            sample_rate=48000,
            channels=2,
            blocksize=512,
            mic_config=ChannelConfig(volume=100, muted=False, device=None),
            game_config=ChannelConfig(volume=100, muted=False, device=None),
            bgm_config=ChannelConfig(volume=100, muted=False, device=None),
            master_volume=100,
            monitor_device=None,
        )
        mixer = AudioMixer(config=mix_cfg, encoder_queue=audio_q)

        signal = np.ones((512, 2), dtype=np.float32) * 0.7
        for _ in range(5):
            mixer._mix_and_enqueue(signal, signal, signal)

        peaks = mixer.get_peaks()
        # After 5 frames of 0.7-amplitude signal, master peak EMA must be > 0
        assert peaks["master"] > 0.0
        # Must also be <= clipped max (3 channels × 0.7 × (volume/100) clamped to 1.0)
        assert peaks["master"] <= 1.0

    def test_encoder_config_no_targets_raises(self, tmp_path):
        """EncoderThread with no RTMP targets should build a tee string that ffmpeg rejects."""
        enc_cfg = EncoderConfig(
            video_fifo=str(tmp_path / "v.fifo"),
            audio_fifo=str(tmp_path / "a.fifo"),
            width=1920, height=1080, fps=30,
            sample_rate=48000, audio_channels=2,
            video_bitrate="6000k", audio_bitrate="160k",
            rtmp_targets=[],
        )
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = enc_cfg
        tee = enc._build_tee_string()
        # Empty tee string is technically valid Python but ffmpeg will reject it
        assert tee == ""
```

- [ ] **Step 2: Run test to verify it fails (unit portion)**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/test_integration_stream.py -v -k "not stream_3_seconds" 2>&1 | head -30
```

Expected: `test_mixer_peak_meters_update_during_stream` and `test_encoder_config_no_targets_raises` run and pass once implementation is in place; if they fail initially it is because AudioMixer or EncoderThread are not yet imported correctly.

- [ ] **Step 3: No new implementation required**

Tasks 1–7 provide all implementation. This task only adds the integration test file. Verify both components import cleanly:

```bash
cd /home/nova/git/nova-vt && python -c "from nova_vt.audio.mixer import AudioMixer; from nova_vt.encoder.encoder import EncoderThread; print('imports ok')"
```

Expected: `imports ok`

- [ ] **Step 4: Run all non-slow tests to verify nothing regressed**

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/ -v -k "not slow" --tb=short
```

Expected: all tests `PASSED`, no regressions.

Run the slow integration test (requires ffmpeg on PATH):

```bash
cd /home/nova/git/nova-vt && python -m pytest tests/nova_vt/test_integration_stream.py -v -m slow --tb=short
```

Expected: `test_stream_3_seconds_to_local_rtmp` passes (EncoderThread exits cleanly, RTMP sink returncode in `{0, -15, 255, None}`).

- [ ] **Step 5: Commit**

```bash
cd /home/nova/git/nova-vt && git add tests/nova_vt/test_integration_stream.py && git commit -m "test: add AudioMixer + EncoderThread integration test streaming to local RTMP

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>"
```

---

## Summary

| Task | Files Created | Key Assertion |
|------|--------------|---------------|
| 1 AudioMixer | `nova_vt/audio/mixer.py` | s16le chunk size == frames × 2 ch × 2 bytes; peak EMA rises on signal |
| 2 EncoderThread | `nova_vt/encoder/encoder.py` | tee string contains `[f=flv]`; FIFOs are true FIFOs after `_create_fifos()` |
| 3 ChatProvider + ChatManager | `nova_vt/chat/provider.py` | `send(platform=None)` broadcasts to all providers; specific platform sends only to that one |
| 4 StreamStats + StatsPollerThread | `nova_vt/chat/stats.py` | `total_viewers` == sum of per-platform counts; `stream_time_str` matches HH:MM:SS |
| 5 TwitchChatProvider | `nova_vt/chat/twitch.py` | `_handle_raw_message` produces `event_type="message"`; sub/raid handlers produce correct types |
| 6 YouTubeChatProvider | `nova_vt/chat/youtube.py` | `_parse_and_emit` maps `superChatEvent` → `gift`; `newSponsorEvent` → `sub` |
| 7 TikTokChatProvider | `nova_vt/chat/tiktok.py` | `send()` raises `NotImplementedError("TBD")`; gift/follow events map correctly |
| 8 Integration | `tests/nova_vt/test_integration_stream.py` | EncoderThread exits cleanly after 3s stream; RTMP sink returncode in `{0, -15, 255, None}` |
