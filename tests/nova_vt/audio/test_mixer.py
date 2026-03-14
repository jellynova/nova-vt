from __future__ import annotations

import queue
import time
import unittest.mock as mock

import numpy as np
import pytest

from nova_vt.audio.mixer import AudioMixer, ChannelConfig, MixerConfig


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


class TestAudioMixerPeakMeter:
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
    def test_mix_produces_s16le_bytes(self):
        encoder_q: queue.Queue[bytes] = queue.Queue(maxsize=4)
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._encoder_queue = encoder_q
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        mixer._config = _make_config()
        mixer._lock = __import__("threading").Lock()

        mic = np.zeros((2048, 2), dtype=np.float32)
        game = np.zeros((2048, 2), dtype=np.float32)
        bgm = np.zeros((2048, 2), dtype=np.float32)
        mixer._mix_and_enqueue(mic, game, bgm)

        assert not encoder_q.empty()
        chunk = encoder_q.get_nowait()
        assert isinstance(chunk, (bytes, bytearray))
        assert len(chunk) == 2048 * 2 * 2  # s16le: 2 bytes × 2 channels × 2048 frames

    def test_full_encoder_queue_drops_chunk(self):
        encoder_q: queue.Queue[bytes] = queue.Queue(maxsize=1)
        encoder_q.put_nowait(b"sentinel")
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._encoder_queue = encoder_q
        mixer._peak_ema = {"mic": 0.0, "game": 0.0, "bgm": 0.0, "master": 0.0}
        mixer._config = _make_config()
        mixer._lock = __import__("threading").Lock()

        mic = np.zeros((2048, 2), dtype=np.float32)
        game = np.zeros((2048, 2), dtype=np.float32)
        bgm = np.zeros((2048, 2), dtype=np.float32)
        mixer._mix_and_enqueue(mic, game, bgm)

        assert encoder_q.get_nowait() == b"sentinel"


class TestAudioMixerPeakAPI:
    def test_get_peaks_returns_all_channels(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._peak_ema = {"mic": 0.3, "game": 0.5, "bgm": 0.1, "master": 0.4}
        mixer._lock = __import__("threading").Lock()
        peaks = mixer.get_peaks()
        assert set(peaks.keys()) == {"mic", "game", "bgm", "master"}
        assert peaks["game"] == pytest.approx(0.5)


class TestAudioMixerSetVolume:
    def test_set_volume_clamps_to_0_100(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer._lock = __import__("threading").Lock()
        mixer.set_volume("mic", 150)
        assert mixer._config.mic_config.volume == 100

    def test_set_volume_below_zero_clamps(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer._lock = __import__("threading").Lock()
        mixer.set_volume("mic", -5)
        assert mixer._config.mic_config.volume == 0

    def test_set_mute_toggles_channel(self):
        mixer = AudioMixer.__new__(AudioMixer)
        mixer._config = _make_config()
        mixer._lock = __import__("threading").Lock()
        mixer.set_mute("game", True)
        assert mixer._config.game_config.muted is True
        mixer.set_mute("game", False)
        assert mixer._config.game_config.muted is False
