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


FIFO_VIDEO = "/tmp/nova-vt-test-video.fifo"
FIFO_AUDIO = "/tmp/nova-vt-test-audio.fifo"


def _make_config(rtmp_url: str = "rtmp://localhost:1935/live/test") -> EncoderConfig:
    return EncoderConfig(
        video_fifo=FIFO_VIDEO,
        audio_fifo=FIFO_AUDIO,
        width=1920, height=1080, fps=30,
        sample_rate=48000, audio_channels=2,
        video_bitrate="6000k", audio_bitrate="160k",
        rtmp_targets=[rtmp_url],
    )


class TestEncoderConfig:
    def test_tee_string_single_target(self):
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = _make_config("rtmp://live.twitch.tv/app/mykey")
        assert enc._build_tee_string() == "[f=flv]rtmp://live.twitch.tv/app/mykey"

    def test_tee_string_multiple_targets(self):
        cfg = EncoderConfig(
            video_fifo=FIFO_VIDEO, audio_fifo=FIFO_AUDIO,
            width=1920, height=1080, fps=30,
            sample_rate=48000, audio_channels=2,
            video_bitrate="6000k", audio_bitrate="160k",
            rtmp_targets=["rtmp://live.twitch.tv/app/k1", "rtmp://a.rtmp.youtube.com/live2/k2"],
        )
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = cfg
        tee = enc._build_tee_string()
        assert "[f=flv]rtmp://live.twitch.tv/app/k1" in tee
        assert "[f=flv]rtmp://a.rtmp.youtube.com/live2/k2" in tee
        assert "|" in tee

    def test_ffmpeg_args_structure(self):
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = _make_config()
        args = enc._build_ffmpeg_args()
        assert args[0] == "ffmpeg"
        assert FIFO_VIDEO in args
        assert FIFO_AUDIO in args
        assert "rawvideo" in args
        assert "s16le" in args
        assert "libx264" in args
        assert "aac" in args
        tee_idx = [i for i, a in enumerate(args) if a == "-f" and i+1 < len(args) and args[i+1] == "tee"]
        assert len(tee_idx) >= 1


class TestFifoLifecycle:
    def test_create_fifos_removes_stale(self, tmp_path):
        vf = str(tmp_path / "video.fifo")
        af = str(tmp_path / "audio.fifo")
        Path(vf).write_bytes(b"stale")
        Path(af).write_bytes(b"stale")
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = EncoderConfig(
            video_fifo=vf, audio_fifo=af,
            width=1920, height=1080, fps=30,
            sample_rate=48000, audio_channels=2,
            video_bitrate="6000k", audio_bitrate="160k",
            rtmp_targets=["rtmp://localhost/live/test"],
        )
        enc._create_fifos()
        import stat
        assert stat.S_ISFIFO(os.stat(vf).st_mode)
        assert stat.S_ISFIFO(os.stat(af).st_mode)
        enc._unlink_fifos()
        assert not Path(vf).exists()
        assert not Path(af).exists()

    def test_create_fifos_ok_when_not_exist(self, tmp_path):
        vf = str(tmp_path / "v.fifo")
        af = str(tmp_path / "a.fifo")
        enc = EncoderThread.__new__(EncoderThread)
        enc._config = EncoderConfig(
            video_fifo=vf, audio_fifo=af,
            width=1920, height=1080, fps=30,
            sample_rate=48000, audio_channels=2,
            video_bitrate="6000k", audio_bitrate="160k",
            rtmp_targets=["rtmp://localhost/live/test"],
        )
        enc._create_fifos()
        import stat
        assert stat.S_ISFIFO(os.stat(vf).st_mode)
        assert stat.S_ISFIFO(os.stat(af).st_mode)
        enc._unlink_fifos()
