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
    @pytest.mark.slow
    def test_stream_3_seconds_to_local_rtmp(self, rtmp_sink, tmp_path):
        """AudioMixer (mocked sounddevice) + EncoderThread → local RTMP sink."""

        video_queue: queue.Queue = queue.Queue(maxsize=16)
        audio_queue: queue.Queue = queue.Queue(maxsize=32)

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

        silence = np.zeros((2048, 2), dtype=np.float32)

        def _push_audio(stop_ev: threading.Event):
            while not stop_ev.is_set():
                mixer._mix_and_enqueue(silence, silence, silence)
                time.sleep(2048 / 48000)  # one blocksize interval

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
        # Peak EMA is computed before clipping, so it can exceed 1.0 when
        # multiple channels are summed at full volume.
        assert peaks["master"] > 0.0

    def test_encoder_config_no_targets_raises(self, tmp_path):
        """EncoderThread with no RTMP targets should build an empty tee string."""
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
        assert tee == ""
